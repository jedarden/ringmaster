"""WebSocket endpoint for real-time updates."""

import asyncio
import contextlib
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ringmaster.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str | None = None,
) -> None:
    """WebSocket endpoint for receiving real-time events.

    Query Parameters:
        project_id: Optional project ID to filter events

    The WebSocket will receive JSON messages with the following structure:
    {
        "id": "abc123",
        "type": "task.updated",
        "timestamp": "2024-01-01T00:00:00Z",
        "data": {...},
        "project_id": "uuid-string"
    }

    Clients can send messages to control the connection:
    - {"action": "ping"} -> responds with {"action": "pong"}
    - {"action": "subscribe", "project_id": "uuid"} -> filter by project
    """
    await websocket.accept()

    subscriber_id = f"ws-{uuid4().hex[:8]}"
    logger.info(f"WebSocket connected: {subscriber_id} (project: {project_id or 'all'})")

    # Subscribe to events
    queue = await event_bus.subscribe(subscriber_id, project_id)

    try:
        # Handle bidirectional communication
        receive_task = asyncio.create_task(_handle_receive(websocket, subscriber_id))
        send_task = asyncio.create_task(_handle_send(websocket, queue, project_id))

        # Wait for either task to complete (client disconnect or error)
        done, pending = await asyncio.wait(
            [receive_task, send_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {subscriber_id}")

    finally:
        await event_bus.unsubscribe(subscriber_id)


async def _handle_receive(websocket: WebSocket, subscriber_id: str) -> None:
    """Handle incoming WebSocket messages."""
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "ping":
                    await websocket.send_json({"action": "pong"})

                elif action == "subscribe":
                    # Update subscription (not implemented yet - would need to track per-subscriber)
                    new_project = message.get("project_id")
                    logger.debug(f"Subscriber {subscriber_id} updated project filter: {new_project}")
                    await websocket.send_json({"action": "subscribed", "project_id": new_project})

                else:
                    logger.debug(f"Unknown action from {subscriber_id}: {action}")

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {subscriber_id}: {data}")

    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(f"Receive error for {subscriber_id}: {e}")
        raise


async def _handle_send(
    websocket: WebSocket,
    queue: asyncio.Queue,
    project_id: str | None,
) -> None:
    """Send events from queue to WebSocket."""
    try:
        while True:
            event = await queue.get()

            # Filter by project if specified
            if project_id is not None and event.project_id != project_id:
                continue

            await websocket.send_json(event.to_json())

    except WebSocketDisconnect:
        raise
    except Exception as e:
        logger.error(f"Send error: {e}")
        raise
