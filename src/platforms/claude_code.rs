//! Claude Code CLI platform implementation
//!
//! This module implements the CodingPlatform trait for Claude Code CLI,
//! enabling users to leverage their Claude Max/Pro subscriptions instead
//! of pay-per-token API billing.

use async_trait::async_trait;
use chrono::Utc;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::RwLock;

use super::installer;
use super::stream_parser::StreamParser;
use super::types::*;
use super::{CodingPlatform, PlatformError, SessionConfig};

/// Claude Code CLI platform implementation
pub struct ClaudeCodePlatform {
    /// Path to the claude binary (default: "claude" from PATH)
    binary_path: String,

    /// Custom config directory for multi-account support
    config_dir: Option<PathBuf>,

    /// Default model to use
    default_model: String,

    /// Maximum concurrent sessions
    max_concurrent: u32,

    /// Active sessions
    sessions: Arc<RwLock<HashMap<uuid::Uuid, SessionInfo>>>,

    /// Whether to auto-install if binary not found
    auto_install: bool,
}

/// Internal session tracking info
struct SessionInfo {
    handle: SessionHandle,
    parser: StreamParser,
    output_buffer: String,
    events: Vec<SessionEvent>,
}

impl ClaudeCodePlatform {
    /// Create a new Claude Code platform with default settings
    pub fn new() -> Self {
        Self {
            binary_path: "claude".to_string(),
            config_dir: None,
            default_model: "claude-sonnet-4-20250514".to_string(),
            max_concurrent: 1,
            sessions: Arc::new(RwLock::new(HashMap::new())),
            auto_install: true, // Auto-install by default for codespace environments
        }
    }

    /// Set custom binary path
    pub fn with_binary_path(mut self, path: impl Into<String>) -> Self {
        self.binary_path = path.into();
        self
    }

    /// Set custom config directory (for multi-account support)
    pub fn with_config_dir(mut self, path: PathBuf) -> Self {
        self.config_dir = Some(path);
        self
    }

    /// Set default model
    pub fn with_default_model(mut self, model: impl Into<String>) -> Self {
        self.default_model = model.into();
        self
    }

    /// Set maximum concurrent sessions
    pub fn with_max_concurrent(mut self, max: u32) -> Self {
        self.max_concurrent = max;
        self
    }

    /// Enable or disable auto-installation
    pub fn with_auto_install(mut self, auto_install: bool) -> Self {
        self.auto_install = auto_install;
        self
    }

    /// Build command arguments for claude CLI
    fn build_command(&self, worktree: &Path, prompt: &str, config: &SessionConfig) -> Command {
        let mut cmd = Command::new(&self.binary_path);

        // Set working directory
        cmd.current_dir(worktree);

        // Set config directory if specified
        if let Some(config_dir) = &self.config_dir {
            cmd.env("CLAUDE_CONFIG_DIR", config_dir);
        }

        // Add custom environment variables
        for (key, value) in &config.env_vars {
            cmd.env(key, value);
        }

        // Core arguments
        cmd.arg("--output-format").arg("stream-json");

        // Model selection
        let model = config.model.as_deref().unwrap_or(&self.default_model);
        cmd.arg("--model").arg(model);

        // Max turns if specified
        if let Some(max_turns) = config.max_turns {
            cmd.arg("--max-turns").arg(max_turns.to_string());
        }

        // Dangerous operations flag (required for autonomous operation)
        if config.allow_dangerous {
            cmd.arg("--dangerously-skip-permissions");
        }

        // Add extra arguments
        for arg in &config.extra_args {
            cmd.arg(arg);
        }

        // Finally, the prompt (using -p for non-interactive mode)
        cmd.arg("-p").arg(prompt);

        // Configure stdio
        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());
        cmd.stdin(Stdio::null());

