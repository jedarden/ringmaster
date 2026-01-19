//! Configuration module for Ringmaster

use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Main configuration structure
#[derive(Debug, Clone, Serialize, Deserialize)]
#[derive(Default)]
pub struct Config {
    /// Server configuration
    #[serde(default)]
    pub server: ServerConfig,

    /// Database configuration
    #[serde(default)]
    pub database: DatabaseConfig,

    /// State machine configuration
    #[serde(default)]
    pub state_machine: StateMachineConfig,

    /// Loop manager configuration
    #[serde(default)]
    pub loop_manager: LoopManagerConfig,

    /// Integration configuration
    #[serde(default)]
    pub integrations: IntegrationsConfig,
}


/// Server configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerConfig {
    /// Host to bind to
    #[serde(default = "default_host")]
    pub host: String,

    /// Port to listen on
    #[serde(default = "default_port")]
    pub port: u16,

    /// Enable CORS
    #[serde(default = "default_true")]
    pub cors_enabled: bool,
}

fn default_host() -> String {
    "127.0.0.1".to_string()
}

fn default_port() -> u16 {
    8080
}

fn default_true() -> bool {
    true
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: default_host(),
            port: default_port(),
            cors_enabled: true,
        }
    }
}

/// Database configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[derive(Default)]
pub struct DatabaseConfig {
    /// Path to SQLite database
    pub path: Option<String>,
}


impl DatabaseConfig {
    pub fn get_path(&self) -> PathBuf {
        if let Some(path) = &self.path {
            PathBuf::from(path)
        } else {
            get_data_dir().join("data.db")
        }
    }
}

/// State machine configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateMachineConfig {
    /// Maximum retries before failing
    #[serde(default = "default_max_retries")]
    pub max_retries: i32,

    /// Timeout for each phase in seconds
    #[serde(default)]
    pub timeouts: PhaseTimeouts,

    /// Auto-transition settings
    #[serde(default)]
    pub auto: AutoTransitions,
}

fn default_max_retries() -> i32 {
    5
}

impl Default for StateMachineConfig {
    fn default() -> Self {
        Self {
            max_retries: default_max_retries(),
            timeouts: PhaseTimeouts::default(),
            auto: AutoTransitions::default(),
        }
    }
}

/// Phase timeouts in seconds
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PhaseTimeouts {
    #[serde(default = "default_planning_timeout")]
    pub planning: u64,
    #[serde(default = "default_coding_timeout")]
    pub coding: u64,
    #[serde(default = "default_building_timeout")]
    pub building: u64,
    #[serde(default = "default_deploying_timeout")]
    pub deploying: u64,
    #[serde(default = "default_verifying_timeout")]
    pub verifying: u64,
}

fn default_planning_timeout() -> u64 {
    3600
}
fn default_coding_timeout() -> u64 {
    14400
}
fn default_building_timeout() -> u64 {
    1800
}
fn default_deploying_timeout() -> u64 {
    600
}
fn default_verifying_timeout() -> u64 {
    300
}

impl Default for PhaseTimeouts {
    fn default() -> Self {
        Self {
            planning: default_planning_timeout(),
            coding: default_coding_timeout(),
            building: default_building_timeout(),
            deploying: default_deploying_timeout(),
            verifying: default_verifying_timeout(),
        }
    }
}

/// Auto-transition settings
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutoTransitions {
    /// Auto move from BUILD_SUCCESS to DEPLOY_QUEUE
    #[serde(default = "default_true")]
    pub build_success_to_deploy: bool,

    /// Auto archive completed cards after N days (0 = disabled)
    #[serde(default)]
    pub archive_completed_after_days: u32,
}

impl Default for AutoTransitions {
    fn default() -> Self {
        Self {
            build_success_to_deploy: true,
            archive_completed_after_days: 30,
        }
    }
}

/// Loop manager configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoopManagerConfig {
    /// Maximum iterations per loop
    #[serde(default = "default_max_iterations")]
    pub max_iterations: u32,

    /// Maximum runtime in seconds
    #[serde(default = "default_max_runtime")]
    pub max_runtime_seconds: u64,

    /// Maximum cost in USD
    #[serde(default = "default_max_cost")]
    pub max_cost_usd: f64,

    /// Checkpoint every N iterations
    #[serde(default = "default_checkpoint_interval")]
    pub checkpoint_interval: u32,

    /// Cooldown between iterations in seconds
    #[serde(default = "default_cooldown")]
    pub cooldown_seconds: u64,

    /// Maximum consecutive errors before stopping
    #[serde(default = "default_max_consecutive_errors")]
    pub max_consecutive_errors: u32,

    /// Completion signal to look for
    #[serde(default = "default_completion_signal")]
    pub completion_signal: String,
}

