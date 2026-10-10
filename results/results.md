## Results (n=5 synthetic incidents)

### Retrieval (hit@k = true cause's runbook/postmortem in top-k documents)

| Query | hit@1 | hit@3 |
|---|---|---|
| alert text only | 0% (0/5, 95% CI 0-43%) | 20% (1/5, 95% CI 4-62%) |
| alert + log evidence | 60% (3/5, 95% CI 23-88%) | 80% (4/5, 95% CI 38-96%) |

### Anomaly onset detection (within 15 min of true onset)

| Method | Detected |
|---|---|
| robust z-score | 100% (5/5, 95% CI 57-100%) |
| IsolationForest | 60% (3/5, 95% CI 23-88%) |

### RCA evaluation

| Variant | Accuracy on successful predictions | Completed | Failed | Valid RCA | Avg tool calls | Avg latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 40% (2/5, 95% CI 12-77%) | 5/5 (100%) | 0 | 5/5 | 0.0 | 1.4 |
| agent_no_rag | 100% (5/5, 95% CI 57-100%) | 5/5 (100%) | 0 | 5/5 | 2.0 | 10.0 |
| agent | 100% (5/5, 95% CI 57-100%) | 5/5 (100%) | 0 | 5/5 | 3.0 | 7.2 |
