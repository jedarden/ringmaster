//! Database row models for SQLx

use sqlx::FromRow;

/// Project row from database
#[derive(Debug, Clone, FromRow)]
pub struct ProjectRow {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub repository_url: String,
    pub repository_path: Option<String>,
    pub tech_stack: String, // JSON array
    pub coding_conventions: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

/// Card row from database
#[derive(Debug, Clone, FromRow)]
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
    pub labels: String, // JSON array
    pub priority: i32,
    pub deadline: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

/// Acceptance criteria row from database
#[derive(Debug, Clone, FromRow)]
pub struct AcceptanceCriteriaRow {
    pub id: String,
    pub card_id: String,
    pub description: String,
    pub met: i32, // Boolean as integer
    pub met_at: Option<String>,
    pub order_index: i32,
    pub created_at: String,
}

/// Card dependency row from database
#[derive(Debug, Clone, FromRow)]
pub struct CardDependencyRow {
    pub id: String,
    pub card_id: String,
    pub depends_on_card_id: String,
    pub dependency_type: String,
    pub created_at: String,
}

/// Attempt row from database
#[derive(Debug, Clone, FromRow)]
pub struct AttemptRow {
    pub id: String,
    pub card_id: String,
    pub attempt_number: i32,
    pub agent_type: String,
    pub status: String,
    pub started_at: String,
    pub completed_at: Option<String>,
    pub duration_ms: Option<i64>,
    pub tokens_used: Option<i32>,
    pub cost_usd: Option<f64>,
    pub output: Option<String>,
    pub error_message: Option<String>,
    pub commit_sha: Option<String>,
    pub diff_stats: Option<String>, // JSON
}

/// Error row from database
#[derive(Debug, Clone, FromRow)]
pub struct ErrorRow {
    pub id: String,
    pub card_id: String,
    pub attempt_id: Option<String>,
    pub error_type: String,
    pub message: String,
    pub stack_trace: Option<String>,
    pub context: Option<String>, // JSON
    pub category: Option<String>,
    pub severity: String,
    pub resolved: i32, // Boolean as integer
    pub resolved_at: Option<String>,
    pub resolution_attempt_id: Option<String>,
    pub created_at: String,
}

/// Loop snapshot row from database
#[derive(Debug, Clone, FromRow)]
pub struct LoopSnapshotRow {
    pub id: String,
    pub card_id: String,
    pub iteration: i32,
    pub state: String, // JSON
    pub checkpoint_commit: Option<String>,
    pub created_at: String,
}

/// Deployment row from database
#[derive(Debug, Clone, FromRow)]
pub struct DeploymentRow {
    pub id: String,
    pub card_id: String,
    pub build_id: Option<String>,
    pub image_tag: Option<String>,
    pub image_digest: Option<String>,
    pub workflow_run_id: Option<i64>,
    pub workflow_status: Option<String>,
    pub workflow_conclusion: Option<String>,
    pub argocd_app_name: Option<String>,
    pub argocd_sync_status: Option<String>,
    pub argocd_health_status: Option<String>,
    pub argocd_revision: Option<i32>,
    pub namespace: Option<String>,
    pub deployment_name: Option<String>,
    pub replicas_desired: Option<i32>,
    pub replicas_ready: Option<i32>,
    pub build_started_at: Option<String>,
    pub build_completed_at: Option<String>,
    pub deploy_started_at: Option<String>,
    pub deploy_completed_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

/// State transition row from database
#[derive(Debug, Clone, FromRow)]
pub struct StateTransitionRow {
    pub id: String,
    pub card_id: String,
    pub from_state: String,
    pub to_state: String,
    pub trigger: String,
    pub metadata: Option<String>, // JSON
    pub created_at: String,
}

/// Prompt metric row from database
#[derive(Debug, Clone, FromRow)]
pub struct PromptMetricRow {
    pub id: String,
    pub card_id: String,
    pub attempt_id: Option<String>,
    pub layer_name: String,
    pub tokens_added: i32,
    pub processing_time_ms: i32,
    pub content_hash: Option<String>,
    pub cache_hit: i32, // Boolean as integer
    pub created_at: String,
}

/// Project with stats row (for aggregate queries)
#[derive(Debug, Clone, FromRow)]
pub struct ProjectWithStatsRow {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub repository_url: String,
    pub repository_path: Option<String>,
    pub tech_stack: String,
    pub coding_conventions: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub card_count: i64,
    pub active_loops: i64,
    pub total_cost: f64,
}
