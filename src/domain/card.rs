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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_card_new() {
        let project_id = Uuid::new_v4();
        let card = Card::new(
            project_id,
            "Test Card".to_string(),
            "Implement test feature".to_string(),
        );

        assert_eq!(card.project_id, project_id);
        assert_eq!(card.title, "Test Card");
        assert_eq!(card.task_prompt, "Implement test feature");
        assert_eq!(card.state, CardState::Draft);
        assert!(card.previous_state.is_none());
        assert_eq!(card.loop_iteration, 0);
        assert_eq!(card.error_count, 0);
        assert_eq!(card.max_retries, 5);
        assert!(card.worktree_path.is_none());
        assert!(card.labels.is_empty());
    }

    #[test]
    fn test_card_has_code_changes() {
        let project_id = Uuid::new_v4();
        let mut card = Card::new(project_id, "Test".to_string(), "Test".to_string());

        // Initially no code changes
        assert!(!card.has_code_changes());

        // Only worktree set - still no changes
        card.worktree_path = Some("/tmp/worktree".to_string());
        assert!(!card.has_code_changes());

        // Only iteration > 0 but no worktree - still no changes
        card.worktree_path = None;
        card.loop_iteration = 1;
        assert!(!card.has_code_changes());

        // Both worktree and iteration > 0 - has changes
        card.worktree_path = Some("/tmp/worktree".to_string());
        assert!(card.has_code_changes());
    }

    #[test]
    fn test_card_under_retry_limit() {
        let project_id = Uuid::new_v4();
        let mut card = Card::new(project_id, "Test".to_string(), "Test".to_string());

        // Initially under limit
        assert!(card.under_retry_limit());

        // At max_retries - 1, still under limit
        card.error_count = 4;
        assert!(card.under_retry_limit());

        // At max_retries, not under limit
        card.error_count = 5;
        assert!(!card.under_retry_limit());

        // Over max_retries, definitely not under limit
        card.error_count = 10;
        assert!(!card.under_retry_limit());
    }

    #[test]
    fn test_card_serialization() {
        let project_id = Uuid::new_v4();
        let card = Card::new(project_id, "Test".to_string(), "Test prompt".to_string());

        let json = serde_json::to_value(&card).unwrap();

        // Verify camelCase serialization
        assert!(json.get("projectId").is_some());
        assert!(json.get("taskPrompt").is_some());
        assert!(json.get("loopIteration").is_some());
        assert!(json.get("errorCount").is_some());
        assert!(json.get("maxRetries").is_some());
        assert!(json.get("createdAt").is_some());
        assert!(json.get("updatedAt").is_some());

        // snake_case fields should not exist
        assert!(json.get("project_id").is_none());
        assert!(json.get("task_prompt").is_none());
    }

    #[test]
    fn test_acceptance_criteria_new() {
        let card_id = Uuid::new_v4();
        let criteria = AcceptanceCriteria::new(
            card_id,
            "User can log in".to_string(),
            0,
        );

        assert_eq!(criteria.card_id, card_id);
        assert_eq!(criteria.description, "User can log in");
        assert!(!criteria.met);
        assert!(criteria.met_at.is_none());
        assert_eq!(criteria.order_index, 0);
    }

    #[test]
    fn test_dependency_type_serialization() {
        // Test all dependency types serialize correctly
        assert_eq!(
            serde_json::to_value(DependencyType::Blocks).unwrap(),
            "blocks"
        );
        assert_eq!(
            serde_json::to_value(DependencyType::RelatesTo).unwrap(),
            "relates_to"
        );
        assert_eq!(
            serde_json::to_value(DependencyType::Duplicates).unwrap(),
            "duplicates"
        );
    }

    #[test]
    fn test_dependency_type_deserialization() {
        let blocks: DependencyType = serde_json::from_str("\"blocks\"").unwrap();
        assert_eq!(blocks, DependencyType::Blocks);

        let relates_to: DependencyType = serde_json::from_str("\"relates_to\"").unwrap();
        assert_eq!(relates_to, DependencyType::RelatesTo);

        let duplicates: DependencyType = serde_json::from_str("\"duplicates\"").unwrap();
        assert_eq!(duplicates, DependencyType::Duplicates);
    }

    #[test]
    fn test_create_card_request_deserialization() {
        let json = serde_json::json!({
            "projectId": "00000000-0000-0000-0000-000000000001",
            "title": "Test Card",
            "taskPrompt": "Implement feature X",
            "labels": ["urgent", "feature"],
            "priority": 1
        });

        let request: CreateCardRequest = serde_json::from_value(json).unwrap();
        assert_eq!(request.title, "Test Card");
        assert_eq!(request.task_prompt, "Implement feature X");
        assert!(request.description.is_none());
        assert_eq!(request.labels.unwrap().len(), 2);
        assert_eq!(request.priority, Some(1));
    }

    #[test]
    fn test_update_card_request_deserialization() {
        let json = serde_json::json!({
            "title": "Updated Title",
            "priority": 2
        });

        let request: UpdateCardRequest = serde_json::from_value(json).unwrap();
        assert_eq!(request.title, Some("Updated Title".to_string()));
        assert!(request.description.is_none());
        assert!(request.task_prompt.is_none());
        assert_eq!(request.priority, Some(2));
    }

    #[test]
    fn test_transition_request_deserialization() {
        let json = serde_json::json!({
            "trigger": "StartPlanning"
        });

        let request: TransitionRequest = serde_json::from_value(json).unwrap();
        assert_eq!(request.trigger, "StartPlanning");
        assert!(request.data.is_none());
    }
}
