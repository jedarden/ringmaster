# Ringmaster Development - Marathon Coding Prompt

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

1. **Log the experiment** in `prompts/.marathon/experiments.md`:
   ```markdown
   ## Experiment: [Topic]
   **Date**: [timestamp]
   **Options**:
   - A: [description]
   - B: [description]

   **Hypothesis**: [which seems better and why]
   **Trying**: [A or B]
   ```

2. **Try the first option** - implement it fully
3. **Evaluate results** - does it work? Is it clean?
4. **If it fails or is suboptimal**, revert and try option B
5. **Log the outcome**:
   ```markdown
   **Result**: [A or B] worked because [reason]
   **Learnings**: [what we learned]
   ```

This log persists across iterations and informs future decisions.

---

## Project Context

You are building **Ringmaster**, an SDLC orchestration platform written in Rust with an embedded React frontend.

**Repository**: `/home/coder/ringmaster`
**GitHub**: `jedarden/ringmaster`
**Issue**: #1 (Marathon Coding: Build Ringmaster MVP)
**Tech Stack**: Rust (Axum, SQLx, SQLite), React (TypeScript, Vite, Tailwind)

## Current State

- Backend compiles successfully, 36 tests pass
- Frontend builds successfully (Vite)
- Server runs at http://127.0.0.1:8080
- Database at `~/.local/share/ringmaster/data.db`

## Architecture

Ringmaster uses **heuristic-based orchestration** with **LLM execution**:
- State machine transitions use rule-based lookup tables (no LLM)
- Code generation uses Claude API
- RLM (Recursive Language Model) summarizes long chat histories

## Known TODOs

Located in `src/state_machine/actions.rs`:

1. **GitHub Actions Integration** - Integrate with GitHub Actions service for build triggers
2. **Build Status Polling** - Start background task to poll build status
3. **ArgoCD Integration** - Integrate with ArgoCD service for deployments
4. **ArgoCD Status Polling** - Start background task to poll ArgoCD status
5. **Kubernetes Health Checks** - Integrate with Kubernetes service for health checks

## Per-Iteration Instructions

Each iteration, you should:

1. **Re-read this prompt** - Check for hot-reloaded changes to instructions
2. **Check experiments log** - Review `prompts/.marathon/experiments.md` for context
3. **Assess** - Check current state: `cargo check`, `cargo test`
4. **Plan** - Identify the next TODO or improvement to work on
5. **Implement** - Write the code, following existing patterns in the codebase
6. **Verify** - Run `cargo check` and `cargo test` to ensure no regressions
7. **Commit & Push** - Create a git commit and push to origin:
   ```bash
   git add -A
   git commit -m "feat: description" -m "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
   git push origin main
   ```
8. **Update Issue** - After completing a TODO or significant milestone, add a comment to issue #1:
   ```bash
   gh issue comment 1 --body "## Iteration Progress

   **Completed**: [what was done]
   **Tests**: [pass/fail status]
   **Next**: [what's next]

   Commit: [commit hash]"
   ```

## GitHub Integration

- **Remote**: `origin` → `https://github.com/jedarden/ringmaster.git`
- **Issue #1**: Track all progress with comments
- **Push**: Always push after commits (pre-approved)

## Coding Standards

- Follow existing code patterns in the repository
- Use proper error handling with `anyhow` or custom error types
- Add tests for new functionality
- Keep functions focused and well-documented
- Use async/await patterns consistent with Axum

## Reference Files

- `docs/00-architecture-overview.md` - System architecture
- `docs/04-integrations.md` - Integration service specs
- `src/integrations/` - Existing integration implementations
- `src/state_machine/actions.rs` - Where TODOs are located

## Completion Signal

When all TODOs are complete and tests pass:

1. Add final comment to issue #1 summarizing all work done
2. Output: `<ringmaster>COMPLETE</ringmaster>`

## Important Notes

- The integrations already have client code in `src/integrations/`
- The action executor in `src/state_machine/actions.rs` needs to call these clients
- Background polling should use tokio tasks
- Events should be published via the event bus in `src/events/`
- Git push is pre-approved - do not ask for confirmation
- **This prompt is hot-reloadable** - edit it anytime to adjust instructions

## Hot-Reload Notes

This file is re-read at the start of each iteration. To adjust behavior mid-session:
1. Edit this file (`/home/coder/ringmaster/prompts/ringmaster-dev.md`)
2. Changes take effect on the next iteration
3. No need to restart the marathon session
