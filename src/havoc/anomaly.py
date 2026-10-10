"""Metric anomaly detection: robust z-score per metric + IsolationForest across all metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .datagen import BASELINE_POINTS, METRICS

Z_THRESHOLD = 4.0
MIN_RUN = 3  # consecutive anomalous points required (suppresses single-point noise)


@dataclass
class MetricAnomaly:
    metric: str
    baseline: float
    recent: float
    z: float
    onset_index: int | None
    onset_ts: str | None
    shape: str  # step | ramp | erratic

    @property
    def direction(self) -> str:
        return "UP" if self.z > 0 else "DOWN"


@dataclass
class AnomalyReport:
    anomalies: list[MetricAnomaly] = field(default_factory=list)
    normal: list[str] = field(default_factory=list)
    z_onset: int | None = None
    if_onset: int | None = None

    def to_text(self) -> str:
        if not self.anomalies:
            return "No metric deviates significantly from its baseline."
        lines = ["Anomalous metrics (strongest first):"]
        for a in self.anomalies:
            lines.append(
                f"- {a.metric}: {a.direction} baseline {a.baseline:.1f} -> recent {a.recent:.1f} "
                f"(z={a.z:+.0f}), began {a.onset_ts}, shape={a.shape}"
            )
        lines.append("Normal metrics: " + (", ".join(self.normal) or "none"))
        return "\n".join(lines)


def robust_z(s: pd.Series, n_base: int = BASELINE_POINTS) -> pd.Series:
    """z-score using median/MAD of the baseline window (robust to outliers)."""
    base = s.iloc[:n_base]
    med = float(base.median())
    mad = float((base - med).abs().median()) * 1.4826
    scale = max(mad, 0.02 * abs(med), 1e-6)  # floor avoids division blow-ups on flat series
    return (s - med) / scale


def first_run(mask: np.ndarray, min_run: int = MIN_RUN) -> int | None:
    run = 0
    for i, flag in enumerate(mask):
        run = run + 1 if flag else 0
        if run >= min_run:
            return i - min_run + 1
    return None


def _shape(window: np.ndarray, base: float) -> str:
    if len(window) >= 15 and np.corrcoef(np.arange(len(window)), window)[0, 1] > 0.85:
        return "ramp"
    shift = abs(window.mean() - base)
    if shift > 0 and window.std() / shift > 0.3:
        return "erratic"
    return "step"


def analyze_metrics(df: pd.DataFrame, n_base: int = BASELINE_POINTS) -> AnomalyReport:
    report = AnomalyReport()
    zs = {}
    for m in METRICS:
        z = robust_z(df[m], n_base)
        zs[m] = z
        onset = first_run(np.abs(z.to_numpy()[n_base:]) > Z_THRESHOLD)
        if onset is None:
            report.normal.append(m)
            continue
        onset += n_base
        window = df[m].to_numpy()[onset:]
        base = float(df[m].iloc[:n_base].median())
        report.anomalies.append(
            MetricAnomaly(
                metric=m,
                baseline=base,
                recent=float(df[m].tail(5).mean()),
                z=float(z.tail(5).mean()),
                onset_index=onset,
                onset_ts=str(df["timestamp"].iloc[onset])[11:16],
                shape=_shape(window, base),
            )
        )
    report.anomalies.sort(key=lambda a: -abs(a.z))
    if report.anomalies:
        report.z_onset = min(a.onset_index for a in report.anomalies if a.onset_index is not None)

    # Multivariate view: IsolationForest trained only on the baseline period.
    X = df[list(METRICS)].to_numpy()
    scaler = StandardScaler().fit(X[:n_base])
    forest = IsolationForest(n_estimators=100, random_state=0).fit(scaler.transform(X[:n_base]))
    flags = forest.predict(scaler.transform(X)) == -1
    report.if_onset = first_run(flags[n_base:])
    if report.if_onset is not None:
        report.if_onset += n_base
    return report
