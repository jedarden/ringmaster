//! Integration API routes for GitHub, ArgoCD, Docker Hub, and Kubernetes

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::integrations::{
    argocd::ArgoCDClient,
    dockerhub::DockerHubClient,
    github::GitHubClient,
    kubernetes::KubernetesService,
    IntegrationError,
};

use super::{ApiError, ApiResponse, AppState};

// =============================================================================
// ROUTES
// =============================================================================

/// Create integration routes
pub fn integration_routes() -> Router<AppState> {
    Router::new()
        // GitHub Actions
        .route("/github/workflows/:owner/:repo", get(list_workflow_runs))
        .route("/github/workflows/:owner/:repo/:run_id", get(get_workflow_run))
        .route("/github/workflows/:owner/:repo/:run_id/jobs", get(get_workflow_jobs))
        .route("/github/workflows/:owner/:repo/:workflow_id/dispatch", post(dispatch_workflow))
        .route("/github/workflows/:owner/:repo/:run_id/cancel", post(cancel_workflow))
        // ArgoCD
        .route("/argocd/apps", get(list_argocd_apps))
        .route("/argocd/apps/:app_name", get(get_argocd_app))
        .route("/argocd/apps/:app_name/sync", post(sync_argocd_app))
        .route("/argocd/apps/:app_name/rollback", post(rollback_argocd_app))
        .route("/argocd/apps/:app_name/refresh", post(refresh_argocd_app))
        // Docker Hub
        .route("/dockerhub/tags/:namespace/:repo", get(list_docker_tags))
        .route("/dockerhub/tags/:namespace/:repo/:tag", get(get_docker_tag))
        .route("/dockerhub/repos/:namespace/:repo", get(get_docker_repo))
        .route("/dockerhub/latest/:namespace/:repo", get(get_latest_semver))
        // Kubernetes
        .route("/k8s/:namespace/deployments/:name", get(get_deployment_status))
        .route("/k8s/:namespace/pods", get(list_pods))
        .route("/k8s/:namespace/pods/:pod_name/logs", get(get_pod_logs))
        .route("/k8s/:namespace/deployments/:name/errors", get(collect_deployment_errors))
}

// =============================================================================
// GITHUB HANDLERS
// =============================================================================

#[derive(Debug, Deserialize)]
pub struct WorkflowRunsQuery {
    branch: Option<String>,
    status: Option<String>,
    per_page: Option<u32>,
}

async fn list_workflow_runs(
    State(_state): State<AppState>,
    Path((owner, repo)): Path<(String, String)>,
    Query(params): Query<WorkflowRunsQuery>,
) -> Result<Json<ApiResponse<Vec<GitHubWorkflowRun>>>, (StatusCode, Json<ApiError>)> {
    let client = GitHubClient::new(None);

    let runs = client
        .get_workflow_runs(
            &owner,
            &repo,
            params.branch.as_deref(),
            params.status.as_deref(),
            params.per_page,
        )
        .await
        .map_err(integration_error_to_api)?;

    let response_runs: Vec<GitHubWorkflowRun> = runs
        .into_iter()
        .map(|r| GitHubWorkflowRun {
            id: r.id,
            name: r.name,
            status: r.status,
            conclusion: r.conclusion,
            head_branch: r.head_branch,
            html_url: r.html_url,
            created_at: r.created_at,
            updated_at: r.updated_at,
        })
        .collect();

    Ok(Json(ApiResponse::new(response_runs)))
}

async fn get_workflow_run(
    State(_state): State<AppState>,
    Path((owner, repo, run_id)): Path<(String, String, i64)>,
) -> Result<Json<ApiResponse<GitHubWorkflowRun>>, (StatusCode, Json<ApiError>)> {
    let client = GitHubClient::new(None);

    let run = client
        .get_workflow_run(&owner, &repo, run_id)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(GitHubWorkflowRun {
        id: run.id,
        name: run.name,
        status: run.status,
        conclusion: run.conclusion,
        head_branch: run.head_branch,
        html_url: run.html_url,
        created_at: run.created_at,
        updated_at: run.updated_at,
    })))
}

