//! RLM (Recursive Language Model) Summarization
//!
//! This module implements chat history compression using Claude to summarize
//! older messages while preserving important context. This allows for long
//! coding sessions without exceeding token limits.

use sqlx::SqlitePool;
use uuid::Uuid;

use crate::integrations::claude::{ClaudeClient, ClaudeError, Message};

/// Configuration for RLM summarization
#[derive(Debug, Clone)]
pub struct RlmConfig {
    /// Maximum tokens before triggering summarization
    pub max_history_tokens: u32,
    /// Target tokens after summarization
    pub target_tokens: u32,
    /// Minimum messages to keep unsummarized
    pub preserve_recent_messages: usize,
    /// Summary prompt template
    pub summary_prompt: String,
}

impl Default for RlmConfig {
    fn default() -> Self {
        Self {
            max_history_tokens: 50_000,
            target_tokens: 20_000,
            preserve_recent_messages: 6, // Keep last 3 exchanges
            summary_prompt: DEFAULT_SUMMARY_PROMPT.to_string(),
        }
    }
}

const DEFAULT_SUMMARY_PROMPT: &str = r#"You are summarizing a coding conversation between a developer and an AI assistant.

Create a concise summary that preserves:
1. Key technical decisions made
2. Important code changes and their locations
3. Outstanding issues or TODOs
4. The current state of the task

Focus on information that will be needed to continue the coding task effectively.

## Conversation to summarize:
"#;

/// Result of summarization
#[derive(Debug)]
pub struct SummarizationResult {
    /// The generated summary
    pub summary: String,
    /// Number of messages that were summarized
    pub messages_summarized: usize,
    /// Token count before summarization
    pub tokens_before: u32,
    /// Token count after summarization
    pub tokens_after: u32,
    /// Compression ratio achieved
    pub compression_ratio: f32,
}

/// RLM Summarizer for managing chat history size
pub struct RlmSummarizer {
    claude_client: ClaudeClient,
    config: RlmConfig,
}

impl RlmSummarizer {
    /// Create a new RLM summarizer
    pub fn new(claude_client: ClaudeClient) -> Self {
        Self {
            claude_client,
            config: RlmConfig::default(),
        }
    }

    /// Create with custom configuration
    pub fn with_config(claude_client: ClaudeClient, config: RlmConfig) -> Self {
        Self {
            claude_client,
            config,
        }
    }

    /// Check if chat history needs summarization
    pub fn needs_summarization(&self, messages: &[Message]) -> bool {
        let total_tokens = estimate_tokens_for_messages(messages);
        total_tokens > self.config.max_history_tokens
    }

    /// Summarize chat history, preserving recent messages
    pub async fn summarize(
        &self,
        messages: &[Message],
    ) -> Result<(Vec<Message>, SummarizationResult), ClaudeError> {
        let total_tokens_before = estimate_tokens_for_messages(messages);

        // Don't summarize if below threshold
        if total_tokens_before <= self.config.max_history_tokens {
            return Ok((
                messages.to_vec(),
                SummarizationResult {
                    summary: String::new(),
                    messages_summarized: 0,
                    tokens_before: total_tokens_before,
                    tokens_after: total_tokens_before,
                    compression_ratio: 1.0,
                },
            ));
        }

        // Split into messages to summarize and messages to keep
        let preserve_count = self.config.preserve_recent_messages.min(messages.len());
        let split_point = messages.len().saturating_sub(preserve_count);

        let to_summarize = &messages[..split_point];
        let to_preserve = &messages[split_point..];

        if to_summarize.is_empty() {
            return Ok((
                messages.to_vec(),
                SummarizationResult {
                    summary: String::new(),
                    messages_summarized: 0,
                    tokens_before: total_tokens_before,
                    tokens_after: total_tokens_before,
                    compression_ratio: 1.0,
                },
            ));
        }

        // Build prompt for summarization
        let conversation_text = format_messages_for_summary(to_summarize);
        let summary_request = format!("{}\n{}", self.config.summary_prompt, conversation_text);

        // Call Claude to generate summary
        let summary_messages = vec![Message::user(&summary_request)];
        let response = self.claude_client.complete(None, &summary_messages).await?;

        let summary = response.content;

        // Build new message list with summary
        let mut new_messages = Vec::new();

        // Add summary as a system-style context message
        new_messages.push(Message::user(format!(
            "## Previous Conversation Summary\n\n{}\n\n---\n\nContinuing from the summary above:",
            summary
        )));

        // Add preserved recent messages
        new_messages.extend(to_preserve.iter().cloned());

        let total_tokens_after = estimate_tokens_for_messages(&new_messages);

        let result = SummarizationResult {
            summary: summary.clone(),
            messages_summarized: to_summarize.len(),
            tokens_before: total_tokens_before,
            tokens_after: total_tokens_after,
            compression_ratio: total_tokens_before as f32 / total_tokens_after as f32,
        };

        Ok((new_messages, result))
    }