        cmd
    }

    /// Process stdout stream and emit events
    async fn process_session(&self, session_id: uuid::Uuid) {
        let sessions = self.sessions.clone();

        tokio::spawn(async move {
            loop {
                // Get the process stdout
                let stdout = {
                    let mut sessions = sessions.write().await;
                    let session_info = match sessions.get_mut(&session_id) {
                        Some(s) => s,
                        None => return,
                    };

                    // Take stdout from process
                    let mut process = session_info.handle.process.lock().await;
                    process.stdout.take()
                };

                let stdout = match stdout {
                    Some(s) => s,
                    None => return,
                };

                let mut reader = BufReader::new(stdout).lines();

                // Read lines and parse
                while let Ok(Some(line)) = reader.next_line().await {
                    let mut sessions = sessions.write().await;
                    if let Some(session_info) = sessions.get_mut(&session_id) {
                        // Parse the line
                        let events = session_info.parser.parse_chunk(&format!("{}\n", line));

                        // Store events
                        for event in events {
                            session_info.events.push(event.clone());

                            // Accumulate text output
                            if let SessionEvent::AssistantMessage { content, .. } = &event {
                                session_info.output_buffer.push_str(content);
                                session_info.output_buffer.push('\n');
                            }
                        }
                    }
                }

                // Check if process has exited
                {
                    let mut sessions = sessions.write().await;
                    if let Some(session_info) = sessions.get_mut(&session_id) {
                        let mut process = session_info.handle.process.lock().await;
                        if let Ok(Some(_)) = process.try_wait() {
                            // Process has exited
                            return;
                        }
                    }
                }
            }
        });
    }
}

impl Default for ClaudeCodePlatform {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CodingPlatform for ClaudeCodePlatform {
    fn name(&self) -> &str {
        "claude-code"
    }

    async fn is_available(&self) -> Result<bool, PlatformError> {
        // First check if already available via configured path or PATH
        if let Some(path) = installer::find_claude_binary().await {
            tracing::info!("Claude Code CLI found at {:?}", path);
            return Ok(true);
        }

        // Not found - attempt auto-install if enabled
        if self.auto_install {
            tracing::info!("Claude Code CLI not found, attempting auto-installation...");
            match installer::ensure_claude_available().await {
                Ok(path) => {
                    tracing::info!("Claude Code CLI installed at {:?}", path);
                    Ok(true)
                }
                Err(e) => {
                    tracing::warn!("Auto-installation failed: {}", e);
                    Ok(false)
                }
            }
        } else {
            Ok(false)
        }
    }

