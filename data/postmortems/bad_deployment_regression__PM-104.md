# Postmortem PM-104: inventory-service incident

## Summary
Customers saw degraded behaviour on inventory-service for about 40 minutes.

## Root cause
A refactor introduced a null dereference on an optional field that production payloads frequently omit.

## Resolution
Rolled back to the previous version within minutes and re-released with a null check and a test for the missing-field case.
