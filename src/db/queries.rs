//! Database queries for all entities

use chrono::{DateTime, Utc};
use sqlx::SqlitePool;
use uuid::Uuid;

use crate::domain::*;
use super::models::*;

/// Convert a CardRow to a Card domain model
pub fn card_row_to_domain(row: CardRow) -> Result<Card, String> {
    Ok(Card {
        id: Uuid::parse_str(&row.id).map_err(|e| e.to_string())?,
        project_id: Uuid::parse_str(&row.project_id).map_err(|e| e.to_string())?,
        title: row.title,
        description: row.description,
        task_prompt: row.task_prompt,
        state: row.state.parse()?,
        previous_state: row.previous_state.as_ref().map(|s| s.parse()).transpose()?,
        state_changed_at: row.state_changed_at.as_ref().map(|s| {
            DateTime::parse_from_rfc3339(s)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now())
        }),
        loop_iteration: row.loop_iteration,
        total_time_spent_ms: row.total_time_spent_ms,
        total_cost_usd: row.total_cost_usd,
        error_count: row.error_count,
        max_retries: row.max_retries,
        worktree_path: row.worktree_path,
        branch_name: row.branch_name,
        pull_request_url: row.pull_request_url,
        deployment_namespace: row.deployment_namespace,
        deployment_name: row.deployment_name,
        argocd_app_name: row.argocd_app_name,
        labels: serde_json::from_str(&row.labels).unwrap_or_default(),
        priority: row.priority,
        deadline: row.deadline.as_ref().map(|s| {
            DateTime::parse_from_rfc3339(s)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now())
        }),
        created_at: DateTime::parse_from_rfc3339(&row.created_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
        updated_at: DateTime::parse_from_rfc3339(&row.updated_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
    })
}

