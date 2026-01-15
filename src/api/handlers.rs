//! API request handlers

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use uuid::Uuid;

use crate::domain::*;
use crate::db;
use crate::events::Event;

use super::state::AppState;
use super::types::*;

type ApiResult<T> = Result<Json<ApiResponse<T>>, (StatusCode, Json<ApiError>)>;

// =============================================================================
// CARDS
// =============================================================================

pub async fn list_cards(
    State(state): State<AppState>,
    Query(params): Query<CardListParams>,
) -> ApiResult<Vec<Card>> {
    let project_id = params.project_id.as_ref().and_then(|s| Uuid::parse_str(s).ok());

    let states: Option<Vec<CardState>> = params.state.as_ref().map(|s| {
        s.split(',')
            .filter_map(|state| state.trim().parse().ok())
            .collect()
    });

    let labels: Option<Vec<String>> = params.labels.as_ref().map(|s| {
        s.split(',').map(|l| l.trim().to_string()).collect()
    });

    let cards = db::get_cards(
        &state.pool,
        project_id.as_ref(),
        states.as_deref(),
        labels.as_deref(),
        params.search.as_deref(),
        params.limit.min(100),
        params.offset,
    )
    .await
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiError::internal_error(e.to_string())),
        )
    })?;

    Ok(Json(ApiResponse::new(cards)))
}

pub async fn get_card(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Card> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let card = db::get_card(&state.pool, &card_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Card not found")),
            )
        })?;

    Ok(Json(ApiResponse::new(card)))
}

pub async fn create_card(
    State(state): State<AppState>,
    Json(req): Json<CreateCardRequest>,
) -> Result<(StatusCode, Json<ApiResponse<Card>>), (StatusCode, Json<ApiError>)> {
    // Validate project exists
    let project = db::get_project(&state.pool, &req.project_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::BAD_REQUEST,
                Json(ApiError::validation_error("Project not found")),
            )
        })?;

    // Create the card
    let mut card = Card::new(project.id, req.title, req.task_prompt);
    card.description = req.description;
    card.labels = req.labels.unwrap_or_default();
    card.priority = req.priority.unwrap_or(0);
    card.deadline = req.deadline;
    card.deployment_namespace = req.deployment_namespace;
    card.deployment_name = req.deployment_name;
    card.argocd_app_name = req.argocd_app_name;

    db::create_card(&state.pool, &card)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    // Create acceptance criteria if provided
    if let Some(criteria) = req.acceptance_criteria {
        for (i, c) in criteria.into_iter().enumerate() {
            let ac = AcceptanceCriteria::new(card.id, c.description, i as i32);
            db::create_acceptance_criteria(&state.pool, &ac)
                .await
                .ok();
        }
    }

    // Emit event
    state.event_bus.publish(Event::CardCreated {
        card_id: card.id,
        project_id: card.project_id,
        timestamp: chrono::Utc::now(),
    });

    Ok((StatusCode::CREATED, Json(ApiResponse::new(card))))
}

pub async fn update_card(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<UpdateCardRequest>,
) -> ApiResult<Card> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let mut card = db::get_card(&state.pool, &card_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Card not found")),
            )
        })?;

    // Update fields
    if let Some(title) = req.title {
        card.title = title;
    }
    if let Some(description) = req.description {
        card.description = Some(description);
    }
    if let Some(task_prompt) = req.task_prompt {
        card.task_prompt = task_prompt;
    }
    if let Some(labels) = req.labels {
        card.labels = labels;
    }
    if let Some(priority) = req.priority {
        card.priority = priority;
    }
    if let Some(deadline) = req.deadline {
        card.deadline = Some(deadline);
    }

    db::update_card(&state.pool, &card)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    // Emit event
    state.event_bus.publish(Event::CardUpdated {
        card_id: card.id,
        card: card.clone(),
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(card)))
}

