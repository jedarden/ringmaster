//! Project API routes

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{delete, get, patch, post},
    Json, Router,
};
use uuid::Uuid;

use crate::db;
use crate::domain::{CreateProjectRequest, Project, ProjectWithStats, UpdateProjectRequest};

use super::{ApiResponse, AppError, AppState};

/// Create project routes
pub fn project_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(list_projects))
        .route("/", post(create_project))
        .route("/:project_id", get(get_project))
        .route("/:project_id", patch(update_project))
        .route("/:project_id", delete(delete_project))
}

async fn list_projects(
    State(state): State<AppState>,
) -> Result<Json<ApiResponse<Vec<ProjectWithStats>>>, AppError> {
    let projects = db::list_projects_with_stats(&state.pool).await?;
    Ok(Json(ApiResponse::new(projects)))
}

async fn get_project(
    State(state): State<AppState>,
    Path(project_id): Path<Uuid>,
) -> Result<Json<ApiResponse<Project>>, AppError> {
    let project = db::get_project(&state.pool, &project_id.to_string())
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Project {} not found", project_id)))?;

    Ok(Json(ApiResponse::new(project)))
}

async fn create_project(
    State(state): State<AppState>,
    Json(req): Json<CreateProjectRequest>,
) -> Result<(StatusCode, Json<ApiResponse<Project>>), AppError> {
    let project = db::create_project(&state.pool, &req).await?;
    Ok((StatusCode::CREATED, Json(ApiResponse::new(project))))
}

async fn update_project(
    State(state): State<AppState>,
    Path(project_id): Path<Uuid>,
    Json(req): Json<UpdateProjectRequest>,
) -> Result<Json<ApiResponse<Project>>, AppError> {
    let project = db::update_project(&state.pool, &project_id.to_string(), &req)
        .await?
        .ok_or_else(|| AppError::NotFound(format!("Project {} not found", project_id)))?;

    Ok(Json(ApiResponse::new(project)))
}

async fn delete_project(
    State(state): State<AppState>,
    Path(project_id): Path<Uuid>,
) -> Result<StatusCode, AppError> {
    let deleted = db::delete_project(&state.pool, &project_id.to_string()).await?;

    if deleted {
        Ok(StatusCode::NO_CONTENT)
    } else {
        Err(AppError::NotFound(format!("Project {} not found", project_id)))
    }
}
