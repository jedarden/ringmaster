# Ringmaster Implementation Progress

## Current State

**Status**: Core Implementation Complete

The Python-based implementation is now functional with all core components in place.

## Completed Components

### Domain Models (`src/ringmaster/domain/`)
- ✅ Task, Epic, Subtask entities with Beads-style IDs
- ✅ Decision and Question types for human-in-the-loop
- ✅ Worker entity with CLI configuration
- ✅ Project entity with tech stack and settings
- ✅ Status enums (TaskStatus, WorkerStatus, Priority)

### Database Layer (`src/ringmaster/db/`)
- ✅ SQLite connection with async support (aiosqlite)
- ✅ Automatic migration runner
- ✅ Repository pattern for Projects, Tasks, Workers
- ✅ Dependency tracking in graph structure

### Queue Manager (`src/ringmaster/queue/`)
- ✅ Priority calculation using PageRank algorithm
- ✅ Betweenness centrality for bottleneck detection
- ✅ Critical path analysis
- ✅ Task assignment to idle workers
- ✅ Dependency-aware task readiness

### API Server (`src/ringmaster/api/`)
- ✅ FastAPI application with CORS
- ✅ RESTful routes for projects, tasks, workers
- ✅ Queue management endpoints
- ✅ Health check endpoint
- ✅ WebSocket endpoint for real-time events

### Event System (`src/ringmaster/events/`)
- ✅ EventBus with pub/sub pattern
- ✅ EventType enum (task, worker, project, queue, scheduler events)
- ✅ Async callback support
- ✅ Project-based event filtering

### Worker Interface (`src/ringmaster/worker/`)
- ✅ Abstract WorkerInterface base class
- ✅ Claude Code CLI implementation
- ✅ Aider CLI implementation
- ✅ Generic worker for arbitrary CLIs
- ✅ Async subprocess execution with streaming
- ✅ Session lifecycle management
- ✅ **Real-time output streaming**
  - OutputBuffer class with pub/sub for real-time output
  - GET /api/workers/{id}/output - Poll recent output lines
  - GET /api/workers/{id}/output/stream - SSE stream for real-time
  - GET /api/workers/output/stats - Buffer statistics
  - WORKER_OUTPUT event for WebSocket notifications
  - Executor integration: writes to buffer and emits events

### Enricher (`src/ringmaster/enricher/`)
- ✅ 9-layer prompt assembly pipeline
- ✅ Stage-based architecture
- ✅ Context hash for deduplication
- ✅ RLM summarization with hierarchical compression
- ✅ Code context extraction with intelligent file selection
- ✅ **Deployment context extraction**
  - Environment config loading (.env, .env.example, etc.) with secret redaction
  - Docker Compose file parsing
  - Kubernetes manifest extraction with YAML parsing and secret redaction
  - Helm values files
  - CI/CD workflow configs (GitHub Actions, GitLab CI)
  - GitHub Actions run status via gh CLI
  - Task relevance scoring for deployment keywords
  - Token budgeting with file limits
- ✅ **Documentation context extraction** (per docs/04-context-enrichment.md section 3)
  - README files (always included)
  - Coding conventions and .editorconfig
  - Architecture Decision Records (ADRs) filtered by relevance
  - API specifications (when task is API-related)
  - Architecture documentation (when task is architecture-related)
  - Token budgeting with file truncation
- ✅ **Logs context extraction** (per docs/04-context-enrichment.md section 6)
  - Keyword-based debugging task detection (error, bug, fix, crash, etc.)
  - Task-specific logs (matching task_id)
  - Project-level error/critical logs from last 24 hours
  - Stack traces and error details from log data
  - Token budgeting with truncation
- ✅ **Research context extraction** (per docs/04-context-enrichment.md section 2)
  - Prior agent task outputs and completion summaries
  - Keyword-based relevance scoring with Jaccard similarity
  - Session metrics integration for output_summary
  - Fallback to task description when no summary
  - Configurable relevance threshold and max results
  - Token budgeting with truncation
- ✅ **Context assembly observability** (per docs/04-context-enrichment.md Observability section)
  - ContextAssemblyLog domain model for tracking assembly metrics
  - Database table (migration 010) for storing logs
  - ContextAssemblyLogRepository for CRUD and aggregation queries
  - EnrichmentPipeline logs assembly events with timing and token usage
  - API endpoints for querying logs, stats, and budget utilization alerts
  - Cleanup endpoint for old log pruning

### Scheduler (`src/ringmaster/scheduler/`)
- ✅ Worker lifecycle management
- ✅ Task assignment loop
- ✅ Health check monitoring
- ✅ Graceful shutdown handling
- ✅ **Self-improvement flywheel integration**
  - Detects when tasks modify ringmaster source code
  - Runs tests via HotReloader after task completion
  - Reloads modules on test success
  - Rollback on test failure (configurable)
  - Emits SCHEDULER_RELOAD events for UI notifications

### Hot-Reload (`src/ringmaster/reload/`)
- ✅ FileChangeWatcher for monitoring source directories
- ✅ ConfigWatcher for configuration file changes
- ✅ SafetyValidator for protected files and test coverage
- ✅ HotReloader orchestrating tests, reload, and rollback
- ✅ Hash-based change detection for accurate modification tracking
- ✅ Git-based rollback on test failure

### CLI (`src/ringmaster/cli.py`)
- ✅ `ringmaster serve` - Start API server
- ✅ `ringmaster scheduler` - Start task scheduler
- ✅ `ringmaster init` - Initialize database
- ✅ `ringmaster status` - Show queue stats
- ✅ `ringmaster doctor` - Check system health
- ✅ `ringmaster project` - Project management
- ✅ `ringmaster task` - Task management
- ✅ `ringmaster worker` - Worker management

### Tests
- ✅ Domain model unit tests
- ✅ Database CRUD tests
- ✅ Dependency tracking tests
- ✅ Event bus unit tests
- ✅ API integration tests (29 tests covering all endpoints)
- ✅ Hot-reload tests (27 tests covering watcher, safety, reloader, scheduler integration)

## Tech Stack

- **Backend**: Python 3.11+ with asyncio
- **Web Framework**: FastAPI with uvicorn
- **Database**: SQLite with aiosqlite
- **CLI**: Click with Rich formatting
- **Testing**: pytest with pytest-asyncio

## File Structure

```
src/ringmaster/
├── __init__.py
├── cli.py                 # CLI entry point
├── api/
│   ├── __init__.py
│   ├── app.py             # FastAPI app
│   ├── deps.py            # Dependencies
│   └── routes/
│       ├── projects.py
│       ├── tasks.py
│       ├── workers.py
│       ├── queue.py
│       └── ws.py
├── db/
│   ├── __init__.py
│   ├── connection.py      # Database connection
│   └── repositories.py    # Repository classes
├── domain/
│   ├── __init__.py
│   ├── enums.py           # Status enums
│   └── models.py          # Pydantic models
├── enricher/
│   ├── __init__.py
│   ├── pipeline.py        # Prompt assembly
│   ├── rlm.py             # RLM summarization
│   └── stages.py          # Individual stages
├── events/
│   ├── __init__.py
│   ├── bus.py             # Event bus pub/sub
│   └── types.py           # Event type definitions
├── queue/
│   ├── __init__.py
│   ├── manager.py         # Queue management
│   └── priority.py        # Priority algorithms
├── reload/
│   ├── __init__.py
│   ├── watcher.py         # File change detection
│   ├── safety.py          # Protected files & validation
│   └── reloader.py        # Hot-reload orchestration
├── scheduler/
│   ├── __init__.py
│   └── manager.py         # Scheduler loop
├── creator/
│   ├── __init__.py
│   ├── parser.py          # Input parsing
│   ├── decomposer.py      # Task decomposition
│   ├── matcher.py         # Duplicate detection
│   └── service.py         # BeadCreator service
└── worker/
    ├── __init__.py
    ├── interface.py       # Abstract interface
    ├── platforms.py       # Platform implementations
    └── executor.py        # Task execution
```

