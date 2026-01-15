# Integration Services

## Overview

Ringmaster integrates with external systems to monitor and manage the complete SDLC pipeline. Each integration service provides real-time status updates, error collection, and automated actions.

### Heuristic Status Interpretation

**All integration status evaluations use pattern matching, not LLM analysis.**

Integration services interpret external system status using deterministic rules:

| Decision | Heuristic Implementation | NOT |
|----------|-------------------------|-----|
| Build passed/failed? | `workflow_run.conclusion == "success"` | "LLM reads build logs" |
| Deploy healthy? | `app.health_status in ["Healthy", "Progressing"]` | "LLM interprets status" |
| Pod ready? | `pod.status.phase == "Running"` | "LLM checks pod health" |
| Should retry? | Configurable retry count | "LLM decides strategy" |

When errors occur, logs are collected and **injected into the next LLM prompt** for code generation, but Ringmaster itself doesn't use LLMs to interpret the logs. See [09-heuristic-orchestration.md](./09-heuristic-orchestration.md) for detailed rationale.

## Integration Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            INTEGRATION HUB                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘

                              ┌───────────────────┐
                              │  Integration Hub  │
                              │                   │
                              │ • Event routing   │
                              │ • State sync      │
                              │ • Error handling  │
                              │ • Rate limiting   │
                              └─────────┬─────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  GitHub Actions     │     │  ArgoCD             │     │  Kubernetes         │
│                     │     │                     │     │                     │
│ Monitors:           │     │ Monitors:           │     │ Monitors:           │
│ • Workflow runs     │     │ • App sync status   │     │ • Pod status        │
│ • Job status        │     │ • Health status     │     │ • Container logs    │
│ • Build logs        │     │ • Sync errors       │     │ • Events            │
│                     │     │                     │     │                     │
│ Actions:            │     │ Actions:            │     │ Actions:            │
│ • Trigger workflow  │     │ • Trigger sync      │     │ • Get logs          │
│ • Cancel workflow   │     │ • Rollback          │     │ • Exec commands     │
│ • Get logs          │     │ • Hard refresh      │     │ • Port forward      │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
          │                             │                             │
          ▼                             ▼                             ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Docker Hub         │     │  Git Operations     │     │  LLM Service        │
│                     │     │                     │     │                     │
│ Monitors:           │     │ Operations:         │     │ Operations:         │
│ • Image tags        │     │ • Clone/fetch       │     │ • Prompt completion │
│ • Push events       │     │ • Branch/worktree   │     │ • Token counting    │
│ • Scan results      │     │ • Commit/push       │     │ • Cost calculation  │
│                     │     │ • Merge/rebase      │     │ • Model selection   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

## 1. GitHub Actions Integration

### Purpose
Monitors CI/CD workflows, collects build logs, and detects failures for automatic error fixing.

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       GITHUB ACTIONS INTEGRATION FLOW                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

    Card enters BUILD_QUEUE state
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  1. Find associated repository and branch                                      │
    │     • card.project.repository_url                                              │
    │     • card.branch_name                                                         │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  2. Poll GitHub Actions API for workflow runs                                  │
    │     GET /repos/{owner}/{repo}/actions/runs?branch={branch}                     │
    │     • Every 10 seconds while in BUILDING state                                 │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  3. Detect workflow status                                                     │
    │     • queued → Card state: BUILD_QUEUE                                         │
    │     • in_progress → Card state: BUILDING                                       │
    │     • completed/success → Card state: BUILD_SUCCESS                            │
    │     • completed/failure → Collect logs, Card state: BUILD_FAILED               │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
    ┌───────┴───────┐
    │               │
 SUCCESS         FAILURE
    │               │
    ▼               ▼
DEPLOY_QUEUE    ┌───────────────────────────────────────────────────────────────────┐
                │  4. On failure: Collect error context                              │
                │     • Download workflow logs                                       │
                │     • Parse failed job steps                                       │
                │     • Extract error messages                                       │
                │     • Store in errors table                                        │
                └───────────────────────────────────────────────────────────────────┘
                        │
                        ▼
                ┌───────────────────────────────────────────────────────────────────┐
                │  5. Trigger error recovery                                         │
                │     • Card state → ERROR_FIXING                                    │
                │     • Restart Ralph loop with build logs in context                │
                └───────────────────────────────────────────────────────────────────┘
