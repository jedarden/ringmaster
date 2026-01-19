//! Card API routes

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{delete, get, patch, post},
    Json, Router,
};
use serde::Deserialize;
use uuid::Uuid;

use crate::db;
use crate::domain::{
    Card, CardDetail, CreateCardRequest, TransitionRequest, TransitionResult, Trigger,
    UpdateCardRequest,
};
use crate::events::Event;
use crate::state_machine::CardStateMachine;

use super::{ApiResponse, AppError, AppState, Pagination, PaginatedResponse};

/// Create card routes
pub fn card_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(list_cards))
        .route("/", post(create_card))
        .route("/:card_id", get(get_card))
        .route("/:card_id", patch(update_card))
        .route("/:card_id", delete(delete_card))
        .route("/:card_id/transition", post(transition_card))
}

#[derive(Debug, Deserialize)]
pub struct ListCardsQuery {
    pub project_id: Option<Uuid>,
    pub state: Option<String>,
    pub labels: Option<String>,
    pub search: Option<String>,
    pub limit: Option<i32>,
    pub offset: Option<i32>,
    pub sort: Option<String>,
    pub order: Option<String>,
}

async fn list_cards(
    State(state): State<AppState>,
    Query(query): Query<ListCardsQuery>,
) -> Result<Json<PaginatedResponse<Card>>, AppError> {
    let limit = query.limit.unwrap_or(50).min(100);
    let offset = query.offset.unwrap_or(0);

    let project_id = query.project_id.map(|id| id.to_string());
    let states: Option<Vec<&str>> = query
        .state
        .as_ref()
        .map(|s| s.split(',').collect());

    let cards = db::list_cards(
        &state.pool,
        project_id.as_deref(),
        states.as_deref(),
        limit,
        offset,
    )
    .await?;

    // Get total count - simplified for now
    let total = cards.len() as i64;

    Ok(Json(PaginatedResponse {
        data: cards,
        pagination: Pagination {
            total,
            limit,
            offset,
            has_more: total > (offset as i64 + limit as i64),
        },
    }))
}

