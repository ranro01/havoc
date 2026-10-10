"""Read-only access to an incident's metrics and logs (stand-in for Prometheus/Loki)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

LINE = re.compile(r"^(\S+) (\w+) \[(.+?)\] (.*)$")


class TelemetryStore:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir)
        path = self.root / "incidents" / "incidents.json"
        self._incidents = {i["incident_id"]: i for i in json.loads(path.read_text())}

    def list_incidents(self) -> list[dict]:
        return list(self._incidents.values())

    def get_incident(self, incident_id: str) -> dict:
        if incident_id not in self._incidents:  # also blocks path traversal
            raise KeyError(f"unknown incident: {incident_id}")
        return self._incidents[incident_id]

    def metrics(self, incident_id: str) -> pd.DataFrame:
        self.get_incident(incident_id)
        return pd.read_csv(self.root / "telemetry" / incident_id / "metrics.csv")

    def logs(self, incident_id: str) -> list[tuple[str, str, str]]:
        self.get_incident(incident_id)
        out = []
        for raw in (self.root / "telemetry" / incident_id / "logs.log").read_text().splitlines():
            m = LINE.match(raw)
            if m:
                out.append((m.group(1), m.group(2), m.group(4)))
        return out

    def log_patterns(
        self, incident_id: str, keyword: str = "", window: int = 60, top: int = 8
    ) -> list[dict]:
        """Group WARN/ERROR lines of the last `window` minutes by message template."""
        lines = self.logs(incident_id)
        if not lines:
            return []
        last = pd.Timestamp(lines[-1][0])
        cutoff = (last - pd.Timedelta(minutes=window)).strftime("%Y-%m-%dT%H:%M:%SZ")
        groups: dict[str, dict] = defaultdict(lambda: {"count": 0, "first": "", "sample": ""})
        for ts, level, msg in lines:
            if level == "INFO" or ts < cutoff:
                continue
            if keyword and keyword.lower() not in msg.lower():
                continue
            g = groups[re.sub(r"\d+", "<n>", msg)]
            g["count"] += 1
            g["first"] = g["first"] or ts[11:16]
            g["sample"] = g["sample"] or f"{level} {msg}"
        ranked = sorted(groups.values(), key=lambda g: -g["count"])
        return ranked[:top]

    def log_patterns_text(self, incident_id: str, keyword: str = "") -> str:
        pats = self.log_patterns(incident_id, keyword)
        if not pats:
            return "No WARN/ERROR log lines matched in the last 60 minutes."
        return "\n".join(
            f"- x{p['count']} (first {p['first']}): {p['sample'][:160]}" for p in pats
        )
