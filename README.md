# BOTNET_WORKER — opt-in distributed monitor

This repository contains a small, **consent-based machine monitoring demo**:

- A FastAPI controller that accepts authenticated worker registrations and health heartbeats.
- A foreground Python worker that reports CPU, memory, disk usage, platform, and uptime.
- No remote shell, arbitrary task execution, port scanning, traffic generation, stealth, or persistence.

The worker runs only when a user starts it. Use it only on machines you own or are explicitly authorized to monitor.

## Requirements

- Python 3.10+
- Network access from each worker to the controller
- A shared bearer token configured privately on the controller and each worker

## 1. Start the controller

Clone the repository, then:

```bash
python -m venv .venv
```

Activate the environment:

**Windows PowerShell**
```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS**
```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a strong token and set it in the controller environment. Keep this value private.

**Windows PowerShell**
```powershell
$env:WORKER_SHARED_TOKEN = "<replace-with-a-long-random-secret>"
uvicorn controller:app --host 127.0.0.1 --port 8000
```

**Linux / macOS**
```bash
export WORKER_SHARED_TOKEN="<replace-with-a-long-random-secret>"
uvicorn controller:app --host 127.0.0.1 --port 8000
```

For workers on other machines, bind the controller to an appropriate private interface (or place it behind HTTPS), configure firewall access narrowly, and use HTTPS. Do not expose the development server directly to the public internet.

Controller endpoints:
- `GET /health` — liveness check
- `POST /api/v1/workers/register` — authenticated worker registration
- `POST /api/v1/workers/{worker_id}/heartbeat` — authenticated health report
- `GET /api/v1/workers` — authenticated list of currently known workers

Interactive API documentation is available at `/docs` while the controller is running.

## 2. Run a worker

On each machine you are authorized to monitor, install the requirements and set:

- `CONTROLLER_URL`: controller base URL, e.g. `http://127.0.0.1:8000` for local testing or an `https://...` URL for remote use.
- `WORKER_SHARED_TOKEN`: the same secret configured on the controller.
- `WORKER_ID` (optional): a memorable ID. If omitted, a new ID is generated for this run.
- `HEARTBEAT_INTERVAL` (optional): seconds between heartbeats; minimum is 5, default is 15.

**Windows PowerShell**
```powershell
$env:CONTROLLER_URL = "http://127.0.0.1:8000"
$env:WORKER_SHARED_TOKEN = "<same-secret>"
$env:WORKER_ID = "my-laptop"
python worker.py
```

**Linux / macOS**
```bash
export CONTROLLER_URL="https://your-private-controller.example"
export WORKER_SHARED_TOKEN="<same-secret>"
export WORKER_ID="my-server"
python worker.py
```

Stop the worker with `Ctrl+C`. It does not install itself as a service or start automatically.

## Security notes

- Use a unique, high-entropy token and do not commit real secrets.
- Use HTTPS for traffic crossing a network; HTTP is allowed by the worker only for loopback testing.
- The controller keeps worker state in memory; restarting it clears the list.
- The shared-token design is intended for a small private demo. For production, use per-worker credentials, token rotation, durable storage, rate limiting, and a reverse proxy with TLS.
