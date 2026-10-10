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