async fn get_workflow_jobs(
    State(_state): State<AppState>,
    Path((owner, repo, run_id)): Path<(String, String, i64)>,
) -> Result<Json<ApiResponse<Vec<GitHubWorkflowJob>>>, (StatusCode, Json<ApiError>)> {
    let client = GitHubClient::new(None);

    let jobs = client
        .get_workflow_jobs(&owner, &repo, run_id)
        .await
        .map_err(integration_error_to_api)?;

    let response_jobs: Vec<GitHubWorkflowJob> = jobs
        .into_iter()
        .map(|j| GitHubWorkflowJob {
            id: j.id,
            name: j.name,
            status: j.status,
            conclusion: j.conclusion,
            started_at: j.started_at,
            completed_at: j.completed_at,
        })
        .collect();

    Ok(Json(ApiResponse::new(response_jobs)))
}

#[derive(Debug, Deserialize)]
pub struct DispatchWorkflowRequest {
    #[serde(rename = "ref")]
    ref_name: String,
    inputs: Option<serde_json::Value>,
}

async fn dispatch_workflow(
    State(_state): State<AppState>,
    Path((owner, repo, workflow_id)): Path<(String, String, String)>,
    Json(req): Json<DispatchWorkflowRequest>,
) -> Result<Json<ApiResponse<serde_json::Value>>, (StatusCode, Json<ApiError>)> {
    let client = GitHubClient::new(None);

    client
        .dispatch_workflow(&owner, &repo, &workflow_id, &req.ref_name, req.inputs)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(serde_json::json!({
        "status": "dispatched",
        "workflow_id": workflow_id
    }))))
}

async fn cancel_workflow(
    State(_state): State<AppState>,
    Path((owner, repo, run_id)): Path<(String, String, i64)>,
) -> Result<Json<ApiResponse<serde_json::Value>>, (StatusCode, Json<ApiError>)> {
    let client = GitHubClient::new(None);

    client
        .cancel_workflow_run(&owner, &repo, run_id)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(serde_json::json!({
        "status": "cancelled",
        "run_id": run_id
    }))))
}

// =============================================================================
// ARGOCD HANDLERS
// =============================================================================

#[derive(Debug, Deserialize)]
pub struct ArgoCDQuery {
    project: Option<String>,
    server_url: Option<String>,
}

async fn list_argocd_apps(
    State(_state): State<AppState>,
    Query(params): Query<ArgoCDQuery>,
) -> Result<Json<ApiResponse<Vec<ArgoCDAppSummary>>>, (StatusCode, Json<ApiError>)> {
    let env_url = std::env::var("ARGOCD_SERVER").ok();
    let server_url = params
        .server_url
        .as_deref()
        .or(env_url.as_deref())
        .unwrap_or("https://localhost:8080");

    let client = ArgoCDClient::new(server_url, None);

    let apps = client
        .list_applications(params.project.as_deref())
        .await
        .map_err(integration_error_to_api)?;

    let summaries: Vec<ArgoCDAppSummary> = apps
        .into_iter()
        .map(|a| ArgoCDAppSummary {
            name: a.metadata.name,
            namespace: a.metadata.namespace,
            project: a.spec.project,
            sync_status: a.status.sync.status,
            health_status: a.status.health.status,
            repo_url: a.spec.source.repo_url,
            path: a.spec.source.path,
            target_revision: a.spec.source.target_revision,
        })
        .collect();

    Ok(Json(ApiResponse::new(summaries)))
}

