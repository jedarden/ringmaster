//! Attempt domain model - represents a loop iteration

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Status of an attempt
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttemptStatus {
    Running,
    Completed,
    Failed,
    Cancelled,
}

impl std::fmt::Display for AttemptStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AttemptStatus::Running => write!(f, "running"),
            AttemptStatus::Completed => write!(f, "completed"),
            AttemptStatus::Failed => write!(f, "failed"),
            AttemptStatus::Cancelled => write!(f, "cancelled"),
        }
    }
}

impl std::str::FromStr for AttemptStatus {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "running" => Ok(AttemptStatus::Running),
            "completed" => Ok(AttemptStatus::Completed),
            "failed" => Ok(AttemptStatus::Failed),
            "cancelled" => Ok(AttemptStatus::Cancelled),
            _ => Err(format!("Unknown attempt status: {}", s)),
        }
    }
}

/// An attempt represents a single loop iteration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Attempt {
    pub id: Uuid,
    pub card_id: Uuid,
    pub attempt_number: i32,
    pub agent_type: String,
    pub status: AttemptStatus,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<i64>,
    pub tokens_used: Option<i32>,
    pub cost_usd: Option<f64>,
    pub output: Option<String>,
    pub error_message: Option<String>,
    pub commit_sha: Option<String>,
    pub diff_stats: Option<DiffStats>,
}

impl Attempt {
    pub fn new(card_id: Uuid, attempt_number: i32) -> Self {
        Self {
            id: Uuid::new_v4(),
            card_id,
            attempt_number,
            agent_type: "claude-opus-4".to_string(),
            status: AttemptStatus::Running,
            started_at: Utc::now(),
            completed_at: None,
            duration_ms: None,
            tokens_used: None,
            cost_usd: None,
            output: None,
            error_message: None,
            commit_sha: None,
            diff_stats: None,
        }
    }
}

/// Git diff statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiffStats {
    pub files_changed: i32,
    pub insertions: i32,
    pub deletions: i32,
}

/// Loop snapshot for checkpointing
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopSnapshot {
    pub id: Uuid,
    pub card_id: Uuid,
    pub iteration: i32,
    pub state: serde_json::Value,
    pub checkpoint_commit: Option<String>,
    pub created_at: DateTime<Utc>,
}

impl LoopSnapshot {
    pub fn new(card_id: Uuid, iteration: i32, state: serde_json::Value) -> Self {
        Self {
            id: Uuid::new_v4(),
            card_id,
            iteration,
            state,
            checkpoint_commit: None,
            created_at: Utc::now(),
        }
    }
}

/// Deployment tracking
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Deployment {
    pub id: Uuid,
    pub card_id: Uuid,
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
    pub build_started_at: Option<DateTime<Utc>>,
    pub build_completed_at: Option<DateTime<Utc>>,
    pub deploy_started_at: Option<DateTime<Utc>>,
    pub deploy_completed_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Deployment {
    pub fn new(card_id: Uuid) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            card_id,
            build_id: None,
            image_tag: None,
            image_digest: None,
            workflow_run_id: None,
            workflow_status: None,
            workflow_conclusion: None,
            argocd_app_name: None,
            argocd_sync_status: None,
            argocd_health_status: None,
            argocd_revision: None,
            namespace: None,
            deployment_name: None,
            replicas_desired: None,
            replicas_ready: None,
            build_started_at: None,
            build_completed_at: None,
            deploy_started_at: None,
            deploy_completed_at: None,
            created_at: now,
            updated_at: now,
        }
    }
}

/// State transition record for audit
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StateTransition {
    pub id: Uuid,
    pub card_id: Uuid,
    pub from_state: String,
    pub to_state: String,
    pub trigger: String,
    pub metadata: Option<serde_json::Value>,
    pub created_at: DateTime<Utc>,
}
