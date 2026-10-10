# Runbook RB-04: Bad deployment / code regression

## Symptoms
- Error rate steps up sharply right after a release
- New exceptions appear that were not present before
- Infrastructure metrics such as CPU and memory stay roughly normal

## Diagnosis
1. Compare the onset time with the deployment timeline
2. Group new error signatures by release version
3. Check whether the failing endpoints were touched by the change

## Remediation
1. Roll back to the previous release
2. Disable the new feature flag if one gates the change
3. Add a regression test and canary checks before re-releasing
