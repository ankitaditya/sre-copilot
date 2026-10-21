#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

STATE_PATH = Path(__file__).parent / "runtime" / "state.json"

SCENARIOS = {
    "healthy": {
        "fault": "none",
        "symptoms": [],
        "log": "INFO service health restored; all dependencies ready",
    },
    "db-down": {
        "fault": "db-down",
        "symptoms": [
            "HTTP 503 responses",
            "database connection refused",
            "readiness probe failing",
        ],
        "log": "ERROR database connection refused host=postgres port=5432",
    },
    "bad-config": {
        "fault": "bad-config",
        "symptoms": [
            "startup validation failed",
            "DATABASE_URL is malformed",
            "deployment unavailable",
        ],
        "log": "ERROR configuration validation failed field=DATABASE_URL",
    },
    "latency": {
        "fault": "latency",
        "symptoms": [
            "p95 latency above 4 seconds",
            "database pool saturation",
            "request queue growing",
        ],
        "log": "WARN slow request duration_ms=4812 pool_wait_ms=3900",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject a portable SRE Copilot demo fault.")
    parser.add_argument(
        "scenario",
        choices=["reset", *SCENARIOS],
        help="reset is an alias for the db-down assessment scenario",
    )
    args = parser.parse_args()
    scenario = "db-down" if args.scenario == "reset" else args.scenario
    definition = SCENARIOS[scenario]
    now = datetime.now(UTC).isoformat()
    state = {
        "service": "demo-api",
        "fault": definition["fault"],
        "symptoms": definition["symptoms"],
        "last_changed_at": now,
        "logs": [
            f"{now} INFO demo-api scenario controller ready",
            f"{now} {definition['log']}",
        ],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"demo-api scenario set to {scenario}: {STATE_PATH}")


if __name__ == "__main__":
    main()

