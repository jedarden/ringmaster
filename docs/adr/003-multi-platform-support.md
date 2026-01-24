# ADR-003: Multi-Platform Coding Agent Support via CLI Execution

## Status

Accepted (Revised)

## Context

Different coding tasks may benefit from different AI coding platforms:
- **Claude Code**: Native Claude integration with tool use, file editing, bash execution
- **Aider**: Git-focused, multiple model support
- **Codex/Copilot**: Fast completions
- **Custom CLIs**: Specialized tooling

**Critical Constraint**: Users have Claude Max/Pro subscriptions (flat-rate unlimited usage). Direct API calls would incur pay-per-token costs, making marathon coding sessions prohibitively expensive.

The original implementation used direct Anthropic API calls via `reqwest`. This was **incorrect** because:
1. API usage is billed per-token ($3-15/M input, $15-75/M output)
2. Marathon sessions can consume millions of tokens
3. Users already pay for unlimited usage via Max/Pro subscriptions
4. Claude Code CLI provides native tool use (file editing, bash, etc.) that raw API doesn't

## Decision

**Execute coding agents via CLI subprocess, NOT direct API calls.**

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLI-BASED EXECUTION                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   LoopExecutor                                                   │
│        │                                                         │
│        └── CodingPlatform trait                                  │
│              │                                                   │
│              ├── ClaudeCodePlatform (PRIMARY)                    │
│              │     ├── Spawns: claude --dangerously-skip-perms   │
│              │     ├── Streams: --output-format stream-json      │
│              │     ├── Auth: ~/.claude/ (Max/Pro subscription)   │
│              │     └── Tools: Native file edit, bash, etc.       │
│              │                                                   │
│              ├── AiderPlatform                                   │
│              │     ├── Spawns: aider --yes-always                │
│              │     └── Auth: Per-platform API keys               │
│              │                                                   │
│              └── CustomCliPlatform                               │
│                    └── Configurable command template             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Subscription Management

Support multiple Claude Max/Pro accounts for teams:

```toml
# config.toml
[[subscriptions]]
name = "team-alpha"
platform = "claude-code"
config_dir = "~/.claude-team-alpha"  # Separate auth
model = "opus"
max_concurrent = 3

[[subscriptions]]
name = "team-beta"
platform = "claude-code"
config_dir = "~/.claude-team-beta"
model = "sonnet"
max_concurrent = 5

[[subscriptions]]
name = "personal"
platform = "claude-code"
config_dir = "~/.claude"  # Default
model = "sonnet"
max_concurrent = 2
```

### Per-Project/Card Assignment

```toml
# Project-level default
[project]
subscription = "team-alpha"

# Or per-card override via UI/API
card.subscription = "team-beta"
```

### Platform Trait

```rust
#[async_trait]
pub trait CodingPlatform: Send + Sync {
    /// Start a coding session in the given worktree
    async fn start_session(
        &self,
        worktree: &Path,
        prompt: &str,
        config: &SessionConfig,
    ) -> Result<SessionHandle, PlatformError>;

    /// Stream events from the running session
    fn event_stream(&self, handle: &SessionHandle) -> impl Stream<Item = SessionEvent>;

    /// Send additional input to a running session
    async fn send_input(&self, handle: &SessionHandle, input: &str) -> Result<(), PlatformError>;

    /// Stop a running session
    async fn stop_session(&self, handle: &SessionHandle) -> Result<SessionResult, PlatformError>;

    /// Get platform capabilities
    fn capabilities(&self) -> PlatformCapabilities;
}
```

### Claude Code Implementation

```rust
pub struct ClaudeCodePlatform {
    config_dir: PathBuf,      // Auth location (~/.claude or custom)
    model: String,            // sonnet, opus, haiku
    max_turns: u32,           // --max-turns flag
}

impl CodingPlatform for ClaudeCodePlatform {
    async fn start_session(
        &self,
        worktree: &Path,
        prompt: &str,
        config: &SessionConfig,
    ) -> Result<SessionHandle, PlatformError> {
        let mut cmd = Command::new("claude");
        cmd.current_dir(worktree)
           .env("CLAUDE_CONFIG_DIR", &self.config_dir)
           .arg("--dangerously-skip-permissions")
           .arg("--output-format").arg("stream-json")
           .arg("--model").arg(&self.model)
           .arg("--max-turns").arg(self.max_turns.to_string())
           .arg("-p").arg(prompt)
           .stdout(Stdio::piped())
           .stderr(Stdio::piped());

        let child = cmd.spawn()?;
        // ... handle streaming JSON output
    }
}
```

### JSON Stream Parsing

Claude Code outputs events as newline-delimited JSON:

```json
{"type": "assistant", "message": {...}, "session_id": "..."}
{"type": "tool_use", "tool": "Write", "input": {...}}
{"type": "tool_result", "output": "..."}
{"type": "result", "duration_ms": 12345, "cost_usd": 0.00}
```

The executor parses these to:
- Track iteration progress
- Detect completion signals
- Extract cost/token metrics (even though subscription-based)
- Monitor for errors

## Consequences

### Benefits

1. **Cost-effective**: Uses existing Max/Pro subscriptions (flat-rate)
2. **Native tool use**: Claude Code handles file editing, bash, git natively
3. **Multi-account**: Distribute load across team subscriptions
4. **Platform flexibility**: Same interface for Aider, custom CLIs
5. **Battle-tested**: Claude Code CLI is production-ready

### Trade-offs

1. **Process overhead**: Spawning CLI processes vs direct HTTP
2. **Streaming complexity**: Must parse JSON event stream
3. **Error handling**: CLI exit codes + stderr parsing
4. **Platform parity**: Not all platforms support same features

### Migration

Remove:
- `ClaudeClient` (direct API calls)
- `ANTHROPIC_API_KEY` dependency for loops

Add:
- `CodingPlatform` trait and implementations
- Subscription configuration
- JSON stream parser
- Process lifecycle management

## Auto-Installation

Ringmaster automatically installs Claude Code CLI on first run if not found:

```rust
// src/platforms/installer.rs
pub async fn ensure_claude_available() -> Result<PathBuf, String> {
    if let Some(path) = find_claude_binary().await {
        return Ok(path);
    }
    // Run: curl -fsSL https://claude.ai/install.sh | bash
    install_claude_code().await
}
```

The installer:
1. Checks common locations (`~/.claude/local/claude`, PATH, homebrew)
2. If not found, runs the official native installer
3. Returns the binary path for `ClaudeCodePlatform` to use

### Manual Installation

```bash
# Native installer (recommended)
curl -fsSL https://claude.ai/install.sh | bash

# Verify installation
claude --version
```

### Doctor Command

Check or install dependencies:

```bash
ringmaster doctor             # Check if Claude Code CLI is installed
ringmaster doctor --install   # Install if missing
```

## References

- Claude Code CLI: `claude --help`
- Claude Code Setup: https://code.claude.com/docs/en/setup
- Aider: https://aider.chat
- Marathon coding skill: `~/.claude/skills/marathon-coding/`