### Frontend (`frontend/`)
- ✅ React + Vite + TypeScript scaffold
- ✅ React Router with 5 views (Projects, ProjectDetail, Workers, Queue, Logs)
- ✅ API client with full coverage of backend endpoints
- ✅ TypeScript types matching backend domain models
- ✅ Layout component with navigation and API health indicator
- ✅ Vite proxy configuration for development
- ✅ Real-time WebSocket updates via useWebSocket hook
- ✅ WebSocket connection status in header
- ✅ ChatPanel component integrated in project detail view
- ✅ Chat API client functions (messages, summaries, context)
- ✅ Real-time chat message updates via WebSocket
- ✅ FileBrowser component with directory navigation and file preview
- ✅ TaskInput component for natural language task creation
  - Text area with auto-resize and placeholder examples
  - Priority selector with color-coded options
  - Auto-decompose toggle for large task breakdown
  - Debounced related task search for duplicate detection
  - Created tasks display with type badges and update indicators
- ✅ Voice input using Web Speech API
  - useSpeechRecognition hook with browser-native transcription
  - Voice toggle button with visual feedback (pulse animation)
  - Interim and final transcript handling
  - Error handling for microphone access and browser support
- ✅ File attachments
  - Attachment button to select files for upload
  - Attachment preview with filename, size, and remove button
  - Upload progress indication
  - Media type icons (image, document, code, archive)
  - Display attachments in message history

### Chat API (`src/ringmaster/api/routes/chat.py`)
- ✅ Message CRUD endpoints (create, list, recent, count)
- ✅ Task-scoped message filtering
- ✅ Summary listing and latest retrieval
- ✅ History context endpoint with RLM compression
- ✅ Configurable compression parameters
- ✅ Clear summaries endpoint for re-summarization
- ✅ File upload endpoint (POST /api/chat/projects/{id}/upload)
  - Size validation (10MB limit)
  - MIME type detection
  - Unique filename generation with content hash
  - Media type categorization (image, document, code, archive)
- ✅ File metadata endpoint (GET /api/chat/projects/{id}/uploads/{filename})
- ✅ 19 integration tests covering all endpoints

### File Browser API (`src/ringmaster/api/routes/files.py`)
- ✅ Directory listing endpoint with breadcrumb navigation support
- ✅ File content retrieval with binary detection
- ✅ Path traversal protection (security)
- ✅ Smart file type detection (text vs binary)
- ✅ Ignored directories filtering (.git, node_modules, etc.)
- ✅ Project working directory from repo_url or settings.working_dir
- ✅ 6 integration tests covering all endpoints

### Metrics API (`src/ringmaster/api/routes/metrics.py`)
- ✅ Complete metrics endpoint with task/worker stats, events, activity summaries
- ✅ Task stats endpoint (counts by status)
- ✅ Worker metrics endpoint (status counts, completion totals)
- ✅ Recent events endpoint with filtering (by event_type, entity_type)
- ✅ Activity summary endpoint with custom time period
- ✅ 9 integration tests covering all endpoints

### Metrics Dashboard (`frontend/src/components/MetricsDashboard.tsx`)
- ✅ Task overview grid with status counts and color coding
- ✅ Worker status with success rate calculation
- ✅ Activity comparison (24h vs 7 days)
- ✅ Recent events timeline with icons and time-ago display
- ✅ WebSocket integration for real-time updates
- ✅ Dedicated /metrics route in navigation

### Logs Viewer (`frontend/src/components/LogsViewer.tsx`)
- ✅ Real-time log viewing with WebSocket streaming (live mode)
- ✅ Filter by log level (debug, info, warning, error, critical)
- ✅ Filter by component (api, queue, enricher, scheduler, worker, reload, creator)
- ✅ Full-text search in messages (paginated mode)
- ✅ Task/worker/project scoping via props
- ✅ Log statistics bar showing 24h totals
- ✅ Expandable log entries with detailed data view
- ✅ Pagination for historical log browsing
- ✅ Dedicated /logs route in navigation
- ✅ API client functions for all log endpoints
- ✅ WebSocket connection status indicator (live vs reconnecting)
- ✅ Duplicate prevention via seen log ID tracking

### Bead Creator Service (`src/ringmaster/creator/`)
- ✅ Parser module for extracting task candidates from natural language
  - Action type detection (create, fix, update, remove, test, document, investigate)
  - Target extraction from action phrases
  - Ordering hints detection (first, then, finally, after)
  - Multi-segment splitting (conjunctions, lists, bullets)
  - Epic detection based on size/keyword signals
- ✅ Decomposer module for breaking large tasks into subtasks
  - Size signal detection (length, components, concerns, conjunctions)
  - List-based subtask extraction (numbered/bulleted)
  - Component-based subtask extraction
  - Standard subtask inference based on action type
- ✅ Matcher module for finding existing similar tasks
  - Jaccard and Cosine similarity scoring
  - Configurable match threshold
  - Related task suggestions
- ✅ BeadCreator service orchestrating the full flow
  - Parse → Match → Decompose → Create pipeline
  - Duplicate detection to update instead of recreate
  - Dependency creation based on ordering
  - Event emission for real-time updates
- ✅ Input API endpoints (`/api/input`)
  - POST `/api/input` - Create tasks from natural language
  - POST `/api/input/suggest-related` - Find related existing tasks
- ✅ 32 tests (26 creator + 6 API integration)

### Worker Executor (`src/ringmaster/worker/executor.py`)
- ✅ EnrichmentPipeline integration for context-aware prompts
  - Lazy initialization of enrichment pipeline
  - Automatic project context fetching
  - 5-layer prompt assembly (task, project, code, history, refinement)
  - Context hash tracking for deduplication
  - Prompt file saving for debugging/auditing
  - Fallback prompt when enrichment fails
- ✅ 11 new tests covering executor enrichment

### Logs API (`src/ringmaster/api/routes/logs.py`)
- ✅ Create log endpoint (POST /api/logs)
- ✅ List logs with filtering (component, level, task, worker, project, since)
- ✅ Full-text search in log messages via FTS5
- ✅ Pagination (offset/limit)
- ✅ Recent logs endpoint (last N minutes)
- ✅ Task-scoped logs endpoint (GET /api/logs/for-task/{task_id})
- ✅ Worker-scoped logs endpoint (GET /api/logs/for-worker/{worker_id})
- ✅ Log statistics endpoint (counts by level/component)
- ✅ Clear old logs endpoint (DELETE /api/logs)
- ✅ Components and levels listing endpoints
- ✅ 17 integration tests covering all endpoints

### Graph API (`src/ringmaster/api/routes/graph.py`)
- ✅ GET /api/graph endpoint for task dependency graph data
  - Returns nodes (tasks) and edges (dependencies)
  - Filter by project_id (required)
  - Optional include_done flag for completed tasks
  - Optional include_subtasks flag
  - Includes parent-child relationships (epic->task, task->subtask)
  - Stats with counts by status and type
- ✅ 8 integration tests covering all graph functionality

### Dependency Graph UI (`frontend/src/components/DependencyGraph.tsx`)
- ✅ Force-directed layout with SVG rendering
- ✅ Node shapes by type (hexagon=epic, rect=task, circle=subtask)
- ✅ Node colors by task status
- ✅ Priority affects node size
- ✅ Critical path highlighting (orange border)
- ✅ Interactive: drag nodes, hover tooltips, click to select
- ✅ Controls to toggle completed tasks and subtasks
- ✅ Legend showing status colors and shape meanings
- ✅ Dedicated /projects/:projectId/graph route
- ✅ "View Graph" link on project detail page

