//! Metrics collection and reporting for coding sessions
//!
//! This module tracks token usage, costs, and performance metrics
//! across all coding sessions.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::SqlitePool;
use uuid::Uuid;

/// Metrics for a single coding session
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionMetrics {
    /// Unique identifier for these metrics
    pub id: Uuid,
    /// The card this session was for
    pub card_id: Uuid,
    /// Platform used (e.g., "claude-code", "aider")
    pub platform: String,
    /// Subscription name used
    pub subscription: Option<String>,
    /// Input tokens used
    pub input_tokens: i64,
    /// Output tokens generated
    pub output_tokens: i64,
    /// Estimated cost in USD
    pub estimated_cost_usd: f64,
    /// Session duration in seconds
    pub duration_seconds: i64,
    /// Number of iterations/turns
    pub iterations: i32,
    /// Whether the session completed successfully
    pub success: bool,
    /// When the session started
    pub started_at: DateTime<Utc>,
    /// When the session ended
    pub ended_at: DateTime<Utc>,
}

impl SessionMetrics {
    /// Create new session metrics
    pub fn new(card_id: Uuid, platform: &str) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            card_id,
            platform: platform.to_string(),
            subscription: None,
            input_tokens: 0,
            output_tokens: 0,
            estimated_cost_usd: 0.0,
            duration_seconds: 0,
            iterations: 0,
            success: false,
            started_at: now,
            ended_at: now,
        }
    }

    /// Set subscription name
    pub fn with_subscription(mut self, name: &str) -> Self {
        self.subscription = Some(name.to_string());
        self
    }

    /// Update token counts
    pub fn with_tokens(mut self, input: i64, output: i64) -> Self {
        self.input_tokens = input;
        self.output_tokens = output;
        self
    }

    /// Set estimated cost
    pub fn with_cost(mut self, cost: f64) -> Self {
        self.estimated_cost_usd = cost;
        self
    }

    /// Set duration
    pub fn with_duration(mut self, seconds: i64) -> Self {
        self.duration_seconds = seconds;
        self
    }

    /// Set iterations
    pub fn with_iterations(mut self, iterations: i32) -> Self {
        self.iterations = iterations;
        self
    }

    /// Mark as successful
    pub fn mark_success(mut self) -> Self {
        self.success = true;
        self
    }

    /// Set end time
    pub fn ended(mut self, at: DateTime<Utc>) -> Self {
        self.ended_at = at;
        self
    }

    /// Total tokens used
    pub fn total_tokens(&self) -> i64 {
        self.input_tokens + self.output_tokens
    }
}

/// Summary of metrics across multiple sessions
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MetricsSummary {
    /// Total sessions
    pub total_sessions: i64,
    /// Successful sessions
    pub successful_sessions: i64,
    /// Total input tokens
    pub total_input_tokens: i64,
    /// Total output tokens
    pub total_output_tokens: i64,
    /// Total cost in USD
    pub total_cost_usd: f64,
    /// Total duration in seconds
    pub total_duration_seconds: i64,
    /// Total iterations
    pub total_iterations: i64,
    /// Success rate (0-1)
    pub success_rate: f64,
    /// Average cost per session
    pub avg_cost_per_session: f64,
    /// Average tokens per session
    pub avg_tokens_per_session: f64,
    /// Average duration per session
    pub avg_duration_per_session: f64,
}

impl Default for MetricsSummary {
    fn default() -> Self {
        Self {
            total_sessions: 0,
            successful_sessions: 0,
            total_input_tokens: 0,
            total_output_tokens: 0,
            total_cost_usd: 0.0,
            total_duration_seconds: 0,
            total_iterations: 0,
            success_rate: 0.0,
            avg_cost_per_session: 0.0,
            avg_tokens_per_session: 0.0,
            avg_duration_per_session: 0.0,
        }
    }
}

/// Metrics breakdown by subscription
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SubscriptionMetrics {
    /// Subscription name
    pub subscription: String,
    /// Platform
    pub platform: String,
    /// Summary for this subscription
    pub summary: MetricsSummary,
}

// Database operations

