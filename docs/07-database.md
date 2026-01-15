# Database Schema

## Overview

Ringmaster uses SQLite for local persistence with sqlx for compile-time query verification. The schema supports the complete SDLC lifecycle tracking, loop execution history, and integration monitoring.

## Entity Relationship Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           ENTITY RELATIONSHIP DIAGRAM                                 │
└──────────────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
    │    PROJECTS     │          │     CARDS       │          │    ATTEMPTS     │
    ├─────────────────┤          ├─────────────────┤          ├─────────────────┤
    │ id (PK)         │◄────────┐│ id (PK)         │◄────────┐│ id (PK)         │
    │ name            │         ││ project_id (FK) │─────────┘│ card_id (FK)    │─┐
    │ description     │         ││ title           │          │ attempt_number  │ │
    │ repository_url  │         ││ description     │          │ agent_type      │ │
    │ repository_path │         ││ task_prompt     │          │ status          │ │
    │ tech_stack      │         ││ state           │          │ output          │ │
    │ coding_convent. │         ││ previous_state  │          │ tokens_used     │ │
    │ created_at      │         ││ loop_iteration  │          │ cost_usd        │ │
    │ updated_at      │         ││ total_cost_usd  │          │ commit_sha      │ │
    └─────────────────┘         ││ worktree_path   │          │ started_at      │ │
                                ││ branch_name     │          │ completed_at    │ │
                                ││ labels          │          └─────────────────┘ │
                                ││ ...             │                              │
                                │└─────────────────┘                              │
                                │         │                                       │
                                │         │                                       │
    ┌─────────────────┐         │         │          ┌─────────────────┐          │
    │ ACCEPTANCE_     │         │         │          │     ERRORS      │          │
    │ CRITERIA        │         │         │          ├─────────────────┤          │
    ├─────────────────┤         │         │          │ id (PK)         │          │
    │ id (PK)         │         │         └─────────▶│ card_id (FK)    │──────────┘
    │ card_id (FK)    │─────────┘                    │ attempt_id (FK) │◄─────────┘
    │ description     │                              │ error_type      │
    │ met             │                              │ message         │
    │ met_at          │                              │ stack_trace     │
    │ order_index     │                              │ context         │
    └─────────────────┘                              │ category        │
                                                     │ resolved        │
                                                     │ resolved_at     │
    ┌─────────────────┐          ┌─────────────────┐ └─────────────────┘
    │ CARD_           │          │ LOOP_SNAPSHOTS  │
    │ DEPENDENCIES    │          ├─────────────────┤
    ├─────────────────┤          │ id (PK)         │
    │ id (PK)         │          │ card_id (FK)    │──────────────────────────────┐
    │ card_id (FK)    │──────────│ iteration       │                              │
    │ depends_on (FK) │──────────│ state (JSON)    │                              │
    │ dependency_type │          │ checkpoint_sha  │                              │
    └─────────────────┘          │ created_at      │                              │
                                 └─────────────────┘                              │
                                                                                  │
    ┌─────────────────┐          ┌─────────────────┐                              │
    │   DEPLOYMENTS   │          │ PROMPT_METRICS  │                              │
    ├─────────────────┤          ├─────────────────┤                              │
    │ id (PK)         │          │ id (PK)         │                              │
    │ card_id (FK)    │──────────│ card_id (FK)    │──────────────────────────────┤
    │ build_id        │          │ attempt_id (FK) │                              │
    │ image_tag       │          │ layer_name      │                              │
    │ workflow_run_id │          │ tokens_added    │                              │
    │ argocd_app_name │          │ processing_ms   │                              │
    │ sync_status     │          │ cache_hit       │                              │
    │ health_status   │          │ created_at      │                              │
    │ ...             │          └─────────────────┘                              │
    └─────────────────┘                                                           │
                                                                                  │
    ┌─────────────────┐          ┌─────────────────┐                              │
    │ STATE_          │          │ WEBSOCKET_      │                              │
    │ TRANSITIONS     │          │ SUBSCRIPTIONS   │                              │
    ├─────────────────┤          ├─────────────────┤                              │
    │ id (PK)         │          │ id (PK)         │                              │
    │ card_id (FK)    │──────────│ connection_id   │                              │
    │ from_state      │          │ card_ids        │──────────────────────────────┘
    │ to_state        │          │ project_ids     │
    │ trigger         │          │ connected_at    │
    │ created_at      │          │ last_heartbeat  │
    └─────────────────┘          └─────────────────┘
