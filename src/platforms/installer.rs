//! Claude Code CLI auto-installer
//!
//! Automatically installs Claude Code CLI using the official native installer
//! when running in a codespace/devcontainer environment.

use std::path::PathBuf;
use std::process::Stdio;
use tokio::process::Command;
use tracing::{info, warn, error};

/// Installation result
#[derive(Debug)]
pub struct InstallResult {
    pub success: bool,
    pub binary_path: Option<PathBuf>,
    pub version: Option<String>,
    pub message: String,
}

/// Check if Claude Code CLI is installed and return its path
pub async fn find_claude_binary() -> Option<PathBuf> {
    // Check common locations in order of preference
    let paths_to_check = [
        // Native installer location (most common)
        dirs::home_dir().map(|h| h.join(".claude").join("local").join("claude")),
        // Homebrew on macOS
        Some(PathBuf::from("/opt/homebrew/bin/claude")),
        Some(PathBuf::from("/usr/local/bin/claude")),
        // npm global install (deprecated but might exist)
        dirs::home_dir().map(|h| h.join(".npm-global").join("bin").join("claude")),
    ];

    for path_opt in paths_to_check.into_iter().flatten() {
        if path_opt.exists() {
            // Verify it's executable
            if let Ok(output) = Command::new(&path_opt)
                .arg("--version")
                .output()
                .await
            {
                if output.status.success() {
                    return Some(path_opt);
                }
            }
        }
    }

    // Fallback: check PATH
    if let Ok(output) = Command::new("which").arg("claude").output().await {
        if output.status.success() {
            let path_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path_str.is_empty() {
                return Some(PathBuf::from(path_str));
            }
        }
    }

    None
}

/// Get the installed version of Claude Code
pub async fn get_installed_version() -> Option<String> {
    let output = Command::new("claude")
        .arg("--version")
        .output()
        .await
        .ok()?;

    if output.status.success() {
        let version = String::from_utf8_lossy(&output.stdout)
            .trim()
            .to_string();
        // Parse "claude-code vX.Y.Z" format
        version.split_whitespace()
            .last()
            .map(|v| v.trim_start_matches('v').to_string())
    } else {
        None
    }
}

/// Install Claude Code CLI using the official native installer
///
/// This runs the equivalent of: curl -fsSL https://claude.ai/install.sh | bash
pub async fn install_claude_code() -> InstallResult {
    info!("Installing Claude Code CLI via native installer...");

    // Run the official installer script
    let install_result = Command::new("bash")
        .arg("-c")
        .arg("curl -fsSL https://claude.ai/install.sh | bash")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .await;

    match install_result {
        Ok(output) => {
            if output.status.success() {
                info!("Claude Code CLI installer completed successfully");

                // Verify installation
                if let Some(path) = find_claude_binary().await {
                    let version = get_installed_version().await;
                    InstallResult {
                        success: true,
                        binary_path: Some(path),
                        version,
                        message: "Claude Code CLI installed successfully".to_string(),
                    }
                } else {
                    // Installation claimed success but binary not found
                    // This can happen if PATH wasn't updated in current session
                    let default_path = dirs::home_dir()
                        .map(|h| h.join(".claude").join("local").join("claude"));

                    if let Some(ref path) = default_path {
                        if path.exists() {
                            return InstallResult {
                                success: true,
                                binary_path: default_path,
                                version: None,
                                message: "Claude Code CLI installed. Binary at ~/.claude/local/claude".to_string(),
                            };
                        }
                    }

                    warn!("Installer succeeded but claude binary not found in PATH");
                    InstallResult {
                        success: false,
                        binary_path: None,
                        version: None,
                        message: "Installer completed but binary not found. Try restarting your shell.".to_string(),
                    }
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                error!("Claude Code CLI installation failed: {}", stderr);
                InstallResult {
                    success: false,
                    binary_path: None,
                    version: None,
                    message: format!("Installation failed: {}", stderr),
                }
            }
        }
        Err(e) => {
            error!("Failed to run installer: {}", e);
            InstallResult {
                success: false,
                binary_path: None,
                version: None,
                message: format!("Failed to run installer: {}", e),
            }
        }
    }
}

/// Ensure Claude Code CLI is available, installing if necessary
///
/// Returns the path to the claude binary, installing it first if needed.
pub async fn ensure_claude_available() -> Result<PathBuf, String> {
    // First check if already installed
    if let Some(path) = find_claude_binary().await {
        let version = get_installed_version().await.unwrap_or_else(|| "unknown".to_string());
        info!("Claude Code CLI v{} found at {:?}", version, path);
        return Ok(path);
    }

    // Not installed - attempt auto-install
    info!("Claude Code CLI not found, attempting auto-installation...");

    let result = install_claude_code().await;

    if result.success {
        if let Some(path) = result.binary_path {
            return Ok(path);
        }
    }

    Err(result.message)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_find_claude_binary() {
        // This test just verifies the function doesn't panic
        let _ = find_claude_binary().await;
    }

    #[tokio::test]
    async fn test_get_installed_version() {
        // This test just verifies the function doesn't panic
        let _ = get_installed_version().await;
    }
}
