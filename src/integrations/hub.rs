//! Integration Hub - unified coordination of all external services
//!
//! This module provides a centralized hub for managing integration clients
//! with proper lifecycle management and configuration.

use std::sync::Arc;

use super::argocd::ArgoCDClient;
use super::dockerhub::DockerHubClient;
use super::github::GitHubClient;
use super::kubernetes::KubernetesService;
use crate::config::{Config, load_config};

/// Integration Hub coordinates all external service clients
pub struct IntegrationHub {
    /// GitHub Actions client (always available)
    github: Arc<GitHubClient>,
    /// ArgoCD client (optional, requires ARGOCD_SERVER)
    argocd: Option<Arc<ArgoCDClient>>,
    /// Kubernetes client (optional, requires cluster access)
    kubernetes: Option<Arc<KubernetesService>>,
    /// Docker Hub client (always available)
    dockerhub: Arc<DockerHubClient>,
}

impl IntegrationHub {
    /// Create a new integration hub from configuration
    pub fn new() -> Self {
        let config = load_config();
        Self::from_config(&config)
    }

    /// Create a new integration hub from explicit configuration
    pub fn from_config(config: &Config) -> Self {
        // GitHub client
        let github_token = config
            .integrations
            .github
            .as_ref()
            .and_then(|g| g.token.clone())
            .or_else(|| std::env::var("GITHUB_TOKEN").ok());

        let mut github = GitHubClient::new(github_token);

        if let Some(api_url) = config
            .integrations
            .github
            .as_ref()
            .and_then(|g| g.api_url.clone())
        {
            github = github.with_api_url(api_url);
        }

        // ArgoCD client (optional)
        let argocd = config
            .integrations
            .argocd
            .as_ref()
            .map(|a| {
                Arc::new(ArgoCDClient::new(&a.server_url, a.token.clone()))
            })
            .or_else(|| {
                std::env::var("ARGOCD_SERVER")
                    .ok()
                    .map(|server| Arc::new(ArgoCDClient::new(server, None)))
            });

        // Kubernetes service (optional - will fail gracefully if not available)
        let kubernetes = Self::try_create_kubernetes_service();

        // Docker Hub client
        let dockerhub = DockerHubClient::new();

        Self {
            github: Arc::new(github),
            argocd,
            kubernetes,
            dockerhub: Arc::new(dockerhub),
        }
    }

    /// Try to create a Kubernetes service (returns None if not available)
    fn try_create_kubernetes_service() -> Option<Arc<KubernetesService>> {
        // Try to create the service - it will fail if no cluster access
        match KubernetesService::try_new() {
            Ok(service) => Some(Arc::new(service)),
            Err(e) => {
                tracing::debug!("Kubernetes service not available: {}", e);
                None
            }
        }
    }

    /// Get the GitHub client
    pub fn github(&self) -> &GitHubClient {
        &self.github
    }

    /// Get the ArgoCD client (if available)
    pub fn argocd(&self) -> Option<&ArgoCDClient> {
        self.argocd.as_ref().map(|a| a.as_ref())
    }

    /// Get the Kubernetes service (if available)
    pub fn kubernetes(&self) -> Option<&KubernetesService> {
        self.kubernetes.as_ref().map(|k| k.as_ref())
    }

    /// Get the Docker Hub client
    pub fn dockerhub(&self) -> &DockerHubClient {
        &self.dockerhub
    }

    /// Check if ArgoCD is configured
    pub fn has_argocd(&self) -> bool {
        self.argocd.is_some()
    }

    /// Check if Kubernetes is available
    pub fn has_kubernetes(&self) -> bool {
        self.kubernetes.is_some()
    }

    /// Get a summary of available integrations
    pub fn status(&self) -> IntegrationStatus {
        IntegrationStatus {
            github: true,
            argocd: self.argocd.is_some(),
            kubernetes: self.kubernetes.is_some(),
            dockerhub: true,
        }
    }
}

impl Default for IntegrationHub {
    fn default() -> Self {
        Self::new()
    }
}

/// Status of available integrations
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IntegrationStatus {
    pub github: bool,
    pub argocd: bool,
    pub kubernetes: bool,
    pub dockerhub: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hub_creation() {
        let hub = IntegrationHub::new();
        // GitHub and Docker Hub should always be available
        let _ = hub.github();
        let _ = hub.dockerhub();
    }

    #[test]
    fn test_hub_status() {
        let hub = IntegrationHub::new();
        let status = hub.status();
        // GitHub and Docker Hub are always true
        assert!(status.github);
        assert!(status.dockerhub);
        // ArgoCD and Kubernetes depend on environment
    }

    #[test]
    fn test_default_hub() {
        let hub = IntegrationHub::default();
        let status = hub.status();
        assert!(status.github);
        assert!(status.dockerhub);
    }
}
