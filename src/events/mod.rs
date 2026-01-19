//! Event bus for pub/sub communication between components

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use uuid::Uuid;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};

use crate::domain::{Card, CardState, Trigger};

/// Event types that can be published
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    /// Card was created
    CardCreated {
        card_id: Uuid,
        project_id: Uuid,
        timestamp: DateTime<Utc>,
    },

    /// Card was updated
    CardUpdated {
        card_id: Uuid,
        card: Box<Card>,
        timestamp: DateTime<Utc>,
    },

    /// Card state changed
    StateChanged {
        card_id: Uuid,
        from_state: CardState,
        to_state: CardState,
        trigger: Trigger,
        timestamp: DateTime<Utc>,
    },

    /// Loop iteration completed
    LoopIteration {
        card_id: Uuid,
        iteration: i32,
        tokens_used: i32,
        cost_usd: f64,
        timestamp: DateTime<Utc>,
    },

    /// Loop started
    LoopStarted {
        card_id: Uuid,
        timestamp: DateTime<Utc>,
    },

    /// Loop completed
    LoopCompleted {
        card_id: Uuid,
        result: LoopCompletionResult,
        total_iterations: i32,
        total_cost_usd: f64,
        total_tokens: i64,
        timestamp: DateTime<Utc>,
    },

    /// Loop paused
    LoopPaused {
        card_id: Uuid,
        iteration: i32,
        timestamp: DateTime<Utc>,
    },

    /// Build status update
    BuildStatus {
        card_id: Uuid,
        run_id: i64,
        status: String,
        conclusion: Option<String>,
        timestamp: DateTime<Utc>,
    },

    /// Deploy status update
    DeployStatus {
        card_id: Uuid,
        app_name: String,
        sync_status: String,
        health_status: String,
        timestamp: DateTime<Utc>,
    },

    /// Error detected
    ErrorDetected {
        card_id: Uuid,
        error_id: Uuid,
        error_type: String,
        message: String,
        category: String,
        timestamp: DateTime<Utc>,
    },

    /// Loop stopped
    LoopStopped {
        card_id: Uuid,
        iteration: i32,
        reason: Option<crate::loops::StopReason>,
        timestamp: DateTime<Utc>,
    },

    /// Git worktree created
    WorktreeCreated {
        card_id: Uuid,
        worktree_path: String,
        branch_name: String,
        timestamp: DateTime<Utc>,
    },

    /// Pull request created
    PullRequestCreated {
        card_id: Uuid,
        pr_url: String,
        timestamp: DateTime<Utc>,
    },

    /// Error context collected
    ErrorContextCollected {
        card_id: Uuid,
        timestamp: DateTime<Utc>,
    },

    /// User notification
    UserNotification {
        card_id: Uuid,
        message: String,
        timestamp: DateTime<Utc>,
    },

    /// Metrics recorded
    MetricsRecorded {
        card_id: Uuid,
        timestamp: DateTime<Utc>,
    },

    /// Configuration synced from config repo
    ConfigSynced {
        card_id: Uuid,
        claude_md_synced: bool,
        skills_synced: usize,
        patterns_synced: bool,
        timestamp: DateTime<Utc>,
    },
}

impl Event {
    /// Get the card ID associated with this event
    pub fn card_id(&self) -> Option<Uuid> {
        match self {
            Event::CardCreated { card_id, .. } => Some(*card_id),
            Event::CardUpdated { card_id, .. } => Some(*card_id),
            Event::StateChanged { card_id, .. } => Some(*card_id),
            Event::LoopIteration { card_id, .. } => Some(*card_id),
            Event::LoopStarted { card_id, .. } => Some(*card_id),
            Event::LoopCompleted { card_id, .. } => Some(*card_id),
            Event::LoopPaused { card_id, .. } => Some(*card_id),
            Event::LoopStopped { card_id, .. } => Some(*card_id),
            Event::BuildStatus { card_id, .. } => Some(*card_id),
            Event::DeployStatus { card_id, .. } => Some(*card_id),
            Event::ErrorDetected { card_id, .. } => Some(*card_id),
            Event::WorktreeCreated { card_id, .. } => Some(*card_id),
            Event::PullRequestCreated { card_id, .. } => Some(*card_id),
            Event::ErrorContextCollected { card_id, .. } => Some(*card_id),
            Event::UserNotification { card_id, .. } => Some(*card_id),
            Event::MetricsRecorded { card_id, .. } => Some(*card_id),
            Event::ConfigSynced { card_id, .. } => Some(*card_id),
        }
    }

    /// Get the project ID associated with this event (if applicable)
    pub fn project_id(&self) -> Option<Uuid> {
        match self {
            Event::CardCreated { project_id, .. } => Some(*project_id),
            _ => None,
        }
    }
}

/// Loop completion result
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum LoopCompletionResult {
    CompletionSignal,
    MaxIterations,
    CostLimit,
    TimeLimit,
    UserStopped,
    CircuitBreaker,
    Error,
}