/// Save session metrics to the database
pub async fn save_metrics(pool: &SqlitePool, metrics: &SessionMetrics) -> Result<(), sqlx::Error> {
    let id = metrics.id.to_string();
    let card_id = metrics.card_id.to_string();
    let started_at = metrics.started_at.to_rfc3339();
    let ended_at = metrics.ended_at.to_rfc3339();

    sqlx::query(
        r#"
        INSERT INTO session_metrics (
            id, card_id, platform, subscription,
            input_tokens, output_tokens, estimated_cost_usd,
            duration_seconds, iterations, success,
            started_at, ended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        "#,
    )
    .bind(&id)
    .bind(&card_id)
    .bind(&metrics.platform)
    .bind(&metrics.subscription)
    .bind(metrics.input_tokens)
    .bind(metrics.output_tokens)
    .bind(metrics.estimated_cost_usd)
    .bind(metrics.duration_seconds)
    .bind(metrics.iterations)
    .bind(metrics.success)
    .bind(&started_at)
    .bind(&ended_at)
    .execute(pool)
    .await?;

    Ok(())
}

/// Get metrics for a specific card
pub async fn get_card_metrics(
    pool: &SqlitePool,
    card_id: &Uuid,
) -> Result<Vec<SessionMetrics>, sqlx::Error> {
    let card_id_str = card_id.to_string();

    let rows = sqlx::query_as::<_, MetricsRow>(
        r#"
        SELECT id, card_id, platform, subscription,
               input_tokens, output_tokens, estimated_cost_usd,
               duration_seconds, iterations, success,
               started_at, ended_at
        FROM session_metrics
        WHERE card_id = ?
        ORDER BY started_at DESC
        "#,
    )
    .bind(&card_id_str)
    .fetch_all(pool)
    .await?;

    Ok(rows.into_iter().map(|r| r.into()).collect())
}

/// Get overall metrics summary
pub async fn get_summary(pool: &SqlitePool) -> Result<MetricsSummary, sqlx::Error> {
    let row = sqlx::query_as::<_, SummaryRow>(
        r#"
        SELECT
            COUNT(*) as total_sessions,
            COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) as successful_sessions,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd,
            COALESCE(SUM(duration_seconds), 0) as total_duration_seconds,
            COALESCE(SUM(iterations), 0) as total_iterations
        FROM session_metrics
        "#,
    )
    .fetch_one(pool)
    .await?;

    let total = row.total_sessions as f64;
    let success_rate = if total > 0.0 {
        row.successful_sessions as f64 / total
    } else {
        0.0
    };

    Ok(MetricsSummary {
        total_sessions: row.total_sessions,
        successful_sessions: row.successful_sessions,
        total_input_tokens: row.total_input_tokens,
        total_output_tokens: row.total_output_tokens,
        total_cost_usd: row.total_cost_usd,
        total_duration_seconds: row.total_duration_seconds,
        total_iterations: row.total_iterations,
        success_rate,
        avg_cost_per_session: if total > 0.0 {
            row.total_cost_usd / total
        } else {
            0.0
        },
        avg_tokens_per_session: if total > 0.0 {
            (row.total_input_tokens + row.total_output_tokens) as f64 / total
        } else {
            0.0
        },
        avg_duration_per_session: if total > 0.0 {
            row.total_duration_seconds as f64 / total
        } else {
            0.0
        },
    })
}

/// Get metrics summary by subscription
pub async fn get_subscription_metrics(
    pool: &SqlitePool,
) -> Result<Vec<SubscriptionMetrics>, sqlx::Error> {
    let rows = sqlx::query_as::<_, SubscriptionSummaryRow>(
        r#"
        SELECT
            COALESCE(subscription, 'default') as subscription,
            platform,
            COUNT(*) as total_sessions,
            COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) as successful_sessions,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd,
            COALESCE(SUM(duration_seconds), 0) as total_duration_seconds,
            COALESCE(SUM(iterations), 0) as total_iterations
        FROM session_metrics
        GROUP BY COALESCE(subscription, 'default'), platform
        ORDER BY total_cost_usd DESC
        "#,
    )
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|r| {
            let total = r.total_sessions as f64;
            let success_rate = if total > 0.0 {
                r.successful_sessions as f64 / total
            } else {
                0.0
            };

            SubscriptionMetrics {
                subscription: r.subscription,
                platform: r.platform,
                summary: MetricsSummary {
                    total_sessions: r.total_sessions,
                    successful_sessions: r.successful_sessions,
                    total_input_tokens: r.total_input_tokens,
                    total_output_tokens: r.total_output_tokens,
                    total_cost_usd: r.total_cost_usd,
                    total_duration_seconds: r.total_duration_seconds,
                    total_iterations: r.total_iterations,
                    success_rate,
                    avg_cost_per_session: if total > 0.0 {
                        r.total_cost_usd / total
                    } else {
                        0.0
                    },
                    avg_tokens_per_session: if total > 0.0 {
                        (r.total_input_tokens + r.total_output_tokens) as f64 / total
                    } else {
                        0.0
                    },
                    avg_duration_per_session: if total > 0.0 {
                        r.total_duration_seconds as f64 / total
                    } else {
                        0.0
                    },
                },
            }
        })
        .collect())
}

