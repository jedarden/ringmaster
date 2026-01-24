//! Integration services for external systems
//!
//! This module provides integrations with various external services:
//! - GitHub Actions (CI/CD monitoring)
//! - ArgoCD (GitOps deployments)
//! - Docker Hub (container registry)
//! - Git operations (worktrees, commits, etc.)
//!
//! ## Claude Integration (Deprecated)
//!
//! The `claude` submodule provides direct API access but is **deprecated**.
//! Use `crate::platforms::ClaudeCodePlatform` instead for CLI-based execution
//! with subscription billing.
//!
//! See [`crate::platforms`] for the recommended approach.

use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::env;
use thiserror::Error;

// Integration Hub - unified coordination of all services
pub mod hub;
pub use hub::{IntegrationHub, IntegrationStatus};

// Re-export Claude integration from dedicated module (deprecated - use platforms instead)
#[deprecated(
    since = "0.2.0",
    note = "Use crate::platforms module instead for CLI-based execution"
)]
pub mod claude;

#[allow(deprecated)]
pub use claude::{ClaudeClient, ClaudeError, CompletionResponse, Message, Role, StopReason};

// Kubernetes integration
pub mod kubernetes;
pub use kubernetes::{KubernetesService, KubeError, DeploymentErrorContext};

// Config sync integration
pub mod config_sync;
pub use config_sync::{ConfigSyncService, ConfigSyncError, ConfigSyncStatus, SyncResult};

