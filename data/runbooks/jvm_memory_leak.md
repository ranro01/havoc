# Runbook RB-02: Memory leak causing heap exhaustion

## Symptoms
- Memory climbs steadily and never returns to baseline after garbage collection
- Latency creeps up as GC pauses lengthen
- Eventually out-of-memory errors or restarts appear

## Diagnosis
1. Compare heap usage after GC over several hours; a rising floor indicates a leak
2. Take a heap dump and look for the largest retained objects
3. Correlate the start of growth with recent deployments or new caches

## Remediation
1. Restart the service to recover immediately and buy time
2. Roll back the release that introduced the growth
3. Fix unbounded caches or listeners holding references and add a heap-growth alert
