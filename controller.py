"""Authenticated controller for an opt-in machine health monitor.

This service stores worker metadata and health metrics in memory. It deliberately
has no endpoint for command execution, file transfer, or traffic generation.
"""
from __future__ import annotations

import hmac
import os
import threading
from datetime import datetime, timezone
from typing import Dict

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(
    title="Opt-in Worker Monitor",
    version="1.0.0",
    description="Receives authenticated worker registration and health heartbeats.",
)

_workers: Dict[str, dict] = {}
_workers_lock = threading.Lock()


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("WORKER_SHARED_TOKEN", "")
    if len(expected) < 24:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Controller is not configured: set a high-entropy WORKER_SHARED_TOKEN (at least 24 characters).",
        )

    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class Registration(BaseModel):
    worker_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    hostname: str = Field(min_length=1, max_length=255)
    platform: str = Field(min_length=1, max_length=255)


class Heartbeat(BaseModel):
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)
    uptime_seconds: float = Field(ge=0)
    timestamp: datetime


@app.get("/health")
def health() -> dict:
    """Unauthenticated liveness endpoint; reveals no worker data."""
    return {"status": "ok"}


@app.post("/api/v1/workers/register", dependencies=[Depends(require_token)])
def register_worker(payload: Registration) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with _workers_lock:
        existing = _workers.get(payload.worker_id, {})
        _workers[payload.worker_id] = {
            "worker_id": payload.worker_id,
            "hostname": payload.hostname,
            "platform": payload.platform,
            "registered_at": existing.get("registered_at", now),
            "last_seen": now,
            "metrics": existing.get("metrics"),
        }
    return {"ok": True, "worker_id": payload.worker_id}


@app.post(
    "/api/v1/workers/{worker_id}/heartbeat",
    dependencies=[Depends(require_token)],
)
def heartbeat(worker_id: str, payload: Heartbeat) -> dict:
    with _workers_lock:
        worker = _workers.get(worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="Worker is not registered.")
        worker["last_seen"] = datetime.now(timezone.utc).isoformat()
        worker["metrics"] = payload.model_dump(mode="json")
    return {"ok": True}


@app.get("/api/v1/workers", dependencies=[Depends(require_token)])
def list_workers() -> dict:
    with _workers_lock:
        snapshot = [dict(item) for item in _workers.values()]
    snapshot.sort(key=lambda item: item["worker_id"])
    return {"workers": snapshot, "count": len(snapshot)}
