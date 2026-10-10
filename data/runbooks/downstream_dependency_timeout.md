# Runbook RB-08: Downstream dependency timeout

## Symptoms
- Latency rises sharply while our own CPU and memory stay normal
- Logs show timeouts and open circuit breakers for one specific dependency
- Error rate rises moderately as requests exceed their timeout budgets

## Diagnosis
1. Check the dependency's own dashboards and status
2. Compare outbound call latency per dependency
3. Verify timeout and retry settings are not amplifying load

## Remediation
1. Engage the team that owns the dependency
2. Enable degraded mode or fallback responses
3. Tune timeouts, retries and circuit breaker thresholds
