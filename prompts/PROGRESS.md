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
- ✅ 5-layer prompt assembly pipeline
- ✅ Stage-based architecture
- ✅ Context hash for deduplication
- ✅ RLM summarization with hierarchical compression
- ✅ Code context extraction with intelligent file selection

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

## Blockers

None - ready for feature expansion.
