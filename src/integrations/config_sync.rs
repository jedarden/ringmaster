//! Configuration sync service for syncing CLAUDE.md, skills, and patterns from a config repository.
//!
//! When a loop starts, Ringmaster can sync configuration files from a specified git repository:
//! - `CLAUDE.md` → Copied to worktree root
//! - `skills/` → Copied to `.claude/skills/`
//! - `patterns.json` → Applied to session configuration

use std::path::{Path, PathBuf};
use thiserror::Error;

use crate::config::{get_data_dir, ConfigSyncConfig};

/// Error type for config sync operations
#[derive(Error, Debug)]
pub enum ConfigSyncError {
    #[error("Git operation failed: {0}")]
    GitError(String),

    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),

    #[error("Config repository not configured")]
    NotConfigured,

    #[error("Invalid config repository URL: {0}")]
    InvalidUrl(String),
}

/// Result of a config sync operation
#[derive(Debug, Clone)]
pub struct SyncResult {
    /// Whether CLAUDE.md was synced
    pub claude_md_synced: bool,
    /// Number of skills synced
    pub skills_synced: usize,
    /// Whether patterns.json was synced
    pub patterns_synced: bool,
    /// Path to the cached config repo
    pub cache_path: PathBuf,
}

/// Configuration sync service
pub struct ConfigSyncService {
    config: ConfigSyncConfig,
    cache_dir: PathBuf,
}

impl ConfigSyncService {
    /// Create a new config sync service
    pub fn new(config: ConfigSyncConfig) -> Self {
        let cache_dir = config
            .cache_path
            .as_ref()
            .map(PathBuf::from)
            .unwrap_or_else(|| get_data_dir().join("config-repos"));

        Self { config, cache_dir }
    }

    /// Check if config sync is configured
    pub fn is_configured(&self) -> bool {
        self.config.repository_url.is_some()
    }

    /// Get the local cache path for the config repository
    fn get_repo_cache_path(&self) -> Result<PathBuf, ConfigSyncError> {
        let url = self
            .config
            .repository_url
            .as_ref()
            .ok_or(ConfigSyncError::NotConfigured)?;

        // Extract repo name from URL for cache path
        let repo_name = extract_repo_name(url)?;
        Ok(self.cache_dir.join(repo_name))
    }

    /// Clone or update the config repository
    pub fn update_cache(&self) -> Result<PathBuf, ConfigSyncError> {
        let url = self
            .config
            .repository_url
            .as_ref()
            .ok_or(ConfigSyncError::NotConfigured)?;

        let cache_path = self.get_repo_cache_path()?;

        // Create cache directory if needed
        std::fs::create_dir_all(&self.cache_dir)?;

        if cache_path.exists() {
            // Pull latest changes
            self.pull_repo(&cache_path)?;
        } else {
            // Clone the repository
            self.clone_repo(url, &cache_path)?;
        }

        // Checkout the configured branch
        self.checkout_branch(&cache_path, &self.config.branch)?;

        Ok(cache_path)
    }

    /// Clone a repository to the cache
    fn clone_repo(&self, url: &str, dest: &Path) -> Result<(), ConfigSyncError> {
        let mut builder = git2::build::RepoBuilder::new();

        // Try with default credentials
        let mut fetch_opts = git2::FetchOptions::new();
        let mut callbacks = git2::RemoteCallbacks::new();

        // Handle SSH authentication
        callbacks.credentials(|_url, username_from_url, _allowed_types| {
            git2::Cred::ssh_key_from_agent(username_from_url.unwrap_or("git"))
        });

        fetch_opts.remote_callbacks(callbacks);
        builder.fetch_options(fetch_opts);

        builder
            .clone(url, dest)
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to clone {}: {}", url, e)))?;

        tracing::info!("Cloned config repository to {:?}", dest);
        Ok(())
    }

