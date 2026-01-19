# CLI Platform Implementation - Marathon Coding Prompt

## CRITICAL: Autonomous Execution Mode

**YOU MUST NEVER STOP TO ASK FOR HUMAN INPUT.** This is a marathon-coding session designed to run autonomously.

### Decision Making Rules

1. **Never ask permission** - All reversible operations are pre-approved (file edits, git commits, git push, cargo commands)
2. **Pick and proceed** - When facing multiple approaches, pick the simpler one and go
3. **Experiment, don't deliberate** - If uncertain, try it and see what happens
4. **Backtrack freely** - If an approach fails, revert and try another without asking
5. **Document decisions in commits** - Use commit messages to explain choices made

### When Multiple Paths Exist

If you encounter 2+ valid approaches:

1. **Log the experiment** in `prompts/.marathon/experiments.md`
2. **Try the first option** - implement it fully
3. **Evaluate results** - does it work? Is it clean?
4. **If it fails or is suboptimal**, revert and try option B
5. **Log the outcome**

---

## Project Context

**Repository**: `/home/coder/ringmaster`
**GitHub**: `jedarden/ringmaster`
**Tech Stack**: Rust (Axum, SQLx, SQLite), React (TypeScript, Vite, Tailwind)

## Objective

Replace the current direct Claude API implementation with CLI-based execution using Claude Code (and other platforms). This enables users to leverage their Claude Max/Pro subscriptions instead of pay-per-token API billing.

## Architecture Change

### REMOVE (Current - Wrong)

```rust
// src/integrations/claude.rs - Direct API calls
pub struct ClaudeClient {
    api_key: String,  // ANTHROPIC_API_KEY
    // ...
}

impl ClaudeClient {
    pub async fn complete(&self, ...) {
        self.client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &self.api_key)
            // Pay-per-token billing!
    }
}
```

### ADD (New - Correct)

```rust
// src/platforms/mod.rs - CLI-based execution
pub trait CodingPlatform: Send + Sync {
    async fn start_session(&self, worktree: &Path, prompt: &str, config: &SessionConfig)
        -> Result<SessionHandle, PlatformError>;
    fn event_stream(&self, handle: &SessionHandle) -> impl Stream<Item = SessionEvent>;
    async fn stop_session(&self, handle: &SessionHandle) -> Result<SessionResult, PlatformError>;
}

// src/platforms/claude_code.rs
pub struct ClaudeCodePlatform {
    config_dir: PathBuf,  // ~/.claude or custom for multi-account
    model: String,
    max_turns: u32,
}

impl CodingPlatform for ClaudeCodePlatform {
    async fn start_session(&self, worktree: &Path, prompt: &str, ...) {
        Command::new("claude")
            .current_dir(worktree)
            .env("CLAUDE_CONFIG_DIR", &self.config_dir)
            .arg("--dangerously-skip-permissions")
            .arg("--output-format").arg("stream-json")
            .arg("--model").arg(&self.model)
            .arg("-p").arg(prompt)
            .spawn()
        // Uses Max/Pro subscription - flat rate!
    }
}
```

## Implementation Tasks

### Phase 1: Platform Abstraction

1. **Create `src/platforms/` module**
   - `mod.rs` - CodingPlatform trait, SessionHandle, SessionEvent, etc.
   - `claude_code.rs` - ClaudeCodePlatform implementation
   - `stream_parser.rs` - Parse Claude Code's JSON stream output

2. **Define core types**
   ```rust
   pub struct SessionHandle {
       pub id: Uuid,
       pub process: Child,
       pub stdout: BufReader<ChildStdout>,
   }

   pub enum SessionEvent {
       Started { session_id: String },
       Message { role: String, content: String },
       ToolUse { tool: String, input: Value },
       ToolResult { output: String },
       Completed { duration_ms: u64, cost_usd: f64 },
       Error { message: String },
   }

   pub struct SessionResult {
       pub success: bool,
       pub output: String,
       pub duration_ms: u64,
       pub iterations: u32,
   }
   ```

