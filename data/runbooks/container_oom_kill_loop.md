# Runbook RB-15: Container OOMKilled / restart loop

## Symptoms
- Memory repeatedly climbs to the container limit then drops when the container restarts
- Capacity and throughput dip during each restart
- Pods show OOMKilled and CrashLoopBackOff

## Diagnosis
1. Inspect pod events and last state for OOMKilled and exit code 137
2. Compare the memory limit with the working set during peak
3. Check recent changes to limits, heap settings or batch sizes

## Remediation
1. Raise the container memory limit to stop the loop
2. Align JVM or runtime heap settings with the limit
3. Reduce batch sizes and add working-set alerts
