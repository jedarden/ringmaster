//! Error API routes

use axum::{
    extract::{Path, Query, State},
    routing::{get, post},
    Json, Router,
};
use chrono::{DateTime, Utc};
use serde::Deserialize;
use uuid::Uuid;

use crate::domain::{CardError, ResolveErrorRequest};

use super::{ApiResponse, AppError, AppState, Pagination, PaginatedResponse};

/// Create error routes for a card
pub fn error_routes() -> Router<AppState> {
    Router::new()
        .route("/:card_id/errors", get(list_errors))
        .route("/:card_id/errors/:error_id", get(get_error))
        .route("/:card_id/errors/:error_id/resolve", post(resolve_error))
}

#[derive(Debug, Deserialize)]
pub struct ListErrorsQuery {
    pub resolved: Option<bool>,
    pub category: Option<String>,
    pub limit: Option<i32>,
    pub offset: Option<i32>,
}

#[derive(Debug, sqlx::FromRow)]
struct ErrorRow {
    id: String,
    card_id: String,
    attempt_id: Option<String>,
    error_type: String,
    message: String,
    stack_trace: Option<String>,
    context: Option<String>,
    category: Option<String>,
    severity: String,
    resolved: i32,
    resolved_at: Option<String>,
    resolution_attempt_id: Option<String>,
    created_at: String,
}

impl ErrorRow {
    fn to_card_error(&self) -> CardError {
        CardError {
            id: Uuid::parse_str(&self.id).unwrap_or_default(),
            card_id: Uuid::parse_str(&self.card_id).unwrap_or_default(),
            attempt_id: self.attempt_id.as_ref().and_then(|s| Uuid::parse_str(s).ok()),
            error_type: self.error_type.clone(),
            message: self.message.clone(),
            stack_trace: self.stack_trace.clone(),
            context: self.context.as_ref().and_then(|s| serde_json::from_str(s).ok()),
            category: self.category.as_ref().and_then(|s| s.parse().ok()),
            severity: self.severity.parse().unwrap_or(crate::domain::ErrorSeverity::Error),
            resolved: self.resolved != 0,
            resolved_at: self
                .resolved_at
                .as_ref()
                .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
                .map(|dt| dt.with_timezone(&Utc)),
            resolution_attempt_id: self
                .resolution_attempt_id
                .as_ref()
                .and_then(|s| Uuid::parse_str(s).ok()),
            created_at: DateTime::parse_from_rfc3339(&self.created_at)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now()),
        }
    }
}

async fn list_errors(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
    Query(query): Query<ListErrorsQuery>,
) -> Result<Json<PaginatedResponse<CardError>>, AppError> {
    let limit = query.limit.unwrap_or(20).min(100);
    let offset = query.offset.unwrap_or(0);

    let mut sql = String::from("SELECT * FROM errors WHERE card_id = ?");
    let mut bindings: Vec<String> = vec![card_id.to_string()];

    if let Some(resolved) = query.resolved {
        sql.push_str(" AND resolved = ?");
        bindings.push(if resolved { "1" } else { "0" }.to_string());
    }

    if let Some(category) = &query.category {
        sql.push_str(" AND category = ?");
        bindings.push(category.clone());
    }

    sql.push_str(" ORDER BY created_at DESC LIMIT ? OFFSET ?");

    let mut q = sqlx::query_as::<_, ErrorRow>(&sql);
    for binding in &bindings {
        q = q.bind(binding);
    }
    q = q.bind(limit).bind(offset);

    let rows = q.fetch_all(&state.pool).await?;
    let errors: Vec<CardError> = rows.into_iter().map(|r| r.to_card_error()).collect();

    // Count total
    let count_sql = format!(
        "SELECT COUNT(*) as count FROM errors WHERE card_id = '{}'",
        card_id
    );
    #[derive(sqlx::FromRow)]
    struct CountRow {
        count: i64,
    }
    let count: CountRow = sqlx::query_as(&count_sql)
        .fetch_one(&state.pool)
        .await
        .unwrap_or(CountRow { count: 0 });

    Ok(Json(PaginatedResponse {
        data: errors,
        pagination: Pagination {
            total: count.count,
            limit,
            offset,
            has_more: count.count > (offset as i64 + limit as i64),
        },
    }))
}

async fn get_error(
    State(state): State<AppState>,
    Path((card_id, error_id)): Path<(Uuid, Uuid)>,
) -> Result<Json<ApiResponse<CardError>>, AppError> {
    let row = sqlx::query_as::<_, ErrorRow>(
        "SELECT * FROM errors WHERE id = ? AND card_id = ?",
    )
    .bind(error_id.to_string())
    .bind(card_id.to_string())
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| AppError::NotFound(format!("Error {} not found", error_id)))?;

    Ok(Json(ApiResponse::new(row.to_card_error())))
}

async fn resolve_error(
    State(state): State<AppState>,
    Path((card_id, error_id)): Path<(Uuid, Uuid)>,
    Json(req): Json<ResolveErrorRequest>,
) -> Result<Json<ApiResponse<CardError>>, AppError> {
    let resolution_id = req
        .resolution_attempt_id
        .map(|id| id.to_string());

    sqlx::query(
        r#"
        UPDATE errors
        SET resolved = 1, resolved_at = datetime('now'), resolution_attempt_id = ?
        WHERE id = ? AND card_id = ?
        "#,
    )
    .bind(&resolution_id)
    .bind(error_id.to_string())
    .bind(card_id.to_string())
    .execute(&state.pool)
    .await?;

    let row = sqlx::query_as::<_, ErrorRow>(
        "SELECT * FROM errors WHERE id = ? AND card_id = ?",
    )
    .bind(error_id.to_string())
    .bind(card_id.to_string())
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| AppError::NotFound(format!("Error {} not found", error_id)))?;

    Ok(Json(ApiResponse::new(row.to_card_error())))
}

/// Create a new error record
pub async fn create_error(
    pool: &sqlx::SqlitePool,
    error: &CardError,
) -> Result<(), sqlx::Error> {
    let context_json = error
        .context
        .as_ref()
        .and_then(|c| serde_json::to_string(c).ok());

    sqlx::query(
        r#"
        INSERT INTO errors (id, card_id, attempt_id, error_type, message, stack_trace, context, category, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    .execute(pool)
    .await?;

    Ok(())
}
