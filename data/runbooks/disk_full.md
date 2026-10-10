# Runbook RB-05: Disk full

## Symptoms
- Disk usage climbs toward 100% and writes begin to fail
- Errors mention no space left on device
- Services that write logs, temp files or WAL segments fail first

## Diagnosis
1. Find the largest directories with du and check log and temp folders
2. Check whether log rotation or cleanup jobs stopped running
3. Look for runaway debug logging or an unbounded temp file

## Remediation
1. Delete or archive old logs and temp files to free space immediately
2. Expand the volume if the growth is legitimate
3. Fix log rotation and add a disk-usage alert at 80%