/// Convert a ProjectRow to a Project domain model
pub fn project_row_to_domain(row: ProjectRow) -> Result<Project, String> {
    Ok(Project {
        id: Uuid::parse_str(&row.id).map_err(|e| e.to_string())?,
        name: row.name,
        description: row.description,
        repository_url: row.repository_url,
        repository_path: row.repository_path,
        tech_stack: serde_json::from_str(&row.tech_stack).unwrap_or_default(),
        coding_conventions: row.coding_conventions,
        created_at: DateTime::parse_from_rfc3339(&row.created_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
        updated_at: DateTime::parse_from_rfc3339(&row.updated_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
    })
}

// =============================================================================
// PROJECT QUERIES
// =============================================================================

/// Get all projects
pub async fn get_projects(pool: &SqlitePool) -> Result<Vec<Project>, sqlx::Error> {
    let rows = sqlx::query_as::<_, ProjectRow>("SELECT * FROM projects ORDER BY name")
        .fetch_all(pool)
        .await?;

    Ok(rows
        .into_iter()
        .filter_map(|r| project_row_to_domain(r).ok())
        .collect())
}

/// Get a project by ID
pub async fn get_project(pool: &SqlitePool, id: &Uuid) -> Result<Option<Project>, sqlx::Error> {
    let row = sqlx::query_as::<_, ProjectRow>("SELECT * FROM projects WHERE id = ?")
        .bind(id.to_string())
        .fetch_optional(pool)
        .await?;

    Ok(row.and_then(|r| project_row_to_domain(r).ok()))
}

/// Create a new project
pub async fn create_project(pool: &SqlitePool, project: &Project) -> Result<(), sqlx::Error> {
    let tech_stack_json = serde_json::to_string(&project.tech_stack).unwrap_or_default();

    sqlx::query(
        r#"
        INSERT INTO projects (id, name, description, repository_url, repository_path, tech_stack, coding_conventions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(project.id.to_string())
    .bind(&project.name)
    .bind(&project.description)
    .bind(&project.repository_url)
    .bind(&project.repository_path)
    .bind(&tech_stack_json)
    .bind(&project.coding_conventions)
    .bind(project.created_at.to_rfc3339())
    .bind(project.updated_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

/// Update a project
pub async fn update_project(pool: &SqlitePool, project: &Project) -> Result<(), sqlx::Error> {
    let tech_stack_json = serde_json::to_string(&project.tech_stack).unwrap_or_default();

    sqlx::query(
        r#"
        UPDATE projects
        SET name = ?, description = ?, repository_url = ?, repository_path = ?,
            tech_stack = ?, coding_conventions = ?, updated_at = ?
        WHERE id = ?
        "#,
    )
    .bind(&project.name)
    .bind(&project.description)
    .bind(&project.repository_url)
    .bind(&project.repository_path)
    .bind(&tech_stack_json)
    .bind(&project.coding_conventions)
    .bind(Utc::now().to_rfc3339())
    .bind(project.id.to_string())
    .execute(pool)
    .await?;

    Ok(())
}

/// Delete a project
pub async fn delete_project(pool: &SqlitePool, id: &Uuid) -> Result<(), sqlx::Error> {
    sqlx::query("DELETE FROM projects WHERE id = ?")
        .bind(id.to_string())
        .execute(pool)
        .await?;

    Ok(())
}

// =============================================================================
// CARD QUERIES
// =============================================================================

/// Get cards with optional filters
pub async fn get_cards(
    pool: &SqlitePool,
    project_id: Option<&Uuid>,
    states: Option<&[CardState]>,
    labels: Option<&[String]>,
    search: Option<&str>,
    limit: i32,
    offset: i32,
) -> Result<Vec<Card>, sqlx::Error> {
    let mut query = String::from("SELECT * FROM cards WHERE 1=1");
    let mut args: Vec<String> = Vec::new();

    if let Some(pid) = project_id {
        query.push_str(" AND project_id = ?");
        args.push(pid.to_string());
    }

    if let Some(states) = states {
        if !states.is_empty() {
            let placeholders: Vec<_> = states.iter().map(|_| "?").collect();
            query.push_str(&format!(" AND state IN ({})", placeholders.join(",")));
            for state in states {
                args.push(state.to_string());
            }
        }
    }

    if let Some(search) = search {
        query.push_str(" AND (title LIKE ? OR description LIKE ?)");
        args.push(format!("%{}%", search));
        args.push(format!("%{}%", search));
    }

    query.push_str(" ORDER BY priority DESC, updated_at DESC LIMIT ? OFFSET ?");
    args.push(limit.to_string());
    args.push(offset.to_string());

    // Build and execute dynamic query
    let mut q = sqlx::query_as::<_, CardRow>(&query);
    for arg in &args {
        q = q.bind(arg);
    }

    let rows = q.fetch_all(pool).await?;

    // Filter by labels in memory if provided (JSON array makes SQL filtering complex)
    let cards: Vec<Card> = rows
        .into_iter()
        .filter_map(|r| card_row_to_domain(r).ok())
        .filter(|card| {
            if let Some(filter_labels) = labels {
                filter_labels.iter().any(|l| card.labels.contains(l))
            } else {
                true
            }
        })
        .collect();

    Ok(cards)
}

/// Get a card by ID
pub async fn get_card(pool: &SqlitePool, id: &Uuid) -> Result<Option<Card>, sqlx::Error> {
    let row = sqlx::query_as::<_, CardRow>("SELECT * FROM cards WHERE id = ?")
        .bind(id.to_string())
        .fetch_optional(pool)
        .await?;

    Ok(row.and_then(|r| card_row_to_domain(r).ok()))
}

/// Create a new card
pub async fn create_card(pool: &SqlitePool, card: &Card) -> Result<(), sqlx::Error> {
    let labels_json = serde_json::to_string(&card.labels).unwrap_or_default();

    sqlx::query(
        r#"
        INSERT INTO cards (
            id, project_id, title, description, task_prompt, state, previous_state,
            state_changed_at, loop_iteration, total_time_spent_ms, total_cost_usd,
            error_count, max_retries, worktree_path, branch_name, pull_request_url,
            deployment_namespace, deployment_name, argocd_app_name, labels, priority,
            deadline, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(card.id.to_string())
    .bind(card.project_id.to_string())
    .bind(&card.title)
    .bind(&card.description)
    .bind(&card.task_prompt)
    .bind(card.state.as_str())
    .bind(card.previous_state.map(|s| s.as_str().to_string()))
    .bind(card.state_changed_at.map(|dt| dt.to_rfc3339()))
    .bind(card.loop_iteration)
    .bind(card.total_time_spent_ms)
    .bind(card.total_cost_usd)
    .bind(card.error_count)
    .bind(card.max_retries)
    .bind(&card.worktree_path)
    .bind(&card.branch_name)
    .bind(&card.pull_request_url)
    .bind(&card.deployment_namespace)
    .bind(&card.deployment_name)
    .bind(&card.argocd_app_name)
    .bind(&labels_json)
    .bind(card.priority)
    .bind(card.deadline.map(|dt| dt.to_rfc3339()))
    .bind(card.created_at.to_rfc3339())
    .bind(card.updated_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

/// Update a card
pub async fn update_card(pool: &SqlitePool, card: &Card) -> Result<(), sqlx::Error> {
    let labels_json = serde_json::to_string(&card.labels).unwrap_or_default();

    sqlx::query(
        r#"
        UPDATE cards
        SET title = ?, description = ?, task_prompt = ?, state = ?, previous_state = ?,
            state_changed_at = ?, loop_iteration = ?, total_time_spent_ms = ?, total_cost_usd = ?,
            error_count = ?, max_retries = ?, worktree_path = ?, branch_name = ?,
            pull_request_url = ?, deployment_namespace = ?, deployment_name = ?,
            argocd_app_name = ?, labels = ?, priority = ?, deadline = ?, updated_at = ?
        WHERE id = ?
        "#,
    )
    .bind(&card.title)
    .bind(&card.description)
    .bind(&card.task_prompt)
    .bind(card.state.as_str())
    .bind(card.previous_state.map(|s| s.as_str().to_string()))
    .bind(card.state_changed_at.map(|dt| dt.to_rfc3339()))
    .bind(card.loop_iteration)
    .bind(card.total_time_spent_ms)
    .bind(card.total_cost_usd)
    .bind(card.error_count)
    .bind(card.max_retries)
    .bind(&card.worktree_path)
    .bind(&card.branch_name)
    .bind(&card.pull_request_url)
    .bind(&card.deployment_namespace)
    .bind(&card.deployment_name)
    .bind(&card.argocd_app_name)
    .bind(&labels_json)
    .bind(card.priority)
    .bind(card.deadline.map(|dt| dt.to_rfc3339()))
    .bind(Utc::now().to_rfc3339())
    .bind(card.id.to_string())
    .execute(pool)
    .await?;

    Ok(())
}

/// Update card state and record transition
pub async fn update_card_state(
    pool: &SqlitePool,
    card_id: &Uuid,
    new_state: CardState,
    previous_state: CardState,
    trigger: &str,
) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;
    let now = Utc::now().to_rfc3339();

    // Update card state
    sqlx::query(
        r#"
        UPDATE cards
        SET state = ?, previous_state = ?, state_changed_at = ?, updated_at = ?
        WHERE id = ?
        "#,
    )
    .bind(new_state.as_str())
    .bind(previous_state.as_str())
    .bind(&now)
    .bind(&now)
    .bind(card_id.to_string())
    .execute(&mut *tx)
    .await?;

    // Record state transition
    let trans_id = Uuid::new_v4().to_string();
    sqlx::query(
        r#"
        INSERT INTO state_transitions (id, card_id, from_state, to_state, trigger, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&trans_id)
    .bind(card_id.to_string())
    .bind(previous_state.as_str())
    .bind(new_state.as_str())
    .bind(trigger)
    .bind(&now)
    .execute(&mut *tx)
    .await?;

    tx.commit().await?;

    Ok(())
}

/// Delete a card
pub async fn delete_card(pool: &SqlitePool, id: &Uuid) -> Result<(), sqlx::Error> {
    sqlx::query("DELETE FROM cards WHERE id = ?")
        .bind(id.to_string())
        .execute(pool)
        .await?;

    Ok(())
}

// =============================================================================
// ACCEPTANCE CRITERIA QUERIES
// =============================================================================

/// Get acceptance criteria for a card
pub async fn get_acceptance_criteria(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<Vec<AcceptanceCriteria>, sqlx::Error> {
    let rows = sqlx::query_as::<_, AcceptanceCriteriaRow>(
        "SELECT * FROM acceptance_criteria WHERE card_id = ? ORDER BY order_index",
    )
    .bind(card_id.to_string())
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .filter_map(|r| {
            Some(AcceptanceCriteria {
                id: Uuid::parse_str(&r.id).ok()?,
                card_id: Uuid::parse_str(&r.card_id).ok()?,
                description: r.description,
                met: r.met != 0,
                met_at: r.met_at.as_ref().and_then(|s| {
                    DateTime::parse_from_rfc3339(s)
                        .map(|dt| dt.with_timezone(&Utc))
                        .ok()
                }),
                order_index: r.order_index,
                created_at: DateTime::parse_from_rfc3339(&r.created_at)
                    .map(|dt| dt.with_timezone(&Utc))
                    .unwrap_or_else(|_| Utc::now()),
            })
        })
        .collect())
}

/// Create acceptance criteria
pub async fn create_acceptance_criteria(
    pool: &SqlitePool,
    criteria: &AcceptanceCriteria,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO acceptance_criteria (id, card_id, description, met, met_at, order_index, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(criteria.id.to_string())
    .bind(criteria.card_id.to_string())
    .bind(&criteria.description)
    .bind(criteria.met as i32)
    .bind(criteria.met_at.map(|dt| dt.to_rfc3339()))
    .bind(criteria.order_index)
    .bind(criteria.created_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

// =============================================================================
// ATTEMPT QUERIES
// =============================================================================

/// Get attempts for a card
pub async fn get_attempts(
    pool: &SqlitePool,
    card_id: &Uuid,
    limit: i32,
    offset: i32,
) -> Result<Vec<Attempt>, sqlx::Error> {
    let rows = sqlx::query_as::<_, AttemptRow>(
        "SELECT * FROM attempts WHERE card_id = ? ORDER BY attempt_number DESC LIMIT ? OFFSET ?",
    )
    .bind(card_id.to_string())
    .bind(limit)
    .bind(offset)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .filter_map(|r| attempt_row_to_domain(r).ok())
        .collect())
}

/// Create a new attempt
pub async fn create_attempt(pool: &SqlitePool, attempt: &Attempt) -> Result<(), sqlx::Error> {
    let diff_stats_json = attempt
        .diff_stats
        .as_ref()
        .map(|d| serde_json::to_string(d).unwrap_or_default());

    sqlx::query(
        r#"
        INSERT INTO attempts (
            id, card_id, attempt_number, agent_type, status, started_at,
            completed_at, duration_ms, tokens_used, cost_usd, output,
            error_message, commit_sha, diff_stats
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(attempt.id.to_string())
    .bind(attempt.card_id.to_string())
    .bind(attempt.attempt_number)
    .bind(&attempt.agent_type)
    .bind(attempt.status.to_string())
    .bind(attempt.started_at.to_rfc3339())
    .bind(attempt.completed_at.map(|dt| dt.to_rfc3339()))
    .bind(attempt.duration_ms)
    .bind(attempt.tokens_used)
    .bind(attempt.cost_usd)
    .bind(&attempt.output)
    .bind(&attempt.error_message)
    .bind(&attempt.commit_sha)
    .bind(&diff_stats_json)
    .execute(pool)
    .await?;

    Ok(())
}

/// Update an attempt
pub async fn update_attempt(pool: &SqlitePool, attempt: &Attempt) -> Result<(), sqlx::Error> {
    let diff_stats_json = attempt
        .diff_stats
        .as_ref()
        .map(|d| serde_json::to_string(d).unwrap_or_default());

    sqlx::query(
        r#"
        UPDATE attempts
        SET status = ?, completed_at = ?, duration_ms = ?, tokens_used = ?,
            cost_usd = ?, output = ?, error_message = ?, commit_sha = ?, diff_stats = ?
        WHERE id = ?
        "#,
    )
    .bind(attempt.status.to_string())
    .bind(attempt.completed_at.map(|dt| dt.to_rfc3339()))
    .bind(attempt.duration_ms)
    .bind(attempt.tokens_used)
    .bind(attempt.cost_usd)
    .bind(&attempt.output)
    .bind(&attempt.error_message)
    .bind(&attempt.commit_sha)
    .bind(&diff_stats_json)
    .bind(attempt.id.to_string())
    .execute(pool)
    .await?;

    Ok(())
}

fn attempt_row_to_domain(row: AttemptRow) -> Result<Attempt, String> {
    Ok(Attempt {
        id: Uuid::parse_str(&row.id).map_err(|e| e.to_string())?,
        card_id: Uuid::parse_str(&row.card_id).map_err(|e| e.to_string())?,
        attempt_number: row.attempt_number,
        agent_type: row.agent_type,
        status: row.status.parse()?,
        started_at: DateTime::parse_from_rfc3339(&row.started_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
        completed_at: row.completed_at.as_ref().and_then(|s| {
            DateTime::parse_from_rfc3339(s)
                .map(|dt| dt.with_timezone(&Utc))
                .ok()
        }),
        duration_ms: row.duration_ms,
        tokens_used: row.tokens_used,
        cost_usd: row.cost_usd,
        output: row.output,
        error_message: row.error_message,
        commit_sha: row.commit_sha,
        diff_stats: row.diff_stats.as_ref().and_then(|s| serde_json::from_str(s).ok()),
    })
}

// =============================================================================
// ERROR QUERIES
// =============================================================================

/// Get errors for a card
pub async fn get_errors(
    pool: &SqlitePool,
    card_id: &Uuid,
    resolved: Option<bool>,
    category: Option<&str>,
    limit: i32,
    offset: i32,
) -> Result<Vec<CardError>, sqlx::Error> {
    let mut query = String::from("SELECT * FROM errors WHERE card_id = ?");
    let mut args: Vec<String> = vec![card_id.to_string()];

    if let Some(resolved) = resolved {
        query.push_str(" AND resolved = ?");
        args.push((resolved as i32).to_string());
    }

    if let Some(category) = category {
        query.push_str(" AND category = ?");
        args.push(category.to_string());
    }

    query.push_str(" ORDER BY created_at DESC LIMIT ? OFFSET ?");
    args.push(limit.to_string());
    args.push(offset.to_string());

    let mut q = sqlx::query_as::<_, ErrorRow>(&query);
    for arg in &args {
        q = q.bind(arg);
    }

    let rows = q.fetch_all(pool).await?;

    Ok(rows
        .into_iter()
        .filter_map(|r| error_row_to_domain(r).ok())
        .collect())
}

/// Create an error
pub async fn create_error(pool: &SqlitePool, error: &CardError) -> Result<(), sqlx::Error> {
    let context_json = error
        .context
        .as_ref()
        .map(|c| serde_json::to_string(c).unwrap_or_default());

    sqlx::query(
        r#"
        INSERT INTO errors (
            id, card_id, attempt_id, error_type, message, stack_trace, context,
            category, severity, resolved, resolved_at, resolution_attempt_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(error.id.to_string())
    .bind(error.card_id.to_string())
    .bind(error.attempt_id.map(|id| id.to_string()))
    .bind(&error.error_type)
    .bind(&error.message)
    .bind(&error.stack_trace)
    .bind(&context_json)
    .bind(error.category.map(|c| c.to_string()))
    .bind(error.severity.to_string())
    .bind(error.resolved as i32)
    .bind(error.resolved_at.map(|dt| dt.to_rfc3339()))
    .bind(error.resolution_attempt_id.map(|id| id.to_string()))
    .bind(error.created_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

fn error_row_to_domain(row: ErrorRow) -> Result<CardError, String> {
    Ok(CardError {
        id: Uuid::parse_str(&row.id).map_err(|e| e.to_string())?,
        card_id: Uuid::parse_str(&row.card_id).map_err(|e| e.to_string())?,
        attempt_id: row
            .attempt_id
            .as_ref()
            .map(|s| Uuid::parse_str(s))
            .transpose()
            .map_err(|e| e.to_string())?,
        error_type: row.error_type,
        message: row.message,
        stack_trace: row.stack_trace,
        context: row
            .context
            .as_ref()
            .and_then(|s| serde_json::from_str(s).ok()),
        category: row.category.as_ref().and_then(|s| s.parse().ok()),
        severity: row.severity.parse().unwrap_or(ErrorSeverity::Error),
        resolved: row.resolved != 0,
        resolved_at: row.resolved_at.as_ref().and_then(|s| {
            DateTime::parse_from_rfc3339(s)
                .map(|dt| dt.with_timezone(&Utc))
                .ok()
        }),
        resolution_attempt_id: row
            .resolution_attempt_id
            .as_ref()
            .map(|s| Uuid::parse_str(s))
            .transpose()
            .map_err(|e| e.to_string())?,
        created_at: DateTime::parse_from_rfc3339(&row.created_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now()),
    })
}

// =============================================================================
// LOOP SNAPSHOT QUERIES
// =============================================================================

/// Create a loop snapshot
pub async fn create_loop_snapshot(
    pool: &SqlitePool,
    snapshot: &LoopSnapshot,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO loop_snapshots (id, card_id, iteration, state, checkpoint_commit, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(snapshot.id.to_string())
    .bind(snapshot.card_id.to_string())
    .bind(snapshot.iteration)
    .bind(snapshot.state.to_string())
    .bind(&snapshot.checkpoint_commit)
    .bind(snapshot.created_at.to_rfc3339())
    .execute(pool)
    .await?;

    Ok(())
}

/// Get latest loop snapshot for a card
pub async fn get_latest_snapshot(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<Option<LoopSnapshot>, sqlx::Error> {
    let row = sqlx::query_as::<_, LoopSnapshotRow>(
        "SELECT * FROM loop_snapshots WHERE card_id = ? ORDER BY iteration DESC LIMIT 1",
    )
    .bind(card_id.to_string())
    .fetch_optional(pool)
    .await?;

    Ok(row.and_then(|r| {
        Some(LoopSnapshot {
            id: Uuid::parse_str(&r.id).ok()?,
            card_id: Uuid::parse_str(&r.card_id).ok()?,
            iteration: r.iteration,
            state: serde_json::from_str(&r.state).ok()?,
            checkpoint_commit: r.checkpoint_commit,
            created_at: DateTime::parse_from_rfc3339(&r.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        })
    }))
}
