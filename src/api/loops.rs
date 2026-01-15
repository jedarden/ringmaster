//! Loop API routes

use axum::{
    extract::{Path, State},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db;
use crate::domain::Attempt;
use crate::events::Event;
use crate::loops::{LoopConfig, LoopState, LoopStatus};

use super::{ApiResponse, AppError, AppState, Pagination, PaginatedResponse};

/// Create loop routes for a card
pub fn loop_routes() -> Router<AppState> {
    Router::new()
        .route("/:card_id/loop", get(get_loop_state))
        .route("/:card_id/loop/start", post(start_loop))
        .route("/:card_id/loop/pause", post(pause_loop))
        .route("/:card_id/loop/resume", post(resume_loop))
        .route("/:card_id/loop/stop", post(stop_loop))
        .route("/:card_id/attempts", get(list_attempts))
        .route("/:card_id/attempts/:attempt_id", get(get_attempt))
}

/// Create global loop routes
pub fn global_loop_routes() -> Router<AppState> {
    Router::new().route("/", get(list_active_loops))
}

#[derive(Debug, Deserialize)]
pub struct StartLoopRequest {
    pub config: Option<LoopConfigOverride>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopConfigOverride {
    pub max_iterations: Option<u32>,
    pub max_runtime_seconds: Option<u64>,
    pub max_cost_usd: Option<f64>,
    pub checkpoint_interval: Option<u32>,
    pub cooldown_seconds: Option<u64>,
    pub completion_signal: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopStartResponse {
    pub loop_id: String,
    pub card_id: Uuid,
    pub state: LoopState,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopStopResponse {
    pub status: String,
    pub final_iteration: i32,
    pub total_cost_usd: f64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveLoopInfo {
    pub card_id: Uuid,
    pub card_title: String,
    pub iteration: i32,
    pub status: LoopStatus,
    pub total_cost_usd: f64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveLoopsResponse {
    pub loops: Vec<ActiveLoopInfo>,
    pub stats: ActiveLoopsStats,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveLoopsStats {
    pub total_active: usize,
    pub running: usize,
    pub paused: usize,
    pub total_cost_usd: f64,
    pub total_iterations: i64,
}

async fn get_loop_state(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<Json<ApiResponse<Option<LoopState>>>, AppError> {
    let loop_manager = state.loop_manager.read().await;
    let loop_state = loop_manager.get_loop_state(&card_id);
    Ok(Json(ApiResponse::new(loop_state.cloned())))
}

async fn start_loop(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
    Json(req): Json<StartLoopRequest>,
) -> Result<Json<ApiResponse<LoopStartResponse>>, AppError> {
    // Verify card exists
    let card = db::get_card(&state.pool, &card_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Card {} not found", card_id)))?;

    // Build config with overrides
    let mut config = LoopConfig::default();
    if let Some(overrides) = req.config {
        if let Some(v) = overrides.max_iterations {
            config.max_iterations = v;
        }
        if let Some(v) = overrides.max_runtime_seconds {
            config.max_runtime_seconds = v;
        }
        if let Some(v) = overrides.max_cost_usd {
            config.max_cost_usd = v;
        }
        if let Some(v) = overrides.checkpoint_interval {
            config.checkpoint_interval = v;
        }
        if let Some(v) = overrides.cooldown_seconds {
            config.cooldown_seconds = v;
        }
        if let Some(v) = overrides.completion_signal {
            config.completion_signal = v;
        }
    }

    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager
        .start_loop(card_id, config)
        .map_err(|e| AppError::LoopError(e))?;

    // Publish event
    state.event_bus.publish(Event::LoopStarted {
        card_id: card.id,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(LoopStartResponse {
        loop_id: format!("loop-{}", card_id),
        card_id,
        state: loop_state,
    })))
}

async fn pause_loop(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<Json<ApiResponse<LoopState>>, AppError> {
    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager
        .pause_loop(&card_id)
        .map_err(|e| AppError::LoopError(e))?;

    state.event_bus.publish(Event::LoopPaused {
        card_id,
        iteration: loop_state.iteration,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(loop_state)))
}

async fn resume_loop(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<Json<ApiResponse<LoopState>>, AppError> {
    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager
        .resume_loop(&card_id)
        .map_err(|e| AppError::LoopError(e))?;

    Ok(Json(ApiResponse::new(loop_state)))
}

async fn stop_loop(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
) -> Result<Json<ApiResponse<LoopStopResponse>>, AppError> {
    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager
        .stop_loop(&card_id)
        .map_err(|e| AppError::LoopError(e))?;

    Ok(Json(ApiResponse::new(LoopStopResponse {
        status: "stopped".to_string(),
        final_iteration: loop_state.iteration,
        total_cost_usd: loop_state.total_cost_usd,
    })))
}

async fn list_active_loops(
    State(state): State<AppState>,
) -> Result<Json<ApiResponse<ActiveLoopsResponse>>, AppError> {
    let loop_manager = state.loop_manager.read().await;
    let active_loops = loop_manager.list_active_loops();

    let mut loops = Vec::new();
    let mut running = 0;
    let mut paused = 0;
    let mut total_cost = 0.0;
    let mut total_iterations: i64 = 0;

    for (card_id, loop_state) in active_loops {
        // Get card title
        let card_title = db::get_card(&state.pool, &card_id.to_string())
            .await
            .ok()
            .flatten()
            .map(|c| c.title)
            .unwrap_or_else(|| "Unknown".to_string());

        match loop_state.status {
            LoopStatus::Running => running += 1,
            LoopStatus::Paused => paused += 1,
            _ => {}
        }

        total_cost += loop_state.total_cost_usd;
        total_iterations += loop_state.iteration as i64;

        loops.push(ActiveLoopInfo {
            card_id: *card_id,
            card_title,
            iteration: loop_state.iteration,
            status: loop_state.status,
            total_cost_usd: loop_state.total_cost_usd,
        });
    }

    Ok(Json(ApiResponse::new(ActiveLoopsResponse {
        stats: ActiveLoopsStats {
            total_active: loops.len(),
            running,
            paused,
            total_cost_usd: total_cost,
            total_iterations,
        },
        loops,
    })))
}

#[derive(Debug, Deserialize)]
pub struct ListAttemptsQuery {
    pub status: Option<String>,
    pub limit: Option<i32>,
    pub offset: Option<i32>,
}

async fn list_attempts(
    State(state): State<AppState>,
    Path(card_id): Path<Uuid>,
    axum::extract::Query(query): axum::extract::Query<ListAttemptsQuery>,
) -> Result<Json<PaginatedResponse<Attempt>>, AppError> {
    let limit = query.limit.unwrap_or(20).min(100);
    let offset = query.offset.unwrap_or(0);

    let attempts = db::list_attempts(&state.pool, &card_id.to_string(), limit, offset).await?;
    let total = db::count_attempts(&state.pool, &card_id.to_string()).await?;

    Ok(Json(PaginatedResponse {
        data: attempts,
        pagination: Pagination {
            total,
            limit,
            offset,
            has_more: total > (offset as i64 + limit as i64),
        },
    }))
}

async fn get_attempt(
    State(state): State<AppState>,
    Path((card_id, attempt_id)): Path<(Uuid, Uuid)>,
) -> Result<Json<ApiResponse<Attempt>>, AppError> {
    let _ = card_id; // Validate card ownership if needed

    let attempt = db::get_attempt(&state.pool, &attempt_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Attempt {} not found", attempt_id)))?;

    Ok(Json(ApiResponse::new(attempt)))
}