async fn get_argocd_app(
    State(_state): State<AppState>,
    Path(app_name): Path<String>,
    Query(params): Query<ArgoCDQuery>,
) -> Result<Json<ApiResponse<ArgoCDAppDetail>>, (StatusCode, Json<ApiError>)> {
    let env_url = std::env::var("ARGOCD_SERVER").ok();
    let server_url = params
        .server_url
        .as_deref()
        .or(env_url.as_deref())
        .unwrap_or("https://localhost:8080");

    let client = ArgoCDClient::new(server_url, None);

    let app = client
        .get_application(&app_name)
        .await
        .map_err(integration_error_to_api)?;

    let resources: Vec<ArgoCDResource> = app
        .status
        .resources
        .into_iter()
        .map(|r| ArgoCDResource {
            kind: r.kind,
            name: r.name,
            namespace: r.namespace,
            status: r.status,
            health_status: r.health.map(|h| h.status),
            health_message: None,
        })
        .collect();

    Ok(Json(ApiResponse::new(ArgoCDAppDetail {
        name: app.metadata.name,
        namespace: app.metadata.namespace,
        project: app.spec.project,
        sync_status: app.status.sync.status,
        sync_revision: app.status.sync.revision,
        health_status: app.status.health.status,
        health_message: app.status.health.message,
        destination_server: app.spec.destination.server,
        destination_namespace: app.spec.destination.namespace,
        repo_url: app.spec.source.repo_url,
        path: app.spec.source.path,
        target_revision: app.spec.source.target_revision,
        resources,
    })))
}

#[derive(Debug, Deserialize)]
pub struct SyncAppRequest {
    revision: Option<String>,
    #[serde(default)]
    prune: bool,
    server_url: Option<String>,
}

async fn sync_argocd_app(
    State(_state): State<AppState>,
    Path(app_name): Path<String>,
    Json(req): Json<SyncAppRequest>,
) -> Result<Json<ApiResponse<ArgoCDAppSummary>>, (StatusCode, Json<ApiError>)> {
    let env_url = std::env::var("ARGOCD_SERVER").ok();
    let server_url = req
        .server_url
        .as_deref()
        .or(env_url.as_deref())
        .unwrap_or("https://localhost:8080");

    let client = ArgoCDClient::new(server_url, None);

    let app = client
        .sync_application(&app_name, req.revision.as_deref(), req.prune)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(ArgoCDAppSummary {
        name: app.metadata.name,
        namespace: app.metadata.namespace,
        project: app.spec.project,
        sync_status: app.status.sync.status,
        health_status: app.status.health.status,
        repo_url: app.spec.source.repo_url,
        path: app.spec.source.path,
        target_revision: app.spec.source.target_revision,
    })))
}

#[derive(Debug, Deserialize)]
pub struct RollbackRequest {
    id: i64,
    server_url: Option<String>,
}

async fn rollback_argocd_app(
    State(_state): State<AppState>,
    Path(app_name): Path<String>,
    Json(req): Json<RollbackRequest>,
) -> Result<Json<ApiResponse<ArgoCDAppSummary>>, (StatusCode, Json<ApiError>)> {
    let env_url = std::env::var("ARGOCD_SERVER").ok();
    let server_url = req
        .server_url
        .as_deref()
        .or(env_url.as_deref())
        .unwrap_or("https://localhost:8080");

    let client = ArgoCDClient::new(server_url, None);

    let app = client
        .rollback(&app_name, req.id)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(ArgoCDAppSummary {
        name: app.metadata.name,
        namespace: app.metadata.namespace,
        project: app.spec.project,
        sync_status: app.status.sync.status,
        health_status: app.status.health.status,
        repo_url: app.spec.source.repo_url,
        path: app.spec.source.path,
        target_revision: app.spec.source.target_revision,
    })))
}

#[derive(Debug, Deserialize)]
pub struct RefreshRequest {
    #[serde(default)]
    hard: bool,
    server_url: Option<String>,
}

