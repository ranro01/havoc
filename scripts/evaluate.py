
"""Evaluate retrieval, anomaly detection and RCA accuracy.

Examples:
  python scripts/evaluate.py --skip-llm
  python scripts/evaluate.py --limit 5 --sleep 3
  python scripts/evaluate.py --variants baseline,agent_no_rag,agent --sleep 3
  python scripts/evaluate.py --variants agent_no_rag,agent --sleep 3 --no-cache

Predictions are cached in results/cache/predictions.jsonl.
Failed predictions are retried on subsequent runs.
"""

import argparse
import json
import math
import time
from pathlib import Path

from havoc import config
from havoc.agent import PlainLLMBaseline, TriageAgent, get_llm
from havoc.anomaly import analyze_metrics
from havoc.retrieval import RunbookRetriever, get_embeddings
from havoc.telemetry import TelemetryStore


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0

    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(k: int, n: int) -> str:
    if n == 0:
        return "N/A (n=0)"
    lo, hi = wilson(k, n)
    return (
        f"{100 * k / n:.0f}% "
        f"({k}/{n}, 95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"
    )


def eval_detector(store, incidents, labels) -> dict:
    z_ok = if_ok = 0

    for inc in incidents:
        result = analyze_metrics(store.metrics(inc["incident_id"]))
        truth = labels[inc["incident_id"]]["onset_index"]

        z_ok += (
            result.z_onset is not None
            and abs(result.z_onset - truth) <= 15
        )
        if_ok += (
            result.if_onset is not None
            and abs(result.if_onset - truth) <= 15
        )

    return {
        "n": len(incidents),
        "zscore_onset_within_15min": int(z_ok),
        "isolation_forest_within_15min": int(if_ok),
    }


def eval_retrieval(store, retriever, incidents, labels) -> dict:
    n = len(incidents)
    out = {
        "n": n,
        "alert_only@1": 0,
        "alert_only@3": 0,
        "alert+logs@1": 0,
        "alert+logs@3": 0,
    }

    for inc in incidents:
        incident_id = inc["incident_id"]
        truth = labels[incident_id]["fault_id"]
        patterns = " ".join(
            item["sample"]
            for item in store.log_patterns(incident_id, top=5)
        )

        queries = (
            ("alert_only", inc["alert"]),
            ("alert+logs", inc["alert"] + " " + patterns),
        )

        for name, query in queries:
            ids = [
                hit.fault_id
                for hit in retriever.search(query, k=3)
            ]
            out[f"{name}@1"] += bool(ids and truth == ids[0])
            out[f"{name}@3"] += truth in ids

    return out


def load_cache(path: Path) -> dict:
    """Load the latest recorded prediction for each variant and incident."""
    rows = {}

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            try:
                row = json.loads(line)
                rows[(row["variant"], row["incident_id"])] = row
            except (json.JSONDecodeError, KeyError):
                continue

    return rows


def is_success(row: dict) -> bool:
    """Support both new records and older cached records."""
    if row.get("status") is not None:
        return row["status"] == "success"

    # Backward compatibility with earlier cache formats.
    return row.get("pred") is not None and not row.get("error")


def eval_variant(
    name,
    runner,
    incidents,
    labels,
    cache,
    path,
    sleep,
) -> list[dict]:
    rows = []

    for inc in incidents:
        incident_id = inc["incident_id"]
        cache_key = (name, incident_id)

        # Reuse successful cached results. Retry previous failures.
        if cache_key in cache and is_success(cache[cache_key]):
            rows.append(cache[cache_key])
            continue

        try:
            result = runner.run(incident_id, inc["alert"])
            pred = (
                result.rca.root_cause_id
                if result.rca is not None
                else None
            )

            success = pred is not None and result.error is None

            row = {
                "variant": name,
                "incident_id": incident_id,
                "truth": labels[incident_id]["fault_id"],
                "pred": pred,
                "correct": (
                    pred == labels[incident_id]["fault_id"]
                    if success
                    else None
                ),
                "status": "success" if success else "failed",
                "valid_rca": result.rca is not None,
                "tool_calls": len(result.tool_calls),
                "llm_calls": result.llm_calls,
                "latency_s": result.latency_s,
                "error": result.error,
            }

        except Exception as exc:  # noqa: BLE001
            row = {
                "variant": name,
                "incident_id": incident_id,
                "truth": labels[incident_id]["fault_id"],
                "pred": None,
                "correct": None,
                "status": "failed",
                "valid_rca": False,
                "tool_calls": 0,
                "llm_calls": 0,
                "latency_s": 0.0,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }

        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row) + "\n")

        rows.append(row)

        result_label = (
            "OK"
            if row["correct"] is True
            else "WRONG"
            if row["status"] == "success"
            else "FAILED"
        )
        print(
            f"  {name} {incident_id}: "
            f"truth={row['truth']} pred={row['pred']} {result_label}"
        )

        if row["error"]:
            print(f"    Error: {row['error'][:250]}")

        time.sleep(sleep)

    return rows


