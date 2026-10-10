# Postmortem PM-103: order-service incident

## Summary
Customers saw degraded behaviour on order-service for about 40 minutes.

## Root cause
A marketing campaign tripled inbound traffic and the autoscaler hit its maximum replica count, leaving the pods CPU-bound.

## Resolution
Raised the replica ceiling, added rate limits for anonymous clients, and set a capacity review for planned campaigns.
