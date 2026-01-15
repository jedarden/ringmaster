//! Action executor - wires state machine actions to actual implementations

use std::path::Path;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::domain::{Action, Card, Project};
use crate::events::{Event, EventBus};
use crate::integrations::git;
use crate::loops::{LoopConfig, LoopExecutor, LoopManager};

/// Error type for action execution
#[derive(Debug, thiserror::Error)]
pub enum ActionError {
    #[error("Git operation failed: {0}")]
    GitError(String),
    #[error("Loop operation failed: {0}")]
    LoopError(String),
    #[error("Integration error: {0}")]
    IntegrationError(String),
    #[error("Database error: {0}")]
    DatabaseError(#[from] sqlx::Error),
}

/// Executor for state machine actions
pub struct ActionExecutor {
    pool: sqlx::SqlitePool,
    event_bus: EventBus,
    loop_manager: Arc<RwLock<LoopManager>>,
}

impl ActionExecutor {
    /// Create a new action executor
    pub fn new(
        pool: sqlx::SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
    ) -> Self {
        Self {
            pool,
            event_bus,
            loop_manager,
        }
    }

    /// Execute a single action for a card
    pub async fn execute(
        &self,
        card: &Card,
        project: &Project,
        action: &Action,
    ) -> Result<(), ActionError> {
        tracing::info!("Executing action {:?} for card {}", action, card.id);

        match action {
            Action::CreateGitWorktree => self.create_git_worktree(card, project).await,
            Action::StartRalphLoop => self.start_ralph_loop(card, project).await,
            Action::PauseRalphLoop => self.pause_ralph_loop(card).await,
            Action::StopRalphLoop => self.stop_ralph_loop(card).await,
            Action::CreatePullRequest => self.create_pull_request(card, project).await,
            Action::TriggerBuild => self.trigger_build(card).await,
            Action::MonitorBuild => self.monitor_build(card).await,
            Action::TriggerDeploy => self.trigger_deploy(card).await,
            Action::MonitorArgoCD => self.monitor_argocd(card).await,
            Action::RunHealthChecks => self.run_health_checks(card).await,
            Action::CollectErrorContext => self.collect_error_context(card).await,
            Action::RestartLoopWithError => self.restart_loop_with_error(card, project).await,
            Action::NotifyUser => self.notify_user(card).await,
            Action::RecordMetrics => self.record_metrics(card).await,
        }
    }

    /// Execute multiple actions for a card
    pub async fn execute_all(
        &self,
        card: &Card,
        project: &Project,
        actions: &[Action],
    ) -> Result<(), ActionError> {
        for action in actions {
            self.execute(card, project, action).await?;
        }
        Ok(())
    }

    /// Create a git worktree for the card
    async fn create_git_worktree(&self, card: &Card, project: &Project) -> Result<(), ActionError> {
        let branch_name = format!("card/{}", &card.id.to_string()[..8]);
        let worktree_path = format!(
            "/tmp/ringmaster/worktrees/{}/{}",
            project.id, card.id
        );

        // Use git service to create worktree
        if let Some(repo_path) = &project.repository_path {
            // Run blocking git2 operations in a blocking task
            let repo_path = repo_path.clone();
            let worktree_path_clone = worktree_path.clone();
            let branch_name_clone = branch_name.clone();

            tokio::task::spawn_blocking(move || {
                git::create_worktree(
                    Path::new(&repo_path),
                    Path::new(&worktree_path_clone),
                    &branch_name_clone,
                )
            })
            .await
            .map_err(|e| ActionError::GitError(format!("Task join error: {}", e)))?
            .map_err(ActionError::GitError)?;

            // Update card with worktree info
            crate::db::update_card_worktree(
                &self.pool,
                &card.id.to_string(),
                &worktree_path,
                &branch_name,
            )
            .await?;

            self.event_bus.publish(Event::WorktreeCreated {
                card_id: card.id,
                worktree_path: worktree_path.clone(),
                branch_name: branch_name.clone(),
                timestamp: chrono::Utc::now(),
            });
        }

        Ok(())
    }

    /// Start the Ralph coding loop for a card
    async fn start_ralph_loop(&self, card: &Card, project: &Project) -> Result<(), ActionError> {
        let config = LoopConfig::default();

        {
            let mut loop_manager = self.loop_manager.write().await;
            loop_manager
                .start_loop(card.id, config.clone())
                .map_err(ActionError::LoopError)?;
        }

        self.event_bus.publish(Event::LoopStarted {
            card_id: card.id,
            timestamp: chrono::Utc::now(),
        });

        // Spawn the actual executor in a background task
        let pool = self.pool.clone();
        let event_bus = self.event_bus.clone();
        let loop_manager = self.loop_manager.clone();
        let card_id = card.id;
        let project = project.clone();

        tokio::spawn(async move {
            let executor = match LoopExecutor::new(pool.clone(), event_bus.clone(), loop_manager.clone()) {
                Ok(e) => e,
                Err(e) => {
                    tracing::error!("Failed to create loop executor: {}", e);
                    return;
                }
            };

            if let Err(e) = executor.run_loop(card_id, &project, config).await {
                tracing::error!("Loop execution failed for card {}: {}", card_id, e);
            }
        });

        Ok(())
    }

