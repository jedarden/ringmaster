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

#[cfg(test)]
mod tests {
    use super::*;

    // AttemptStatus tests
    #[test]
    fn test_attempt_status_display() {
        assert_eq!(AttemptStatus::Running.to_string(), "running");
        assert_eq!(AttemptStatus::Completed.to_string(), "completed");
        assert_eq!(AttemptStatus::Failed.to_string(), "failed");
        assert_eq!(AttemptStatus::Cancelled.to_string(), "cancelled");
    }

    #[test]
    fn test_attempt_status_from_str() {
        assert_eq!("running".parse::<AttemptStatus>().unwrap(), AttemptStatus::Running);
        assert_eq!("completed".parse::<AttemptStatus>().unwrap(), AttemptStatus::Completed);
        assert_eq!("failed".parse::<AttemptStatus>().unwrap(), AttemptStatus::Failed);
        assert_eq!("cancelled".parse::<AttemptStatus>().unwrap(), AttemptStatus::Cancelled);
    }

    #[test]
    fn test_attempt_status_from_str_invalid() {
        let result = "invalid".parse::<AttemptStatus>();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Unknown attempt status"));
    }

    #[test]
    fn test_attempt_status_serialization() {
        let json = serde_json::to_string(&AttemptStatus::Running).unwrap();
        assert_eq!(json, "\"running\"");

        let deserialized: AttemptStatus = serde_json::from_str("\"failed\"").unwrap();
        assert_eq!(deserialized, AttemptStatus::Failed);
    }

    // Attempt tests
    #[test]
    fn test_attempt_new() {
        let card_id = Uuid::new_v4();
        let attempt = Attempt::new(card_id, 1);

        assert_eq!(attempt.card_id, card_id);
        assert_eq!(attempt.attempt_number, 1);
        assert_eq!(attempt.agent_type, "claude-opus-4");
        assert_eq!(attempt.status, AttemptStatus::Running);
        assert!(attempt.completed_at.is_none());
        assert!(attempt.duration_ms.is_none());
        assert!(attempt.tokens_used.is_none());
        assert!(attempt.cost_usd.is_none());
        assert!(attempt.output.is_none());
        assert!(attempt.error_message.is_none());
        assert!(attempt.commit_sha.is_none());
        assert!(attempt.diff_stats.is_none());
    }

    #[test]
    fn test_attempt_serialization_camel_case() {
        let attempt = Attempt::new(Uuid::new_v4(), 1);
        let json = serde_json::to_string(&attempt).unwrap();

        // Verify camelCase serialization
        assert!(json.contains("\"cardId\""));
        assert!(json.contains("\"attemptNumber\""));
        assert!(json.contains("\"agentType\""));
        assert!(json.contains("\"startedAt\""));
        assert!(json.contains("\"completedAt\""));
        assert!(json.contains("\"durationMs\""));
        assert!(json.contains("\"tokensUsed\""));
        assert!(json.contains("\"costUsd\""));
        assert!(json.contains("\"errorMessage\""));
        assert!(json.contains("\"commitSha\""));
        assert!(json.contains("\"diffStats\""));

        // Should not contain snake_case
        assert!(!json.contains("\"card_id\""));
        assert!(!json.contains("\"attempt_number\""));
    }

    // DiffStats tests
    #[test]
    fn test_diff_stats_serialization() {
        let stats = DiffStats {
            files_changed: 5,
            insertions: 100,
            deletions: 25,
        };

        let json = serde_json::to_string(&stats).unwrap();

        assert!(json.contains("\"filesChanged\":5"));
        assert!(json.contains("\"insertions\":100"));
        assert!(json.contains("\"deletions\":25"));
    }

    #[test]
    fn test_diff_stats_deserialization() {
        let json = r#"{"filesChanged": 3, "insertions": 50, "deletions": 10}"#;
        let stats: DiffStats = serde_json::from_str(json).unwrap();

        assert_eq!(stats.files_changed, 3);
        assert_eq!(stats.insertions, 50);
        assert_eq!(stats.deletions, 10);
    }

    // LoopSnapshot tests
    #[test]
    fn test_loop_snapshot_new() {
        let card_id = Uuid::new_v4();
        let state = serde_json::json!({"key": "value", "count": 42});
        let snapshot = LoopSnapshot::new(card_id, 5, state.clone());

        assert_eq!(snapshot.card_id, card_id);
        assert_eq!(snapshot.iteration, 5);
        assert_eq!(snapshot.state, state);
        assert!(snapshot.checkpoint_commit.is_none());
    }

    #[test]
    fn test_loop_snapshot_serialization() {
        let snapshot = LoopSnapshot::new(Uuid::new_v4(), 3, serde_json::json!({}));
        let json = serde_json::to_string(&snapshot).unwrap();

        assert!(json.contains("\"cardId\""));
        assert!(json.contains("\"checkpointCommit\""));
        assert!(json.contains("\"createdAt\""));
    }

