import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from havoc.agent import PlainLLMBaseline, TriageAgent, classify_alert, parse_rca
from havoc.api import create_app
from tests.conftest import ScriptedLLM

GOOD = {
    "root_cause_id": "disk_full",
    "root_cause_summary": "The data volume is full so writes fail.",
    "confidence": 0.9,
    "evidence": ["No space left on device"],
    "suggested_actions": ["Free disk space"],
    "runbooks_cited": ["RB-05"],
}


def calls(*names, inc="INC-001"):
    args = {"get_metric_anomalies": {"incident_id": inc}, "search_logs": {"incident_id": inc},
            "search_runbooks": {"query": "no space left on device"}}
    return AIMessage(content="", tool_calls=[
        {"name": n, "args": args[n], "id": f"c{i}"} for i, n in enumerate(names)])


def test_parse_rca_handles_code_fences_and_rejects_bad_labels():
    assert parse_rca("```json\n" + json.dumps(GOOD) + "\n```").root_cause_id == "disk_full"
    with pytest.raises(Exception):
        parse_rca(json.dumps({**GOOD, "root_cause_id": "aliens"}))
    with pytest.raises(ValueError):
        parse_rca("no json here")


def test_classify_alert():
    assert classify_alert("[HIGH] x: p95 latency 900 ms") == "latency"
    assert classify_alert("[HIGH] x: HTTP error rate 5%") == "error_rate"
    assert classify_alert("[HIGH] x: disk usage at 98%") == "disk"


def test_agent_runs_tools_then_reports(store, retriever):
    llm = ScriptedLLM([calls("get_metric_anomalies", "search_logs", "search_runbooks"),
                       AIMessage(content="done"), json.dumps(GOOD)])
    res = TriageAgent(llm, store, retriever).run("INC-001")
    assert res.rca.root_cause_id == "disk_full" and res.llm_calls == 3
    assert [t.name for t in res.tool_calls] == ["get_metric_anomalies", "search_logs", "search_runbooks"]
    assert "error_rate_pct" in res.tool_calls[0].output_preview


def test_agent_repairs_invalid_json_once(store, retriever):
    llm = ScriptedLLM([AIMessage(content="done"), "not json", json.dumps(GOOD)])
    res = TriageAgent(llm, store, retriever).run("INC-001")
    assert res.rca is not None and res.llm_calls == 3


def test_agent_gives_up_cleanly_after_failed_repair(store, retriever):
    llm = ScriptedLLM([AIMessage(content="done"), "bad", "still bad"])
    res = TriageAgent(llm, store, retriever).run("INC-001")
    assert res.rca is None and "invalid RCA JSON" in res.error


def test_agent_survives_tool_errors(store, retriever):
    llm = ScriptedLLM([calls("search_logs", inc="INC-999"), AIMessage(content="x"), json.dumps(GOOD)])
    res = TriageAgent(llm, store, retriever).run("INC-001")
    assert res.tool_calls[0].output_preview.startswith("ERROR")


def test_no_rag_variant_has_no_runbook_tool(store, retriever):
    agent = TriageAgent(ScriptedLLM([]), store, retriever, use_rag=False)
    assert "search_runbooks" not in agent.tools


def test_baseline(store):
    res = PlainLLMBaseline(ScriptedLLM([json.dumps(GOOD)])).run("INC-001", "alert")
    assert res.rca.root_cause_id == "disk_full" and res.tool_calls == []


def test_api(store, retriever):
    llm = ScriptedLLM([AIMessage(content="done"), json.dumps(GOOD)])
    agent = TriageAgent(llm, store, retriever)
    client = TestClient(create_app(agent_provider=lambda: agent, store=store))
    assert client.get("/health").json() == {"status": "ok"}
    assert len(client.get("/incidents").json()) == 30
    ok = client.post("/triage", json={"incident_id": "INC-001"})
    assert ok.status_code == 200 and ok.json()["rca"]["root_cause_id"] == "disk_full"
    assert client.post("/triage", json={"incident_id": "NOPE"}).status_code == 404
    assert client.post("/triage", json={}).status_code == 422