/// Common integration error type
#[derive(Error, Debug)]
pub enum IntegrationError {
    #[error("HTTP request failed: {0}")]
    RequestFailed(#[from] reqwest::Error),

    #[error("API error: {status} - {message}")]
    ApiError { status: u16, message: String },

    #[error("Authentication required")]
    AuthRequired,

    #[error("Resource not found: {0}")]
    NotFound(String),

    #[error("Rate limited, retry after {retry_after:?} seconds")]
    RateLimited { retry_after: Option<u64> },

    #[error("Parse error: {0}")]
    ParseError(String),
}

/// GitHub Actions integration
pub mod github {
    use super::*;

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct WorkflowRun {
        pub id: i64,
        pub name: String,
        pub status: String,
        pub conclusion: Option<String>,
        #[serde(default)]
        pub head_branch: String,
        pub html_url: String,
        pub created_at: String,
        pub updated_at: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct WorkflowJob {
        pub id: i64,
        pub name: String,
        pub status: String,
        pub conclusion: Option<String>,
        pub started_at: Option<String>,
        pub completed_at: Option<String>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    struct WorkflowRunsResponse {
        total_count: i32,
        workflow_runs: Vec<WorkflowRun>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    struct JobsResponse {
        total_count: i32,
        jobs: Vec<WorkflowJob>,
    }

    /// GitHub Actions client
    pub struct GitHubClient {
        client: Client,
        token: Option<String>,
        api_url: String,
    }

    impl GitHubClient {
        /// Create a new GitHub client
        ///
        /// Reads token from GITHUB_TOKEN environment variable if not provided
        pub fn new(token: Option<String>) -> Self {
            let token = token.or_else(|| env::var("GITHUB_TOKEN").ok());
            Self {
                client: Client::new(),
                token,
                api_url: "https://api.github.com".to_string(),
            }
        }

        /// Create a client with a custom API URL (for GitHub Enterprise)
        pub fn with_api_url(mut self, url: impl Into<String>) -> Self {
            self.api_url = url.into();
            self
        }

        fn build_request(&self, url: &str) -> reqwest::RequestBuilder {
            let mut req = self.client
                .get(url)
                .header("Accept", "application/vnd.github+json")
                .header("User-Agent", "ringmaster/0.1.0")
                .header("X-GitHub-Api-Version", "2022-11-28");

            if let Some(ref token) = self.token {
                req = req.header("Authorization", format!("Bearer {}", token));
            }

            req
        }

        /// Get a specific workflow run
        pub async fn get_workflow_run(
            &self,
            owner: &str,
            repo: &str,
            run_id: i64,
        ) -> Result<WorkflowRun, IntegrationError> {
            let url = format!(
                "{}/repos/{}/{}/actions/runs/{}",
                self.api_url, owner, repo, run_id
            );

            let response = self.build_request(&url).send().await?;
            self.handle_response(response).await
        }

        /// Get workflow runs for a repository
        pub async fn get_workflow_runs(
            &self,
            owner: &str,
            repo: &str,
            branch: Option<&str>,
            status: Option<&str>,
            per_page: Option<u32>,
        ) -> Result<Vec<WorkflowRun>, IntegrationError> {
            let mut url = format!(
                "{}/repos/{}/{}/actions/runs",
                self.api_url, owner, repo
            );

            let mut params = Vec::new();
            if let Some(b) = branch {
                params.push(format!("branch={}", b));
            }
            if let Some(s) = status {
                params.push(format!("status={}", s));
            }
            if let Some(p) = per_page {
                params.push(format!("per_page={}", p));
            }

            if !params.is_empty() {
                url.push('?');
                url.push_str(&params.join("&"));
            }

            let response = self.build_request(&url).send().await?;
            let runs_response: WorkflowRunsResponse = self.handle_response(response).await?;
            Ok(runs_response.workflow_runs)
        }

        /// Get jobs for a workflow run
        pub async fn get_workflow_jobs(
            &self,
            owner: &str,
            repo: &str,
            run_id: i64,
        ) -> Result<Vec<WorkflowJob>, IntegrationError> {
            let url = format!(
                "{}/repos/{}/{}/actions/runs/{}/jobs",
                self.api_url, owner, repo, run_id
            );

            let response = self.build_request(&url).send().await?;
            let jobs_response: JobsResponse = self.handle_response(response).await?;
            Ok(jobs_response.jobs)
        }

        /// Trigger a workflow dispatch event
        pub async fn dispatch_workflow(
            &self,
            owner: &str,
            repo: &str,
            workflow_id: &str,
            ref_name: &str,
            inputs: Option<serde_json::Value>,
        ) -> Result<(), IntegrationError> {
            if self.token.is_none() {
                return Err(IntegrationError::AuthRequired);
            }

            let url = format!(
                "{}/repos/{}/{}/actions/workflows/{}/dispatches",
                self.api_url, owner, repo, workflow_id
            );

            let mut body = serde_json::json!({
                "ref": ref_name
            });

            if let Some(inp) = inputs {
                body["inputs"] = inp;
            }

            let mut req = self.client
                .post(&url)
                .header("Accept", "application/vnd.github+json")
                .header("User-Agent", "ringmaster/0.1.0")
                .header("X-GitHub-Api-Version", "2022-11-28")
                .json(&body);

            if let Some(ref token) = self.token {
                req = req.header("Authorization", format!("Bearer {}", token));
            }

            let response = req.send().await?;
            let status = response.status();

            if status.is_success() {
                Ok(())
            } else if status == reqwest::StatusCode::NOT_FOUND {
                Err(IntegrationError::NotFound(format!("Workflow {} not found", workflow_id)))
            } else {
                let error_text = response.text().await.unwrap_or_default();
                Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                })
            }
        }

        /// Cancel a workflow run
        pub async fn cancel_workflow_run(
            &self,
            owner: &str,
            repo: &str,
            run_id: i64,
        ) -> Result<(), IntegrationError> {
            if self.token.is_none() {
                return Err(IntegrationError::AuthRequired);
            }

            let url = format!(
                "{}/repos/{}/{}/actions/runs/{}/cancel",
                self.api_url, owner, repo, run_id
            );

            let mut req = self.client
                .post(&url)
                .header("Accept", "application/vnd.github+json")
                .header("User-Agent", "ringmaster/0.1.0")
                .header("X-GitHub-Api-Version", "2022-11-28");

            if let Some(ref token) = self.token {
                req = req.header("Authorization", format!("Bearer {}", token));
            }

            let response = req.send().await?;
            let status = response.status();

            if status.is_success() || status == reqwest::StatusCode::ACCEPTED {
                Ok(())
            } else {
                let error_text = response.text().await.unwrap_or_default();
                Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                })
            }
        }

