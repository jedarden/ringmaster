# Ringmaster Marathon Session v2 - Feature Completion

## CRITICAL: Autonomous Execution Mode

**YOU MUST NEVER STOP TO ASK FOR HUMAN INPUT.** This is a marathon-coding session designed to run autonomously.

### Decision Making Rules

1. **Never ask permission** - All reversible operations are pre-approved (file edits, git commits, git push, npm/cargo commands)
2. **Pick and proceed** - When facing multiple approaches, pick the simpler one and go
3. **Experiment, don't deliberate** - If uncertain, try it and see what happens
4. **Backtrack freely** - If an approach fails, revert and try another without asking
5. **Document decisions in commits** - Use commit messages to explain choices made

### When Multiple Paths Exist

If you encounter 2+ valid approaches:

1. **Log the experiment** in `prompts/.marathon/experiments.md`
2. **Try the first option** - implement it fully
3. **Evaluate results** - does it work? Is it clean?
4. **If it fails**, revert and try the alternative
5. **Log the outcome**

---

## Project Context

**Repository**: `/home/coder/ringmaster`
**GitHub**: `jedarden/ringmaster`
**Issue**: #1 (Marathon Coding: Build Ringmaster MVP)
**Tech Stack**: Rust (Axum, SQLx, SQLite), React (TypeScript, Vite, Tailwind)

## Current State (as of 2026-01-24)

### Completed Features
- Core state machine (16 card states)
- Loop manager (Ralph-Wiggum pattern)
- CLI Platform abstraction (Claude Code)
- Integration clients: GitHub Actions, ArgoCD, Kubernetes, Docker Hub, Git
- Action executor wiring all integrations
- Backend compiles, 271+ tests pass
- Frontend builds (Vite)

### What This Session Will Complete

---

## Phase 1: Integration Tests with Claude Code CLI

**Priority**: HIGH
**Estimated Scope**: 3 files, ~400 lines

### Goal
Create end-to-end integration tests that verify the Claude Code CLI platform actually works when executing coding tasks.

### Implementation Plan

1. **Create test harness** (`tests/integration/claude_code_test.rs`):
   ```rust
   // Test that we can:
   // - Start a Claude Code session
   // - Send a simple coding prompt
   // - Receive streamed JSON events
   // - Verify session completes
   ```

2. **Mock workspace setup**:
   - Create a temp directory with a simple Rust/JS project
   - Provide a trivial task (e.g., "add a function that returns 42")
   - Verify the file was modified

3. **Test environment detection**:
   - Skip tests gracefully if `claude` CLI not installed
   - Use `#[ignore]` attribute for CI environments without Claude

### Files to Create/Modify
- `tests/integration/mod.rs` - Module declaration
- `tests/integration/claude_code.rs` - Integration tests
- `tests/fixtures/simple_project/` - Test fixture

### Success Criteria
- `cargo test --test integration` passes when Claude CLI is available
- Tests skip gracefully when CLI is unavailable
- At least 3 test cases: start session, complete task, handle error

---

## Phase 2: Session Resumption for Interrupted Loops

**Priority**: HIGH
**Estimated Scope**: 5 files, ~600 lines

### Goal
Allow paused or crashed loops to resume from their last checkpoint rather than restarting from scratch.

### Implementation Plan

1. **Add checkpoint persistence** (`src/loops/checkpoint.rs`):
   ```rust
   pub struct LoopCheckpoint {
       pub card_id: Uuid,
       pub iteration: u32,
       pub last_prompt: String,
       pub last_response_summary: String,
       pub file_changes: Vec<FileChange>,
       pub created_at: DateTime<Utc>,
   }
   ```

2. **Database schema** (`migrations/XXXXXX_add_checkpoints.sql`):
   ```sql
   CREATE TABLE loop_checkpoints (
       id TEXT PRIMARY KEY,
       card_id TEXT NOT NULL REFERENCES cards(id),
       iteration INTEGER NOT NULL,
       state_json TEXT NOT NULL,
       created_at TEXT NOT NULL
   );
   ```

3. **Checkpoint save points**:
   - After each successful iteration completion
   - Before starting external operations (build, deploy)
   - Limit to last 3 checkpoints per card

4. **Resume logic** (`src/loops/platform_executor.rs`):
   - On loop start, check for existing checkpoint
   - If found, restore context and continue from that iteration
   - Clear checkpoints on successful card completion

### Files to Create/Modify
- `src/loops/checkpoint.rs` - New checkpoint module
- `src/loops/mod.rs` - Export checkpoint
- `src/loops/platform_executor.rs` - Add checkpoint save/restore
- `migrations/XXXXXX_add_checkpoints.sql` - Schema
- `src/db/mod.rs` - Checkpoint CRUD operations

### Success Criteria
- Loop can be paused and resumed without losing progress
- Crashed loops auto-resume on restart
- Checkpoints are cleaned up after completion

---

## Phase 3: Aider Platform Support

**Priority**: MEDIUM
**Estimated Scope**: 4 files, ~350 lines

### Goal
Add Aider as an alternative coding platform alongside Claude Code.

### Implementation Plan

1. **Aider platform implementation** (`src/platforms/aider.rs`):
   ```rust
   pub struct AiderPlatform {
       config_dir: Option<PathBuf>,
       model: String,  // e.g., "gpt-4", "claude-3-opus"
   }

   impl CodingPlatform for AiderPlatform {
       // Implement trait methods
       // Uses `aider` CLI with --yes-always flag for non-interactive mode
   }
   ```

