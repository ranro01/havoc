# Runbook RB-09: Slow database queries (missing index)

## Symptoms
- Latency grows gradually as the table grows or after a schema change
- Database load and pool use rise moderately without being fully exhausted
- The slow query log shows full scans of one table

## Diagnosis
1. Review the slow query log and run EXPLAIN on the top query
2. Check whether an index was dropped or never created
3. Check recent migrations or data growth on the table

## Remediation
1. Create the missing index concurrently
2. Rewrite the query or add pagination
3. Add slow-query alerts and review plans for new queries before release