pub async fn delete_card(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, (StatusCode, Json<ApiError>)> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    db::delete_card(&state.pool, &card_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(StatusCode::NO_CONTENT)
}

pub async fn transition_card(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<TransitionRequest>,
) -> ApiResult<TransitionResponse> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let mut card = db::get_card(&state.pool, &card_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Card not found")),
            )
        })?;

    // Parse trigger
    let trigger: Trigger = req.trigger.parse().map_err(|_| {
        let valid_triggers = state.state_machine.valid_triggers(&card);
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::with_details(
                "INVALID_TRANSITION",
                format!("Invalid trigger: {}", req.trigger),
                serde_json::json!({
                    "currentState": card.state.to_string(),
                    "trigger": req.trigger,
                    "validTriggers": valid_triggers.iter().map(|t| t.to_string()).collect::<Vec<_>>()
                }),
            )),
        )
    })?;

    let previous_state = card.state;

    // Execute transition using state machine
    let (_new_state, _actions) = state
        .state_machine
        .transition(&mut card, trigger)
        .map_err(|e| {
            let valid_triggers = state.state_machine.valid_triggers(&card);
            (
                StatusCode::BAD_REQUEST,
                Json(ApiError::with_details(
                    "INVALID_TRANSITION",
                    e.to_string(),
                    serde_json::json!({
                        "currentState": card.state.to_string(),
                        "trigger": req.trigger,
                        "validTriggers": valid_triggers.iter().map(|t| t.to_string()).collect::<Vec<_>>()
                    }),
                )),
            )
        })?;

    // Save state transition
    db::update_card_state(
        &state.pool,
        &card.id,
        card.state,
        previous_state,
        &trigger.to_string(),
    )
    .await
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiError::internal_error(e.to_string())),
        )
    })?;

    // Emit event
    state.event_bus.publish(Event::StateChanged {
        card_id: card.id,
        from_state: previous_state,
        to_state: card.state,
        trigger,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(TransitionResponse {
        previous_state: previous_state.to_string(),
        new_state: card.state.to_string(),
        card: serde_json::to_value(&card).unwrap_or_default(),
    })))
}

// =============================================================================
// LOOPS
// =============================================================================

pub async fn get_loop_state(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Option<LoopStateResponse>> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let loop_manager = state.loop_manager.read().await;
    let loop_state = loop_manager.get_loop_state(&card_id);

    Ok(Json(ApiResponse::new(loop_state.map(|ls| LoopStateResponse {
        card_id: ls.card_id.to_string(),
        iteration: ls.iteration,
        status: ls.status.to_string(),
        total_cost_usd: ls.total_cost_usd,
        total_tokens: ls.total_tokens,
        consecutive_errors: ls.consecutive_errors,
        start_time: ls.start_time,
        elapsed_seconds: (chrono::Utc::now() - ls.start_time).num_seconds(),
        config: LoopConfigResponse {
            max_iterations: ls.config.max_iterations,
            max_runtime_seconds: ls.config.max_runtime_seconds,
            max_cost_usd: ls.config.max_cost_usd,
        },
    }))))
}

pub async fn start_loop(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<StartLoopRequest>,
) -> ApiResult<LoopStateResponse> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    // Verify card exists and is in a loopable state
    let card = db::get_card(&state.pool, &card_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Card not found")),
            )
        })?;

    if !card.state.allows_loop() {
        return Err((
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error(format!(
                "Cannot start loop in state {}",
                card.state
            ))),
        ));
    }

    let mut loop_manager = state.loop_manager.write().await;

    // Build config overrides
    let config_overrides = req.config.map(|c| crate::loops::LoopConfigOverrides {
        max_iterations: c.max_iterations,
        max_runtime_seconds: c.max_runtime_seconds,
        max_cost_usd: c.max_cost_usd,
        checkpoint_interval: c.checkpoint_interval,
        cooldown_seconds: c.cooldown_seconds,
        completion_signal: c.completion_signal,
    });

    let loop_state = loop_manager
        .start_loop(card_id, config_overrides)
        .map_err(|e| {
            (
                StatusCode::CONFLICT,
                Json(ApiError::new("LOOP_ALREADY_EXISTS", e.to_string())),
            )
        })?;

    state.event_bus.publish(Event::LoopStarted {
        card_id,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(LoopStateResponse {
        card_id: loop_state.card_id.to_string(),
        iteration: loop_state.iteration,
        status: loop_state.status.to_string(),
        total_cost_usd: loop_state.total_cost_usd,
        total_tokens: loop_state.total_tokens,
        consecutive_errors: loop_state.consecutive_errors,
        start_time: loop_state.start_time,
        elapsed_seconds: 0,
        config: LoopConfigResponse {
            max_iterations: loop_state.config.max_iterations,
            max_runtime_seconds: loop_state.config.max_runtime_seconds,
            max_cost_usd: loop_state.config.max_cost_usd,
        },
    })))
}

