//! Configuration module for Ringmaster

use directories::ProjectDirs;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Subscription configuration for coding platforms
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Subscription {
    /// Unique name for this subscription
    pub name: String,

    /// Platform type (e.g., "claude-code", "aider")
    pub platform: String,

    /// Custom config directory for this subscription (multi-account support)
    /// For Claude Code, this maps to CLAUDE_CONFIG_DIR
    pub config_dir: Option<PathBuf>,

    /// Model to use for this subscription
    pub model: Option<String>,

    /// Maximum concurrent sessions for this subscription
    #[serde(default = "default_max_concurrent")]
    pub max_concurrent: u32,

    /// Whether this subscription is enabled
    #[serde(default = "default_true")]
    pub enabled: bool,

    /// Priority (lower = higher priority for selection)
    #[serde(default = "default_priority")]
    pub priority: u32,
}

fn default_max_concurrent() -> u32 {
    1
}

fn default_priority() -> u32 {
    100
}

impl Default for Subscription {
    fn default() -> Self {
        Self {
            name: "default".to_string(),
            platform: "claude-code".to_string(),
            config_dir: None,
            model: None,
            max_concurrent: 1,
            enabled: true,
            priority: 100,
        }
    }
}

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

    /// Subscriptions for coding platforms (replaces direct API usage)
    #[serde(default)]
    pub subscriptions: Vec<Subscription>,
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

#[cfg(test)]
mod tests {
    use super::*;

    // Default configuration tests
    #[test]
    fn test_config_default() {
        let config = Config::default();

        assert_eq!(config.server.host, "127.0.0.1");
        assert_eq!(config.server.port, 8080);
        assert!(config.server.cors_enabled);
        assert!(config.database.path.is_none());
        assert_eq!(config.state_machine.max_retries, 5);
        assert_eq!(config.loop_manager.max_iterations, 100);
    }

    // Server config tests
    #[test]
    fn test_server_config_default() {
        let config = ServerConfig::default();

        assert_eq!(config.host, "127.0.0.1");
        assert_eq!(config.port, 8080);
        assert!(config.cors_enabled);
    }

