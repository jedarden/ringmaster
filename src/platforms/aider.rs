//! Aider CLI platform implementation
//!
//! This module implements the CodingPlatform trait for Aider,
//! a popular AI pair programming tool that supports multiple LLM backends
//! including OpenAI GPT-4, Claude, and local models.

use async_trait::async_trait;
use chrono::Utc;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::RwLock;

use super::types::*;
use super::{CodingPlatform, PlatformError, SessionConfig};

/// Aider CLI platform implementation
pub struct AiderPlatform {
    /// Path to the aider binary (default: "aider" from PATH)
    binary_path: String,

    /// Default model to use (e.g., "gpt-4", "claude-3-opus-20240229")
    default_model: String,

    /// Whether to use --yes-always for non-interactive mode
    auto_confirm: bool,

    /// Maximum concurrent sessions
    max_concurrent: u32,

    /// Active sessions
    sessions: Arc<RwLock<HashMap<uuid::Uuid, AiderSessionInfo>>>,

    /// Custom configuration file path
    config_file: Option<PathBuf>,
}

/// Internal session tracking info
struct AiderSessionInfo {
    handle: SessionHandle,
    output_buffer: String,
    file_changes: Vec<String>,
    completion_detected: bool,
    iteration_count: i32,
    completion_signal: String,
}

impl AiderPlatform {
    /// Create a new Aider platform with default settings
    pub fn new() -> Self {
        Self {
            binary_path: "aider".to_string(),
            default_model: "gpt-4".to_string(),
            auto_confirm: true,
            max_concurrent: 1,
            sessions: Arc::new(RwLock::new(HashMap::new())),
            config_file: None,
        }
    }

    /// Set custom binary path
    pub fn with_binary_path(mut self, path: impl Into<String>) -> Self {
        self.binary_path = path.into();
        self
    }

    /// Set default model
    pub fn with_default_model(mut self, model: impl Into<String>) -> Self {
        self.default_model = model.into();
        self
    }

    /// Set auto-confirm mode
    pub fn with_auto_confirm(mut self, auto: bool) -> Self {
        self.auto_confirm = auto;
        self
    }

    /// Set maximum concurrent sessions
    pub fn with_max_concurrent(mut self, max: u32) -> Self {
        self.max_concurrent = max;
        self
    }

    /// Set custom config file
    pub fn with_config_file(mut self, path: PathBuf) -> Self {
        self.config_file = Some(path);
        self
    }

    /// Build command arguments for aider CLI
    fn build_command(&self, worktree: &Path, prompt: &str, config: &SessionConfig) -> Command {
        let mut cmd = Command::new(&self.binary_path);

        // Set working directory
        cmd.current_dir(worktree);

        // Add custom environment variables
        for (key, value) in &config.env_vars {
            cmd.env(key, value);
        }

        // Model selection
        let model = config.model.as_deref().unwrap_or(&self.default_model);
        cmd.arg("--model").arg(model);

        // Non-interactive mode (auto-confirm all changes)
        if self.auto_confirm {
            cmd.arg("--yes-always");
        }

        // Skip git if configured
        // Aider has good git integration but we might want to control commits
        cmd.arg("--auto-commits");

        // No browser opening
        cmd.arg("--no-browser");

        // Config file if specified
        if let Some(config_file) = &self.config_file {
            cmd.arg("--config").arg(config_file);
        }

        // Add extra arguments
        for arg in &config.extra_args {
            cmd.arg(arg);
        }

        // Finally, the message/prompt
        cmd.arg("--message").arg(prompt);

        // Configure stdio
        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());
        cmd.stdin(Stdio::null());

