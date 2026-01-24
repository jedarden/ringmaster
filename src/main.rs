//! Ringmaster - SDLC orchestration platform

use std::net::SocketAddr;
use std::sync::Arc;

use axum::{
    routing::get,
    Router,
};
use clap::{Parser, Subcommand};
use tokio::sync::RwLock;
use tower_http::cors::{Any, CorsLayer};
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use ringmaster::{
    api::{card_routes, error_routes, global_loop_routes, integration_routes, loop_routes, project_routes, ws_handler, AppState},
    config::{get_data_dir, load_config},
    db::init_database,
    events::EventBus,
    loops::LoopManager,
    monitor::{IntegrationMonitor, MonitorConfig},
    platforms::{ensure_claude_available, find_claude_binary, get_installed_version},
    state_machine::ActionExecutor,
    static_files::static_handler,
};

#[derive(Parser)]
#[command(name = "ringmaster")]
#[command(author = "Ringmaster Team")]
#[command(version = "0.1.0")]
#[command(about = "SDLC orchestration platform with visual Kanban and autonomous AI coding loops")]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,

    /// Host to bind to
    #[arg(short = 'H', long, default_value = "127.0.0.1")]
    host: String,

    /// Port to listen on
    #[arg(short, long, default_value = "8080")]
    port: u16,

    /// Database path (defaults to ~/.ringmaster/data.db)
    #[arg(short, long)]
    database: Option<String>,
}