async fn get_card(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<Json<ApiResponse<CardDetail>>, AppError> {
    let card = db::get_card(&state.pool, &card_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    let acceptance_criteria = db::get_acceptance_criteria(&state.pool, &card_id.to_string()).await?;

    // Dependencies would need another query - simplified for now
    let dependencies = Vec::new();

    Ok(Json(ApiResponse::new(CardDetail {
        card,
        acceptance_criteria,
        dependencies,
    })))
}

async fn create_card(
    State(state): State<AppState>,
    Json(req): Json<CreateCardRequest>,
) -> Result<(StatusCode, Json<ApiResponse<Card>>), AppError> {
    let card = db::create_card(&state.pool, &req).await?;

    // Publish event
    state.event_bus.publish(Event::CardCreated {
        card_id: card.id,
        project_id: card.project_id,
        timestamp: chrono::Utc::now(),
    });

    Ok((StatusCode::CREATED, Json(ApiResponse::new(card))))
}

async fn update_card(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
    Json(req): Json<UpdateCardRequest>,
) -> Result<Json<ApiResponse<Card>>, AppError> {
    let card = db::update_card(&state.pool, &card_id.to_string(), &req)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    // Publish event
    state.event_bus.publish(Event::CardUpdated {
        card_id: card.id,
        card: Box::new(card.clone()),
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(card)))
}

async fn delete_card(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<StatusCode, AppError> {
    let deleted = db::delete_card(&state.pool, &card_id.to_string()).await?;

    if deleted {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(AppError::NotFound(format!("Card {} not found", card_id)))
    }
}

async fn transition_card(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
    Json(req): Json<TransitionRequest>,
) -> Result<Json<ApiResponse<TransitionResult>>, AppError> {
    let mut card = db::get_card(&state.pool, &card_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    let trigger: Trigger = req
        .trigger
        .parse()
        .map_err(|_| AppError::BadRequest(format!("Unknown trigger: {}", req.trigger)))?;

    let machine = CardStateMachine::new();
    let previous_state = card.state;

    let (new_state, actions) = machine
        .transition(&mut card, trigger)
        .map_err(|e| match e {
            crate::state_machine::TransitionError::InvalidTransition { from, trigger } => {
                AppError::InvalidTransition(format!(
                    "Cannot transition from {} with trigger {}",
                    from, trigger
                ))
            }
            crate::state_machine::TransitionError::GuardFailed { guard } => {
                AppError::GuardFailed(format!("Guard condition not met: {:?}", guard))
            }
            crate::state_machine::TransitionError::ActionFailed { action, message } => {
                AppError::InternalError(format!("Action {:?} failed: {}", action, message))
            }
        })?;

    // Update in database
    db::update_card_state(
        &state.pool,
        &card_id.to_string(),
        new_state.as_str(),
        previous_state.as_str(),
        &trigger.to_string(),
    )
    .await?;

    // Publish event
    state.event_bus.publish(Event::StateChanged {
        card_id: card.id,
        from_state: previous_state,
        to_state: new_state,
        trigger,
        timestamp: chrono::Utc::now(),
    });

    // Refresh card from DB to get updated state
    let card = db::get_card(&state.pool, &card_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    // Execute actions for the transition
    if !actions.is_empty() {
        // Get project for the card
        let project = db::get_project(&state.pool, &card.project_id.to_string())
            .await?
            .ok_or_else(|| AppError::NotFound(format!("Project {} not found", card.project_id)))?;

        // Execute actions (fire-and-forget for non-blocking actions, or await for critical ones)
        let action_executor = state.action_executor.clone();
        let card_for_actions = card.clone();
        tokio::spawn(async move {
            if let Err(e) = action_executor
                .execute_all(&card_for_actions, &project, &actions)
                .await
            {
                tracing::error!(
                    "Failed to execute actions for card {}: {}",
                    card_for_actions.id,
                    e
                );
            }
        });
    }

    Ok(Json(ApiResponse::new(TransitionResult {
        previous_state,
        new_state,
        card,
    })))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    /// Create an in-memory test database
    async fn setup_test_db() -> sqlx::SqlitePool {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        // Run migrations
        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        pool
    }

    /// Create test AppState
    async fn create_test_state() -> AppState {
        let pool = setup_test_db().await;
        let event_bus = crate::events::EventBus::new();
        let loop_manager = std::sync::Arc::new(tokio::sync::RwLock::new(
            crate::loops::LoopManager::new(),
        ));
        let action_executor = std::sync::Arc::new(crate::state_machine::ActionExecutor::new(
            pool.clone(),
            event_bus.clone(),
            loop_manager.clone(),
        ));

        AppState {
            pool,
            event_bus,
            loop_manager,
            action_executor,
        }
    }

    /// Create a test project in the database
    async fn create_test_project(pool: &sqlx::SqlitePool) -> Uuid {
        let id = Uuid::new_v4();
        sqlx::query(
            "INSERT INTO projects (id, name, repository_url) VALUES (?, 'Test Project', 'https://github.com/test/repo')",
        )
        .bind(id.to_string())
        .execute(pool)
        .await
        .expect("Failed to create test project");
        id
    }

    #[tokio::test]
    async fn test_list_cards_empty() {
        let state = create_test_state().await;
        let app = Router::new()
            .route("/cards", get(list_cards))
            .with_state(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/cards")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_create_and_get_card() {
        let state = create_test_state().await;
        let project_id = create_test_project(&state.pool).await;

        let app = Router::new()
            .route("/cards", post(create_card))
            .route("/cards/:card_id", get(get_card))
            .with_state(state);

        // Create a card (using camelCase per API conventions)
        let create_body = serde_json::json!({
            "projectId": project_id.to_string(),
            "title": "Test Card",
            "taskPrompt": "Implement a test feature"
        });

        let response = app.clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/cards")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&create_body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        let status = response.status();
        let body_bytes = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();

        // Debug: print response body if not successful
        if status != StatusCode::CREATED {
            let body = String::from_utf8_lossy(&body_bytes);
            panic!("Expected CREATED, got {}: {}", status, body);
        }
        let resp: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        let card_id = resp["data"]["id"].as_str().unwrap();

        // Get the card
        let response = app
            .oneshot(
                Request::builder()
                    .uri(format!("/cards/{}", card_id))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_get_card_not_found() {
        let state = create_test_state().await;
        let app = Router::new()
            .route("/cards/:card_id", get(get_card))
            .with_state(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri(format!("/cards/{}", Uuid::new_v4()))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_transition_card() {
        let state = create_test_state().await;
        let project_id = create_test_project(&state.pool).await;

        // Create a card directly in the database
        let card_id = Uuid::new_v4();
        sqlx::query(
            "INSERT INTO cards (id, project_id, title, task_prompt, state) VALUES (?, ?, 'Test Card', 'Test prompt', 'draft')",
        )
        .bind(card_id.to_string())
        .bind(project_id.to_string())
        .execute(&state.pool)
        .await
        .expect("Failed to create test card");

        let app = Router::new()
            .route("/cards/:card_id/transition", post(transition_card))
            .with_state(state);

        // Transition from Draft to Planning (triggers use PascalCase)
        let transition_body = serde_json::json!({
            "trigger": "StartPlanning"
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!("/cards/{}/transition", card_id))
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&transition_body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        let status = response.status();
        let body_bytes = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();

        if status != StatusCode::OK {
            let body = String::from_utf8_lossy(&body_bytes);
            panic!("Expected OK, got {}: {}", status, body);
        }

        // Parse response to verify new state
        let resp: serde_json::Value = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(resp["data"]["newState"], "planning");
        assert_eq!(resp["data"]["previousState"], "draft");
    }

    #[tokio::test]
    async fn test_invalid_transition() {
        let state = create_test_state().await;
        let project_id = create_test_project(&state.pool).await;

        // Create a card in Draft state
        let card_id = Uuid::new_v4();
        sqlx::query(
            "INSERT INTO cards (id, project_id, title, task_prompt, state) VALUES (?, ?, 'Test Card', 'Test prompt', 'draft')",
        )
        .bind(card_id.to_string())
        .bind(project_id.to_string())
        .execute(&state.pool)
        .await
        .expect("Failed to create test card");

        let app = Router::new()
            .route("/cards/:card_id/transition", post(transition_card))
            .with_state(state);

        // Try an invalid transition (Draft -> Build)
        let transition_body = serde_json::json!({
            "trigger": "BuildStarted"
        });

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!("/cards/{}/transition", card_id))
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_string(&transition_body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn test_delete_card() {
        let state = create_test_state().await;
        let project_id = create_test_project(&state.pool).await;

        // Create a card
        let card_id = Uuid::new_v4();
        sqlx::query(
            "INSERT INTO cards (id, project_id, title, task_prompt, state) VALUES (?, ?, 'Test Card', 'Test prompt', 'draft')",
        )
        .bind(card_id.to_string())
        .bind(project_id.to_string())
        .execute(&state.pool)
        .await
        .expect("Failed to create test card");

        let app = Router::new()
            .route("/cards/:card_id", delete(delete_card))
            .with_state(state);

        // Delete the card
        let response = app.clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri(format!("/cards/{}", card_id))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);

        // Try to delete again - should be not found
        let response = app
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri(format!("/cards/{}", card_id))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
}