```

### Implementation

```rust
// File: crates/integrations/src/github.rs

use octocrab::Octocrab;
use std::time::Duration;

pub struct GitHubActionsService {
    client: Octocrab,
    owner: String,
    repo: String,
    poll_interval: Duration,
}

#[derive(Debug, Clone)]
pub struct WorkflowRun {
    pub id: u64,
    pub name: String,
    pub status: WorkflowStatus,
    pub conclusion: Option<WorkflowConclusion>,
    pub html_url: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum WorkflowStatus {
    Queued,
    InProgress,
    Completed,
}

#[derive(Debug, Clone, PartialEq)]
pub enum WorkflowConclusion {
    Success,
    Failure,
    Cancelled,
    Skipped,
    TimedOut,
}

impl GitHubActionsService {
    pub fn new(token: &str, owner: &str, repo: &str) -> Result<Self, GitHubError> {
        let client = Octocrab::builder()
            .personal_token(token.to_string())
            .build()?;

        Ok(Self {
            client,
            owner: owner.to_string(),
            repo: repo.to_string(),
            poll_interval: Duration::from_secs(10),
        })
    }

    /// Get the latest workflow run for a branch
    pub async fn get_latest_run(&self, branch: &str) -> Result<Option<WorkflowRun>, GitHubError> {
        let runs = self.client
            .actions()
            .list_workflow_runs(&self.owner, &self.repo)
            .branch(branch)
            .per_page(1)
            .send()
            .await?;

        Ok(runs.items.first().map(|r| self.map_run(r)))
    }

    /// Wait for a workflow run to complete
    pub async fn wait_for_completion(
        &self,
        run_id: u64,
        timeout: Duration,
    ) -> Result<WorkflowRun, GitHubError> {
        let start = std::time::Instant::now();

        loop {
            if start.elapsed() > timeout {
                return Err(GitHubError::Timeout);
            }

            let run = self.client
                .actions()
                .get_workflow_run(&self.owner, &self.repo, run_id)
                .await?;

            if run.status == "completed" {
                return Ok(self.map_run(&run));
            }

            tokio::time::sleep(self.poll_interval).await;
        }
    }

    /// Get logs for a workflow run
    pub async fn get_logs(&self, run_id: u64) -> Result<String, GitHubError> {
        let logs = self.client
            .actions()
            .download_workflow_run_logs(&self.owner, &self.repo, run_id)
            .await?;

        // Parse zip file and extract logs
        self.extract_logs_from_zip(&logs)
    }

