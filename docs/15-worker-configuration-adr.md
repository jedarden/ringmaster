# Worker Configuration ADR

## Problem Statement

Ringmaster needs workers to execute tasks, but workers need configuration before they can be dispatched:
- What CLI tool does the worker use? (Claude Code, Aider, Codex, etc.)
- What model/API key?
- What capabilities does the worker have?
- How does the worker poll, execute, and report results?

Currently:
- `Worker` model exists with `generated_script` field
- `WorkerSpawner` has a hardcoded template with `claude-code` and `aider` cases
- Launcher scripts exist in `workers/` but aren't integrated
- No UI/CLI flow for creating or configuring workers

## ADR-024: Worker Configuration Model

### Decision

Worker configuration follows a **template + customization** pattern:

1. **Worker Templates** - Pre-defined configurations for known tools (Claude Code, Aider, etc.)
2. **Worker Instances** - Configured workers ready to be spawned
3. **Generated Scripts** - LLM can generate custom scripts from natural language

### Worker Template Schema

```python
@dataclass
class WorkerTemplate:
    """Template for a type of worker."""

    id: str  # e.g., "claude-code", "aider", "codex-cli"
    name: str  # Human-readable name
    description: str

    # The CLI tool
    command: str  # e.g., "claude", "aider", "codex"

    # How to pass the prompt
    prompt_method: str  # "flag", "stdin", "file", "arg"
    prompt_flag: str | None  # e.g., "--prompt", "-m", "--message"

    # Required environment variables
    required_env: list[str]  # e.g., ["ANTHROPIC_API_KEY"]
    optional_env: list[str]  # e.g., ["CLAUDE_MODEL"]

    # Default model
    default_model: str | None

    # Capabilities this tool is known for
    default_capabilities: list[str]

    # Template script (Jinja2)
    script_template: str
```

### Built-in Templates

```python
WORKER_TEMPLATES = {
    "claude-code": WorkerTemplate(
        id="claude-code",
        name="Claude Code",
        description="Anthropic's Claude Code CLI - strong reasoning, tool use",
        command="claude",
        prompt_method="flag",
        prompt_flag="--prompt",
        required_env=["ANTHROPIC_API_KEY"],
        optional_env=["CLAUDE_MODEL", "CLAUDE_MAX_TOKENS"],
        default_model="claude-sonnet-4-20250514",
        default_capabilities=["reasoning", "tool-use", "multi-file"],
        script_template=CLAUDE_CODE_TEMPLATE,
    ),

    "aider": WorkerTemplate(
        id="aider",
        name="Aider",
        description="AI pair programming - good at focused edits",
        command="aider",
        prompt_method="flag",
        prompt_flag="--message",
        required_env=["ANTHROPIC_API_KEY"],  # or OPENAI_API_KEY
        optional_env=["AIDER_MODEL"],
        default_model="claude-sonnet-4-20250514",
        default_capabilities=["editing", "refactoring", "focused-changes"],
        script_template=AIDER_TEMPLATE,
    ),

    "codex-cli": WorkerTemplate(
        id="codex-cli",
        name="Codex CLI",
        description="OpenAI's Codex CLI - fast iteration",
        command="codex",
        prompt_method="arg",
        prompt_flag=None,
        required_env=["OPENAI_API_KEY"],
        optional_env=["CODEX_MODEL"],
        default_model="gpt-4o",
        default_capabilities=["fast", "iteration"],
        script_template=CODEX_TEMPLATE,
    ),

    "custom": WorkerTemplate(
        id="custom",
        name="Custom Worker",
        description="User-defined or LLM-generated worker",
        command="",
        prompt_method="custom",
        prompt_flag=None,
        required_env=[],
        optional_env=[],
        default_model=None,
        default_capabilities=[],
        script_template=CUSTOM_TEMPLATE,
    ),
}
```

---

## ADR-025: Worker Configuration Flow

### Option A: CLI-Based Configuration (Recommended for MVP)

