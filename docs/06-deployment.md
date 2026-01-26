# Deployment Architecture

## Overview

Ringmaster is designed for **hot-reloading and self-improvement**—not a single binary. The architecture enables Ringmaster to improve itself, creating a flywheel effect where better orchestration leads to faster iteration.

## Design Principles

1. **Hot-reloadable** - Update code without stopping workers
2. **Self-improving** - Ringmaster can modify its own code
3. **Process isolation** - Components restart independently
4. **Flywheel effect** - Each improvement accelerates the next

## Why Not a Single Binary?

A single Rust binary would be elegant but creates friction:

| Single Binary | Hot-Reloadable |
|---------------|----------------|
| Must stop all workers to update | Update components independently |
| Full recompile for any change | Reload only changed modules |
| Can't self-modify safely | Ringmaster improves itself |
| Slow iteration during development | Fast feedback loops |

The goal is a **flywheel**: Ringmaster orchestrating workers that improve Ringmaster.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         THE FLYWHEEL                                 │
│                                                                      │
│    ┌──────────────┐                                                 │
│    │  Ringmaster  │◄────────────────────────────┐                   │
│    │  orchestrates│                              │                   │
│    └──────┬───────┘                              │                   │
│           │                                      │                   │
│           ▼                                      │                   │
│    ┌──────────────┐                              │                   │
│    │   Workers    │                              │                   │
│    │  execute     │                              │                   │
│    └──────┬───────┘                              │                   │
│           │                                      │                   │
│           ▼                                      │                   │
│    ┌──────────────┐                              │                   │
│    │    Tasks     │                              │                   │
│    │  (including  │──────────────────────────────┘                   │
│    │  Ringmaster  │     improvements fed back                        │
│    │  improvements│                                                  │
│    └──────────────┘                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RINGMASTER SYSTEM                             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  SUPERVISOR (systemd / supervisord)                             ││
│  │  Manages component lifecycles, restarts on failure              ││
│  └──────────────────────────────┬──────────────────────────────────┘│
│                                 │                                    │
│  ┌──────────────────────────────┴──────────────────────────────────┐│
│  │                                                                  ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ ││
│  │  │   API      │  │   Queue    │  │  Enricher  │  │  Scheduler │ ││
│  │  │  Server    │  │  Manager   │  │            │  │            │ ││
│  │  │            │  │            │  │            │  │            │ ││
│  │  │  :8080     │  │            │  │            │  │            │ ││
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘ ││
│  │                                                                  ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ ││
│  │  │  Worker    │  │  Worker    │  │  Worker    │  │  Worker    │ ││
│  │  │  Manager   │  │  Pool      │  │  Pool      │  │  Pool      │ ││
│  │  │            │  │  (Claude)  │  │  (Codex)   │  │  (Aider)   │ ││
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘ ││
│  │                                                                  ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │  SHARED STATE                                                    ││
│  │  SQLite + Files (see 05-state-persistence.md)                    ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. API Server

HTTP/WebSocket interface for UI and external integrations.

```
ringmaster-api/
├── src/
│   ├── main.py           # FastAPI app
│   ├── routes/
│   │   ├── projects.py
│   │   ├── tasks.py
│   │   ├── workers.py
│   │   └── websocket.py
│   └── models/
└── requirements.txt
```

**Hot-reload:** `uvicorn --reload` during development, graceful restart in production.

### 2. Queue Manager

Maintains priority queue, handles task assignment.

```
ringmaster-queue/
├── src/
│   ├── main.py           # Queue loop
│   ├── priority.py       # PageRank, betweenness calculations
│   ├── assignment.py     # Worker-task matching
│   └── events.py         # Event publishing
└── requirements.txt
```

**Hot-reload:** Restart process; in-flight assignments are atomic and survive restart.

### 3. Enricher

Context enrichment pipeline (RLM, file selection, etc.).

```
ringmaster-enricher/
├── src/
│   ├── main.py           # Enrichment service
│   ├── stages/
│   │   ├── parse.py      # Stage 1: Parse & normalize
│   │   ├── project.py    # Stage 2: Project context
│   │   ├── history.py    # Stage 3: RLM summarization
│   │   ├── code.py       # Stage 4: Code context
│   │   └── structure.py  # Stage 5: Task structuring
│   └── models/
└── requirements.txt
```

**Hot-reload:** Stateless; can restart anytime without affecting queue.

### 4. Scheduler

Manages worker lifecycles, monitors health.

```
ringmaster-scheduler/
├── src/
│   ├── main.py           # Scheduler loop
│   ├── workers.py        # Worker process management
│   ├── health.py         # Health checks
│   └── scaling.py        # Auto-scaling logic
└── requirements.txt
```

**Hot-reload:** Workers survive scheduler restart; reconnect on startup.

### 5. Worker Pools

Each worker type runs as separate processes managed by the scheduler.

```
Workers are external CLIs (Claude Code, Codex, etc.)
Scheduler spawns/monitors them as subprocesses
```

## Inter-Process Communication

### Message Queue (Internal)

Components communicate via a simple file-based or Redis queue:

```python
# Simple file-based queue for single-server deployment
class FileQueue:
    def __init__(self, path: str):
        self.path = Path(path)

    def push(self, channel: str, message: dict):
        msg_file = self.path / channel / f"{uuid4()}.json"
        msg_file.write_text(json.dumps(message))

    def pop(self, channel: str) -> dict | None:
        channel_path = self.path / channel
        files = sorted(channel_path.glob("*.json"))
        if files:
            msg = json.loads(files[0].read_text())
            files[0].unlink()
            return msg
        return None
```

### Event Bus

Components publish events; others subscribe:

```python
# Events
TASK_CREATED = "task.created"
TASK_ASSIGNED = "task.assigned"
TASK_COMPLETED = "task.completed"
WORKER_AVAILABLE = "worker.available"
DECISION_NEEDED = "decision.needed"

# Publisher
def publish_event(event_type: str, data: dict):
    queue.push("events", {"type": event_type, "data": data, "ts": now()})

# Subscriber
def subscribe(event_types: list[str], callback):
    while True:
        event = queue.pop("events")
        if event and event["type"] in event_types:
            callback(event)
```

## Hot-Reload Mechanisms

### 1. Python Components

Use `importlib.reload()` or process restart:

```python
# Development: auto-reload on file change
uvicorn ringmaster_api:app --reload --reload-dir src

# Production: graceful restart
def graceful_restart():
    # Finish current requests
    server.shutdown(timeout=30)
    # Reload config
    config.reload()
    # Start new server
    server.start()
```

### 2. Configuration Reload

```python
# ringmaster.toml is watched for changes
class ConfigWatcher:
    def __init__(self, path: str):
        self.path = path
        self.last_modified = 0

    def check_reload(self) -> bool:
        mtime = os.path.getmtime(self.path)
        if mtime > self.last_modified:
            self.last_modified = mtime
            return True
        return False

# Components poll for config changes
while True:
    if config_watcher.check_reload():
        config = load_config()
        apply_config(config)
    time.sleep(5)
```

### 3. Code Reload (Self-Improvement)

When Ringmaster improves its own code:

```python
def apply_self_improvement(task: Task):
    # 1. Worker has modified Ringmaster code
    # 2. Run tests
    result = subprocess.run(["pytest", "tests/"], capture_output=True)

    if result.returncode == 0:
        # 3. Tests pass - trigger reload
        component = detect_modified_component(task.modified_files)
        signal_reload(component)
    else:
        # 4. Tests fail - revert
        subprocess.run(["git", "checkout", "--"] + task.modified_files)
        task.status = "failed"
        task.failure_reason = result.stderr.decode()
```

## Process Supervision

### Using systemd

```ini
# /etc/systemd/system/ringmaster-api.service
[Unit]
Description=Ringmaster API Server
After=network.target

[Service]
Type=simple
User=ringmaster
WorkingDirectory=/opt/ringmaster
ExecStart=/opt/ringmaster/venv/bin/uvicorn ringmaster_api:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/ringmaster-queue.service
[Unit]
Description=Ringmaster Queue Manager
After=network.target

[Service]
Type=simple
User=ringmaster
WorkingDirectory=/opt/ringmaster
ExecStart=/opt/ringmaster/venv/bin/python -m ringmaster_queue
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Using supervisord

```ini
# /etc/supervisor/conf.d/ringmaster.conf
[program:ringmaster-api]
command=/opt/ringmaster/venv/bin/uvicorn ringmaster_api:app --host 0.0.0.0 --port 8080
directory=/opt/ringmaster
user=ringmaster
autorestart=true
startsecs=5
stderr_logfile=/var/log/ringmaster/api.err.log
stdout_logfile=/var/log/ringmaster/api.out.log

[program:ringmaster-queue]
command=/opt/ringmaster/venv/bin/python -m ringmaster_queue
directory=/opt/ringmaster
user=ringmaster
autorestart=true
startsecs=5

[program:ringmaster-enricher]
command=/opt/ringmaster/venv/bin/python -m ringmaster_enricher
directory=/opt/ringmaster
user=ringmaster
autorestart=true
startsecs=5

[program:ringmaster-scheduler]
command=/opt/ringmaster/venv/bin/python -m ringmaster_scheduler
directory=/opt/ringmaster
user=ringmaster
autorestart=true
startsecs=5

[group:ringmaster]
programs=ringmaster-api,ringmaster-queue,ringmaster-enricher,ringmaster-scheduler
```

## Self-Improvement Flywheel

### How It Works

1. **User creates task** to improve Ringmaster
2. **Task enters queue** like any other task
3. **Worker implements** the improvement
4. **Tests run** automatically
5. **If pass**, component hot-reloads
6. **Improvement is live**, feeds back into system

### Safety Rails

```python
# Ringmaster self-improvement has extra guards

PROTECTED_FILES = [
    "ringmaster_scheduler/src/safety.py",  # This file
    "tests/",                               # Tests can't be deleted
    ".ringmaster/ringmaster.db",            # Database
]

def validate_self_modification(task: Task) -> bool:
    for file in task.modified_files:
        if any(file.startswith(p) for p in PROTECTED_FILES):
            task.status = "blocked"
            task.create_decision(
                "Modification to protected file requires human approval",
                options=["approve", "reject"]
            )
            return False

    # Must have test coverage
    if not has_test_coverage(task.modified_files):
        task.status = "blocked"
        task.create_decision(
            "Self-improvement requires test coverage",
            options=["add tests", "skip tests (risky)"]
        )
        return False

    return True
```

### Rollback

```python
def rollback_improvement(task: Task):
    # Git-based rollback
    subprocess.run([
        "git", "revert", "--no-commit", task.commit_hash
    ])

    # Restart affected component
    component = detect_modified_component(task.modified_files)
    signal_reload(component)

    # Log rollback
    log_event("self_improvement_rolled_back", {
        "task_id": task.id,
        "reason": task.failure_reason,
        "component": component
    })
```

## Deployment Commands

```bash
# Initial setup
./scripts/setup.sh

# Start all components
supervisorctl start ringmaster:*

# Restart specific component (hot-reload)
supervisorctl restart ringmaster-api

# View logs
tail -f /var/log/ringmaster/*.log

# Reload config without restart
kill -HUP $(cat /var/run/ringmaster-api.pid)

# Full system restart
supervisorctl restart ringmaster:*
```

## Configuration

```toml
# ringmaster.toml

[deployment]
mode = "development"  # or "production"

[components]
api_port = 8080
api_workers = 4

[hot_reload]
enabled = true
watch_dirs = ["src/", "config/"]
debounce_seconds = 2

[self_improvement]
enabled = true
protected_files = [
    "src/safety.py",
    "tests/",
    ".ringmaster/"
]
require_tests = true
auto_rollback = true
```
