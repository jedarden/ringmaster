# ADR-003: Multi-Platform Coding Agent Support

## Status

Accepted

## Context

Different coding tasks may benefit from different AI coding platforms:
- Claude Code: native Claude integration, tool use
- Aider: git-focused, multiple model support
- Codex/Copilot: fast completions
- Custom CLIs: specialized tooling

Locking to a single platform limits flexibility.

## Decision

Support multiple coding platforms as execution backends:
- Abstract platform interface for starting/stopping loops
- Platform-specific adapters handle CLI invocation
- Config sync (CLAUDE.md, skills) applied per-platform where supported
- Model selection passed to platform

## Consequences

**Easier:**
- Use best tool for each task
- Switch platforms without changing cards
- Test same task across platforms

**Harder:**
- Must maintain multiple adapters
- Feature parity varies across platforms
- Config sync differs per platform
