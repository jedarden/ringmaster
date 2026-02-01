# Worker Interface

## Design Philosophy

**Use CLI tools as-is. The only abstraction is text input.**

Ringmaster does not wrap, modify, or abstract the underlying LLM coding tools. Each worker is invoked via its native CLI with a text prompt. This keeps Ringmaster:

- **Decoupled** from tool internals
- **Future-proof** as new tools emerge
- **Simple** to add new worker types

## Worker Types

### Claude Code (Headless)

Anthropic's official CLI in non-interactive mode.

```bash
claude --print --dangerously-skip-permissions \
  --model claude-sonnet-4-20250514 \
  --prompt "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Strong reasoning and planning
- Excellent tool use
- Multi-file editing
- Native MCP support

**Invocation:**
- Input: Text prompt via `--prompt` or stdin
- Output: Stdout (conversation + tool calls)
- Working dir: Set via `cd` before invocation
- Session: Stateless (each invocation is fresh)

### Codex CLI (OpenAI)

OpenAI's terminal coding agent.

```bash
codex --quiet --auto-approve \
  --model gpt-5-codex \
  "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Fast iteration
- Strong at refactoring
- Good test generation

**Invocation:**
- Input: Text prompt as positional argument
- Output: Stdout
- Working dir: Current directory
- Session: Stateless

### Aider

Popular open-source coding assistant.

```bash
aider --yes --no-git \
  --model claude-sonnet-4-20250514 \
  --message "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Multi-model support
- Git-aware editing
- Architect/editor modes

**Invocation:**
- Input: `--message` flag
- Output: Stdout + file changes
- Working dir: Git repo root
- Session: Can maintain context via `--chat-history-file`

### Goose

Block's extensible AI agent.

```bash
goose run --non-interactive \
  --prompt "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Plugin ecosystem
- Extensible toolkits
- Memory system

**Invocation:**
- Input: `--prompt` flag
- Output: Stdout
- Working dir: Current directory
- Session: Stateless (or via session files)

### Kilo Code

Local/private coding assistant.

```bash
kilo --headless \
  --input "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Runs locally
- Privacy-focused
- Customizable

### Codebuff

Lightweight terminal coding tool.

```bash
codebuff --auto \
  "$(cat enriched_prompt.txt)"
```

**Strengths:**
- Fast startup
- Minimal overhead
- Good for small tasks

## Worker Registration

Workers are registered in configuration, not code:

```toml
# ringmaster.toml

[[workers]]
name = "claude-code-1"
type = "claude-code"
command = "claude"
args = ["--print", "--dangerously-skip-permissions", "--model", "claude-sonnet-4-20250514"]
prompt_flag = "--prompt"
working_dir = "/workspace"
timeout_seconds = 1800
max_concurrent = 3

[[workers]]
name = "codex-1"
type = "codex"
command = "codex"
args = ["--quiet", "--auto-approve"]
prompt_flag = ""  # positional argument
working_dir = "/workspace"
timeout_seconds = 900
max_concurrent = 2

[[workers]]
name = "aider-1"
type = "aider"
command = "aider"
args = ["--yes", "--no-git", "--model", "claude-sonnet-4-20250514"]
prompt_flag = "--message"
working_dir = "/workspace"
timeout_seconds = 1200
max_concurrent = 2
```

## Launcher Scripts

For maximum flexibility, workers can use **custom launcher scripts** instead of built-in commands. This allows:

1. **Custom API endpoints** - Use Claude Max, Z.AI, or other providers
2. **Custom environment variables** - Pass API keys, model settings
3. **Complex launch logic** - Pre-flight checks, configuration loading
4. **Model-specific workers** - Different workers for Sonnet, Opus, Haiku

### Launcher Script Environment

When a launcher script is invoked, Ringmaster sets these environment variables:

| Variable | Description |
|----------|-------------|
| `RINGMASTER_PROMPT_FILE` | Path to file containing the enriched prompt |
| `RINGMASTER_WORKING_DIR` | Working directory for the task |
| `RINGMASTER_TASK_ID` | Task/bead identifier |
| `RINGMASTER_WORKER_ID` | Worker identifier |
| `RINGMASTER_LOG_FILE` | Path to worker log file |

### Example: Custom Launcher Script

```bash
#!/bin/bash
# workers/claude-max-launcher.sh

# Read environment variables
PROMPT_FILE="${RINGMASTER_PROMPT_FILE}"
WORKING_DIR="${RINGMASTER_WORKING_DIR}"