pub async fn pause_loop(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<LoopStateResponse> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager.pause_loop(&card_id).map_err(|e| {
        (
            StatusCode::NOT_FOUND,
            Json(ApiError::new("LOOP_NOT_FOUND", e.to_string())),
        )
    })?;

    state.event_bus.publish(Event::LoopPaused {
        card_id,
        iteration: loop_state.iteration,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(LoopStateResponse {
        card_id: loop_state.card_id.to_string(),
        iteration: loop_state.iteration,
        status: loop_state.status.to_string(),
        total_cost_usd: loop_state.total_cost_usd,
        total_tokens: loop_state.total_tokens,
        consecutive_errors: loop_state.consecutive_errors,
        start_time: loop_state.start_time,
        elapsed_seconds: (chrono::Utc::now() - loop_state.start_time).num_seconds(),
        config: LoopConfigResponse {
            max_iterations: loop_state.config.max_iterations,
            max_runtime_seconds: loop_state.config.max_runtime_seconds,
            max_cost_usd: loop_state.config.max_cost_usd,
        },
    })))
}

pub async fn resume_loop(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<LoopStateResponse> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let mut loop_manager = state.loop_manager.write().await;
    let loop_state = loop_manager.resume_loop(&card_id).map_err(|e| {
        (
            StatusCode::NOT_FOUND,
            Json(ApiError::new("LOOP_NOT_FOUND", e.to_string())),
        )
    })?;

    Ok(Json(ApiResponse::new(LoopStateResponse {
        card_id: loop_state.card_id.to_string(),
        iteration: loop_state.iteration,
        status: loop_state.status.to_string(),
        total_cost_usd: loop_state.total_cost_usd,
        total_tokens: loop_state.total_tokens,
        consecutive_errors: loop_state.consecutive_errors,
        start_time: loop_state.start_time,
        elapsed_seconds: (chrono::Utc::now() - loop_state.start_time).num_seconds(),
        config: LoopConfigResponse {
            max_iterations: loop_state.config.max_iterations,
            max_runtime_seconds: loop_state.config.max_runtime_seconds,
            max_cost_usd: loop_state.config.max_cost_usd,
        },
    })))
}

pub async fn stop_loop(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<serde_json::Value> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let mut loop_manager = state.loop_manager.write().await;
    let final_state = loop_manager.stop_loop(&card_id).map_err(|e| {
        (
            StatusCode::NOT_FOUND,
            Json(ApiError::new("LOOP_NOT_FOUND", e.to_string())),
        )
    })?;

    state.event_bus.publish(Event::LoopCompleted {
        card_id,
        result: crate::events::LoopCompletionResult::UserStopped,
        total_iterations: final_state.iteration,
        total_cost_usd: final_state.total_cost_usd,
        total_tokens: final_state.total_tokens,
        timestamp: chrono::Utc::now(),
    });

    Ok(Json(ApiResponse::new(serde_json::json!({
        "status": "stopped",
        "finalIteration": final_state.iteration,
        "totalCostUsd": final_state.total_cost_usd
    }))))
}

pub async fn list_active_loops(
    State(state): State<AppState>,
) -> ApiResult<serde_json::Value> {
    let loop_manager = state.loop_manager.read().await;
    let loops = loop_manager.list_active_loops();

    let total_cost: f64 = loops.iter().map(|l| l.total_cost_usd).sum();
    let total_iterations: i32 = loops.iter().map(|l| l.iteration).sum();
    let running_count = loops.iter().filter(|l| l.status == crate::loops::LoopStatus::Running).count();
    let paused_count = loops.iter().filter(|l| l.status == crate::loops::LoopStatus::Paused).count();

    Ok(Json(ApiResponse::new(serde_json::json!({
        "data": loops.iter().map(|l| serde_json::json!({
            "cardId": l.card_id.to_string(),
            "iteration": l.iteration,
            "status": l.status.to_string(),
            "totalCostUsd": l.total_cost_usd
        })).collect::<Vec<_>>(),
        "stats": {
            "totalActive": loops.len(),
            "running": running_count,
            "paused": paused_count,
            "totalCostUsd": total_cost,
            "totalIterations": total_iterations
        }
    }))))
}

// =============================================================================
// ATTEMPTS
// =============================================================================

pub async fn list_attempts(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(params): Query<AttemptListParams>,
) -> ApiResult<Vec<Attempt>> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let attempts = db::get_attempts(&state.pool, &card_id, params.limit.min(100), params.offset)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(Json(ApiResponse::new(attempts)))
}

