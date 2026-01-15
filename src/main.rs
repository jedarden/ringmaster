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
    api::{card_routes, error_routes, global_loop_routes, loop_routes, project_routes, ws_handler, AppState},
    config::{get_data_dir, load_config},
    db::init_database,
    events::EventBus,
    loops::LoopManager,
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
    /// Start the Ringmaster server
    Serve,
    /// Initialize the database
    Init,
    /// Show configuration info
    Config,
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
        Some(Commands::Init) => {
            println!("Initializing database at: {}", db_path);
            let _pool = init_database(&db_path).await?;
            println!("Database initialized successfully!");
            return Ok(());
        }
        Some(Commands::Config) => {
            println!("Ringmaster Configuration");
            println!("========================");
            println!("Data directory: {}", get_data_dir().display());
            println!("Database path: {}", db_path);
            println!("Server: {}:{}", cli.host, cli.port);
            return Ok(());
        }
        _ => {}
    }

    // Start server
    run_server(&cli.host, cli.port, &db_path).await
}

async fn run_server(host: &str, port: u16, db_path: &str) -> anyhow::Result<()> {
    // Initialize database
    tracing::info!("Initializing database at: {}", db_path);
    let pool = init_database(db_path).await?;

    // Create shared state
    let event_bus = EventBus::new();
    let loop_manager = Arc::new(RwLock::new(LoopManager::new()));

    let app_state = AppState {
        pool,
        event_bus,
        loop_manager,
    };

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
