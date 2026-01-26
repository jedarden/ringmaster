"""Tests for the event bus system."""

import asyncio

import pytest

from ringmaster.events import Event, EventBus, EventType


@pytest.fixture
def event_bus_fixture() -> EventBus:
    """Create a fresh event bus for each test."""
    return EventBus()


async def test_subscribe_and_receive(event_bus_fixture: EventBus) -> None:
    """Test that subscribers receive published events."""
    queue = await event_bus_fixture.subscribe("test-sub-1")

    # Publish an event
    event = Event(type=EventType.TASK_CREATED, data={"task_id": "test-123"})
    await event_bus_fixture.publish(event)

    # Check we received it
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.type == EventType.TASK_CREATED
    assert received.data["task_id"] == "test-123"


async def test_unsubscribe(event_bus_fixture: EventBus) -> None:
    """Test that unsubscribed clients don't receive events."""
    queue = await event_bus_fixture.subscribe("test-sub-2")

    # Unsubscribe
    await event_bus_fixture.unsubscribe("test-sub-2")

    # Publish an event
    event = Event(type=EventType.TASK_CREATED, data={})
    await event_bus_fixture.publish(event)

    # Queue should be empty
    assert queue.empty()


async def test_emit_convenience_method(event_bus_fixture: EventBus) -> None:
    """Test the emit convenience method."""
    queue = await event_bus_fixture.subscribe("test-sub-3")

    # Emit an event
    emitted = await event_bus_fixture.emit(
        EventType.WORKER_CONNECTED,
        data={"worker_id": "worker-abc"},
        project_id="project-123",
    )

    # Check the returned event
    assert emitted.type == EventType.WORKER_CONNECTED
    assert emitted.data["worker_id"] == "worker-abc"
    assert emitted.project_id == "project-123"

    # Check we received it
    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.id == emitted.id


async def test_multiple_subscribers(event_bus_fixture: EventBus) -> None:
    """Test that multiple subscribers all receive events."""
    queue1 = await event_bus_fixture.subscribe("sub-1")
    queue2 = await event_bus_fixture.subscribe("sub-2")
    queue3 = await event_bus_fixture.subscribe("sub-3")

    assert event_bus_fixture.subscriber_count == 3

    # Publish event
    await event_bus_fixture.emit(EventType.QUEUE_UPDATED, data={"count": 5})

    # All should receive
    for queue in [queue1, queue2, queue3]:
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.type == EventType.QUEUE_UPDATED
        assert received.data["count"] == 5


async def test_callback_execution(event_bus_fixture: EventBus) -> None:
    """Test that callbacks are called for events."""
    received_events: list[Event] = []

    def callback(event: Event) -> None:
        received_events.append(event)

    event_bus_fixture.add_callback(callback)

    # Emit event
    await event_bus_fixture.emit(EventType.SCHEDULER_STARTED)

    # Check callback was called
    assert len(received_events) == 1
    assert received_events[0].type == EventType.SCHEDULER_STARTED

    # Remove callback
    event_bus_fixture.remove_callback(callback)

    # Emit another event
    await event_bus_fixture.emit(EventType.SCHEDULER_STOPPED)

    # Should not receive new event
    assert len(received_events) == 1


async def test_async_callback(event_bus_fixture: EventBus) -> None:
    """Test that async callbacks work correctly."""
    received: list[Event] = []

    async def async_callback(event: Event) -> None:
        await asyncio.sleep(0.01)  # Simulate async work
        received.append(event)

    event_bus_fixture.add_callback(async_callback)

    await event_bus_fixture.emit(EventType.TASK_COMPLETED, data={"success": True})

    assert len(received) == 1
    assert received[0].data["success"] is True


def test_event_to_json() -> None:
    """Test Event serialization to JSON."""
    event = Event(
        type=EventType.TASK_UPDATED,
        data={"status": "completed"},
        project_id="proj-123",
    )

    json_dict = event.to_json()

    assert json_dict["type"] == "task.updated"
    assert json_dict["data"]["status"] == "completed"
    assert json_dict["project_id"] == "proj-123"
    assert "timestamp" in json_dict
    assert "id" in json_dict


def test_event_type_values() -> None:
    """Test that EventType enum has expected values."""
    assert EventType.TASK_CREATED.value == "task.created"
    assert EventType.WORKER_CONNECTED.value == "worker.connected"
    assert EventType.SCHEDULER_STARTED.value == "scheduler.started"
