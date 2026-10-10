# Runbook RB-10: Thread pool exhaustion

## Symptoms
- Latency and errors rise while CPU stays low
- Logs show rejected tasks and busy worker threads
- Threads are blocked waiting on I/O rather than computing

## Diagnosis
1. Take thread dumps and see what the blocked threads are waiting on
2. Check pool and queue sizes against concurrency
3. Look for a slow downstream call or a lock held by many threads

## Remediation
1. Restart pods to clear the blocked threads
2. Increase the pool or add timeouts to the blocking call
3. Move blocking work off request threads and add bulkheads
