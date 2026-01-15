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
        card: card.clone(),
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

    let (new_state, _actions) = machine
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

    // Refresh card from DB
    let card = db::get_card(&state.pool, &card_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    Ok(Json(ApiResponse::new(TransitionResult {
        previous_state,
        new_state,
        card,
    })))
}