    /// Pull latest changes in the repository
    fn pull_repo(&self, repo_path: &Path) -> Result<(), ConfigSyncError> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to open repo: {}", e)))?;

        // Fetch from origin
        let mut remote = repo
            .find_remote("origin")
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to find remote: {}", e)))?;

        let mut callbacks = git2::RemoteCallbacks::new();
        callbacks.credentials(|_url, username_from_url, _allowed_types| {
            git2::Cred::ssh_key_from_agent(username_from_url.unwrap_or("git"))
        });

        let mut fetch_opts = git2::FetchOptions::new();
        fetch_opts.remote_callbacks(callbacks);

        remote
            .fetch(&[&self.config.branch], Some(&mut fetch_opts), None)
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to fetch: {}", e)))?;

        tracing::debug!("Fetched updates for config repository at {:?}", repo_path);
        Ok(())
    }

    /// Checkout a specific branch
    fn checkout_branch(&self, repo_path: &Path, branch: &str) -> Result<(), ConfigSyncError> {
        let repo = git2::Repository::open(repo_path)
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to open repo: {}", e)))?;

        // Find the remote branch
        let remote_ref = format!("refs/remotes/origin/{}", branch);
        let reference = repo.find_reference(&remote_ref).map_err(|e| {
            ConfigSyncError::GitError(format!("Failed to find branch {}: {}", branch, e))
        })?;

        let commit = reference.peel_to_commit().map_err(|e| {
            ConfigSyncError::GitError(format!("Failed to peel to commit: {}", e))
        })?;

        // Reset to the commit (hard reset to get clean state)
        repo.reset(commit.as_object(), git2::ResetType::Hard, None)
            .map_err(|e| ConfigSyncError::GitError(format!("Failed to reset: {}", e)))?;

        tracing::debug!("Checked out branch {} in config repository", branch);
        Ok(())
    }

    /// Sync configuration files to a worktree
    pub fn sync_to_worktree(&self, worktree_path: &Path) -> Result<SyncResult, ConfigSyncError> {
        if !self.is_configured() {
            return Err(ConfigSyncError::NotConfigured);
        }

        // Update the cache first
        let cache_path = self.update_cache()?;

        let mut result = SyncResult {
            claude_md_synced: false,
            skills_synced: 0,
            patterns_synced: false,
            cache_path: cache_path.clone(),
        };

        // Sync CLAUDE.md
        let claude_md_src = cache_path.join("CLAUDE.md");
        if claude_md_src.exists() {
            let claude_md_dest = worktree_path.join("CLAUDE.md");
            std::fs::copy(&claude_md_src, &claude_md_dest)?;
            result.claude_md_synced = true;
            tracing::info!("Synced CLAUDE.md to {:?}", claude_md_dest);
        }

        // Sync skills directory
        let skills_src = cache_path.join("skills");
        if skills_src.exists() && skills_src.is_dir() {
            let skills_dest = worktree_path.join(".claude").join("skills");
            std::fs::create_dir_all(&skills_dest)?;
            result.skills_synced = copy_dir_contents(&skills_src, &skills_dest)?;
            tracing::info!("Synced {} skills to {:?}", result.skills_synced, skills_dest);
        }

        // Sync patterns.json
        let patterns_src = cache_path.join("patterns.json");
        if patterns_src.exists() {
            let patterns_dest = worktree_path.join(".claude").join("patterns.json");
            std::fs::create_dir_all(patterns_dest.parent().unwrap())?;
            std::fs::copy(&patterns_src, &patterns_dest)?;
            result.patterns_synced = true;
            tracing::info!("Synced patterns.json to {:?}", patterns_dest);
        }

        Ok(result)
    }

    /// Get the current sync status
    pub fn get_status(&self) -> Result<ConfigSyncStatus, ConfigSyncError> {
        if !self.is_configured() {
            return Ok(ConfigSyncStatus {
                configured: false,
                repository_url: None,
                branch: self.config.branch.clone(),
                cached: false,
                last_commit: None,
            });
        }

        let cache_path = self.get_repo_cache_path()?;
        let cached = cache_path.exists();
        let last_commit = if cached {
            get_head_commit(&cache_path).ok()
        } else {
            None
        };

        Ok(ConfigSyncStatus {
            configured: true,
            repository_url: self.config.repository_url.clone(),
            branch: self.config.branch.clone(),
            cached,
            last_commit,
        })
    }
}