```

## Complete Schema

```sql
-- File: migrations/001_initial_schema.sql

-- Enable foreign keys and WAL mode
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-------------------------------------------------------------------------------
-- PROJECTS TABLE
-------------------------------------------------------------------------------
CREATE TABLE projects (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    description TEXT,
    repository_url TEXT NOT NULL,
    repository_path TEXT,

    -- Technology and conventions
    tech_stack TEXT DEFAULT '[]',  -- JSON array
    coding_conventions TEXT,

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_projects_name ON projects(name);

-------------------------------------------------------------------------------
-- CARDS TABLE (Main entity)
-------------------------------------------------------------------------------
CREATE TABLE cards (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Basic info
    title TEXT NOT NULL,
    description TEXT,
    task_prompt TEXT NOT NULL,

    -- State machine
    state TEXT NOT NULL DEFAULT 'draft'
        CHECK (state IN (
            'draft', 'planning', 'coding', 'code_review', 'testing',
            'build_queue', 'building', 'build_success', 'build_failed',
            'deploy_queue', 'deploying', 'verifying',
            'completed', 'error_fixing', 'archived', 'failed'
        )),
    previous_state TEXT,
    state_changed_at TEXT,

    -- Loop tracking
    loop_iteration INTEGER DEFAULT 0,
    total_time_spent_ms INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,

    -- Error tracking
    error_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,

    -- Git integration
    worktree_path TEXT,
    branch_name TEXT,
    pull_request_url TEXT,

    -- Deployment info
    deployment_namespace TEXT,
    deployment_name TEXT,
    argocd_app_name TEXT,

    -- Metadata
    labels TEXT DEFAULT '[]',  -- JSON array
    priority INTEGER DEFAULT 0,
    deadline TEXT,

    -- Timestamps
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_cards_project ON cards(project_id);
CREATE INDEX idx_cards_state ON cards(state);
CREATE INDEX idx_cards_updated ON cards(updated_at DESC);
CREATE INDEX idx_cards_priority ON cards(priority DESC);

-- Trigger to update updated_at
CREATE TRIGGER cards_updated_at
AFTER UPDATE ON cards
BEGIN
    UPDATE cards SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-------------------------------------------------------------------------------
-- ACCEPTANCE CRITERIA TABLE
-------------------------------------------------------------------------------
CREATE TABLE acceptance_criteria (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    description TEXT NOT NULL,
    met INTEGER DEFAULT 0,  -- Boolean
    met_at TEXT,
    order_index INTEGER NOT NULL DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_acceptance_criteria_card ON acceptance_criteria(card_id);

-------------------------------------------------------------------------------
-- CARD DEPENDENCIES TABLE
-------------------------------------------------------------------------------
CREATE TABLE card_dependencies (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    depends_on_card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    dependency_type TEXT DEFAULT 'blocks'
        CHECK (dependency_type IN ('blocks', 'relates_to', 'duplicates')),

    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    -- Prevent self-dependency
    CHECK (card_id != depends_on_card_id),
    -- Unique constraint
    UNIQUE (card_id, depends_on_card_id)
);

CREATE INDEX idx_card_deps_card ON card_dependencies(card_id);
CREATE INDEX idx_card_deps_depends_on ON card_dependencies(depends_on_card_id);

-------------------------------------------------------------------------------
-- ATTEMPTS TABLE (Loop iterations / agent runs)
-------------------------------------------------------------------------------
CREATE TABLE attempts (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    attempt_number INTEGER NOT NULL,
    agent_type TEXT NOT NULL DEFAULT 'claude-opus-4',

    -- Status
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),

    -- Timing
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    duration_ms INTEGER,

    -- Metrics
    tokens_used INTEGER,
    cost_usd REAL,

    -- Results
    output TEXT,
    error_message TEXT,

    -- Git
    commit_sha TEXT,
    diff_stats TEXT,  -- JSON: {filesChanged, insertions, deletions}

    -- Unique constraint: one attempt number per card
    UNIQUE (card_id, attempt_number)
);

CREATE INDEX idx_attempts_card ON attempts(card_id);
CREATE INDEX idx_attempts_status ON attempts(status);
CREATE INDEX idx_attempts_started ON attempts(started_at DESC);

-------------------------------------------------------------------------------
-- ERRORS TABLE
-------------------------------------------------------------------------------
CREATE TABLE errors (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,

    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    context TEXT,  -- JSON object with additional context

    -- Classification
    category TEXT CHECK (category IN ('build', 'test', 'deploy', 'runtime', 'other')),
    severity TEXT DEFAULT 'error' CHECK (severity IN ('error', 'warning', 'info')),

    -- Resolution tracking
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    resolution_attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_errors_card ON errors(card_id);
CREATE INDEX idx_errors_resolved ON errors(resolved);
CREATE INDEX idx_errors_category ON errors(category);

-------------------------------------------------------------------------------
-- LOOP SNAPSHOTS TABLE (Checkpoints for recovery)
-------------------------------------------------------------------------------
CREATE TABLE loop_snapshots (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    iteration INTEGER NOT NULL,
    state TEXT NOT NULL,  -- JSON serialized loop state
    checkpoint_commit TEXT,  -- Git commit SHA

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_loop_snapshots_card ON loop_snapshots(card_id);
CREATE INDEX idx_loop_snapshots_iteration ON loop_snapshots(card_id, iteration);

-------------------------------------------------------------------------------
-- DEPLOYMENTS TABLE (Build and deploy tracking)
-------------------------------------------------------------------------------
CREATE TABLE deployments (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    -- Build info
    build_id TEXT,
    image_tag TEXT,
    image_digest TEXT,

    -- GitHub Actions
    workflow_run_id INTEGER,
    workflow_status TEXT,
    workflow_conclusion TEXT,

    -- ArgoCD
    argocd_app_name TEXT,
    argocd_sync_status TEXT,
    argocd_health_status TEXT,
    argocd_revision INTEGER,

    -- Kubernetes
    namespace TEXT,
    deployment_name TEXT,
    replicas_desired INTEGER,
    replicas_ready INTEGER,

    -- Timing
    build_started_at TEXT,
    build_completed_at TEXT,
    deploy_started_at TEXT,
    deploy_completed_at TEXT,

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_deployments_card ON deployments(card_id);
CREATE INDEX idx_deployments_workflow ON deployments(workflow_run_id);

-------------------------------------------------------------------------------
-- STATE TRANSITIONS TABLE (Audit log)
-------------------------------------------------------------------------------
CREATE TABLE state_transitions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,

    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger TEXT NOT NULL,
    metadata TEXT,  -- JSON object

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_state_trans_card ON state_transitions(card_id);
CREATE INDEX idx_state_trans_created ON state_transitions(created_at DESC);

-------------------------------------------------------------------------------
-- PROMPT METRICS TABLE
-------------------------------------------------------------------------------
CREATE TABLE prompt_metrics (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,

    layer_name TEXT NOT NULL,
    tokens_added INTEGER NOT NULL,
    processing_time_ms INTEGER NOT NULL,
    content_hash TEXT,
    cache_hit INTEGER DEFAULT 0,

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_prompt_metrics_card ON prompt_metrics(card_id);
CREATE INDEX idx_prompt_metrics_layer ON prompt_metrics(layer_name);

-------------------------------------------------------------------------------
-- WEBSOCKET SUBSCRIPTIONS TABLE
-------------------------------------------------------------------------------
CREATE TABLE websocket_subscriptions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    connection_id TEXT NOT NULL UNIQUE,
    user_id TEXT,

    card_ids TEXT DEFAULT '[]',     -- JSON array
    project_ids TEXT DEFAULT '[]',  -- JSON array

    connected_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_heartbeat TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_ws_subs_connection ON websocket_subscriptions(connection_id);
CREATE INDEX idx_ws_subs_heartbeat ON websocket_subscriptions(last_heartbeat);
```

## Common Queries

### Card Queries

```sql
-- Get card with acceptance criteria
SELECT
    c.*,
    json_group_array(json_object(
        'id', ac.id,
        'description', ac.description,
        'met', ac.met,
        'metAt', ac.met_at,
        'orderIndex', ac.order_index
    )) as acceptance_criteria
FROM cards c
LEFT JOIN acceptance_criteria ac ON ac.card_id = c.id
WHERE c.id = ?
GROUP BY c.id;

-- Get cards by state with pagination
SELECT * FROM cards
WHERE project_id = ?
  AND state IN (?, ?, ?)
ORDER BY priority DESC, updated_at DESC
LIMIT ? OFFSET ?;

-- Get cards with active loops
SELECT c.*, ls.iteration, ls.state as loop_state
FROM cards c
INNER JOIN (
    SELECT card_id, MAX(iteration) as iteration, state
    FROM loop_snapshots
    GROUP BY card_id
) ls ON ls.card_id = c.id
WHERE c.state = 'coding';

-- Search cards
SELECT * FROM cards
WHERE project_id = ?
  AND (title LIKE '%' || ? || '%' OR description LIKE '%' || ? || '%')
ORDER BY updated_at DESC
LIMIT 50;
```

### Attempt Queries

```sql
-- Get attempts for card
SELECT * FROM attempts
WHERE card_id = ?
ORDER BY attempt_number DESC
LIMIT ? OFFSET ?;

-- Get latest successful attempt
SELECT * FROM attempts
WHERE card_id = ?
  AND status = 'completed'
ORDER BY attempt_number DESC
LIMIT 1;

-- Calculate total cost for card
SELECT SUM(cost_usd) as total_cost
FROM attempts
WHERE card_id = ?;

-- Get attempts with errors
SELECT a.*, e.message as error_message, e.category
FROM attempts a
LEFT JOIN errors e ON e.attempt_id = a.id
WHERE a.card_id = ?
  AND a.status = 'failed';
```

### Error Queries

```sql
-- Get unresolved errors for card
SELECT * FROM errors
WHERE card_id = ?
  AND resolved = 0
ORDER BY created_at DESC;

-- Get errors by category
SELECT category, COUNT(*) as count
FROM errors
WHERE card_id = ?
GROUP BY category;

-- Get recent errors across all cards
SELECT e.*, c.title as card_title
FROM errors e
JOIN cards c ON c.id = e.card_id
WHERE e.resolved = 0
ORDER BY e.created_at DESC
LIMIT 20;
```

### Metrics Queries

```sql
-- Token usage by layer
SELECT
    layer_name,
    AVG(tokens_added) as avg_tokens,
    MAX(tokens_added) as max_tokens,
    SUM(tokens_added) as total_tokens
FROM prompt_metrics
WHERE card_id = ?
GROUP BY layer_name;

-- Cache hit rate by layer
SELECT
    layer_name,
    COUNT(*) as total,
    SUM(cache_hit) as hits,
    ROUND(100.0 * SUM(cache_hit) / COUNT(*), 2) as hit_rate_pct
FROM prompt_metrics
GROUP BY layer_name;

-- Processing time trends
SELECT
    date(created_at) as date,
    layer_name,
    AVG(processing_time_ms) as avg_time_ms
FROM prompt_metrics
GROUP BY date(created_at), layer_name
ORDER BY date DESC;

-- Cost by day
SELECT
    date(started_at) as date,
    SUM(cost_usd) as daily_cost,
    COUNT(*) as attempts
FROM attempts
GROUP BY date(started_at)
ORDER BY date DESC;
```

### Dashboard Queries

```sql
-- Cards by state (for Kanban columns)
SELECT state, COUNT(*) as count
FROM cards
WHERE project_id = ?
  AND state != 'archived'
GROUP BY state;

-- Active loops summary
SELECT
    c.id,
    c.title,
    c.loop_iteration,
    c.total_cost_usd,
    c.state
FROM cards c
WHERE c.state IN ('coding', 'error_fixing')
  AND c.project_id = ?;

-- Recent activity
SELECT
    st.created_at,
    st.from_state,
    st.to_state,
    st.trigger,
    c.id as card_id,
    c.title as card_title
FROM state_transitions st
JOIN cards c ON c.id = st.card_id
WHERE c.project_id = ?
ORDER BY st.created_at DESC
LIMIT 20;

-- Project stats
SELECT
    p.id,
    p.name,
    COUNT(DISTINCT c.id) as card_count,
    SUM(CASE WHEN c.state IN ('coding', 'error_fixing') THEN 1 ELSE 0 END) as active_loops,
    SUM(c.total_cost_usd) as total_cost
FROM projects p
LEFT JOIN cards c ON c.project_id = p.id
GROUP BY p.id;
```

## Rust SQLx Integration

```rust
// File: crates/core/src/db/mod.rs

use sqlx::{sqlite::SqlitePoolOptions, SqlitePool};

pub async fn create_pool(database_url: &str) -> Result<SqlitePool, sqlx::Error> {
    let pool = SqlitePoolOptions::new()
        .max_connections(10)
        .connect(database_url)
        .await?;

    // Run migrations
    sqlx::migrate!("./migrations").run(&pool).await?;

    Ok(pool)
}

// File: crates/core/src/db/queries.rs

use sqlx::FromRow;
use uuid::Uuid;

#[derive(Debug, FromRow)]
pub struct CardRow {
    pub id: String,
    pub project_id: String,
    pub title: String,
    pub description: Option<String>,
    pub task_prompt: String,
    pub state: String,
    pub previous_state: Option<String>,
    pub state_changed_at: Option<String>,
    pub loop_iteration: i32,
    pub total_time_spent_ms: i64,
    pub total_cost_usd: f64,
    pub error_count: i32,
    pub max_retries: i32,
    pub worktree_path: Option<String>,
    pub branch_name: Option<String>,
    pub pull_request_url: Option<String>,
    pub deployment_namespace: Option<String>,
    pub deployment_name: Option<String>,
    pub argocd_app_name: Option<String>,
    pub labels: String,  // JSON
    pub priority: i32,
    pub deadline: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

impl CardRow {
    pub fn to_card(&self) -> Card {
        Card {
            id: Uuid::parse_str(&self.id).unwrap(),
            project_id: Uuid::parse_str(&self.project_id).unwrap(),
            title: self.title.clone(),
            state: CardState::from_str(&self.state).unwrap(),
            labels: serde_json::from_str(&self.labels).unwrap_or_default(),
            // ... map other fields
        }
    }
}

// Compile-time verified queries
pub async fn get_card(pool: &SqlitePool, card_id: &str) -> Result<Option<CardRow>, sqlx::Error> {
    sqlx::query_as!(
        CardRow,
        r#"
        SELECT * FROM cards WHERE id = ?
        "#,
        card_id
    )
    .fetch_optional(pool)
    .await
}

pub async fn create_card(pool: &SqlitePool, card: &NewCard) -> Result<String, sqlx::Error> {
    let id = Uuid::new_v4().to_string();
    let labels_json = serde_json::to_string(&card.labels)?;

    sqlx::query!(
        r#"
        INSERT INTO cards (id, project_id, title, description, task_prompt, labels, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        "#,
        id,
        card.project_id,
        card.title,
        card.description,
        card.task_prompt,
        labels_json,
        card.priority
    )
    .execute(pool)
    .await?;

    Ok(id)
}

pub async fn update_card_state(
    pool: &SqlitePool,
    card_id: &str,
    new_state: &str,
    previous_state: &str,
    trigger: &str,
) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;

    // Update card
    sqlx::query!(
        r#"
        UPDATE cards
        SET state = ?, previous_state = ?, state_changed_at = datetime('now')
        WHERE id = ?
        "#,
        new_state,
        previous_state,
        card_id
    )
    .execute(&mut *tx)
    .await?;

    // Record transition
    let trans_id = Uuid::new_v4().to_string();
    sqlx::query!(
        r#"
        INSERT INTO state_transitions (id, card_id, from_state, to_state, trigger)
        VALUES (?, ?, ?, ?, ?)
        "#,
        trans_id,
        card_id,
        previous_state,
        new_state,
        trigger
    )
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    Ok(())
}

pub async fn create_attempt(pool: &SqlitePool, attempt: &NewAttempt) -> Result<String, sqlx::Error> {
    let id = Uuid::new_v4().to_string();

    sqlx::query!(
        r#"
        INSERT INTO attempts (id, card_id, attempt_number, agent_type, status)
        VALUES (?, ?, ?, ?, 'running')
        "#,
        id,
        attempt.card_id,
        attempt.attempt_number,
        attempt.agent_type
    )
    .execute(pool)
    .await?;

    Ok(id)
}

pub async fn complete_attempt(
    pool: &SqlitePool,
    attempt_id: &str,
    output: &str,
    tokens_used: i32,
    cost_usd: f64,
    commit_sha: Option<&str>,
) -> Result<(), sqlx::Error> {
    sqlx::query!(
        r#"
        UPDATE attempts
        SET status = 'completed',
            completed_at = datetime('now'),
            duration_ms = (strftime('%s', datetime('now')) - strftime('%s', started_at)) * 1000,
            output = ?,
            tokens_used = ?,
            cost_usd = ?,
            commit_sha = ?
        WHERE id = ?
        "#,
        output,
        tokens_used,
        cost_usd,
        commit_sha,
        attempt_id
    )
    .execute(pool)
    .await?;

    Ok(())
}
```

## Data Retention

```sql
-- Archive old completed cards (run periodically)
UPDATE cards
SET state = 'archived'
WHERE state = 'completed'
  AND updated_at < datetime('now', '-30 days');

-- Clean up old loop snapshots (keep last 10 per card)
DELETE FROM loop_snapshots
WHERE id NOT IN (
    SELECT id FROM loop_snapshots ls2
    WHERE ls2.card_id = loop_snapshots.card_id
    ORDER BY iteration DESC
    LIMIT 10
);

-- Clean up old prompt metrics (older than 7 days)
DELETE FROM prompt_metrics
WHERE created_at < datetime('now', '-7 days');

-- Clean up stale WebSocket subscriptions
DELETE FROM websocket_subscriptions
WHERE last_heartbeat < datetime('now', '-5 minutes');
```

## Backup and Recovery

```bash
# Backup database
sqlite3 ~/.ringmaster/data.db ".backup ~/.ringmaster/backup-$(date +%Y%m%d).db"

# Export to SQL
sqlite3 ~/.ringmaster/data.db .dump > backup.sql

# Restore from backup
cp ~/.ringmaster/backup-20240115.db ~/.ringmaster/data.db

# Vacuum to reclaim space
sqlite3 ~/.ringmaster/data.db "VACUUM;"
```
