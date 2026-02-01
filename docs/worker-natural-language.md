# Natural Language Worker Configuration

> Simplified worker configuration: just name, description, model, and a start script with prompt placeholder

## Problem

Creating workers previously required:
- Complex configuration with many fields
- Understanding command vs args structure
- Manual capability tagging
- Knowledge of prompt flags and positions

## Solution

**Simplified worker configuration** with just:
- `name` - Worker identifier
- `description` (optional) - Human-readable description
- `model` (optional) - Default model to use
- `start_script` - Shell script with `{model}` and `{prompt}` placeholders

## Usage

### Python API

#### Parse a Natural Language Description

```python
from ringmaster.worker import parse_worker_description

result = parse_worker_description("claude code with opus")

print(result.name)        # "claude-code"
print(result.model)       # "claude-opus-4-20250514"
print(result.start_script) # "claude --model {model} --print -- {prompt}"
```

#### Create a Worker

```python
from ringmaster.worker import create_worker

worker = create_worker("aider with sonnet")

print(worker.name)         # "aider"
print(worker.model)        # "claude-sonnet-4-20250514"
print(worker.start_script) # "aider --model {model} --message {prompt} --yes"
```

#### Build a Command

```python
# Build command with specific model and prompt
cmd = worker.build_command(model="claude-opus-4-20250514", prompt="fix the bug")
# ["aider", "--model", "claude-opus-4-20250514", "--message", "fix", "the", "bug", "--yes"]

# Build command with default model
cmd = worker.build_command(prompt="test")
# ["aider", "--model", "claude-sonnet-4-20250514", "--message", "test", "--yes"]
```

#### List Available Workers

```python
from ringmaster.worker import list_workers, list_all_workers

# List only installed workers
available = list_workers()

# List all registered workers (even if not installed)
all_workers = list_all_workers()

for worker in all_workers:
    print(f"{worker.name}: {worker.description}")
    print(f"  model: {worker.model}")
    print(f"  script: {worker.start_script}")
```

#### Register a Custom Worker

```python
from ringmaster.worker import WorkerDefinition, register_worker

custom = WorkerDefinition(
    name="my-tool",
    description="My custom coding assistant",
    model="gpt-4o",
    start_script="my-tool --model {model} --prompt {prompt}",
)
register_worker(custom)
```

### CLI

#### Create from Natural Language

```bash
# Simple
ringmaster worker create "claude code with sonnet"

# With model override
ringmaster worker create "aider using opus"

# See all workers
ringmaster worker types
```

### API

#### Create from Natural Language

```bash
POST /api/workers/natural

{
    "description": "claude code with sonnet",
    "worker_id": "my-worker"  // optional
}
```

Response:
```json
{
    "success": true,
    "worker_id": "my-worker",
    "worker_type": "claude-code",
    "model": "claude-sonnet-4-20250514",
    "parsed_description": "Using claude-code with claude-sonnet-4-20250514",
    "confidence": 1.0
}
```

#### Parse Description

```bash
POST /api/workers/parse

{
    "description": "claude code with opus"
}
```

Response:
```json
{
    "success": true,
    "worker_type": "claude-code",
    "model": "claude-opus-4-20250514",
    "confidence": 1.0
}
```

#### List Worker Types

```bash
GET /api/workers/types
```

Response:
```json
{
    "workers": [
        {
            "name": "claude-code",
            "description": "Anthropic's Claude Code CLI",
            "available": true,
            "default_model": "claude-sonnet-4-20250514",
            "start_script": "claude --model {model} --print -- {prompt}"
        },
        {
            "name": "aider",
            "description": "Aider AI coding assistant",
            "available": false,
            "default_model": "claude-3-5-sonnet-20241022",
            "start_script": "aider --model {model} --message {prompt} --yes"
        }
    ],
    "total": 2
}
```

## Default Workers

| Name | Description | Model | Start Script |
|------|-------------|-------|--------------|
| **claude-code** | Anthropic's Claude Code CLI | claude-sonnet-4-20250514 | `claude --model {model} --print -- {prompt}` |
| **aider** | Aider AI coding assistant | claude-3-5-sonnet-20241022 | `aider --model {model} --message {prompt} --yes` |
| **cursor** | Cursor AI (CLI mode) | gpt-4o | `cursor --model {model} --message {prompt}` |
| **opencode** | OpenCode AI | gpt-4o | `opencode --model {model} --prompt {prompt}` |
| **codex** | Codex CLI | gpt-4o | `codex --model {model} --message {prompt}` |
| **goose** | Goose AI | gpt-4o | `goose --model {model} {prompt}` |
| **kilo** | Kilo Code | gpt-4o | `kilo --model {model} {prompt}` |

