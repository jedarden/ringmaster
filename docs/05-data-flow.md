# Data Flow and Component Interactions

## Overview

This document describes how data flows through Ringmaster, showing the interactions between components during key operations. Understanding these flows is essential for debugging, extending functionality, and maintaining system coherence.

## High-Level Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            RINGMASTER DATA FLOW OVERVIEW                               │
└──────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              USER INTERACTIONS                                   │
    │                                                                                  │
    │   React UI ◄──────────────────────────────────────────────────────────────────┐ │
    │      │                                                                        │ │
    │      │ HTTP Requests                                           WebSocket      │ │
    │      │ (REST API)                                             (Real-time)     │ │
    │      ▼                                                                        │ │
    └──────┼────────────────────────────────────────────────────────────────────────┼─┘
           │                                                                        │
           ▼                                                                        │
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              WEB SERVER (Axum)                                   │
    │                                                                                  │
    │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐ │
    │   │   REST Routes   │    │  WebSocket Hub  │    │   Static File Server        │ │
    │   │                 │    │                 │    │   (rust-embed)              │ │
    │   │ /api/cards/*    │    │ /api/ws         │    │                             │ │
    │   │ /api/loops/*    │    │                 │    │ /index.html                 │ │
    │   │ /api/projects/* │    │ Subscriptions:  │    │ /assets/*                   │ │
    │   │ /api/integr/*   │    │ • Card events   │────┼▶ Serves React bundle        │ │
    │   └────────┬────────┘    │ • Loop events   │    └─────────────────────────────┘ │
    │            │             │ • System events │                                     │
    │            │             └────────┬────────┘                                     │
    │            │                      │                                              │
    └────────────┼──────────────────────┼──────────────────────────────────────────────┘
                 │                      │
                 ▼                      ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              CORE SERVICES                                       │
    │                                                                                  │
    │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐ │
    │   │  Card Service   │    │  Loop Manager   │    │    Event Bus                │ │
    │   │                 │    │                 │    │                             │ │
    │   │ • CRUD ops      │◄───┤ • Start/Stop    │───▶│ • Publish events            │ │
    │   │ • State trans   │    │ • Pause/Resume  │    │ • Route to subscribers      │ │
    │   │ • Validation    │    │ • Monitor loops │    │ • Persist audit log         │ │
    │   └────────┬────────┘    └────────┬────────┘    └──────────────┬──────────────┘ │
    │            │                      │                            │                │
    │            ▼                      ▼                            │                │
    │   ┌─────────────────┐    ┌─────────────────┐                   │                │
    │   │ State Machine   │    │ Prompt Pipeline │                   │                │
    │   │                 │    │                 │                   │                │
    │   │ • Transitions   │    │ • 5 Layers      │                   │                │
    │   │ • Guards        │    │ • Token mgmt    │                   │                │
    │   │ • Actions       │    │ • Caching       │                   │                │
    │   └────────┬────────┘    └────────┬────────┘                   │                │
    │            │                      │                            │                │
    └────────────┼──────────────────────┼────────────────────────────┼────────────────┘
                 │                      │                            │
                 ▼                      ▼                            ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                              DATA LAYER                                          │
    │                                                                                  │
    │   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────┐ │
    │   │  SQLite DB      │    │  Git Worktrees  │    │   File System               │ │
    │   │                 │    │                 │    │                             │ │
    │   │ • Cards         │    │ • Per-card      │    │ • Config files              │ │
    │   │ • Attempts      │    │   isolation     │    │ • Log files                 │ │
    │   │ • Errors        │    │ • Branch mgmt   │    │ • Cache                     │ │
    │   │ • Projects      │    │ • Commit hist   │    │                             │ │
    │   └─────────────────┘    └─────────────────┘    └─────────────────────────────┘ │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
                 │                      │
                 ▼                      ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                            EXTERNAL SYSTEMS                                      │
    │                                                                                  │
    │   ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐ │
    │   │  Claude   │  │  GitHub   │  │  ArgoCD   │  │   K8s     │  │  Docker Hub   │ │
    │   │   API     │  │   API     │  │   API     │  │   API     │  │     API       │ │
    │   └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────────┘ │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

## Detailed Flow: Card Creation to Completion

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE CARD LIFECYCLE DATA FLOW                                  │
└──────────────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════════════
PHASE 1: CARD CREATION
═══════════════════════════════════════════════════════════════════════════════════════

    User fills form in React UI
         │
         │ POST /api/cards
         │ {
         │   "projectId": "uuid",
         │   "title": "Add user auth",
         │   "description": "...",
         │   "taskPrompt": "Implement JWT...",
         │   "acceptanceCriteria": [...]
         │ }
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ Axum Router                                                                      │
    │   │                                                                              │
    │   ▼                                                                              │
    │ cards::create_card()                                                             │
    │   │                                                                              │
    │   ├── Validate request body                                                      │
    │   ├── Check project exists                                                       │
    │   │                                                                              │
    │   ▼                                                                              │
    │ CardService::create()                                                            │
    │   │                                                                              │
    │   ├── Generate UUID                                                              │
    │   ├── Set initial state: DRAFT                                                   │
    │   ├── Create acceptance_criteria records                                         │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Database::insert()                                                               │
    │   │                                                                              │
    │   ├── INSERT INTO cards (...)                                                    │
    │   ├── INSERT INTO acceptance_criteria (...)                                      │
    │   │                                                                              │
    │   ▼                                                                              │
    │ EventBus::publish(CardCreated { card })                                          │
    │   │                                                                              │
    │   ▼                                                                              │
    │ WebSocketHub::broadcast_to_project(project_id, event)                            │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
         │
         │ Response: 201 Created
         │ { "id": "card-uuid", "state": "draft", ... }
         │
         ▼
    React UI updates Kanban board (via WebSocket)


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 2: START PLANNING (User clicks "Start Planning")
═══════════════════════════════════════════════════════════════════════════════════════

    User clicks button
         │
         │ POST /api/cards/{id}/transition
         │ { "trigger": "StartPlanning" }
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ CardStateMachine::transition(card, StartPlanning)                                │
    │   │                                                                              │
    │   ├── Validate: current_state == DRAFT                                           │
    │   ├── Check guards: (none for this transition)                                   │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Execute transition                                                               │
    │   │                                                                              │
    │   ├── card.previous_state = DRAFT                                                │
    │   ├── card.state = PLANNING                                                      │
    │   ├── card.state_changed_at = now()                                              │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Database::update_card_state()                                                    │
    │   │                                                                              │
    │   ▼                                                                              │
    │ EventBus::publish(StateChanged { from: DRAFT, to: PLANNING })                    │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 3: APPROVE PLAN → START CODING (with Ralph Loop)
═══════════════════════════════════════════════════════════════════════════════════════

    User approves plan
         │
         │ POST /api/cards/{id}/transition
         │ { "trigger": "ApprovePlan" }
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ CardStateMachine::transition(card, ApprovePlan)                                  │
    │   │                                                                              │
    │   ├── Validate: current_state == PLANNING                                        │
    │   ├── Check guard: HasAcceptanceCriteria ✓                                       │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Execute Actions:                                                                 │
    │   │                                                                              │
    │   ├─────────────────────────────────────────────────────────────────────────────┐│
    │   │ Action: CreateGitWorktree                                                   ││
    │   │   │                                                                         ││
    │   │   ▼                                                                         ││
    │   │ GitService::create_worktree(card_id, branch_name)                           ││
    │   │   │                                                                         ││
    │   │   ├── git branch feature/card-{id}                                          ││
    │   │   ├── git worktree add ~/.ringmaster/worktrees/card-{id}                     ││
    │   │   │                                                                         ││
    │   │   ▼                                                                         ││
    │   │ Returns: /home/coder/.ringmaster/worktrees/card-{id}                         ││
    │   │   │                                                                         ││
    │   │   ▼                                                                         ││
    │   │ Database::update_card({ worktree_path, branch_name })                       ││
    │   └─────────────────────────────────────────────────────────────────────────────┘│
    │   │                                                                              │
    │   ├─────────────────────────────────────────────────────────────────────────────┐│
    │   │ Action: StartRalphLoop                                                      ││
    │   │   │                                                                         ││
    │   │   ▼                                                                         ││
    │   │ LoopManager::start_loop(card_id, config)                                    ││
    │   │   │                                                                         ││
    │   │   ├── Create RalphLoop instance                                             ││
    │   │   ├── Store in active_loops map                                             ││
    │   │   ├── Spawn async task for loop execution                                   ││
    │   │   │                                                                         ││
    │   │   ▼                                                                         ││
    │   │ [ASYNC] RalphLoop::run()  ──────────────────────────────────────────────────┼┼──▶ See Phase 4
    │   └─────────────────────────────────────────────────────────────────────────────┘│
    │   │                                                                              │
    │   ▼                                                                              │
    │ card.state = CODING                                                              │
    │ EventBus::publish(StateChanged { to: CODING })                                   │
    │ EventBus::publish(LoopStarted { card_id })                                       │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 4: RALPH LOOP EXECUTION (Async, runs in background)
═══════════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ RalphLoop::run() - ITERATION CYCLE                                               │
    │                                                                                  │
    │   loop {                                                                         │
    │     │                                                                            │
    │     ├── Check stop conditions (max iterations, cost, time)                       │
    │     │                                                                            │
    │     ├── iteration += 1                                                           │
    │     │   EventBus::publish(IterationStarted { iteration })                        │
    │     │                                                                            │
    │     ▼                                                                            │
    │   ┌───────────────────────────────────────────────────────────────────────────┐ │
    │   │ PromptPipeline::process(card_id, task_prompt)                             │ │
    │   │   │                                                                       │ │
    │   │   ├── Load card from DB                                                   │ │
    │   │   ├── Load project from DB                                                │ │
    │   │   ├── Load attempts history                                               │ │
    │   │   ├── Load errors history                                                 │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Layer 1: CardContextLayer                                                 │ │
    │   │   ├── Add task description                                                │ │
    │   │   ├── Add acceptance criteria                                             │ │
    │   │   └── ~500 tokens                                                         │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Layer 2: ProjectContextLayer                                              │ │
    │   │   ├── Load architecture docs                                              │ │
    │   │   ├── Run Repomix for codebase summary                                    │ │
    │   │   └── ~3000 tokens                                                        │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Layer 3: SDLCStateLayer                                                   │ │
    │   │   ├── Add current iteration                                               │ │
    │   │   ├── Add previous attempts summary                                       │ │
    │   │   ├── Add error history                                                   │ │
    │   │   └── ~1500 tokens                                                        │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Layer 4: SupplementalLayer                                                │ │
    │   │   ├── Read affected source files                                          │ │
    │   │   ├── Include test files                                                  │ │
    │   │   └── ~5000 tokens (dynamic)                                              │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Layer 5: RefinementLayer                                                  │ │
    │   │   ├── Add stage-specific instructions                                     │ │
    │   │   ├── Add safety constraints                                              │ │
    │   │   ├── Add completion signal format                                        │ │
    │   │   └── ~800 tokens                                                         │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Returns: ProcessedPrompt { final_prompt, ~11000 tokens }                  │ │
    │   └───────────────────────────────────────────────────────────────────────────┘ │
    │     │                                                                            │
    │     ▼                                                                            │
    │   ┌───────────────────────────────────────────────────────────────────────────┐ │
    │   │ LLMService::complete(prompt)                                              │ │
    │   │   │                                                                       │ │
    │   │   ├── POST https://api.anthropic.com/v1/messages                          │ │
    │   │   │   {                                                                   │ │
    │   │   │     "model": "claude-opus-4-20250514",                                │ │
    │   │   │     "max_tokens": 16000,                                              │ │
    │   │   │     "messages": [{ "role": "user", "content": final_prompt }]         │ │
    │   │   │   }                                                                   │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ Returns: LLMResponse { content, tokens_used, cost }                       │ │
    │   └───────────────────────────────────────────────────────────────────────────┘ │
    │     │                                                                            │
    │     ├── Update metrics: total_cost += response.cost                              │
    │     │   EventBus::publish(CostIncurred { cost })                                 │
    │     │                                                                            │
    │     ▼                                                                            │
    │   ┌───────────────────────────────────────────────────────────────────────────┐ │
    │   │ Record Attempt in Database                                                │ │
    │   │   INSERT INTO attempts (card_id, iteration, output, cost, tokens, ...)    │ │
    │   └───────────────────────────────────────────────────────────────────────────┘ │
    │     │                                                                            │
    │     ▼                                                                            │
    │   ┌───────────────────────────────────────────────────────────────────────────┐ │
    │   │ Check for completion signal                                               │ │
    │   │   response.contains("<promise>CODE_COMPLETE</promise>") ?                 │ │
    │   │     │                                                                     │ │
    │   │     ├── YES: Break loop, transition to CODE_REVIEW                        │ │
    │   │     └── NO: Continue                                                      │ │
    │   └───────────────────────────────────────────────────────────────────────────┘ │
    │     │                                                                            │
    │     ▼ (if not complete)                                                          │
    │   ┌───────────────────────────────────────────────────────────────────────────┐ │
    │   │ Execute Response (apply code changes)                                     │ │
    │   │   │                                                                       │ │
    │   │   ├── Parse code blocks from response                                     │ │
    │   │   ├── For each file change:                                               │ │
    │   │   │     └── Write to worktree: ~/.ringmaster/worktrees/card-{id}/{path}    │ │
    │   │   │                                                                       │ │
    │   │   ├── git add .                                                           │ │
    │   │   │                                                                       │ │
    │   │   ▼                                                                       │ │
    │   │ If iteration % checkpoint_interval == 0:                                  │ │
    │   │   └── git commit -m "[ralph] Checkpoint iteration {n}"                    │ │
    │   │       Store LoopSnapshot in database                                      │ │
    │   └───────────────────────────────────────────────────────────────────────────┘ │
    │     │                                                                            │
    │     ├── EventBus::publish(IterationCompleted { iteration })                      │
    │     │                                                                            │
    │     ├── sleep(cooldown)                                                          │
    │     │                                                                            │
    │     └── Continue loop                                                            │
    │   }                                                                              │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 5: LOOP COMPLETES → CODE REVIEW
═══════════════════════════════════════════════════════════════════════════════════════

    Loop detects completion signal
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ RalphLoop completion detected                                                    │
    │   │                                                                              │
    │   ├── final git commit                                                           │
    │   ├── update loop state to COMPLETED                                             │
    │   │                                                                              │
    │   ▼                                                                              │
    │ EventBus::publish(LoopCompleted { result: CompletionSignal })                    │
    │   │                                                                              │
    │   ▼                                                                              │
    │ CardStateMachine::transition(card, LoopComplete)                                 │
    │   │                                                                              │
    │   ├── Check guard: HasGeneratedCode ✓                                            │
    │   │                                                                              │
    │   ├── Action: CreatePullRequest                                                  │
    │   │   │                                                                          │
    │   │   ├── git push origin feature/card-{id}                                      │
    │   │   ├── GitHub API: Create PR                                                  │
    │   │   └── Store PR URL in card                                                   │
    │   │                                                                              │
    │   ▼                                                                              │
    │ card.state = CODE_REVIEW                                                         │
    │ EventBus::publish(StateChanged { to: CODE_REVIEW })                              │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
    WebSocket broadcasts to React UI
    Kanban card moves to "Code Review" column


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 6: BUILD MONITORING (After review approved)
═══════════════════════════════════════════════════════════════════════════════════════

    Code review approved, tests passed
         │
         │ Card enters BUILD_QUEUE
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ IntegrationHub::monitor_card() [Background Task]                                 │
    │   │                                                                              │
    │   │ [Polling loop every 10 seconds]                                              │
    │   │                                                                              │
    │   ▼                                                                              │
    │ GitHubActionsService::get_latest_run(branch)                                     │
    │   │                                                                              │
    │   ├── GET /repos/{owner}/{repo}/actions/runs?branch=feature/card-{id}            │
    │   │                                                                              │
    │   ├── Workflow status: queued → in_progress → completed                          │
    │   │                                                                              │
    │   ▼                                                                              │
    │ On status change:                                                                │
    │   │                                                                              │
    │   ├── in_progress: card.state → BUILDING                                         │
    │   │   EventBus::publish(BuildStarted)                                            │
    │   │                                                                              │
    │   ├── completed/success:                                                         │
    │   │   │                                                                          │
    │   │   ├── card.state → BUILD_SUCCESS                                             │
    │   │   ├── EventBus::publish(BuildCompleted { success: true })                    │
    │   │   └── Auto-transition to DEPLOY_QUEUE                                        │
    │   │                                                                              │
    │   └── completed/failure:                                                         │
    │       │                                                                          │
    │       ├── GitHubActionsService::get_logs(run_id)                                 │
    │       ├── GitHubActionsService::get_failed_steps(run_id)                         │
    │       │                                                                          │
    │       ├── Store error in database:                                               │
    │       │   INSERT INTO errors (card_id, type='build', context=logs)               │
    │       │                                                                          │
    │       ├── card.state → BUILD_FAILED                                              │
    │       ├── EventBus::publish(BuildFailed { logs, steps })                         │
    │       │                                                                          │
    │       └── Trigger ERROR_FIXING flow (see Phase 8)                                │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 7: DEPLOYMENT MONITORING
═══════════════════════════════════════════════════════════════════════════════════════

    Build succeeded, card in DEPLOY_QUEUE
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ IntegrationHub (continued)                                                       │
    │   │                                                                              │
    │   ▼                                                                              │
    │ ArgoCDService::get_status(app_name)                                              │
    │   │                                                                              │
    │   ├── GET /api/v1/applications/{app_name}                                        │
    │   │   (via argocd-proxy with auth injection)                                     │
    │   │                                                                              │
    │   ├── Monitor sync status: OutOfSync → Synced                                    │
    │   ├── Monitor health: Progressing → Healthy                                      │
    │   │                                                                              │
    │   ▼                                                                              │
    │ When sync=Synced:                                                                │
    │   │                                                                              │
    │   ├── card.state → VERIFYING                                                     │
    │   │                                                                              │
    │   ▼                                                                              │
    │ KubernetesService::collect_deployment_errors(namespace, deployment)              │
    │   │                                                                              │
    │   ├── GET /apis/apps/v1/namespaces/{ns}/deployments/{name}                       │
    │   ├── GET /api/v1/namespaces/{ns}/pods?labelSelector=app={name}                  │
    │   │                                                                              │
    │   ├── For each pod:                                                              │
    │   │   ├── Check container statuses                                               │
    │   │   ├── Detect: CrashLoopBackOff, ImagePullBackOff, OOMKilled                  │
    │   │   └── Collect logs if needed                                                 │
    │   │                                                                              │
    │   ▼                                                                              │
    │ All pods healthy?                                                                │
    │   │                                                                              │
    │   ├── YES: card.state → COMPLETED                                                │
    │   │        EventBus::publish(DeploymentCompleted { success: true })              │
    │   │                                                                              │
    │   └── NO: Collect error context → ERROR_FIXING                                   │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════════════
PHASE 8: ERROR RECOVERY (Auto-restart loop with error context)
═══════════════════════════════════════════════════════════════════════════════════════

    Error detected at any phase
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ Error Recovery Flow                                                              │
    │   │                                                                              │
    │   ├── Check retry limit: card.error_count < max_retries ?                        │
    │   │   │                                                                          │
    │   │   ├── NO: card.state → FAILED (terminal)                                     │
    │   │   │       Notify user                                                        │
    │   │   │                                                                          │
    │   │   └── YES: Continue                                                          │
    │   │                                                                              │
    │   ├── card.error_count += 1                                                      │
    │   ├── card.previous_state = current_state                                        │
    │   ├── card.state → ERROR_FIXING                                                  │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Collect comprehensive error context:                                             │
    │   │                                                                              │
    │   ├── Build errors: GitHub Actions logs                                          │
    │   ├── Deploy errors: ArgoCD sync messages + K8s pod logs                         │
    │   ├── Runtime errors: Application logs                                           │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Database::create_error({                                                         │
    │   card_id,                                                                       │
    │   error_type: 'build' | 'deploy' | 'runtime',                                    │
    │   message: error_summary,                                                        │
    │   context: {                                                                     │
    │     logs: "...",                                                                 │
    │     source_state: previous_state,                                                │
    │     stack_trace: "...",                                                          │
    │   }                                                                              │
    │ })                                                                               │
    │   │                                                                              │
    │   ▼                                                                              │
    │ LoopManager::restart_loop_with_error(card_id, error_context)                     │
    │   │                                                                              │
    │   ├── Ralph loop starts with error context injected                              │
    │   │   (via Layer 4: SupplementalLayer includes error logs)                       │
    │   │                                                                              │
    │   ├── LLM analyzes error and generates fix                                       │
    │   │                                                                              │
    │   ├── Fix applied to code                                                        │
    │   │                                                                              │
    │   ▼                                                                              │
    │ On fix completion:                                                               │
    │   │                                                                              │
    │   ├── Determine return state based on error source:                              │
    │   │   ├── Build error → BUILD_QUEUE (retry build)                                │
    │   │   ├── Deploy error → DEPLOY_QUEUE (retry deploy)                             │
    │   │   └── Code error → CODE_REVIEW (re-review)                                   │
    │   │                                                                              │
    │   └── CardStateMachine::transition(card, FixApplied)                             │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

## WebSocket Event Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            WEBSOCKET EVENT FLOW                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘

    React UI connects to WebSocket
         │
         │ WS /api/ws
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ WebSocketHub                                                                     │
    │   │                                                                              │
    │   ├── Accept connection                                                          │
    │   ├── Generate connection_id                                                     │
    │   ├── Store in active_connections map                                            │
    │   │                                                                              │
    │   ▼                                                                              │
    │ Client sends subscribe message:                                                  │
    │ { "type": "subscribe", "cardIds": ["card-1", "card-2"], "projectIds": ["proj-1"] │
    │   │                                                                              │
    │   ├── Add connection to card_subscriptions[card_id]                              │
    │   └── Add connection to project_subscriptions[project_id]                        │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
         │
         │ Connection established
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ Event Publishing (from any service)                                              │
    │                                                                                  │
    │   EventBus::publish(event)                                                       │
    │         │                                                                        │
    │         ▼                                                                        │
    │   Route event to WebSocketHub based on event type:                               │
    │         │                                                                        │
    │         ├── CardCreated, CardUpdated, StateChanged                               │
    │         │     └── Broadcast to card subscribers + project subscribers            │
    │         │                                                                        │
    │         ├── LoopStarted, IterationStarted, IterationCompleted, LoopCompleted     │
    │         │     └── Broadcast to card subscribers                                  │
    │         │                                                                        │
    │         ├── BuildStarted, BuildCompleted, BuildFailed                            │
    │         │     └── Broadcast to card subscribers                                  │
    │         │                                                                        │
    │         └── DeployStarted, DeployCompleted, DeployFailed                         │
    │               └── Broadcast to card subscribers                                  │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
         │
         │ WebSocket messages
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ React UI receives events                                                         │
    │                                                                                  │
    │   useWebSocket hook:                                                             │
    │     │                                                                            │
    │     ├── Parse message type                                                       │
    │     │                                                                            │
    │     ├── card_updated → useCardStore.updateCard(card)                             │
    │     │     └── Kanban board re-renders                                            │
    │     │                                                                            │
    │     ├── state_changed → useCardStore.updateCardState(cardId, newState)           │
    │     │     └── Card moves to new column                                           │
    │     │                                                                            │
    │     ├── loop_iteration → useLoopStore.updateIteration(cardId, iteration)         │
    │     │     └── Loop progress indicator updates                                    │
    │     │                                                                            │
    │     ├── build_status → Update build indicator                                    │
    │     │                                                                            │
    │     └── deploy_status → Update deploy indicator                                  │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

## Database Transaction Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                          DATABASE TRANSACTION FLOW                                    │
└──────────────────────────────────────────────────────────────────────────────────────┘

    State Transition Request
         │
         ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │ Database Transaction (atomic)                                                    │
    │                                                                                  │
    │   BEGIN TRANSACTION;                                                             │
    │                                                                                  │
    │   -- 1. Lock card row                                                            │
    │   SELECT * FROM cards WHERE id = $1 FOR UPDATE;                                  │
    │                                                                                  │
    │   -- 2. Update card state                                                        │
    │   UPDATE cards SET                                                               │
    │     state = $2,                                                                  │
    │     previous_state = $3,                                                         │
    │     state_changed_at = NOW(),                                                    │
    │     updated_at = NOW()                                                           │
    │   WHERE id = $1;                                                                 │
    │                                                                                  │
    │   -- 3. Record state transition (audit)                                          │
    │   INSERT INTO state_transitions                                                  │
    │     (card_id, from_state, to_state, trigger, created_at)                         │
    │   VALUES ($1, $3, $2, $4, NOW());                                                │
    │                                                                                  │
    │   -- 4. Update related records if needed                                         │
    │   -- (e.g., mark acceptance criteria as met)                                     │
    │                                                                                  │
    │   COMMIT;                                                                        │
    │                                                                                  │
    │   -- On error: ROLLBACK                                                          │
    │                                                                                  │
    └─────────────────────────────────────────────────────────────────────────────────┘
         │
         │ Transaction committed
         │
         ▼
    EventBus::publish() - Events only sent AFTER successful commit
```

## Concurrent Operation Handling

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                        CONCURRENT OPERATIONS                                          │
└──────────────────────────────────────────────────────────────────────────────────────┘

    Multiple Ralph Loops Running Simultaneously
         │
    ┌────┴────┬────────────┬────────────┐
    │         │            │            │
    ▼         ▼            ▼            ▼
 Card A    Card B       Card C       Card D
 (Loop)    (Loop)       (Loop)       (Loop)
    │         │            │            │
    │         │            │            │
    ▼         ▼            ▼            ▼
 ┌────────────────────────────────────────────┐
 │ LoopManager::active_loops (RwLock)         │
 │                                            │
 │  HashMap<Uuid, Arc<RalphLoop>>             │
 │  • Read lock for status queries            │
 │  • Write lock for add/remove               │
 │                                            │
 └────────────────────────────────────────────┘
    │         │            │            │
    │         │            │            │
    ▼         ▼            ▼            ▼
 ┌────────────────────────────────────────────┐
 │ Git Worktrees (Isolated)                   │
 │                                            │
 │  ~/.ringmaster/worktrees/                   │
 │  ├── card-A/  (isolated branch)            │
 │  ├── card-B/  (isolated branch)            │
 │  ├── card-C/  (isolated branch)            │
 │  └── card-D/  (isolated branch)            │
 │                                            │
 │  No conflicts: each card has own worktree  │
 │                                            │
 └────────────────────────────────────────────┘
    │         │            │            │
    │         │            │            │
    ▼         ▼            ▼            ▼
 ┌────────────────────────────────────────────┐
 │ LLM API Calls (Rate Limited)               │
 │                                            │
 │  Semaphore: max_concurrent_calls = 5       │
 │  • Each loop acquires permit before call   │
 │  • Releases after response                 │
 │  • Prevents API rate limiting              │
 │                                            │
 └────────────────────────────────────────────┘
    │         │            │            │
    │         │            │            │
    ▼         ▼            ▼            ▼
 ┌────────────────────────────────────────────┐
 │ Database Connections (Pool)                │
 │                                            │
 │  sqlx::Pool<Sqlite>                        │
 │  • Connection pool size: 10                │
 │  • Async connection checkout               │
 │  • Automatic connection recycling          │
 │                                            │
 └────────────────────────────────────────────┘
    │         │            │            │
    └────┬────┴────────────┴────────────┘
         │
         ▼
 ┌────────────────────────────────────────────┐
 │ EventBus (Broadcast Channel)               │
 │                                            │
 │  tokio::sync::broadcast::channel(1000)     │
 │  • Multiple producers (loops, services)    │
 │  • Multiple consumers (websocket, logger)  │
 │  • Non-blocking publish                    │
 │                                            │
 └────────────────────────────────────────────┘
```