    /// Get failed job steps with their error messages
    pub async fn get_failed_steps(&self, run_id: u64) -> Result<Vec<FailedStep>, GitHubError> {
        let jobs = self.client
            .actions()
            .list_jobs_for_workflow_run(&self.owner, &self.repo, run_id)
            .send()
            .await?;

        let mut failed_steps = Vec::new();

        for job in jobs.items {
            if job.conclusion.as_deref() == Some("failure") {
                for step in job.steps.unwrap_or_default() {
                    if step.conclusion.as_deref() == Some("failure") {
                        failed_steps.push(FailedStep {
                            job_name: job.name.clone(),
                            step_name: step.name,
                            step_number: step.number,
                        });
                    }
                }
            }
        }

        Ok(failed_steps)
    }
}

#[derive(Debug)]
pub struct FailedStep {
    pub job_name: String,
    pub step_name: String,
    pub step_number: i64,
}
```

---

## 2. ArgoCD Integration

### Purpose
Monitors GitOps deployments via ArgoCD, triggers syncs, and handles rollbacks.

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ARGOCD INTEGRATION FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────────┘

    Card enters DEPLOY_QUEUE state
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  1. Identify ArgoCD application                                                │
    │     • card.argocd_app_name                                                     │
    │     • Or derive from: {project}-{card.deployment_name}                         │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  2. Trigger sync (if needed)                                                   │
    │     POST /api/v1/applications/{name}/sync                                      │
    │     • Wait for image updater or manual sync                                    │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  3. Poll application status                                                    │
    │     GET /api/v1/applications/{name}                                            │
    │     • Every 5 seconds while in DEPLOYING state                                 │
    │                                                                                │
    │     Status mapping:                                                            │
    │     ┌────────────────────────────────────────────────────────────────────────┐│
    │     │ ArgoCD Status         │ Card State                                     ││
    │     ├────────────────────────────────────────────────────────────────────────┤│
    │     │ sync=OutOfSync        │ DEPLOYING                                      ││
    │     │ sync=Synced           │ Check health                                   ││
    │     │ health=Healthy        │ VERIFYING → COMPLETED                          ││
    │     │ health=Progressing    │ VERIFYING                                      ││
    │     │ health=Degraded       │ Collect errors → ERROR_FIXING                  ││
    │     │ operationState=Failed │ Collect errors → ERROR_FIXING                  ││
    │     └────────────────────────────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────────────────────────────────┘
            │
    ┌───────┴───────┐
    │               │
 HEALTHY        DEGRADED/FAILED
    │               │
    ▼               ▼
COMPLETED      ┌───────────────────────────────────────────────────────────────────┐
               │  4. On failure: Collect deployment errors                          │
               │     • Sync error messages                                          │
               │     • Resource conditions                                          │
               │     • Pod events                                                   │
               │     • Store in errors table                                        │
               └───────────────────────────────────────────────────────────────────┘
                       │
                       ▼
               ┌───────────────────────────────────────────────────────────────────┐
               │  5. Error recovery options                                         │
               │     • Rollback to previous revision                                │
               │     • Fix manifests and retry                                      │
               │     • Restart Ralph loop with deploy context                       │
               └───────────────────────────────────────────────────────────────────┘
```

### Implementation

```rust
// File: crates/integrations/src/argocd.rs

use reqwest::Client;
use std::time::Duration;

pub struct ArgoCDService {
    client: Client,
    base_url: String,  // argocd-proxy URL
    poll_interval: Duration,
    sync_timeout: Duration,
}

#[derive(Debug, Clone)]
pub struct ApplicationStatus {
    pub name: String,
    pub namespace: String,
    pub sync_status: SyncStatus,
    pub health_status: HealthStatus,
    pub operation_state: Option<OperationState>,
    pub resources: Vec<ResourceStatus>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum SyncStatus {
    Synced,
    OutOfSync,
    Unknown,
}

#[derive(Debug, Clone, PartialEq)]
pub enum HealthStatus {
    Healthy,
    Progressing,
    Degraded,
    Suspended,
    Missing,
    Unknown,
}

#[derive(Debug, Clone)]
pub struct OperationState {
    pub phase: OperationPhase,
    pub message: String,
    pub sync_result: Option<SyncResult>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum OperationPhase {
    Running,
    Succeeded,
    Failed,
    Error,
}

impl ArgoCDService {
    pub fn new(proxy_url: &str) -> Self {
        Self {
            client: Client::new(),
            base_url: proxy_url.to_string(),
            poll_interval: Duration::from_secs(5),
            sync_timeout: Duration::from_secs(600),
        }
    }

    /// Get application status
    pub async fn get_status(&self, app_name: &str) -> Result<ApplicationStatus, ArgoCDError> {
        let url = format!("{}/api/v1/applications/{}", self.base_url, app_name);

        let response = self.client
            .get(&url)
            .send()
            .await?
            .json::<serde_json::Value>()
            .await?;

        self.parse_application_status(&response)
    }

    /// Trigger a sync
    pub async fn sync(&self, app_name: &str) -> Result<(), ArgoCDError> {
        let url = format!("{}/api/v1/applications/{}/sync", self.base_url, app_name);

        self.client
            .post(&url)
            .json(&serde_json::json!({
                "prune": true,
                "dryRun": false
            }))
            .send()
            .await?;

        Ok(())
    }

    /// Wait for sync to complete
    pub async fn wait_for_sync(
        &self,
        app_name: &str,
    ) -> Result<ApplicationStatus, ArgoCDError> {
        let start = std::time::Instant::now();

        loop {
            if start.elapsed() > self.sync_timeout {
                return Err(ArgoCDError::SyncTimeout);
            }

            let status = self.get_status(app_name).await?;

            // Check if sync completed (successfully or failed)
            if status.sync_status == SyncStatus::Synced {
                if status.health_status == HealthStatus::Healthy {
                    return Ok(status);
                } else if status.health_status == HealthStatus::Degraded {
                    return Err(ArgoCDError::HealthDegraded(status));
                }
            }

            // Check for sync failure
            if let Some(op) = &status.operation_state {
                if op.phase == OperationPhase::Failed || op.phase == OperationPhase::Error {
                    return Err(ArgoCDError::SyncFailed(op.message.clone()));
                }
            }

            tokio::time::sleep(self.poll_interval).await;
        }
    }

    /// Rollback to a previous revision
    pub async fn rollback(&self, app_name: &str, revision: i64) -> Result<(), ArgoCDError> {
        let url = format!("{}/api/v1/applications/{}/rollback", self.base_url, app_name);

        self.client
            .post(&url)
            .json(&serde_json::json!({
                "id": revision,
                "prune": true
            }))
            .send()
            .await?;

        Ok(())
    }

    /// Get application history (for rollback targets)
    pub async fn get_history(&self, app_name: &str) -> Result<Vec<Revision>, ArgoCDError> {
        let status = self.get_status(app_name).await?;
        // Extract history from status
        Ok(status.history.unwrap_or_default())
    }

    /// Collect detailed error information
    pub async fn collect_errors(&self, app_name: &str) -> Result<DeploymentErrors, ArgoCDError> {
        let status = self.get_status(app_name).await?;

        let mut errors = DeploymentErrors::default();

        // Collect sync errors
        if let Some(op) = status.operation_state {
            if op.phase == OperationPhase::Failed {
                errors.sync_error = Some(op.message);
            }

            if let Some(result) = op.sync_result {
                for resource in result.resources {
                    if resource.status == "SyncFailed" {
                        errors.resource_errors.push(ResourceError {
                            kind: resource.kind,
                            name: resource.name,
                            message: resource.message,
                        });
                    }
                }
            }
        }

        // Collect unhealthy resources
        for resource in status.resources {
            if resource.health_status == HealthStatus::Degraded {
                errors.unhealthy_resources.push(UnhealthyResource {
                    kind: resource.kind,
                    name: resource.name,
                    namespace: resource.namespace,
                    message: resource.health_message,
                });
            }
        }

        Ok(errors)
    }
}

#[derive(Debug, Default)]
pub struct DeploymentErrors {
    pub sync_error: Option<String>,
    pub resource_errors: Vec<ResourceError>,
    pub unhealthy_resources: Vec<UnhealthyResource>,
}

#[derive(Debug)]
pub struct ResourceError {
    pub kind: String,
    pub name: String,
    pub message: String,
}

#[derive(Debug)]
pub struct UnhealthyResource {
    pub kind: String,
    pub name: String,
    pub namespace: String,
    pub message: Option<String>,
}
```

---

## 3. Kubernetes Integration

### Purpose
Collects pod logs, monitors deployment status, and retrieves events for debugging.

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        KUBERNETES INTEGRATION FLOW                                   │
└─────────────────────────────────────────────────────────────────────────────────────┘

