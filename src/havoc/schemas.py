from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .catalog import FAULT_IDS


class RCAReport(BaseModel):
    root_cause_id: str
    root_cause_summary: str = Field(min_length=10)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(min_length=1)
    suggested_actions: list[str] = Field(min_length=1)
    runbooks_cited: list[str] = Field(default_factory=list)

    @field_validator("root_cause_id")
    @classmethod
    def known_cause(cls, v: str) -> str:
        if v not in FAULT_IDS:
            raise ValueError(f"root_cause_id must be one of {list(FAULT_IDS)}")
        return v


class ToolCall(BaseModel):
    name: str
    args: dict
    output_preview: str


class TriageRequest(BaseModel):
    incident_id: str
    alert: str | None = None


class TriageResult(BaseModel):
    incident_id: str
    rca: RCAReport | None = None
    error: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    llm_calls: int = 0
    latency_s: float = 0.0
