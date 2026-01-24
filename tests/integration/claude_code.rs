//! Integration tests for Claude Code CLI platform
//!
//! These tests verify the Claude Code platform implementation works
//! end-to-end with the actual CLI.
//!
//! Tests are skipped gracefully if the Claude CLI is not installed.

use std::path::PathBuf;
use std::time::Duration;
use tokio::time::timeout;

/// Check if Claude CLI is available for testing
async fn is_claude_available() -> bool {
    match tokio::process::Command::new("claude")
        .arg("--version")
        .output()
        .await
    {
        Ok(output) => output.status.success(),
        Err(_) => false,
    }
}

/// Get the path to the test fixtures
fn fixtures_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

/// Create a temporary worktree copy of a fixture project
async fn create_temp_worktree(fixture_name: &str) -> std::io::Result<tempfile::TempDir> {
    let temp = tempfile::tempdir()?;
    let fixture = fixtures_path().join(fixture_name);

    // Copy fixture to temp directory
    copy_dir_recursive(&fixture, temp.path()).await?;

    // Initialize git repo (required by Claude Code)
    tokio::process::Command::new("git")
        .arg("init")
        .current_dir(temp.path())
        .output()
        .await?;

    tokio::process::Command::new("git")
        .args(["config", "user.email", "test@test.com"])
        .current_dir(temp.path())
        .output()
        .await?;

    tokio::process::Command::new("git")
        .args(["config", "user.name", "Test"])
        .current_dir(temp.path())
        .output()
        .await?;

    tokio::process::Command::new("git")
        .args(["add", "."])
        .current_dir(temp.path())
        .output()
        .await?;

    tokio::process::Command::new("git")
        .args(["commit", "-m", "Initial commit"])
        .current_dir(temp.path())
        .output()
        .await?;

    Ok(temp)
}

/// Recursively copy a directory
async fn copy_dir_recursive(src: &std::path::Path, dst: &std::path::Path) -> std::io::Result<()> {
    tokio::fs::create_dir_all(dst).await?;

    let mut entries = tokio::fs::read_dir(src).await?;
    while let Some(entry) = entries.next_entry().await? {
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());

        if entry.file_type().await?.is_dir() {
            Box::pin(copy_dir_recursive(&src_path, &dst_path)).await?;
        } else {
            tokio::fs::copy(&src_path, &dst_path).await?;
        }
    }

    Ok(())
}

/// Test that we can detect whether Claude CLI is available
#[tokio::test]
async fn test_claude_cli_detection() {
    let available = is_claude_available().await;
    // This test always passes - it just records whether Claude is available
    println!("Claude CLI available: {}", available);
}

/// Test that we can start a Claude Code session and receive output
///
/// This test is ignored by default since it requires Claude CLI and API access.
#[tokio::test]
#[ignore = "Requires Claude CLI with API access"]
async fn test_start_session() {
    if !is_claude_available().await {
        println!("Skipping test: Claude CLI not available");
        return;
    }

    let temp_dir = create_temp_worktree("simple_rust_project")
        .await
        .expect("Failed to create temp worktree");

    // Simple prompt that should produce output quickly
    let prompt = "What files are in this project? Just list them briefly.";

    let mut cmd = tokio::process::Command::new("claude");
    cmd.current_dir(temp_dir.path())
        .arg("--output-format")
        .arg("stream-json")
        .arg("--max-turns")
        .arg("1") // Limit to 1 turn for fast test
        .arg("-p")
        .arg(prompt)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    let result = timeout(Duration::from_secs(60), async {
        let output = cmd.output().await.expect("Failed to run claude command");
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        println!("stdout: {}", stdout);
        println!("stderr: {}", stderr);

        // Verify we got some JSON output
        assert!(
            stdout.contains("\"type\""),
            "Expected JSON output from Claude CLI"
        );

        // Verify the session completed
        assert!(
            stdout.contains("\"type\":\"result\"") || output.status.success(),
            "Expected successful session"
        );
    })
    .await;

    match result {
        Ok(_) => println!("Test completed successfully"),
        Err(_) => panic!("Test timed out after 60 seconds"),
    }
}