    Card in VERIFYING state (ArgoCD synced, checking pods)
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  1. Identify target deployment                                                 │
    │     • card.deployment_namespace                                                │
    │     • card.deployment_name                                                     │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  2. Get deployment status                                                      │
    │     GET /apis/apps/v1/namespaces/{ns}/deployments/{name}                       │
    │                                                                                │
    │     Check:                                                                     │
    │     • spec.replicas == status.readyReplicas                                    │
    │     • status.conditions (Available, Progressing)                               │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────────────────────────────────────────┐
    │  3. Get pods by label selector                                                 │
    │     GET /api/v1/namespaces/{ns}/pods?labelSelector={selector}                  │
    │                                                                                │
    │     For each pod:                                                              │
    │     • Check phase (Running, Pending, Failed)                                   │
    │     • Check container statuses                                                 │
    │     • Detect CrashLoopBackOff, ImagePullBackOff, etc.                          │
    └───────────────────────────────────────────────────────────────────────────────┘
            │
    ┌───────┴───────┐
    │               │
ALL READY      POD ISSUES
    │               │
    ▼               ▼
COMPLETED      ┌───────────────────────────────────────────────────────────────────┐
               │  4. Collect pod logs and events                                    │
               │     GET /api/v1/namespaces/{ns}/pods/{pod}/log?tailLines=100       │
               │     GET /api/v1/namespaces/{ns}/events?fieldSelector=...           │
               │                                                                    │
               │  Common issues to detect:                                          │
               │  • CrashLoopBackOff: Get previous container logs                   │
               │  • ImagePullBackOff: Registry auth or image not found              │
               │  • OOMKilled: Memory limit exceeded                                │
               │  • Pending: Resource constraints or scheduling issues              │
               └───────────────────────────────────────────────────────────────────┘
                       │
                       ▼
               ┌───────────────────────────────────────────────────────────────────┐
               │  5. Store error context and trigger fixing                         │
               │     • Pod logs in errors.context                                   │
               │     • Events in errors.context                                     │
               │     • Card state → ERROR_FIXING                                    │
               └───────────────────────────────────────────────────────────────────┘
```

### Implementation

```rust
// File: crates/integrations/src/kubernetes.rs

use kube::{
    Api, Client,
    api::{ListParams, LogParams},
};
use k8s_openapi::api::{
    apps::v1::Deployment,
    core::v1::{Pod, Event},
};

pub struct KubernetesService {
    client: Client,
}

#[derive(Debug, Clone)]
pub struct DeploymentStatus {
    pub name: String,
    pub namespace: String,
    pub replicas: i32,
    pub ready_replicas: i32,
    pub updated_replicas: i32,
    pub available: bool,
    pub conditions: Vec<DeploymentCondition>,
}

#[derive(Debug, Clone)]
pub struct PodStatus {
    pub name: String,
    pub phase: PodPhase,
    pub container_statuses: Vec<ContainerStatus>,
    pub start_time: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum PodPhase {
    Pending,
    Running,
    Succeeded,
    Failed,
    Unknown,
}

#[derive(Debug, Clone)]
pub struct ContainerStatus {
    pub name: String,
    pub ready: bool,
    pub restart_count: i32,
    pub state: ContainerState,
    pub last_state: Option<ContainerState>,
}

#[derive(Debug, Clone)]
pub enum ContainerState {
    Waiting { reason: String, message: Option<String> },
    Running { started_at: DateTime<Utc> },
    Terminated { exit_code: i32, reason: String, message: Option<String> },
}

impl KubernetesService {
    pub async fn new() -> Result<Self, KubeError> {
        let client = Client::try_default().await?;
        Ok(Self { client })
    }

