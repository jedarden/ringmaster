//! Stream parser for Claude Code JSON output
//!
//! Claude Code with `--output-format stream-json` outputs newline-delimited JSON
//! with various event types. This module parses that stream.

use chrono::Utc;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::types::{SessionEndReason, SessionEvent};

/// Raw message type from Claude Code stream
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClaudeCodeMessage {
    /// Initial message (user prompt sent)
    #[serde(rename = "user")]
    User {
        message: MessageContent,
        session_id: Option<String>,
    },

    /// Assistant response
    #[serde(rename = "assistant")]
    Assistant {
        message: MessageContent,
        session_id: Option<String>,
    },

    /// System message
    #[serde(rename = "system")]
    System {
        message: String,
        session_id: Option<String>,
    },

    /// Result/completion message
    #[serde(rename = "result")]
    Result {
        duration_ms: Option<u64>,
        cost_usd: Option<f64>,
        session_id: Option<String>,
        #[serde(default)]
        is_error: bool,
        #[serde(default)]
        num_turns: Option<u32>,
    },
}

/// Content within a message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageContent {
    pub role: Option<String>,
    pub content: ContentValue,
}

/// Content can be either a string or array of content blocks
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum ContentValue {
    Text(String),
    Blocks(Vec<ContentBlock>),
}

impl ContentValue {
    /// Extract text content
    pub fn as_text(&self) -> String {
        match self {
            ContentValue::Text(s) => s.clone(),
            ContentValue::Blocks(blocks) => {
                blocks
                    .iter()
                    .filter_map(|b| {
                        match b {
                            ContentBlock::Text { text } => Some(text.clone()),
                            ContentBlock::ToolUse { .. } => None,
                            ContentBlock::ToolResult { content, .. } => Some(content.clone()),
                        }
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            }
        }
    }
}

/// Content block types
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ContentBlock {
    /// Text content
    Text { text: String },

    /// Tool use (assistant invoking a tool)
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: Value,
    },

    /// Tool result
    #[serde(rename = "tool_result")]
    ToolResult {
        tool_use_id: String,
        content: String,
        #[serde(default)]
        is_error: bool,
    },
}

/// Parser for Claude Code JSON stream output
pub struct StreamParser {
    /// Buffer for incomplete lines
    buffer: String,
    /// Accumulated session ID
    session_id: Option<String>,
    /// Completion signal to detect
    completion_signal: String,
    /// Total cost accumulated
    total_cost: f64,
    /// Total tokens accumulated (estimated from content length)
    estimated_tokens: i64,
    /// Number of iterations
    iteration_count: i32,
    /// Last assistant response for completion signal detection
    last_response: String,
    /// Whether completion signal was detected
    completion_detected: bool,
}

impl StreamParser {
    /// Create a new stream parser
    pub fn new(completion_signal: &str) -> Self {
        Self {
            buffer: String::new(),
            session_id: None,
            completion_signal: completion_signal.to_string(),
            total_cost: 0.0,
            estimated_tokens: 0,
            iteration_count: 0,
            last_response: String::new(),
            completion_detected: false,
        }
    }

    /// Parse a chunk of data and return any complete events
    pub fn parse_chunk(&mut self, data: &str) -> Vec<SessionEvent> {
        let mut events = Vec::new();

        // Add to buffer
        self.buffer.push_str(data);

        // Process complete lines
        while let Some(newline_pos) = self.buffer.find('\n') {
            let line = self.buffer[..newline_pos].to_string();
            self.buffer = self.buffer[newline_pos + 1..].to_string();

            if let Some(event) = self.parse_line(&line) {
                events.push(event);
            }
        }

        events
    }

