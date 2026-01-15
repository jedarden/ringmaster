# UX Controls

## Core Loop

```
Create Card → Add Context → Run Loop → Done
                 ↑              │
                 └── Intervene ←┘
```

## Primary Controls

### 1. Loop Control

```
┌────────────────────────────────────────────┐
│  [▶ Run]   [⏸ Pause]   [⏹ Stop]           │
│                                            │
│  Iteration: 7/100    Cost: $4.23/$50       │
└────────────────────────────────────────────┘
```

| Action | What it does |
|--------|--------------|
| **Run** | Start or resume loop |
| **Pause** | Stop after current iteration, keep state |
| **Stop** | Halt immediately, can restart from checkpoint |

### 2. Platform & Model

```
┌────────────────────────────────────────────┐
│  Platform: [Claude Code ▼]                 │
│  Model:    [Sonnet ▼]                      │
│  Config:   [claude-config ▼]  [Sync ⟳]     │
└────────────────────────────────────────────┘
```

| Setting | Options |
|---------|---------|
| **Platform** | Claude Code, Aider, Codex, Custom CLI |
| **Model** | Opus, Sonnet, Haiku, GPT-4, etc. |
| **Config** | Config repo to sync (CLAUDE.md, skills, patterns) |

Platform = the coding agent/CLI that executes.
Model = the LLM that powers it.
Config = repo containing CLAUDE.md, skills/, patterns.json synced to session.

### Config Sync

When a loop starts, Ringmaster syncs from the config repo:

```
claude-config/
├── CLAUDE.md        → Copied to worktree as CLAUDE.md
├── skills/          → Copied to .claude/skills/
└── patterns.json    → Applied to session
```

This ensures all coding sessions use consistent instructions, skills, and patterns.

### 3. Limits

```
┌────────────────────────────────────────────┐
│  Max Iterations: [100]                     │
│  Max Cost:       [$50]                     │
│  Max Runtime:    [4h]                      │
└────────────────────────────────────────────┘
```

Loop stops when any limit hit.

### 4. Context

```
┌────────────────────────────────────────────┐
│  Notes:        [+ Add]     ← Free text     │
│  Files:        [+ Add]     ← Source files  │
│  Chat History: [Summarize] ← RLM if long   │
└────────────────────────────────────────────┘
```

| Context Type | Purpose |
|--------------|---------|
| **Notes** | Guide the LLM ("use existing AuthService pattern") |
| **Files** | Include specific source files |
| **History** | Previous conversation (auto-summarized if too long) |

### 5. Intervention

When loop is paused or needs approval:

```
┌────────────────────────────────────────────┐
│  LLM wants to modify auth.rs               │
│                                            │
│  [Approve]  [Edit]  [Skip]  [Hint]         │
└────────────────────────────────────────────┘
```

| Action | When to use |
|--------|-------------|
| **Approve** | Output looks good |
| **Edit** | Fix small issue before applying |
| **Skip** | Bad output, try again |
| **Hint** | Add guidance for next iteration |

## User Paths

### Happy Path
```
Create Card → Add Notes → Run → Approve iterations → Complete
```

### Stuck Path
```
Loop hits error → Pause → Add hint/context → Resume → Continue
```

### Abandon Path
```
Loop not working → Stop → Restart from earlier checkpoint
                       → Or manually complete/fail card
```

## Card States (Kanban Columns)

```
Draft → Planning → Coding → Building → Deploying → Done
                     ↓          ↓          ↓
                  Error ←── Error ←──── Error
                     │
                     └→ (fix and retry)
```

## Minimal Board View

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ DRAFT       │ CODING      │ BUILDING    │ DONE        │
├─────────────┼─────────────┼─────────────┼─────────────┤
│ ┌─────────┐ │ ┌─────────┐ │ ┌─────────┐ │             │
│ │ Task A  │ │ │●Task B  │ │ │ Task C  │ │             │
│ │ [Start] │ │ │ 7/100   │ │ │ 60%     │ │             │
│ └─────────┘ │ │ $4.23   │ │ └─────────┘ │             │
│             │ └─────────┘ │             │             │
│             │ ┌─────────┐ │             │             │
│             │ │⚠Task D  │ │             │             │
│             │ │ error   │ │             │             │
│             │ └─────────┘ │             │             │
└─────────────┴─────────────┴─────────────┴─────────────┘

● = running    ⚠ = needs attention
```

## Summary

| Lever | Options |
|-------|---------|
| **Execution** | Run / Pause / Stop |
| **Platform** | Claude Code, Aider, Codex, Custom |
| **Model** | Opus, Sonnet, Haiku, GPT-4, etc. |
| **Config** | Repo with CLAUDE.md, skills/, patterns.json |
| **Limits** | Iterations, Cost, Time |
| **Context** | Notes, Files, History |
| **Intervention** | Approve, Edit, Skip, Hint |
| **State** | Force transition if needed |
