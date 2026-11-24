"""Foreground, opt-in health-monitoring worker.

The worker sends a small JSON registration and periodic health metrics to the
configured controller. It does not execute instructions received over the
network, install a service, or modify system startup settings.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil


def validate_controller_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("CONTROLLER_URL must be an http:// or https:// URL.")
    host = (parsed.hostname or "").lower()
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme == "http" and host not in loopback_hosts:
        raise ValueError("HTTP is permitted only for loopback testing. Use HTTPS for remote controllers.")
    return value.rstrip("/")


def request_json(url: str, token: str, payload: dict, timeout: float = 10.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "opt-in-worker-monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(64 * 1024)
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"Controller returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach controller: {exc.reason}") from exc


def collect_metrics() -> dict:
    home_path = str(Path.home())
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(home_path)
    return {
        "cpu_percent": float(psutil.cpu_percent(interval=0.2)),
        "memory_percent": float(memory.percent),
        "disk_percent": float(disk.percent),
        "uptime_seconds": max(0.0, time.time() - psutil.boot_time()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_worker(controller_url: str, token: str, worker_id: str, interval: int, once: bool) -> None:
    register_url = f"{controller_url}/api/v1/workers/register"
    heartbeat_url = f"{controller_url}/api/v1/workers/{urllib.parse.quote(worker_id, safe='')}/heartbeat"

    registration = {
        "worker_id": worker_id,
        "hostname": platform.node() or "unknown",
        "platform": f"{platform.system()} {platform.release()}",
    }
    request_json(register_url, token, registration)
    print(f"Registered worker '{worker_id}' with {controller_url}", flush=True)

    while True:
        metrics = collect_metrics()
        request_json(heartbeat_url, token, metrics)
        print(
            "Heartbeat sent: "
            f"CPU {metrics['cpu_percent']:.1f}% | "
            f"RAM {metrics['memory_percent']:.1f}% | "
            f"Disk {metrics['disk_percent']:.1f}%",
            flush=True,
        )
        if once:
            break
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an opt-in machine health-monitoring worker.")
    parser.add_argument("--once", action="store_true", help="send one heartbeat and exit")
    parser.add_argument("--interval", type=int, default=int(os.getenv("HEARTBEAT_INTERVAL", "15")),
                        help="heartbeat interval in seconds (minimum: 5; default: 15)")
    args = parser.parse_args()

    controller = os.getenv("CONTROLLER_URL", "http://127.0.0.1:8000")
    token = os.getenv("WORKER_SHARED_TOKEN", "")
    worker_id = os.getenv("WORKER_ID") or f"worker-{uuid.uuid4().hex[:12]}"

    try:
        controller = validate_controller_url(controller)
        if len(token) < 24:
            raise ValueError("Set WORKER_SHARED_TOKEN to a secret of at least 24 characters.")
        if not 5 <= args.interval <= 3600:
            raise ValueError("Heartbeat interval must be between 5 and 3600 seconds.")
        run_worker(controller, token, worker_id, args.interval, args.once)
    except KeyboardInterrupt:
        print("\nWorker stopped by user.", flush=True)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Worker error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
