//! Project domain model

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// A project represents a codebase being managed by Ringmaster
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Project {
    pub id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub repository_url: String,
    pub repository_path: Option<String>,
    pub tech_stack: Vec<String>,
    pub coding_conventions: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Project {
    pub fn new(name: String, repository_url: String) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            name,
            description: None,
            repository_url,
            repository_path: None,
            tech_stack: Vec::new(),
            coding_conventions: None,
            created_at: now,
            updated_at: now,
        }
    }

    /// Create a default project for a card when no project is specified
    pub fn default_for_card(card: &super::Card) -> Self {
        let now = Utc::now();
        Self {
            id: card.project_id,
            name: format!("Project for {}", card.title),
            description: None,
            repository_url: String::new(),
            repository_path: card.worktree_path.clone(),
            tech_stack: Vec::new(),
            coding_conventions: None,
            created_at: now,
            updated_at: now,
        }
    }
}

/// Request to create a new project
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CreateProjectRequest {
    pub name: String,
    pub description: Option<String>,
    pub repository_url: String,
    pub repository_path: Option<String>,
    pub tech_stack: Option<Vec<String>>,
    pub coding_conventions: Option<String>,
}

/// Request to update a project
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateProjectRequest {
    pub name: Option<String>,
    pub description: Option<String>,
    pub repository_url: Option<String>,
    pub repository_path: Option<String>,
    pub tech_stack: Option<Vec<String>>,
    pub coding_conventions: Option<String>,
}

/// Project with aggregated statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectWithStats {
    #[serde(flatten)]
    pub project: Project,
    pub card_count: i64,
    pub active_loops: i64,
    pub total_cost_usd: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_new() {
        let project = Project::new("my-project".to_string(), "https://github.com/org/repo".to_string());

        assert_eq!(project.name, "my-project");
        assert_eq!(project.repository_url, "https://github.com/org/repo");
        assert!(project.description.is_none());
        assert!(project.repository_path.is_none());
        assert!(project.tech_stack.is_empty());
        assert!(project.coding_conventions.is_none());
    }

    #[test]
    fn test_project_default_for_card() {
        let card = super::super::Card::new(
            Uuid::new_v4(),
            "Test Card".to_string(),
            "Test description".to_string(),
        );

        let project = Project::default_for_card(&card);

        assert_eq!(project.id, card.project_id);
        assert!(project.name.contains("Test Card"));
        assert_eq!(project.repository_url, "");
        assert!(project.tech_stack.is_empty());
    }

    #[test]
    fn test_project_default_for_card_with_worktree() {
        let mut card = super::super::Card::new(
            Uuid::new_v4(),
            "Test Card".to_string(),
            "Test description".to_string(),
        );
        card.worktree_path = Some("/tmp/worktree".to_string());

        let project = Project::default_for_card(&card);

        assert_eq!(project.repository_path, Some("/tmp/worktree".to_string()));
    }

    #[test]
    fn test_project_serialization_camel_case() {
        let project = Project::new("test".to_string(), "https://github.com/test/repo".to_string());
        let json = serde_json::to_string(&project).unwrap();

        // Verify camelCase serialization
        assert!(json.contains("\"repositoryUrl\""));
        assert!(json.contains("\"repositoryPath\""));
        assert!(json.contains("\"techStack\""));
        assert!(json.contains("\"codingConventions\""));
        assert!(json.contains("\"createdAt\""));
        assert!(json.contains("\"updatedAt\""));

        // Should not contain snake_case
        assert!(!json.contains("\"repository_url\""));
        assert!(!json.contains("\"tech_stack\""));
    }

    #[test]
    fn test_create_project_request_deserialization() {
        let json = r#"{
            "name": "my-project",
            "description": "A test project",
            "repositoryUrl": "https://github.com/org/repo",
            "repositoryPath": "/home/user/code",
            "techStack": ["rust", "typescript"],
            "codingConventions": "Use 4-space indentation"
        }"#;

        let request: CreateProjectRequest = serde_json::from_str(json).unwrap();

        assert_eq!(request.name, "my-project");
        assert_eq!(request.description, Some("A test project".to_string()));
        assert_eq!(request.repository_url, "https://github.com/org/repo");
        assert_eq!(request.repository_path, Some("/home/user/code".to_string()));
        assert_eq!(request.tech_stack, Some(vec!["rust".to_string(), "typescript".to_string()]));
        assert_eq!(request.coding_conventions, Some("Use 4-space indentation".to_string()));
    }

    #[test]
    fn test_create_project_request_minimal() {
        let json = r#"{
            "name": "minimal-project",
            "repositoryUrl": "https://github.com/org/repo"
        }"#;

        let request: CreateProjectRequest = serde_json::from_str(json).unwrap();

        assert_eq!(request.name, "minimal-project");
        assert!(request.description.is_none());
        assert!(request.repository_path.is_none());
        assert!(request.tech_stack.is_none());
        assert!(request.coding_conventions.is_none());
    }

    #[test]
    fn test_update_project_request_partial() {
        let json = r#"{
            "name": "new-name",
            "techStack": ["go", "python"]
        }"#;

        let request: UpdateProjectRequest = serde_json::from_str(json).unwrap();

        assert_eq!(request.name, Some("new-name".to_string()));
        assert!(request.description.is_none());
        assert!(request.repository_url.is_none());
        assert_eq!(request.tech_stack, Some(vec!["go".to_string(), "python".to_string()]));
    }

    #[test]
    fn test_update_project_request_empty() {
        let json = r#"{}"#;

        let request: UpdateProjectRequest = serde_json::from_str(json).unwrap();

        assert!(request.name.is_none());
        assert!(request.description.is_none());
        assert!(request.repository_url.is_none());
        assert!(request.repository_path.is_none());
        assert!(request.tech_stack.is_none());
        assert!(request.coding_conventions.is_none());
    }

    #[test]
    fn test_project_with_stats_serialization() {
        let project = Project::new("test".to_string(), "https://github.com/test/repo".to_string());
        let with_stats = ProjectWithStats {
            project,
            card_count: 5,
            active_loops: 2,
            total_cost_usd: 1.50,
        };

        let json = serde_json::to_string(&with_stats).unwrap();

        // Should include both project fields and stats fields
        assert!(json.contains("\"name\""));
        assert!(json.contains("\"repositoryUrl\""));
        assert!(json.contains("\"cardCount\""));
        assert!(json.contains("\"activeLoops\""));
        assert!(json.contains("\"totalCostUsd\""));
    }

    #[test]
    fn test_project_with_stats_flattened() {
        let json = r#"{
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "test-project",
            "repositoryUrl": "https://github.com/org/repo",
            "techStack": [],
            "createdAt": "2024-01-01T00:00:00Z",
            "updatedAt": "2024-01-01T00:00:00Z",
            "cardCount": 10,
            "activeLoops": 3,
            "totalCostUsd": 5.25
        }"#;

        let with_stats: ProjectWithStats = serde_json::from_str(json).unwrap();

        assert_eq!(with_stats.project.name, "test-project");
        assert_eq!(with_stats.card_count, 10);
        assert_eq!(with_stats.active_loops, 3);
        assert!((with_stats.total_cost_usd - 5.25).abs() < 0.001);
    }
}