#[derive(Subcommand)]
enum Commands {
    /// Show configuration info
    Config,
    /// Check or install Claude Code CLI
    Doctor {
        /// Install Claude Code CLI if not found
        #[arg(long)]
        install: bool,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "ringmaster=info,tower_http=debug".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    let cli = Cli::parse();
    let config = load_config();

    // Determine database path
    let db_path = cli
        .database
        .or(config.database.path.clone())
        .unwrap_or_else(|| get_data_dir().join("data.db").to_string_lossy().to_string());

    match cli.command {
        Some(Commands::Config) => {
            println!("Ringmaster Configuration");
            println!("========================");
            println!("Data directory: {}", get_data_dir().display());
            println!("Database path: {}", db_path);
            println!("Server: {}:{}", cli.host, cli.port);
            return Ok(());
        }
        Some(Commands::Doctor { install }) => {
            return run_doctor(install).await;
        }
        None => {}
    }

    // Start server (database is auto-created if it doesn't exist)
    run_server(&cli.host, cli.port, &db_path).await
}

async fn run_server(host: &str, port: u16, db_path: &str) -> anyhow::Result<()> {
    // Check and auto-install Claude Code CLI if needed
    match ensure_claude_available().await {
        Ok(path) => {
            let version = get_installed_version().await.unwrap_or_else(|| "unknown".to_string());
            tracing::info!("Claude Code CLI v{} available at {:?}", version, path);
        }
        Err(e) => {
            tracing::warn!("Claude Code CLI not available: {}. Coding loops will not work until installed.", e);
            tracing::warn!("Run 'ringmaster doctor --install' to install Claude Code CLI");
        }
    }

    // Ensure data directory exists
    if let Some(parent) = std::path::Path::new(db_path).parent() {
        std::fs::create_dir_all(parent)?;
    }

    // Initialize database (auto-creates if it doesn't exist)
    let db_exists = std::path::Path::new(db_path).exists();
    if !db_exists {
        tracing::info!("Creating new database at: {}", db_path);
    }
    let pool = init_database(db_path).await?;
    if !db_exists {
        tracing::info!("Database created and initialized");
    }

    // Create shared state
    let event_bus = EventBus::new();
    let loop_manager = Arc::new(RwLock::new(LoopManager::new()));
    let action_executor = Arc::new(ActionExecutor::new(
        pool.clone(),
        event_bus.clone(),
        loop_manager.clone(),
    ));

    let app_state = AppState {
        pool: pool.clone(),
        event_bus: event_bus.clone(),
        loop_manager,
        action_executor,
    };

    // Start integration monitor (background task)
    let mut monitor = IntegrationMonitor::new(
        pool,
        event_bus,
        MonitorConfig::default(),
    );

    // Configure monitor from environment variables
    if let (Ok(token), Ok(owner), Ok(repo)) = (
        std::env::var("GITHUB_TOKEN"),
        std::env::var("GITHUB_OWNER"),
        std::env::var("GITHUB_REPO"),
    ) {
        tracing::info!("GitHub Actions monitoring enabled for {}/{}", owner, repo);
        monitor = monitor.with_github(token, owner, repo);
    }

    if let (Ok(url), Ok(token)) = (
        std::env::var("ARGOCD_URL"),
        std::env::var("ARGOCD_AUTH_TOKEN"),
    ) {
        tracing::info!("ArgoCD monitoring enabled at {}", url);
        monitor = monitor.with_argocd(url, token);
    }

    // Start monitor in background
    let monitor = Arc::new(monitor);
    tokio::spawn(async move {
        monitor.start().await;
    });

    // Build CORS layer
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // Build router
    let app = Router::new()
        // Health check
        .route("/health", get(health_check))
        // API routes
        .nest("/api/cards", card_routes())
        .nest("/api/cards", loop_routes())
        .nest("/api/cards", error_routes())
        .nest("/api/projects", project_routes())
        .nest("/api/loops", global_loop_routes())
        .nest("/api/integrations", integration_routes())
        .route("/api/ws", get(ws_handler))
        // Static files (embedded frontend)
        .fallback(static_handler)
        // Middleware
        .layer(TraceLayer::new_for_http())
        .layer(cors)
        .with_state(app_state);

    // Parse address
    let addr: SocketAddr = format!("{}:{}", host, port).parse()?;

    // Print startup banner
    print_banner(host, port, db_path);

    // Start server
    tracing::info!("Starting server on {}", addr);
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

async fn health_check() -> &'static str {
    "OK"
}

fn print_banner(host: &str, port: u16, db_path: &str) {
    println!();
    println!("  ╭─────────────────────────────────────────────────────────────╮");
    println!("  │                                                             │");
    println!("  │   RINGMASTER v0.1.0                                         │");
    println!("  │   SDLC Orchestration Platform                               │");
    println!("  │                                                             │");
    println!("  ├─────────────────────────────────────────────────────────────┤");
    println!("  │                                                             │");
    println!("  │   Web UI:    http://{}:{}                         │", host, port);
    println!("  │   API:       http://{}:{}/api                     │", host, port);
    println!("  │   WebSocket: ws://{}:{}/api/ws                    │", host, port);
    println!("  │   Database:  {}   │", truncate_path(db_path, 35));
    println!("  │                                                             │");
    println!("  ╰─────────────────────────────────────────────────────────────╯");
    println!();
}

fn truncate_path(path: &str, max_len: usize) -> String {
    if path.len() <= max_len {
        format!("{:width$}", path, width = max_len)
    } else {
        format!("...{}", &path[path.len() - max_len + 3..])
    }
}

/// Run the doctor command to check/install Claude Code CLI
async fn run_doctor(install: bool) -> anyhow::Result<()> {
    println!();
    println!("  Ringmaster Doctor");
    println!("  =================");
    println!();

    // Check Claude Code CLI
    print!("  Claude Code CLI: ");
    if let Some(path) = find_claude_binary().await {
        let version = get_installed_version().await.unwrap_or_else(|| "unknown".to_string());
        println!("✓ Installed (v{})", version);
        println!("    Path: {:?}", path);
    } else {
        println!("✗ Not found");

        if install {
            println!();
            println!("  Installing Claude Code CLI...");
            match ensure_claude_available().await {
                Ok(path) => {
                    let version = get_installed_version().await.unwrap_or_else(|| "unknown".to_string());
                    println!("  ✓ Installed successfully (v{})", version);
                    println!("    Path: {:?}", path);
                }
                Err(e) => {
                    println!("  ✗ Installation failed: {}", e);
                    println!();
                    println!("  Manual installation:");
                    println!("    curl -fsSL https://claude.ai/install.sh | bash");
                    return Err(anyhow::anyhow!("Claude Code CLI installation failed"));
                }
            }
        } else {
            println!();
            println!("  To install Claude Code CLI, run:");
            println!("    ringmaster doctor --install");
            println!();
            println!("  Or install manually:");
            println!("    curl -fsSL https://claude.ai/install.sh | bash");
        }
    }

    println!();
    Ok(())
}
