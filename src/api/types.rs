//! API request/response types

use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

/// Standard API response wrapper
#[derive(Debug, Serialize)]
pub struct ApiResponse<T> {
    pub data: T,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub meta: Option<ResponseMeta>,
}

impl<T> ApiResponse<T> {
    pub fn new(data: T) -> Self {
        Self {
            data,
            meta: Some(ResponseMeta {
                timestamp: Utc::now(),
            }),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ResponseMeta {
    pub timestamp: DateTime<Utc>,
}

/// Paginated response
#[derive(Debug, Serialize)]
pub struct PaginatedResponse<T> {
    pub data: Vec<T>,
    pub pagination: Pagination,
}

#[derive(Debug, Serialize)]
pub struct Pagination {
    pub total: i64,
    pub limit: i32,
    pub offset: i32,
    #[serde(rename = "hasMore")]
    pub has_more: bool,
}

/// API error response
#[derive(Debug, Serialize)]
pub struct ApiError {
    pub error: ErrorDetail,
}

#[derive(Debug, Serialize)]
pub struct ErrorDetail {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}

impl ApiError {
    pub fn new(code: &str, message: impl Into<String>) -> Self {
        Self {
            error: ErrorDetail {
                code: code.to_string(),
                message: message.into(),
                details: None,
            },
        }
    }

    pub fn with_details(code: &str, message: impl Into<String>, details: serde_json::Value) -> Self {
        Self {
            error: ErrorDetail {
                code: code.to_string(),
                message: message.into(),
                details: Some(details),
            },
        }
    }

    pub fn validation_error(message: impl Into<String>) -> Self {
        Self::new("VALIDATION_ERROR", message)
    }

    pub fn not_found(message: impl Into<String>) -> Self {
        Self::new("NOT_FOUND", message)
    }

    pub fn invalid_transition(message: impl Into<String>) -> Self {
        Self::new("INVALID_TRANSITION", message)
    }

    pub fn internal_error(message: impl Into<String>) -> Self {
        Self::new("INTERNAL_ERROR", message)
    }
}

/// Query parameters for card listing
#[derive(Debug, Deserialize)]
pub struct CardListParams {
    pub project_id: Option<String>,
    pub state: Option<String>,
    pub labels: Option<String>,
    pub search: Option<String>,
    #[serde(default = "default_limit")]
    pub limit: i32,
    #[serde(default)]
    pub offset: i32,
    pub sort: Option<String>,
    pub order: Option<String>,
}

fn default_limit() -> i32 {
    50
}

/// Query parameters for attempt listing
#[derive(Debug, Deserialize)]
pub struct AttemptListParams {
    pub status: Option<String>,
    #[serde(default = "default_attempt_limit")]
    pub limit: i32,
    #[serde(default)]
    pub offset: i32,
}

fn default_attempt_limit() -> i32 {
    20
}

/// Query parameters for error listing
#[derive(Debug, Deserialize)]
pub struct ErrorListParams {
    pub resolved: Option<bool>,
    pub category: Option<String>,
    #[serde(default = "default_limit")]
    pub limit: i32,
    #[serde(default)]
    pub offset: i32,
}

/// Loop start request
#[derive(Debug, Deserialize)]
pub struct StartLoopRequest {
    #[serde(default)]
    pub config: Option<LoopConfigOverride>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopConfigOverride {
    pub max_iterations: Option<i32>,
    pub max_runtime_seconds: Option<i64>,
    pub max_cost_usd: Option<f64>,
    pub checkpoint_interval: Option<i32>,
    pub cooldown_seconds: Option<i32>,
    pub completion_signal: Option<String>,
}

/// Loop state response
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopStateResponse {
    pub card_id: String,
    pub iteration: i32,
    pub status: String,
    pub total_cost_usd: f64,
    pub total_tokens: i64,
    pub consecutive_errors: i32,
    pub start_time: DateTime<Utc>,
    pub elapsed_seconds: i64,
    pub config: LoopConfigResponse,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LoopConfigResponse {
    pub max_iterations: i32,
    pub max_runtime_seconds: i64,
    pub max_cost_usd: f64,
}

/// Transition request
#[derive(Debug, Deserialize)]
pub struct TransitionRequest {
    pub trigger: String,
    #[serde(default)]
    pub data: Option<serde_json::Value>,
}

/// Transition response
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TransitionResponse {
    pub previous_state: String,
    pub new_state: String,
    pub card: serde_json::Value,
}