pub async fn get_attempt(
    State(state): State<AppState>,
    Path((card_id, attempt_id)): Path<(String, String)>,
) -> ApiResult<Attempt> {
    let _card_id = Uuid::parse_str(&card_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let attempt_uuid = Uuid::parse_str(&attempt_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid attempt ID")),
        )
    })?;

    let attempt = db::get_attempt(&state.pool, &attempt_uuid)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Attempt not found")),
            )
        })?;

    Ok(Json(ApiResponse::new(attempt)))
}

// =============================================================================
// ERRORS
// =============================================================================

pub async fn list_errors(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(params): Query<ErrorListParams>,
) -> ApiResult<Vec<CardError>> {
    let card_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let errors = db::get_errors(
        &state.pool,
        &card_id,
        params.resolved,
        params.category.as_deref(),
        params.limit.min(100),
        params.offset,
    )
    .await
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiError::internal_error(e.to_string())),
        )
    })?;

    Ok(Json(ApiResponse::new(errors)))
}

pub async fn get_error(
    State(state): State<AppState>,
    Path((card_id, error_id)): Path<(String, String)>,
) -> ApiResult<CardError> {
    let _card_id = Uuid::parse_str(&card_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let error_uuid = Uuid::parse_str(&error_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid error ID")),
        )
    })?;

    let error = db::get_error(&state.pool, &error_uuid)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Error not found")),
            )
        })?;

    Ok(Json(ApiResponse::new(error)))
}

pub async fn resolve_error(
    State(state): State<AppState>,
    Path((card_id, error_id)): Path<(String, String)>,
    Json(req): Json<ResolveErrorRequest>,
) -> ApiResult<CardError> {
    let _card_id = Uuid::parse_str(&card_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid card ID")),
        )
    })?;

    let error_uuid = Uuid::parse_str(&error_id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid error ID")),
        )
    })?;

    let error = db::resolve_error(&state.pool, &error_uuid, req.resolution_attempt_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(Json(ApiResponse::new(error)))
}

// =============================================================================
// PROJECTS
// =============================================================================

pub async fn list_projects(
    State(state): State<AppState>,
) -> ApiResult<Vec<Project>> {
    let projects = db::get_projects(&state.pool)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(Json(ApiResponse::new(projects)))
}

pub async fn get_project(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> ApiResult<Project> {
    let project_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid project ID")),
        )
    })?;

    let project = db::get_project(&state.pool, &project_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Project not found")),
            )
        })?;

    Ok(Json(ApiResponse::new(project)))
}

pub async fn create_project(
    State(state): State<AppState>,
    Json(req): Json<CreateProjectRequest>,
) -> Result<(StatusCode, Json<ApiResponse<Project>>), (StatusCode, Json<ApiError>)> {
    let mut project = Project::new(req.name, req.repository_url);
    project.description = req.description;
    project.repository_path = req.repository_path;
    project.tech_stack = req.tech_stack.unwrap_or_default();
    project.coding_conventions = req.coding_conventions;

    db::create_project(&state.pool, &project)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok((StatusCode::CREATED, Json(ApiResponse::new(project))))
}

pub async fn update_project(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<UpdateProjectRequest>,
) -> ApiResult<Project> {
    let project_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid project ID")),
        )
    })?;

    let mut project = db::get_project(&state.pool, &project_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?
        .ok_or_else(|| {
            (
                StatusCode::NOT_FOUND,
                Json(ApiError::not_found("Project not found")),
            )
        })?;

    if let Some(name) = req.name {
        project.name = name;
    }
    if let Some(description) = req.description {
        project.description = Some(description);
    }
    if let Some(repository_url) = req.repository_url {
        project.repository_url = repository_url;
    }
    if let Some(repository_path) = req.repository_path {
        project.repository_path = Some(repository_path);
    }
    if let Some(tech_stack) = req.tech_stack {
        project.tech_stack = tech_stack;
    }
    if let Some(coding_conventions) = req.coding_conventions {
        project.coding_conventions = Some(coding_conventions);
    }

    db::update_project(&state.pool, &project)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(Json(ApiResponse::new(project)))
}

pub async fn delete_project(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<StatusCode, (StatusCode, Json<ApiError>)> {
    let project_id = Uuid::parse_str(&id).map_err(|_| {
        (
            StatusCode::BAD_REQUEST,
            Json(ApiError::validation_error("Invalid project ID")),
        )
    })?;

    db::delete_project(&state.pool, &project_id)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(e.to_string())),
            )
        })?;

    Ok(StatusCode::NO_CONTENT)
}

// =============================================================================
// HEALTH
// =============================================================================

pub async fn health_check() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "status": "healthy",
        "version": env!("CARGO_PKG_VERSION")
    }))
}
