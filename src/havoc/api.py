"""FastAPI service. Run: uvicorn havoc.api:app --reload"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import FastAPI, HTTPException

from . import config
from .agent import TriageAgent, build_default_agent
from .schemas import TriageRequest, TriageResult
from .telemetry import TelemetryStore


def create_app(agent_provider: Callable[[], TriageAgent] | None = None,
               store: TelemetryStore | None = None) -> FastAPI:
    app = FastAPI(title="Havoc", version="0.1.0")
    provider = agent_provider or lru_cache(maxsize=1)(build_default_agent)
    stores: list[TelemetryStore] = [store] if store else []

    def get_store() -> TelemetryStore:
        if not stores:
            stores.append(TelemetryStore(config.data_dir()))
        return stores[0]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/incidents")
    def incidents() -> list[dict]:
        return get_store().list_incidents()

    @app.post("/triage", response_model=TriageResult)
    def triage(req: TriageRequest) -> TriageResult:
        try:
            get_store().get_incident(req.incident_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown incident {req.incident_id}")
        try:
            return provider().run(req.incident_id, req.alert)
        except RuntimeError as e:  # e.g. missing GROQ_API_KEY
            raise HTTPException(status_code=503, detail=str(e))

    return app


app = create_app()
