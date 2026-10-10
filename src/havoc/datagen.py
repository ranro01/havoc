"""Synthetic data generator: metrics, logs, runbooks, postmortems, labelled incidents."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .catalog import (
    DECOY_LOGS,
    DEPENDENCIES,
    FAULT_BY_ID,
    FAULT_IDS,
    FAULTS,
    GENERIC_ERRORS,
    SERVICES,
    Fault,
)

N_POINTS = 240  # one point per minute, 4 hours
BASELINE_POINTS = 120  # the first 2 hours are "normal"; the detector learns from these
START = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
ENDPOINTS = ("items", "orders", "cart", "users", "search", "health")

# metric -> (baseline level, noise std-dev)
METRICS: dict[str, tuple[float, float]] = {
    "cpu_pct": (35, 2.5),
    "mem_pct": (55, 0.8),
    "disk_pct": (60, 0.2),
    "latency_p95_ms": (220, 18),
    "error_rate_pct": (0.3, 0.06),
    "rps": (400, 22),
    "db_pool_pct": (30, 3),
}
PCT_METRICS = {"cpu_pct", "mem_pct", "disk_pct", "db_pool_pct"}


def apply_effect(s: np.ndarray, base: float, kind: str, val: float, onset: int, rng) -> None:
    """Modify series `s` in place from `onset` to the end according to the effect kind."""
    m = len(s) - onset
    idx = slice(onset, len(s))
    if kind == "step_x":
        s[idx] += base * (val - 1)
    elif kind == "ramp_x":
        s[idx] += base * (val - 1) * np.linspace(0, 1, m)
    elif kind == "step_to":
        s[idx] += val - base
    elif kind == "ramp_to":
        s[idx] += (val - base) * np.linspace(0, 1, m)
    elif kind == "jitter_x":
        s[idx] = base * val * rng.lognormal(0, 0.5, m)
    elif kind == "saw_to":
        period = int(rng.integers(22, 34))
        phase = (np.arange(m) % period) / period
        s[idx] = base + (val - base) * phase**0.7 + rng.normal(0, 0.5, m)
    else:
        raise ValueError(f"unknown effect kind: {kind}")


def make_metrics(fault: Fault, onset: int, scale: float, rng) -> pd.DataFrame:
    t = np.arange(N_POINTS)
    cols = {}
    for name, (level, sd) in METRICS.items():
        k = scale if name in ("latency_p95_ms", "rps") else 1.0
        base, sd = level * k, sd * k
        drift = 0.5 * sd * np.sin(t / 40 + rng.uniform(0, 6))
        s = base + drift + rng.normal(0, sd, N_POINTS)
        if name in fault.effects:
            kind, val = fault.effects[name]
            apply_effect(s, base, kind, val, onset, rng)
        s = np.clip(s, 0, 100 if name in PCT_METRICS else None)
        cols[name] = np.round(s, 3)
    ts = [(START + timedelta(minutes=int(i))).strftime("%Y-%m-%dT%H:%M:%SZ") for i in t]
    return pd.DataFrame({"timestamp": ts, **cols})


def make_alert(fault: Fault, svc: str, df: pd.DataFrame) -> str:
    """Symptom-only alert text. It never names the cause."""
    kind = fault.alert_kind
    col = {
        "latency": "latency_p95_ms",
        "errors": "error_rate_pct",
        "cpu": "cpu_pct",
        "memory": "mem_pct",
        "disk": "disk_pct",
    }[kind]
    now = float(df[col].tail(5).mean())
    base = float(df[col].iloc[:BASELINE_POINTS].median())
    if kind == "latency":
        return f"[HIGH] {svc}: p95 latency {now:,.0f} ms ({now / base:.1f}x its usual level) for 5m"
    if kind == "errors":
        return f"[HIGH] {svc}: HTTP error rate {now:.1f}% (usual {base:.1f}%) for 5m"
    label = {"cpu": "CPU utilisation", "memory": "memory usage", "disk": "disk usage"}[kind]
    return f"[HIGH] {svc}: {label} at {now:.0f}% (usual {base:.0f}%) for 5m"


def _fill(template: str, svc: str, rng) -> str:
    return template.format(
        svc=svc,
        dep=str(rng.choice(DEPENDENCIES)),
        n=int(rng.integers(5, 900)),
        ms=int(rng.integers(800, 9000)),
        host=f"10.0.{int(rng.integers(0, 9))}.{int(rng.integers(2, 250))}",
    )


def make_logs(fault: Fault, svc: str, onset: int, day: int, rng) -> list[str]:
    rows: list[tuple[float, str]] = []

    def add(minute: float, text: str) -> None:
        level, msg = text.split(" ", 1)
        rows.append((minute, f"{level} [{svc}] {_fill(msg, svc, rng)}"))

    for _ in range(180):  # normal traffic
        ep, ms = rng.choice(ENDPOINTS), int(rng.integers(8, 120))
        add(rng.uniform(0, N_POINTS - 0.1), f"INFO GET /api/v1/{ep} 200 {ms}ms")
    for _ in range(int(rng.integers(2, 5))):  # benign decoys before the incident
        add(rng.uniform(0, onset - 1), str(rng.choice(DECOY_LOGS)))
    for _ in range(int(rng.integers(1, 3))):  # context line near the onset
        add(rng.uniform(max(onset - 3, 0), onset + 3), str(rng.choice(fault.context_logs)))
    for _ in range(int(rng.integers(60, 120))):  # the fault's signature
        pool = fault.error_logs if rng.random() < 0.65 else GENERIC_ERRORS
        add(rng.uniform(onset, N_POINTS - 0.1), str(rng.choice(pool)))
    rows.sort(key=lambda r: r[0])
    base = START + timedelta(days=day)
    out = []
    for minute, text in rows:
        ts = (base + timedelta(seconds=int(minute * 60))).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append(f"{ts} {text}")
    return out


def runbook_md(f: Fault) -> str:
    sym = "\n".join(f"- {x}" for x in f.symptoms)
    dia = "\n".join(f"{i}. {x}" for i, x in enumerate(f.diagnosis, 1))
    rem = "\n".join(f"{i}. {x}" for i, x in enumerate(f.remediation, 1))
    return f"# Runbook {f.rb}: {f.name}\n\n## Symptoms\n{sym}\n\n## Diagnosis\n{dia}\n\n## Remediation\n{rem}\n"


def postmortem_md(f: Fault, num: int, svc: str) -> str:
    return (
        f"# Postmortem PM-{num}: {svc} incident\n\n"
        f"## Summary\nCustomers saw degraded behaviour on {svc} for about 40 minutes.\n\n"
        f"## Root cause\n{f.pm_root}\n\n## Resolution\n{f.pm_fix}\n"
    )


def generate(out_dir: str | Path, n: int = 30, seed: int = 42) -> dict:
    out = Path(out_dir)
    for sub in ("runbooks", "postmortems", "incidents", "telemetry"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    for f in FAULTS:
        (out / "runbooks" / f"{f.id}.md").write_text(runbook_md(f), encoding="utf-8")
    for i, f in enumerate(FAULTS):
        svc = SERVICES[(i * 3 + 1) % len(SERVICES)]
        name = f"{f.id}__PM-{101 + i}.md"
        (out / "postmortems" / name).write_text(postmortem_md(f, 101 + i, svc), encoding="utf-8")

    faults: list[str] = []
    while len(faults) < n:  # stratified: every fault appears before any repeats
        faults += list(rng.permutation(list(FAULT_IDS)))
    public, labels = [], {}
    for i, fid in enumerate(faults[:n], 1):
        fault, inc = FAULT_BY_ID[fid], f"INC-{i:03d}"
        svc = str(rng.choice(SERVICES))
        onset = int(rng.integers(150, 200))
        df = make_metrics(fault, onset, float(rng.uniform(0.7, 1.4)), rng)
        alert = make_alert(fault, svc, df)
        d = out / "telemetry" / inc
        d.mkdir(exist_ok=True)
        df.to_csv(d / "metrics.csv", index=False)
        (d / "logs.log").write_text("\n".join(make_logs(fault, svc, onset, i, rng)) + "\n")
        public.append({"incident_id": inc, "service": svc, "alert": alert})
        labels[inc] = {"fault_id": fid, "onset_index": onset}
    (out / "incidents" / "incidents.json").write_text(json.dumps(public, indent=2))
    (out / "labels.json").write_text(json.dumps(labels, indent=2))  # never read by the agent
    return {"incidents": len(public), "faults": len(FAULTS)}