fn default_max_iterations() -> u32 {
    100
}
fn default_max_runtime() -> u64 {
    14400
}
fn default_max_cost() -> f64 {
    300.0
}
fn default_checkpoint_interval() -> u32 {
    10
}
fn default_cooldown() -> u64 {
    3
}
fn default_max_consecutive_errors() -> u32 {
    3
}
fn default_completion_signal() -> String {
    "<promise>COMPLETE</promise>".to_string()
}

impl Default for LoopManagerConfig {
    fn default() -> Self {
        Self {
            max_iterations: default_max_iterations(),
            max_runtime_seconds: default_max_runtime(),
            max_cost_usd: default_max_cost(),
            checkpoint_interval: default_checkpoint_interval(),
            cooldown_seconds: default_cooldown(),
            max_consecutive_errors: default_max_consecutive_errors(),
            completion_signal: default_completion_signal(),
        }
    }
}

/// Integration configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[derive(Default)]
pub struct IntegrationsConfig {
    /// GitHub configuration
    #[serde(default)]
    pub github: Option<GitHubConfig>,

    /// ArgoCD configuration
    #[serde(default)]
    pub argocd: Option<ArgoCDConfig>,

    /// Claude API configuration
    #[serde(default)]
    pub claude: Option<ClaudeConfig>,

    /// Configuration sync settings
    #[serde(default)]
    pub config_sync: ConfigSyncConfig,
}


#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitHubConfig {
    pub token: Option<String>,
    pub api_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArgoCDConfig {
    pub server_url: String,
    pub token: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClaudeConfig {
    pub api_key: Option<String>,
    pub model: Option<String>,
}

/// Configuration sync settings
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ConfigSyncConfig {
    /// Git repository URL containing configuration files
    /// e.g., https://github.com/org/claude-config.git
    pub repository_url: Option<String>,

    /// Branch to sync from (default: main)
    #[serde(default = "default_config_branch")]
    pub branch: String,

    /// Local cache path for cloned config repo
    /// Default: ~/.local/share/ringmaster/config-repos/<repo-name>
    pub cache_path: Option<String>,

    /// Whether to auto-sync on loop start
    #[serde(default = "default_true")]
    pub auto_sync: bool,
}

fn default_config_branch() -> String {
    "main".to_string()
}

/// Get the data directory for Ringmaster
pub fn get_data_dir() -> PathBuf {
    if let Some(proj_dirs) = ProjectDirs::from("com", "ringmaster", "ringmaster") {
        proj_dirs.data_dir().to_path_buf()
    } else {
        // Fallback to home directory
        dirs::home_dir()
            .map(|h| h.join(".ringmaster"))
            .unwrap_or_else(|| PathBuf::from(".ringmaster"))
    }
}

/// Get the config directory for Ringmaster
pub fn get_config_dir() -> PathBuf {
    if let Some(proj_dirs) = ProjectDirs::from("com", "ringmaster", "ringmaster") {
        proj_dirs.config_dir().to_path_buf()
    } else {
        get_data_dir()
    }
}

/// Load configuration from file or defaults
pub fn load_config() -> Config {
    let config_path = get_config_dir().join("config.toml");

    if config_path.exists() {
        if let Ok(contents) = std::fs::read_to_string(&config_path) {
            if let Ok(config) = toml::from_str(&contents) {
                return config;
            }
        }
    }

    Config::default()
}

/// Save configuration to file
pub fn save_config(config: &Config) -> std::io::Result<()> {
    let config_dir = get_config_dir();
    std::fs::create_dir_all(&config_dir)?;

    let config_path = config_dir.join("config.toml");
    let contents = toml::to_string_pretty(config).unwrap_or_default();
    std::fs::write(config_path, contents)?;

    Ok(())
}

// Add dirs crate for home_dir
mod dirs {
    use std::path::PathBuf;

    pub fn home_dir() -> Option<PathBuf> {
        std::env::var_os("HOME")
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(PathBuf::from)
    }
}