    /// Pause the Ralph loop
    async fn pause_ralph_loop(&self, card: &Card) -> Result<(), ActionError> {
        let mut loop_manager = self.loop_manager.write().await;
        loop_manager
            .pause_loop(&card.id)
            .map_err(ActionError::LoopError)?;

        let loop_state = loop_manager.get_loop_state(&card.id);
        let iteration = loop_state.map(|s| s.iteration).unwrap_or(0);

        self.event_bus.publish(Event::LoopPaused {
            card_id: card.id,
            iteration,
            timestamp: chrono::Utc::now(),
        });

        Ok(())
    }

    /// Stop the Ralph loop
    async fn stop_ralph_loop(&self, card: &Card) -> Result<(), ActionError> {
        let mut loop_manager = self.loop_manager.write().await;
        let final_state = loop_manager
            .stop_loop(&card.id)
            .map_err(ActionError::LoopError)?;

        self.event_bus.publish(Event::LoopStopped {
            card_id: card.id,
            iteration: final_state.iteration,
            reason: final_state.stop_reason.clone(),
            timestamp: chrono::Utc::now(),
        });

        Ok(())
    }

    /// Create a pull request for the card's branch
    async fn create_pull_request(&self, card: &Card, project: &Project) -> Result<(), ActionError> {
        // This would integrate with GitHub to create a PR
        tracing::info!("Creating pull request for card {} in project {}", card.id, project.name);

        if let (Some(worktree_path), Some(branch_name)) = (&card.worktree_path, &card.branch_name) {
            // Push the branch first
            let worktree_path_clone = worktree_path.clone();
            let branch_name_clone = branch_name.clone();

            tokio::task::spawn_blocking(move || {
                git::push_to_remote(
                    Path::new(&worktree_path_clone),
                    "origin",
                    &branch_name_clone,
                )
            })
            .await
            .map_err(|e| ActionError::GitError(format!("Task join error: {}", e)))?
            .map_err(ActionError::GitError)?;

            // For now, we'll just record a compare URL since GitHub API isn't integrated
            let pr_url = format!(
                "{}/compare/main...{}",
                project.repository_url,
                branch_name
            );

            crate::db::update_card_pr(&self.pool, &card.id.to_string(), &pr_url).await?;

            self.event_bus.publish(Event::PullRequestCreated {
                card_id: card.id,
                pr_url: pr_url.clone(),
                timestamp: chrono::Utc::now(),
            });
        }

        Ok(())
    }

    /// Trigger a build via GitHub Actions
    async fn trigger_build(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Triggering build for card {}", card.id);
        // TODO: Integrate with GitHub Actions service
        Ok(())
    }

    /// Start monitoring a build
    async fn monitor_build(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Starting build monitor for card {}", card.id);
        // TODO: Start background task to poll build status
        Ok(())
    }

    /// Trigger a deployment via ArgoCD
    async fn trigger_deploy(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Triggering deployment for card {}", card.id);
        // TODO: Integrate with ArgoCD service
        Ok(())
    }

    /// Start monitoring ArgoCD sync status
    async fn monitor_argocd(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Starting ArgoCD monitor for card {}", card.id);
        // TODO: Start background task to poll ArgoCD status
        Ok(())
    }

    /// Run health checks against deployed services
    async fn run_health_checks(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Running health checks for card {}", card.id);
        // TODO: Integrate with Kubernetes service for health checks
        Ok(())
    }

    /// Collect error context for debugging
    async fn collect_error_context(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Collecting error context for card {}", card.id);

        // Collect various error sources
        // - Build logs from GitHub Actions
        // - Pod logs from Kubernetes
        // - ArgoCD sync errors

        self.event_bus.publish(Event::ErrorContextCollected {
            card_id: card.id,
            timestamp: chrono::Utc::now(),
        });

        Ok(())
    }

    /// Restart the loop with error context for fixing
    async fn restart_loop_with_error(
        &self,
        card: &Card,
        project: &Project,
    ) -> Result<(), ActionError> {
        tracing::info!("Restarting loop with error context for card {}", card.id);

        // Increment error count
        crate::db::increment_card_error_count(&self.pool, &card.id.to_string()).await?;

        // Start the loop again - it will pick up error context from the card's errors
        self.start_ralph_loop(card, project).await
    }

    /// Notify user about important events
    async fn notify_user(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Notifying user about card {}", card.id);

        self.event_bus.publish(Event::UserNotification {
            card_id: card.id,
            message: format!("Card '{}' requires attention", card.title),
            timestamp: chrono::Utc::now(),
        });

        Ok(())
    }

    /// Record metrics for the card
    async fn record_metrics(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Recording metrics for card {}", card.id);

        // Metrics are already tracked in the card and loop state
        // This action is for any additional metric recording needed

        self.event_bus.publish(Event::MetricsRecorded {
            card_id: card.id,
            timestamp: chrono::Utc::now(),
        });

        Ok(())
    }
}
