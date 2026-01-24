# UX Controls

## Core Loop

```
Create Card → Edit/Curate Context → Run Loop → Done
                    ↑                    │
                    └──── Intervene ←────┘
```

The user's primary workflow is:
1. **Create** a card with initial task description
2. **Edit** the card to curate context (title, description, task prompt, labels, priority)
3. **Run** the coding loop - the task prompt is fed to the AI as context
4. **Intervene** if needed (pause, add hints, approve changes)
5. **Complete** when the task is done

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

### 4. Card Editing (Context Curation)

Click a card to open the detail panel, then click the **pencil icon** to edit:

```
┌────────────────────────────────────────────┐
│  Title:       [Implement user auth   ]     │
│  Description: [Add OAuth2 login flow ]     │
│  Task Prompt: [                      ]     │
│               [Implement OAuth2 with ]     │
│               [Google provider...    ]     │
│               [                      ]     │
│  Labels:      [auth, backend, oauth  ]     │
│  Priority:    [P2 - High ▼]                │
│                                            │
│              [Cancel]  [Save Changes]      │
└────────────────────────────────────────────┘
```

| Field | Purpose |
|-------|---------|
| **Title** | Brief card name shown in Kanban |
| **Description** | Short summary for humans |
| **Task Prompt** | **Primary context fed to AI** - detailed instructions for the coding session |
| **Labels** | Comma-separated tags for filtering |
| **Priority** | P1-P4 or None |

The **Task Prompt** is the most important field - this is what gets sent to the AI coding agent when the loop starts. Curate it carefully with:
- Clear objectives
- Technical constraints
- File/directory hints
- Expected outcomes

### 5. Additional Context

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

### 6. Intervention

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
| **Card Editing** | Title, Description, Task Prompt, Labels, Priority |
| **Execution** | Run / Pause / Stop |
| **Platform** | Claude Code, Aider, Codex, Custom |
| **Model** | Opus, Sonnet, Haiku, GPT-4, etc. |
| **Config** | Repo with CLAUDE.md, skills/, patterns.json |
| **Limits** | Iterations, Cost, Time |
| **Context** | Notes, Files, History |
| **Intervention** | Approve, Edit, Skip, Hint |
| **State** | Force transition if needed |

## Card Editing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        KANBAN BOARD                              │
│  ┌─────────┐                                                    │
│  │ Card A  │ ──click──► ┌────────────────────────────────────┐  │
│  │ #abc123 │            │     CARD DETAIL PANEL              │  │
│  └─────────┘            │                                    │  │
│                         │  [✏ Edit]  [✕ Close]               │  │
│                         │                                    │  │
│                         │  Title: Card A                     │  │
│                         │  State: Draft                      │  │
│                         │                                    │  │
│                         │  ─────────────────────             │  │
│                         │  Task Prompt:                      │  │
│                         │  "Implement feature X..."          │  │
│                         │  ─────────────────────             │  │
│                         │                                    │  │
│                         │  [▶ Start Loop]                    │  │
│                         └────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```