        async fn handle_response<T: serde::de::DeserializeOwned>(
            &self,
            response: reqwest::Response,
        ) -> Result<T, IntegrationError> {
            let status = response.status();

            if status == reqwest::StatusCode::NOT_FOUND {
                return Err(IntegrationError::NotFound("Resource not found".to_string()));
            }

            if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
                return Err(IntegrationError::AuthRequired);
            }

            if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
                let retry_after = response
                    .headers()
                    .get("retry-after")
                    .and_then(|h| h.to_str().ok())
                    .and_then(|s| s.parse().ok());
                return Err(IntegrationError::RateLimited { retry_after });
            }

            if !status.is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                });
            }

            response
                .json()
                .await
                .map_err(|e| IntegrationError::ParseError(e.to_string()))
        }
    }
}

/// ArgoCD integration
pub mod argocd {
    use super::*;

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(rename_all = "camelCase")]
    pub struct Application {
        pub metadata: ApplicationMetadata,
        pub spec: ApplicationSpec,
        pub status: ApplicationStatus,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ApplicationMetadata {
        pub name: String,
        pub namespace: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(rename_all = "camelCase")]
    pub struct ApplicationSpec {
        pub project: String,
        pub source: ApplicationSource,
        pub destination: ApplicationDestination,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(rename_all = "camelCase")]
    pub struct ApplicationSource {
        pub repo_url: String,
        pub path: String,
        pub target_revision: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ApplicationDestination {
        pub server: String,
        pub namespace: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(rename_all = "camelCase")]
    pub struct ApplicationStatus {
        pub sync: SyncStatus,
        pub health: HealthStatus,
        #[serde(default)]
        pub resources: Vec<Resource>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct SyncStatus {
        pub status: String,
        #[serde(default)]
        pub revision: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct HealthStatus {
        pub status: String,
        #[serde(default)]
        pub message: Option<String>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    #[serde(rename_all = "camelCase")]
    pub struct Resource {
        pub kind: String,
        pub name: String,
        #[serde(default)]
        pub namespace: String,
        pub status: Option<String>,
        pub health: Option<HealthStatus>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    struct ApplicationList {
        items: Vec<Application>,
    }

    /// ArgoCD client
    pub struct ArgoCDClient {
        client: Client,
        server_url: String,
        token: Option<String>,
    }

    impl ArgoCDClient {
        /// Create a new ArgoCD client
        ///
        /// Reads token from ARGOCD_AUTH_TOKEN environment variable if not provided
        pub fn new(server_url: impl Into<String>, token: Option<String>) -> Self {
            let token = token.or_else(|| env::var("ARGOCD_AUTH_TOKEN").ok());
            Self {
                client: Client::builder()
                    .danger_accept_invalid_certs(true) // ArgoCD often uses self-signed certs
                    .build()
                    .unwrap_or_else(|_| Client::new()),
                server_url: server_url.into().trim_end_matches('/').to_string(),
                token,
            }
        }

        fn build_request(&self, method: reqwest::Method, path: &str) -> Result<reqwest::RequestBuilder, IntegrationError> {
            let token = self.token.as_ref().ok_or(IntegrationError::AuthRequired)?;

            let url = format!("{}/api/v1{}", self.server_url, path);

            Ok(self.client
                .request(method, &url)
                .header("Authorization", format!("Bearer {}", token))
                .header("Content-Type", "application/json"))
        }

        /// Get an application by name
        pub async fn get_application(&self, app_name: &str) -> Result<Application, IntegrationError> {
            let req = self.build_request(reqwest::Method::GET, &format!("/applications/{}", app_name))?;
            let response = req.send().await?;
            self.handle_response(response).await
        }

        /// List all applications
        pub async fn list_applications(&self, project: Option<&str>) -> Result<Vec<Application>, IntegrationError> {
            let mut path = "/applications".to_string();
            if let Some(proj) = project {
                path.push_str(&format!("?project={}", proj));
            }

            let req = self.build_request(reqwest::Method::GET, &path)?;
            let response = req.send().await?;
            let list: ApplicationList = self.handle_response(response).await?;
            Ok(list.items)
        }

        /// Sync an application
        pub async fn sync_application(
            &self,
            app_name: &str,
            revision: Option<&str>,
            prune: bool,
        ) -> Result<Application, IntegrationError> {
            let mut body = serde_json::json!({
                "prune": prune
            });

            if let Some(rev) = revision {
                body["revision"] = serde_json::Value::String(rev.to_string());
            }

            let req = self.build_request(reqwest::Method::POST, &format!("/applications/{}/sync", app_name))?
                .json(&body);
            let response = req.send().await?;
            self.handle_response(response).await
        }

        /// Rollback an application to a specific revision
        pub async fn rollback(&self, app_name: &str, id: i64) -> Result<Application, IntegrationError> {
            let body = serde_json::json!({
                "id": id
            });

            let req = self.build_request(reqwest::Method::POST, &format!("/applications/{}/rollback", app_name))?
                .json(&body);
            let response = req.send().await?;
            self.handle_response(response).await
        }

        /// Get application resource tree
        pub async fn get_resource_tree(&self, app_name: &str) -> Result<Vec<Resource>, IntegrationError> {
            let app = self.get_application(app_name).await?;
            Ok(app.status.resources)
        }

        /// Refresh an application (force reconciliation)
        pub async fn refresh_application(&self, app_name: &str, hard: bool) -> Result<Application, IntegrationError> {
            let refresh_type = if hard { "hard" } else { "normal" };
            let req = self.build_request(
                reqwest::Method::GET,
                &format!("/applications/{}?refresh={}", app_name, refresh_type)
            )?;
            let response = req.send().await?;
            self.handle_response(response).await
        }

        /// Delete an application
        pub async fn delete_application(&self, app_name: &str, cascade: bool) -> Result<(), IntegrationError> {
            let req = self.build_request(
                reqwest::Method::DELETE,
                &format!("/applications/{}?cascade={}", app_name, cascade)
            )?;
            let response = req.send().await?;
            let status = response.status();

            if status.is_success() {
                Ok(())
            } else {
                let error_text = response.text().await.unwrap_or_default();
                Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                })
            }
        }

        async fn handle_response<T: serde::de::DeserializeOwned>(
            &self,
            response: reqwest::Response,
        ) -> Result<T, IntegrationError> {
            let status = response.status();

            if status == reqwest::StatusCode::NOT_FOUND {
                return Err(IntegrationError::NotFound("Application not found".to_string()));
            }

            if status == reqwest::StatusCode::UNAUTHORIZED || status == reqwest::StatusCode::FORBIDDEN {
                return Err(IntegrationError::AuthRequired);
            }

            if !status.is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                });
            }

            response
                .json()
                .await
                .map_err(|e| IntegrationError::ParseError(e.to_string()))
        }
    }
}