    /// Parse a single line of JSON
    fn parse_line(&mut self, line: &str) -> Option<SessionEvent> {
        let line = line.trim();
        if line.is_empty() {
            return None;
        }

        // Try to parse as JSON
        let msg: ClaudeCodeMessage = match serde_json::from_str(line) {
            Ok(m) => m,
            Err(e) => {
                tracing::debug!("Failed to parse Claude Code line: {} - {}", e, line);
                return None;
            }
        };

        match msg {
            ClaudeCodeMessage::User { message, session_id } => {
                if let Some(id) = session_id {
                    if self.session_id.is_none() {
                        self.session_id = Some(id.clone());
                        return Some(SessionEvent::Started {
                            session_id: id,
                            timestamp: Utc::now(),
                        });
                    }
                }

                let content = message.content.as_text();
                self.estimated_tokens += estimate_tokens(&content);

                Some(SessionEvent::UserMessage {
                    content,
                    timestamp: Utc::now(),
                })
            }

            ClaudeCodeMessage::Assistant { message, session_id } => {
                if self.session_id.is_none() {
                    if let Some(id) = session_id {
                        self.session_id = Some(id);
                    }
                }

                self.iteration_count += 1;

                // Process content blocks
                match &message.content {
                    ContentValue::Blocks(blocks) => {
                        for block in blocks {
                            match block {
                                ContentBlock::ToolUse { name, input, .. } => {
                                    return Some(SessionEvent::ToolUse {
                                        tool_name: name.clone(),
                                        input: input.clone(),
                                        timestamp: Utc::now(),
                                    });
                                }
                                ContentBlock::ToolResult { content, is_error, .. } => {
                                    return Some(SessionEvent::ToolResult {
                                        tool_name: "unknown".to_string(),
                                        output: content.clone(),
                                        is_error: *is_error,
                                        timestamp: Utc::now(),
                                    });
                                }
                                ContentBlock::Text { text } => {
                                    self.last_response = text.clone();
                                    self.estimated_tokens += estimate_tokens(text);

                                    // Check for completion signal
                                    if text.contains(&self.completion_signal) {
                                        self.completion_detected = true;
                                        return Some(SessionEvent::CompletionSignal {
                                            timestamp: Utc::now(),
                                        });
                                    }
                                }
                            }
                        }
                    }
                    ContentValue::Text(text) => {
                        self.last_response = text.clone();
                        self.estimated_tokens += estimate_tokens(text);

                        // Check for completion signal
                        if text.contains(&self.completion_signal) {
                            self.completion_detected = true;
                            return Some(SessionEvent::CompletionSignal {
                                timestamp: Utc::now(),
                            });
                        }
                    }
                }

                let content = message.content.as_text();
                Some(SessionEvent::AssistantMessage {
                    content,
                    timestamp: Utc::now(),
                })
            }

            ClaudeCodeMessage::System { message, .. } => {
                Some(SessionEvent::System {
                    message,
                    timestamp: Utc::now(),
                })
            }

            ClaudeCodeMessage::Result {
                duration_ms,
                cost_usd,
                is_error,
                num_turns: _,
                ..
            } => {
                if let Some(cost) = cost_usd {
                    self.total_cost += cost;
                }

                let result = if self.completion_detected {
                    SessionEndReason::Completed
                } else if is_error {
                    SessionEndReason::Error
                } else {
                    SessionEndReason::ProcessExited
                };

                Some(SessionEvent::Ended {
                    result,
                    duration_ms: duration_ms.unwrap_or(0),
                    total_cost_usd: Some(self.total_cost),
                    timestamp: Utc::now(),
                })
            }
        }
    }

    /// Check if completion signal was detected
    pub fn has_completion_signal(&self) -> bool {
        self.completion_detected
    }

    /// Get the session ID
    pub fn session_id(&self) -> Option<&str> {
        self.session_id.as_deref()
    }

    /// Get total cost
    pub fn total_cost(&self) -> f64 {
        self.total_cost
    }

    /// Get estimated tokens
    pub fn estimated_tokens(&self) -> i64 {
        self.estimated_tokens
    }

    /// Get iteration count
    pub fn iteration_count(&self) -> i32 {
        self.iteration_count
    }

    /// Get the last assistant response
    pub fn last_response(&self) -> &str {
        &self.last_response
    }