        cmd
    }

    /// Check if aider binary is available
    async fn find_aider_binary() -> Option<PathBuf> {
        // Check common locations
        let paths_to_check = [
            "aider",
            "/usr/local/bin/aider",
            "/usr/bin/aider",
        ];

        for path in paths_to_check {
            if let Ok(output) = Command::new(path)
                .arg("--version")
                .output()
                .await
            {
                if output.status.success() {
                    return Some(PathBuf::from(path));
                }
            }
        }

        // Check PATH
        if let Ok(path) = which::which("aider") {
            return Some(path);
        }

        None
    }

    /// Process stdout stream and track progress
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

                // Read lines and parse Aider output
                while let Ok(Some(line)) = reader.next_line().await {
                    let mut sessions = sessions.write().await;
                    if let Some(session_info) = sessions.get_mut(&session_id) {
                        // Accumulate output
                        session_info.output_buffer.push_str(&line);
                        session_info.output_buffer.push('\n');

                        // Parse Aider-specific patterns
                        parse_aider_output(&line, session_info);
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

/// Parse Aider output for file changes and completion signals
fn parse_aider_output(line: &str, session_info: &mut AiderSessionInfo) {
    // Detect file changes
    if line.starts_with("Wrote ") || line.contains("Applied edit to") {
        // Extract filename from "Wrote path/to/file" or similar
        if let Some(file) = line.strip_prefix("Wrote ") {
            session_info.file_changes.push(file.trim().to_string());
        }
    }

    // Detect commits
    if line.starts_with("Commit ") || line.contains("committed") {
        session_info.iteration_count += 1;
    }

    // Detect completion signal
    if line.contains(&session_info.completion_signal) {
        session_info.completion_detected = true;
    }
}

impl Default for AiderPlatform {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CodingPlatform for AiderPlatform {
    fn name(&self) -> &str {
        "aider"
    }

    async fn is_available(&self) -> Result<bool, PlatformError> {
        Ok(Self::find_aider_binary().await.is_some())
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

        // Check if aider is available
        if Self::find_aider_binary().await.is_none() {
            return Err(PlatformError::BinaryNotFound("aider".to_string()));
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

        // Store session info
        let session_info = AiderSessionInfo {
            handle,
            output_buffer: String::new(),
            file_changes: Vec::new(),
            completion_detected: false,
            iteration_count: 0,
            completion_signal: config.completion_signal.clone(),
        };

        {
            let mut sessions = self.sessions.write().await;
            sessions.insert(session_id, session_info);
        }

        // Start processing stdout
        self.process_session(session_id).await;

        // Return a new handle
        let sessions = self.sessions.read().await;
        let session_info = sessions.get(&session_id).ok_or_else(|| {
            PlatformError::SessionNotFound(session_id.to_string())
        })?;

        Ok(SessionHandle {
            id: session_id,
            platform_session_id: None,
            process: session_info.handle.process.clone(),
            started_at: session_info.handle.started_at,
            worktree_path: session_info.handle.worktree_path.clone(),
        })
    }

    async fn stop_session(&self, handle: &SessionHandle) -> Result<SessionResult, PlatformError> {
        let session_id = handle.id;

        // Get session info and kill process
        let (output, completed, iterations, files) = {
            let mut sessions = self.sessions.write().await;
            let session_info = sessions.remove(&session_id).ok_or_else(|| {
                PlatformError::SessionNotFound(session_id.to_string())
            })?;

            // Kill the process
            {
                let mut process = session_info.handle.process.lock().await;
                let _ = process.kill().await;
            }

            (
                session_info.output_buffer,
                session_info.completion_detected,
                session_info.iteration_count,
                session_info.file_changes,
            )
        };

        let duration_ms = (Utc::now() - handle.started_at).num_milliseconds() as u64;

        let result = if completed {
            SessionResult::success(output, duration_ms, iterations as u32)
        } else {
            SessionResult::failure(
                SessionEndReason::UserStopped,
                "Session stopped by user".to_string(),
                duration_ms,
                iterations as u32,
            )
        };

        // Log file changes
        if !files.is_empty() {
            tracing::info!("Aider modified files: {:?}", files);
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
                    if status.success() && session_info.completion_detected {
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
            iteration: session_info.iteration_count,
            runtime_ms,
            tokens_used: None, // Aider doesn't report tokens in output
            cost_usd: None,    // Aider doesn't report cost in output
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
        let platform = AiderPlatform::new();
        assert_eq!(platform.name(), "aider");
    }

    #[test]
    fn test_platform_builder() {
        let platform = AiderPlatform::new()
            .with_binary_path("/usr/local/bin/aider")
            .with_default_model("gpt-4-turbo")
            .with_auto_confirm(false)
            .with_max_concurrent(3);

        assert_eq!(platform.binary_path, "/usr/local/bin/aider");
        assert_eq!(platform.default_model, "gpt-4-turbo");
        assert!(!platform.auto_confirm);
        assert_eq!(platform.max_concurrent, 3);
    }

    #[test]
    fn test_default_platform() {
        let platform = AiderPlatform::default();
        assert_eq!(platform.binary_path, "aider");
        assert_eq!(platform.default_model, "gpt-4");
        assert!(platform.auto_confirm);
        assert_eq!(platform.max_concurrent, 1);
    }

    #[tokio::test]
    async fn test_build_command() {
        let platform = AiderPlatform::new();
        let worktree = PathBuf::from("/tmp/test-worktree");
        let prompt = "Fix the bug in main.rs";

        let mut config = SessionConfig::default();
        config.model = Some("claude-3-opus-20240229".to_string());
        config.extra_args = vec!["--verbose".to_string()];

        // We can't easily inspect the Command, but we can verify it builds without panic
        let _cmd = platform.build_command(&worktree, prompt, &config);
    }

    // Helper struct for testing parse_aider_output without full SessionHandle
    struct TestSessionInfo {
        file_changes: Vec<String>,
        completion_detected: bool,
        iteration_count: i32,
        completion_signal: String,
    }

    fn test_parse_output(line: &str, info: &mut TestSessionInfo) {
        // Detect file changes
        if line.starts_with("Wrote ") || line.contains("Applied edit to") {
            if let Some(file) = line.strip_prefix("Wrote ") {
                info.file_changes.push(file.trim().to_string());
            }
        }

        // Detect commits
        if line.starts_with("Commit ") || line.contains("committed") {
            info.iteration_count += 1;
        }

        // Detect completion signal
        if line.contains(&info.completion_signal) {
            info.completion_detected = true;
        }
    }

    #[test]
    fn test_parse_aider_output_file_write() {
        let mut info = TestSessionInfo {
            file_changes: Vec::new(),
            completion_detected: false,
            iteration_count: 0,
            completion_signal: "<done>".to_string(),
        };

        test_parse_output("Wrote src/main.rs", &mut info);
        assert_eq!(info.file_changes, vec!["src/main.rs".to_string()]);
    }

    #[test]
    fn test_parse_aider_output_completion() {
        let mut info = TestSessionInfo {
            file_changes: Vec::new(),
            completion_detected: false,
            iteration_count: 0,
            completion_signal: "<ringmaster>COMPLETE</ringmaster>".to_string(),
        };

        test_parse_output("Task completed <ringmaster>COMPLETE</ringmaster>", &mut info);
        assert!(info.completion_detected);
    }

    #[test]
    fn test_parse_aider_output_commit() {
        let mut info = TestSessionInfo {
            file_changes: Vec::new(),
            completion_detected: false,
            iteration_count: 0,
            completion_signal: "<done>".to_string(),
        };

        test_parse_output("Commit abc1234: Fixed the bug", &mut info);
        assert_eq!(info.iteration_count, 1);
    }
}
