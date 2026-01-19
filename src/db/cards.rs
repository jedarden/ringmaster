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

/// Update card worktree and branch info
pub async fn update_card_worktree(
    pool: &SqlitePool,
    card_id: &str,
    worktree_path: &str,
    branch_name: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE cards
        SET worktree_path = ?, branch_name = ?, updated_at = datetime('now')
        WHERE id = ?
        "#,
    )
    .bind(worktree_path)
    .bind(branch_name)
    .bind(card_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// Update card pull request URL
pub async fn update_card_pr(
    pool: &SqlitePool,
    card_id: &str,
    pr_url: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        UPDATE cards
        SET pull_request_url = ?, updated_at = datetime('now')
        WHERE id = ?
        "#,
    )
    .bind(pr_url)
    .bind(card_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// Increment card error count (alias for backwards compatibility)
pub async fn increment_card_error_count(
    pool: &SqlitePool,
    card_id: &str,
) -> Result<(), sqlx::Error> {
    increment_error_count(pool, card_id).await
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::init_database;
    use crate::domain::CreateProjectRequest;

    async fn setup_test_db() -> SqlitePool {
        init_database("sqlite::memory:").await.unwrap()
    }

    async fn create_test_project(pool: &SqlitePool) -> String {
        let req = CreateProjectRequest {
            name: "Test Project".to_string(),
            description: None,
            repository_url: "https://github.com/test/repo".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project = crate::db::create_project(pool, &req).await.unwrap();
        project.id.to_string()
    }

    fn make_card_request(project_id: Uuid, title: &str) -> CreateCardRequest {
        CreateCardRequest {
            project_id,
            title: title.to_string(),
            description: None,
            task_prompt: "Test".to_string(),
            acceptance_criteria: None,
            labels: None,
            priority: None,
            deadline: None,
            deployment_namespace: None,
            deployment_name: None,
            argocd_app_name: None,
        }
    }

    #[tokio::test]
    async fn test_create_card() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let mut req = make_card_request(pid, "Test Card");
        req.description = Some("A test card description".to_string());
        req.task_prompt = "Implement the feature".to_string();
        req.labels = Some(vec!["bug".to_string(), "priority".to_string()]);
        req.priority = Some(5);
        req.deployment_namespace = Some("default".to_string());
        req.deployment_name = Some("test-app".to_string());
        req.argocd_app_name = Some("test-argocd".to_string());

        let card = create_card(&pool, &req).await.unwrap();

        assert_eq!(card.title, "Test Card");
        assert_eq!(card.description, Some("A test card description".to_string()));
        assert_eq!(card.task_prompt, "Implement the feature");
        assert_eq!(card.state, CardState::Draft);
        assert_eq!(card.labels, vec!["bug", "priority"]);
        assert_eq!(card.priority, 5);
    }

    #[tokio::test]
    async fn test_create_card_minimal() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Minimal Card");
        let card = create_card(&pool, &req).await.unwrap();

        assert_eq!(card.title, "Minimal Card");
        assert!(card.labels.is_empty());
        assert_eq!(card.priority, 0);
    }

    #[tokio::test]
    async fn test_create_card_with_acceptance_criteria() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        use crate::domain::CreateAcceptanceCriteriaRequest;
        let mut req = make_card_request(pid, "Card with AC");
        req.acceptance_criteria = Some(vec![
            CreateAcceptanceCriteriaRequest { description: "Feature works".to_string() },
            CreateAcceptanceCriteriaRequest { description: "Tests pass".to_string() },
        ]);

        let card = create_card(&pool, &req).await.unwrap();
        let criteria = get_acceptance_criteria(&pool, &card.id.to_string()).await.unwrap();

        assert_eq!(criteria.len(), 2);
        assert_eq!(criteria[0].description, "Feature works");
        assert_eq!(criteria[1].description, "Tests pass");
    }

    #[tokio::test]
    async fn test_get_card() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Get Test Card");
        let created = create_card(&pool, &req).await.unwrap();
        let fetched = get_card(&pool, &created.id.to_string()).await.unwrap();

        assert!(fetched.is_some());
        assert_eq!(fetched.unwrap().title, "Get Test Card");
    }

    #[tokio::test]
    async fn test_get_card_not_found() {
        let pool = setup_test_db().await;
        let result = get_card(&pool, "non-existent-id").await.unwrap();
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_list_cards() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        for i in 1..=5 {
            let req = make_card_request(pid, &format!("Card {}", i));
            create_card(&pool, &req).await.unwrap();
        }

        let cards = list_cards(&pool, None, None, 100, 0).await.unwrap();
        assert_eq!(cards.len(), 5);
    }

    #[tokio::test]
    async fn test_list_cards_by_project() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        // Create second project
        let req2 = CreateProjectRequest {
            name: "Second Project".to_string(),
            description: None,
            repository_url: "https://github.com/test/repo2".to_string(),
            repository_path: None,
            tech_stack: None,
            coding_conventions: None,
        };
        let project2 = crate::db::create_project(&pool, &req2).await.unwrap();

        for _ in 0..3 {
            let req = make_card_request(pid, "P1 Card");
            create_card(&pool, &req).await.unwrap();
        }
        for _ in 0..2 {
            let req = make_card_request(project2.id, "P2 Card");
            create_card(&pool, &req).await.unwrap();
        }

        let p1_cards = list_cards(&pool, Some(&project_id), None, 100, 0).await.unwrap();
        assert_eq!(p1_cards.len(), 3);

        let p2_cards = list_cards(&pool, Some(&project2.id.to_string()), None, 100, 0).await.unwrap();
        assert_eq!(p2_cards.len(), 2);
    }

    #[tokio::test]
    async fn test_list_cards_by_state() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Card");
        let card = create_card(&pool, &req).await.unwrap();
        set_card_state(&pool, &card.id.to_string(), CardState::Coding).await.unwrap();

        let coding_cards = list_cards(&pool, None, Some(&["coding"]), 100, 0).await.unwrap();
        assert_eq!(coding_cards.len(), 1);

        let draft_cards = list_cards(&pool, None, Some(&["draft"]), 100, 0).await.unwrap();
        assert_eq!(draft_cards.len(), 0);
    }

    #[tokio::test]
    async fn test_list_cards_pagination() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        for i in 0..10 {
            let req = make_card_request(pid, &format!("Card {}", i));
            create_card(&pool, &req).await.unwrap();
        }

        let page1 = list_cards(&pool, None, None, 3, 0).await.unwrap();
        assert_eq!(page1.len(), 3);

        let page2 = list_cards(&pool, None, None, 3, 3).await.unwrap();
        assert_eq!(page2.len(), 3);

        let page4 = list_cards(&pool, None, None, 3, 9).await.unwrap();
        assert_eq!(page4.len(), 1);
    }

    #[tokio::test]
    async fn test_update_card() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let mut req = make_card_request(pid, "Original Title");
        req.description = Some("Original description".to_string());
        req.priority = Some(1);
        let card = create_card(&pool, &req).await.unwrap();

        let update_req = UpdateCardRequest {
            title: Some("Updated Title".to_string()),
            description: Some("Updated description".to_string()),
            task_prompt: Some("Updated prompt".to_string()),
            labels: Some(vec!["updated".to_string()]),
            priority: Some(10),
            deadline: None,
        };

        let updated = update_card(&pool, &card.id.to_string(), &update_req).await.unwrap().unwrap();

        assert_eq!(updated.title, "Updated Title");
        assert_eq!(updated.description, Some("Updated description".to_string()));
        assert_eq!(updated.labels, vec!["updated"]);
        assert_eq!(updated.priority, 10);
    }

    #[tokio::test]
    async fn test_update_card_partial() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let mut req = make_card_request(pid, "Keep This");
        req.description = Some("Keep this too".to_string());
        let card = create_card(&pool, &req).await.unwrap();

        let update_req = UpdateCardRequest {
            title: None,
            description: None,
            task_prompt: Some("Updated prompt only".to_string()),
            labels: None,
            priority: None,
            deadline: None,
        };

        let updated = update_card(&pool, &card.id.to_string(), &update_req).await.unwrap().unwrap();

        assert_eq!(updated.title, "Keep This");
        assert_eq!(updated.description, Some("Keep this too".to_string()));
        assert_eq!(updated.task_prompt, "Updated prompt only");
    }

    #[tokio::test]
    async fn test_update_card_state() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "State Test");
        let card = create_card(&pool, &req).await.unwrap();

        update_card_state(&pool, &card.id.to_string(), "planning", "draft", "start_planning")
            .await
            .unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.state, CardState::Planning);
        assert_eq!(updated.previous_state, Some(CardState::Draft));
    }

    #[tokio::test]
    async fn test_delete_card() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "To Delete");
        let card = create_card(&pool, &req).await.unwrap();

        let deleted = delete_card(&pool, &card.id.to_string()).await.unwrap();
        assert!(deleted);

        let fetched = get_card(&pool, &card.id.to_string()).await.unwrap();
        assert!(fetched.is_none());
    }

    #[tokio::test]
    async fn test_delete_card_not_found() {
        let pool = setup_test_db().await;
        let deleted = delete_card(&pool, "non-existent").await.unwrap();
        assert!(!deleted);
    }

    #[tokio::test]
    async fn test_increment_error_count() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Error Test");
        let card = create_card(&pool, &req).await.unwrap();
        assert_eq!(card.error_count, 0);

        increment_error_count(&pool, &card.id.to_string()).await.unwrap();
        increment_error_count(&pool, &card.id.to_string()).await.unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.error_count, 2);
    }

    #[tokio::test]
    async fn test_update_loop_iteration() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Iteration Test");
        let card = create_card(&pool, &req).await.unwrap();

        update_loop_iteration(&pool, &card.id.to_string(), 5).await.unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.loop_iteration, 5);
    }

    #[tokio::test]
    async fn test_add_card_cost() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Cost Test");
        let card = create_card(&pool, &req).await.unwrap();

        add_card_cost(&pool, &card.id.to_string(), 0.05, 1000).await.unwrap();
        add_card_cost(&pool, &card.id.to_string(), 0.03, 500).await.unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert!((updated.total_cost_usd - 0.08).abs() < 0.001);
        assert_eq!(updated.total_time_spent_ms, 1500);
    }

    #[tokio::test]
    async fn test_set_card_state() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Set State Test");
        let card = create_card(&pool, &req).await.unwrap();

        set_card_state(&pool, &card.id.to_string(), CardState::Completed).await.unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.state, CardState::Completed);
    }

    #[tokio::test]
    async fn test_update_card_worktree() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "Worktree Test");
        let card = create_card(&pool, &req).await.unwrap();

        update_card_worktree(&pool, &card.id.to_string(), "/tmp/worktree/card1", "card/abc123")
            .await
            .unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.worktree_path, Some("/tmp/worktree/card1".to_string()));
        assert_eq!(updated.branch_name, Some("card/abc123".to_string()));
    }

    #[tokio::test]
    async fn test_update_card_pr() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        let req = make_card_request(pid, "PR Test");
        let card = create_card(&pool, &req).await.unwrap();

        update_card_pr(&pool, &card.id.to_string(), "https://github.com/test/repo/pull/1")
            .await
            .unwrap();

        let updated = get_card(&pool, &card.id.to_string()).await.unwrap().unwrap();
        assert_eq!(updated.pull_request_url, Some("https://github.com/test/repo/pull/1".to_string()));
    }

    #[tokio::test]
    async fn test_count_cards_by_state() {
        let pool = setup_test_db().await;
        let project_id = create_test_project(&pool).await;
        let pid = Uuid::parse_str(&project_id).unwrap();

        for _ in 0..3 {
            let req = make_card_request(pid, "Draft Card");
            create_card(&pool, &req).await.unwrap();
        }

        let req = make_card_request(pid, "Coding Card");
        let coding_card = create_card(&pool, &req).await.unwrap();
        set_card_state(&pool, &coding_card.id.to_string(), CardState::Coding).await.unwrap();

        let counts = count_cards_by_state(&pool, &project_id).await.unwrap();

        let draft_count = counts.iter().find(|(s, _)| s == "draft").map(|(_, c)| *c);
        let coding_count = counts.iter().find(|(s, _)| s == "coding").map(|(_, c)| *c);

        assert_eq!(draft_count, Some(3));
        assert_eq!(coding_count, Some(1));
    }

    #[tokio::test]
    async fn test_card_row_to_card() {
        let row = CardRow {
            id: "550e8400-e29b-41d4-a716-446655440000".to_string(),
            project_id: "550e8400-e29b-41d4-a716-446655440001".to_string(),
            title: "Test".to_string(),
            description: Some("Desc".to_string()),
            task_prompt: "Prompt".to_string(),
            state: "coding".to_string(),
            previous_state: Some("draft".to_string()),
            state_changed_at: Some("2024-01-01T00:00:00Z".to_string()),
            loop_iteration: 5,
            total_time_spent_ms: 1000,
            total_cost_usd: 0.05,
            error_count: 1,
            max_retries: 5,
            worktree_path: Some("/tmp/wt".to_string()),
            branch_name: Some("card/test".to_string()),
            pull_request_url: None,
            deployment_namespace: None,
            deployment_name: None,
            argocd_app_name: None,
            labels: r#"["bug"]"#.to_string(),
            priority: 3,
            deadline: None,
            created_at: "2024-01-01T00:00:00Z".to_string(),
            updated_at: "2024-01-01T00:00:00Z".to_string(),
        };

        let card = row.to_card();
        assert_eq!(card.title, "Test");
        assert_eq!(card.state, CardState::Coding);
        assert_eq!(card.previous_state, Some(CardState::Draft));
        assert_eq!(card.loop_iteration, 5);
        assert_eq!(card.labels, vec!["bug"]);
    }

    #[tokio::test]
    async fn test_card_row_invalid_state() {
        let row = CardRow {
            id: "550e8400-e29b-41d4-a716-446655440000".to_string(),
            project_id: "550e8400-e29b-41d4-a716-446655440001".to_string(),
            title: "Test".to_string(),
            description: None,
            task_prompt: "Prompt".to_string(),
            state: "invalid_state".to_string(),
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
            labels: "[]".to_string(),
            priority: 0,
            deadline: None,
            created_at: "2024-01-01T00:00:00Z".to_string(),
            updated_at: "2024-01-01T00:00:00Z".to_string(),
        };

        let card = row.to_card();
        assert_eq!(card.state, CardState::Draft);
    }
}