### Task Assignment UI (`frontend/src/pages/ProjectDetailPage.tsx`)
- ✅ Worker selector dropdown in task cards
- ✅ Shows available (idle or already assigned) workers only
- ✅ POST /api/tasks/{task_id}/assign endpoint
- ✅ Validates worker availability (rejects offline/busy workers)
- ✅ Validates task type (epics cannot be assigned)
- ✅ Updates both task (status=assigned) and worker (status=busy) atomically
- ✅ Unassign by selecting "Unassigned" option
- ✅ Real-time updates via WebSocket events
- ✅ 5 new integration tests

### Nested Subtask Display (`frontend/src/pages/ProjectDetailPage.tsx`)
- ✅ Subtasks grouped by parent task ID
- ✅ Collapsible subtask section under each task card
- ✅ Expand/collapse toggle showing subtask count
- ✅ Subtask priority badge and status badge
- ✅ Status dropdown for changing subtask status
- ✅ Worker assignment dropdown for subtasks
- ✅ Delete button for individual subtasks
- ✅ Color-coded border based on subtask status (ready/in-progress/blocked/done)
- ✅ CSS styles for nested subtask components

### Epic Child Tasks Display (`frontend/src/pages/ProjectDetailPage.tsx`)
- ✅ Tasks grouped by parent epic ID
- ✅ Progress bar showing completion percentage (done/total tasks)
- ✅ Collapsible child tasks section under each epic card
- ✅ Expand/collapse toggle showing task count
- ✅ Child task priority badge and status badge
- ✅ Subtask count indicator showing nested subtasks per task
- ✅ Status dropdown for changing child task status
- ✅ Worker assignment dropdown for child tasks
- ✅ Delete button for individual child tasks
- ✅ Color-coded border based on child task status (ready/in-progress/blocked/done/review)
- ✅ CSS styles for epic child task components
- ✅ Non-epic tasks (orphan tasks) displayed separately in kanban board

### Bulk Task Operations (`frontend/src/pages/ProjectDetailPage.tsx`)
- ✅ Task selection with checkboxes in kanban board
- ✅ Select All / Deselect All buttons
- ✅ Bulk operations toolbar (appears when tasks selected)
- ✅ Bulk status change dropdown
- ✅ Bulk priority change dropdown
- ✅ Bulk worker assignment dropdown with unassign option
- ✅ Bulk delete with confirmation
- ✅ Loading state during bulk operations
- ✅ Error handling with partial success reporting
- ✅ Visual highlighting of selected tasks
- ✅ CSS styles for bulk operations UI

### Bulk Operations API (`src/ringmaster/api/routes/tasks.py`)
- ✅ POST /api/tasks/bulk-update endpoint for bulk status/priority/assignment
- ✅ POST /api/tasks/bulk-delete endpoint for bulk deletion
- ✅ Validation: worker availability, epic assignment prevention
- ✅ Graceful handling of invalid task IDs
- ✅ Partial success reporting (updated, failed, errors)
- ✅ 4 new integration tests

### Interactive Graph Editing (`frontend/src/components/DependencyGraph.tsx`)
- ✅ Drag-to-create dependencies: click connector (+) on node and drag to target
- ✅ Visual feedback during drag with dashed line preview
- ✅ Right-click context menu on edges to delete dependencies
- ✅ DELETE /api/tasks/{task_id}/dependencies/{parent_id} endpoint
- ✅ removeTaskDependency function in frontend API client
- ✅ remove_dependency method in TaskRepository
- ✅ Instructions bar explaining interactions
- ✅ Error notification for failed operations
- ✅ 2 new integration tests

### Keyboard Shortcuts (`frontend/src/hooks/useKeyboardShortcuts.ts`)
- ✅ useKeyboardShortcuts hook for global keyboard handling
- ✅ Support for key sequences (e.g., "g m" for go to mailbox)
- ✅ useListNavigation hook for j/k navigation in lists
- ✅ useDefaultShortcuts hook with standard shortcuts
- ✅ CommandPalette component (Cmd+K or /) for quick navigation
- ✅ ShortcutsHelp modal (?) showing all keyboard shortcuts
- ✅ Pending sequence indicator during multi-key shortcuts
- ✅ ProjectsPage with j/k navigation and Enter to open
- ✅ WorkersPage with j/k navigation and Enter to toggle

### Worker Output Panel (`frontend/src/components/WorkerOutputPanel.tsx`)
- ✅ Real-time output streaming via SSE (Server-Sent Events)
- ✅ Live mode with EventSource connection
- ✅ Polling mode fallback with refresh button
- ✅ Auto-scroll with manual scroll detection
- ✅ Line number display and total line count
- ✅ Connection status indicator (green=connected, red=disconnected)

### Worker Monitor (`src/ringmaster/worker/monitor.py`)
- ✅ Heartbeat-based liveness detection (ACTIVE, THINKING, SLOW, LIKELY_HUNG)
- ✅ Context degradation detection (repetition, excessive apologies, retry loops)
- ✅ Configurable thresholds for monitoring sensitivity
- ✅ Recovery action recommendations (none, log_warning, interrupt, checkpoint_restart, escalate)
- ✅ N-gram analysis for repetition scoring
- ✅ Pattern-based detection for apology/retry phrases
- ✅ Integration with WorkerExecutor for real-time monitoring
- ✅ Event emission for hung/degraded worker notifications

Implemented shortcuts:
- g m: Go to mailbox (projects)
- g a: Go to agents (workers)
- g q: Go to queue
- g d: Go to dashboard (metrics)
- g l: Go to logs
- j/k: Navigate up/down in lists
- Enter: Open selected item
- Cmd+K or /: Open command palette
- ?: Show shortcuts help
- Escape: Close modal or go back

### Undo/Redo System (`src/ringmaster/api/routes/undo.py`)
- ✅ Action domain model for tracking reversible operations
- ✅ ActionType, EntityType, ActorType enums for action classification
- ✅ ActionRepository for persisting action history
- ✅ action_history table migration (005_action_history.sql)
- ✅ GET /api/undo/history - List recent actions with can_undo/can_redo flags
- ✅ GET /api/undo/last - Get last undoable action
- ✅ POST /api/undo - Undo the last action
- ✅ POST /api/undo/redo - Redo the last undone action
- ✅ Undo/redo for task CRUD operations
- ✅ Undo/redo for task status changes
- ✅ Undo/redo for dependency changes
- ✅ UNDO_PERFORMED/REDO_PERFORMED event types
- ✅ Project-scoped action filtering
- ✅ 7 new integration tests

### Frontend Undo UI (`frontend/src/hooks/useUndo.ts`, `frontend/src/components/Toast.tsx`)
- ✅ useUndo hook for managing undo/redo state
- ✅ Toast component for notification feedback
- ✅ useToast hook with success/error/info methods
- ✅ Cmd+Z keyboard shortcut for undo
- ✅ Cmd+Shift+Z keyboard shortcut for redo
- ✅ WebSocket refresh on undo/redo events
- ✅ API client functions (performUndo, performRedo, getUndoHistory)
- ✅ TypeScript types for undo/redo responses