    // Deployment tests
    #[test]
    fn test_deployment_new() {
        let card_id = Uuid::new_v4();
        let deployment = Deployment::new(card_id);

        assert_eq!(deployment.card_id, card_id);
        assert!(deployment.build_id.is_none());
        assert!(deployment.image_tag.is_none());
        assert!(deployment.image_digest.is_none());
        assert!(deployment.workflow_run_id.is_none());
        assert!(deployment.workflow_status.is_none());
        assert!(deployment.workflow_conclusion.is_none());
        assert!(deployment.argocd_app_name.is_none());
        assert!(deployment.argocd_sync_status.is_none());
        assert!(deployment.argocd_health_status.is_none());
        assert!(deployment.argocd_revision.is_none());
        assert!(deployment.namespace.is_none());
        assert!(deployment.deployment_name.is_none());
        assert!(deployment.replicas_desired.is_none());
        assert!(deployment.replicas_ready.is_none());
        assert!(deployment.build_started_at.is_none());
        assert!(deployment.build_completed_at.is_none());
        assert!(deployment.deploy_started_at.is_none());
        assert!(deployment.deploy_completed_at.is_none());
    }

    #[test]
    fn test_deployment_serialization() {
        let deployment = Deployment::new(Uuid::new_v4());
        let json = serde_json::to_string(&deployment).unwrap();

        // Verify camelCase serialization for key fields
        assert!(json.contains("\"cardId\""));
        assert!(json.contains("\"buildId\""));
        assert!(json.contains("\"imageTag\""));
        assert!(json.contains("\"imageDigest\""));
        assert!(json.contains("\"workflowRunId\""));
        assert!(json.contains("\"workflowStatus\""));
        assert!(json.contains("\"workflowConclusion\""));
        assert!(json.contains("\"argocdAppName\""));
        assert!(json.contains("\"argocdSyncStatus\""));
        assert!(json.contains("\"argocdHealthStatus\""));
        assert!(json.contains("\"argocdRevision\""));
        assert!(json.contains("\"deploymentName\""));
        assert!(json.contains("\"replicasDesired\""));
        assert!(json.contains("\"replicasReady\""));
        assert!(json.contains("\"buildStartedAt\""));
        assert!(json.contains("\"buildCompletedAt\""));
        assert!(json.contains("\"deployStartedAt\""));
        assert!(json.contains("\"deployCompletedAt\""));
        assert!(json.contains("\"createdAt\""));
        assert!(json.contains("\"updatedAt\""));
    }

    #[test]
    fn test_deployment_deserialization() {
        let json = r#"{
            "id": "00000000-0000-0000-0000-000000000001",
            "cardId": "00000000-0000-0000-0000-000000000002",
            "buildId": "build-123",
            "imageTag": "v1.0.0",
            "imageDigest": "sha256:abc123",
            "workflowRunId": 12345,
            "workflowStatus": "completed",
            "workflowConclusion": "success",
            "argocdAppName": "my-app",
            "argocdSyncStatus": "Synced",
            "argocdHealthStatus": "Healthy",
            "argocdRevision": 5,
            "namespace": "production",
            "deploymentName": "my-deployment",
            "replicasDesired": 3,
            "replicasReady": 3,
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z"
        }"#;

        let deployment: Deployment = serde_json::from_str(json).unwrap();

        assert_eq!(deployment.build_id, Some("build-123".to_string()));
        assert_eq!(deployment.image_tag, Some("v1.0.0".to_string()));
        assert_eq!(deployment.image_digest, Some("sha256:abc123".to_string()));
        assert_eq!(deployment.workflow_run_id, Some(12345));
        assert_eq!(deployment.workflow_status, Some("completed".to_string()));
        assert_eq!(deployment.workflow_conclusion, Some("success".to_string()));
        assert_eq!(deployment.argocd_app_name, Some("my-app".to_string()));
        assert_eq!(deployment.argocd_sync_status, Some("Synced".to_string()));
        assert_eq!(deployment.argocd_health_status, Some("Healthy".to_string()));
        assert_eq!(deployment.argocd_revision, Some(5));
        assert_eq!(deployment.namespace, Some("production".to_string()));
        assert_eq!(deployment.deployment_name, Some("my-deployment".to_string()));
        assert_eq!(deployment.replicas_desired, Some(3));
        assert_eq!(deployment.replicas_ready, Some(3));
    }

    // StateTransition tests
    #[test]
    fn test_state_transition_serialization() {
        let transition = StateTransition {
            id: Uuid::new_v4(),
            card_id: Uuid::new_v4(),
            from_state: "draft".to_string(),
            to_state: "planning".to_string(),
            trigger: "StartPlanning".to_string(),
            metadata: Some(serde_json::json!({"user": "test"})),
            created_at: Utc::now(),
        };

        let json = serde_json::to_string(&transition).unwrap();

        assert!(json.contains("\"cardId\""));
        assert!(json.contains("\"fromState\""));
        assert!(json.contains("\"toState\""));
        assert!(json.contains("\"createdAt\""));
    }

    #[test]
    fn test_state_transition_deserialization() {
        let json = r#"{
            "id": "00000000-0000-0000-0000-000000000001",
            "cardId": "00000000-0000-0000-0000-000000000002",
            "fromState": "coding",
            "toState": "code_review",
            "trigger": "LoopComplete",
            "metadata": {"iteration": 5},
            "createdAt": "2024-01-01T00:00:00Z"
        }"#;

        let transition: StateTransition = serde_json::from_str(json).unwrap();

        assert_eq!(transition.from_state, "coding");
        assert_eq!(transition.to_state, "code_review");
        assert_eq!(transition.trigger, "LoopComplete");
        assert!(transition.metadata.is_some());
    }
}
