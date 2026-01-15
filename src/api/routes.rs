//! API route definitions

use axum::{
    routing::{get, post, patch, delete},
    Router,
};
use tower_http::cors::{CorsLayer, Any};
use tower_http::trace::TraceLayer;

use super::handlers;
use super::state::AppState;
use super::websocket::ws_handler;

/// Build the API router
pub fn build_router(state: AppState) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    let api_routes = Router::new()
        // Cards
        .route("/cards", get(handlers::list_cards).post(handlers::create_card))
        .route("/cards/:id", get(handlers::get_card).patch(handlers::update_card).delete(handlers::delete_card))
        .route("/cards/:id/transition", post(handlers::transition_card))

        // Loops
        .route("/cards/:id/loop", get(handlers::get_loop_state))
        .route("/cards/:id/loop/start", post(handlers::start_loop))
        .route("/cards/:id/loop/pause", post(handlers::pause_loop))
        .route("/cards/:id/loop/resume", post(handlers::resume_loop))
        .route("/cards/:id/loop/stop", post(handlers::stop_loop))
        .route("/loops", get(handlers::list_active_loops))

        // Attempts
        .route("/cards/:id/attempts", get(handlers::list_attempts))
        .route("/cards/:id/attempts/:attempt_id", get(handlers::get_attempt))

        // Errors
        .route("/cards/:id/errors", get(handlers::list_errors))
        .route("/cards/:id/errors/:error_id", get(handlers::get_error))
        .route("/cards/:id/errors/:error_id/resolve", post(handlers::resolve_error))

        // Projects
        .route("/projects", get(handlers::list_projects).post(handlers::create_project))
        .route("/projects/:id", get(handlers::get_project).patch(handlers::update_project).delete(handlers::delete_project))

        // Integrations
        .nest("/integrations", super::integrations::integration_routes())

        // WebSocket
        .route("/ws", get(ws_handler))

        // Health
        .route("/health", get(handlers::health_check));

    Router::new()
        .nest("/api", api_routes)
        .layer(cors)
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

/// Build the router including static file serving for the frontend
pub fn build_full_router(state: AppState) -> Router {
    let api_router = build_router(state);

    // In production, serve embedded static files
    // For now, just return the API router
    api_router
}
