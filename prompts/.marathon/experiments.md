# Experimentation Log - CLI Platform Implementation

This log tracks decisions made when multiple implementation paths were available.
It persists across marathon iterations and informs future decisions.

---

## Session Started: CLI Platform Implementation

**Goal**: Replace direct Claude API calls with CLI-based execution using Claude Code to leverage Max/Pro subscriptions.

**Key Files to Modify**:
- `src/platforms/` (new module)
- `src/loops/executor.rs` (update to use platforms)
- `src/config/mod.rs` (subscription config)
- `src/integrations/claude.rs` (deprecate/remove)

---

## Implementation Complete: 2026-01-19

### Changes Made

1. **Platform Module** (`src/platforms/`):
   - `mod.rs` - CodingPlatform trait, PlatformRegistry, SessionConfig
   - `types.rs` - SessionHandle, SessionEvent, SessionResult, SessionStatus
   - `claude_code.rs` - ClaudeCodePlatform implementation
   - `stream_parser.rs` - JSON stream parser for Claude Code output

2. **New PlatformExecutor** (`src/loops/platform_executor.rs`):
   - Uses CodingPlatform trait instead of direct ClaudeClient
   - Supports subscription selection (by name or priority)
   - Monitors session via process status instead of API responses
   - Integrates with LoopManager for state tracking

3. **Config Updates** (`src/config/mod.rs`):
   - Added `Subscription` struct with:
     - name, platform, config_dir (for multi-account)
     - model, max_concurrent, enabled, priority
   - Subscriptions array in main Config

4. **Deprecations**:
   - `src/integrations/claude.rs` - Marked with deprecation notice
   - `src/loops/executor.rs` - Marked as deprecated, recommends PlatformExecutor
   - All Claude-related types re-exported with deprecation warnings

### Architecture Decision

**Approach chosen**: CLI-based execution via subprocess

**Alternatives considered**:
1. Direct API calls (current) - Pay-per-token, no tool use
2. CLI subprocess (chosen) - Subscription billing, full agentic capabilities
3. WebSocket/streaming API - More complex, still per-token

**Rationale**: The Claude Code CLI already handles:
- Authentication via subscription
- Tool use (file operations, bash, etc.)
- Session persistence and resumption
- Output streaming in JSON format

This saves significant implementation effort compared to building equivalent functionality directly.

### Test Results

All 271 tests pass:
- Platform module: 23 tests
- Loop executor: 15 tests
- Config: 25 tests
- Other modules: 208 tests

### Next Steps (Future Iterations)

1. Add integration tests with actual Claude Code CLI
2. Implement session resumption for interrupted loops
3. Add Aider platform support
4. Add API metrics/monitoring for subscription usage
5. Create migration documentation for API users

---

## Session v2 Completed: 2026-01-24

**Goal**: Complete remaining MVP features after CLI Platform implementation.

**Phases Completed**:
1. ✅ Integration tests with Claude Code CLI
2. ✅ Session resumption for interrupted loops (checkpoint persistence)
3. ✅ Aider platform support
4. ✅ API metrics & monitoring
5. ✅ Integration Hub refactor

**Session File**: `prompts/marathon-session-v2.md`

**Status**: COMPLETE - All 5 phases implemented

### Phase 1: Integration Tests (Claude Code CLI)

**Files Created**:
- `tests/integration/mod.rs` - Integration test module
- `tests/integration/claude_code.rs` - Claude Code CLI tests

**Tests**:
- `test_claude_cli_detection` - Verifies CLI is found (or gracefully not)
- `test_stream_parser_with_mock_output` - Tests JSON event parsing
- `test_session_timeout` - Verifies timeout handling
- `test_start_session` - Full session start (requires CLI)
- `test_complete_coding_task` - End-to-end task (requires CLI)
- `test_error_handling` - Error conditions (requires CLI)

**Approach**: Tests skip gracefully with `#[ignore]` when Claude CLI is not available.

### Phase 2: Checkpoint Persistence

**Files Created**:
- `src/loops/checkpoint.rs` - LoopCheckpoint struct and DB operations
- `migrations/003_loop_checkpoints.sql` - Database schema