    /// Get deployment status
    pub async fn get_deployment_status(
        &self,
        namespace: &str,
        name: &str,
    ) -> Result<DeploymentStatus, KubeError> {
        let deployments: Api<Deployment> = Api::namespaced(self.client.clone(), namespace);
        let deployment = deployments.get(name).await?;

        let spec = deployment.spec.ok_or(KubeError::MissingSpec)?;
        let status = deployment.status.ok_or(KubeError::MissingStatus)?;

        Ok(DeploymentStatus {
            name: name.to_string(),
            namespace: namespace.to_string(),
            replicas: spec.replicas.unwrap_or(1),
            ready_replicas: status.ready_replicas.unwrap_or(0),
            updated_replicas: status.updated_replicas.unwrap_or(0),
            available: status.available_replicas.unwrap_or(0) >= spec.replicas.unwrap_or(1),
            conditions: self.map_conditions(status.conditions),
        })
    }

    /// Get pods by label selector
    pub async fn get_pods(
        &self,
        namespace: &str,
        label_selector: &str,
    ) -> Result<Vec<PodStatus>, KubeError> {
        let pods: Api<Pod> = Api::namespaced(self.client.clone(), namespace);
        let list = pods.list(&ListParams::default().labels(label_selector)).await?;

        Ok(list.items.into_iter().map(|p| self.map_pod_status(p)).collect())
    }

    /// Get logs from a pod
    pub async fn get_pod_logs(
        &self,
        namespace: &str,
        pod_name: &str,
        container: Option<&str>,
        tail_lines: i64,
    ) -> Result<String, KubeError> {
        let pods: Api<Pod> = Api::namespaced(self.client.clone(), namespace);

        let mut params = LogParams {
            tail_lines: Some(tail_lines),
            ..Default::default()
        };

        if let Some(c) = container {
            params.container = Some(c.to_string());
        }

        let logs = pods.logs(pod_name, &params).await?;
        Ok(logs)
    }

