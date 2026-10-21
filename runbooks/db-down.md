# Database unavailable

## Signals

- Readiness checks fail while liveness remains available.
- Logs contain `connection refused`, `pool timeout`, or DNS failures for PostgreSQL.
- Customer requests return HTTP 503.

## Safe investigation

1. Confirm the affected service and deployment scope.
2. Check whether the database container or process is running.
3. Inspect the latest bounded service logs.
4. Confirm whether the incident followed a configuration change.

## Remediation

Prefer restoring the failed dependency or last known-good configuration. A restart is acceptable
only when evidence indicates stale connections or a recovered dependency. Any mutating action
requires operator approval and must be followed by a health check.

## Verification

Require a passing readiness check and one successful customer-path request before closure.

