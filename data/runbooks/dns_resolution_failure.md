# Runbook RB-06: DNS resolution failure

## Symptoms
- Calls to internal hostnames fail while the target services are healthy
- Errors mention unknown host or name resolution
- Failures are intermittent and latency is erratic

## Diagnosis
1. Run nslookup or dig from an affected pod against the cluster resolver
2. Check CoreDNS pods for restarts, load and errors
3. Check for recent changes to DNS records, search domains or network policies

## Remediation
1. Restart or scale CoreDNS
2. Correct the broken record or search-domain setting
3. Add node-local DNS caching and DNS error-rate alerts
