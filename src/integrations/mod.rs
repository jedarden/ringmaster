//! Integration services for external systems

use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::env;
use thiserror::Error;

// Re-export Claude integration from dedicated module
pub mod claude;
pub use claude::{ClaudeClient, ClaudeError, CompletionResponse, Message, Role, StopReason};

// Kubernetes integration
pub mod kubernetes;
pub use kubernetes::{KubernetesService, KubeError, DeploymentErrorContext};

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
}
