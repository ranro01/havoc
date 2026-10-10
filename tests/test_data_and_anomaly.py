import json

from havoc.anomaly import analyze_metrics, robust_z
from havoc.catalog import FAULT_IDS
from havoc.datagen import generate


def test_generation_is_deterministic(tmp_path):
    generate(tmp_path / "a", n=5, seed=1)
    generate(tmp_path / "b", n=5, seed=1)
    for name in ("labels.json", "telemetry/INC-003/logs.log", "telemetry/INC-003/metrics.csv"):
        assert (tmp_path / "a" / name).read_text() == (tmp_path / "b" / name).read_text()


def test_all_faults_covered_and_labels_separate(data_dir, labels):
    assert {v["fault_id"] for v in labels.values()} == set(FAULT_IDS)
    public = json.loads((data_dir / "incidents" / "incidents.json").read_text())
    assert all("fault_id" not in i for i in public)  # agent-visible data has no labels


def test_alert_does_not_name_the_cause(store):
    text = " ".join(i["alert"] for i in store.list_incidents()).lower()
    assert "certificate" not in text and "oom" not in text and "pool" not in text


def test_detector_finds_onset_in_all_incidents(store, labels):
    for inc in store.list_incidents():
        report = analyze_metrics(store.metrics(inc["incident_id"]))
        truth = labels[inc["incident_id"]]["onset_index"]
        assert report.z_onset is not None and abs(report.z_onset - truth) <= 15


def test_detector_quiet_on_clean_baseline(store):
    df = store.metrics("INC-001").iloc[:120].reset_index(drop=True)
    assert analyze_metrics(df).anomalies == []


def test_robust_z_flat_series_does_not_explode(store):
    s = store.metrics("INC-001")["disk_pct"]
    assert abs(robust_z(s).iloc[:120]).max() < 4


def test_db_pool_incident_flags_pool_metric(store, labels):
    inc = next(i for i, v in labels.items() if v["fault_id"] == "db_conn_pool_exhausted")
    names = [a.metric for a in analyze_metrics(store.metrics(inc)).anomalies]
    assert "db_pool_pct" in names and "latency_p95_ms" in names


def test_log_patterns_group_repeated_messages(store, labels):
    inc = next(i for i, v in labels.items() if v["fault_id"] == "disk_full")
    text = store.log_patterns_text(inc)
    assert "No space left on device" in text or "disk quota" in text
