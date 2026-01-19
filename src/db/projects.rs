//! Project database operations

use chrono::{DateTime, Utc};
use sqlx::SqlitePool;
use uuid::Uuid;

use crate::domain::{CreateProjectRequest, Project, ProjectWithStats, UpdateProjectRequest};

/// Row type for projects table
#[derive(Debug, sqlx::FromRow)]
pub struct ProjectRow {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub repository_url: String,
    pub repository_path: Option<String>,
    pub tech_stack: String,
    pub coding_conventions: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

impl ProjectRow {
    pub fn to_project(&self) -> Project {
        Project {
            id: Uuid::parse_str(&self.id).unwrap_or_default(),
            name: self.name.clone(),
            description: self.description.clone(),
            repository_url: self.repository_url.clone(),
            repository_path: self.repository_path.clone(),
            tech_stack: serde_json::from_str(&self.tech_stack).unwrap_or_default(),
            coding_conventions: self.coding_conventions.clone(),
            created_at: DateTime::parse_from_rfc3339(&self.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
            updated_at: DateTime::parse_from_rfc3339(&self.updated_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        }
    }
}

/// Get a project by ID
pub async fn get_project(
    pool: &SqlitePool,
    project_id: &str,
) -> Result<Option<Project>, sqlx::Error> {
    let row = sqlx::query_as::<_, ProjectRow>("SELECT * FROM projects WHERE id = ?")
        .bind(project_id)
        .fetch_optional(pool)
        .await?;

    Ok(row.map(|r| r.to_project()))
}

/// List all projects
pub async fn list_projects(pool: &SqlitePool) -> Result<Vec<Project>, sqlx::Error> {
    let rows =
        sqlx::query_as::<_, ProjectRow>("SELECT * FROM projects ORDER BY updated_at DESC")
            .fetch_all(pool)
            .await?;

    Ok(rows.into_iter().map(|r| r.to_project()).collect())
}

/// List projects with stats
pub async fn list_projects_with_stats(
    pool: &SqlitePool,
) -> Result<Vec<ProjectWithStats>, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct ProjectStatsRow {
        id: String,
        name: String,
        description: Option<String>,
        repository_url: String,
        repository_path: Option<String>,
        tech_stack: String,
        coding_conventions: Option<String>,
        created_at: String,
        updated_at: String,
        card_count: i64,
        active_loops: i64,
        total_cost_usd: f64,
    }

    let rows = sqlx::query_as::<_, ProjectStatsRow>(
        r#"
        SELECT
            p.*,
            COUNT(DISTINCT c.id) as card_count,
            SUM(CASE WHEN c.state IN ('coding', 'error_fixing') THEN 1 ELSE 0 END) as active_loops,
            COALESCE(SUM(c.total_cost_usd), 0.0) as total_cost_usd
        FROM projects p
        LEFT JOIN cards c ON c.project_id = p.id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
        "#,
    )
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|r| {
            let project = Project {
                id: Uuid::parse_str(&r.id).unwrap_or_default(),
                name: r.name,
                description: r.description,
                repository_url: r.repository_url,
                repository_path: r.repository_path,
                tech_stack: serde_json::from_str(&r.tech_stack).unwrap_or_default(),
                coding_conventions: r.coding_conventions,
                created_at: DateTime::parse_from_rfc3339(&r.created_at)
                    .map(|dt| dt.with_timezone(&Utc))
                    .unwrap_or_else(|_| Utc::now()),
                updated_at: DateTime::parse_from_rfc3339(&r.updated_at)
                    .map(|dt| dt.with_timezone(&Utc))
                    .unwrap_or_else(|_| Utc::now()),
            };
            ProjectWithStats {
                project,
                card_count: r.card_count,
                active_loops: r.active_loops,
                total_cost_usd: r.total_cost_usd,
            }
        })
        .collect())
}