```bash
# List available templates
ringmaster worker templates

# Create worker from template
ringmaster worker create \
  --name "claude-main" \
  --template claude-code \
  --capabilities python,typescript,security \
  --model claude-sonnet-4-20250514

# Create worker with custom script (LLM-generated)
ringmaster worker create \
  --name "custom-worker" \
  --template custom \
  --script-file ./my-worker.sh

# Create worker from natural language (LLM generates script)
ringmaster worker create \
  --name "fast-python" \
  --from-description "A fast worker for Python tasks using Claude Haiku"

# List configured workers
ringmaster worker list

# Show worker details
ringmaster worker show claude-main

# Update worker
ringmaster worker update claude-main --capabilities python,rust

# Delete worker
ringmaster worker delete claude-main

# Spawn (start) a worker
ringmaster worker spawn claude-main

# Stop a worker
ringmaster worker stop claude-main
```

### Option B: Web UI Configuration

```
Workers Page
├── Templates section (read-only)
│   ├── Claude Code
│   ├── Aider
│   ├── Codex CLI
│   └── Custom
│
├── Configured Workers section
│   ├── [+ New Worker] button
│   ├── Worker cards with status
│   └── Each card has: Edit, Spawn/Stop, Delete
│
└── Worker Detail Modal
    ├── Name, Description
    ├── Template selection
    ├── Model override
    ├── Capabilities (tags)
    ├── Environment variables
    └── Generated script (readonly preview)
```

### Decision: Start with CLI, UI follows

CLI-based configuration is implemented first:
- Faster to implement
- Scriptable/automatable
- Workers can configure workers (self-improvement)

Web UI added later by Ringmaster itself.

---

## ADR-026: Script Generation

### When Scripts Are Generated

1. **From template** - Template's `script_template` is rendered with worker config
2. **From description** - LLM generates complete script from natural language
3. **Custom** - User provides their own script

### Script Template (Jinja2)

```bash
#!/bin/bash
# {{ worker.name }} - Generated by Ringmaster
# Template: {{ template.id }}

set -euo pipefail

WORKER_ID="{{ worker.id }}"
WORKER_NAME="{{ worker.name }}"
WORKER_TYPE="{{ worker.type }}"
LOG_FILE="{{ log_path }}"
CAPABILITIES="{{ worker.capabilities | join(',') }}"

{% if template.required_env %}
# Required environment variables
{% for env in template.required_env %}
if [ -z "${{'{'}}{{ env }}:-}" ]; then
    echo "ERROR: {{ env }} not set" >&2
    exit 1
fi
{% endfor %}
{% endif %}

# Configuration
MODEL="${{'{'}}{{ template.id | upper }}_MODEL:-{{ worker.model or template.default_model }}}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Worker $WORKER_NAME starting (model: $MODEL)"

trap 'log "Shutting down..."; exit 0' SIGINT SIGTERM

# Main loop
while true; do
    # Pull task
    TASK_JSON=$(ringmaster pull-task "$WORKER_ID" --capabilities "$CAPABILITIES" --json 2>/dev/null || echo "")

    if [ -z "$TASK_JSON" ] || [ "$TASK_JSON" = "null" ]; then
        sleep {{ backoff_seconds | default(5) }}
        continue
    fi

    TASK_ID=$(echo "$TASK_JSON" | jq -r '.id')
    log "Picked up task: $TASK_ID"

    # Build prompt
    PROMPT_FILE=$(mktemp)
    ringmaster build-prompt "$TASK_ID" -o "$PROMPT_FILE"

    # Get working directory
    WORK_DIR=$(echo "$TASK_JSON" | jq -r '.working_dir // "."')
    cd "$WORK_DIR"

    # Execute
    EXIT_CODE=0
    {% if template.prompt_method == "flag" %}
    {{ template.command }} {{ template.prompt_flag }} "$(cat $PROMPT_FILE)" \
        --model "$MODEL" \
        {{ extra_flags | default("") }} \
        2>&1 | tee -a "$LOG_FILE" || EXIT_CODE=$?
    {% elif template.prompt_method == "stdin" %}
    cat "$PROMPT_FILE" | {{ template.command }} \
        --model "$MODEL" \
        {{ extra_flags | default("") }} \
        2>&1 | tee -a "$LOG_FILE" || EXIT_CODE=$?
    {% elif template.prompt_method == "arg" %}
    {{ template.command }} "$(cat $PROMPT_FILE)" \
        {{ extra_flags | default("") }} \
        2>&1 | tee -a "$LOG_FILE" || EXIT_CODE=$?
    {% endif %}

    # Report result
    if [ $EXIT_CODE -eq 0 ]; then
        ringmaster report-result "$TASK_ID" --status completed
    else
        ringmaster report-result "$TASK_ID" --status failed --exit-code $EXIT_CODE
    fi

    rm -f "$PROMPT_FILE"
    log "Finished task: $TASK_ID"
done
```

