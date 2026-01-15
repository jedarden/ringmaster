//! Card domain model - the main entity in Ringmaster

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use super::state::CardState;

/// A card represents a task in the SDLC pipeline
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Card {
    pub id: Uuid,
    pub project_id: Uuid,
    pub title: String,
    pub description: Option<String>,
    pub task_prompt: String,
    pub state: CardState,
    pub previous_state: Option<CardState>,
    pub state_changed_at: Option<DateTime<Utc>>,
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
    pub labels: Vec<String>,
    pub priority: i32,
    pub deadline: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Card {
    pub fn new(project_id: Uuid, title: String, task_prompt: String) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            project_id,
            title,
            description: None,
            task_prompt,
            state: CardState::Draft,
            previous_state: None,
            state_changed_at: None,
            loop_iteration: 0,
            total_time_spent_ms: 0,
            total_cost_usd: 0.0,
            error_count: 0,
            max_retries: 5,
            worktree_path: None,
            branch_name: None,
            pull_request_url: None,
            deployment_namespace: None,
            deployment_name: None,
            argocd_app_name: None,
            labels: Vec::new(),
            priority: 0,
            deadline: None,
            created_at: now,
            updated_at: now,
        }
    }

    /// Check if the card has generated code (for guards)
    pub fn has_code_changes(&self) -> bool {
        self.worktree_path.is_some() && self.loop_iteration > 0
    }

    /// Check if the card is under the retry limit
    pub fn under_retry_limit(&self) -> bool {
        self.error_count < self.max_retries
    }
}

/// Acceptance criteria for a card
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AcceptanceCriteria {
    pub id: Uuid,
    pub card_id: Uuid,
    pub description: String,
    pub met: bool,
    pub met_at: Option<DateTime<Utc>>,
    pub order_index: i32,
    pub created_at: DateTime<Utc>,
}

impl AcceptanceCriteria {
    pub fn new(card_id: Uuid, description: String, order_index: i32) -> Self {
        Self {
            id: Uuid::new_v4(),
            card_id,
            description,
            met: false,
            met_at: None,
            order_index,
            created_at: Utc::now(),
        }
    }
}

/// Card dependency relationship
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CardDependency {
    pub id: Uuid,
    pub card_id: Uuid,
    pub depends_on_card_id: Uuid,
    pub dependency_type: DependencyType,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DependencyType {
    Blocks,
    RelatesTo,
    Duplicates,
}

/// Request to create a new card
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateCardRequest {
    pub project_id: Uuid,
    pub title: String,
    pub description: Option<String>,
    pub task_prompt: String,
    pub acceptance_criteria: Option<Vec<CreateAcceptanceCriteriaRequest>>,
    pub labels: Option<Vec<String>>,
    pub priority: Option<i32>,
    pub deadline: Option<DateTime<Utc>>,
    pub deployment_namespace: Option<String>,
    pub deployment_name: Option<String>,
    pub argocd_app_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateAcceptanceCriteriaRequest {
    pub description: String,
}

/// Request to update a card
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateCardRequest {
    pub title: Option<String>,
    pub description: Option<String>,
    pub task_prompt: Option<String>,
    pub labels: Option<Vec<String>>,
    pub priority: Option<i32>,
    pub deadline: Option<DateTime<Utc>>,
}

/// Card with all related data
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CardDetail {
    #[serde(flatten)]
    pub card: Card,
    pub acceptance_criteria: Vec<AcceptanceCriteria>,
    pub dependencies: Vec<CardDependencyInfo>,
}

/// Dependency info with card title
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CardDependencyInfo {
    pub card_id: Uuid,
    pub title: String,
    pub state: CardState,
    pub dependency_type: DependencyType,
}

/// State transition request
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TransitionRequest {
    pub trigger: String,
    pub data: Option<serde_json::Value>,
}

/// State transition result
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TransitionResult {
    pub previous_state: CardState,
    pub new_state: CardState,
    pub card: Card,
}