### Worker Capabilities (`src/ringmaster/domain/models.py`, `src/ringmaster/db/repositories.py`)
- ✅ capabilities field on Worker model (e.g., ["python", "typescript", "security"])
- ✅ required_capabilities field on Task and Subtask models
- ✅ Database migration 006 for new columns
- ✅ WorkerRepository.get_capable_workers() for capability matching
- ✅ Scheduler uses capability matching when assigning tasks to workers
- ✅ API endpoints for managing worker capabilities:
  - GET /api/workers/{id}/capabilities - List worker capabilities
  - POST /api/workers/{id}/capabilities - Add a capability
  - DELETE /api/workers/{id}/capabilities/{cap} - Remove a capability
  - GET /api/workers/capable/{cap} - List workers with a capability
- ✅ 7 new integration tests

### Worker Output Parsing (`src/ringmaster/worker/outcome.py`)
- ✅ Multi-signal outcome detection per docs/09-remaining-decisions.md Section 6
- ✅ Outcome enum: SUCCESS, LIKELY_SUCCESS, FAILED, LIKELY_FAILED, NEEDS_DECISION, UNKNOWN
- ✅ OutcomeSignals dataclass tracking exit_code, markers, test results, completion signal
- ✅ OutcomeResult with outcome, signals, confidence (0.0-1.0), reason, decision_question
- ✅ SUCCESS_MARKERS: completion signal, checkmarks, "successfully completed", etc.
- ✅ FAILURE_MARKERS: "Error:", "FAILED", "Build failed", etc.
- ✅ DECISION_MARKERS: "? Decision needed", "BLOCKED:", "Should I", etc.
- ✅ Test result detection: pytest, Jest, Mocha patterns
- ✅ Decision question extraction from output
- ✅ blocked_reason field on Task model for NEEDS_DECISION outcomes
- ✅ outcome/outcome_confidence columns in session_metrics (migration 007)
- ✅ Executor integration: uses detect_outcome() for task status determination
- ✅ BLOCKED status with event emission when human input needed
- ✅ 31 new tests covering all detection scenarios

### Priority Inheritance (`src/ringmaster/queue/priority.py`)
- ✅ Blockers inherit priority from high-priority blocked tasks
- ✅ Transitive inheritance through dependency chains
- ✅ Completed/failed tasks don't propagate inheritance
- ✅ Only BLOCKED status triggers inheritance
- ✅ Prevents queue starvation for important blocked tasks
- ✅ Iterative propagation until no changes (handles cycles)
- ✅ 9 new tests for priority inheritance scenarios

### Decision & Question API (`src/ringmaster/api/routes/decisions.py`)
- ✅ Human-in-the-loop decision points that block task progress
- ✅ Non-blocking clarification questions with urgency levels
- ✅ Decision model: blocks_id, question, options, recommendation, resolution
- ✅ Question model: related_id, question, urgency, default_answer, answer
- ✅ Repository methods: create, get, list, resolve/answer
- ✅ API endpoints:
  - POST /api/decisions - Create decision (blocks task)
  - GET /api/decisions - List decisions with filters
  - GET /api/decisions/{id} - Get specific decision
  - POST /api/decisions/{id}/resolve - Resolve with chosen option
  - GET /api/decisions/for-task/{task_id} - Get decisions blocking a task
  - GET /api/projects/{id}/decisions/stats - Decision statistics
  - POST /api/questions - Create question (non-blocking)
  - GET /api/questions - List questions with filters (ordered by urgency)
  - GET /api/questions/{id} - Get specific question
  - POST /api/questions/{id}/answer - Answer question
  - GET /api/questions/for-task/{task_id} - Get questions for a task
  - GET /api/projects/{id}/questions/stats - Question statistics
- ✅ Event types: DECISION_CREATED, DECISION_RESOLVED, QUESTION_CREATED, QUESTION_ANSWERED
- ✅ Task status transitions: BLOCKED when decision created, READY when resolved
- ✅ 14 new integration tests

### Decision & Question Frontend (`frontend/src/components/`)
- ✅ DecisionPanel component for human-in-the-loop decisions
  - Displays pending decisions with question and context
  - Predefined options with recommendation badges
  - Custom answer input for "Other" option
  - Decision stats display (pending/total)
  - Time-ago formatting for decision age
  - Real-time refresh on resolve
- ✅ QuestionPanel component for clarification questions
  - Urgency-based display (low/medium/high) with color coding
  - Default answer display with "Use Default" button
  - Custom answer textarea
  - Show/hide answered questions toggle
  - Question stats with urgency breakdown
  - Time-ago formatting for question age
- ✅ TypeScript types (Decision, Question, related DTOs)
- ✅ API client functions for all endpoints
- ✅ CSS styles for decision-panel and question-panel
- ✅ Integrated in ProjectDetailPage sidebar above ChatPanel

### Project Summary API (`src/ringmaster/api/routes/projects.py`)
- ✅ GET /api/projects/with-summaries - List projects with activity summaries
- ✅ GET /api/projects/{id}/summary - Single project summary
- ✅ TaskStatusCounts model (draft, ready, assigned, in_progress, blocked, review, done, failed)
- ✅ ProjectSummary model with project, task_counts, total_tasks, active_workers, pending_decisions/questions, latest_activity
- ✅ Task counts aggregated by status (excludes epics/decisions/questions)
- ✅ Active workers computed via current_task_id join
- ✅ 5 new integration tests

### Rich Project Mailbox (`frontend/src/pages/ProjectsPage.tsx`)
- ✅ Uses listProjectsWithSummaries API for activity data
- ✅ Status indicators: needs_attention (red), in_progress (yellow), complete (green), idle (gray)
- ✅ Colored left border based on project status
- ✅ Activity summary line showing active workers, pending decisions, pending questions
- ✅ Task progress bar with percentage completion
- ✅ Time-ago display for latest activity
- ✅ Real-time refresh via WebSocket on task/worker/decision events
- ✅ TypeScript types: ProjectSummary, TaskStatusCounts
- ✅ CSS styles for status dots, progress bars, activity items

### Git File History & Diff API (`src/ringmaster/git/`, `src/ringmaster/api/routes/files.py`)
- ✅ Git operations module with async subprocess execution
  - get_file_history(): Git log for a file with commit metadata and stats
  - get_file_diff(): Diff between commits or working tree changes
  - get_file_at_commit(): Retrieve file content at specific commit
  - is_git_repo(): Check if path is in a git repository
- ✅ API endpoints for git operations:
  - GET /api/projects/{id}/files/history - File git history with commit list
  - GET /api/projects/{id}/files/diff - File diff (hunks, additions/deletions)
  - GET /api/projects/{id}/files/at-commit - File content at specific commit
- ✅ Path traversal security checks
- ✅ 17 new tests (10 git operations + 7 API integration)

### Git History Frontend UI (`frontend/src/components/`)
- ✅ GitHistoryModal component
  - Displays commit history for selected file
  - Commit list with hash, message, author, time-ago display
  - Color-coded additions/deletions stats per commit
  - Click commit to view diff
  - Escape key to close modal
- ✅ FileDiffViewer component
  - Unified diff display with syntax highlighting
  - Color-coded lines: green for additions, red for deletions
  - Hunk headers with line range info
  - Special handling for new/deleted/renamed files
  - Diff stats summary
- ✅ FileBrowser integration
  - "History" button in file preview header
  - Opens GitHistoryModal for selected file
- ✅ TypeScript types: CommitInfo, FileHistoryResponse, DiffHunkInfo, FileDiffResponse, FileAtCommitResponse
- ✅ API client functions: getFileHistory(), getFileDiff(), getFileAtCommit()

