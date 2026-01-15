-- Ringmaster Initial Schema
-- Enable foreign keys and WAL mode
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-------------------------------------------------------------------------------
-- PROJECTS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    repository_url TEXT NOT NULL,
    repository_path TEXT,
    tech_stack TEXT DEFAULT '[]',
    coding_conventions TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

-------------------------------------------------------------------------------
-- CARDS TABLE (Main entity)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY NOT NULL,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    task_prompt TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft'
        CHECK (state IN (
            'draft', 'planning', 'coding', 'code_review', 'testing',
            'build_queue', 'building', 'build_success', 'build_failed',
            'deploy_queue', 'deploying', 'verifying',
            'completed', 'error_fixing', 'archived', 'failed'
        )),
    previous_state TEXT,
    state_changed_at TEXT,
    loop_iteration INTEGER DEFAULT 0,
    total_time_spent_ms INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    error_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    worktree_path TEXT,
    branch_name TEXT,
    pull_request_url TEXT,
    deployment_namespace TEXT,
    deployment_name TEXT,
    argocd_app_name TEXT,
    labels TEXT DEFAULT '[]',
    priority INTEGER DEFAULT 0,
    deadline TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cards_project ON cards(project_id);
CREATE INDEX IF NOT EXISTS idx_cards_state ON cards(state);
CREATE INDEX IF NOT EXISTS idx_cards_updated ON cards(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cards_priority ON cards(priority DESC);

-------------------------------------------------------------------------------
-- ACCEPTANCE CRITERIA TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acceptance_criteria (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    met INTEGER DEFAULT 0,
    met_at TEXT,
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_acceptance_criteria_card ON acceptance_criteria(card_id);

-------------------------------------------------------------------------------
-- CARD DEPENDENCIES TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS card_dependencies (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    depends_on_card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    dependency_type TEXT DEFAULT 'blocks'
        CHECK (dependency_type IN ('blocks', 'relates_to', 'duplicates')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (card_id != depends_on_card_id),
    UNIQUE (card_id, depends_on_card_id)
);

CREATE INDEX IF NOT EXISTS idx_card_deps_card ON card_dependencies(card_id);
CREATE INDEX IF NOT EXISTS idx_card_deps_depends_on ON card_dependencies(depends_on_card_id);

-------------------------------------------------------------------------------
-- ATTEMPTS TABLE (Loop iterations / agent runs)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    agent_type TEXT NOT NULL DEFAULT 'claude-opus-4',
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    duration_ms INTEGER,
    tokens_used INTEGER,
    cost_usd REAL,
    output TEXT,
    error_message TEXT,
    commit_sha TEXT,
    diff_stats TEXT,
    UNIQUE (card_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_attempts_card ON attempts(card_id);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON attempts(status);
CREATE INDEX IF NOT EXISTS idx_attempts_started ON attempts(started_at DESC);

-------------------------------------------------------------------------------
-- ERRORS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS errors (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    context TEXT,
    category TEXT CHECK (category IN ('build', 'test', 'deploy', 'runtime', 'other')),
    severity TEXT DEFAULT 'error' CHECK (severity IN ('error', 'warning', 'info')),
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    resolution_attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_errors_card ON errors(card_id);
CREATE INDEX IF NOT EXISTS idx_errors_resolved ON errors(resolved);
CREATE INDEX IF NOT EXISTS idx_errors_category ON errors(category);

-------------------------------------------------------------------------------
-- LOOP SNAPSHOTS TABLE (Checkpoints for recovery)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loop_snapshots (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    iteration INTEGER NOT NULL,
    state TEXT NOT NULL,
    checkpoint_commit TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_loop_snapshots_card ON loop_snapshots(card_id);
CREATE INDEX IF NOT EXISTS idx_loop_snapshots_iteration ON loop_snapshots(card_id, iteration);

-------------------------------------------------------------------------------
-- DEPLOYMENTS TABLE (Build and deploy tracking)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deployments (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    build_id TEXT,
    image_tag TEXT,
    image_digest TEXT,
    workflow_run_id INTEGER,
    workflow_status TEXT,
    workflow_conclusion TEXT,
    argocd_app_name TEXT,
    argocd_sync_status TEXT,
    argocd_health_status TEXT,
    argocd_revision INTEGER,
    namespace TEXT,
    deployment_name TEXT,
    replicas_desired INTEGER,
    replicas_ready INTEGER,
    build_started_at TEXT,
    build_completed_at TEXT,
    deploy_started_at TEXT,
    deploy_completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_deployments_card ON deployments(card_id);
CREATE INDEX IF NOT EXISTS idx_deployments_workflow ON deployments(workflow_run_id);

-------------------------------------------------------------------------------
-- STATE TRANSITIONS TABLE (Audit log)
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS state_transitions (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_state_trans_card ON state_transitions(card_id);
CREATE INDEX IF NOT EXISTS idx_state_trans_created ON state_transitions(created_at DESC);

-------------------------------------------------------------------------------
-- PROMPT METRICS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompt_metrics (
    id TEXT PRIMARY KEY NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    attempt_id TEXT REFERENCES attempts(id) ON DELETE SET NULL,
    layer_name TEXT NOT NULL,
    tokens_added INTEGER NOT NULL,
    processing_time_ms INTEGER NOT NULL,
    content_hash TEXT,
    cache_hit INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prompt_metrics_card ON prompt_metrics(card_id);
CREATE INDEX IF NOT EXISTS idx_prompt_metrics_layer ON prompt_metrics(layer_name);

-------------------------------------------------------------------------------
-- WEBSOCKET SUBSCRIPTIONS TABLE
-------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS websocket_subscriptions (
    id TEXT PRIMARY KEY NOT NULL,
    connection_id TEXT NOT NULL UNIQUE,
    user_id TEXT,
    card_ids TEXT DEFAULT '[]',
    project_ids TEXT DEFAULT '[]',
    connected_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_heartbeat TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ws_subs_connection ON websocket_subscriptions(connection_id);
CREATE INDEX IF NOT EXISTS idx_ws_subs_heartbeat ON websocket_subscriptions(last_heartbeat);