async fn refresh_argocd_app(
    State(_state): State<AppState>,
    Path(app_name): Path<String>,
    Json(req): Json<RefreshRequest>,
) -> Result<Json<ApiResponse<ArgoCDAppSummary>>, (StatusCode, Json<ApiError>)> {
    let env_url = std::env::var("ARGOCD_SERVER").ok();
    let server_url = req
        .server_url
        .as_deref()
        .or(env_url.as_deref())
        .unwrap_or("https://localhost:8080");

    let client = ArgoCDClient::new(server_url, None);

    let app = client
        .refresh_application(&app_name, req.hard)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(ArgoCDAppSummary {
        name: app.metadata.name,
        namespace: app.metadata.namespace,
        project: app.spec.project,
        sync_status: app.status.sync.status,
        health_status: app.status.health.status,
        repo_url: app.spec.source.repo_url,
        path: app.spec.source.path,
        target_revision: app.spec.source.target_revision,
    })))
}

// =============================================================================
// DOCKER HUB HANDLERS
// =============================================================================

#[derive(Debug, Deserialize)]
pub struct DockerTagsQuery {
    page_size: Option<u32>,
}

async fn list_docker_tags(
    State(_state): State<AppState>,
    Path((namespace, repo)): Path<(String, String)>,
    Query(params): Query<DockerTagsQuery>,
) -> Result<Json<ApiResponse<Vec<DockerTag>>>, (StatusCode, Json<ApiError>)> {
    let client = DockerHubClient::new();
    let image = format!("{}/{}", namespace, repo);

    let tags = client
        .get_tags(&image, params.page_size)
        .await
        .map_err(integration_error_to_api)?;

    let response_tags: Vec<DockerTag> = tags
        .into_iter()
        .map(|t| DockerTag {
            name: t.name,
            digest: t.digest,
            last_updated: t.last_updated,
            full_size: t.full_size,
            platforms: t
                .images
                .into_iter()
                .map(|p| DockerPlatform {
                    architecture: p.architecture,
                    os: p.os,
                    size: p.size,
                })
                .collect(),
        })
        .collect();

    Ok(Json(ApiResponse::new(response_tags)))
}

async fn get_docker_tag(
    State(_state): State<AppState>,
    Path((namespace, repo, tag)): Path<(String, String, String)>,
) -> Result<Json<ApiResponse<DockerTag>>, (StatusCode, Json<ApiError>)> {
    let client = DockerHubClient::new();
    let image = format!("{}/{}", namespace, repo);

    let tag_info = client
        .get_tag(&image, &tag)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(DockerTag {
        name: tag_info.name,
        digest: tag_info.digest,
        last_updated: tag_info.last_updated,
        full_size: tag_info.full_size,
        platforms: tag_info
            .images
            .into_iter()
            .map(|p| DockerPlatform {
                architecture: p.architecture,
                os: p.os,
                size: p.size,
            })
            .collect(),
    })))
}

async fn get_docker_repo(
    State(_state): State<AppState>,
    Path((namespace, repo)): Path<(String, String)>,
) -> Result<Json<ApiResponse<DockerRepository>>, (StatusCode, Json<ApiError>)> {
    let client = DockerHubClient::new();
    let image = format!("{}/{}", namespace, repo);

    let repo_info = client
        .get_repository(&image)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(DockerRepository {
        namespace: repo_info.namespace,
        name: repo_info.name,
        description: repo_info.description,
        star_count: repo_info.star_count,
        pull_count: repo_info.pull_count,
        last_updated: repo_info.last_updated,
        is_private: repo_info.is_private,
    })))
}

async fn get_latest_semver(
    State(_state): State<AppState>,
    Path((namespace, repo)): Path<(String, String)>,
) -> Result<Json<ApiResponse<serde_json::Value>>, (StatusCode, Json<ApiError>)> {
    let client = DockerHubClient::new();
    let image = format!("{}/{}", namespace, repo);

    let latest = client
        .get_latest_semver(&image)
        .await
        .map_err(integration_error_to_api)?;

    Ok(Json(ApiResponse::new(serde_json::json!({
        "image": image,
        "latestSemverTag": latest
    }))))
}

// =============================================================================
// KUBERNETES HANDLERS
// =============================================================================