# Custom configuration
export CLAUDE_MAX_API_KEY="${CLAUDE_MAX_API_KEY}"
export CLAUDE_MAX_BASE_URL="${CLAUDE_MAX_BASE_URL}"

# Execute with custom endpoint
cd "$WORKING_DIR" || exit 1
claude --print --dangerously-skip-permissions \
    --api-url "$CLAUDE_MAX_BASE_URL" \
    --prompt "$(cat "$PROMPT_FILE")"
```

### Registering Workers with Launcher Scripts

```bash
# Using CLI
ringmaster worker add claude-max-1 \
  --type claude-code \
  --launcher-script /path/to/claude-max-launcher.sh \
  --capabilities python rust

# Spawn with launcher script
ringmaster worker spawn claude-max-1 \
  --type claude-code \
  --launcher-script ./workers/claude-max-launcher.sh \
  --capabilities python
```

### Inline Launcher Scripts

Alternatively, store the script content directly in the worker configuration:

```python
worker = Worker(
    name="custom-worker",
    type="launcher",
    launcher_script_inline='''#!/bin/bash
cd "$RINGMASTER_WORKING_DIR" || exit 1
my-agent --prompt "$(cat $RINGMASTER_PROMPT_FILE)"
''',
    capabilities=["python"],
)
```

See `workers/README.md` for more examples and documentation.

## Invocation Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  RINGMASTER                                                          │
│                                                                      │
│  1. Select ready task from queue                                     │
│  2. Find available worker                                            │
│  3. Write enriched prompt to temp file                               │
│  4. Build command:                                                   │
│     {command} {args} {prompt_flag} "$(cat /tmp/prompt_xyz.txt)"     │
│  5. Execute in working_dir                                           │
│  6. Capture stdout/stderr                                            │
│  7. Parse output for completion signals                              │
│  8. Update task status                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Output Parsing

Ringmaster doesn't understand tool-specific output formats. Instead, it looks for **universal signals** in stdout:

### Success Indicators
```
✓ All tests passing
✓ Build successful
✓ Task complete
✓ Changes committed
```

### Failure Indicators
```
✗ Tests failing
✗ Build error
✗ Compilation failed
✗ Unable to complete
```

### Decision Needed
```
? Need clarification
? Multiple options
? Blocked on decision
? User input required
```

Workers are prompted to emit these signals in their enriched prompts.

## Prompt Template

Every worker receives the same structure:

```markdown
# Task: {task.id}

## Objective
{task.title}

## Context
{enriched_context}

## Requirements
{task.description}

## Acceptance Criteria
{task.acceptance_criteria}

## Files
{relevant_files}

## Instructions
1. Implement the requirements
2. Run tests: {test_command}
3. If tests pass, output: ✓ Task complete
4. If tests fail, fix and retry
5. If stuck after {max_attempts} attempts, output: ? Blocked on decision
6. If you need clarification, output: ? Need clarification: <your question>

## Constraints
- Do not modify files outside the task scope
- Commit messages should reference {task.id}
- Maximum iterations: {max_attempts}
```

## Worker Pool Management

```
┌─────────────────────────────────────────────────────────────────────┐
│  WORKER POOL                                                         │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │claude-code-1│  │claude-code-2│  │claude-code-3│  ← max_concurrent│
│  │   [busy]    │  │   [idle]    │  │   [busy]    │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐                                   │
│  │  codex-1    │  │  codex-2    │                                   │
│  │   [idle]    │  │   [busy]    │                                   │
│  └─────────────┘  └─────────────┘                                   │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐                                   │
│  │  aider-1    │  │  aider-2    │                                   │
│  │   [idle]    │  │   [idle]    │                                   │
│  └─────────────┘  └─────────────┘                                   │
│                                                                      │
│  Available: 4  |  Busy: 3  |  Total: 7                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Worker Selection Strategy

When a task is ready, Ringmaster selects a worker based on:

1. **Availability** - Must be idle
2. **Affinity** - Some tasks prefer certain workers (configurable)
3. **Round-robin** - Default: spread load across worker types
4. **Performance** - Optional: weight by historical success rate

```toml
# Task-level worker affinity (optional)
[task.preferences]
preferred_workers = ["claude-code"]  # Strong reasoning tasks
fallback_workers = ["codex", "aider"]
```

## Adding New Workers

To add support for a new CLI tool:

1. Add entry to `ringmaster.toml`
2. Test invocation manually
3. Verify output signal parsing

No code changes required. The text-in/text-out abstraction handles everything.