### Phase 2: Subscription Configuration

1. **Update `src/config/mod.rs`**
   ```rust
   #[derive(Debug, Clone, Serialize, Deserialize)]
   pub struct Subscription {
       pub name: String,
       pub platform: String,  // "claude-code", "aider", etc.
       pub config_dir: Option<PathBuf>,
       pub model: Option<String>,
       pub max_concurrent: u32,
   }

   pub struct Config {
       // ...existing...
       pub subscriptions: Vec<Subscription>,
   }
   ```

2. **Add subscription selection to Project/Card**
   - `project.default_subscription: Option<String>`
   - `card.subscription_override: Option<String>`

### Phase 3: Update LoopExecutor

1. **Replace ClaudeClient with CodingPlatform**
   ```rust
   pub struct LoopExecutor {
       pool: SqlitePool,
       event_bus: EventBus,
       loop_manager: Arc<RwLock<LoopManager>>,
       platform: Arc<dyn CodingPlatform>,  // NEW
       // Remove: claude_client: ClaudeClient
   }
   ```

2. **Update `run_iteration` to use platform**
   - Spawn Claude Code process
   - Stream and parse JSON events
   - Detect completion signal in output
   - Handle process lifecycle

### Phase 4: JSON Stream Parser

1. **Parse Claude Code output format**
   ```json
   {"type":"user","message":{...},"session_id":"..."}
   {"type":"assistant","message":{...}}
   {"type":"result","duration_ms":1234,"cost_usd":0.05}
   ```

2. **Extract key information**
   - Completion signal detection
   - Error detection
   - Token/cost tracking (for metrics, even if subscription-based)
   - Commit SHA extraction

### Phase 5: Multi-Account Support

1. **Subscription registry**
   - Load subscriptions from config
   - Track concurrent sessions per subscription
   - Select subscription for new sessions (project default or card override)

2. **Environment isolation**
   - Set `CLAUDE_CONFIG_DIR` per subscription
   - Each subscription uses its own auth credentials

### Phase 6: Migration & Cleanup

1. **Remove deprecated code**
   - `src/integrations/claude.rs` (direct API client)
   - `ANTHROPIC_API_KEY` references in config
   - API-based cost calculation (keep for metrics but note it's subscription-based)

2. **Update tests**
   - Mock CodingPlatform for unit tests
   - Integration tests with actual Claude Code CLI

## Reference Implementation

See the marathon-coding skill for a working example:
- `~/.claude/skills/marathon-coding/launcher.sh` - Shell-based Claude Code invocation
- `~/.claude/skills/marathon-coding/stream-parser.sh` - JSON stream parsing

## Success Criteria

1. **All existing tests pass** - `cargo test` succeeds
2. **New platform tests pass** - Unit tests for CodingPlatform implementations
3. **Integration works** - Can start a loop using Claude Code CLI
4. **Multi-subscription works** - Can configure and use multiple subscriptions
5. **No API key required** - Loops work without ANTHROPIC_API_KEY (uses Claude Code auth)

## Per-Iteration Instructions

Each iteration, you should:

1. **Re-read this prompt** - Check for hot-reloaded changes
2. **Check experiments log** - Review `prompts/.marathon/experiments.md`
3. **Assess** - Run `cargo check`, `cargo test`
4. **Implement** - Work on the next task in sequence
5. **Verify** - Run `cargo check` and `cargo test`
6. **Commit & Push**:
   ```bash
   git add -A
   git commit -m "feat: description" -m "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
   git push origin main
   ```

## Completion Signal

When all tasks are complete and tests pass:
1. Run full test suite: `cargo test`
2. Build release: `cargo build --release`
3. Output: `<ringmaster>COMPLETE</ringmaster>`

## Hot-Reload Notes

This file is re-read at the start of each iteration. Edit it to adjust instructions.