### Task Auto-Retry with Exponential Backoff (`src/ringmaster/worker/executor.py`)
- ✅ `retry_after` and `last_failure_reason` fields on Task/Subtask models
- ✅ Database migration 008_retry_tracking.sql for new columns
- ✅ `calculate_retry_backoff()` function with exponential delay (30s, 60s, 120s, ...)
- ✅ `get_ready_tasks()` filters out tasks with future retry_after
- ✅ Executor sets retry_after on failure with configurable max delay (1 hour)
- ✅ TASK_RETRY event emission with backoff details
- ✅ Success clears retry tracking fields
- ✅ 10 new tests covering backoff calculation and retry behavior

### Worker Control Buttons (`frontend/src/pages/WorkersPage.tsx`)
- ✅ POST /api/workers/{id}/cancel endpoint to cancel running task
  - Cancels task, marks worker as idle, marks task as failed
  - Emits WORKER_TASK_CANCELLED event
- ✅ POST /api/workers/{id}/pause endpoint to pause worker gracefully
  - Worker finishes current task then becomes offline
  - Emits WORKER_PAUSED event
- ✅ View Output button opens WorkerOutputPanel for busy workers
- ✅ Pause button to gracefully stop worker after current iteration
- ✅ Cancel button to immediately abort current task
- ✅ cancelWorkerTask() and pauseWorker() API client functions
- ✅ CSS styles for control buttons (view-output-btn, pause-btn, cancel-btn)
- ✅ 4 new tests for cancel/pause endpoints

### Task Resubmission for Decomposition (`src/ringmaster/api/routes/tasks.py`)
- ✅ NEEDS_DECOMPOSITION status added to TaskStatus enum
- ✅ POST /api/tasks/{id}/resubmit endpoint for worker resubmission
  - Workers can mark tasks as "too large" and send them for decomposition
  - Validates task type (only tasks, not epics/subtasks)
  - Unassigns worker and marks them idle
  - Stores resubmission reason in task description
  - Attempts immediate decomposition via BeadCreator decomposer
  - Creates subtasks if decomposition succeeds
  - Returns decomposition results (status, subtask count)
- ✅ TASK_RESUBMITTED event type for notifications
- ✅ Migration 009 for NEEDS_DECOMPOSITION status CHECK constraint
- ✅ 7 new integration tests

### Git Worktree Management (`src/ringmaster/git/worktrees.py`)
- ✅ Worktree and WorktreeConfig dataclasses for worktree representation
- ✅ Worktree operations for parallel worker isolation:
  - list_worktrees(): List all worktrees for a repository
  - get_or_create_worktree(): Create or reuse worktree for a worker
  - remove_worktree(): Clean up worker's worktree
  - get_worktree_status(): Check uncommitted changes and commits ahead
  - commit_worktree_changes(): Commit changes in a worktree
  - merge_worktree_to_main(): Merge worker's branch to main
  - clean_stale_worktrees(): Prune orphaned worktrees
- ✅ Support for both repos with origin remote and local-only repos
- ✅ Branch naming convention: `ringmaster/<task-id>`
- ✅ Layout: `/workspace/project-main.worktrees/worker-<id>/`
- ✅ 20 new tests covering all worktree operations

### Worker Executor Worktree Integration (`src/ringmaster/worker/executor.py`)
- ✅ `use_worktrees` parameter to enable/disable worktree isolation
- ✅ `_get_working_directory()` method determines execution directory
  - Creates worktree for git-based projects when enabled
  - Falls back to project directory for non-git repos
  - Reuses existing worktree for same worker
- ✅ `_report_worktree_status()` logs worktree state after task completion
- ✅ Graceful fallback on worktree creation failure
- ✅ 4 new integration tests for worktree execution paths

### Worker CLI Commands (`src/ringmaster/cli.py`)
- ✅ `pull-bead` - Workers pull next available task matching capabilities
  - Claims task atomically (sets status=assigned, worker_id)
  - Filters by worker capabilities vs task required_capabilities
  - Returns JSON task data for bash script consumption
  - Marks worker as busy
- ✅ `build-prompt` - Build enriched prompt for a task
  - Uses full EnrichmentPipeline (task, project, code, deployment, history context)
  - Outputs to stdout or file (-o flag)
  - Includes context hash and token estimate
- ✅ `report-result` - Report task completion/failure
  - Supports --status completed/failed
  - Handles retry backoff on failure
  - Updates worker to idle
  - Unblocks dependent tasks on success
- ✅ 7 new tests covering all CLI commands

### Worker Spawner (`src/ringmaster/worker/spawner.py`)
- ✅ WorkerSpawner class for tmux-based worker management
- ✅ Worker script template generation for multiple worker types:
  - Claude Code (`claude --print --dangerously-skip-permissions`)
  - Aider (`aider --yes --no-git`)
  - Codex (`codex --quiet --auto-approve`)
  - Goose (`goose run --non-interactive`)
  - Generic (custom command via WORKER_COMMAND env var)
- ✅ Spawner operations:
  - spawn(): Create tmux session with worker script
  - kill(): Terminate worker's tmux session
  - is_running(): Check if worker session exists
  - list_sessions(): List all ringmaster worker sessions
  - get_output(): Retrieve recent log output
  - send_signal(): Send signals to worker process
  - cleanup_stale(): Prune orphaned sessions/scripts
- ✅ SpawnedWorker dataclass with status tracking
- ✅ 21 new tests covering all spawner operations

### Worker Tmux CLI Commands (`src/ringmaster/cli.py`)
- ✅ `worker spawn` - Spawn worker in tmux session
  - Creates worker record if not exists
  - Generates bash worker script
  - Launches in detached tmux session
- ✅ `worker attach` - Show attach command for worker session
- ✅ `worker kill` - Kill worker's tmux session
- ✅ `worker sessions` - List all running worker sessions
- ✅ `worker output` - Show recent log output (supports -f follow mode)

### Worker Spawning API (`src/ringmaster/api/routes/workers.py`)
- ✅ POST /api/workers/{id}/spawn - Spawn worker in tmux
- ✅ POST /api/workers/{id}/kill - Kill worker's tmux session
- ✅ GET /api/workers/{id}/session - Get session info
- ✅ GET /api/workers/sessions/list - List all worker sessions
- ✅ GET /api/workers/{id}/log - Get worker log output
- ✅ GET /api/workers/with-tasks - List workers with enriched task info
  - Returns CurrentTaskInfo (task_id, title, status, started_at, attempts, max_attempts) for busy workers
  - Enables UI to show task title and duration for active workers

### Worker Health Monitoring API (`src/ringmaster/api/routes/workers.py`)
- ✅ GET /api/workers/{id}/health - Worker health status endpoint
  - Liveness status (active, thinking, slow, likely_hung, degraded)
  - Degradation signals (repetition_score, apology_count, retry_count, contradiction_count)
  - Recommended recovery action (none, log_warning, interrupt, checkpoint_restart, escalate)
  - Runtime and idle time tracking
  - Integrates with WorkerMonitor from worker/monitor.py
- ✅ 5 new integration tests for health endpoint

### Model Routing (`src/ringmaster/queue/routing.py`)
- ✅ Task complexity estimation with deterministic heuristics (no LLM calls)
  - File count detection from task description
  - Keyword analysis (simple vs complex signals)
  - Task type scoring (epic +2, subtask -1)
  - Priority scoring (P0 +1)
  - Description length scoring
- ✅ TaskComplexity enum (simple, moderate, complex)
- ✅ ModelTier enum (fast, balanced, powerful)
- ✅ ComplexitySignals dataclass with transparent scoring breakdown
- ✅ Model suggestions per tier for different worker types (claude-code, aider, codex, goose)
- ✅ GET /api/tasks/{id}/routing endpoint
  - Returns complexity, tier, reasoning, suggested models
  - Optional worker_type param for specific model recommendations
  - Signals breakdown for transparency
- ✅ 33 unit tests + 5 API integration tests