    /// Get previous container logs (for CrashLoopBackOff)
    pub async fn get_previous_logs(
        &self,
        namespace: &str,
        pod_name: &str,
        container: &str,
    ) -> Result<String, KubeError> {
        let pods: Api<Pod> = Api::namespaced(self.client.clone(), namespace);

        let params = LogParams {
            previous: true,
            container: Some(container.to_string()),
            tail_lines: Some(100),
            ..Default::default()
        };

        let logs = pods.logs(pod_name, &params).await?;
        Ok(logs)
    }

    /// Get events for a resource
    pub async fn get_events(
        &self,
        namespace: &str,
        resource_name: &str,
    ) -> Result<Vec<KubeEvent>, KubeError> {
        let events: Api<Event> = Api::namespaced(self.client.clone(), namespace);

        let field_selector = format!("involvedObject.name={}", resource_name);
        let list = events.list(&ListParams::default().fields(&field_selector)).await?;

        Ok(list.items.into_iter().map(|e| KubeEvent {
            reason: e.reason.unwrap_or_default(),
            message: e.message.unwrap_or_default(),
            event_type: e.type_.unwrap_or_default(),
            count: e.count.unwrap_or(1),
            first_timestamp: e.first_timestamp,
            last_timestamp: e.last_timestamp,
        }).collect())
    }

    /// Collect all error context for a deployment
    pub async fn collect_deployment_errors(
        &self,
        namespace: &str,
        deployment_name: &str,
    ) -> Result<DeploymentErrorContext, KubeError> {
        let mut context = DeploymentErrorContext::default();

        // Get deployment status
        let deployment = self.get_deployment_status(namespace, deployment_name).await?;
        context.deployment_status = Some(deployment.clone());

        // Get pods
        let label_selector = format!("app={}", deployment_name);  // Common pattern
        let pods = self.get_pods(namespace, &label_selector).await?;

        for pod in pods {
            // Check for issues
            for container in &pod.container_statuses {
                match &container.state {
                    ContainerState::Waiting { reason, message } => {
                        if reason == "CrashLoopBackOff" || reason == "ImagePullBackOff" {
                            // Get logs
                            let logs = if reason == "CrashLoopBackOff" {
                                self.get_previous_logs(namespace, &pod.name, &container.name).await.ok()
                            } else {
                                None
                            };

                            context.container_issues.push(ContainerIssue {
                                pod_name: pod.name.clone(),
                                container_name: container.name.clone(),
                                reason: reason.clone(),
                                message: message.clone(),
                                logs,
                            });
                        }
                    }
                    ContainerState::Terminated { exit_code, reason, message } if *exit_code != 0 => {
                        let logs = self.get_pod_logs(namespace, &pod.name, Some(&container.name), 100).await.ok();

                        context.container_issues.push(ContainerIssue {
                            pod_name: pod.name.clone(),
                            container_name: container.name.clone(),
                            reason: format!("Terminated: {} (exit code {})", reason, exit_code),
                            message: message.clone(),
                            logs,
                        });
                    }
                    _ => {}
                }
            }

            // Get pod events
            let events = self.get_events(namespace, &pod.name).await?;
            for event in events {
                if event.event_type == "Warning" {
                    context.warning_events.push(event);
                }
            }
        }

        Ok(context)
    }
}

#[derive(Debug, Default)]
pub struct DeploymentErrorContext {
    pub deployment_status: Option<DeploymentStatus>,
    pub container_issues: Vec<ContainerIssue>,
    pub warning_events: Vec<KubeEvent>,
}

#[derive(Debug)]
pub struct ContainerIssue {
    pub pod_name: String,
    pub container_name: String,
    pub reason: String,
    pub message: Option<String>,
    pub logs: Option<String>,
}

#[derive(Debug)]
pub struct KubeEvent {
    pub reason: String,
    pub message: String,
    pub event_type: String,
    pub count: i32,
    pub first_timestamp: Option<Time>,
    pub last_timestamp: Option<Time>,
}
```

---

## 4. Docker Hub Integration

### Purpose
Monitors container image availability and version tags.

```rust
// File: crates/integrations/src/dockerhub.rs

pub struct DockerHubService {
    client: Client,
    auth_token: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ImageTag {
    pub name: String,
    pub digest: String,
    pub last_updated: DateTime<Utc>,
    pub size: u64,
}

impl DockerHubService {
    /// Get tags for an image
    pub async fn get_tags(&self, image: &str) -> Result<Vec<ImageTag>, DockerHubError> {
        let (namespace, repo) = self.parse_image(image)?;
        let url = format!(
            "https://hub.docker.com/v2/repositories/{}/{}/tags",
            namespace, repo
        );

        let response = self.client.get(&url).send().await?.json::<TagsResponse>().await?;
        Ok(response.results)
    }

