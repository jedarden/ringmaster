//! Types for the platform abstraction layer

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::process::Child;
use tokio::sync::Mutex;
use uuid::Uuid;

/// Handle to a running coding session
#[derive(Debug)]
pub struct SessionHandle {
    /// Unique session identifier
    pub id: Uuid,

    /// Platform-specific session ID (e.g., Claude Code's session_id)
    pub platform_session_id: Option<String>,

    /// The child process running the session
    pub process: Arc<Mutex<Child>>,

    /// When the session started
    pub started_at: DateTime<Utc>,

    /// Working directory for the session
    pub worktree_path: String,
}

impl SessionHandle {
    /// Create a new session handle
    pub fn new(process: Child, worktree_path: String) -> Self {
        Self {
            id: Uuid::new_v4(),
            platform_session_id: None,
            process: Arc::new(Mutex::new(process)),
            started_at: Utc::now(),
            worktree_path,
        }
    }

    /// Set the platform-specific session ID
    pub fn with_platform_session_id(mut self, id: String) -> Self {
        self.platform_session_id = Some(id);
        self
    }
}

/// Events emitted during a coding session
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SessionEvent {
    /// Session started
    Started {
        session_id: String,
        timestamp: DateTime<Utc>,
    },

    /// System message (e.g., initialization info)
    System {
        message: String,
        timestamp: DateTime<Utc>,
    },

    /// User message sent to the model
    UserMessage {
        content: String,
        timestamp: DateTime<Utc>,
    },

    /// Assistant message received from the model
    AssistantMessage {
        content: String,
        timestamp: DateTime<Utc>,
    },

    /// Tool was used
    ToolUse {
        tool_name: String,
        input: serde_json::Value,
        timestamp: DateTime<Utc>,
    },

    /// Tool returned a result
    ToolResult {
        tool_name: String,
        output: String,
        is_error: bool,
        timestamp: DateTime<Utc>,
    },

    /// Progress update (tokens used, cost, etc.)
    Progress {
        tokens_used: Option<i64>,
        cost_usd: Option<f64>,
        iteration: i32,
        timestamp: DateTime<Utc>,
    },

    /// Completion signal detected
    CompletionSignal {
        timestamp: DateTime<Utc>,
    },

    /// Error occurred
    Error {
        message: String,
        recoverable: bool,
        timestamp: DateTime<Utc>,
    },

    /// Session ended
    Ended {
        result: SessionEndReason,
        duration_ms: u64,
        total_cost_usd: Option<f64>,
        timestamp: DateTime<Utc>,
    },
}

/// Reason why a session ended
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SessionEndReason {
    /// Completion signal was detected
    Completed,
    /// Max turns/iterations reached
    MaxTurns,
    /// Timeout reached
    Timeout,
    /// User stopped the session
    UserStopped,
    /// Error occurred
    Error,
    /// Process exited unexpectedly
    ProcessExited,
}

/// Result of a completed session
#[derive(Debug, Clone)]
pub struct SessionResult {
    /// Whether the session completed successfully
    pub success: bool,

    /// How the session ended
    pub end_reason: SessionEndReason,

    /// Total output from the session
    pub output: String,

    /// Duration in milliseconds
    pub duration_ms: u64,

    /// Number of iterations/turns
    pub iterations: u32,

    /// Total tokens used (if available)
    pub total_tokens: Option<i64>,

    /// Total cost in USD (if available)
    pub total_cost_usd: Option<f64>,

    /// Detected commit SHA (if any commits were made)
    pub commit_sha: Option<String>,

    /// Error message (if any)
    pub error: Option<String>,
}

impl SessionResult {
    /// Create a successful result
    pub fn success(
        output: String,
        duration_ms: u64,
        iterations: u32,
    ) -> Self {
        Self {
            success: true,
            end_reason: SessionEndReason::Completed,
            output,
            duration_ms,
            iterations,
            total_tokens: None,
            total_cost_usd: None,
            commit_sha: None,
            error: None,
        }
    }

    /// Create a failed result
    pub fn failure(
        end_reason: SessionEndReason,
        error: String,
        duration_ms: u64,
        iterations: u32,
    ) -> Self {
        Self {
            success: false,
            end_reason,
            output: String::new(),
            duration_ms,
            iterations,
            total_tokens: None,
            total_cost_usd: None,
            commit_sha: None,
            error: Some(error),
        }
    }

    /// Set token count
    pub fn with_tokens(mut self, tokens: i64) -> Self {
        self.total_tokens = Some(tokens);
        self
    }

    /// Set cost
    pub fn with_cost(mut self, cost: f64) -> Self {
        self.total_cost_usd = Some(cost);
        self
    }

    /// Set commit SHA
    pub fn with_commit(mut self, sha: String) -> Self {
        self.commit_sha = Some(sha);
        self
    }
}

/// Current status of a session
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionStatus {
    /// Session ID
    pub session_id: Uuid,

    /// Current state
    pub state: SessionState,

    /// Current iteration/turn number
    pub iteration: i32,

    /// Running time in milliseconds
    pub runtime_ms: u64,

    /// Tokens used so far
    pub tokens_used: Option<i64>,

    /// Cost so far
    pub cost_usd: Option<f64>,

    /// Last activity timestamp
    pub last_activity: DateTime<Utc>,

    /// Current activity description
    pub current_activity: Option<String>,
}

/// Session state
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SessionState {
    /// Session is starting up
    Starting,
    /// Session is actively running
    Running,
    /// Session is waiting for input
    Waiting,
    /// Session is paused
    Paused,
    /// Session is stopping
    Stopping,
    /// Session has completed
    Completed,
    /// Session has failed
    Failed,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_result_success() {
        let result = SessionResult::success(
            "Task completed".to_string(),
            5000,
            3,
        );
        assert!(result.success);
        assert_eq!(result.end_reason, SessionEndReason::Completed);
        assert_eq!(result.iterations, 3);
    }

    #[test]
    fn test_session_result_failure() {
        let result = SessionResult::failure(
            SessionEndReason::Error,
            "Something went wrong".to_string(),
            1000,
            1,
        );
        assert!(!result.success);
        assert_eq!(result.end_reason, SessionEndReason::Error);
        assert!(result.error.is_some());
    }

    #[test]
    fn test_session_result_builder() {
        let result = SessionResult::success("output".to_string(), 1000, 2)
            .with_tokens(5000)
            .with_cost(0.05)
            .with_commit("abc1234".to_string());

        assert_eq!(result.total_tokens, Some(5000));
        assert_eq!(result.total_cost_usd, Some(0.05));
        assert_eq!(result.commit_sha, Some("abc1234".to_string()));
    }

    #[test]
    fn test_session_event_serialization() {
        let event = SessionEvent::Started {
            session_id: "test-123".to_string(),
            timestamp: Utc::now(),
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"started\""));
        assert!(json.contains("test-123"));
    }

    #[test]
    fn test_session_state_serialization() {
        let state = SessionState::Running;
        let json = serde_json::to_string(&state).unwrap();
        assert_eq!(json, "\"running\"");
    }

    #[test]
    fn test_session_end_reason_serialization() {
        let reason = SessionEndReason::Completed;
        let json = serde_json::to_string(&reason).unwrap();
        assert_eq!(json, "\"completed\"");

        let reason = SessionEndReason::UserStopped;
        let json = serde_json::to_string(&reason).unwrap();
        assert_eq!(json, "\"user_stopped\"");
    }
}