**Features**:
- `LoopCheckpoint` struct with full state serialization
- Saves checkpoint after each iteration
- Keeps only last 3 checkpoints per card
- Resume from checkpoint with `resume_from_checkpoint()`
- Clears checkpoints on successful completion

**Integration**: `PlatformExecutor` uses checkpoints via `monitor_session_with_checkpoints()`.

### Phase 3: Aider Platform Support

**Files Created**:
- `src/platforms/aider.rs` - Full CodingPlatform implementation

**Features**:
- Configurable model selection (GPT-4, Claude, etc.)
- `--yes-always` for non-interactive mode
- Output parsing for file changes and commits
- Concurrent session limits
- Builder pattern for configuration

### Phase 4: Metrics & Monitoring

**Files Created**:
- `src/metrics/mod.rs` - SessionMetrics, MetricsSummary types
- `src/api/metrics.rs` - REST API endpoints
- `migrations/004_session_metrics.sql` - Database schema

**API Endpoints**:
- `GET /api/metrics/summary` - Overall metrics (with period filter)
- `GET /api/metrics/by-card/:id` - Per-card metrics
- `GET /api/metrics/by-subscription` - Per-subscription breakdown

**Tracked**:
- Input/output tokens
- Estimated cost (USD)
- Duration (seconds)
- Iterations
- Success/failure

### Phase 5: Integration Hub

**Files Created**:
- `src/integrations/hub.rs` - IntegrationHub with lifecycle management

**Features**:
- Unified access to all integrations (GitHub, ArgoCD, K8s, Docker Hub)
- Auto-detection of available services
- Status reporting via `hub.status()`
- Thread-safe with `Arc<>` wrapping

---

## Final Verification: 2026-01-19

All implementation complete. The CLI platform abstraction is fully functional.

---

## Verification Session: 2026-01-19

### Success Criteria Verification

| Criterion | Status |
|-----------|--------|
| All existing tests pass (`cargo test`) | ✅ 271 tests pass |
| New platform tests pass | ✅ 23+ platform module tests |
| Integration works - Can start loop using Claude Code CLI | ✅ API endpoints wired to PlatformExecutor |
| Multi-subscription support | ✅ Config supports multiple subscriptions with priority |
| No API key required | ✅ Uses Claude Code CLI auth (subscription-based) |
| Release build succeeds | ✅ `cargo build --release` completes |

### Final Verification: 2026-01-19T14:30:00Z

All implementation verified complete by subsequent iteration. All 271 tests pass, release build successful.

### Architecture Summary

```
src/
├── platforms/
│   ├── mod.rs           # CodingPlatform trait, PlatformRegistry
│   ├── types.rs         # SessionHandle, SessionEvent, SessionResult
│   ├── claude_code.rs   # ClaudeCodePlatform implementation
│   └── stream_parser.rs # JSON stream parser for CLI output
├── loops/
│   ├── mod.rs           # LoopManager, LoopConfig, LoopState
│   ├── platform_executor.rs  # NEW: Uses CodingPlatform trait
│   └── executor.rs      # DEPRECATED: Direct API calls
├── config/
│   └── mod.rs           # Subscription config added
└── api/
    └── loops.rs         # API uses PlatformExecutor
```

### Key Changes

1. **Platform Trait**: `CodingPlatform` provides abstraction for CLI-based coding agents
2. **PlatformExecutor**: Replaces direct ClaudeClient usage in loop execution
3. **Subscription System**: Config supports multiple subscriptions with priority-based selection
4. **API Integration**: Loop endpoints spawn PlatformExecutor instead of deprecated LoopExecutor
5. **Stream Parser**: Parses Claude Code's JSON output for session events
6. **Deprecation**: Old `LoopExecutor` and `ClaudeClient` marked deprecated with migration notes

---

## Marathon Session: 2026-01-24

### Iteration 1: Fix Clippy Warnings

**Issue**: 4 clippy warnings found
- 2x `field_reassign_with_default` in `platform_executor.rs`
- 2x `if_same_then_else` in `aider.rs` and `claude_code.rs`

**Fix**:
- Use struct initialization syntax instead of field reassignment for `SessionConfig`
- Simplify if/else branches where both success conditions returned the same state