### Reasoning Bank (`src/ringmaster/db/repositories.py`, `src/ringmaster/queue/routing.py`)
- ✅ task_outcomes database table (migration 011) for reflexion-based learning
- ✅ TaskOutcome domain model with task signals (file_count, keywords, bead_type, has_dependencies)
- ✅ ReasoningBankRepository with CRUD and learning queries:
  - record(): Store task outcome
  - get(), get_for_task(): Retrieve outcomes
  - find_similar(): Keyword-based Jaccard similarity for learning
  - get_model_success_rates(): Per-model performance stats
  - get_stats(): Aggregated statistics
  - cleanup_old(): Prune old outcomes
- ✅ Learning-enhanced model routing:
  - LearnedSignals dataclass for learning metadata
  - extract_keywords(): Extract task keywords for similarity
  - select_model_with_learning(): Blend static heuristics with learned experience
  - generate_success_reflection(): Create task reflections
  - MIN_SAMPLES_FOR_LEARNING=10, LEARNING_SUCCESS_THRESHOLD=0.1
- ✅ Executor integration: _record_outcome() stores outcomes after task completion
- ✅ API endpoints for outcomes:
  - GET /api/outcomes - List outcomes with project filter
  - GET /api/outcomes/{id} - Get specific outcome
  - GET /api/outcomes/for-task/{task_id} - Get outcome for task
  - POST /api/outcomes/find-similar - Find similar outcomes for learning
  - GET /api/outcomes/model-stats - Model success rates
  - GET /api/outcomes/stats - Aggregated statistics
  - DELETE /api/outcomes/cleanup - Prune old outcomes
- ✅ 25 new tests (15 reasoning bank + 10 learning routing)

### Task Validator (`src/ringmaster/worker/validator.py`)
- ✅ TaskValidator class for running deterministic validation checks
- ✅ Auto-detection of test commands:
  - Python: pytest
  - Node.js: npm test
  - Rust: cargo test
  - Go: go test ./...
- ✅ Auto-detection of lint commands:
  - Python: ruff, flake8
  - Node.js: eslint
  - Rust: cargo clippy
  - Go: golangci-lint
- ✅ Auto-detection of type check commands:
  - Python: mypy
  - TypeScript: tsc
- ✅ Sensitive pattern detection (security, auth, payment, crypto)
  - Triggers human review requirement
- ✅ ValidationResult with check status (passed/failed/skipped/error)
- ✅ Configurable timeouts and commands
- ✅ API endpoints:
  - POST /api/tasks/{id}/validate - Run validation and transition status
  - POST /api/tasks/{id}/approve - Manual approval from REVIEW to DONE
  - POST /api/tasks/{id}/reject - Rejection with feedback back to IN_PROGRESS
- ✅ Task status transitions based on validation result:
  - REVIEW → DONE (validation passed)
  - REVIEW → IN_PROGRESS (validation failed, for fixes)
  - REVIEW → REVIEW (needs human review, stays for attention)
- ✅ 23 new tests covering all validation scenarios

## Next Steps

1. **Real Worker Test**: Connect to actual Claude Code CLI in development environment

## Iteration Log

