# Runbook RB-13: Network partition / packet loss

## Symptoms
- Latency is erratic with large swings rather than a steady rise
- Throughput drops and errors rise across several dependencies at once
- Logs show connection resets and retransmits

## Diagnosis
1. Run ping and mtr between affected nodes to measure loss
2. Check cloud provider network events and node health
3. Check whether the issue is limited to one availability zone or node pool

## Remediation
1. Drain traffic away from the affected zone or node
2. Cordon and replace the faulty nodes
3. Engage the network or cloud provider and add loss and retransmit alerts