/// Event bus for pub/sub communication
pub struct EventBus {
    /// Broadcast sender for all events
    sender: broadcast::Sender<Event>,

    /// Card-specific subscriptions
    card_subscriptions: Arc<RwLock<HashMap<Uuid, Vec<String>>>>,

    /// Project-specific subscriptions
    project_subscriptions: Arc<RwLock<HashMap<Uuid, Vec<String>>>>,
}

impl EventBus {
    /// Create a new event bus
    pub fn new() -> Self {
        let (sender, _) = broadcast::channel(1024);
        Self {
            sender,
            card_subscriptions: Arc::new(RwLock::new(HashMap::new())),
            project_subscriptions: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Publish an event
    pub fn publish(&self, event: Event) {
        // Ignore errors if there are no receivers
        let _ = self.sender.send(event);
    }

    /// Subscribe to all events
    pub fn subscribe(&self) -> broadcast::Receiver<Event> {
        self.sender.subscribe()
    }

    /// Subscribe a connection to specific card events
    pub async fn subscribe_to_card(&self, connection_id: &str, card_id: Uuid) {
        let mut subs = self.card_subscriptions.write().await;
        subs.entry(card_id)
            .or_default()
            .push(connection_id.to_string());
    }

    /// Subscribe a connection to specific project events
    pub async fn subscribe_to_project(&self, connection_id: &str, project_id: Uuid) {
        let mut subs = self.project_subscriptions.write().await;
        subs.entry(project_id)
            .or_default()
            .push(connection_id.to_string());
    }

    /// Unsubscribe a connection from card events
    pub async fn unsubscribe_from_card(&self, connection_id: &str, card_id: Uuid) {
        let mut subs = self.card_subscriptions.write().await;
        if let Some(connections) = subs.get_mut(&card_id) {
            connections.retain(|c| c != connection_id);
        }
    }

    /// Unsubscribe a connection from project events
    pub async fn unsubscribe_from_project(&self, connection_id: &str, project_id: Uuid) {
        let mut subs = self.project_subscriptions.write().await;
        if let Some(connections) = subs.get_mut(&project_id) {
            connections.retain(|c| c != connection_id);
        }
    }

    /// Remove all subscriptions for a connection
    pub async fn remove_connection(&self, connection_id: &str) {
        {
            let mut subs = self.card_subscriptions.write().await;
            for connections in subs.values_mut() {
                connections.retain(|c| c != connection_id);
            }
        }
        {
            let mut subs = self.project_subscriptions.write().await;
            for connections in subs.values_mut() {
                connections.retain(|c| c != connection_id);
            }
        }
    }

    /// Check if a connection is subscribed to a card
    pub async fn is_subscribed_to_card(&self, connection_id: &str, card_id: Uuid) -> bool {
        let subs = self.card_subscriptions.read().await;
        subs.get(&card_id)
            .map(|c| c.contains(&connection_id.to_string()))
            .unwrap_or(false)
    }

    /// Check if a connection is subscribed to a project
    pub async fn is_subscribed_to_project(&self, connection_id: &str, project_id: Uuid) -> bool {
        let subs = self.project_subscriptions.read().await;
        subs.get(&project_id)
            .map(|c| c.contains(&connection_id.to_string()))
            .unwrap_or(false)
    }
}

impl Default for EventBus {
    fn default() -> Self {
        Self::new()
    }
}

impl Clone for EventBus {
    fn clone(&self) -> Self {
        Self {
            sender: self.sender.clone(),
            card_subscriptions: Arc::clone(&self.card_subscriptions),
            project_subscriptions: Arc::clone(&self.project_subscriptions),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_publish_subscribe() {
        let bus = EventBus::new();
        let mut receiver = bus.subscribe();

        let card_id = Uuid::new_v4();
        let project_id = Uuid::new_v4();

        bus.publish(Event::CardCreated {
            card_id,
            project_id,
            timestamp: Utc::now(),
        });

        let event = receiver.recv().await.unwrap();
        assert_eq!(event.card_id(), Some(card_id));
    }

    #[tokio::test]
    async fn test_card_subscription() {
        let bus = EventBus::new();
        let card_id = Uuid::new_v4();
        let connection_id = "conn-123";

        bus.subscribe_to_card(connection_id, card_id).await;
        assert!(bus.is_subscribed_to_card(connection_id, card_id).await);

        bus.unsubscribe_from_card(connection_id, card_id).await;
        assert!(!bus.is_subscribed_to_card(connection_id, card_id).await);
    }

    #[tokio::test]
    async fn test_remove_connection() {
        let bus = EventBus::new();
        let card_id = Uuid::new_v4();
        let project_id = Uuid::new_v4();
        let connection_id = "conn-123";

        bus.subscribe_to_card(connection_id, card_id).await;
        bus.subscribe_to_project(connection_id, project_id).await;

        bus.remove_connection(connection_id).await;

        assert!(!bus.is_subscribed_to_card(connection_id, card_id).await);
        assert!(!bus.is_subscribed_to_project(connection_id, project_id).await);
    }
}
