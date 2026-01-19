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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_category_display() {
        assert_eq!(ErrorCategory::Build.to_string(), "build");
        assert_eq!(ErrorCategory::Test.to_string(), "test");
        assert_eq!(ErrorCategory::Deploy.to_string(), "deploy");
        assert_eq!(ErrorCategory::Runtime.to_string(), "runtime");
        assert_eq!(ErrorCategory::Other.to_string(), "other");
    }

    #[test]
    fn test_error_category_from_str() {
        assert_eq!("build".parse::<ErrorCategory>().unwrap(), ErrorCategory::Build);
        assert_eq!("test".parse::<ErrorCategory>().unwrap(), ErrorCategory::Test);
        assert_eq!("deploy".parse::<ErrorCategory>().unwrap(), ErrorCategory::Deploy);
        assert_eq!("runtime".parse::<ErrorCategory>().unwrap(), ErrorCategory::Runtime);
        assert_eq!("other".parse::<ErrorCategory>().unwrap(), ErrorCategory::Other);
    }

    #[test]
    fn test_error_category_from_str_invalid() {
        let result = "invalid".parse::<ErrorCategory>();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Unknown error category"));
    }

    #[test]
    fn test_error_severity_display() {
        assert_eq!(ErrorSeverity::Error.to_string(), "error");
        assert_eq!(ErrorSeverity::Warning.to_string(), "warning");
        assert_eq!(ErrorSeverity::Info.to_string(), "info");
    }

    #[test]
    fn test_error_severity_from_str() {
        assert_eq!("error".parse::<ErrorSeverity>().unwrap(), ErrorSeverity::Error);
        assert_eq!("warning".parse::<ErrorSeverity>().unwrap(), ErrorSeverity::Warning);
        assert_eq!("info".parse::<ErrorSeverity>().unwrap(), ErrorSeverity::Info);
    }

    #[test]
    fn test_error_severity_from_str_invalid() {
        let result = "invalid".parse::<ErrorSeverity>();
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Unknown error severity"));
    }

    #[test]
    fn test_card_error_new() {
        let card_id = Uuid::new_v4();
        let error = CardError::new(card_id, "compile_error".to_string(), "Failed to compile".to_string());

        assert_eq!(error.card_id, card_id);
        assert_eq!(error.error_type, "compile_error");
        assert_eq!(error.message, "Failed to compile");
        assert!(error.attempt_id.is_none());
        assert!(error.stack_trace.is_none());
        assert!(error.context.is_none());
        assert!(error.category.is_none());
        assert_eq!(error.severity, ErrorSeverity::Error);
        assert!(!error.resolved);
        assert!(error.resolved_at.is_none());
        assert!(error.resolution_attempt_id.is_none());
    }

    #[test]
    fn test_card_error_with_category() {
        let error = CardError::new(Uuid::new_v4(), "test".to_string(), "msg".to_string())
            .with_category(ErrorCategory::Build);

        assert_eq!(error.category, Some(ErrorCategory::Build));
    }

    #[test]
    fn test_card_error_with_stack_trace() {
        let error = CardError::new(Uuid::new_v4(), "test".to_string(), "msg".to_string())
            .with_stack_trace("stack trace here".to_string());

        assert_eq!(error.stack_trace, Some("stack trace here".to_string()));
    }

    #[test]
    fn test_card_error_with_attempt() {
        let attempt_id = Uuid::new_v4();
        let error = CardError::new(Uuid::new_v4(), "test".to_string(), "msg".to_string())
            .with_attempt(attempt_id);

        assert_eq!(error.attempt_id, Some(attempt_id));
    }

    #[test]
    fn test_card_error_with_context() {
        let context = ErrorContext::new()
            .with_logs("error logs".to_string())
            .with_source_state("building".to_string());

        let error = CardError::new(Uuid::new_v4(), "test".to_string(), "msg".to_string())
            .with_context(context);

        assert!(error.context.is_some());
        let ctx = error.context.unwrap();
        assert_eq!(ctx.logs, Some("error logs".to_string()));
        assert_eq!(ctx.source_state, Some("building".to_string()));
    }

    #[test]
    fn test_error_context_new() {
        let context = ErrorContext::new();

        assert!(context.file.is_none());
        assert!(context.line.is_none());
        assert!(context.source_state.is_none());
        assert!(context.build_run_id.is_none());
        assert!(context.logs.is_none());
        assert!(context.extra.is_none());
    }

    #[test]
    fn test_error_context_default() {
        let context = ErrorContext::default();

        assert!(context.file.is_none());
        assert!(context.line.is_none());
    }

    #[test]
    fn test_error_context_builders() {
        let context = ErrorContext::new()
            .with_logs("my logs".to_string())
            .with_source_state("testing".to_string());

        assert_eq!(context.logs, Some("my logs".to_string()));
        assert_eq!(context.source_state, Some("testing".to_string()));
    }

    #[test]
    fn test_error_category_serialization() {
        let json = serde_json::to_string(&ErrorCategory::Build).unwrap();
        assert_eq!(json, "\"build\"");

        let deserialized: ErrorCategory = serde_json::from_str("\"deploy\"").unwrap();
        assert_eq!(deserialized, ErrorCategory::Deploy);
    }

    #[test]
    fn test_error_severity_serialization() {
        let json = serde_json::to_string(&ErrorSeverity::Warning).unwrap();
        assert_eq!(json, "\"warning\"");

        let deserialized: ErrorSeverity = serde_json::from_str("\"info\"").unwrap();
        assert_eq!(deserialized, ErrorSeverity::Info);
    }

    #[test]
    fn test_card_error_serialization() {
        let error = CardError::new(
            Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap(),
            "test_error".to_string(),
            "Test message".to_string(),
        )
        .with_category(ErrorCategory::Test);

        let json = serde_json::to_string(&error).unwrap();

        // Verify camelCase serialization
        assert!(json.contains("\"cardId\""));
        assert!(json.contains("\"errorType\""));
        assert!(!json.contains("\"card_id\""));
        assert!(!json.contains("\"error_type\""));
    }

    #[test]
    fn test_resolve_error_request_deserialization() {
        let json = r#"{"resolutionAttemptId": "00000000-0000-0000-0000-000000000001"}"#;
        let request: ResolveErrorRequest = serde_json::from_str(json).unwrap();

        assert_eq!(
            request.resolution_attempt_id,
            Some(Uuid::parse_str("00000000-0000-0000-0000-000000000001").unwrap())
        );
    }

    #[test]
    fn test_resolve_error_request_without_attempt_id() {
        let json = r#"{}"#;
        let request: ResolveErrorRequest = serde_json::from_str(json).unwrap();

        assert!(request.resolution_attempt_id.is_none());
    }
}