| Iteration | Date | Summary |
|-----------|------|---------|
| 1 | 2026-01-26 | Initial Python implementation with all core components |
| 2 | 2026-01-26 | Fix deprecation warnings: replaced datetime.utcnow() with timezone-aware datetime.now(UTC), updated ruff config, removed unused import |
| 3 | 2026-01-26 | Add WebSocket support: event bus system, EventType enum, /ws endpoint with project filtering, event emission from task API routes |
| 4 | 2026-01-26 | Add comprehensive API integration tests: 29 tests covering health, projects, tasks, workers, and queue endpoints |
| 5 | 2026-01-26 | Build React frontend: Vite scaffold, TypeScript types, API client, React Router with 4 views (Projects, ProjectDetail, Workers, Queue), Layout with nav and API health indicator |
| 6 | 2026-01-26 | Add WebSocket integration to frontend: useWebSocket hook with auto-reconnect, all pages use real-time events for auto-refresh, WS connection status in header |
| 7 | 2026-01-26 | Implement RLM summarization: ChatMessage/Summary domain models, ChatRepository, RLMSummarizer with hierarchical compression, decision extraction, token budgeting, 11 new tests |
| 8 | 2026-01-26 | Implement code context extraction: CodeContextExtractor with explicit file detection, keyword-based search, import resolution, token budgeting, 16 new tests |
| 9 | 2026-01-26 | Add Chat API endpoints: 8 REST endpoints for messages/summaries/context, integrates RLM summarization, 12 new tests, total 86 tests passing |
| 10 | 2026-01-26 | Add Chat UI to frontend: ChatPanel component with message list and input, Chat API client functions, TypeScript types, integrated in project detail page as sidebar |
| 11 | 2026-01-26 | Wire ChatPanel to WebSocket: MESSAGE_CREATED event type, real-time message updates without polling, duplicate detection |
| 12 | 2026-01-26 | Implement hot-reload system: FileChangeWatcher, ConfigWatcher, SafetyValidator, HotReloader with test validation, module reload, and git rollback, 22 new tests, total 108 tests passing |
| 13 | 2026-01-26 | Integrate hot-reload into scheduler for self-improvement flywheel: detect source modifications after task completion, run tests, reload modules on success, rollback on failure, SCHEDULER_RELOAD event, 5 new tests, total 113 tests passing |
| 14 | 2026-01-26 | Add file browser: REST API for directory listing and file content, FileBrowser React component with breadcrumb navigation, file preview with syntax detection, path traversal protection, 6 new tests, total 119 tests passing |
| 15 | 2026-01-26 | Add end-to-end flywheel tests: 9 integration tests covering file change detection, hot-reload success/failure, mock worker simulation, protected file handling, total 128 tests passing |
| 16 | 2026-01-26 | Add metrics dashboard: REST API for task/worker stats and events, MetricsDashboard React component with activity summaries and event timeline, 9 new tests, total 137 tests passing |
| 17 | 2026-01-26 | Add bead creator service: Parser with action detection and ordering, Decomposer for large task breakdown, Matcher for duplicate detection, BeadCreator service, Input API endpoints, 32 new tests, total 169 tests passing |
| 18 | 2026-01-26 | Add frontend TaskInput component: natural language task creation UI, Input API types and client functions, priority selector, auto-decompose toggle, related task search with debouncing, result display with type badges |
| 19 | 2026-01-26 | Integrate EnrichmentPipeline into WorkerExecutor: 5-layer prompt assembly, project context fetching, context hash tracking, prompt file saving, fallback prompt, 11 new tests, total 180 tests passing |
| 20 | 2026-01-26 | Add Logs API for observability: structured logging with SQLite storage, FTS5 search, filtering by component/level/task/worker, pagination, statistics endpoint, 17 new tests, total 197 tests passing |
| 21 | 2026-01-27 | Add voice input to ChatPanel: useSpeechRecognition hook using Web Speech API, voice toggle button with pulse animation, interim transcript display, browser compatibility handling |
| 22 | 2026-01-27 | Add file attachments to chat: backend upload endpoint with size/type validation, FileUploadResponse type, uploadFile client function, ChatPanel attachment UI with preview, message attachment display with media icons, fixed chat API paths, 7 new tests, total 204 tests passing |
| 23 | 2026-01-27 | Add Logs UI: LogsViewer component with live mode auto-refresh, level/component filtering, full-text search, log statistics bar, expandable log details, pagination; LogsPage with /logs route; TypeScript types and API client functions for all log endpoints |
| 24 | 2026-01-27 | Add WebSocket log streaming: LOG_CREATED event emission from logs API, LogsViewer WebSocket integration for real-time updates in live mode, connection status indicator, duplicate prevention via seen log IDs, 2 new tests, total 206 tests passing |
| 25 | 2026-01-27 | Add file download endpoint: GET /api/chat/projects/{id}/uploads/{filename}/download with proper Content-Type and Content-Disposition headers, frontend client helpers (getDownloadUrl, downloadFile, triggerDownload), 3 new tests, total 209 tests passing |
| 26 | 2026-01-27 | Add task dependency graph visualization: /api/graph endpoint for graph data, DependencyGraph React component with force-directed SVG layout, node shapes by type, colors by status, size by priority, critical path highlighting, interactive drag/hover/click, /projects/:projectId/graph route, 8 new tests, total 217 tests passing |
| 27 | 2026-01-27 | Add task assignment UI: POST /api/tasks/{task_id}/assign endpoint, worker selector dropdown in task cards, validates worker availability (idle/not offline), validates task type (no epics), updates task and worker status atomically, unassign support, 5 new tests, total 222 tests passing |
| 28 | 2026-01-27 | Fix TypeScript error in DependencyGraph (useRef type), add nested subtask display in task cards: collapsible subtask section with expand/collapse toggle, subtask priority/status/title display, status and worker assignment dropdowns, delete button, color-coded border by status, CSS styles for subtask components |
| 29 | 2026-01-27 | Add epic child tasks display: tasks grouped by parent epic, progress bar with completion percentage, collapsible child tasks section, expand/collapse toggle with task count, subtask count indicator, status/worker dropdowns, delete button, color-coded border by status, orphan tasks separate in kanban |
| 30 | 2026-01-27 | Add worker integration tests: MockWorkerInterface/MockSessionHandle for CLI simulation, 14 new tests covering task execution flow, status transitions, output streaming, metrics recording, worker status updates, scheduler integration, unavailable worker handling, enrichment integration, total 236 tests passing |
| 31 | 2026-01-27 | Add bulk task operations: POST /api/tasks/bulk-update and /bulk-delete endpoints, task selection checkboxes in kanban board, select all/deselect all buttons, bulk toolbar with status/priority/assignment dropdowns, bulk delete with confirmation, 4 new tests, total 240 tests passing |
| 32 | 2026-01-27 | Add interactive graph editing: drag-to-create dependencies via connector (+) points, right-click context menu to delete edges, DELETE dependency endpoint, visual feedback during drag, instructions bar, error notifications, 2 new tests, total 242 tests passing |
| 33 | 2026-01-27 | Add keyboard shortcuts: useKeyboardShortcuts hook with sequence support (g m, g a), useListNavigation for j/k, CommandPalette (Cmd+K), ShortcutsHelp modal (?), pending sequence indicator, ProjectsPage/WorkersPage with j/k navigation |
| 34 | 2026-01-27 | Add undo/redo system: Action domain model, ActionRepository, undo API routes, action_history migration, UNDO/REDO events, 7 new tests, total 249 tests passing |
| 35 | 2026-01-27 | Add frontend undo UI: Cmd+Z/Cmd+Shift+Z keyboard shortcuts, useUndo hook, Toast notification component, undo/redo API client functions, WebSocket event refresh |
| 36 | 2026-01-27 | Add worker capabilities: capabilities field on Worker, required_capabilities on Task/Subtask, migration 006, get_capable_workers() method, scheduler capability matching, API endpoints for capability management, 7 new tests, total 256 tests passing |
| 37 | 2026-01-27 | Fix sqlite3.Row compatibility bug: capabilities and required_capabilities columns were not being read due to sqlite3.Row not supporting 'in' operator, switched to row.keys() checks, all 256 tests passing |
| 38 | 2026-01-27 | Add real-time worker output streaming: OutputBuffer class for buffering worker output with pub/sub support, SSE stream endpoint for real-time output, polling endpoint for recent output, WORKER_OUTPUT event type, WorkerOutputPanel React component with live/polling modes, auto-scroll detection, 6 new tests, total 262 tests passing |
| 39 | 2026-01-27 | Add long-running task monitoring: WorkerMonitor class with heartbeat-based liveness detection (ACTIVE/THINKING/SLOW/LIKELY_HUNG), context degradation detection (repetition, apologies, retry loops), n-gram analysis for repetition scoring, recovery action recommendations, executor integration for real-time monitoring, 21 new tests, total 283 tests passing |
| 40 | 2026-01-27 | Add worker output parsing with multi-signal detection: Outcome enum (SUCCESS, LIKELY_SUCCESS, FAILED, LIKELY_FAILED, NEEDS_DECISION, UNKNOWN), detect_outcome() with exit codes + markers + test results, SUCCESS_MARKERS, FAILURE_MARKERS, DECISION_MARKERS, blocked_reason field on Task model, outcome/outcome_confidence fields in metrics, migration 007, executor integration, 31 new tests, total 314 tests passing |
| 41 | 2026-01-27 | Add priority inheritance for blocked task queues: blockers inherit priority from high-priority blocked tasks, transitive inheritance, completed/failed tasks excluded, only BLOCKED status triggers inheritance, prevents queue starvation, 9 new tests, total 323 tests passing |
| 42 | 2026-01-27 | Add Decision & Question API for human-in-the-loop workflows: Decision model (blocks task), Question model (non-blocking), repository methods, 12 API endpoints for CRUD/resolve/answer, event types (DECISION_CREATED/RESOLVED, QUESTION_CREATED/ANSWERED), task blocking integration, 14 new tests, total 337 tests passing |
| 43 | 2026-01-27 | Add Decision & Question frontend UI: DecisionPanel component with option buttons and custom answers, QuestionPanel component with urgency badges and default answer support, TypeScript types and API client functions, CSS styles, integrated in ProjectDetailPage sidebar, fixed unused import in WorkersPage |
| 44 | 2026-01-27 | Add rich project mailbox view: GET /api/projects/with-summaries endpoint returning task counts, active workers, pending decisions/questions, latest activity; GET /api/projects/{id}/summary endpoint; ProjectSummary type with TaskStatusCounts; ProjectsPage updated with status indicators, activity summaries, progress bars, time-ago display; CSS styles for project cards, 5 new tests, total 342 tests passing |
| 45 | 2026-01-27 | Add task iteration progress display: shows attempt count (e.g., "2/5") in task cards, epic child tasks, and subtasks when tasks are in-progress; CSS styling for iteration badge; aligns with docs/07-user-experience.md iteration display spec |
| 46 | 2026-01-27 | Add deployment context source for enrichment pipeline: DeploymentContextExtractor class with env file loading (.env with secret redaction), Docker Compose configs, K8s manifests (with YAML parsing and secret value redaction), Helm values, CI/CD workflow files (GitHub Actions, GitLab CI), GitHub Actions status via gh CLI; task relevance scoring for deployment keywords; token budgeting with file limits; DeploymentContextStage integrated into 6-layer pipeline; 22 new tests, total 364 tests passing |
| 47 | 2026-01-27 | Add Git file history and diff API: Git operations module (get_file_history, get_file_diff, get_file_at_commit, is_git_repo), 3 new API endpoints for file git operations with path traversal protection, response models for commit info and diff hunks, 17 new tests, total 381 tests passing |
| 48 | 2026-01-27 | Add Git History Frontend UI: GitHistoryModal component with commit list and time-ago formatting, FileDiffViewer with unified diff display and color-coded lines, TypeScript types for git API responses, API client functions (getFileHistory, getFileDiff, getFileAtCommit), History button integrated into FileBrowser file preview, CSS styles for modal and diff viewer |
| 49 | 2026-01-27 | Add task auto-retry with exponential backoff: retry_after and last_failure_reason fields on Task/Subtask models, migration 008_retry_tracking.sql, calculate_retry_backoff() function (30s/60s/120s/...), get_ready_tasks() filters tasks in backoff period, TASK_RETRY event emission, success clears retry tracking, 10 new tests, total 391 tests passing |
| 50 | 2026-01-27 | Add worker control buttons: POST /api/workers/{id}/cancel and /pause endpoints, WORKER_TASK_CANCELLED and WORKER_PAUSED event types, View Output/Pause/Cancel buttons in WorkersPage for busy workers, WorkerOutputPanel integration, CSS styling for control buttons, 4 new tests, total 395 tests passing |
| 51 | 2026-01-27 | Add task resubmission for decomposition: NEEDS_DECOMPOSITION status, POST /api/tasks/{id}/resubmit endpoint for workers to mark tasks as too large, immediate decomposition via BeadCreator, TASK_RESUBMITTED event, migration 009, 7 new tests, total 402 tests passing |
| 52 | 2026-01-27 | Add git worktree support for worker isolation: Worktree/WorktreeConfig dataclasses, list_worktrees(), get_or_create_worktree(), remove_worktree(), get_worktree_status(), commit_worktree_changes(), merge_worktree_to_main(), clean_stale_worktrees(); handles both repos with origin remote and local-only repos; 20 new tests, total 422 tests passing |
| 53 | 2026-01-27 | Integrate git worktrees into WorkerExecutor: use_worktrees parameter, _get_working_directory() creates worktree for git repos, falls back for non-git, reuses worktree per worker, _report_worktree_status() for debugging; 4 new tests, total 426 tests passing |
| 54 | 2026-01-27 | Add worker CLI commands for external scripts: `pull-bead` (claim task matching capabilities), `build-prompt` (enriched prompt to stdout/file), `report-result` (completion/failure with retry backoff); enables bash-based worker scripts per docs/09-remaining-decisions.md section 4; 7 new tests, total 433 tests passing |
| 55 | 2026-01-27 | Add tmux-based worker spawning: WorkerSpawner class with spawn/kill/list_sessions, worker script generation for claude-code/aider/codex/goose/generic; CLI commands `worker spawn/attach/kill/sessions/output`; API endpoints POST /spawn, POST /kill, GET /session, GET /sessions/list, GET /log; enables on-demand worker management per docs/09-remaining-decisions.md section 4; 21 new tests, total 454 tests passing |
| 56 | 2026-01-27 | Fix test portability: use sys.executable instead of hardcoded 'python' in test_cli_worker.py subprocess calls, fix linting issues in test_spawner.py (combine nested with statements, remove unused imports/variables), all 454 tests passing |
| 57 | 2026-01-27 | Add worker spawner frontend UI: TypeScript types (SpawnWorkerRequest, SpawnedWorkerResponse, TmuxSessionResponse, WorkerLogResponse), API client functions (spawnWorker, killWorker, getWorkerSession, listWorkerSessions, getWorkerLog), WorkersPage spawn modal with worker type/capabilities/worktree config, tmux session status display, spawn/kill buttons, all 454 tests passing |
| 58 | 2026-01-27 | Add worker task duration display: GET /api/workers/with-tasks endpoint returns enriched worker info including current task title, started_at, attempts; WorkerWithTask/CurrentTaskInfo TypeScript types; listWorkersWithTasks API client; WorkersPage shows task title and live elapsed time with auto-updating timer; CSS styling for current-task-info section; 3 new tests, total 457 tests passing |
| 59 | 2026-01-27 | Implement HistoryContextStage with RLM integration: completed the TODO in stages.py to wire HistoryContextStage to RLMSummarizer, provides compressed conversation history as worker context; removed stale TODO comment from pipeline.py; 5 new tests, total 462 tests passing |
| 60 | 2026-01-27 | Add worker health monitoring API: GET /api/workers/{id}/health endpoint exposing liveness status, degradation signals, and recovery recommendations from WorkerMonitor; 5 new tests, total 467 tests passing |
| 61 | 2026-01-27 | Add LogsContextStage for debugging task context: per docs/04-context-enrichment.md section 6, enrichment pipeline now includes relevant logs for debugging-related tasks; keyword-based task detection (error, bug, fix, crash, etc.); fetches task-specific logs and project-level error/critical logs from last 24h; includes stack traces and error details; token budgeting with truncation; 14 new tests, total 481 tests passing |
| 62 | 2026-01-27 | Add ResearchContextStage for prior agent outputs: per docs/04-context-enrichment.md section 2, enrichment pipeline now includes related completed task summaries; keyword-based relevance scoring with Jaccard similarity; queries session_metrics for output_summary from completed tasks; falls back to task description; token budgeting with truncation; 8-layer pipeline (task, project, code, deployment, history, logs, research, refinement); 17 new tests, total 498 tests passing |
| 63 | 2026-01-27 | Add DocumentationContextStage for project documentation: per docs/04-context-enrichment.md section 3, enrichment pipeline now includes README, coding conventions, ADRs (filtered by relevance), API specs (for API tasks), and architecture docs; keyword-based ADR filtering; 9-layer pipeline; 19 new tests, total 517 tests passing |
| 64 | 2026-01-27 | Add Context Assembly observability: ContextAssemblyLog domain model, migration 010, ContextAssemblyLogRepository with CRUD and stats queries, EnrichmentPipeline logs assembly metrics (timing, tokens, stages), /api/enricher routes for logs/stats/budget-alerts, cleanup endpoint; enables debugging and analysis of enrichment pipeline per docs/04-context-enrichment.md; 22 new tests, total 539 tests passing |
| 65 | 2026-01-27 | Code cleanup: fix linting errors in test_documentation_context.py (remove unused tempfile import and unused variable), remove stale TODO comment from enricher pipeline (code context already implemented via CodeContextExtractor); all 539 tests passing |
| 66 | 2026-01-27 | Make worktree base branch configurable per project: uses project.settings.get("base_branch", "main") allowing projects to specify their default branch (e.g., "master", "develop"); all 539 tests passing |
| 67 | 2026-01-27 | Add model routing based on task complexity: deterministic heuristics for complexity estimation (file count, keywords, task type, priority), TaskComplexity/ModelTier enums, select_model_for_task(), GET /api/tasks/{id}/routing endpoint with worker_type param; per docs/08-open-architecture.md section 11; 38 new tests, total 577 tests passing |
| 68 | 2026-01-27 | Add Reasoning Bank for reflexion-based learning: TaskOutcome model, task_outcomes table (migration 011), ReasoningBankRepository with find_similar() using Jaccard similarity, select_model_with_learning() blending static heuristics with learned experience, executor integration via _record_outcome(), API endpoints for outcomes/model-stats/find-similar; per docs/08-open-architecture.md Reflexion-Based Learning; 25 new tests, total 602 tests passing |
| 69 | 2026-01-27 | Wire model routing into executor: execute_task() now calls select_model_for_task() and get_model_for_worker_type() to select appropriate model based on task complexity, passes selected model to SessionConfig, tracks actual model used (e.g., "claude-sonnet-4-20250514") in TaskOutcome instead of just worker type; enables accurate learning from model performance; all 602 tests passing |
| 70 | 2026-01-27 | Add task validation stage: TaskValidator class with auto-detection of test/lint commands for Python, Node.js, Rust, Go; ValidationResult with check status (passed/failed/skipped/error); sensitive pattern detection triggers human review; POST /api/tasks/{id}/validate, /approve, /reject endpoints; transitions tasks from REVIEW to DONE or back to IN_PROGRESS; per docs/08-open-architecture.md section 3; 23 new tests, total 625 tests passing |

## Blockers

None - ready for feature expansion.
