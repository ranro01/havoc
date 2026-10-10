# Postmortem PM-106: checkout-service incident

## Summary
Customers saw degraded behaviour on checkout-service for about 40 minutes.

## Root cause
CoreDNS pods were overloaded after a node pool upgrade and began timing out lookups for internal hostnames.

## Resolution
Scaled CoreDNS replicas, enabled node-local DNS caching, and added alerts on resolver latency.
