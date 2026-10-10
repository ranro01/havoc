# Runbook RB-07: Expired TLS certificate

## Symptoms
- A large share of calls fail instantly with TLS or certificate errors
- Latency drops because calls fail fast
- Started abruptly at a round timestamp with no deployment

## Diagnosis
1. Inspect the certificate with openssl s_client and read the not-after date
2. Check whether the renewal job or cert-manager issuer is failing
3. Verify the full chain and the trust store on the client

## Remediation
1. Issue and install a renewed certificate, then reload the affected services
2. Fix the automation that should have renewed it
3. Add expiry monitoring with alerts at 30, 14 and 7 days
