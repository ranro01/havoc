# Postmortem PM-109: payment-gateway incident

## Summary
Customers saw degraded behaviour on payment-gateway for about 40 minutes.

## Root cause
A migration dropped a composite index and the orders query fell back to sequential scans as the table grew.

## Resolution
Recreated the index concurrently, which restored latency, and added a migration check for dropped indexes.
