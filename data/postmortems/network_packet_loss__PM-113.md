# Postmortem PM-113: notification-worker incident

## Summary
Customers saw degraded behaviour on notification-worker for about 40 minutes.

## Root cause
A faulty switch in one availability zone caused packet loss between nodes, which showed up as resets and erratic latency.

## Resolution
Shifted traffic out of the zone and replaced the affected nodes while the provider repaired the switch.