    async fn start_session(
        &self,
        worktree: &Path,
        prompt: &str,
        config: &SessionConfig,
    ) -> Result<SessionHandle, PlatformError> {
        // Check concurrent session limit
        let current_sessions = self.sessions.read().await.len();
        if current_sessions >= self.max_concurrent as usize {
            return Err(PlatformError::SubscriptionLimit(format!(
                "Maximum concurrent sessions ({}) reached",
                self.max_concurrent
            )));
        }

        // Build and spawn command
        let mut cmd = self.build_command(worktree, prompt, config);

        let child = cmd.spawn().map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                PlatformError::BinaryNotFound(self.binary_path.clone())
            } else {
                PlatformError::ProcessError(e.to_string())
            }
        })?;

        // Create session handle
        let handle = SessionHandle::new(child, worktree.to_string_lossy().to_string());
        let session_id = handle.id;

        // Create parser
        let parser = StreamParser::new(&config.completion_signal);

        // Store session info
        let session_info = SessionInfo {
            handle,
            parser,
            output_buffer: String::new(),
            events: Vec::new(),
        };

        {
            let mut sessions = self.sessions.write().await;
            sessions.insert(session_id, session_info);
        }

        // Start processing stdout
        self.process_session(session_id).await;

        // Return a new handle (we moved the original into session_info)
        let sessions = self.sessions.read().await;
        let session_info = sessions.get(&session_id).ok_or_else(|| {
            PlatformError::SessionNotFound(session_id.to_string())
        })?;

        // Create a new handle referencing the same session
        Ok(SessionHandle {
            id: session_id,
            platform_session_id: session_info.parser.session_id().map(|s| s.to_string()),
            process: session_info.handle.process.clone(),
            started_at: session_info.handle.started_at,
            worktree_path: session_info.handle.worktree_path.clone(),
        })
    }

    async fn stop_session(&self, handle: &SessionHandle) -> Result<SessionResult, PlatformError> {
        let session_id = handle.id;

        // Get session info and kill process
        let (output, parser_state) = {
            let mut sessions = self.sessions.write().await;
            let session_info = sessions.remove(&session_id).ok_or_else(|| {
                PlatformError::SessionNotFound(session_id.to_string())
            })?;

            // Kill the process
            {
                let mut process = session_info.handle.process.lock().await;
                let _ = process.kill().await;
            }

            let output = session_info.output_buffer;
            let parser_state = (
                session_info.parser.has_completion_signal(),
                session_info.parser.estimated_tokens(),
                session_info.parser.total_cost(),
                session_info.parser.iteration_count(),
                session_info.parser.extract_commit_sha(),
            );

            (output, parser_state)
        };

        let (completed, tokens, cost, iterations, commit_sha) = parser_state;
        let duration_ms = (Utc::now() - handle.started_at).num_milliseconds() as u64;

        let mut result = if completed {
            SessionResult::success(output, duration_ms, iterations as u32)
        } else {
            SessionResult::failure(
                SessionEndReason::UserStopped,
                "Session stopped by user".to_string(),
                duration_ms,
                iterations as u32,
            )
        };

        result = result.with_tokens(tokens);
        if cost > 0.0 {
            result = result.with_cost(cost);
        }
        if let Some(sha) = commit_sha {
            result = result.with_commit(sha);
        }

        Ok(result)
    }

    async fn is_session_running(&self, handle: &SessionHandle) -> bool {
        let sessions = self.sessions.read().await;
        if let Some(session_info) = sessions.get(&handle.id) {
            let mut process = session_info.handle.process.lock().await;
            matches!(process.try_wait(), Ok(None))
        } else {
            false
        }
    }

    async fn get_session_status(&self, handle: &SessionHandle) -> Result<SessionStatus, PlatformError> {
        let sessions = self.sessions.read().await;
        let session_info = sessions.get(&handle.id).ok_or_else(|| {
            PlatformError::SessionNotFound(handle.id.to_string())
        })?;

        let runtime_ms = (Utc::now() - handle.started_at).num_milliseconds() as u64;

        // Determine state
        let state = {
            let mut process = session_info.handle.process.lock().await;
            match process.try_wait() {
                Ok(Some(status)) => {
                    if status.success() && session_info.parser.has_completion_signal() {
                        SessionState::Completed
                    } else if status.success() {
                        SessionState::Completed
                    } else {
                        SessionState::Failed
                    }
                }
                Ok(None) => SessionState::Running,
                Err(_) => SessionState::Failed,
            }
        };

        Ok(SessionStatus {
            session_id: handle.id,
            state,
            iteration: session_info.parser.iteration_count(),
            runtime_ms,
            tokens_used: Some(session_info.parser.estimated_tokens()),
            cost_usd: Some(session_info.parser.total_cost()),
            last_activity: Utc::now(),
            current_activity: Some("Processing".to_string()),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_platform_name() {
        let platform = ClaudeCodePlatform::new();
        assert_eq!(platform.name(), "claude-code");
    }

    #[test]
    fn test_platform_builder() {
        let platform = ClaudeCodePlatform::new()
            .with_binary_path("/usr/local/bin/claude")
            .with_config_dir(PathBuf::from("/home/user/.claude"))
            .with_default_model("claude-opus-4-5-20251101")
            .with_max_concurrent(3);

        assert_eq!(platform.binary_path, "/usr/local/bin/claude");
        assert_eq!(platform.config_dir, Some(PathBuf::from("/home/user/.claude")));
        assert_eq!(platform.default_model, "claude-opus-4-5-20251101");
        assert_eq!(platform.max_concurrent, 3);
    }

    #[test]
    fn test_default_platform() {
        let platform = ClaudeCodePlatform::default();
        assert_eq!(platform.binary_path, "claude");
        assert!(platform.config_dir.is_none());
        assert_eq!(platform.default_model, "claude-sonnet-4-20250514");
        assert_eq!(platform.max_concurrent, 1);
        assert!(platform.auto_install); // Auto-install enabled by default
    }

    #[test]
    fn test_auto_install_builder() {
        let platform = ClaudeCodePlatform::new().with_auto_install(false);
        assert!(!platform.auto_install);
    }

    #[tokio::test]
    async fn test_build_command() {
        let platform = ClaudeCodePlatform::new();
        let worktree = PathBuf::from("/tmp/test-worktree");
        let prompt = "Fix the bug in main.rs";

        let mut config = SessionConfig::default();
        config.model = Some("claude-opus-4-5".to_string());
        config.max_turns = Some(10);
        config.extra_args = vec!["--verbose".to_string()];

        // We can't easily inspect the Command, but we can at least verify it builds without panic
        let _cmd = platform.build_command(&worktree, prompt, &config);
    }

    #[tokio::test]
    async fn test_session_config_env_vars() {
        let platform = ClaudeCodePlatform::new()
            .with_config_dir(PathBuf::from("/custom/claude"));

        let worktree = PathBuf::from("/tmp/test");
        let mut config = SessionConfig::default();
        config.env_vars.insert("MY_VAR".to_string(), "my_value".to_string());

        let _cmd = platform.build_command(&worktree, "test", &config);
        // Command is built successfully with env vars
    }
}
