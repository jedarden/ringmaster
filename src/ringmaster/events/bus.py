"""Event bus for broadcasting events to WebSocket clients."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ringmaster.events.types import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """Centralized event bus for broadcasting events to subscribers.

    Supports both:
    - Async generators for WebSocket streaming
    - Callback-based subscriptions for internal handlers
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue[Event]] = {}
        self._callbacks: list[Callable[[Event], Any]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber_id: str, project_id: str | None = None) -> asyncio.Queue[Event]:
        """Subscribe to events and return a queue to receive them.

        Args:
            subscriber_id: Unique ID for this subscriber (e.g., WebSocket connection ID)
            project_id: Optional project ID to filter events (None = all events)

        Returns:
            Queue that will receive events
        """
        async with self._lock:
            queue: asyncio.Queue[Event] = asyncio.Queue()
            # Store with project filter info
            self._subscribers[subscriber_id] = queue
            logger.debug(f"Subscriber {subscriber_id} connected (project: {project_id or 'all'})")
            return queue

    async def unsubscribe(self, subscriber_id: str) -> None:
        """Unsubscribe from events."""
        async with self._lock:
            if subscriber_id in self._subscribers:
                del self._subscribers[subscriber_id]
                logger.debug(f"Subscriber {subscriber_id} disconnected")

    def add_callback(self, callback: Callable[[Event], Any]) -> None:
        """Add a callback to be called for every event."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Event], Any]) -> None:
        """Remove a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        logger.debug(f"Publishing event: {event.type.value}")

        # Notify all subscribers
        async with self._lock:
            for subscriber_id, queue in list(self._subscribers.items()):
                try:
                    await queue.put(event)
                except Exception as e:
                    logger.error(f"Failed to send event to {subscriber_id}: {e}")

        # Call all callbacks
        for callback in self._callbacks:
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Callback error: {e}")

    async def emit(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> Event:
        """Convenience method to create and publish an event.

        Args:
            event_type: The type of event
            data: Event payload data
            project_id: Optional project ID for filtering

        Returns:
            The created event
        """
        event = Event(type=event_type, data=data or {}, project_id=project_id)
        await self.publish(event)
        return event

    @property
    def subscriber_count(self) -> int:
        """Get the number of active subscribers."""
        return len(self._subscribers)


# Global event bus instance
event_bus = EventBus()