async fn get_deployment_status(
    State(_state): State<AppState>,
    Path((namespace, name)): Path<(String, String)>,
) -> Result<Json<ApiResponse<K8sDeploymentStatus>>, (StatusCode, Json<ApiError>)> {
    let service = KubernetesService::new()
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to connect to Kubernetes: {}", e))),
            )
        })?;

    let status = service
        .get_deployment_status(&namespace, &name)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to get deployment: {}", e))),
            )
        })?;

    Ok(Json(ApiResponse::new(K8sDeploymentStatus {
        name: status.name,
        namespace: status.namespace,
        replicas: status.replicas,
        ready_replicas: status.ready_replicas,
        updated_replicas: status.updated_replicas,
        available: status.available,
    })))
}

#[derive(Debug, Deserialize)]
pub struct PodsQuery {
    label_selector: Option<String>,
}

async fn list_pods(
    State(_state): State<AppState>,
    Path(namespace): Path<String>,
    Query(params): Query<PodsQuery>,
) -> Result<Json<ApiResponse<Vec<K8sPodStatus>>>, (StatusCode, Json<ApiError>)> {
    let service = KubernetesService::new()
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to connect to Kubernetes: {}", e))),
            )
        })?;

    let label_selector = params.label_selector.as_deref().unwrap_or("");

    let pods = service
        .get_pods(&namespace, label_selector)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to list pods: {}", e))),
            )
        })?;

    let response_pods: Vec<K8sPodStatus> = pods
        .into_iter()
        .map(|p| K8sPodStatus {
            name: p.name,
            phase: p.phase.to_string(),
            ready: p.container_statuses.iter().all(|c| c.ready),
            restart_count: p.container_statuses.iter().map(|c| c.restart_count).sum(),
            start_time: p.start_time,
        })
        .collect();

    Ok(Json(ApiResponse::new(response_pods)))
}

#[derive(Debug, Deserialize)]
pub struct PodLogsQuery {
    container: Option<String>,
    tail_lines: Option<i64>,
    previous: Option<bool>,
}

async fn get_pod_logs(
    State(_state): State<AppState>,
    Path((namespace, pod_name)): Path<(String, String)>,
    Query(params): Query<PodLogsQuery>,
) -> Result<Json<ApiResponse<serde_json::Value>>, (StatusCode, Json<ApiError>)> {
    let service = KubernetesService::new()
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to connect to Kubernetes: {}", e))),
            )
        })?;

    let tail_lines = params.tail_lines.unwrap_or(100);

    let logs = if params.previous.unwrap_or(false) {
        service
            .get_previous_logs(&namespace, &pod_name, params.container.as_deref().unwrap_or(""))
            .await
    } else {
        service
            .get_pod_logs(&namespace, &pod_name, params.container.as_deref(), tail_lines)
            .await
    }
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiError::internal_error(format!("Failed to get logs: {}", e))),
        )
    })?;

    Ok(Json(ApiResponse::new(serde_json::json!({
        "pod": pod_name,
        "namespace": namespace,
        "container": params.container,
        "logs": logs
    }))))
}

async fn collect_deployment_errors(
    State(_state): State<AppState>,
    Path((namespace, name)): Path<(String, String)>,
) -> Result<Json<ApiResponse<K8sDeploymentErrors>>, (StatusCode, Json<ApiError>)> {
    let service = KubernetesService::new()
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to connect to Kubernetes: {}", e))),
            )
        })?;

    let errors = service
        .collect_deployment_errors(&namespace, &name)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ApiError::internal_error(format!("Failed to collect errors: {}", e))),
            )
        })?;

    let container_issues: Vec<K8sContainerIssue> = errors
        .container_issues
        .into_iter()
        .map(|i| K8sContainerIssue {
            pod_name: i.pod_name,
            container_name: i.container_name,
            reason: i.reason,
            message: i.message,
            logs: i.logs,
        })
        .collect();

    let warning_events: Vec<K8sEvent> = errors
        .warning_events
        .into_iter()
        .map(|e| K8sEvent {
            reason: e.reason,
            message: e.message,
            event_type: e.event_type,
            count: e.count,
        })
        .collect();

    Ok(Json(ApiResponse::new(K8sDeploymentErrors {
        deployment_name: name,
        namespace,
        container_issues,
        warning_events,
    })))
}

