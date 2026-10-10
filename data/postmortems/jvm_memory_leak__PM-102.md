# Postmortem PM-102: search-api incident

## Summary
Customers saw degraded behaviour on search-api for about 40 minutes.

## Root cause
An unbounded in-memory cache kept every response object alive, so heap usage rose steadily until garbage collection could not keep up.

## Resolution
Restarted pods on a schedule as a stopgap and replaced the cache with a size-bounded one with expiry.
