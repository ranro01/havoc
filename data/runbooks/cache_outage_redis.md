# Runbook RB-11: Cache (Redis) outage

## Symptoms
- Cache hit ratio collapses and database load rises sharply
- Latency increases because every request goes to the database
- Logs show Redis connection errors

## Diagnosis
1. Check Redis pod or instance health, memory and evictions
2. Verify network reachability and credentials
3. Check for a failover in progress or an eviction storm after hitting maxmemory

## Remediation
1. Restore or fail over Redis
2. Protect the database with request coalescing and rate limits while the cache is cold
3. Pre-warm hot keys after recovery
