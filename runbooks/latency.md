# Elevated request latency

## Signals

- p95 latency rises while error rate may remain low.
- Connection-pool wait time, queue depth, or downstream duration dominates traces.
- CPU and memory are not necessarily saturated.

## Remediation

Identify the constrained downstream dependency before scaling or restarting. Avoid broad restarts
without evidence. If a bounded restart is approved, verify both latency and error-rate recovery.