### LLM-Generated Scripts

When user provides `--from-description`, the LLM generates a complete script:

```python
async def generate_worker_script(description: str, template: WorkerTemplate | None = None) -> str:
    """Use LLM to generate a worker script from natural language."""

    prompt = f"""Generate a bash worker script for Ringmaster.

Description: {description}

The script must:
1. Poll for tasks using: ringmaster pull-task <worker-id> --capabilities <caps> --json
2. Build prompts using: ringmaster build-prompt <task-id> -o <file>
3. Execute the appropriate CLI tool
4. Report results using: ringmaster report-result <task-id> --status <status>
5. Handle SIGINT/SIGTERM gracefully
6. Log to the file specified by LOG_FILE environment variable

Environment variables available:
- WORKER_ID, WORKER_NAME, WORKER_TYPE
- LOG_FILE
- ANTHROPIC_API_KEY, OPENAI_API_KEY (if needed)
- RINGMASTER_PROMPT_FILE (path to prompt)
- RINGMASTER_TASK_ID

Return ONLY the bash script, no explanation.
"""

    # Call LLM
    response = await llm.complete(prompt)
    return response.strip()
```

---

## ADR-027: Worker Database Schema

```sql
-- Worker templates (optional - can be hardcoded)
CREATE TABLE IF NOT EXISTS worker_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    command TEXT NOT NULL,
    prompt_method TEXT NOT NULL,  -- flag, stdin, file, arg
    prompt_flag TEXT,
    required_env TEXT,  -- JSON array
    optional_env TEXT,  -- JSON array
    default_model TEXT,
    default_capabilities TEXT,  -- JSON array
    script_template TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Configured workers
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL,  -- template id or "custom"
    status TEXT NOT NULL DEFAULT 'offline',
    current_task_id TEXT,

    -- Configuration
    model TEXT,  -- Override template default
    capabilities TEXT,  -- JSON array
    env_overrides TEXT,  -- JSON object
    extra_flags TEXT,  -- Additional CLI flags

    -- The generated script
    generated_script TEXT,
    script_hash TEXT,  -- For detecting changes

    -- Stats
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    avg_completion_seconds REAL,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_active_at TEXT,

    -- Foreign keys
    FOREIGN KEY (current_task_id) REFERENCES tasks(id)
);

-- Worker run history (for debugging/audit)
CREATE TABLE IF NOT EXISTS worker_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id TEXT NOT NULL,
    task_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    exit_code INTEGER,
    log_path TEXT,

    FOREIGN KEY (worker_id) REFERENCES workers(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

---

## ADR-028: Worker Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                     WORKER LIFECYCLE                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────┐                                                  │
│   │   CREATED    │  ← ringmaster worker create                      │
│   └──────┬───────┘                                                  │
│          │                                                          │
│          │ ringmaster worker spawn                                  │
│          ▼                                                          │
│   ┌──────────────┐                                                  │
│   │   STARTING   │  ← tmux session created, script starting        │
│   └──────┬───────┘                                                  │
│          │                                                          │
│          │ script reaches main loop                                 │
│          ▼                                                          │
│   ┌──────────────┐     ┌──────────────┐                            │
│   │    IDLE      │────►│    BUSY      │  ← pulled task, executing  │
│   │  (polling)   │◄────│  (working)   │                            │
│   └──────┬───────┘     └──────────────┘                            │
│          │                                                          │
│          │ ringmaster worker stop / SIGTERM                        │
│          ▼                                                          │
│   ┌──────────────┐                                                  │
│   │   STOPPING   │  ← graceful shutdown                            │
│   └──────┬───────┘                                                  │
│          │                                                          │
│          │ cleanup complete                                         │
│          ▼                                                          │
│   ┌──────────────┐                                                  │
│   │   OFFLINE    │  ← ready to be spawned again                    │
│   └──────────────┘                                                  │
│                                                                      │
│   Error states:                                                      │
│   ┌──────────────┐                                                  │
│   │    FAILED    │  ← script crashed, config error                 │
│   └──────────────┘                                                  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ADR-029: Minimal CLI Implementation

### Commands for MVP

```python
# In cli.py, add worker subcommand group

