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
            COALESCE(SUM(c.total_cost_usd), 0) as total_cost_usd
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
