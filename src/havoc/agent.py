
"""LangGraph agent: classify -> (reason <-> tools)* -> report, plus the no-tools baseline."""

from __future__ import annotations

import json
import os
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from . import config
from .anomaly import analyze_metrics
from .catalog import taxonomy_text
from .retrieval import RunbookRetriever, get_embeddings
from .schemas import RCAReport, ToolCall, TriageResult
from .telemetry import TelemetryStore

MAX_STEPS = 5

AGENT_SYSTEM = """You are an SRE assistant investigating a production alert.
Use the available tools to gather evidence.
Always call get_metric_anomalies and search_logs first.
If search_runbooks is available, call it with a query built from the
strongest evidence, such as error messages and metric patterns.
Stop calling tools once you can identify the root cause."""

AGENT_NO_RAG_SYSTEM = """You are an SRE assistant investigating a production alert.
Use the available tools to gather evidence.
Always call get_metric_anomalies and search_logs first.
Do not call tools that are not available.
Stop calling tools once you can identify the root cause."""

REPORT_SYSTEM = (
    "You are an SRE assistant. Reply with a single JSON object and nothing else."
)

REPORT_PROMPT = """Alert: {alert}

{evidence}

Choose the single most likely root cause from this list:
{taxonomy}

Return JSON with exactly these keys:
root_cause_id (one id from the list), root_cause_summary (1-2 sentences),
confidence (0 to 1), evidence (list of short strings quoting the data above),
suggested_actions (list of short strings), runbooks_cited (list of doc ids like RB-01)."""


def classify_alert(alert: str) -> str:
    a = alert.lower()
    for key, label in (
        ("latency", "latency"),
        ("error rate", "error_rate"),
        ("cpu", "cpu"),
        ("memory", "memory"),
        ("disk", "disk"),
    ):
        if key in a:
            return label
    return "unknown"


def parse_rca(text: str) -> RCAReport:
    """Extract the JSON object from an LLM reply and validate it against the schema."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in reply")
    return RCAReport.model_validate(json.loads(text[start : end + 1]))


def _content_to_text(content: Any) -> str:
    """Normalize string or block-based model response content into text."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_text = block.get("text")
                if isinstance(block_text, str):
                    parts.append(block_text)
        return "\n".join(parts)

    return str(content)