/// Docker Hub integration
pub mod dockerhub {
    use super::*;

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ImageTag {
        pub name: String,
        #[serde(default)]
        pub digest: String,
        pub last_updated: Option<String>,
        #[serde(default)]
        pub full_size: u64,
        #[serde(default)]
        pub images: Vec<ImagePlatform>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct ImagePlatform {
        pub architecture: String,
        pub os: String,
        #[serde(default)]
        pub size: u64,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    struct TagsResponse {
        count: i32,
        next: Option<String>,
        previous: Option<String>,
        results: Vec<ImageTag>,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct Repository {
        pub namespace: String,
        pub name: String,
        pub description: Option<String>,
        pub star_count: i32,
        pub pull_count: i64,
        pub last_updated: Option<String>,
        pub is_private: bool,
    }

    /// Docker Hub client for monitoring container images
    pub struct DockerHubClient {
        client: Client,
        api_url: String,
        auth_token: Option<String>,
    }

    impl DockerHubClient {
        /// Create a new Docker Hub client
        pub fn new() -> Self {
            Self {
                client: Client::new(),
                api_url: "https://hub.docker.com/v2".to_string(),
                auth_token: None,
            }
        }

        /// Create a client with authentication
        pub fn with_token(mut self, token: impl Into<String>) -> Self {
            self.auth_token = Some(token.into());
            self
        }

        /// Authenticate with Docker Hub
        pub async fn authenticate(
            &mut self,
            username: &str,
            password: &str,
        ) -> Result<(), IntegrationError> {
            let url = format!("{}/users/login", self.api_url);

            let body = serde_json::json!({
                "username": username,
                "password": password
            });

            let response = self.client
                .post(&url)
                .json(&body)
                .send()
                .await?;

            let status = response.status();
            if !status.is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                });
            }

            #[derive(Deserialize)]
            struct AuthResponse {
                token: String,
            }

            let auth: AuthResponse = response
                .json()
                .await
                .map_err(|e| IntegrationError::ParseError(e.to_string()))?;

            self.auth_token = Some(auth.token);
            Ok(())
        }

        fn build_request(&self, url: &str) -> reqwest::RequestBuilder {
            let mut req = self.client
                .get(url)
                .header("Accept", "application/json");

            if let Some(ref token) = self.auth_token {
                req = req.header("Authorization", format!("Bearer {}", token));
            }

            req
        }

        /// Parse image name into namespace and repository
        fn parse_image(&self, image: &str) -> Result<(String, String), IntegrationError> {
            let parts: Vec<&str> = image.split('/').collect();
            match parts.len() {
                1 => Ok(("library".to_string(), parts[0].to_string())),
                2 => Ok((parts[0].to_string(), parts[1].to_string())),
                _ => Err(IntegrationError::ParseError(format!(
                    "Invalid image name: {}",
                    image
                ))),
            }
        }

        /// Get repository information
        pub async fn get_repository(&self, image: &str) -> Result<Repository, IntegrationError> {
            let (namespace, repo) = self.parse_image(image)?;
            let url = format!("{}/repositories/{}/{}", self.api_url, namespace, repo);

            let response = self.build_request(&url).send().await?;
            self.handle_response(response).await
        }

        /// Get all tags for an image
        pub async fn get_tags(
            &self,
            image: &str,
            page_size: Option<u32>,
        ) -> Result<Vec<ImageTag>, IntegrationError> {
            let (namespace, repo) = self.parse_image(image)?;
            let page_size = page_size.unwrap_or(100);
            let url = format!(
                "{}/repositories/{}/{}/tags?page_size={}",
                self.api_url, namespace, repo, page_size
            );

            let response = self.build_request(&url).send().await?;
            let tags_response: TagsResponse = self.handle_response(response).await?;
            Ok(tags_response.results)
        }

        /// Check if a specific tag exists
        pub async fn tag_exists(&self, image: &str, tag: &str) -> Result<bool, IntegrationError> {
            let (namespace, repo) = self.parse_image(image)?;
            let url = format!(
                "{}/repositories/{}/{}/tags/{}",
                self.api_url, namespace, repo, tag
            );

            let response = self.build_request(&url).send().await?;
            Ok(response.status().is_success())
        }

        /// Get a specific tag
        pub async fn get_tag(&self, image: &str, tag: &str) -> Result<ImageTag, IntegrationError> {
            let (namespace, repo) = self.parse_image(image)?;
            let url = format!(
                "{}/repositories/{}/{}/tags/{}",
                self.api_url, namespace, repo, tag
            );

            let response = self.build_request(&url).send().await?;
            self.handle_response(response).await
        }

        /// Get the latest semver tag
        pub async fn get_latest_semver(&self, image: &str) -> Result<Option<String>, IntegrationError> {
            let tags = self.get_tags(image, Some(100)).await?;

            let mut semver_tags: Vec<(semver::Version, String)> = tags
                .iter()
                .filter_map(|t| {
                    // Try to parse as semver, stripping 'v' prefix if present
                    let name = t.name.strip_prefix('v').unwrap_or(&t.name);
                    semver::Version::parse(name)
                        .ok()
                        .map(|v| (v, t.name.clone()))
                })
                .collect();

            semver_tags.sort_by(|a, b| b.0.cmp(&a.0));
            Ok(semver_tags.into_iter().next().map(|(_, name)| name))
        }

        /// Get tags matching a semver range
        pub async fn get_tags_in_range(
            &self,
            image: &str,
            range: &str,
        ) -> Result<Vec<ImageTag>, IntegrationError> {
            let req = semver::VersionReq::parse(range)
                .map_err(|e| IntegrationError::ParseError(format!("Invalid semver range: {}", e)))?;

            let tags = self.get_tags(image, Some(100)).await?;

            Ok(tags
                .into_iter()
                .filter(|t| {
                    let name = t.name.strip_prefix('v').unwrap_or(&t.name);
                    semver::Version::parse(name)
                        .map(|v| req.matches(&v))
                        .unwrap_or(false)
                })
                .collect())
        }

        /// Wait for a specific tag to be available
        pub async fn wait_for_tag(
            &self,
            image: &str,
            tag: &str,
            timeout: std::time::Duration,
            poll_interval: std::time::Duration,
        ) -> Result<ImageTag, IntegrationError> {
            let start = std::time::Instant::now();

            loop {
                if start.elapsed() > timeout {
                    return Err(IntegrationError::ApiError {
                        status: 408,
                        message: format!("Timeout waiting for tag {}:{}", image, tag),
                    });
                }

                match self.get_tag(image, tag).await {
                    Ok(tag_info) => return Ok(tag_info),
                    Err(IntegrationError::NotFound(_)) => {
                        tokio::time::sleep(poll_interval).await;
                    }
                    Err(e) => return Err(e),
                }
            }
        }

        async fn handle_response<T: serde::de::DeserializeOwned>(
            &self,
            response: reqwest::Response,
        ) -> Result<T, IntegrationError> {
            let status = response.status();

            if status == reqwest::StatusCode::NOT_FOUND {
                return Err(IntegrationError::NotFound("Image or tag not found".to_string()));
            }

            if status == reqwest::StatusCode::UNAUTHORIZED {
                return Err(IntegrationError::AuthRequired);
            }

            if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
                let retry_after = response
                    .headers()
                    .get("retry-after")
                    .and_then(|h| h.to_str().ok())
                    .and_then(|s| s.parse().ok());
                return Err(IntegrationError::RateLimited { retry_after });
            }

            if !status.is_success() {
                let error_text = response.text().await.unwrap_or_default();
                return Err(IntegrationError::ApiError {
                    status: status.as_u16(),
                    message: error_text,
                });
            }

            response
                .json()
                .await
                .map_err(|e| IntegrationError::ParseError(e.to_string()))
        }
    }

    impl Default for DockerHubClient {
        fn default() -> Self {
            Self::new()
        }
    }
}

