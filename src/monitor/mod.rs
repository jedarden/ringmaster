//! Background monitoring tasks for integrations

use std::sync::Arc;
use std::time::Duration;

use sqlx::SqlitePool;

use crate::domain::CardState;
use crate::events::{Event, EventBus};

/// Configuration for the integration monitor
#[derive(Debug, Clone)]
pub struct MonitorConfig {
    /// Interval for polling GitHub Actions builds
    pub github_poll_interval: Duration,
    /// Interval for polling ArgoCD applications
    pub argocd_poll_interval: Duration,
    /// Interval for checking card states
    pub state_check_interval: Duration,
}

impl Default for MonitorConfig {
    fn default() -> Self {
        Self {
            github_poll_interval: Duration::from_secs(10),
            argocd_poll_interval: Duration::from_secs(5),
            state_check_interval: Duration::from_secs(15),
        }
    }
}

/// Background monitor for integration status
pub struct IntegrationMonitor {
    pool: SqlitePool,
    event_bus: EventBus,
    config: MonitorConfig,
    github_token: Option<String>,
    github_owner: Option<String>,
    github_repo: Option<String>,
    argocd_url: Option<String>,
    argocd_token: Option<String>,
}

impl IntegrationMonitor {
    /// Create a new integration monitor
    pub fn new(pool: SqlitePool, event_bus: EventBus, config: MonitorConfig) -> Self {
        Self {
            pool,
            event_bus,
            config,
            github_token: None,
            github_owner: None,
            github_repo: None,
            argocd_url: None,
            argocd_token: None,
        }
    }

    /// Configure GitHub Actions
    pub fn with_github(mut self, token: String, owner: String, repo: String) -> Self {
        self.github_token = Some(token);
        self.github_owner = Some(owner);
        self.github_repo = Some(repo);
        self
    }

    /// Configure ArgoCD
    pub fn with_argocd(mut self, base_url: String, token: String) -> Self {
        self.argocd_url = Some(base_url);
        self.argocd_token = Some(token);
        self
    }

    /// Start the monitoring tasks
    pub async fn start(self: Arc<Self>) {
        tracing::info!("Starting integration monitor");

        // Spawn GitHub Actions monitor
        if self.github_token.is_some() {
            let monitor = Arc::clone(&self);
            tokio::spawn(async move {
                monitor.github_monitor_loop().await;
            });
        }

        // Spawn ArgoCD monitor
        if self.argocd_url.is_some() {
            let monitor = Arc::clone(&self);
            tokio::spawn(async move {
                monitor.argocd_monitor_loop().await;
            });
        }

        // Spawn state checker
        let monitor = Arc::clone(&self);
        tokio::spawn(async move {
            monitor.state_check_loop().await;
        });
    }

    /// Monitor GitHub Actions builds
    async fn github_monitor_loop(&self) {
        let mut interval = tokio::time::interval(self.config.github_poll_interval);

        loop {
            interval.tick().await;

            if let Err(e) = self.check_github_builds().await {
                tracing::error!("Error checking GitHub builds: {}", e);
            }
        }
    }

    /// Check GitHub builds for cards in Building state
    async fn check_github_builds(&self) -> Result<(), String> {
        // Get cards in Building state
        let cards = crate::db::list_cards(
            &self.pool,
            None,
            Some(&[CardState::Building.as_str()]),
            100,
            0,
        )
        .await
        .map_err(|e| e.to_string())?;

        let (token, owner, repo) = match (&self.github_token, &self.github_owner, &self.github_repo) {
            (Some(t), Some(o), Some(r)) => (t, o, r),
            _ => return Ok(()),
        };

        let client = crate::integrations::github::GitHubClient::new(Some(token.clone()));

        for card in cards {
            if let Some(branch_name) = &card.branch_name {
                match client
                    .get_workflow_runs(owner, repo, Some(branch_name), None, Some(1))
                    .await
                {
                    Ok(runs) => {
                        if let Some(run) = runs.into_iter().next() {
                            self.event_bus.publish(Event::BuildStatus {
                                card_id: card.id,
                                run_id: run.id,
                                status: run.status.clone(),
                                conclusion: run.conclusion.clone(),
                                timestamp: chrono::Utc::now(),
                            });

                            // Note: State transitions would be handled by the API layer
                            // when the frontend receives build status events
                        }
                    }
                    Err(e) => {
                        tracing::warn!("Failed to get workflow runs for card {}: {}", card.id, e);
                    }
                }
            }
        }

        Ok(())
    }

    /// Monitor ArgoCD applications
    async fn argocd_monitor_loop(&self) {
        let mut interval = tokio::time::interval(self.config.argocd_poll_interval);

        loop {
            interval.tick().await;

            if let Err(e) = self.check_argocd_apps().await {
                tracing::error!("Error checking ArgoCD apps: {}", e);
            }
        }
    }

    /// Check ArgoCD sync status for cards in Deploying/Verifying states
    async fn check_argocd_apps(&self) -> Result<(), String> {
        let states = &[
            CardState::Deploying.as_str(),
            CardState::Verifying.as_str(),
        ];
        let cards = crate::db::list_cards(&self.pool, None, Some(states), 100, 0)
            .await
            .map_err(|e| e.to_string())?;

        let (url, token) = match (&self.argocd_url, &self.argocd_token) {
            (Some(u), Some(t)) => (u, t),
            _ => return Ok(()),
        };

        let client = crate::integrations::argocd::ArgoCDClient::new(url.clone(), Some(token.clone()));

        for card in cards {
            if let Some(app_name) = &card.argocd_app_name {
                match client.get_application(app_name).await {
                    Ok(app) => {
                        self.event_bus.publish(Event::DeployStatus {
                            card_id: card.id,
                            app_name: app_name.clone(),
                            sync_status: app.status.sync.status.clone(),
                            health_status: app.status.health.status.clone(),
                            timestamp: chrono::Utc::now(),
                        });
                    }
                    Err(e) => {
                        tracing::warn!(
                            "Failed to get ArgoCD app {} for card {}: {}",
                            app_name,
                            card.id,
                            e
                        );
                    }
                }
            }
        }

        Ok(())
    }