def get_llm():
    """Create the configured Gemini chat model."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        google_api_key=api_key,
        temperature=0,
        max_retries=2,
        timeout=60,
    )


def build_tools(
    store: TelemetryStore,
    retriever: RunbookRetriever | None,
):
    @tool
    def get_metric_anomalies(incident_id: str) -> str:
        """Analyse CPU, memory, disk, latency, error rate, throughput and DB pool metrics for
        an incident. Reports which deviate from baseline, when they began and their shape."""
        return analyze_metrics(store.metrics(incident_id)).to_text()

    @tool
    def search_logs(incident_id: str, keyword: str = "") -> str:
        """Summarise WARN/ERROR log patterns from the last 60 minutes of an incident,
        grouped by message template with counts. Optionally filter by a keyword."""
        return store.log_patterns_text(incident_id, keyword)

    tools = [get_metric_anomalies, search_logs]

    if retriever is not None:

        @tool
        def search_runbooks(query: str) -> str:
            """Search runbooks and past postmortems. Query with symptoms or log messages."""
            hits = retriever.search(query, k=3)
            return "\n\n".join(
                f"[{hit.doc_id}] {hit.text[:600]}" for hit in hits
            )

        tools.append(search_runbooks)

    return tools


class AgentState(TypedDict):
    incident_id: str
    alert: str
    alert_type: str
    messages: Annotated[list[BaseMessage], add_messages]
    steps: int
    llm_calls: int
    trace: list[dict]
    rca: dict | None
    error: str | None


def _report_with_retry(
    llm,
    prompt: str,
) -> tuple[RCAReport | None, str | None, int]:
    msgs: list[BaseMessage] = [
        SystemMessage(content=REPORT_SYSTEM),
        HumanMessage(content=prompt),
    ]
    calls = 0
    err = None

    for _ in range(2):
        response = llm.invoke(msgs)
        text = _content_to_text(response.content)
        calls += 1

        try:
            return parse_rca(text), None, calls
        except Exception as exc:  # noqa: BLE001
            err = str(exc)[:300]
            msgs.extend(
                [
                    AIMessage(content=text),
                    HumanMessage(
                        content=(
                            f"Your previous response was invalid: {err}. "
                            "Return ONLY a corrected JSON object with the required keys."
                        )
                    ),
                ]
            )

    return None, f"invalid RCA JSON: {err}", calls


class TriageAgent:
    def __init__(
        self,
        llm,
        store: TelemetryStore,
        retriever: RunbookRetriever | None,
        use_rag: bool = True,
        max_steps: int = MAX_STEPS,
    ):
        self.llm = llm
        self.store = store
        self.max_steps = max_steps
        self.use_rag = use_rag

        effective_retriever = retriever if use_rag else None
        self.tools = {
            tool_obj.name: tool_obj
            for tool_obj in build_tools(store, effective_retriever)
        }
        self.llm_tools = llm.bind_tools(list(self.tools.values()))
        self.graph = self._build()

    def _classify(self, state: AgentState) -> dict:
        return {"alert_type": classify_alert(state["alert"])}

    
    def _reason(self, state: AgentState) -> dict:
        response = self.llm_tools.invoke(state["messages"])

        # Gemini may request a tool that is not registered.
        # Convert unavailable tool calls into a normal assistant message.
        if isinstance(response, AIMessage) and response.tool_calls:
            unavailable = [
                call["name"]
                for call in response.tool_calls
                if call["name"] not in self.tools
            ]

            if unavailable:
                response = AIMessage(
                    content=(
                        "Some requested tools are unavailable: "
                        + ", ".join(unavailable)
                        + ". Use only the available tool results to identify "
                        "the root cause and produce the final report."
                    )
                )

        return {
            "messages": [response],
            "steps": state["steps"] + 1,
            "llm_calls": state["llm_calls"] + 1,
        }


    def _route(self, state: AgentState) -> str:
        last = state["messages"][-1]
        wants_tools = isinstance(last, AIMessage) and bool(last.tool_calls)
        return (
            "tools"
            if wants_tools and state["steps"] < self.max_steps
            else "report"
        )

    def _tools(self, state: AgentState) -> dict:
        outputs = []
        trace = list(state["trace"])

        for call in state["messages"][-1].tool_calls:
            name = call["name"]

            try:
                if name not in self.tools:
                    raise ValueError(f"Tool is not available: {name}")

                result = str(self.tools[name].invoke(call["args"]))
            except Exception as exc:  # noqa: BLE001
                result = f"ERROR: {type(exc).__name__}: {exc}"

            outputs.append(
                ToolMessage(
                    content=result,
                    tool_call_id=call["id"],
                    name=name,
                )
            )
            trace.append(
                {
                    "name": name,
                    "args": call["args"],
                    "output_preview": result[:300],
                }
            )

        return {"messages": outputs, "trace": trace}

    def _report(self, state: AgentState) -> dict:
        evidence = "\n\n".join(
            f"## {message.name}\n{message.content}"
            for message in state["messages"]
            if isinstance(message, ToolMessage)
        ) or "(no tool evidence was gathered)"

        prompt = REPORT_PROMPT.format(
            alert=state["alert"],
            evidence=evidence,
            taxonomy=taxonomy_text(),
        )
        report, error, calls = _report_with_retry(self.llm, prompt)

        return {
            "rca": report.model_dump() if report else None,
            "error": error,
            "llm_calls": state["llm_calls"] + calls,
        }

    def _build(self):
        graph = StateGraph(AgentState)
        graph.add_node("classify", self._classify)
        graph.add_node("reason", self._reason)
        graph.add_node("tools", self._tools)
        graph.add_node("report", self._report)

        graph.add_edge(START, "classify")
        graph.add_edge("classify", "reason")
        graph.add_conditional_edges(
            "reason",
            self._route,
            {"tools": "tools", "report": "report"},
        )
        graph.add_edge("tools", "reason")
        graph.add_edge("report", END)

        return graph.compile()

    def run(
        self,
        incident_id: str,
        alert: str | None = None,
    ) -> TriageResult:
        start_time = time.time()
        alert = alert or self.store.get_incident(incident_id)["alert"]

        first_message = HumanMessage(
            content=f"Incident: {incident_id}\nAlert: {alert}"
        )
        system_prompt = AGENT_SYSTEM if self.use_rag else AGENT_NO_RAG_SYSTEM

        initial_state: dict[str, Any] = {
            "incident_id": incident_id,
            "alert": alert,
            "alert_type": "",
            "steps": 0,
            "llm_calls": 0,
            "trace": [],
            "rca": None,
            "error": None,
            "messages": [
                SystemMessage(content=system_prompt),
                first_message,
            ],
        }

        final_state = self.graph.invoke(initial_state)

        return TriageResult(
            incident_id=incident_id,
            rca=(
                RCAReport(**final_state["rca"])
                if final_state["rca"]
                else None
            ),
            error=final_state["error"],
            tool_calls=[
                ToolCall(**item) for item in final_state["trace"]
            ],
            llm_calls=final_state["llm_calls"],
            latency_s=round(time.time() - start_time, 2),
        )


class PlainLLMBaseline:
    """No retrieval or tools: the model sees only the alert and label list."""

    def __init__(self, llm):
        self.llm = llm

    def run(
        self,
        incident_id: str,
        alert: str | None = None,
    ) -> TriageResult:
        start_time = time.time()

        prompt = REPORT_PROMPT.format(
            alert=alert or "",
            evidence="(no telemetry or runbooks available)",
            taxonomy=taxonomy_text(),
        )
        report, error, calls = _report_with_retry(self.llm, prompt)

        return TriageResult(
            incident_id=incident_id,
            rca=report,
            error=error,
            llm_calls=calls,
            latency_s=round(time.time() - start_time, 2),
        )


def build_default_agent(use_rag: bool = True) -> TriageAgent:
    embeddings = get_embeddings()
    index_dir = config.index_dir()

    try:
        retriever = RunbookRetriever.load(index_dir, embeddings)
    except Exception:  # noqa: BLE001
        retriever = RunbookRetriever.build(config.data_dir(), embeddings)

    return TriageAgent(
        get_llm(),
        TelemetryStore(config.data_dir()),
        retriever,
        use_rag=use_rag,
    )
