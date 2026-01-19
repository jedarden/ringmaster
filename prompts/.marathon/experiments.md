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
