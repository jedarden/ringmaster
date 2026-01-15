//! Error domain model for tracking errors in the SDLC pipeline

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Error category
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCategory {
    Build,
    Test,
    Deploy,
    Runtime,
    Other,
}

impl std::fmt::Display for ErrorCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ErrorCategory::Build => write!(f, "build"),
            ErrorCategory::Test => write!(f, "test"),
            ErrorCategory::Deploy => write!(f, "deploy"),
            ErrorCategory::Runtime => write!(f, "runtime"),
            ErrorCategory::Other => write!(f, "other"),
        }
    }
}

impl std::str::FromStr for ErrorCategory {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "build" => Ok(ErrorCategory::Build),
            "test" => Ok(ErrorCategory::Test),
            "deploy" => Ok(ErrorCategory::Deploy),
            "runtime" => Ok(ErrorCategory::Runtime),
            "other" => Ok(ErrorCategory::Other),
            _ => Err(format!("Unknown error category: {}", s)),
        }
    }
}

/// Error severity
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorSeverity {
    Error,
    Warning,
    Info,
}

impl std::fmt::Display for ErrorSeverity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ErrorSeverity::Error => write!(f, "error"),
            ErrorSeverity::Warning => write!(f, "warning"),
            ErrorSeverity::Info => write!(f, "info"),
        }
    }
}

impl std::str::FromStr for ErrorSeverity {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "error" => Ok(ErrorSeverity::Error),
            "warning" => Ok(ErrorSeverity::Warning),
            "info" => Ok(ErrorSeverity::Info),
            _ => Err(format!("Unknown error severity: {}", s)),
        }
    }
}

/// An error recorded during the SDLC process
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CardError {
    pub id: Uuid,
    pub card_id: Uuid,
    pub attempt_id: Option<Uuid>,
    pub error_type: String,
    pub message: String,
    pub stack_trace: Option<String>,
    pub context: Option<ErrorContext>,
    pub category: Option<ErrorCategory>,
    pub severity: ErrorSeverity,
    pub resolved: bool,
    pub resolved_at: Option<DateTime<Utc>>,
    pub resolution_attempt_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
}

impl CardError {
    pub fn new(card_id: Uuid, error_type: String, message: String) -> Self {
        Self {
            id: Uuid::new_v4(),
            card_id,
            attempt_id: None,
            error_type,
            message,
            stack_trace: None,
            context: None,
            category: None,
            severity: ErrorSeverity::Error,
            resolved: false,
            resolved_at: None,
            resolution_attempt_id: None,
            created_at: Utc::now(),
        }
    }

    pub fn with_category(mut self, category: ErrorCategory) -> Self {
        self.category = Some(category);
        self
    }

    pub fn with_context(mut self, context: ErrorContext) -> Self {
        self.context = Some(context);
        self
    }

    pub fn with_stack_trace(mut self, stack_trace: String) -> Self {
        self.stack_trace = Some(stack_trace);
        self
    }

    pub fn with_attempt(mut self, attempt_id: Uuid) -> Self {
        self.attempt_id = Some(attempt_id);
        self
    }
}

/// Additional context for an error
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ErrorContext {
    pub file: Option<String>,
    pub line: Option<i32>,
    pub source_state: Option<String>,
    pub build_run_id: Option<i64>,
    pub logs: Option<String>,
    #[serde(flatten)]
    pub extra: Option<serde_json::Value>,
}

impl ErrorContext {
    pub fn new() -> Self {
        Self {
            file: None,
            line: None,
            source_state: None,
            build_run_id: None,
            logs: None,
            extra: None,
        }
    }

    pub fn with_logs(mut self, logs: String) -> Self {
        self.logs = Some(logs);
        self
    }

    pub fn with_source_state(mut self, state: String) -> Self {
        self.source_state = Some(state);
        self
    }
}

impl Default for ErrorContext {
    fn default() -> Self {
        Self::new()
    }
}

/// Request to mark an error as resolved
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ResolveErrorRequest {
    pub resolution_attempt_id: Option<Uuid>,
}