    #[test]
    fn test_server_config_serialization() {
        let config = ServerConfig::default();
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("\"host\""));
        assert!(json.contains("\"port\""));
        assert!(json.contains("\"cors_enabled\""));
    }

    #[test]
    fn test_server_config_deserialization() {
        let json = r#"{"host": "0.0.0.0", "port": 3000, "cors_enabled": false}"#;
        let config: ServerConfig = serde_json::from_str(json).unwrap();

        assert_eq!(config.host, "0.0.0.0");
        assert_eq!(config.port, 3000);
        assert!(!config.cors_enabled);
    }

    // Database config tests
    #[test]
    fn test_database_config_default() {
        let config = DatabaseConfig::default();
        assert!(config.path.is_none());
    }

    #[test]
    fn test_database_config_get_path_custom() {
        let config = DatabaseConfig {
            path: Some("/custom/path/db.sqlite".to_string()),
        };
        assert_eq!(config.get_path(), PathBuf::from("/custom/path/db.sqlite"));
    }

    #[test]
    fn test_database_config_get_path_default() {
        let config = DatabaseConfig::default();
        let path = config.get_path();
        assert!(path.to_string_lossy().contains("data.db"));
    }

    // State machine config tests
    #[test]
    fn test_state_machine_config_default() {
        let config = StateMachineConfig::default();

        assert_eq!(config.max_retries, 5);
        assert_eq!(config.timeouts.planning, 3600);
        assert_eq!(config.timeouts.coding, 14400);
        assert_eq!(config.timeouts.building, 1800);
        assert_eq!(config.timeouts.deploying, 600);
        assert_eq!(config.timeouts.verifying, 300);
    }

    #[test]
    fn test_phase_timeouts_default() {
        let timeouts = PhaseTimeouts::default();

        assert_eq!(timeouts.planning, 3600);    // 1 hour
        assert_eq!(timeouts.coding, 14400);     // 4 hours
        assert_eq!(timeouts.building, 1800);    // 30 minutes
        assert_eq!(timeouts.deploying, 600);    // 10 minutes
        assert_eq!(timeouts.verifying, 300);    // 5 minutes
    }

    #[test]
    fn test_auto_transitions_default() {
        let auto = AutoTransitions::default();

        assert!(auto.build_success_to_deploy);
        assert_eq!(auto.archive_completed_after_days, 30);
    }

    // Loop manager config tests
    #[test]
    fn test_loop_manager_config_default() {
        let config = LoopManagerConfig::default();

        assert_eq!(config.max_iterations, 100);
        assert_eq!(config.max_runtime_seconds, 14400);
        assert!((config.max_cost_usd - 300.0).abs() < 0.01);
        assert_eq!(config.checkpoint_interval, 10);
        assert_eq!(config.cooldown_seconds, 3);
        assert_eq!(config.max_consecutive_errors, 3);
        assert_eq!(config.completion_signal, "<promise>COMPLETE</promise>");
    }

    #[test]
    fn test_loop_manager_config_serialization() {
        let config = LoopManagerConfig::default();
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("\"max_iterations\""));
        assert!(json.contains("\"max_runtime_seconds\""));
        assert!(json.contains("\"max_cost_usd\""));
        assert!(json.contains("\"checkpoint_interval\""));
        assert!(json.contains("\"cooldown_seconds\""));
        assert!(json.contains("\"max_consecutive_errors\""));
        assert!(json.contains("\"completion_signal\""));
    }

    #[test]
    fn test_loop_manager_config_deserialization() {
        let json = r#"{
            "max_iterations": 50,
            "max_runtime_seconds": 7200,
            "max_cost_usd": 150.0,
            "checkpoint_interval": 5,
            "cooldown_seconds": 10,
            "max_consecutive_errors": 2,
            "completion_signal": "<done>DONE</done>"
        }"#;
        let config: LoopManagerConfig = serde_json::from_str(json).unwrap();

        assert_eq!(config.max_iterations, 50);
        assert_eq!(config.max_runtime_seconds, 7200);
        assert!((config.max_cost_usd - 150.0).abs() < 0.01);
        assert_eq!(config.checkpoint_interval, 5);
        assert_eq!(config.cooldown_seconds, 10);
        assert_eq!(config.max_consecutive_errors, 2);
        assert_eq!(config.completion_signal, "<done>DONE</done>");
    }

    // Integrations config tests
    #[test]
    fn test_integrations_config_default() {
        let config = IntegrationsConfig::default();

        assert!(config.github.is_none());
        assert!(config.argocd.is_none());
        assert!(config.claude.is_none());
        assert!(config.config_sync.repository_url.is_none());
    }

    #[test]
    fn test_github_config_serialization() {
        let config = GitHubConfig {
            token: Some("ghp_test123".to_string()),
            api_url: Some("https://api.github.com".to_string()),
        };
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("\"token\""));
        assert!(json.contains("\"api_url\""));
    }

    #[test]
    fn test_argocd_config_serialization() {
        let config = ArgoCDConfig {
            server_url: "https://argocd.example.com".to_string(),
            token: Some("argocd-token".to_string()),
        };
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("\"server_url\""));
        assert!(json.contains("\"token\""));
    }

    #[test]
    fn test_claude_config_serialization() {
        let config = ClaudeConfig {
            api_key: Some("sk-ant-test".to_string()),
            model: Some("claude-3-sonnet".to_string()),
        };
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("\"api_key\""));
        assert!(json.contains("\"model\""));
    }

    // Config sync tests
    #[test]
    fn test_config_sync_config_default() {
        let config = ConfigSyncConfig::default();

        assert!(config.repository_url.is_none());
        // Note: Default derive creates empty string; serde default only applies during deserialization
        assert_eq!(config.branch, "");
        assert!(config.cache_path.is_none());
        // Default derive creates false for bool
        assert!(!config.auto_sync);
    }

    #[test]
    fn test_config_sync_config_serde_defaults() {
        // When deserializing with empty JSON, serde defaults are applied
        let json = r#"{}"#;
        let config: ConfigSyncConfig = serde_json::from_str(json).unwrap();

        assert!(config.repository_url.is_none());
        assert_eq!(config.branch, "main");  // serde default applies
        assert!(config.cache_path.is_none());
        assert!(config.auto_sync);  // serde default applies
    }

    #[test]
    fn test_config_sync_config_deserialization() {
        let json = r#"{
            "repository_url": "https://github.com/org/claude-config.git",
            "branch": "develop",
            "auto_sync": false
        }"#;
        let config: ConfigSyncConfig = serde_json::from_str(json).unwrap();

        assert_eq!(config.repository_url, Some("https://github.com/org/claude-config.git".to_string()));
        assert_eq!(config.branch, "develop");
        assert!(!config.auto_sync);
    }

    // Directory functions tests
    #[test]
    fn test_get_data_dir() {
        let data_dir = get_data_dir();
        // Should return some path (either project dirs or fallback)
        assert!(!data_dir.as_os_str().is_empty());
    }

    #[test]
    fn test_get_config_dir() {
        let config_dir = get_config_dir();
        // Should return some path
        assert!(!config_dir.as_os_str().is_empty());
    }

    // Full config serialization tests
    #[test]
    fn test_full_config_toml_serialization() {
        let config = Config::default();
        let toml_str = toml::to_string_pretty(&config).unwrap();

        assert!(toml_str.contains("[server]"));
        assert!(toml_str.contains("[database]"));
        assert!(toml_str.contains("[state_machine]"));
        assert!(toml_str.contains("[loop_manager]"));
    }

    #[test]
    fn test_full_config_toml_deserialization() {
        let toml_str = r#"
[server]
host = "0.0.0.0"
port = 9090
cors_enabled = true

[database]
path = "/custom/db.sqlite"

[state_machine]
max_retries = 10

[loop_manager]
max_iterations = 200
max_cost_usd = 500.0

[integrations]
"#;
        let config: Config = toml::from_str(toml_str).unwrap();

        assert_eq!(config.server.host, "0.0.0.0");
        assert_eq!(config.server.port, 9090);
        assert_eq!(config.database.path, Some("/custom/db.sqlite".to_string()));
        assert_eq!(config.state_machine.max_retries, 10);
        assert_eq!(config.loop_manager.max_iterations, 200);
        assert!((config.loop_manager.max_cost_usd - 500.0).abs() < 0.01);
    }

    #[test]
    fn test_config_partial_toml_deserialization() {
        // Only specify some fields, rest should default
        let toml_str = r#"
[server]
port = 3000
"#;
        let config: Config = toml::from_str(toml_str).unwrap();

        assert_eq!(config.server.port, 3000);
        // Defaults should be applied
        assert_eq!(config.server.host, "127.0.0.1");
        assert!(config.server.cors_enabled);
        assert_eq!(config.loop_manager.max_iterations, 100);
    }

    // Subscription tests
    #[test]
    fn test_subscription_default() {
        let sub = Subscription::default();

        assert_eq!(sub.name, "default");
        assert_eq!(sub.platform, "claude-code");
        assert!(sub.config_dir.is_none());
        assert!(sub.model.is_none());
        assert_eq!(sub.max_concurrent, 1);
        assert!(sub.enabled);
        assert_eq!(sub.priority, 100);
    }

    #[test]
    fn test_subscription_serialization() {
        let sub = Subscription {
            name: "pro-account".to_string(),
            platform: "claude-code".to_string(),
            config_dir: Some(PathBuf::from("/home/user/.claude-pro")),
            model: Some("claude-opus-4-5-20251101".to_string()),
            max_concurrent: 3,
            enabled: true,
            priority: 10,
        };

        let json = serde_json::to_string(&sub).unwrap();
        assert!(json.contains("\"name\":\"pro-account\""));
        assert!(json.contains("\"platform\":\"claude-code\""));
        assert!(json.contains("\"max_concurrent\":3"));
    }

    #[test]
    fn test_subscription_deserialization() {
        let json = r#"{
            "name": "max-subscription",
            "platform": "claude-code",
            "model": "claude-sonnet-4-20250514",
            "max_concurrent": 2
        }"#;

        let sub: Subscription = serde_json::from_str(json).unwrap();

        assert_eq!(sub.name, "max-subscription");
        assert_eq!(sub.platform, "claude-code");
        assert_eq!(sub.model, Some("claude-sonnet-4-20250514".to_string()));
        assert_eq!(sub.max_concurrent, 2);
        // Defaults applied for missing fields
        assert!(sub.enabled);
        assert_eq!(sub.priority, 100);
    }

    #[test]
    fn test_config_with_subscriptions_toml() {
        let toml_str = r#"
[server]
port = 8080

[[subscriptions]]
name = "personal"
platform = "claude-code"
model = "claude-sonnet-4-20250514"
max_concurrent = 1

[[subscriptions]]
name = "team"
platform = "claude-code"
config_dir = "/home/user/.claude-team"
model = "claude-opus-4-5-20251101"
max_concurrent = 3
priority = 50
"#;

        let config: Config = toml::from_str(toml_str).unwrap();

        assert_eq!(config.subscriptions.len(), 2);

        assert_eq!(config.subscriptions[0].name, "personal");
        assert_eq!(config.subscriptions[0].max_concurrent, 1);

        assert_eq!(config.subscriptions[1].name, "team");
        assert_eq!(config.subscriptions[1].config_dir, Some(PathBuf::from("/home/user/.claude-team")));
        assert_eq!(config.subscriptions[1].priority, 50);
    }

    #[test]
    fn test_config_default_has_empty_subscriptions() {
        let config = Config::default();
        assert!(config.subscriptions.is_empty());
    }
}
