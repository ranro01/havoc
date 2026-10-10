# Runbook RB-01: Database connection pool exhausted

## Symptoms
- Requests hang and then fail with connection acquisition timeouts
- DB pool utilisation is pinned near 100% while the database is not CPU-bound
- Latency and 5xx errors rise together

## Diagnosis
1. Check active versus max pool size and the number of waiting threads
2. Look for connection leaks: connections not closed on error paths
3. Check for long-running queries or locks holding connections

## Remediation
1. Restart or recycle the affected pods to release leaked connections
2. Temporarily raise the max pool size if the database has headroom
3. Fix the leak and add pool-saturation alerts
