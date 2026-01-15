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