## Natural Language Patterns

### Worker Names

| Pattern | Worker |
|---------|--------|
| claude code, claude cli, claude | claude-code |
| aider | aider |
| cursor | cursor |
| opencode | opencode |
| codex cli | codex |
| goose | goose |
| kilo code | kilo |

### Models

| Pattern | Model ID |
|---------|----------|
| opus | claude-opus-4-20250514 |
| sonnet-4, sonnet | claude-sonnet-4-20250514 |
| 3.5-sonnet, sonnet-3.5 | claude-3-5-sonnet-20241022 |
| haiku | claude-3-5-haiku-20241022 |
| gpt-4o | gpt-4o |
| gpt-4 turbo | gpt-4-turbo |

### Pattern Examples

| Description | Parsed As |
|-------------|-----------|
| "claude code with sonnet" | name=claude-code, model=claude-sonnet-4-20250514 |
| "aider using opus" | name=aider, model=claude-opus-4-20250514 |
| "cursor" | name=cursor, model=gpt-4o (default) |

## Script Templates

Each worker is defined by a start script with placeholders:

- `{model}` - Replaced with the model ID
- `{prompt}` - Replaced with the user's prompt

**Example: Claude Code**

```python
# Definition
WorkerDefinition(
    name="claude-code",
    model="claude-sonnet-4-20250514",
    start_script="claude --model {model} --print -- {prompt}",
)

# When executed with model="claude-opus-4-20250514" and prompt="fix the bug":
# Result: claude --model claude-opus-4-20250514 --print -- fix the bug
```

## Extensibility

### Add a New Worker

```python
from ringmaster.worker import WorkerDefinition, register_worker

register_worker(
    WorkerDefinition(
        name="my-custom-tool",
        description="My custom AI coding assistant",
        model="my-default-model",
        start_script="my-tool --model {model} -- {prompt}",
    )
)
```

### Custom Script Template

Your script can use any shell syntax:

```python
WorkerDefinition(
    name="complex-worker",
    start_script="""
        export MODEL={model}
        cd /workspace
        my-tool --model "$MODEL" --prompt "{prompt}" 2>&1 | tee output.log
    """,
)
```

## Implementation Details

### WorkerDefinition Class

```python
@dataclass
class WorkerDefinition:
    """A worker is just a script template."""

    name: str                    # Unique identifier
    start_script: str            # Shell script with {model} and {prompt} placeholders
    description: str | None      # Human-readable description
    model: str | None            # Default model

    def build_command(self, model: str | None = None, prompt: str = "") -> list[str]:
        """Build the command list for subprocess execution."""

    def is_available(self) -> bool:
        """Check if the worker's command is available on the system."""
```

### WorkerConfig Class

```python
class WorkerConfig(BaseModel):
    """Result of parsing natural language."""

    success: bool
    name: str | None
    description: str | None
    model: str | None
    start_script: str | None
    error: str | None
    confidence: float
    suggestions: list[str]
```

### Parser

The `NaturalWorkerParser` uses regex patterns to extract:
1. Worker name from common aliases
2. Model from version nicknames
3. Returns a `WorkerConfig` with all information

## Architecture

```
Natural Language Description
        │
        ▼
┌─────────────────────────────────────┐
│  NaturalWorkerParser                 │
│                                     │
│  1. Extract worker name             │
│     - Pattern matching              │
│     - Supports aliases              │
│                                     │
│  2. Extract model                   │
│     - Claude: opus, sonnet, haiku   │
│     - Other: gpt-4o, gemini, glm    │
│     - Uses default if not specified │
│                                     │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  WorkerConfig (result)               │
│  - name: str                        │
│  - model: str | None                │
│  - start_script: str | None         │
│  - description: str | None          │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  create_worker()                     │
│  Returns WorkerDefinition            │
│  - Can build commands                │
│  - Can check availability            │
└─────────────────────────────────────┘
```

## Migration from Old API

If you were using the old API with capabilities, `WorkerConfig`, etc.:

```python
# Old API (removed)
from ringmaster.worker.natural import (
    WorkerConfig,
    NaturalWorkerFactory,
    create_worker_from_description,
    suggest_worker_improvements,
    get_worker_definition,
    list_available_workers,
)

# New API (simplified)
from ringmaster.worker import (
    WorkerConfig,           # Still exists, but simplified
    WorkerDefinition,       # New simplified class
    create_worker,          # Renamed from create_worker_from_description
    # suggest_worker_improvements removed
    get_worker,             # Renamed from get_worker_definition
    list_workers,           # Renamed from list_available_workers
    list_all_workers,       # New: lists all workers
    parse_worker_description,
    register_worker,        # New: register custom workers
)
```