// =============================================================================
// RESPONSE TYPES
// =============================================================================

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GitHubWorkflowRun {
    pub id: i64,
    pub name: String,
    pub status: String,
    pub conclusion: Option<String>,
    pub head_branch: String,
    pub html_url: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GitHubWorkflowJob {
    pub id: i64,
    pub name: String,
    pub status: String,
    pub conclusion: Option<String>,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArgoCDAppSummary {
    pub name: String,
    pub namespace: String,
    pub project: String,
    pub sync_status: String,
    pub health_status: String,
    pub repo_url: String,
    pub path: String,
    pub target_revision: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArgoCDAppDetail {
    pub name: String,
    pub namespace: String,
    pub project: String,
    pub sync_status: String,
    pub sync_revision: String,
    pub health_status: String,
    pub health_message: Option<String>,
    pub destination_server: String,
    pub destination_namespace: String,
    pub repo_url: String,
    pub path: String,
    pub target_revision: String,
    pub resources: Vec<ArgoCDResource>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ArgoCDResource {
    pub kind: String,
    pub name: String,
    pub namespace: String,
    pub status: Option<String>,
    pub health_status: Option<String>,
    pub health_message: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DockerTag {
    pub name: String,
    pub digest: String,
    pub last_updated: Option<String>,
    pub full_size: u64,
    pub platforms: Vec<DockerPlatform>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DockerPlatform {
    pub architecture: String,
    pub os: String,
    pub size: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DockerRepository {
    pub namespace: String,
    pub name: String,
    pub description: Option<String>,
    pub star_count: i32,
    pub pull_count: i64,
    pub last_updated: Option<String>,
    pub is_private: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct K8sDeploymentStatus {
    pub name: String,
    pub namespace: String,
    pub replicas: i32,
    pub ready_replicas: i32,
    pub updated_replicas: i32,
    pub available: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct K8sPodStatus {
    pub name: String,
    pub phase: String,
    pub ready: bool,
    pub restart_count: i32,
    pub start_time: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct K8sDeploymentErrors {
    pub deployment_name: String,
    pub namespace: String,
    pub container_issues: Vec<K8sContainerIssue>,
    pub warning_events: Vec<K8sEvent>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct K8sContainerIssue {
    pub pod_name: String,
    pub container_name: String,
    pub reason: String,
    pub message: Option<String>,
    pub logs: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct K8sEvent {
    pub reason: String,
    pub message: String,
    pub event_type: String,
    pub count: i32,
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

fn integration_error_to_api(e: IntegrationError) -> (StatusCode, Json<ApiError>) {
    match e {
        IntegrationError::NotFound(msg) => (
            StatusCode::NOT_FOUND,
            Json(ApiError::not_found(&msg)),
        ),
        IntegrationError::AuthRequired => (
            StatusCode::UNAUTHORIZED,
            Json(ApiError::new("UNAUTHORIZED", "Authentication required")),
        ),
        IntegrationError::RateLimited { retry_after } => (
            StatusCode::TOO_MANY_REQUESTS,
            Json(ApiError::with_details(
                "RATE_LIMITED",
                "Too many requests",
                serde_json::json!({ "retryAfter": retry_after }),
            )),
        ),
        IntegrationError::ApiError { status, message } => (
            StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
            Json(ApiError::new("INTEGRATION_ERROR", &message)),
        ),
        IntegrationError::RequestFailed(e) => (
            StatusCode::BAD_GATEWAY,
            Json(ApiError::internal_error(format!("Request failed: {}", e))),
        ),
        IntegrationError::ParseError(msg) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ApiError::internal_error(format!("Parse error: {}", msg))),
        ),
    }
}