    /// Persist summarization result to database
    pub async fn save_summary(
        &self,
        pool: &SqlitePool,
        card_id: &Uuid,
        result: &SummarizationResult,
        first_message_id: &str,
        last_message_id: &str,
    ) -> Result<(), sqlx::Error> {
        let id = Uuid::new_v4().to_string();

        sqlx::query(
            r#"
            INSERT INTO rlm_summaries (
                id, card_id, summary, messages_summarized,
                tokens_before, tokens_after, compression_ratio,
                first_message_id, last_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            "#,
        )
        .bind(&id)
        .bind(&card_id.to_string())
        .bind(&result.summary)
        .bind(result.messages_summarized as i32)
        .bind(result.tokens_before as i32)
        .bind(result.tokens_after as i32)
        .bind(result.compression_ratio as f64)
        .bind(first_message_id)
        .bind(last_message_id)
        .execute(pool)
        .await?;

        // Mark summarized messages
        sqlx::query(
            r#"
            UPDATE chat_messages
            SET summarized = 1, summary_group_id = ?
            WHERE card_id = ? AND id BETWEEN ? AND ?
            "#,
        )
        .bind(&id)
        .bind(&card_id.to_string())
        .bind(first_message_id)
        .bind(last_message_id)
        .execute(pool)
        .await?;

        Ok(())
    }

    /// Load existing summary for a card
    pub async fn load_latest_summary(
        &self,
        pool: &SqlitePool,
        card_id: &Uuid,
    ) -> Result<Option<String>, sqlx::Error> {
        #[derive(sqlx::FromRow)]
        struct SummaryRow {
            summary: String,
        }

        let row = sqlx::query_as::<_, SummaryRow>(
            "SELECT summary FROM rlm_summaries WHERE card_id = ? ORDER BY created_at DESC LIMIT 1",
        )
        .bind(&card_id.to_string())
        .fetch_optional(pool)
        .await?;

        Ok(row.map(|r| r.summary))
    }
}

/// Estimate tokens for a list of messages
fn estimate_tokens_for_messages(messages: &[Message]) -> u32 {
    messages
        .iter()
        .map(|m| estimate_tokens(&m.content))
        .sum()
}

/// Estimate token count (rough approximation: ~4 chars per token)
fn estimate_tokens(text: &str) -> u32 {
    (text.len() as f64 / 4.0).ceil() as u32
}

/// Format messages for summarization
fn format_messages_for_summary(messages: &[Message]) -> String {
    messages
        .iter()
        .map(|m| {
            let role = match m.role {
                crate::integrations::claude::Role::User => "User",
                crate::integrations::claude::Role::Assistant => "Assistant",
            };
            format!("**{}:**\n{}\n", role, m.content)
        })
        .collect::<Vec<_>>()
        .join("\n---\n\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_token_estimation() {
        let text = "Hello, world!"; // 13 chars
        let tokens = estimate_tokens(text);
        assert_eq!(tokens, 4); // ceil(13/4) = 4
    }

    #[test]
    fn test_needs_summarization() {
        let client = ClaudeClient::with_api_key("test");
        let config = RlmConfig {
            max_history_tokens: 100,
            ..Default::default()
        };
        let summarizer = RlmSummarizer::with_config(client, config);

        // Create messages that exceed the threshold
        let long_text = "x".repeat(500); // ~125 tokens
        let messages = vec![Message::user(&long_text)];

        assert!(summarizer.needs_summarization(&messages));
    }

    #[test]
    fn test_format_messages() {
        let messages = vec![
            Message::user("Hello"),
            Message::assistant("Hi there!"),
        ];

        let formatted = format_messages_for_summary(&messages);
        assert!(formatted.contains("**User:**"));
        assert!(formatted.contains("**Assistant:**"));
        assert!(formatted.contains("Hello"));
        assert!(formatted.contains("Hi there!"));
    }

    #[test]
    fn test_summarization_result() {
        let result = SummarizationResult {
            summary: "Test summary".to_string(),
            messages_summarized: 10,
            tokens_before: 1000,
            tokens_after: 200,
            compression_ratio: 5.0,
        };

        assert_eq!(result.compression_ratio, 5.0);
    }
}
