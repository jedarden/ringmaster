//! Kubernetes integration for pod monitoring and log collection
//!
//! This module provides functionality to:
//! - Monitor deployment status
//! - Collect pod logs for error diagnosis
//! - Check pod health and events

use k8s_openapi::api::{
    apps::v1::Deployment,
    core::v1::{Event, Pod},
};
use kube::{
    api::{Api, ListParams, LogParams},
    Client,
};
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum KubeError {
    #[error("Kubernetes client error: {0}")]
    ClientError(#[from] kube::Error),

    #[error("Resource not found: {0}")]
    NotFound(String),

    #[error("Missing spec or status")]
    MissingField,
}

/// Deployment status information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeploymentStatus {
    pub name: String,
    pub namespace: String,
    pub replicas: i32,
    pub ready_replicas: i32,
    pub updated_replicas: i32,
    pub available: bool,
    pub conditions: Vec<DeploymentCondition>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeploymentCondition {
    pub condition_type: String,
    pub status: String,
    pub reason: Option<String>,
    pub message: Option<String>,
}

/// Pod status information
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PodStatus {
    pub name: String,
    pub namespace: String,
    pub phase: String,
    pub container_statuses: Vec<ContainerStatus>,
    pub start_time: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContainerStatus {
    pub name: String,
    pub ready: bool,
    pub restart_count: i32,
    pub state: ContainerState,
    pub last_state: Option<ContainerState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum ContainerState {
    Waiting {
        reason: String,
        message: Option<String>,
    },
    Running {
        started_at: String,
    },
    Terminated {
        exit_code: i32,
        reason: String,
        message: Option<String>,
    },
    Unknown,
}

/// Kubernetes event
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct KubeEvent {
    pub reason: String,
    pub message: String,
    pub event_type: String,
    pub count: i32,
    pub first_timestamp: Option<String>,
    pub last_timestamp: Option<String>,
}

/// Container issue detected during monitoring
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ContainerIssue {
    pub pod_name: String,
    pub container_name: String,
    pub reason: String,
    pub message: Option<String>,
    pub logs: Option<String>,
}

/// Error context collected from a failed deployment
#[derive(Debug, Default, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeploymentErrorContext {
    pub deployment_status: Option<DeploymentStatus>,
    pub container_issues: Vec<ContainerIssue>,
    pub warning_events: Vec<KubeEvent>,
}

/// Kubernetes service for monitoring deployments and collecting logs
pub struct KubernetesService {
    client: Client,
}

impl KubernetesService {
    /// Create a new Kubernetes service using default config
    pub async fn new() -> Result<Self, KubeError> {
        let client = Client::try_default().await?;
        Ok(Self { client })
    }

    /// Create with an existing client
    pub fn with_client(client: Client) -> Self {
        Self { client }
    }

    /// Get deployment status
    pub async fn get_deployment_status(
        &self,
        namespace: &str,
        name: &str,
    ) -> Result<DeploymentStatus, KubeError> {
        let deployments: Api<Deployment> = Api::namespaced(self.client.clone(), namespace);
        let deployment = deployments.get(name).await?;

        let spec = deployment.spec.ok_or(KubeError::MissingField)?;
        let status = deployment.status.ok_or(KubeError::MissingField)?;

        let conditions = status
            .conditions
            .unwrap_or_default()
            .into_iter()
            .map(|c| DeploymentCondition {
                condition_type: c.type_,
                status: c.status,
                reason: c.reason,
                message: c.message,
            })
            .collect();

        Ok(DeploymentStatus {
            name: name.to_string(),
            namespace: namespace.to_string(),
            replicas: spec.replicas.unwrap_or(1),
            ready_replicas: status.ready_replicas.unwrap_or(0),
            updated_replicas: status.updated_replicas.unwrap_or(0),
            available: status.available_replicas.unwrap_or(0) >= spec.replicas.unwrap_or(1),
            conditions,
        })
    }

    /// Get pods by label selector
    pub async fn get_pods(
        &self,
        namespace: &str,
        label_selector: &str,
    ) -> Result<Vec<PodStatus>, KubeError> {
        let pods: Api<Pod> = Api::namespaced(self.client.clone(), namespace);
        let list = pods
            .list(&ListParams::default().labels(label_selector))
            .await?;

        Ok(list
            .items
            .into_iter()
            .map(|p| self.map_pod_status(p))
            .collect())
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
        let list = events
            .list(&ListParams::default().fields(&field_selector))
            .await?;

        Ok(list
            .items
            .into_iter()
            .map(|e| KubeEvent {
                reason: e.reason.unwrap_or_default(),
                message: e.message.unwrap_or_default(),
                event_type: e.type_.unwrap_or_default(),
                count: e.count.unwrap_or(1),
                first_timestamp: e.first_timestamp.map(|t| t.0.to_rfc3339()),
                last_timestamp: e.last_timestamp.map(|t| t.0.to_rfc3339()),
            })
            .collect())
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
        context.deployment_status = Some(deployment);

        // Get pods - try common label selectors
        let label_selector = format!("app={}", deployment_name);
        let pods = self.get_pods(namespace, &label_selector).await?;

        for pod in pods {
            // Check for issues in containers
            for container in &pod.container_statuses {
                match &container.state {
                    ContainerState::Waiting { reason, message } => {
                        if reason == "CrashLoopBackOff" || reason == "ImagePullBackOff" {
                            let logs = if reason == "CrashLoopBackOff" {
                                self.get_previous_logs(namespace, &pod.name, &container.name)
                                    .await
                                    .ok()
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
                    ContainerState::Terminated {
                        exit_code,
                        reason,
                        message,
                    } if *exit_code != 0 => {
                        let logs = self
                            .get_pod_logs(namespace, &pod.name, Some(&container.name), 100)
                            .await
                            .ok();

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

            // Get warning events for the pod
            if let Ok(events) = self.get_events(namespace, &pod.name).await {
                for event in events {
                    if event.event_type == "Warning" {
                        context.warning_events.push(event);
                    }
                }
            }
        }

        Ok(context)
    }

    /// Map a k8s Pod to our PodStatus
    fn map_pod_status(&self, pod: Pod) -> PodStatus {
        let meta = pod.metadata;
        let status = pod.status.unwrap_or_default();

        let container_statuses = status
            .container_statuses
            .unwrap_or_default()
            .into_iter()
            .map(|cs| {
                let state = if let Some(waiting) = cs.state.as_ref().and_then(|s| s.waiting.as_ref())
                {
                    ContainerState::Waiting {
                        reason: waiting.reason.clone().unwrap_or_default(),
                        message: waiting.message.clone(),
                    }
                } else if let Some(running) =
                    cs.state.as_ref().and_then(|s| s.running.as_ref())
                {
                    ContainerState::Running {
                        started_at: running
                            .started_at
                            .as_ref()
                            .map(|t| t.0.to_rfc3339())
                            .unwrap_or_default(),
                    }
                } else if let Some(terminated) =
                    cs.state.as_ref().and_then(|s| s.terminated.as_ref())
                {
                    ContainerState::Terminated {
                        exit_code: terminated.exit_code,
                        reason: terminated.reason.clone().unwrap_or_default(),
                        message: terminated.message.clone(),
                    }
                } else {
                    ContainerState::Unknown
                };

                let last_state = cs.last_state.and_then(|ls| {
                    if let Some(terminated) = ls.terminated {
                        Some(ContainerState::Terminated {
                            exit_code: terminated.exit_code,
                            reason: terminated.reason.unwrap_or_default(),
                            message: terminated.message,
                        })
                    } else {
                        None
                    }
                });

                ContainerStatus {
                    name: cs.name,
                    ready: cs.ready,
                    restart_count: cs.restart_count,
                    state,
                    last_state,
                }
            })
            .collect();

        PodStatus {
            name: meta.name.unwrap_or_default(),
            namespace: meta.namespace.unwrap_or_default(),
            phase: status.phase.unwrap_or_default(),
            container_statuses,
            start_time: status.start_time.map(|t| t.0.to_rfc3339()),
        }
    }

    /// Check if a deployment is healthy (all pods running)
    pub async fn is_deployment_healthy(
        &self,
        namespace: &str,
        deployment_name: &str,
    ) -> Result<bool, KubeError> {
        let status = self.get_deployment_status(namespace, deployment_name).await?;
        Ok(status.available && status.ready_replicas >= status.replicas)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_container_state_serialization() {
        let state = ContainerState::Waiting {
            reason: "ImagePullBackOff".to_string(),
            message: Some("pull access denied".to_string()),
        };

        let json = serde_json::to_string(&state).unwrap();
        assert!(json.contains("ImagePullBackOff"));
    }

    #[test]
    fn test_deployment_error_context_default() {
        let ctx = DeploymentErrorContext::default();
        assert!(ctx.container_issues.is_empty());
        assert!(ctx.warning_events.is_empty());
    }
}
