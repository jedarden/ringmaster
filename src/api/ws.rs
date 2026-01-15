//! WebSocket server for real-time updates

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::IntoResponse,
};
use futures::{sink::SinkExt, stream::StreamExt};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::events::Event;

use super::AppState;

/// WebSocket message from client
#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ClientMessage {
    Subscribe {
        #[serde(default)]
        card_ids: Vec<Uuid>,
        #[serde(default)]
        project_ids: Vec<Uuid>,
    },
    Unsubscribe {
        #[serde(default)]
        card_ids: Vec<Uuid>,
        #[serde(default)]
        project_ids: Vec<Uuid>,
    },
    Ping,
}

/// WebSocket message to client
#[derive(Debug, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ServerMessage {
    Pong,
    Error { message: String },
    Event(Event),
}

/// Handle WebSocket upgrade
pub async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket, state))
}

/// Handle a WebSocket connection
async fn handle_socket(socket: WebSocket, state: AppState) {
    let (mut sender, mut receiver) = socket.split();
    let connection_id = Uuid::new_v4().to_string();

    // Subscribe to event bus
    let mut event_receiver = state.event_bus.subscribe();

    // Spawn task to forward events to WebSocket
    let event_bus = state.event_bus.clone();
    let conn_id = connection_id.clone();
    let send_task = tokio::spawn(async move {
        while let Ok(event) = event_receiver.recv().await {
            // Check if this connection is subscribed to this event
            let should_send = if let Some(card_id) = event.card_id() {
                event_bus.is_subscribed_to_card(&conn_id, card_id).await
            } else if let Some(project_id) = event.project_id() {
                event_bus.is_subscribed_to_project(&conn_id, project_id).await
            } else {
                false
            };

            if should_send {
                let msg = ServerMessage::Event(event);
                if let Ok(json) = serde_json::to_string(&msg) {
                    if sender.send(Message::Text(json)).await.is_err() {
                        break;
                    }
                }
            }
        }
    });

    // Handle incoming messages
    let event_bus = state.event_bus.clone();
    let conn_id = connection_id.clone();
    while let Some(msg) = receiver.next().await {
        match msg {
            Ok(Message::Text(text)) => {
                if let Ok(client_msg) = serde_json::from_str::<ClientMessage>(&text) {
                    match client_msg {
                        ClientMessage::Subscribe {
                            card_ids,
                            project_ids,
                        } => {
                            for card_id in card_ids {
                                event_bus.subscribe_to_card(&conn_id, card_id).await;
                            }
                            for project_id in project_ids {
                                event_bus.subscribe_to_project(&conn_id, project_id).await;
                            }
                        }
                        ClientMessage::Unsubscribe {
                            card_ids,
                            project_ids,
                        } => {
                            for card_id in card_ids {
                                event_bus.unsubscribe_from_card(&conn_id, card_id).await;
                            }
                            for project_id in project_ids {
                                event_bus.unsubscribe_from_project(&conn_id, project_id).await;
                            }
                        }
                        ClientMessage::Ping => {
                            // Pong is sent in the send task
                        }
                    }
                }
            }
            Ok(Message::Close(_)) => break,
            Err(_) => break,
            _ => {}
        }
    }

    // Clean up
    state.event_bus.remove_connection(&connection_id).await;
    send_task.abort();
}
