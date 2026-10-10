## Results (n=30 synthetic incidents)

### Retrieval (hit@k = true cause's runbook/postmortem in top-k documents)

| Query | hit@1 | hit@3 |
|---|---|---|
| alert text only | 17% (5/30, 95% CI 7-34%) | 33% (10/30, 95% CI 19-51%) |
| alert + log evidence | 53% (16/30, 95% CI 36-70%) | 87% (26/30, 95% CI 70-95%) |

### Anomaly onset detection (within 15 min of true onset)

| Method | Detected |
|---|---|
| robust z-score | 100% (30/30, 95% CI 89-100%) |
| IsolationForest | 63% (19/30, 95% CI 46-78%) |

### RCA evaluation

| Variant | Accuracy on successful predictions | Completed | Failed | Valid RCA | Avg tool calls | Avg latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 30% (9/30, 95% CI 17-48%) | 30/30 (100%) | 0 | 30/30 | 0.0 | 2.6 |
| agent_no_rag | 97% (29/30, 95% CI 83-99%) | 30/30 (100%) | 0 | 30/30 | 2.0 | 12.1 |
| agent | 90% (27/30, 95% CI 74-97%) | 30/30 (100%) | 0 | 30/30 | 3.0 | 24.7 |
