//! Application state shared across handlers

use std::sync::Arc;
use sqlx::SqlitePool;
use tokio::sync::RwLock;

use crate::events::EventBus;
use crate::state_machine::CardStateMachine;
use crate::loops::LoopManager;
use crate::config::AppConfig;

/// Shared application state
#[derive(Clone)]
pub struct AppState {
    pub pool: SqlitePool,
    pub event_bus: Arc<EventBus>,
    pub state_machine: Arc<CardStateMachine>,
    pub loop_manager: Arc<RwLock<LoopManager>>,
    pub config: Arc<AppConfig>,
}

impl AppState {
    pub fn new(
        pool: SqlitePool,
        event_bus: EventBus,
        config: AppConfig,
    ) -> Self {
        let event_bus = Arc::new(event_bus);
        let loop_manager = LoopManager::new(event_bus.clone());

        Self {
            pool,
            event_bus,
            state_machine: Arc::new(CardStateMachine::new()),
            loop_manager: Arc::new(RwLock::new(loop_manager)),
            config: Arc::new(config),
        }
    }
}