/// Get metrics for a time period
pub async fn get_metrics_since(
    pool: &SqlitePool,
    since: DateTime<Utc>,
) -> Result<MetricsSummary, sqlx::Error> {
    let since_str = since.to_rfc3339();

    let row = sqlx::query_as::<_, SummaryRow>(
        r#"
        SELECT
            COUNT(*) as total_sessions,
            COALESCE(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END), 0) as successful_sessions,
            COALESCE(SUM(input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(output_tokens), 0) as total_output_tokens,
            COALESCE(SUM(estimated_cost_usd), 0.0) as total_cost_usd,
            COALESCE(SUM(duration_seconds), 0) as total_duration_seconds,
            COALESCE(SUM(iterations), 0) as total_iterations
        FROM session_metrics
        WHERE started_at >= ?
        "#,
    )
    .bind(&since_str)
    .fetch_one(pool)
    .await?;

    let total = row.total_sessions as f64;
    let success_rate = if total > 0.0 {
        row.successful_sessions as f64 / total
    } else {
        0.0
    };

    Ok(MetricsSummary {
        total_sessions: row.total_sessions,
        successful_sessions: row.successful_sessions,
        total_input_tokens: row.total_input_tokens,
        total_output_tokens: row.total_output_tokens,
        total_cost_usd: row.total_cost_usd,
        total_duration_seconds: row.total_duration_seconds,
        total_iterations: row.total_iterations,
        success_rate,
        avg_cost_per_session: if total > 0.0 {
            row.total_cost_usd / total
        } else {
            0.0
        },
        avg_tokens_per_session: if total > 0.0 {
            (row.total_input_tokens + row.total_output_tokens) as f64 / total
        } else {
            0.0
        },
        avg_duration_per_session: if total > 0.0 {
            row.total_duration_seconds as f64 / total
        } else {
            0.0
        },
    })
}

// Internal row types for database queries

#[derive(Debug, sqlx::FromRow)]
struct MetricsRow {
    id: String,
    card_id: String,
    platform: String,
    subscription: Option<String>,
    input_tokens: i64,
    output_tokens: i64,
    estimated_cost_usd: f64,
    duration_seconds: i64,
    iterations: i32,
    success: bool,
    started_at: String,
    ended_at: String,
}

impl From<MetricsRow> for SessionMetrics {
    fn from(row: MetricsRow) -> Self {
        let id = Uuid::parse_str(&row.id).unwrap_or_else(|_| Uuid::new_v4());
        let card_id = Uuid::parse_str(&row.card_id).unwrap_or_else(|_| Uuid::new_v4());
        let started_at = DateTime::parse_from_rfc3339(&row.started_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now());
        let ended_at = DateTime::parse_from_rfc3339(&row.ended_at)
            .map(|dt| dt.with_timezone(&Utc))
            .unwrap_or_else(|_| Utc::now());

        Self {
            id,
            card_id,
            platform: row.platform,
            subscription: row.subscription,
            input_tokens: row.input_tokens,
            output_tokens: row.output_tokens,
            estimated_cost_usd: row.estimated_cost_usd,
            duration_seconds: row.duration_seconds,
            iterations: row.iterations,
            success: row.success,
            started_at,
            ended_at,
        }
    }
}

#[derive(Debug, sqlx::FromRow)]
struct SummaryRow {
    total_sessions: i64,
    successful_sessions: i64,
    total_input_tokens: i64,
    total_output_tokens: i64,
    total_cost_usd: f64,
    total_duration_seconds: i64,
    total_iterations: i64,
}

#[derive(Debug, sqlx::FromRow)]
struct SubscriptionSummaryRow {
    subscription: String,
    platform: String,
    total_sessions: i64,
    successful_sessions: i64,
    total_input_tokens: i64,
    total_output_tokens: i64,
    total_cost_usd: f64,
    total_duration_seconds: i64,
    total_iterations: i64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_metrics_creation() {
        let card_id = Uuid::new_v4();
        let metrics = SessionMetrics::new(card_id, "claude-code")
            .with_subscription("default")
            .with_tokens(1000, 500)
            .with_cost(0.05)
            .with_duration(120)
            .with_iterations(5)
            .mark_success();

        assert_eq!(metrics.card_id, card_id);
        assert_eq!(metrics.platform, "claude-code");
        assert_eq!(metrics.subscription, Some("default".to_string()));
        assert_eq!(metrics.input_tokens, 1000);
        assert_eq!(metrics.output_tokens, 500);
        assert_eq!(metrics.total_tokens(), 1500);
        assert!((metrics.estimated_cost_usd - 0.05).abs() < 0.001);
        assert_eq!(metrics.duration_seconds, 120);
        assert_eq!(metrics.iterations, 5);
        assert!(metrics.success);
    }

    #[test]
    fn test_metrics_summary_default() {
        let summary = MetricsSummary::default();

        assert_eq!(summary.total_sessions, 0);
        assert_eq!(summary.successful_sessions, 0);
        assert_eq!(summary.total_input_tokens, 0);
        assert_eq!(summary.total_output_tokens, 0);
        assert!((summary.total_cost_usd - 0.0).abs() < 0.001);
        assert!((summary.success_rate - 0.0).abs() < 0.001);
    }

    #[test]
    fn test_session_metrics_serialization() {
        let card_id = Uuid::new_v4();
        let metrics = SessionMetrics::new(card_id, "aider")
            .with_tokens(500, 250)
            .with_cost(0.02);

        let json = serde_json::to_string(&metrics).unwrap();

        assert!(json.contains("\"platform\":\"aider\""));
        assert!(json.contains("\"inputTokens\":500"));
        assert!(json.contains("\"outputTokens\":250"));
    }
}
