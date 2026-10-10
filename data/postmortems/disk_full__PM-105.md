# Postmortem PM-105: notification-worker incident

## Summary
Customers saw degraded behaviour on notification-worker for about 40 minutes.

## Root cause
Debug logging was left enabled after an investigation and the log volume filled the disk because rotation was misconfigured.

## Resolution
Purged old logs, disabled debug logging, fixed the rotation policy and added an 80% disk alert.
