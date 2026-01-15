//! Claude API integration for code generation
//!
//! This module provides a client for interacting with the Anthropic Claude API
//! to generate code and handle autonomous coding loops.

use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::env;
use thiserror::Error;

const ANTHROPIC_API_URL: &str = "https://api.anthropic.com/v1/messages";
const DEFAULT_MODEL: &str = "claude-sonnet-4-20250514";
const MAX_TOKENS: u32 = 8192;
const ANTHROPIC_VERSION: &str = "2023-06-01";

#[derive(Error, Debug)]
pub enum ClaudeError {
    #[error("API key not configured")]
    MissingApiKey,

    #[error("HTTP request failed: {0}")]
    RequestFailed(#[from] reqwest::Error),

    #[error("API error: {status} - {message}")]
    ApiError { status: u16, message: String },

    #[error("Failed to parse response: {0}")]
    ParseError(String),

    #[error("Rate limited, retry after {retry_after:?} seconds")]
    RateLimited { retry_after: Option<u64> },
}

/// Role of a message in the conversation
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Role {
    User,
    Assistant,
}

/// A message in the conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: Role,
    pub content: String,
}

impl Message {
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: Role::User,
            content: content.into(),
        }
    }

    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: Role::Assistant,
            content: content.into(),
        }
    }
}

/// Request body for the Claude messages API
#[derive(Debug, Serialize)]
struct MessagesRequest<'a> {
    model: &'a str,
    max_tokens: u32,
    system: Option<&'a str>,
    messages: &'a [Message],
    #[serde(skip_serializing_if = "Option::is_none")]
    stop_sequences: Option<&'a [&'a str]>,
}

/// Content block in the response
#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
pub enum ContentBlock {
    #[serde(rename = "text")]
    Text { text: String },
    #[serde(rename = "tool_use")]
    ToolUse {
        id: String,
        name: String,
        input: serde_json::Value,
    },
}

/// Usage statistics from the API
#[derive(Debug, Clone, Deserialize)]
pub struct Usage {
    pub input_tokens: u32,
    pub output_tokens: u32,
}

/// Response from the Claude messages API
#[derive(Debug, Deserialize)]
struct MessagesResponse {
    id: String,
    content: Vec<ContentBlock>,
    model: String,
    stop_reason: Option<String>,
    stop_sequence: Option<String>,
    usage: Usage,
}

/// Stop reason for completion
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StopReason {
    /// Model reached natural end
    EndTurn,
    /// Max tokens reached
    MaxTokens,
    /// Stop sequence detected
    StopSequence(String),
    /// Tool use requested
    ToolUse,
    /// Unknown reason
    Unknown(String),
}

/// Completion response with parsed results
#[derive(Debug, Clone)]
pub struct CompletionResponse {
    /// The generated text content
    pub content: String,
    /// Raw content blocks from the API
    pub raw_content: Vec<String>,
    /// Input tokens used
    pub input_tokens: u32,
    /// Output tokens used
    pub output_tokens: u32,
    /// Why the completion stopped
    pub stop_reason: StopReason,
    /// Response ID from Claude
    pub id: String,
    /// Model used
    pub model: String,
}

impl CompletionResponse {
    /// Calculate cost in USD based on token usage
    pub fn cost_usd(&self, model: &str) -> f64 {
        // Pricing as of 2024 (per million tokens)
        let (input_price, output_price) = match model {
            m if m.contains("opus") => (15.0, 75.0),
            m if m.contains("sonnet") => (3.0, 15.0),
            m if m.contains("haiku") => (0.25, 1.25),
            _ => (3.0, 15.0), // Default to sonnet pricing
        };

        let input_cost = (self.input_tokens as f64 / 1_000_000.0) * input_price;
        let output_cost = (self.output_tokens as f64 / 1_000_000.0) * output_price;
        input_cost + output_cost
    }

    /// Check if the completion signal was found
    pub fn has_completion_signal(&self, signal: &str) -> bool {
        self.content.contains(signal)
    }
}

/// Claude API client
pub struct ClaudeClient {
    client: Client,
    api_key: String,
    model: String,
    max_tokens: u32,
}

impl ClaudeClient {
    /// Create a new Claude client
    ///
    /// Reads API key from ANTHROPIC_API_KEY environment variable
    pub fn new() -> Result<Self, ClaudeError> {
        let api_key = env::var("ANTHROPIC_API_KEY")
            .map_err(|_| ClaudeError::MissingApiKey)?;

        Ok(Self {
            client: Client::new(),
            api_key,
            model: DEFAULT_MODEL.to_string(),
            max_tokens: MAX_TOKENS,
        })
    }

    /// Create a client with a specific API key
    pub fn with_api_key(api_key: impl Into<String>) -> Self {
        Self {
            client: Client::new(),
            api_key: api_key.into(),
            model: DEFAULT_MODEL.to_string(),
            max_tokens: MAX_TOKENS,
        }
    }

    /// Set the model to use
    pub fn with_model(mut self, model: impl Into<String>) -> Self {
        self.model = model.into();
        self
    }

    /// Set maximum tokens for response
    pub fn with_max_tokens(mut self, max_tokens: u32) -> Self {
        self.max_tokens = max_tokens;
        self
    }

