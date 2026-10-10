# Postmortem PM-111: order-service incident

## Summary
Customers saw degraded behaviour on order-service for about 40 minutes.

## Root cause
The Redis primary ran out of memory and crashed, so all reads fell through to the database and overloaded its connection pool.

## Resolution
Failed over to the replica, throttled expensive endpoints during warm-up, and raised the memory limit.
