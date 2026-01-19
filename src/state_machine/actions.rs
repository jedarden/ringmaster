//! Action executor - wires state machine actions to actual implementations

use std::path::Path;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::RwLock;

use crate::domain::{Action, Card, CardError, ErrorCategory, ErrorContext, Project};
use crate::events::{Event, EventBus};
use crate::integrations::argocd::ArgoCDClient;
use crate::integrations::git;
use crate::integrations::github::GitHubClient;
use crate::integrations::kubernetes::KubernetesService;
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
    github_client: Arc<GitHubClient>,
    argocd_client: Option<Arc<ArgoCDClient>>,
}

impl ActionExecutor {
    /// Create a new action executor
    pub fn new(
        pool: sqlx::SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
    ) -> Self {
        let github_client = Arc::new(GitHubClient::new(None));

        // ArgoCD client is optional - only created if ARGOCD_SERVER is set
        let argocd_client = std::env::var("ARGOCD_SERVER")
            .ok()
            .map(|server| Arc::new(ArgoCDClient::new(server, None)));

        Self {
            pool,
            event_bus,
            loop_manager,
            github_client,
            argocd_client,
        }
    }

    /// Create a new action executor with custom clients (for testing)
    pub fn with_clients(
        pool: sqlx::SqlitePool,
        event_bus: EventBus,
        loop_manager: Arc<RwLock<LoopManager>>,
        github_client: GitHubClient,
        argocd_client: Option<ArgoCDClient>,
    ) -> Self {
        Self {
            pool,
            event_bus,
            loop_manager,
            github_client: Arc::new(github_client),
            argocd_client: argocd_client.map(Arc::new),
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
            Action::TriggerBuild => self.trigger_build(card, project).await,
            Action::MonitorBuild => self.monitor_build(card, project).await,
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
    async fn trigger_build(&self, card: &Card, project: &Project) -> Result<(), ActionError> {
        tracing::info!("Triggering build for card {}", card.id);

        // Parse owner/repo from repository URL
        let (owner, repo) = self
            .parse_github_repo(&project.repository_url)
            .map_err(ActionError::IntegrationError)?;

        // Get the branch name for this card
        let branch = card
            .branch_name
            .as_ref()
            .ok_or_else(|| ActionError::IntegrationError("No branch name set for card".to_string()))?;

        // Try to dispatch a workflow (typically CI workflow)
        // Common workflow names: ci.yml, build.yml, test.yml
        let workflow_names = ["ci.yml", "ci.yaml", "build.yml", "build.yaml", "test.yml", "test.yaml"];

        for workflow in &workflow_names {
            match self
                .github_client
                .dispatch_workflow(&owner, &repo, workflow, branch, None)
                .await
            {
                Ok(()) => {
                    tracing::info!(
                        "Dispatched workflow {} for card {} on branch {}",
                        workflow,
                        card.id,
                        branch
                    );

                    self.event_bus.publish(Event::BuildStatus {
                        card_id: card.id,
                        run_id: 0, // Will be updated when we poll for the run
                        status: "queued".to_string(),
                        conclusion: None,
                        timestamp: chrono::Utc::now(),
                    });

                    return Ok(());
                }
                Err(crate::integrations::IntegrationError::NotFound(_)) => {
                    // Try next workflow name
                    continue;
                }
                Err(crate::integrations::IntegrationError::AuthRequired) => {
                    return Err(ActionError::IntegrationError(
                        "GitHub authentication required - set GITHUB_TOKEN".to_string(),
                    ));
                }
                Err(e) => {
                    return Err(ActionError::IntegrationError(format!(
                        "Failed to dispatch workflow: {}",
                        e
                    )));
                }
            }
        }

        // If no workflow dispatch worked, check if there are existing runs
        // triggered by push (which happens when we push the branch)
        match self
            .github_client
            .get_workflow_runs(&owner, &repo, Some(branch), None, Some(1))
            .await
        {
            Ok(runs) if !runs.is_empty() => {
                let run = &runs[0];
                tracing::info!(
                    "Found existing workflow run {} for branch {}",
                    run.id,
                    branch
                );

                self.event_bus.publish(Event::BuildStatus {
                    card_id: card.id,
                    run_id: run.id,
                    status: run.status.clone(),
                    conclusion: run.conclusion.clone(),
                    timestamp: chrono::Utc::now(),
                });

                Ok(())
            }
            Ok(_) => {
                tracing::warn!(
                    "No workflow runs found for card {} on branch {}",
                    card.id,
                    branch
                );
                Ok(())
            }
            Err(e) => Err(ActionError::IntegrationError(format!(
                "Failed to check workflow runs: {}",
                e
            ))),
        }
    }

    /// Parse GitHub owner/repo from repository URL
    fn parse_github_repo(&self, url: &str) -> Result<(String, String), String> {
        // Handle various GitHub URL formats:
        // https://github.com/owner/repo
        // https://github.com/owner/repo.git
        // git@github.com:owner/repo.git

        let url = url.trim_end_matches(".git");

        if let Some(rest) = url.strip_prefix("https://github.com/") {
            let parts: Vec<&str> = rest.split('/').collect();
            if parts.len() >= 2 {
                return Ok((parts[0].to_string(), parts[1].to_string()));
            }
        }

        if let Some(rest) = url.strip_prefix("git@github.com:") {
            let parts: Vec<&str> = rest.split('/').collect();
            if parts.len() >= 2 {
                return Ok((parts[0].to_string(), parts[1].to_string()));
            }
        }

        Err(format!("Could not parse GitHub repository from URL: {}", url))
    }

    /// Start monitoring a build
    async fn monitor_build(&self, card: &Card, project: &Project) -> Result<(), ActionError> {
        tracing::info!("Starting build monitor for card {}", card.id);

        let (owner, repo) = self
            .parse_github_repo(&project.repository_url)
            .map_err(ActionError::IntegrationError)?;

        let branch = card
            .branch_name
            .clone()
            .ok_or_else(|| ActionError::IntegrationError("No branch name set for card".to_string()))?;

        let card_id = card.id;
        let github_client = self.github_client.clone();
        let event_bus = self.event_bus.clone();
        let pool = self.pool.clone();

        // Spawn background task to poll build status
        tokio::spawn(async move {
            let poll_interval = Duration::from_secs(30);
            let max_polls = 120; // 1 hour max
            let mut polls = 0;
            let mut last_run_id: Option<i64> = None;

            loop {
                polls += 1;
                if polls > max_polls {
                    tracing::warn!("Build monitor timeout for card {}", card_id);
                    break;
                }

                // Get latest workflow runs for the branch
                match github_client
                    .get_workflow_runs(&owner, &repo, Some(&branch), None, Some(5))
                    .await
                {
                    Ok(runs) => {
                        // Find the most recent run that's either in progress or just completed
                        let relevant_run = runs.into_iter().find(|r| {
                            r.status == "in_progress"
                                || r.status == "queued"
                                || (r.status == "completed"
                                    && last_run_id.is_none_or(|id| r.id >= id))
                        });

                        if let Some(run) = relevant_run {
                            last_run_id = Some(run.id);

                            event_bus.publish(Event::BuildStatus {
                                card_id,
                                run_id: run.id,
                                status: run.status.clone(),
                                conclusion: run.conclusion.clone(),
                                timestamp: chrono::Utc::now(),
                            });

                            if run.status == "completed" {
                                tracing::info!(
                                    "Build completed for card {}: {:?}",
                                    card_id,
                                    run.conclusion
                                );

                                // If build failed, record an error
                                if run.conclusion.as_deref() == Some("failure") {
                                    let error = CardError::new(
                                        card_id,
                                        "build_failure".to_string(),
                                        format!("Build failed: {}", run.html_url),
                                    )
                                    .with_category(ErrorCategory::Build)
                                    .with_context(ErrorContext {
                                        build_run_id: Some(run.id),
                                        source_state: Some("building".to_string()),
                                        ..Default::default()
                                    });

                                    if let Err(e) = crate::db::record_error(&pool, &error).await {
                                        tracing::error!("Failed to record build error: {}", e);
                                    }
                                }

                                break;
                            }
                        }
                    }
                    Err(e) => {
                        tracing::error!("Error polling build status for card {}: {}", card_id, e);
                    }
                }

                tokio::time::sleep(poll_interval).await;
            }
        });

        Ok(())
    }

    /// Trigger a deployment via ArgoCD
    async fn trigger_deploy(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Triggering deployment for card {}", card.id);

        let argocd_client = self
            .argocd_client
            .as_ref()
            .ok_or_else(|| {
                ActionError::IntegrationError(
                    "ArgoCD not configured - set ARGOCD_SERVER environment variable".to_string(),
                )
            })?;

        let app_name = card.argocd_app_name.as_ref().ok_or_else(|| {
            ActionError::IntegrationError("No ArgoCD app name set for card".to_string())
        })?;

        // Sync the application with optional revision from the card's branch
        let revision = card.branch_name.as_deref();

        match argocd_client
            .sync_application(app_name, revision, false)
            .await
        {
            Ok(app) => {
                tracing::info!(
                    "ArgoCD sync initiated for app {} (card {}): sync={}, health={}",
                    app_name,
                    card.id,
                    app.status.sync.status,
                    app.status.health.status
                );

                self.event_bus.publish(Event::DeployStatus {
                    card_id: card.id,
                    app_name: app_name.clone(),
                    sync_status: app.status.sync.status,
                    health_status: app.status.health.status,
                    timestamp: chrono::Utc::now(),
                });

                Ok(())
            }
            Err(crate::integrations::IntegrationError::NotFound(_)) => {
                Err(ActionError::IntegrationError(format!(
                    "ArgoCD application '{}' not found",
                    app_name
                )))
            }
            Err(crate::integrations::IntegrationError::AuthRequired) => {
                Err(ActionError::IntegrationError(
                    "ArgoCD authentication required - set ARGOCD_AUTH_TOKEN".to_string(),
                ))
            }
            Err(e) => Err(ActionError::IntegrationError(format!(
                "Failed to sync ArgoCD application: {}",
                e
            ))),
        }
    }

    /// Start monitoring ArgoCD sync status
    async fn monitor_argocd(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Starting ArgoCD monitor for card {}", card.id);

        let argocd_client = self
            .argocd_client
            .clone()
            .ok_or_else(|| {
                ActionError::IntegrationError(
                    "ArgoCD not configured - set ARGOCD_SERVER environment variable".to_string(),
                )
            })?;

        let app_name = card
            .argocd_app_name
            .clone()
            .ok_or_else(|| {
                ActionError::IntegrationError("No ArgoCD app name set for card".to_string())
            })?;

        let card_id = card.id;
        let event_bus = self.event_bus.clone();
        let pool = self.pool.clone();

        // Spawn background task to poll ArgoCD status
        tokio::spawn(async move {
            let poll_interval = Duration::from_secs(15);
            let max_polls = 40; // 10 minutes max
            let mut polls = 0;

            loop {
                polls += 1;
                if polls > max_polls {
                    tracing::warn!("ArgoCD monitor timeout for card {}", card_id);
                    break;
                }

                match argocd_client.get_application(&app_name).await {
                    Ok(app) => {
                        let sync_status = &app.status.sync.status;
                        let health_status = &app.status.health.status;

                        event_bus.publish(Event::DeployStatus {
                            card_id,
                            app_name: app_name.clone(),
                            sync_status: sync_status.clone(),
                            health_status: health_status.clone(),
                            timestamp: chrono::Utc::now(),
                        });

                        // Check if sync is complete
                        let is_synced = sync_status == "Synced";
                        let is_healthy = health_status == "Healthy";
                        let is_degraded = health_status == "Degraded";
                        let sync_failed = sync_status == "OutOfSync"
                            && !app.status.sync.revision.is_empty()
                            && polls > 5; // Give it a few polls before declaring failure

                        if is_synced && is_healthy {
                            tracing::info!(
                                "ArgoCD deployment successful for card {}: app={}",
                                card_id,
                                app_name
                            );
                            break;
                        }

                        if is_degraded || sync_failed {
                            tracing::warn!(
                                "ArgoCD deployment issue for card {}: sync={}, health={}",
                                card_id,
                                sync_status,
                                health_status
                            );

                            let error = CardError::new(
                                card_id,
                                "deploy_failure".to_string(),
                                format!(
                                    "Deployment issue: sync={}, health={}",
                                    sync_status, health_status
                                ),
                            )
                            .with_category(ErrorCategory::Deploy);

                            if let Err(e) = crate::db::record_error(&pool, &error).await {
                                tracing::error!("Failed to record deploy error: {}", e);
                            }

                            break;
                        }
                    }
                    Err(e) => {
                        tracing::error!(
                            "Error polling ArgoCD status for card {}: {}",
                            card_id,
                            e
                        );
                    }
                }

                tokio::time::sleep(poll_interval).await;
            }
        });

        Ok(())
    }

    /// Run health checks against deployed services
    async fn run_health_checks(&self, card: &Card) -> Result<(), ActionError> {
        tracing::info!("Running health checks for card {}", card.id);

        let namespace = card.deployment_namespace.as_ref().ok_or_else(|| {
            ActionError::IntegrationError("No deployment namespace set for card".to_string())
        })?;

        let deployment_name = card.deployment_name.as_ref().ok_or_else(|| {
            ActionError::IntegrationError("No deployment name set for card".to_string())
        })?;

        // Create Kubernetes service - this is async because it loads config
        let k8s_service = KubernetesService::new()
            .await
            .map_err(|e| ActionError::IntegrationError(format!("Failed to create K8s client: {}", e)))?;

        // Check if the deployment is healthy
        match k8s_service.is_deployment_healthy(namespace, deployment_name).await {
            Ok(true) => {
                tracing::info!(
                    "Deployment {}/{} is healthy for card {}",
                    namespace,
                    deployment_name,
                    card.id
                );
                Ok(())
            }
            Ok(false) => {
                tracing::warn!(
                    "Deployment {}/{} is not healthy for card {}",
                    namespace,
                    deployment_name,
                    card.id
                );

                // Collect error context
                match k8s_service
                    .collect_deployment_errors(namespace, deployment_name)
                    .await
                {
                    Ok(error_context) => {
                        // Log container issues
                        for issue in &error_context.container_issues {
                            tracing::warn!(
                                "Container issue in pod {}/{}: {} - {:?}",
                                issue.pod_name,
                                issue.container_name,
                                issue.reason,
                                issue.message
                            );

                            // Record error for each container issue
                            let error = CardError::new(
                                card.id,
                                "container_issue".to_string(),
                                format!("{}: {}", issue.reason, issue.message.as_deref().unwrap_or("")),
                            )
                            .with_category(ErrorCategory::Runtime)
                            .with_context(ErrorContext {
                                logs: issue.logs.clone(),
                                ..Default::default()
                            });

                            if let Err(e) = crate::db::record_error(&self.pool, &error).await {
                                tracing::error!("Failed to record container error: {}", e);
                            }
                        }

                        // Log warning events
                        for event in &error_context.warning_events {
                            tracing::warn!(
                                "K8s warning event: {} - {} (count: {})",
                                event.reason,
                                event.message,
                                event.count
                            );
                        }

                        Err(ActionError::IntegrationError(format!(
                            "Deployment unhealthy: {} container issues, {} warning events",
                            error_context.container_issues.len(),
                            error_context.warning_events.len()
                        )))
                    }
                    Err(e) => Err(ActionError::IntegrationError(format!(
                        "Deployment unhealthy and failed to collect error context: {}",
                        e
                    ))),
                }
            }
            Err(e) => Err(ActionError::IntegrationError(format!(
                "Failed to check deployment health: {}",
                e
            ))),
        }
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