/// Create a new project
pub async fn create_project(
    pool: &SqlitePool,
    req: &CreateProjectRequest,
) -> Result<Project, sqlx::Error> {
    let id = Uuid::new_v4().to_string();
    let tech_stack_json = serde_json::to_string(&req.tech_stack.clone().unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());

    sqlx::query(
        r#"
        INSERT INTO projects (id, name, description, repository_url, repository_path, tech_stack, coding_conventions)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(&req.name)
    .bind(&req.description)
    .bind(&req.repository_url)
    .bind(&req.repository_path)
    .bind(&tech_stack_json)
    .bind(&req.coding_conventions)
    .execute(pool)
    .await?;

    get_project(pool, &id)
        .await?
        .ok_or_else(|| sqlx::Error::RowNotFound)
}

/// Update a project
pub async fn update_project(
    pool: &SqlitePool,
    project_id: &str,
    req: &UpdateProjectRequest,
) -> Result<Option<Project>, sqlx::Error> {
    let mut updates = Vec::new();
    let mut bindings: Vec<String> = Vec::new();

    if let Some(name) = &req.name {
        updates.push("name = ?");
        bindings.push(name.clone());
    }
    if let Some(desc) = &req.description {
        updates.push("description = ?");
        bindings.push(desc.clone());
    }
    if let Some(url) = &req.repository_url {
        updates.push("repository_url = ?");
        bindings.push(url.clone());
    }
    if let Some(path) = &req.repository_path {
        updates.push("repository_path = ?");
        bindings.push(path.clone());
    }
    if let Some(tech_stack) = &req.tech_stack {
        updates.push("tech_stack = ?");
        bindings.push(serde_json::to_string(tech_stack).unwrap_or_else(|_| "[]".to_string()));
    }
    if let Some(conventions) = &req.coding_conventions {
        updates.push("coding_conventions = ?");
        bindings.push(conventions.clone());
    }

    if updates.is_empty() {
        return get_project(pool, project_id).await;
    }

    updates.push("updated_at = datetime('now')");
    let query = format!(
        "UPDATE projects SET {} WHERE id = ?",
        updates.join(", ")
    );

    let mut q = sqlx::query(&query);
    for binding in &bindings {
        q = q.bind(binding);
    }
    q = q.bind(project_id);
    q.execute(pool).await?;

    get_project(pool, project_id).await
}

/// Delete a project
pub async fn delete_project(pool: &SqlitePool, project_id: &str) -> Result<bool, sqlx::Error> {
    let result = sqlx::query("DELETE FROM projects WHERE id = ?")
        .bind(project_id)
        .execute(pool)
        .await?;

    Ok(result.rows_affected() > 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::init_database;

    async fn setup_test_db() -> SqlitePool {
        init_database("sqlite::memory:").await.unwrap()
    }

    #[tokio::test]
    async fn test_create_project() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Test Project".to_string(),
            description: Some("A test project".to_string()),
            repository_url: "https://github.com/test/repo".to_string(),
            repository_path: Some("/path/to/repo".to_string()),
            tech_stack: Some(vec!["Rust".to_string(), "TypeScript".to_string()]),
            coding_conventions: Some("Use 4-space indentation".to_string()),
        };

        let project = create_project(&pool, &req).await.unwrap();

        assert_eq!(project.name, "Test Project");
        assert_eq!(project.description, Some("A test project".to_string()));
        assert_eq!(project.repository_url, "https://github.com/test/repo");
        assert_eq!(project.repository_path, Some("/path/to/repo".to_string()));
        assert_eq!(project.tech_stack, vec!["Rust", "TypeScript"]);
        assert_eq!(
            project.coding_conventions,
            Some("Use 4-space indentation".to_string())
        );
    }

    #[tokio::test]
    async fn test_create_project_minimal() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Minimal Project".to_string(),
            description: None,
            repository_url: "https://github.com/test/minimal".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };

        let project = create_project(&pool, &req).await.unwrap();

        assert_eq!(project.name, "Minimal Project");
        assert!(project.description.is_none());
        assert!(project.tech_stack.is_empty());
    }

    #[tokio::test]
    async fn test_get_project() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Get Test".to_string(),
            description: None,
            repository_url: "https://github.com/test/get".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };

        let created = create_project(&pool, &req).await.unwrap();
        let fetched = get_project(&pool, &created.id.to_string()).await.unwrap();

        assert!(fetched.is_some());
        let fetched = fetched.unwrap();
        assert_eq!(fetched.id, created.id);
        assert_eq!(fetched.name, "Get Test");
    }

    #[tokio::test]
    async fn test_get_project_not_found() {
        let pool = setup_test_db().await;

        let result = get_project(&pool, "non-existent-id").await.unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_list_projects() {
        let pool = setup_test_db().await;

        // Create multiple projects
        for i in 1..=3 {
            let req = CreateProjectRequest {
                name: format!("Project {}", i),
                description: None,
                repository_url: format!("https://github.com/test/project{}", i),
                repository_path: None,
                tech_stack: None,
                coding_conventions: None,
            };
            create_project(&pool, &req).await.unwrap();
        }

        let projects = list_projects(&pool).await.unwrap();
        assert_eq!(projects.len(), 3);
    }

    #[tokio::test]
    async fn test_list_projects_empty() {
        let pool = setup_test_db().await;

        let projects = list_projects(&pool).await.unwrap();
        assert!(projects.is_empty());
    }

    #[tokio::test]
    async fn test_list_projects_with_stats() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Stats Project".to_string(),
            description: None,
            repository_url: "https://github.com/test/stats".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        create_project(&pool, &req).await.unwrap();

        let projects = list_projects_with_stats(&pool).await.unwrap();
        assert_eq!(projects.len(), 1);
        assert_eq!(projects[0].card_count, 0);
        assert_eq!(projects[0].active_loops, 0);
        assert_eq!(projects[0].total_cost_usd, 0.0);
    }

    #[tokio::test]
    async fn test_update_project_name() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Original Name".to_string(),
            description: None,
            repository_url: "https://github.com/test/update".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project = create_project(&pool, &req).await.unwrap();

        let update_req = UpdateProjectRequest {
            name: Some("Updated Name".to_string()),
            description: None,
            repository_url: None,
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };

        let updated = update_project(&pool, &project.id.to_string(), &update_req)
            .await
            .unwrap();

        assert!(updated.is_some());
        let updated = updated.unwrap();
        assert_eq!(updated.name, "Updated Name");
    }

    #[tokio::test]
    async fn test_update_project_multiple_fields() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "Multi Update".to_string(),
            description: Some("Old description".to_string()),
            repository_url: "https://github.com/test/multi".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project = create_project(&pool, &req).await.unwrap();

        let update_req = UpdateProjectRequest {
            name: Some("New Name".to_string()),
            description: Some("New description".to_string()),
            repository_url: None,
            repository_path: Some("/new/path".to_string()),
            tech_stack: Some(vec!["Go".to_string()]),
            coding_conventions: Some("Use gofmt".to_string()),
        };

        let updated = update_project(&pool, &project.id.to_string(), &update_req)
            .await
            .unwrap()
            .unwrap();

        assert_eq!(updated.name, "New Name");
        assert_eq!(updated.description, Some("New description".to_string()));
        assert_eq!(updated.repository_path, Some("/new/path".to_string()));
        assert_eq!(updated.tech_stack, vec!["Go"]);
        assert_eq!(updated.coding_conventions, Some("Use gofmt".to_string()));
    }

    #[tokio::test]
    async fn test_update_project_empty_request() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "No Change".to_string(),
            description: None,
            repository_url: "https://github.com/test/empty".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project = create_project(&pool, &req).await.unwrap();

        let update_req = UpdateProjectRequest {
            name: None,
            description: None,
            repository_url: None,
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };

        let updated = update_project(&pool, &project.id.to_string(), &update_req)
            .await
            .unwrap();

        assert!(updated.is_some());
        let updated = updated.unwrap();
        assert_eq!(updated.name, "No Change");
    }

    #[tokio::test]
    async fn test_update_project_not_found() {
        let pool = setup_test_db().await;

        let update_req = UpdateProjectRequest {
            name: Some("Ghost".to_string()),
            description: None,
            repository_url: None,
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };

        let result = update_project(&pool, "non-existent", &update_req)
            .await
            .unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_delete_project() {
        let pool = setup_test_db().await;

        let req = CreateProjectRequest {
            name: "To Delete".to_string(),
            description: None,
            repository_url: "https://github.com/test/delete".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project = create_project(&pool, &req).await.unwrap();

        let deleted = delete_project(&pool, &project.id.to_string()).await.unwrap();
        assert!(deleted);

        // Verify it's gone
        let fetched = get_project(&pool, &project.id.to_string()).await.unwrap();
        assert!(fetched.is_none());
    }

    #[tokio::test]
    async fn test_delete_project_not_found() {
        let pool = setup_test_db().await;

        let deleted = delete_project(&pool, "non-existent").await.unwrap();
        assert!(!deleted);
    }

    #[tokio::test]
    async fn test_project_row_to_project() {
        let row = ProjectRow {
            id: "550e8400-e29b-41d4-a716-446655440000".to_string(),
            name: "Test".to_string(),
            description: Some("Desc".to_string()),
            repository_url: "https://github.com/test/test".to_string(),
            repository_path: None,
            tech_stack: r#"["Rust"]"#.to_string(),
            coding_conventions: None,
            created_at: "2024-01-01T00:00:00Z".to_string(),
            updated_at: "2024-01-01T00:00:00Z".to_string(),
        };

        let project = row.to_project();
        assert_eq!(project.name, "Test");
        assert_eq!(project.tech_stack, vec!["Rust"]);
    }

    #[tokio::test]
    async fn test_project_row_invalid_json() {
        let row = ProjectRow {
            id: "550e8400-e29b-41d4-a716-446655440000".to_string(),
            name: "Test".to_string(),
            description: None,
            repository_url: "https://github.com/test/test".to_string(),
            repository_path: None,
            tech_stack: "invalid json".to_string(),
            coding_conventions: None,
            created_at: "2024-01-01T00:00:00Z".to_string(),
            updated_at: "2024-01-01T00:00:00Z".to_string(),
        };

        let project = row.to_project();
        // Should default to empty vec on invalid JSON
        assert!(project.tech_stack.is_empty());
    }
}