/// Git operations using git2
pub mod git {
    use std::path::Path;

    /// Create a git worktree for a card
    pub fn create_worktree(
        repo_path: &Path,
        worktree_path: &Path,
        branch_name: &str,
    ) -> Result<(), String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        // Get the HEAD commit
        let head = repo.head().map_err(|e| format!("Failed to get HEAD: {}", e))?;
        let commit = head
            .peel_to_commit()
            .map_err(|e| format!("Failed to peel to commit: {}", e))?;

        // Create branch
        repo.branch(branch_name, &commit, false)
            .map_err(|e| format!("Failed to create branch: {}", e))?;

        // Get the branch reference
        let refname = format!("refs/heads/{}", branch_name);
        let reference = repo
            .find_reference(&refname)
            .map_err(|e| format!("Failed to find reference: {}", e))?;

        // Create worktree with the reference
        let mut opts = git2::WorktreeAddOptions::new();
        opts.reference(Some(&reference));

        repo.worktree(branch_name, worktree_path, Some(&opts))
            .map_err(|e| format!("Failed to create worktree: {}", e))?;

        Ok(())
    }

    /// Remove a git worktree
    pub fn remove_worktree(repo_path: &Path, worktree_name: &str) -> Result<(), String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let worktree = repo
            .find_worktree(worktree_name)
            .map_err(|e| format!("Failed to find worktree: {}", e))?;

        let mut prune_opts = git2::WorktreePruneOptions::new();
        prune_opts.valid(true);

        worktree
            .prune(Some(&mut prune_opts))
            .map_err(|e| format!("Failed to prune worktree: {}", e))?;

        Ok(())
    }

    /// Commit changes in a worktree
    pub fn commit_changes(
        worktree_path: &Path,
        message: &str,
    ) -> Result<String, String> {
        let repo = git2::Repository::open(worktree_path)
            .map_err(|e| format!("Failed to open worktree: {}", e))?;

        let signature = repo
            .signature()
            .map_err(|e| format!("Failed to get signature: {}", e))?;

        let mut index = repo
            .index()
            .map_err(|e| format!("Failed to get index: {}", e))?;

        // Add all changes
        index
            .add_all(["*"].iter(), git2::IndexAddOption::DEFAULT, None)
            .map_err(|e| format!("Failed to add files: {}", e))?;

        let tree_id = index
            .write_tree()
            .map_err(|e| format!("Failed to write tree: {}", e))?;

        let tree = repo
            .find_tree(tree_id)
            .map_err(|e| format!("Failed to find tree: {}", e))?;

        let parent = repo
            .head()
            .and_then(|h| h.peel_to_commit())
            .map_err(|e| format!("Failed to get parent commit: {}", e))?;

        let commit_id = repo
            .commit(
                Some("HEAD"),
                &signature,
                &signature,
                message,
                &tree,
                &[&parent],
            )
            .map_err(|e| format!("Failed to create commit: {}", e))?;

        Ok(commit_id.to_string())
    }

    /// Push changes to remote
    pub fn push_to_remote(
        repo_path: &Path,
        remote_name: &str,
        branch_name: &str,
    ) -> Result<(), String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let mut remote = repo
            .find_remote(remote_name)
            .map_err(|e| format!("Failed to find remote: {}", e))?;

        let refspec = format!("refs/heads/{}:refs/heads/{}", branch_name, branch_name);

        remote
            .push(&[&refspec], None)
            .map_err(|e| format!("Failed to push: {}", e))?;

        Ok(())
    }

    /// Get diff statistics between two commits
    #[derive(Debug, Clone)]
    pub struct DiffStats {
        pub files_changed: usize,
        pub insertions: usize,
        pub deletions: usize,
    }

    /// Get diff stats for a commit compared to its parent
    pub fn get_commit_diff_stats(
        repo_path: &Path,
        commit_sha: &str,
    ) -> Result<DiffStats, String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let oid = git2::Oid::from_str(commit_sha)
            .map_err(|e| format!("Invalid commit SHA: {}", e))?;

        let commit = repo
            .find_commit(oid)
            .map_err(|e| format!("Failed to find commit: {}", e))?;

        let tree = commit
            .tree()
            .map_err(|e| format!("Failed to get commit tree: {}", e))?;

        // Get parent tree (or empty tree if no parent)
        let parent_tree = if commit.parent_count() > 0 {
            Some(
                commit
                    .parent(0)
                    .map_err(|e| format!("Failed to get parent: {}", e))?
                    .tree()
                    .map_err(|e| format!("Failed to get parent tree: {}", e))?,
            )
        } else {
            None
        };

        let diff = repo
            .diff_tree_to_tree(parent_tree.as_ref(), Some(&tree), None)
            .map_err(|e| format!("Failed to create diff: {}", e))?;

        let stats = diff
            .stats()
            .map_err(|e| format!("Failed to get diff stats: {}", e))?;

        Ok(DiffStats {
            files_changed: stats.files_changed(),
            insertions: stats.insertions(),
            deletions: stats.deletions(),
        })
    }

    /// Get the latest commit SHA on a branch
    pub fn get_branch_head(
        repo_path: &Path,
        branch_name: &str,
    ) -> Result<String, String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let refname = format!("refs/heads/{}", branch_name);
        let reference = repo
            .find_reference(&refname)
            .map_err(|e| format!("Failed to find branch: {}", e))?;

        let commit = reference
            .peel_to_commit()
            .map_err(|e| format!("Failed to peel to commit: {}", e))?;

        Ok(commit.id().to_string())
    }

    /// List worktrees for a repository
    pub fn list_worktrees(repo_path: &Path) -> Result<Vec<String>, String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let worktrees = repo
            .worktrees()
            .map_err(|e| format!("Failed to list worktrees: {}", e))?;

        Ok(worktrees
            .iter()
            .filter_map(|w| w.map(|s| s.to_string()))
            .collect())
    }

    /// Check if a branch exists
    pub fn branch_exists(repo_path: &Path, branch_name: &str) -> Result<bool, String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let refname = format!("refs/heads/{}", branch_name);
        let exists = repo.find_reference(&refname).is_ok();
        Ok(exists)
    }

    /// Get current branch name in a worktree
    pub fn get_current_branch(worktree_path: &Path) -> Result<String, String> {
        let repo = git2::Repository::open(worktree_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let head = repo.head().map_err(|e| format!("Failed to get HEAD: {}", e))?;

        let branch_name = head
            .shorthand()
            .ok_or_else(|| "Failed to get branch name".to_string())?;

        Ok(branch_name.to_string())
    }

    /// Get uncommitted changes status
    #[derive(Debug, Clone)]
    pub struct WorktreeStatus {
        pub modified: Vec<String>,
        pub added: Vec<String>,
        pub deleted: Vec<String>,
        pub untracked: Vec<String>,
    }

    pub fn get_worktree_status(worktree_path: &Path) -> Result<WorktreeStatus, String> {
        let repo = git2::Repository::open(worktree_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let statuses = repo
            .statuses(None)
            .map_err(|e| format!("Failed to get status: {}", e))?;

        let mut status = WorktreeStatus {
            modified: Vec::new(),
            added: Vec::new(),
            deleted: Vec::new(),
            untracked: Vec::new(),
        };

        for entry in statuses.iter() {
            let path = entry.path().unwrap_or("").to_string();
            let s = entry.status();

            if s.is_wt_modified() || s.is_index_modified() {
                status.modified.push(path.clone());
            }
            if s.is_wt_new() {
                status.untracked.push(path.clone());
            }
            if s.is_index_new() {
                status.added.push(path.clone());
            }
            if s.is_wt_deleted() || s.is_index_deleted() {
                status.deleted.push(path);
            }
        }

        Ok(status)
    }

    /// Create a branch from a specific commit
    pub fn create_branch_from_commit(
        repo_path: &Path,
        branch_name: &str,
        commit_sha: &str,
    ) -> Result<(), String> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| format!("Failed to open repository: {}", e))?;

        let oid = git2::Oid::from_str(commit_sha)
            .map_err(|e| format!("Invalid commit SHA: {}", e))?;

        let commit = repo
            .find_commit(oid)
            .map_err(|e| format!("Failed to find commit: {}", e))?;

        repo.branch(branch_name, &commit, false)
            .map_err(|e| format!("Failed to create branch: {}", e))?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_github_client_creation() {
        let client = github::GitHubClient::new(None);
        // Just verify it creates without panicking
        let _ = client;
    }

    #[test]
    fn test_argocd_client_creation() {
        let client = argocd::ArgoCDClient::new("https://argocd.example.com", None);
        let _ = client;
    }

    #[test]
    fn test_dockerhub_client_creation() {
        let client = dockerhub::DockerHubClient::new();
        let _ = client;
    }

    #[test]
    fn test_dockerhub_default() {
        let client = dockerhub::DockerHubClient::default();
        // Test default creates successfully
        let _ = client;
    }
}
