# Runbook RB-12: Bad configuration change

## Symptoms
- Errors begin at the exact time of a configuration push
- Failures are fast, so latency does not rise and may even fall
- No code deployment happened, but a config version changed

## Diagnosis
1. Check the config change audit log around the onset
2. Diff the active config against the previous version
3. Verify values and units such as timeouts, limits and flags

## Remediation
1. Revert the configuration to the last known good version
2. Add validation and staged rollout for configuration changes
3. Alert on config version changes correlated with error spikes
