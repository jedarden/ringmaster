//! Card database operations

use chrono::{DateTime, Utc};
use sqlx::SqlitePool;
use uuid::Uuid;

use crate::domain::{
    AcceptanceCriteria, Card, CardState, CreateCardRequest, UpdateCardRequest,
};

/// Row type for cards table
#[derive(Debug, sqlx::FromRow)]
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
    pub labels: String,
    pub priority: i32,
    pub deadline: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

impl CardRow {
    pub fn to_card(&self) -> Card {
        Card {
            id: Uuid::parse_str(&self.id).unwrap_or_default(),
            project_id: Uuid::parse_str(&self.project_id).unwrap_or_default(),
            title: self.title.clone(),
            description: self.description.clone(),
            task_prompt: self.task_prompt.clone(),
            state: self.state.parse().unwrap_or(CardState::Draft),
            previous_state: self
                .previous_state
                .as_ref()
                .and_then(|s| s.parse().ok()),
            state_changed_at: self
                .state_changed_at
                .as_ref()
                .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
                .map(|dt| dt.with_timezone(&Utc)),
            loop_iteration: self.loop_iteration,
            total_time_spent_ms: self.total_time_spent_ms,
            total_cost_usd: self.total_cost_usd,
            error_count: self.error_count,
            max_retries: self.max_retries,
            worktree_path: self.worktree_path.clone(),
            branch_name: self.branch_name.clone(),
            pull_request_url: self.pull_request_url.clone(),
            deployment_namespace: self.deployment_namespace.clone(),
            deployment_name: self.deployment_name.clone(),
            argocd_app_name: self.argocd_app_name.clone(),
            labels: serde_json::from_str(&self.labels).unwrap_or_default(),
            priority: self.priority,
            deadline: self
                .deadline
                .as_ref()
                .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
                .map(|dt| dt.with_timezone(&Utc)),
            created_at: DateTime::parse_from_rfc3339(&self.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
            updated_at: DateTime::parse_from_rfc3339(&self.updated_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        }
    }
}

/// Get a card by ID
pub async fn get_card(pool: &SqlitePool, card_id: &str) -> Result<Option<Card>, sqlx::Error> {
    let row = sqlx::query_as::<_, CardRow>("SELECT * FROM cards WHERE id = ?")
        .bind(card_id)
        .fetch_optional(pool)
        .await?;

    Ok(row.map(|r| r.to_card()))
}

/// List cards with optional filters
pub async fn list_cards(
    pool: &SqlitePool,
    project_id: Option<&str>,
    states: Option<&[&str]>,
    limit: i32,
    offset: i32,
) -> Result<Vec<Card>, sqlx::Error> {
    let mut query = String::from("SELECT * FROM cards WHERE 1=1");
    let mut bindings: Vec<String> = Vec::new();

    if let Some(pid) = project_id {
        query.push_str(" AND project_id = ?");
        bindings.push(pid.to_string());
    }

    if let Some(s) = states {
        if !s.is_empty() {
            let placeholders: Vec<&str> = s.iter().map(|_| "?").collect();
            query.push_str(&format!(" AND state IN ({})", placeholders.join(",")));
            for state in s {
                bindings.push(state.to_string());
            }
        }
    }

    query.push_str(" ORDER BY priority DESC, updated_at DESC LIMIT ? OFFSET ?");

    let mut q = sqlx::query_as::<_, CardRow>(&query);

    for binding in &bindings {
        q = q.bind(binding);
    }
    q = q.bind(limit).bind(offset);

    let rows = q.fetch_all(pool).await?;
    Ok(rows.into_iter().map(|r| r.to_card()).collect())
}

/// Create a new card
pub async fn create_card(pool: &SqlitePool, req: &CreateCardRequest) -> Result<Card, sqlx::Error> {
    let id = Uuid::new_v4().to_string();
    let labels_json = serde_json::to_string(&req.labels.clone().unwrap_or_default())
        .unwrap_or_else(|_| "[]".to_string());
    let priority = req.priority.unwrap_or(0);

    sqlx::query(
        r#"
        INSERT INTO cards (id, project_id, title, description, task_prompt, labels, priority, deployment_namespace, deployment_name, argocd_app_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(req.project_id.to_string())
    .bind(&req.title)
    .bind(&req.description)
    .bind(&req.task_prompt)
    .bind(&labels_json)
    .bind(priority)
    .bind(&req.deployment_namespace)
    .bind(&req.deployment_name)
    .bind(&req.argocd_app_name)
    .execute(pool)
    .await?;

    // Create acceptance criteria if provided
    if let Some(criteria) = &req.acceptance_criteria {
        for (idx, criterion) in criteria.iter().enumerate() {
            let ac_id = Uuid::new_v4().to_string();
            sqlx::query(
                "INSERT INTO acceptance_criteria (id, card_id, description, order_index) VALUES (?, ?, ?, ?)",
            )
            .bind(&ac_id)
            .bind(&id)
            .bind(&criterion.description)
            .bind(idx as i32)
            .execute(pool)
            .await?;
        }
    }

    get_card(pool, &id)
        .await?
        .ok_or_else(|| sqlx::Error::RowNotFound)
}

/// Update a card
pub async fn update_card(
    pool: &SqlitePool,
    card_id: &str,
    req: &UpdateCardRequest,
) -> Result<Option<Card>, sqlx::Error> {
    let mut updates = Vec::new();
    let mut bindings: Vec<String> = Vec::new();

    if let Some(title) = &req.title {
        updates.push("title = ?");
        bindings.push(title.clone());
    }
    if let Some(desc) = &req.description {
        updates.push("description = ?");
        bindings.push(desc.clone());
    }
    if let Some(prompt) = &req.task_prompt {
        updates.push("task_prompt = ?");
        bindings.push(prompt.clone());
    }
    if let Some(labels) = &req.labels {
        updates.push("labels = ?");
        bindings.push(serde_json::to_string(labels).unwrap_or_else(|_| "[]".to_string()));
    }
    if let Some(priority) = req.priority {
        updates.push("priority = ?");
        bindings.push(priority.to_string());
    }

    if updates.is_empty() {
        return get_card(pool, card_id).await;
    }

    let query = format!("UPDATE cards SET {} WHERE id = ?", updates.join(", "));

    let mut q = sqlx::query(&query);
    for binding in &bindings {
        q = q.bind(binding);
    }
    q = q.bind(card_id);
    q.execute(pool).await?;

    get_card(pool, card_id).await
}

/// Update card state
pub async fn update_card_state(
    pool: &SqlitePool,
    card_id: &str,
    new_state: &str,
    previous_state: &str,
    trigger: &str,
) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;

    // Update card
    sqlx::query(
        r#"
        UPDATE cards
        SET state = ?, previous_state = ?, state_changed_at = datetime('now')
        WHERE id = ?
        "#,
    )
    .bind(new_state)
    .bind(previous_state)
    .bind(card_id)
    .execute(&mut *tx)
    .await?;

    // Record transition
    let trans_id = Uuid::new_v4().to_string();
    sqlx::query(
        r#"
        INSERT INTO state_transitions (id, card_id, from_state, to_state, trigger)
        VALUES (?, ?, ?, ?, ?)
        "#,
    )
    .bind(&trans_id)
    .bind(card_id)
    .bind(previous_state)
    .bind(new_state)
    .bind(trigger)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    Ok(())
}

/// Delete a card
pub async fn delete_card(pool: &SqlitePool, card_id: &str) -> Result<bool, sqlx::Error> {
    let result = sqlx::query("DELETE FROM cards WHERE id = ?")
        .bind(card_id)
        .execute(pool)
        .await?;

    Ok(result.rows_affected() > 0)
}

/// Get acceptance criteria for a card
pub async fn get_acceptance_criteria(
    pool: &SqlitePool,
    card_id: &str,
) -> Result<Vec<AcceptanceCriteria>, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct ACRow {
        id: String,
        card_id: String,
        description: String,
        met: i32,
        met_at: Option<String>,
        order_index: i32,
        created_at: String,
    }

    let rows = sqlx::query_as::<_, ACRow>(
        "SELECT * FROM acceptance_criteria WHERE card_id = ? ORDER BY order_index",
    )
    .bind(card_id)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|r| AcceptanceCriteria {
            id: Uuid::parse_str(&r.id).unwrap_or_default(),
            card_id: Uuid::parse_str(&r.card_id).unwrap_or_default(),
            description: r.description,
            met: r.met != 0,
            met_at: r
                .met_at
                .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
                .map(|dt| dt.with_timezone(&Utc)),
            order_index: r.order_index,
            created_at: DateTime::parse_from_rfc3339(&r.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        })
        .collect())
}

/// Increment error count for a card
pub async fn increment_error_count(pool: &SqlitePool, card_id: &str) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE cards SET error_count = error_count + 1 WHERE id = ?")
        .bind(card_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// Update loop iteration for a card
pub async fn update_loop_iteration(
    pool: &SqlitePool,
    card_id: &str,
    iteration: i32,
) -> Result<(), sqlx::Error> {
    sqlx::query("UPDATE cards SET loop_iteration = ? WHERE id = ?")
        .bind(iteration)
        .bind(card_id)
        .execute(pool)
        .await?;
    Ok(())
}

/// Update card cost
pub async fn add_card_cost(
    pool: &SqlitePool,
    card_id: &str,
    cost_usd: f64,
    time_ms: i64,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE cards SET total_cost_usd = total_cost_usd + ?, total_time_spent_ms = total_time_spent_ms + ? WHERE id = ?",
    )
    .bind(cost_usd)
    .bind(time_ms)
    .bind(card_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// Simple state update (without full transition tracking)
pub async fn set_card_state(
    pool: &SqlitePool,
    card_id: &str,
    new_state: CardState,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE cards
        SET state = ?, state_changed_at = datetime('now'), updated_at = datetime('now')
        WHERE id = ?
        "#,
    )
    .bind(new_state.to_string())
    .bind(card_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// Count cards by state for a project
pub async fn count_cards_by_state(
    pool: &SqlitePool,
    project_id: &str,
) -> Result<Vec<(String, i64)>, sqlx::Error> {
    #[derive(sqlx::FromRow)]
    struct CountRow {
        state: String,
        count: i64,
    }

    let rows = sqlx::query_as::<_, CountRow>(
        r#"
        SELECT state, COUNT(*) as count
        FROM cards
        WHERE project_id = ? AND state != 'archived'
        GROUP BY state
        "#,
    )
    .bind(project_id)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| (r.state, r.count)).collect())
}