2. **Aider stream parser** (`src/platforms/aider_parser.rs`):
   - Parse Aider's output format
   - Detect file changes, errors, completions

3. **Config extension**:
   ```toml
   [[subscriptions]]
   name = "aider-gpt4"
   platform = "aider"
   model = "gpt-4"
   enabled = true
   priority = 2
   ```

4. **Platform registry update**:
   - Auto-detect Aider installation
   - Register in platform registry at startup

### Files to Create/Modify
- `src/platforms/aider.rs` - Aider implementation
- `src/platforms/aider_parser.rs` - Output parser
- `src/platforms/mod.rs` - Export and register
- `src/config/mod.rs` - Aider config options

### Success Criteria
- `cargo test` passes with Aider platform tests
- Can start a loop with Aider as the platform
- Proper error handling when Aider not installed

---

## Phase 4: API Metrics & Monitoring

**Priority**: MEDIUM
**Estimated Scope**: 4 files, ~400 lines

### Goal
Track token usage, costs, and performance metrics across all coding sessions.

### Implementation Plan

1. **Metrics types** (`src/metrics/mod.rs`):
   ```rust
   pub struct SessionMetrics {
       pub card_id: Uuid,
       pub platform: String,
       pub subscription: String,
       pub input_tokens: u64,
       pub output_tokens: u64,
       pub estimated_cost_usd: f64,
       pub duration_seconds: u64,
       pub iterations: u32,
       pub success: bool,
   }
   ```

2. **Database schema** (`migrations/XXXXXX_add_metrics.sql`):
   ```sql
   CREATE TABLE session_metrics (
       id TEXT PRIMARY KEY,
       card_id TEXT NOT NULL,
       platform TEXT NOT NULL,
       subscription TEXT,
       input_tokens INTEGER DEFAULT 0,
       output_tokens INTEGER DEFAULT 0,
       estimated_cost_usd REAL DEFAULT 0,
       duration_seconds INTEGER DEFAULT 0,
       iterations INTEGER DEFAULT 0,
       success INTEGER DEFAULT 0,
       created_at TEXT NOT NULL
   );
   ```

3. **Metric collection points**:
   - After each platform session completes
   - Parse token counts from Claude Code/Aider output
   - Calculate costs based on model pricing

4. **API endpoints** (`src/api/metrics.rs`):
   - `GET /api/metrics/summary` - Overall stats
   - `GET /api/metrics/by-card/:id` - Per-card metrics
   - `GET /api/metrics/by-subscription` - Per-subscription breakdown

### Files to Create/Modify
- `src/metrics/mod.rs` - Metrics types and collection
- `src/api/metrics.rs` - API endpoints
- `src/api/mod.rs` - Route registration
- `migrations/XXXXXX_add_metrics.sql` - Schema

### Success Criteria
- Metrics recorded for each completed session
- API endpoints return accurate data
- Frontend can display usage dashboard (future phase)

---

## Phase 5: Integration Hub Refactor

**Priority**: LOW
**Estimated Scope**: 2 files, ~200 lines

### Goal
Create a unified IntegrationHub that coordinates all services with proper lifecycle management.

### Implementation Plan

1. **Integration Hub** (`src/integrations/hub.rs`):
   ```rust
   pub struct IntegrationHub {
       github: Arc<GitHubClient>,
       argocd: Option<Arc<ArgoCDClient>>,
       kubernetes: Option<Arc<KubernetesService>>,
       dockerhub: Arc<DockerHubClient>,
   }

   impl IntegrationHub {
       pub async fn new_from_config(config: &Config) -> Result<Self>;
       pub fn github(&self) -> &GitHubClient;
       // etc.
   }
   ```

2. **Inject into ActionExecutor**:
   - Replace individual client fields with IntegrationHub
   - Simplify constructor

### Files to Create/Modify
- `src/integrations/hub.rs` - Hub implementation
- `src/state_machine/actions.rs` - Use hub

### Success Criteria
- Clean separation of integration lifecycle
- All existing tests pass
- Easier to add new integrations

---

## Per-Iteration Instructions

Each iteration, you should:

1. **Re-read this prompt** - Check for hot-reloaded changes
2. **Check experiments log** - Review `prompts/.marathon/experiments.md`
3. **Assess** - `cargo check && cargo test`
4. **Pick next phase/task** - Work on one phase at a time, one task at a time
5. **Implement** - Follow existing patterns
6. **Verify** - `cargo check && cargo test`
7. **Commit & Push**:
   ```bash
   git add -A
   git commit -m "feat(phase): description" -m "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
   git push origin main
   ```
8. **Update Issue #1** - Comment on progress after each phase

---

## Coding Standards

- Follow existing code patterns
- Use `anyhow` for errors in binaries, `thiserror` for libraries
- Add tests for new functionality
- Keep functions focused (<50 lines when possible)
- Use async/await patterns consistent with Axum

## Reference Files

- `docs/00-architecture-overview.md` - System architecture
- `docs/04-integrations.md` - Integration specs
- `src/platforms/claude_code.rs` - Platform implementation reference
- `src/state_machine/actions.rs` - Action executor reference

## Completion Signal

When all 5 phases are complete and tests pass:

1. Add final comment to issue #1 summarizing all work
2. Output: `<ringmaster>SESSION_V2_COMPLETE</ringmaster>`

## Important Notes

- This prompt is **hot-reloadable** - edit it anytime to adjust instructions
- Git push is pre-approved - do not ask for confirmation
- If a phase is blocked, skip to the next and return later
- Document blockers in `prompts/.marathon/experiments.md`
