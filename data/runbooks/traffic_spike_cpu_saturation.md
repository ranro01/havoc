# Runbook RB-03: Traffic surge saturating CPU

## Symptoms
- Request rate jumps well above normal while CPU approaches 100%
- Latency rises because requests queue for CPU
- The autoscaler is at its replica ceiling

## Diagnosis
1. Compare request rate to the weekly baseline and check for a campaign or retry storm
2. Check autoscaler events and the replica ceiling
3. Look at the top client IPs or tenants for abnormal volume

## Remediation
1. Raise the autoscaler maximum or add capacity
2. Enable rate limiting or block abusive clients
3. Shed non-critical traffic and plan capacity for the new peak