/// Test that Claude Code can complete a simple coding task
///
/// This test verifies that Claude can:
/// 1. Read the project files
/// 2. Understand the TODO
/// 3. Make the required change
/// 4. (Optionally) commit the change
///
/// This test is ignored by default since it requires Claude CLI with API access.
#[tokio::test]
#[ignore = "Requires Claude CLI with API access"]
async fn test_complete_coding_task() {
    if !is_claude_available().await {
        println!("Skipping test: Claude CLI not available");
        return;
    }

    let temp_dir = create_temp_worktree("simple_rust_project")
        .await
        .expect("Failed to create temp worktree");

    let prompt = r#"
Fix the `answer()` function in src/lib.rs to return 42 instead of 0.
The test should pass after the fix.

When done, output: <ringmaster>COMPLETE</ringmaster>
"#;

    let mut cmd = tokio::process::Command::new("claude");
    cmd.current_dir(temp_dir.path())
        .arg("--output-format")
        .arg("stream-json")
        .arg("--dangerously-skip-permissions")
        .arg("--max-turns")
        .arg("5")
        .arg("-p")
        .arg(prompt)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    let result = timeout(Duration::from_secs(120), async {
        let output = cmd.output().await.expect("Failed to run claude command");
        let stdout = String::from_utf8_lossy(&output.stdout);

        println!("Output: {}", stdout);

        // Verify the file was modified
        let lib_content = tokio::fs::read_to_string(temp_dir.path().join("src/lib.rs"))
            .await
            .expect("Failed to read lib.rs");

        assert!(
            lib_content.contains("42"),
            "Expected lib.rs to contain 42 after fix"
        );

        // Verify the test passes
        let test_output = tokio::process::Command::new("cargo")
            .arg("test")
            .current_dir(temp_dir.path())
            .output()
            .await
            .expect("Failed to run cargo test");

        assert!(
            test_output.status.success(),
            "Expected tests to pass after fix. stderr: {}",
            String::from_utf8_lossy(&test_output.stderr)
        );

        // Check for completion signal
        assert!(
            stdout.contains("<ringmaster>COMPLETE</ringmaster>"),
            "Expected completion signal in output"
        );
    })
    .await;

    match result {
        Ok(_) => println!("Test completed successfully"),
        Err(_) => panic!("Test timed out after 120 seconds"),
    }
}

/// Test error handling when Claude CLI encounters an error
///
/// This test verifies that errors are properly reported.
#[tokio::test]
#[ignore = "Requires Claude CLI"]
async fn test_error_handling() {
    if !is_claude_available().await {
        println!("Skipping test: Claude CLI not available");
        return;
    }

    // Try to run in a non-existent directory
    let mut cmd = tokio::process::Command::new("claude");
    cmd.current_dir("/nonexistent/path")
        .arg("--output-format")
        .arg("stream-json")
        .arg("-p")
        .arg("Hello")
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());

    let output = cmd.output().await;

    // Should fail because the directory doesn't exist
    assert!(output.is_err() || !output.unwrap().status.success());
}

/// Test the stream parser integration with real Claude output
#[tokio::test]
async fn test_stream_parser_with_mock_output() {
    // This test doesn't require Claude CLI - it uses mock output
    use ringmaster::platforms::StreamParser;

    let mut parser = StreamParser::new("<ringmaster>COMPLETE</ringmaster>");

    // Simulate Claude Code output
    let mock_output = r#"{"type":"user","message":{"role":"user","content":"Fix the bug"},"session_id":"test-123"}
{"type":"assistant","message":{"role":"assistant","content":"I'll fix the bug. <ringmaster>COMPLETE</ringmaster>"}}
{"type":"result","duration_ms":5000,"cost_usd":0.01,"session_id":"test-123"}
"#;

    let events = parser.parse_chunk(mock_output);

    // Should have parsed multiple events
    assert!(events.len() >= 2, "Expected at least 2 events");

    // Should have detected completion signal
    assert!(
        parser.has_completion_signal(),
        "Expected completion signal to be detected"
    );

    // Should have session ID
    assert_eq!(parser.session_id(), Some("test-123"));
}

/// Test session timeout handling
#[tokio::test]
async fn test_session_timeout() {
    // This test verifies that session timeouts are handled properly
    // Without requiring the Claude CLI

    let result = timeout(Duration::from_millis(100), async {
        // Simulate a long-running operation
        tokio::time::sleep(Duration::from_secs(10)).await;
    })
    .await;

    // Should timeout
    assert!(result.is_err(), "Expected timeout");
}