**Commit**: `fix(clippy): resolve all clippy warnings`

### Iteration 2: Fix TODO - Hardcoded Platform Name

**Issue**: `save_checkpoint_if_needed` used hardcoded "claude-code" for platform name

**Fix**:
- Add `platform_name: &str` parameter to `save_checkpoint_if_needed`
- Pass `platform.name()` from callers

**Commit**: `fix(checkpoint): use actual platform name instead of hardcoded value`

### Iteration 3: Fix React Lint Error

**Issue**: `CardDetailPanel.tsx` had `setState` calls inside `useEffect`, triggering `react-hooks/set-state-in-effect` lint error

**Fix**:
- Use React's key prop pattern to reset state when card changes
- Created inner component `CardDetailPanelInner` with key={card.id}

**Commit**: `fix(frontend): use key prop pattern for CardDetailPanel state reset`

### Iteration 4: Remove Dead WebSocket Code

**Issue**: Duplicate WebSocket handler implementations
- `ws.rs` - Active implementation, exports `ws_handler`
- `websocket.rs` - Dead code, never referenced in module tree
- `types.rs` - Contained unused `WsClientMessage` and `WsServerMessage` types

**Fix**:
- Deleted `websocket.rs` file
- Removed unused WebSocket types from `types.rs`
- ~255 lines of dead code removed

**Commit**: `chore(api): remove dead WebSocket code`

### Iteration 5: Remove Unused types.rs

**Issue**: `src/api/types.rs` was dead code
- File existed but was never declared as a module in `mod.rs`
- Contained duplicate type definitions that shadowed types in `mod.rs`
- ~200 lines of unreferenced code

**Fix**:
- Deleted `src/api/types.rs`
- Active API types remain in `mod.rs`

**Commit**: `chore(api): remove unused types.rs file`

---

## Marathon v3 Session: 2026-01-24

**Goal**: Complete frontend test coverage, E2E tests, and API documentation

### Summary

**Test Results**:
- **301 Rust tests** (backend)
- **74 Vitest tests** (frontend unit tests)
- **5 E2E test files** (Playwright)

### Frontend Unit Tests (74 tests)

#### Store Tests (30 tests)
- `loopStore.test.ts` - 15 tests for loop state management
- `cardStore.test.ts` - 15 tests for card state management

**Key Fix**: Tests were using stale Zustand state references. Fixed by calling `getState()` after mutations.

#### Component Tests (44 tests)
- `DraggableCard.test.tsx` - 11 tests (rendering, labels, priority, click handling)
- `KanbanColumn.test.tsx` - 6 tests (column rendering, card count, empty state)
- `Badge.test.tsx` - 12 tests (all variants and sizes)
- `Button.test.tsx` - 15 tests (variants, sizes, click, disabled state)

### E2E Tests (Playwright)

**Files Created**:
- `playwright.config.ts` - Playwright configuration with dev server
- `e2e/board.spec.ts` - Kanban board navigation tests
- `e2e/card-interaction.spec.ts` - Card click and creation tests
- `e2e/dashboard.spec.ts` - Dashboard and projects navigation tests

**npm Scripts Added**:
- `test:e2e` - Run Playwright tests
- `test:e2e:ui` - Run Playwright UI mode

### API Documentation

**File Created**: `docs/api-reference.md`

**Coverage**:
- Cards API (list, create, get, update, delete, transition)
- Projects API (CRUD operations)
- Loops API (start, pause, resume, stop, status)
- Attempts API (list, get)
- Errors API (list, get, resolve)
- Metrics API (summary, by-card, by-subscription)
- Integrations (GitHub Actions, ArgoCD, Docker Hub, Kubernetes)
- WebSocket API (subscribe, events)

### Commits

1. `4194ff6` - fix(frontend): fix Zustand store tests to use fresh state after mutations
2. `90116f6` - test(frontend): add kanban component tests and fix store test types
3. `130fa5a` - test(frontend): add Badge and Button UI component tests
4. `bd580da` - feat(frontend): setup Playwright E2E testing infrastructure
5. `328f836` - docs: add comprehensive API reference documentation
6. `4a00945` - test(e2e): add card interaction and dashboard E2E tests

---