    /// Get the current model
    pub fn model(&self) -> &str {
        &self.model
    }

    /// Send a completion request to Claude
    pub async fn complete(
        &self,
        system_prompt: Option<&str>,
        messages: &[Message],
    ) -> Result<CompletionResponse, ClaudeError> {
        self.complete_with_stop(system_prompt, messages, None).await
    }

    /// Send a completion request with custom stop sequences
    pub async fn complete_with_stop(
        &self,
        system_prompt: Option<&str>,
        messages: &[Message],
        stop_sequences: Option<&[&str]>,
    ) -> Result<CompletionResponse, ClaudeError> {
        let request = MessagesRequest {
            model: &self.model,
            max_tokens: self.max_tokens,
            system: system_prompt,
            messages,
            stop_sequences,
        };

        let response = self
            .client
            .post(ANTHROPIC_API_URL)
            .header("x-api-key", &self.api_key)
            .header("anthropic-version", ANTHROPIC_VERSION)
            .header("content-type", "application/json")
            .json(&request)
            .send()
            .await?;

        let status = response.status();

        if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
            let retry_after = response
                .headers()
                .get("retry-after")
                .and_then(|h| h.to_str().ok())
                .and_then(|s| s.parse().ok());
            return Err(ClaudeError::RateLimited { retry_after });
        }

        if !status.is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(ClaudeError::ApiError {
                status: status.as_u16(),
                message: error_text,
            });
        }

        let response: MessagesResponse = response
            .json()
            .await
            .map_err(|e| ClaudeError::ParseError(e.to_string()))?;

        // Extract text content
        let mut content_parts = Vec::new();
        for block in &response.content {
            if let ContentBlock::Text { text } = block {
                content_parts.push(text.clone());
            }
        }
        let content = content_parts.join("\n");

        // Parse stop reason
        let stop_reason = match response.stop_reason.as_deref() {
            Some("end_turn") => StopReason::EndTurn,
            Some("max_tokens") => StopReason::MaxTokens,
            Some("stop_sequence") => {
                StopReason::StopSequence(response.stop_sequence.unwrap_or_default())
            }
            Some("tool_use") => StopReason::ToolUse,
            Some(other) => StopReason::Unknown(other.to_string()),
            None => StopReason::EndTurn,
        };

        Ok(CompletionResponse {
            content,
            raw_content: content_parts,
            input_tokens: response.usage.input_tokens,
            output_tokens: response.usage.output_tokens,
            stop_reason,
            id: response.id,
            model: response.model,
        })
    }

    /// Estimate token count for a string (rough approximation)
    pub fn estimate_tokens(text: &str) -> u32 {
        // Rough estimate: ~4 characters per token for English
        (text.len() as f64 / 4.0).ceil() as u32
    }

    /// Calculate cost for token counts
    pub fn calculate_cost(&self, input_tokens: u32, output_tokens: u32) -> f64 {
        let (input_price, output_price) = match self.model.as_str() {
            m if m.contains("opus") => (15.0, 75.0),
            m if m.contains("sonnet") => (3.0, 15.0),
            m if m.contains("haiku") => (0.25, 1.25),
            _ => (3.0, 15.0),
        };

        let input_cost = (input_tokens as f64 / 1_000_000.0) * input_price;
        let output_cost = (output_tokens as f64 / 1_000_000.0) * output_price;
        input_cost + output_cost
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_message_creation() {
        let user_msg = Message::user("Hello");
        assert_eq!(user_msg.role, Role::User);
        assert_eq!(user_msg.content, "Hello");

        let assistant_msg = Message::assistant("Hi there!");
        assert_eq!(assistant_msg.role, Role::Assistant);
        assert_eq!(assistant_msg.content, "Hi there!");
    }

    #[test]
    fn test_token_estimation() {
        // 100 characters should be roughly 25 tokens
        let text = "a".repeat(100);
        let tokens = ClaudeClient::estimate_tokens(&text);
        assert_eq!(tokens, 25);
    }

    #[test]
    fn test_cost_calculation() {
        // Create client with dummy key for testing
        let client = ClaudeClient::with_api_key("test-key")
            .with_model("claude-sonnet-4-20250514");

        // 1M input tokens + 500K output tokens
        // Sonnet: $3/M input, $15/M output
        // Cost = 3 + 7.5 = 10.5
        let cost = client.calculate_cost(1_000_000, 500_000);
        assert!((cost - 10.5).abs() < 0.01);
    }

    #[test]
    fn test_completion_signal_detection() {
        let response = CompletionResponse {
            content: "Here's the code\n<promise>COMPLETE</promise>".to_string(),
            raw_content: vec!["Here's the code\n<promise>COMPLETE</promise>".to_string()],
            input_tokens: 100,
            output_tokens: 50,
            stop_reason: StopReason::EndTurn,
            id: "test-id".to_string(),
            model: "claude-sonnet-4".to_string(),
        };

        assert!(response.has_completion_signal("<promise>COMPLETE</promise>"));
        assert!(!response.has_completion_signal("<promise>INCOMPLETE</promise>"));
    }
}
