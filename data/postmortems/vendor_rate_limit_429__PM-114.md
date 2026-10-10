# Postmortem PM-114: checkout-service incident

## Summary
Customers saw degraded behaviour on checkout-service for about 40 minutes.

## Root cause
A retry loop without backoff multiplied calls to a payment vendor until the account quota was exceeded.

## Resolution
Added exponential backoff with jitter, requested a quota increase, and cached idempotent lookups.
