# Postmortem PM-115: auth-service incident

## Summary
Customers saw degraded behaviour on auth-service for about 40 minutes.

## Root cause
The container memory limit was lowered during a cost review, so the working set exceeded it at peak and the kernel killed the process repeatedly.

## Resolution
Restored the previous limit, aligned heap settings to 75% of the limit, and added restart-count alerts.