    /// Periodically check and update card states
    async fn state_check_loop(&self) {
        let mut interval = tokio::time::interval(self.config.state_check_interval);

        loop {
            interval.tick().await;

            if let Err(e) = self.check_card_states().await {
                tracing::error!("Error checking card states: {}", e);
            }
        }
    }

    /// Check cards and emit state-related events
    async fn check_card_states(&self) -> Result<(), String> {
        let non_terminal = &[
            CardState::Draft.as_str(),
            CardState::Planning.as_str(),
            CardState::Coding.as_str(),
            CardState::CodeReview.as_str(),
            CardState::Testing.as_str(),
            CardState::BuildQueue.as_str(),
            CardState::Building.as_str(),
            CardState::BuildSuccess.as_str(),
            CardState::BuildFailed.as_str(),
            CardState::DeployQueue.as_str(),
            CardState::Deploying.as_str(),
            CardState::Verifying.as_str(),
            CardState::ErrorFixing.as_str(),
        ];

        let cards = crate::db::list_cards(&self.pool, None, Some(non_terminal), 1000, 0)
            .await
            .map_err(|e| e.to_string())?;

        tracing::debug!("Monitoring {} active cards", cards.len());

        for card in &cards {
            if let Some(state_changed_at) = card.state_changed_at {
                let stuck_duration = chrono::Utc::now() - state_changed_at;
                let stuck_hours = stuck_duration.num_hours();

                // Warn about cards stuck for too long
                if stuck_hours > 4 {
                    match card.state {
                        CardState::Building | CardState::Deploying | CardState::Verifying => {
                            tracing::warn!(
                                "Card {} has been in {:?} state for {} hours",
                                card.id,
                                card.state,
                                stuck_hours
                            );
                        }
                        _ => {}
                    }
                }
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_monitor_config_default() {
        let config = MonitorConfig::default();

        assert_eq!(config.github_poll_interval, Duration::from_secs(10));
        assert_eq!(config.argocd_poll_interval, Duration::from_secs(5));
        assert_eq!(config.state_check_interval, Duration::from_secs(15));
    }

    #[test]
    fn test_monitor_config_custom() {
        let config = MonitorConfig {
            github_poll_interval: Duration::from_secs(30),
            argocd_poll_interval: Duration::from_secs(15),
            state_check_interval: Duration::from_secs(60),
        };

        assert_eq!(config.github_poll_interval, Duration::from_secs(30));
        assert_eq!(config.argocd_poll_interval, Duration::from_secs(15));
        assert_eq!(config.state_check_interval, Duration::from_secs(60));
    }

    #[tokio::test]
    async fn test_integration_monitor_builder() {
        // Create in-memory database for testing
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        // Run migrations
        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        let event_bus = EventBus::new();
        let config = MonitorConfig::default();

        // Test builder pattern
        let monitor = IntegrationMonitor::new(pool, event_bus, config)
            .with_github(
                "test-token".to_string(),
                "test-owner".to_string(),
                "test-repo".to_string(),
            )
            .with_argocd(
                "https://argocd.example.com".to_string(),
                "argocd-token".to_string(),
            );

        assert!(monitor.github_token.is_some());
        assert!(monitor.github_owner.is_some());
        assert!(monitor.github_repo.is_some());
        assert!(monitor.argocd_url.is_some());
        assert!(monitor.argocd_token.is_some());

        assert_eq!(monitor.github_token.unwrap(), "test-token");
        assert_eq!(monitor.github_owner.unwrap(), "test-owner");
        assert_eq!(monitor.github_repo.unwrap(), "test-repo");
        assert_eq!(monitor.argocd_url.unwrap(), "https://argocd.example.com");
        assert_eq!(monitor.argocd_token.unwrap(), "argocd-token");
    }

    #[tokio::test]
    async fn test_integration_monitor_without_integrations() {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        let event_bus = EventBus::new();
        let config = MonitorConfig::default();

        let monitor = IntegrationMonitor::new(pool, event_bus, config);

        // Without integration configuration, should have None values
        assert!(monitor.github_token.is_none());
        assert!(monitor.github_owner.is_none());
        assert!(monitor.github_repo.is_none());
        assert!(monitor.argocd_url.is_none());
        assert!(monitor.argocd_token.is_none());
    }

    #[tokio::test]
    async fn test_check_card_states_with_empty_cards() {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        let event_bus = EventBus::new();
        let config = MonitorConfig::default();

        let monitor = IntegrationMonitor::new(pool, event_bus, config);

        // Should succeed with empty cards
        let result = monitor.check_card_states().await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_check_github_builds_without_config() {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        let event_bus = EventBus::new();
        let config = MonitorConfig::default();

        let monitor = IntegrationMonitor::new(pool, event_bus, config);

        // Should succeed (returns early without GitHub config)
        let result = monitor.check_github_builds().await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_check_argocd_apps_without_config() {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .connect("sqlite::memory:")
            .await
            .expect("Failed to create test database");

        sqlx::migrate!("./migrations")
            .run(&pool)
            .await
            .expect("Failed to run migrations");

        let event_bus = EventBus::new();
        let config = MonitorConfig::default();

        let monitor = IntegrationMonitor::new(pool, event_bus, config);

        // Should succeed (returns early without ArgoCD config)
        let result = monitor.check_argocd_apps().await;
        assert!(result.is_ok());
    }
}
