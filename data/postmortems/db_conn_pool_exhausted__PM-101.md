# Postmortem PM-101: payment-gateway incident

## Summary
Customers saw degraded behaviour on payment-gateway for about 40 minutes.

## Root cause
A code path opened a transaction and did not release the connection on the error branch, so the pool filled up under normal traffic.

## Resolution
Restarted pods to free the pool, then shipped a fix that closes connections in a finally block.