/// Status of the config sync service
#[derive(Debug, Clone, serde::Serialize)]
pub struct ConfigSyncStatus {
    pub configured: bool,
    pub repository_url: Option<String>,
    pub branch: String,
    pub cached: bool,
    pub last_commit: Option<String>,
}

/// Extract repository name from URL
fn extract_repo_name(url: &str) -> Result<String, ConfigSyncError> {
    let url = url.trim_end_matches(".git");

    // Try different URL formats
    if let Some(rest) = url.strip_prefix("https://github.com/") {
        let parts: Vec<&str> = rest.split('/').collect();
        if parts.len() >= 2 {
            return Ok(format!("{}_{}", parts[0], parts[1]));
        }
    }

    if let Some(rest) = url.strip_prefix("git@github.com:") {
        let parts: Vec<&str> = rest.split('/').collect();
        if parts.len() >= 2 {
            return Ok(format!("{}_{}", parts[0], parts[1]));
        }
    }

    // Fallback: use hash of URL
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    let mut hasher = DefaultHasher::new();
    url.hash(&mut hasher);
    Ok(format!("repo_{:x}", hasher.finish()))
}

/// Copy directory contents recursively
fn copy_dir_contents(src: &Path, dest: &Path) -> Result<usize, std::io::Error> {
    let mut count = 0;

    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let path = entry.path();
        let dest_path = dest.join(entry.file_name());

        if path.is_dir() {
            std::fs::create_dir_all(&dest_path)?;
            count += copy_dir_contents(&path, &dest_path)?;
        } else {
            std::fs::copy(&path, &dest_path)?;
            count += 1;
        }
    }

    Ok(count)
}

/// Get the HEAD commit SHA
fn get_head_commit(repo_path: &Path) -> Result<String, ConfigSyncError> {
    let repo = git2::Repository::open(repo_path)
        .map_err(|e| ConfigSyncError::GitError(format!("Failed to open repo: {}", e)))?;

    let head = repo
        .head()
        .map_err(|e| ConfigSyncError::GitError(format!("Failed to get HEAD: {}", e)))?;

    let commit = head
        .peel_to_commit()
        .map_err(|e| ConfigSyncError::GitError(format!("Failed to peel to commit: {}", e)))?;

    Ok(commit.id().to_string()[..8].to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_repo_name_https() {
        let name = extract_repo_name("https://github.com/owner/repo").unwrap();
        assert_eq!(name, "owner_repo");
    }

    #[test]
    fn test_extract_repo_name_https_with_git() {
        let name = extract_repo_name("https://github.com/owner/repo.git").unwrap();
        assert_eq!(name, "owner_repo");
    }

    #[test]
    fn test_extract_repo_name_ssh() {
        let name = extract_repo_name("git@github.com:owner/repo.git").unwrap();
        assert_eq!(name, "owner_repo");
    }

    #[test]
    fn test_extract_repo_name_fallback() {
        let name = extract_repo_name("https://other.host/some/path").unwrap();
        assert!(name.starts_with("repo_"));
    }

    #[test]
    fn test_not_configured() {
        let config = ConfigSyncConfig::default();
        let service = ConfigSyncService::new(config);
        assert!(!service.is_configured());
    }

    #[test]
    fn test_configured() {
        let config = ConfigSyncConfig {
            repository_url: Some("https://github.com/org/config".to_string()),
            ..Default::default()
        };
        let service = ConfigSyncService::new(config);
        assert!(service.is_configured());
    }
}