@app.command("worker")
def worker_cmd():
    """Manage workers."""
    pass

@worker_cmd.command("templates")
def list_templates():
    """List available worker templates."""
    for tid, template in WORKER_TEMPLATES.items():
        print(f"{tid}: {template.name}")
        print(f"  {template.description}")
        print(f"  Command: {template.command}")
        print(f"  Requires: {', '.join(template.required_env)}")
        print()

@worker_cmd.command("create")
def create_worker(
    name: str,
    template: str = "claude-code",
    capabilities: str = "",
    model: str | None = None,
    from_description: str | None = None,
    script_file: str | None = None,
):
    """Create a new worker configuration."""
    # Validate template
    if template not in WORKER_TEMPLATES and template != "custom":
        raise ValueError(f"Unknown template: {template}")

    tmpl = WORKER_TEMPLATES.get(template)
    caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    # Generate script
    if script_file:
        script = Path(script_file).read_text()
    elif from_description:
        script = asyncio.run(generate_worker_script(from_description, tmpl))
    elif tmpl:
        script = render_template(tmpl.script_template, {
            "worker": {"id": f"worker-{uuid4().hex[:8]}", "name": name, "capabilities": caps, "model": model},
            "template": tmpl,
        })
    else:
        raise ValueError("Must provide --script-file or --from-description for custom template")

    # Create worker
    worker = Worker(
        name=name,
        type=template,
        capabilities=caps,
        model=model,
        generated_script=script,
    )

    repo = WorkerRepository(get_db())
    asyncio.run(repo.create(worker))

    print(f"Created worker: {worker.id}")

@worker_cmd.command("list")
def list_workers(status: str | None = None):
    """List configured workers."""
    repo = WorkerRepository(get_db())
    workers = asyncio.run(repo.list(status=status))

    for w in workers:
        status_icon = {"idle": "🟢", "busy": "🟡", "offline": "⚪", "failed": "🔴"}.get(w.status, "❓")
        print(f"{status_icon} {w.id}: {w.name} ({w.type})")
        if w.capabilities:
            print(f"   Capabilities: {', '.join(w.capabilities)}")

@worker_cmd.command("spawn")
def spawn_worker(worker_id: str):
    """Spawn (start) a worker."""
    repo = WorkerRepository(get_db())
    worker = asyncio.run(repo.get(worker_id))

    if not worker:
        raise ValueError(f"Worker not found: {worker_id}")

    spawner = WorkerSpawner()
    result = asyncio.run(spawner.spawn(
        worker_id=worker.id,
        worker_name=worker.name,
        worker_type=worker.type,
        capabilities=worker.capabilities,
        generated_script=worker.generated_script,
    ))

    print(f"Spawned: {result.tmux_session}")
    print(f"Attach: {spawner.attach_command(worker_id)}")

@worker_cmd.command("stop")
def stop_worker(worker_id: str):
    """Stop a running worker."""
    spawner = WorkerSpawner()
    asyncio.run(spawner.kill(worker_id))
    print(f"Stopped: {worker_id}")
```

---

## Implementation Priority

1. **Add worker templates** - Hardcode WORKER_TEMPLATES dict
2. **Add CLI commands** - `ringmaster worker create/list/spawn/stop`
3. **Update spawner** - Use worker.generated_script
4. **Add migration** - worker_templates and workers tables
5. **Web UI** - Built later by Ringmaster

## Success Criteria

- [ ] `ringmaster worker templates` lists available templates
- [ ] `ringmaster worker create --name test --template claude-code` creates a worker
- [ ] `ringmaster worker list` shows the worker
- [ ] `ringmaster worker spawn test` starts the worker in tmux
- [ ] Worker polls for tasks and can execute them
- [ ] `ringmaster worker stop test` stops the worker