    /// Check if a specific tag exists
    pub async fn tag_exists(&self, image: &str, tag: &str) -> Result<bool, DockerHubError> {
        let tags = self.get_tags(image).await?;
        Ok(tags.iter().any(|t| t.name == tag))
    }

    /// Get the latest semver tag
    pub async fn get_latest_semver(&self, image: &str) -> Result<Option<String>, DockerHubError> {
        let tags = self.get_tags(image).await?;

        let semver_tags: Vec<_> = tags
            .iter()
            .filter_map(|t| semver::Version::parse(&t.name).ok().map(|v| (v, &t.name)))
            .collect();

        Ok(semver_tags.into_iter().max_by_key(|(v, _)| v.clone()).map(|(_, n)| n.clone()))
    }
}
```

---

## 5. Git Operations Integration

### Purpose
Manages git worktrees, branches, commits, and merges for card isolation.

```rust
// File: crates/integrations/src/git.rs

use git2::{Repository, Signature, Worktree};

pub struct GitService {
    repo_path: PathBuf,
    worktrees_dir: PathBuf,
}

impl GitService {
    /// Create a worktree for a card
    pub async fn create_worktree(&self, card_id: Uuid, branch_name: &str) -> Result<PathBuf, GitError> {
        let repo = Repository::open(&self.repo_path)?;

        // Create branch if not exists
        let head = repo.head()?.peel_to_commit()?;
        repo.branch(branch_name, &head, false)?;

        // Create worktree
        let worktree_path = self.worktrees_dir.join(format!("card-{}", card_id));
        repo.worktree(
            &format!("card-{}", card_id),
            &worktree_path,
            Some(&mut git2::WorktreeAddOptions::new().reference(Some(branch_name))),
        )?;

        Ok(worktree_path)
    }

    /// Commit changes in a worktree
    pub async fn commit(&self, worktree_path: &Path, message: &str) -> Result<String, GitError> {
        let repo = Repository::open(worktree_path)?;

        let mut index = repo.index()?;
        index.add_all(["*"].iter(), git2::IndexAddOption::DEFAULT, None)?;
        index.write()?;

        let tree_id = index.write_tree()?;
        let tree = repo.find_tree(tree_id)?;
        let parent = repo.head()?.peel_to_commit()?;

        let sig = Signature::now("Ringmaster", "ringmaster@localhost")?;
        let commit_id = repo.commit(
            Some("HEAD"),
            &sig,
            &sig,
            message,
            &tree,
            &[&parent],
        )?;

        Ok(commit_id.to_string())
    }

    /// Merge worktree branch back to main
    pub async fn merge_to_main(&self, card_id: Uuid) -> Result<(), GitError> {
        let repo = Repository::open(&self.repo_path)?;
        let branch_name = format!("card-{}", card_id);

        // Checkout main
        let main = repo.find_branch("main", git2::BranchType::Local)?;
        repo.checkout_tree(main.get().peel_to_tree()?.as_object(), None)?;
        repo.set_head("refs/heads/main")?;

        // Merge card branch
        let card_branch = repo.find_branch(&branch_name, git2::BranchType::Local)?;
        let annotated = repo.reference_to_annotated_commit(card_branch.get())?;
        repo.merge(&[&annotated], None, None)?;

        // Commit merge
        self.commit(&self.repo_path, &format!("Merge {} into main", branch_name)).await?;

        // Cleanup worktree
        self.remove_worktree(card_id).await?;

        Ok(())
    }

