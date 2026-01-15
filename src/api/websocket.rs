//! WebSocket handler for real-time updates

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
};
use futures::{sink::SinkExt, stream::StreamExt};
use uuid::Uuid;

use crate::events::Event;
use super::state::AppState;
use super::types::{WsClientMessage, WsServerMessage};

/// WebSocket upgrade handler
pub async fn ws_handler(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket, state))
}

/// Handle a WebSocket connection
async fn handle_socket(socket: WebSocket, state: AppState) {
    let connection_id = Uuid::new_v4().to_string();
    let (mut sender, mut receiver) = socket.split();

    // Subscribe to events
    let mut event_rx = state.event_bus.subscribe();

    tracing::info!("WebSocket connected: {}", connection_id);

    // Spawn task to forward events to client
    let event_bus = state.event_bus.clone();
    let conn_id = connection_id.clone();
    let forward_task = tokio::spawn(async move {
        while let Ok(event) = event_rx.recv().await {
            // Check if client is subscribed to this event
            let should_send = if let Some(card_id) = event.card_id() {
                event_bus.is_subscribed_to_card(&conn_id, card_id).await
            } else if let Some(project_id) = event.project_id() {
                event_bus.is_subscribed_to_project(&conn_id, project_id).await
            } else {
                false
            };

            if should_send {
                if let Some(msg) = event_to_ws_message(event) {
                    let json = serde_json::to_string(&msg).unwrap_or_default();
                    if sender.send(Message::Text(json.into())).await.is_err() {
                        break;
                    }
                }
            }
        }
    });

    // Handle incoming messages
    while let Some(Ok(msg)) = receiver.next().await {
        match msg {
            Message::Text(text) => {
                if let Ok(client_msg) = serde_json::from_str::<WsClientMessage>(&text) {
                    match client_msg {
                        WsClientMessage::Subscribe { card_ids, project_ids } => {
                            for id in card_ids {
                                if let Ok(uuid) = Uuid::parse_str(&id) {
                                    state.event_bus.subscribe_to_card(&connection_id, uuid).await;
                                }
                            }
                            for id in project_ids {
                                if let Ok(uuid) = Uuid::parse_str(&id) {
                                    state.event_bus.subscribe_to_project(&connection_id, uuid).await;
                                }
                            }
                        }
                        WsClientMessage::Unsubscribe { card_ids, project_ids } => {
                            for id in card_ids {
                                if let Ok(uuid) = Uuid::parse_str(&id) {
                                    state.event_bus.unsubscribe_from_card(&connection_id, uuid).await;
                                }
                            }
                            for id in project_ids {
                                if let Ok(uuid) = Uuid::parse_str(&id) {
                                    state.event_bus.unsubscribe_from_project(&connection_id, uuid).await;
                                }
                            }
                        }
                        WsClientMessage::Ping => {
                            // Already handled by Axum
                        }
                    }
                }
            }
            Message::Close(_) => break,
            _ => {}
        }
    }

    // Cleanup
    forward_task.abort();
    state.event_bus.remove_connection(&connection_id).await;
    tracing::info!("WebSocket disconnected: {}", connection_id);
}

/// Convert an internal event to a WebSocket message
fn event_to_ws_message(event: Event) -> Option<WsServerMessage> {
    match event {
        Event::CardUpdated { card_id, card, timestamp } => {
            Some(WsServerMessage::CardUpdated {
                card_id: card_id.to_string(),
                data: serde_json::to_value(&card).unwrap_or_default(),
                timestamp,
            })
        }
        Event::StateChanged { card_id, from_state, to_state, trigger, timestamp } => {
            Some(WsServerMessage::StateChanged {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "from": from_state.to_string(),
                    "to": to_state.to_string(),
                    "trigger": trigger.to_string()
                }),
                timestamp,
            })
        }
        Event::LoopIteration { card_id, iteration, tokens_used, cost_usd, timestamp } => {
            Some(WsServerMessage::LoopIteration {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "iteration": iteration,
                    "tokensUsed": tokens_used,
                    "costUsd": cost_usd
                }),
                timestamp,
            })
        }
        Event::LoopCompleted { card_id, result, total_iterations, total_cost_usd, total_tokens, timestamp } => {
            Some(WsServerMessage::LoopCompleted {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "result": format!("{:?}", result),
                    "totalIterations": total_iterations,
                    "totalCostUsd": total_cost_usd,
                    "totalTokens": total_tokens
                }),
                timestamp,
            })
        }
        Event::BuildStatus { card_id, run_id, status, conclusion, timestamp } => {
            Some(WsServerMessage::BuildStatus {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "runId": run_id,
                    "status": status,
                    "conclusion": conclusion
                }),
                timestamp,
            })
        }
        Event::DeployStatus { card_id, app_name, sync_status, health_status, timestamp } => {
            Some(WsServerMessage::DeployStatus {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "appName": app_name,
                    "syncStatus": sync_status,
                    "healthStatus": health_status
                }),
                timestamp,
            })
        }
        Event::ErrorDetected { card_id, error_id, error_type, message, category, timestamp } => {
            Some(WsServerMessage::ErrorDetected {
                card_id: card_id.to_string(),
                data: serde_json::json!({
                    "errorId": error_id.to_string(),
                    "errorType": error_type,
                    "message": message,
                    "category": category
                }),
                timestamp,
            })
        }
        _ => None,
    }
}
