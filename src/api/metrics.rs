//! Metrics API endpoints

use axum::{
    extract::{Path, Query, State},
    routing::get,
    Json, Router,
};
use chrono::{Duration, Utc};
use serde::Deserialize;
use uuid::Uuid;

use crate::metrics::{
    get_card_metrics, get_metrics_since, get_subscription_metrics, get_summary,
    MetricsSummary, SessionMetrics, SubscriptionMetrics,
};

use super::{ApiResponse, AppError, AppState};

/// Query parameters for metrics filtering
#[derive(Debug, Deserialize)]
pub struct MetricsQuery {
    /// Time period: "day", "week", "month", "all"
    pub period: Option<String>,
}

/// Build metrics routes
pub fn metrics_routes() -> Router<AppState> {
    Router::new()
        .route("/summary", get(get_metrics_summary))
        .route("/by-card/:card_id", get(get_card_metrics_handler))
        .route("/by-subscription", get(get_subscription_metrics_handler))
}

/// GET /api/metrics/summary
/// Returns overall metrics summary
async fn get_metrics_summary(
    State(state): State<AppState>,
    Query(params): Query<MetricsQuery>,
) -> Result<Json<ApiResponse<MetricsSummary>>, AppError> {
    let summary = match params.period.as_deref() {
        Some("day") => {
            let since = Utc::now() - Duration::days(1);
            get_metrics_since(&state.pool, since).await?
        }
        Some("week") => {
            let since = Utc::now() - Duration::weeks(1);
            get_metrics_since(&state.pool, since).await?
        }
        Some("month") => {
            let since = Utc::now() - Duration::days(30);
            get_metrics_since(&state.pool, since).await?
        }
        _ => get_summary(&state.pool).await?,
    };

    Ok(Json(ApiResponse::new(summary)))
}

/// GET /api/metrics/by-card/:card_id
/// Returns metrics for a specific card
async fn get_card_metrics_handler(
    State(state): State<AppState>,
    Path(card_id): Path<String>,
) -> Result<Json<ApiResponse<Vec<SessionMetrics>>>, AppError> {
    let card_uuid = Uuid::parse_str(&card_id)
        .map_err(|_| AppError::BadRequest("Invalid card ID".to_string()))?;

    let metrics = get_card_metrics(&state.pool, &card_uuid).await?;

    Ok(Json(ApiResponse::new(metrics)))
}

/// GET /api/metrics/by-subscription
/// Returns metrics grouped by subscription
async fn get_subscription_metrics_handler(
    State(state): State<AppState>,
) -> Result<Json<ApiResponse<Vec<SubscriptionMetrics>>>, AppError> {
    let metrics = get_subscription_metrics(&state.pool).await?;

    Ok(Json(ApiResponse::new(metrics)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_metrics_query_default() {
        let query: MetricsQuery = serde_json::from_str("{}").unwrap();
        assert!(query.period.is_none());
    }

    #[test]
    fn test_metrics_query_with_period() {
        let query: MetricsQuery = serde_json::from_str(r#"{"period": "week"}"#).unwrap();
        assert_eq!(query.period, Some("week".to_string()));
    }
}
