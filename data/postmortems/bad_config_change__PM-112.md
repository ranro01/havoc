# Postmortem PM-112: inventory-service incident

## Summary
Customers saw degraded behaviour on inventory-service for about 40 minutes.

## Root cause
A configuration push set a request timeout to 50 milliseconds instead of 5 seconds, so most calls timed out immediately.

## Resolution
Reverted the config version and added schema validation with minimum bounds for timeout values.
