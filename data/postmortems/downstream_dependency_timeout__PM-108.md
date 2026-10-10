# Postmortem PM-108: user-profile-service incident

## Summary
Customers saw degraded behaviour on user-profile-service for about 40 minutes.

## Root cause
The inventory dependency slowed down after its own database failover and our calls exceeded their timeout budget.

## Resolution
Opened the circuit breaker with cached fallbacks while the inventory team finished recovery, then shortened retry budgets.
