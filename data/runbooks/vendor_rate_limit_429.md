# Runbook RB-14: Third-party API rate limiting (429)

## Symptoms
- Errors rise while latency stays normal because rejections are immediate
- Request volume to a third-party API grew
- Logs show 429 responses and Retry-After headers

## Diagnosis
1. Check outbound call volume against the vendor's quota
2. Look for retry loops or a new feature making extra calls
3. Confirm which API key or plan limit was hit

## Remediation
1. Throttle and batch outbound calls and honour Retry-After
2. Request a higher quota from the vendor
3. Cache vendor responses and add quota-consumption alerts
