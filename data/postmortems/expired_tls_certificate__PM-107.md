# Postmortem PM-107: auth-service incident

## Summary
Customers saw degraded behaviour on auth-service for about 40 minutes.

## Root cause
The certificate for an internal API expired because the renewal job had been failing silently for weeks.

## Resolution
Issued a new certificate manually, repaired the renewal job, and added alerts for upcoming expiry.