    /// Remove a worktree
    pub async fn remove_worktree(&self, card_id: Uuid) -> Result<(), GitError> {
        let repo = Repository::open(&self.repo_path)?;
        let worktree_path = self.worktrees_dir.join(format!("card-{}", card_id));

        // Prune worktree
        let worktree = repo.find_worktree(&format!("card-{}", card_id))?;
        worktree.prune(None)?;

        // Remove directory
        std::fs::remove_dir_all(worktree_path)?;

        Ok(())
    }
}
```

---

## Integration Hub

The Integration Hub coordinates all services:

```rust
// File: crates/integrations/src/hub.rs

pub struct IntegrationHub {
    github: Arc<GitHubActionsService>,
    argocd: Arc<ArgoCDService>,
    kubernetes: Arc<KubernetesService>,
    dockerhub: Arc<DockerHubService>,
    git: Arc<GitService>,
    event_bus: Arc<EventBus>,
}

impl IntegrationHub {
    /// Monitor a card through its lifecycle
    pub async fn monitor_card(&self, card: &Card) -> Result<(), IntegrationError> {
        match card.state {
            CardState::Building => {
                self.monitor_build(card).await?;
            }
            CardState::Deploying | CardState::Verifying => {
                self.monitor_deployment(card).await?;
            }
            _ => {}
        }
        Ok(())
    }

    async fn monitor_build(&self, card: &Card) -> Result<(), IntegrationError> {
        let run = self.github.get_latest_run(&card.branch_name).await?;

        if let Some(run) = run {
            match run.conclusion {
                Some(WorkflowConclusion::Success) => {
                    self.event_bus.publish(Event::BuildCompleted {
                        card_id: card.id,
                        success: true,
                    }).await;
                }
                Some(WorkflowConclusion::Failure) => {
                    let logs = self.github.get_logs(run.id).await?;
                    let failed_steps = self.github.get_failed_steps(run.id).await?;

                    self.event_bus.publish(Event::BuildFailed {
                        card_id: card.id,
                        logs,
                        failed_steps,
                    }).await;
                }
                _ => {}
            }
        }

        Ok(())
    }

    async fn monitor_deployment(&self, card: &Card) -> Result<(), IntegrationError> {
        // Check ArgoCD status
        let status = self.argocd.get_status(&card.argocd_app_name).await?;

        if status.sync_status == SyncStatus::Synced {
            // Check Kubernetes pods
            let errors = self.kubernetes
                .collect_deployment_errors(&card.deployment_namespace, &card.deployment_name)
                .await?;

            if errors.container_issues.is_empty() && status.health_status == HealthStatus::Healthy {
                self.event_bus.publish(Event::DeploymentCompleted {
                    card_id: card.id,
                    success: true,
                }).await;
            } else {
                self.event_bus.publish(Event::DeploymentFailed {
                    card_id: card.id,
                    argocd_errors: self.argocd.collect_errors(&card.argocd_app_name).await?,
                    k8s_errors: errors,
                }).await;
            }
        }

        Ok(())
    }
}
```

## Configuration

```toml
# config.toml

[integrations.github]
# Personal access token (or use GITHUB_TOKEN env)
token = "${GITHUB_TOKEN}"
# Default poll interval
poll_interval_seconds = 10
# Timeout for workflow completion
workflow_timeout_seconds = 1800

[integrations.argocd]
# argocd-proxy URL
proxy_url = "http://argocd-proxy.argocd.svc.cluster.local"
# Poll interval for sync status
poll_interval_seconds = 5
# Timeout for sync completion
sync_timeout_seconds = 600

[integrations.kubernetes]
# Uses default kubeconfig or in-cluster config
# Optional: explicit kubeconfig path
kubeconfig_path = ""
# Default log tail lines
default_tail_lines = 100

[integrations.dockerhub]
# Optional auth for rate limiting
username = ""
token = ""

[integrations.git]
# Base repository path
repo_path = "/home/coder/project"
# Worktrees directory
worktrees_dir = "/home/coder/.ringmaster/worktrees"
# Default commit author
author_name = "Ringmaster"
author_email = "ringmaster@localhost"
```
