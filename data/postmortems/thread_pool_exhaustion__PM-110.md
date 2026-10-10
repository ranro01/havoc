# Postmortem PM-110: search-api incident

## Summary
Customers saw degraded behaviour on search-api for about 40 minutes.

## Root cause
A synchronous call to a slow service blocked request threads until the worker pool was fully occupied while CPU stayed idle.

## Resolution
Added timeouts to the blocking call, isolated it in its own pool, and restarted pods to recover.