    /// Extract commit SHA from the last response
    pub fn extract_commit_sha(&self) -> Option<String> {
        extract_commit_sha(&self.last_response)
    }
}

/// Estimate token count from text (rough approximation)
fn estimate_tokens(text: &str) -> i64 {
    // Rough estimate: ~4 characters per token for English
    (text.len() as f64 / 4.0).ceil() as i64
}

/// Extract commit SHA from response text
fn extract_commit_sha(response: &str) -> Option<String> {
    // Pattern for full SHA (40 characters)
    let full_sha_re = Regex::new(r"\b[a-f0-9]{40}\b").ok()?;
    // Pattern for short SHA (7-8 characters) in git output format
    let git_output_re = Regex::new(r"\[[\w\-/]+\s+([a-f0-9]{7,8})\]").ok()?;
    // Pattern for commit context
    let short_sha_re = Regex::new(r"(?i)(?:commit|committed|sha)[:\s]+([a-f0-9]{7,8})\b").ok()?;

    // Try to find a full SHA first
    if let Some(m) = full_sha_re.find(response) {
        return Some(m.as_str().to_string());
    }

    // Try git output format
    if let Some(caps) = git_output_re.captures(response) {
        if let Some(m) = caps.get(1) {
            return Some(m.as_str().to_string());
        }
    }

    // Try short SHA with commit context
    if let Some(caps) = short_sha_re.captures(response) {
        if let Some(m) = caps.get(1) {
            return Some(m.as_str().to_string());
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stream_parser_new() {
        let parser = StreamParser::new("<done>DONE</done>");
        assert_eq!(parser.completion_signal, "<done>DONE</done>");
        assert!(!parser.has_completion_signal());
    }

    #[test]
    fn test_parse_user_message() {
        let mut parser = StreamParser::new("<done>");
        let json = r#"{"type":"user","message":{"role":"user","content":"Hello"},"session_id":"test-123"}"#;

        let events = parser.parse_chunk(&format!("{}\n", json));
        assert_eq!(events.len(), 1);

        match &events[0] {
            SessionEvent::Started { session_id, .. } => {
                assert_eq!(session_id, "test-123");
            }
            _ => panic!("Expected Started event"),
        }
    }

    #[test]
    fn test_parse_assistant_message() {
        let mut parser = StreamParser::new("<done>");
        // First, send a user message to establish session
        let user_json = r#"{"type":"user","message":{"role":"user","content":"Hello"},"session_id":"test-123"}"#;
        parser.parse_chunk(&format!("{}\n", user_json));

        let json = r#"{"type":"assistant","message":{"role":"assistant","content":"Hi there!"}}"#;
        let events = parser.parse_chunk(&format!("{}\n", json));

        assert_eq!(events.len(), 1);
        match &events[0] {
            SessionEvent::AssistantMessage { content, .. } => {
                assert_eq!(content, "Hi there!");
            }
            _ => panic!("Expected AssistantMessage event"),
        }
    }

    #[test]
    fn test_completion_signal_detection() {
        let mut parser = StreamParser::new("<done>COMPLETE</done>");
        let json = r#"{"type":"assistant","message":{"role":"assistant","content":"Task finished <done>COMPLETE</done>"}}"#;

        let events = parser.parse_chunk(&format!("{}\n", json));

        assert!(parser.has_completion_signal());
        assert!(events.iter().any(|e| matches!(e, SessionEvent::CompletionSignal { .. })));
    }

    #[test]
    fn test_parse_result() {
        let mut parser = StreamParser::new("<done>");
        let json = r#"{"type":"result","duration_ms":5000,"cost_usd":0.05,"session_id":"test-123"}"#;

        let events = parser.parse_chunk(&format!("{}\n", json));
        assert_eq!(events.len(), 1);

        match &events[0] {
            SessionEvent::Ended { duration_ms, total_cost_usd, .. } => {
                assert_eq!(*duration_ms, 5000);
                assert!(total_cost_usd.is_some());
            }
            _ => panic!("Expected Ended event"),
        }
    }

    #[test]
    fn test_extract_commit_sha_full() {
        let response = "Committed: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0";
        let sha = extract_commit_sha(response);
        assert_eq!(sha, Some("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0".to_string()));
    }

    #[test]
    fn test_extract_commit_sha_git_output() {
        let response = "[main abc1234] feat: add feature";
        let sha = extract_commit_sha(response);
        assert_eq!(sha, Some("abc1234".to_string()));
    }

    #[test]
    fn test_extract_commit_sha_with_context() {
        let response = "Successfully committed: abc1234";
        let sha = extract_commit_sha(response);
        assert_eq!(sha, Some("abc1234".to_string()));
    }

    #[test]
    fn test_content_value_as_text() {
        let text = ContentValue::Text("Hello".to_string());
        assert_eq!(text.as_text(), "Hello");

        let blocks = ContentValue::Blocks(vec![
            ContentBlock::Text { text: "Part 1".to_string() },
            ContentBlock::Text { text: "Part 2".to_string() },
        ]);
        assert_eq!(blocks.as_text(), "Part 1\nPart 2");
    }

    #[test]
    fn test_estimate_tokens() {
        assert_eq!(estimate_tokens("test"), 1); // 4 chars = 1 token
        assert_eq!(estimate_tokens("hello world"), 3); // 11 chars = ~3 tokens
    }

    #[test]
    fn test_parse_incomplete_json() {
        let mut parser = StreamParser::new("<done>");

        // Send partial JSON
        let events = parser.parse_chunk(r#"{"type":"user","#);
        assert!(events.is_empty());

        // Complete the JSON
        let events = parser.parse_chunk(r#""message":{"content":"test"},"session_id":"123"}"#);
        assert!(events.is_empty()); // Still no newline

        // Add newline
        let events = parser.parse_chunk("\n");
        assert_eq!(events.len(), 1);
    }
}
