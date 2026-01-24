//! Platform abstraction for coding agents
//!
//! This module provides a trait-based abstraction for running coding sessions
//! with different AI platforms (Claude Code CLI, Aider, etc.) instead of
//! direct API calls. This allows users to leverage their subscription plans
//! (Claude Max/Pro) instead of pay-per-token API billing.

pub mod claude_code;
pub mod installer;
pub mod stream_parser;
pub mod types;

pub use claude_code::ClaudeCodePlatform;
pub use installer::{ensure_claude_available, find_claude_binary, install_claude_code, get_installed_version};
pub use stream_parser::StreamParser;
pub use types::*;

use async_trait::async_trait;
use std::path::Path;
use thiserror::Error;

/// Errors that can occur during platform operations
#[derive(Error, Debug)]
pub enum PlatformError {
    #[error("Platform not configured: {0}")]
    NotConfigured(String),

    #[error("Session start failed: {0}")]
    SessionStartFailed(String),

    #[error("Session not found: {0}")]
    SessionNotFound(String),

    #[error("Process error: {0}")]
    ProcessError(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("Platform binary not found: {0}")]
    BinaryNotFound(String),

    #[error("Session timeout after {0} seconds")]
    Timeout(u64),

    #[error("Session killed by user")]
    Killed,

    #[error("Subscription limit reached: {0}")]
    SubscriptionLimit(String),
}

/// Configuration for a coding session
#[derive(Debug, Clone)]
pub struct SessionConfig {
    /// Model to use (e.g., "claude-sonnet-4-20250514")
    pub model: Option<String>,

    /// Maximum turns/iterations for the session
    pub max_turns: Option<u32>,

    /// Timeout in seconds
    pub timeout_seconds: Option<u64>,

    /// Custom environment variables
    pub env_vars: std::collections::HashMap<String, String>,

    /// Completion signal to detect task completion
    pub completion_signal: String,

    /// Whether to allow dangerous operations (--dangerously-skip-permissions)
    pub allow_dangerous: bool,

    /// Additional CLI arguments
    pub extra_args: Vec<String>,
}

impl Default for SessionConfig {
    fn default() -> Self {
        Self {
            model: None,
            max_turns: None,
            timeout_seconds: Some(14400), // 4 hours default
            env_vars: std::collections::HashMap::new(),
            completion_signal: "<ringmaster>COMPLETE</ringmaster>".to_string(),
            allow_dangerous: true, // Required for autonomous operation
            extra_args: Vec::new(),
        }
    }
}

/// Trait for coding platforms that can run autonomous coding sessions
#[async_trait]
pub trait CodingPlatform: Send + Sync {
    /// Get the platform name (e.g., "claude-code", "aider")
    fn name(&self) -> &str;

    /// Check if the platform is available (binary exists, configured, etc.)
    async fn is_available(&self) -> Result<bool, PlatformError>;

    /// Start a new coding session in a worktree
    ///
    /// # Arguments
    /// * `worktree` - Path to the git worktree where the session will run
    /// * `prompt` - The coding prompt/instructions
    /// * `config` - Session configuration
    ///
    /// # Returns
    /// A SessionHandle that can be used to monitor and control the session
    async fn start_session(
        &self,
        worktree: &Path,
        prompt: &str,
        config: &SessionConfig,
    ) -> Result<SessionHandle, PlatformError>;

    /// Stop a running session
    async fn stop_session(&self, handle: &SessionHandle) -> Result<SessionResult, PlatformError>;

    /// Check if a session is still running
    async fn is_session_running(&self, handle: &SessionHandle) -> bool;

    /// Get the current status of a session
    async fn get_session_status(&self, handle: &SessionHandle) -> Result<SessionStatus, PlatformError>;
}

/// Registry of available coding platforms
pub struct PlatformRegistry {
    platforms: std::collections::HashMap<String, Box<dyn CodingPlatform>>,
}

impl PlatformRegistry {
    /// Create a new empty registry
    pub fn new() -> Self {
        Self {
            platforms: std::collections::HashMap::new(),
        }
    }

    /// Register a platform
    pub fn register(&mut self, platform: Box<dyn CodingPlatform>) {
        let name = platform.name().to_string();
        self.platforms.insert(name, platform);
    }

    /// Get a platform by name
    pub fn get(&self, name: &str) -> Option<&dyn CodingPlatform> {
        self.platforms.get(name).map(|p| p.as_ref())
    }

    /// List all registered platforms
    pub fn list(&self) -> Vec<&str> {
        self.platforms.keys().map(|s| s.as_str()).collect()
    }

    /// Check which platforms are available
    pub async fn available_platforms(&self) -> Vec<&str> {
        let mut available = Vec::new();
        for (name, platform) in &self.platforms {
            if platform.is_available().await.unwrap_or(false) {
                available.push(name.as_str());
            }
        }
        available
    }
}

impl Default for PlatformRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_config_default() {
        let config = SessionConfig::default();
        assert!(config.model.is_none());
        assert!(config.max_turns.is_none());
        assert_eq!(config.timeout_seconds, Some(14400));
        assert!(config.allow_dangerous);
        assert_eq!(config.completion_signal, "<ringmaster>COMPLETE</ringmaster>");
    }

    #[test]
    fn test_platform_registry_new() {
        let registry = PlatformRegistry::new();
        assert!(registry.list().is_empty());
    }

    #[test]
    fn test_platform_error_display() {
        let err = PlatformError::NotConfigured("test".to_string());
        assert_eq!(err.to_string(), "Platform not configured: test");

        let err = PlatformError::BinaryNotFound("claude".to_string());
        assert_eq!(err.to_string(), "Platform binary not found: claude");

        let err = PlatformError::Timeout(300);
        assert_eq!(err.to_string(), "Session timeout after 300 seconds");
    }
}
