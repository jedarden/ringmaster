//! REST API routes for Ringmaster

mod cards;
mod projects;
mod loops;
mod errors;
mod ws;

pub use cards::*;
pub use projects::*;
pub use loops::*;
pub use errors::*;
pub use ws::*;

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

/// API response wrapper
#[derive(Debug, Serialize)]
pub struct ApiResponse<T> {
    pub data: T,
    pub meta: ResponseMeta,
}

impl<T: Serialize> ApiResponse<T> {
    pub fn new(data: T) -> Self {
        Self {
            data,
            meta: ResponseMeta {
                timestamp: Utc::now(),
            },
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ResponseMeta {
    pub timestamp: DateTime<Utc>,
}

/// Pagination information
#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Pagination {
    pub total: i64,
    pub limit: i32,
    pub offset: i32,
    pub has_more: bool,
}

/// Paginated response
#[derive(Debug, Serialize)]
pub struct PaginatedResponse<T> {
    pub data: Vec<T>,
    pub pagination: Pagination,
}

/// API error response
#[derive(Debug, Serialize)]
pub struct ApiError {
    pub error: ErrorBody,
}

#[derive(Debug, Serialize)]
pub struct ErrorBody {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

impl ApiError {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            error: ErrorBody {
                code: code.to_string(),
                message: message.to_string(),
                details: None,
            },
        }
    }

    pub fn with_details(code: &str, message: &str, details: serde_json::Value) -> Self {
        Self {
            error: ErrorBody {
                code: code.to_string(),
                message: message.to_string(),
                details: Some(details),
            },
        }
    }
}

/// Application error type
#[derive(Debug)]
pub enum AppError {
    NotFound(String),
    BadRequest(String),
    InvalidTransition(String),
    GuardFailed(String),
    LoopError(String),
    DatabaseError(String),
    InternalError(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error) = match self {
            AppError::NotFound(msg) => (
                StatusCode::NOT_FOUND,
                ApiError::new("NOT_FOUND", &msg),
            ),
            AppError::BadRequest(msg) => (
                StatusCode::BAD_REQUEST,
                ApiError::new("BAD_REQUEST", &msg),
            ),
            AppError::InvalidTransition(msg) => (
                StatusCode::BAD_REQUEST,
                ApiError::new("INVALID_TRANSITION", &msg),
            ),
            AppError::GuardFailed(msg) => (
                StatusCode::BAD_REQUEST,
                ApiError::new("GUARD_FAILED", &msg),
            ),
            AppError::LoopError(msg) => (
                StatusCode::BAD_REQUEST,
                ApiError::new("LOOP_ERROR", &msg),
            ),
            AppError::DatabaseError(msg) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                ApiError::new("DATABASE_ERROR", &msg),
            ),
            AppError::InternalError(msg) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                ApiError::new("INTERNAL_ERROR", &msg),
            ),
        };

        (status, Json(error)).into_response()
    }
}

impl From<sqlx::Error> for AppError {
    fn from(err: sqlx::Error) -> Self {
        match err {
            sqlx::Error::RowNotFound => AppError::NotFound("Resource not found".to_string()),
            _ => AppError::DatabaseError(err.to_string()),
        }
    }
}

/// Application state shared between handlers
#[derive(Clone)]
pub struct AppState {
    pub pool: sqlx::SqlitePool,
    pub event_bus: crate::events::EventBus,
    pub loop_manager: std::sync::Arc<tokio::sync::RwLock<crate::loops::LoopManager>>,
}