def summarize_variant(rows: list[dict]) -> dict:
    successful = [row for row in rows if is_success(row)]
    failed = [row for row in rows if not is_success(row)]
    correct = sum(row["pred"] == row["truth"] for row in successful)

    return {
        "n": len(rows),
        "successful": len(successful),
        "failed": len(failed),
        "correct": correct,
        "accuracy_successful": (
            correct / len(successful) if successful else None
        ),
        "completion_rate": (
            len(successful) / len(rows) if rows else 0.0
        ),
        "valid_rca": sum(
            row.get("valid_rca", row.get("valid_json", False))
            for row in rows
        ),
        "avg_tool_calls": (
            sum(row.get("tool_calls", 0) for row in rows) / len(rows)
            if rows else 0.0
        ),
        "avg_latency_s": (
            sum(row.get("latency_s", 0.0) for row in rows) / len(rows)
            if rows else 0.0
        ),
        "wrong": [
            (row["incident_id"], row["truth"], row["pred"])
            for row in successful
            if row["pred"] != row["truth"]
        ],
        "errors": [
            (row["incident_id"], row.get("error"))
            for row in failed
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        default="baseline,agent_no_rag,agent",
        help="Comma-separated variants to evaluate",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Seconds between incidents to reduce API rate-limit errors",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Run retrieval and detector evaluation without calling an LLM",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore previous predictions and run fresh evaluations",
    )
    args = parser.parse_args()

    store = TelemetryStore(config.data_dir())
    labels = json.loads(
        (config.data_dir() / "labels.json").read_text(encoding="utf-8")
    )

    all_incidents = store.list_incidents()
    incidents = (
        all_incidents[:args.limit]
        if args.limit > 0
        else all_incidents
    )

    retriever = RunbookRetriever.build(
        config.data_dir(),
        get_embeddings(),
    )

    results = {
        "detector": eval_detector(store, incidents, labels),
        "retrieval": eval_retrieval(
            store, retriever, incidents, labels
        ),
        "llm": {},
    }

    if not args.skip_llm:
        llm = get_llm()
        runners = {
            "baseline": PlainLLMBaseline(llm),
            "agent_no_rag": TriageAgent(
                llm, store, retriever, use_rag=False
            ),
            "agent": TriageAgent(
                llm, store, retriever, use_rag=True
            ),
        }

        path = (
            config.root()
            / "results"
            / "cache"
            / "predictions.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        cache = {} if args.no_cache else load_cache(path)

        for name in args.variants.split(","):
            name = name.strip()
            if name not in runners:
                parser.error(
                    f"Unknown variant {name!r}. "
                    f"Choose from: {', '.join(runners)}"
                )

            print(f"Running {name} ...")
            rows = eval_variant(
                name,
                runners[name],
                incidents,
                labels,
                cache,
                path,
                args.sleep,
            )
            results["llm"][name] = summarize_variant(rows)

    output_dir = config.root() / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )

    detector = results["detector"]
    retrieval = results["retrieval"]

    markdown = [
        f"## Results (n={detector['n']} synthetic incidents)\n",
        "### Retrieval (hit@k = true cause's runbook/postmortem in top-k documents)\n",
        "| Query | hit@1 | hit@3 |",
        "|---|---|---|",
        (
            f"| alert text only | "
            f"{pct(retrieval['alert_only@1'], retrieval['n'])} | "
            f"{pct(retrieval['alert_only@3'], retrieval['n'])} |"
        ),
        (
            f"| alert + log evidence | "
            f"{pct(retrieval['alert+logs@1'], retrieval['n'])} | "
            f"{pct(retrieval['alert+logs@3'], retrieval['n'])} |"
        ),
        "\n### Anomaly onset detection (within 15 min of true onset)\n",
        "| Method | Detected |",
        "|---|---|",
        (
            f"| robust z-score | "
            f"{pct(detector['zscore_onset_within_15min'], detector['n'])} |"
        ),
        (
            f"| IsolationForest | "
            f"{pct(detector['isolation_forest_within_15min'], detector['n'])} |"
        ),
    ]

    if results["llm"]:
        markdown.extend([
            "\n### RCA evaluation\n",
            "| Variant | Accuracy on successful predictions | Completed | Failed | Valid RCA | Avg tool calls | Avg latency (s) |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])

        for name, value in results["llm"].items():
            accuracy = (
                pct(value["correct"], value["successful"])
                if value["successful"]
                else "N/A (no successful predictions)"
            )

            markdown.append(
                f"| {name} | {accuracy} | "
                f"{value['successful']}/{value['n']} "
                f"({100 * value['completion_rate']:.0f}%) | "
                f"{value['failed']} | "
                f"{value['valid_rca']}/{value['n']} | "
                f"{value['avg_tool_calls']:.1f} | "
                f"{value['avg_latency_s']:.1f} |"
            )

    report = "\n".join(markdown) + "\n"

    (output_dir / "results.md").write_text(
        report,
        encoding="utf-8",
    )
    print(report)


if __name__ == "__main__":
    main()
