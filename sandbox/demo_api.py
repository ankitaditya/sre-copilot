from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI(title="SRE Copilot demo service")
state_path = Path("/runtime/state.json")


def read_state() -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    state = read_state()
    if state.get("fault") != "none":
        raise HTTPException(
            status_code=503,
            detail={"healthy": False, "fault": state.get("fault")},
        )
    return {"healthy": True, "service": state.get("service")}


@app.get("/orders")
async def orders() -> list[dict]:
    state = read_state()
    if state.get("fault") != "none":
        raise HTTPException(status_code=503, detail="dependency unavailable")
    return [{"id": "ord-1001", "status": "ready"}]

