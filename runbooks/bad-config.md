# Invalid service configuration

## Signals

- New instances fail startup validation.
- Logs identify a malformed environment variable or missing secret reference.
- The last deployment changed configuration without changing application code.

## Remediation

Compare against the last known-good value, constrain the change to the affected service, and require
operator approval before redeploying. Never print secret values into the event timeline.

## Verification

Confirm successful startup, passing readiness checks, and no repeated validation errors.

