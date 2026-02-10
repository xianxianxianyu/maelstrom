"""Unit tests for EventBus.

Validates:
- EventBus subscribe/unsubscribe/publish methods (Requirements 1.7, 5.6)
- Module-level singleton getter (get_event_bus)
- Multiple subscribers receive the same event
- Unsubscribed queues no longer receive events
- Publishing to a task with no subscribers is a no-op
"""

import asyncio

import pytest

from agent.event_bus import EventBus, get_event_bus, _bus
import agent.event_bus as event_bus_module


# ---------------------------------------------------------------------------
# EventBus construction
# ---------------------------------------------------------------------------


class TestEventBusInit:
    """Tests for EventBus initialization."""

    def test_initial_subscribers_empty(self):
        """A new EventBus should have no subscribers."""
        bus = EventBus()
        assert bus._subscribers == {}


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------


class TestEventBusSubscribe:
    """Tests for EventBus.subscribe()."""

    def test_subscribe_returns_queue(self):
        """subscribe() should return an asyncio.Queue."""
        bus = EventBus()
        queue = bus.subscribe("task-001")
        assert isinstance(queue, asyncio.Queue)

    def test_subscribe_registers_queue(self):
        """subscribe() should add the queue to the subscribers dict."""
        bus = EventBus()
        queue = bus.subscribe("task-001")
        assert "task-001" in bus._subscribers
        assert queue in bus._subscribers["task-001"]

    def test_subscribe_multiple_to_same_task(self):
        """Multiple subscribes to the same task_id should create separate queues."""
        bus = EventBus()
        q1 = bus.subscribe("task-001")
        q2 = bus.subscribe("task-001")
        assert q1 is not q2
        assert len(bus._subscribers["task-001"]) == 2

    def test_subscribe_different_tasks(self):
        """Subscribing to different task_ids should be independent."""
        bus = EventBus()
        q1 = bus.subscribe("task-001")
        q2 = bus.subscribe("task-002")
        assert len(bus._subscribers["task-001"]) == 1
        assert len(bus._subscribers["task-002"]) == 1
        assert q1 is not q2


# ---------------------------------------------------------------------------
# unsubscribe
# ---------------------------------------------------------------------------


class TestEventBusUnsubscribe:
    """Tests for EventBus.unsubscribe()."""

    def test_unsubscribe_removes_queue(self):
        """unsubscribe() should remove the specific queue from subscribers."""
        bus = EventBus()
        queue = bus.subscribe("task-001")
        bus.unsubscribe("task-001", queue)
        assert queue not in bus._subscribers["task-001"]

    def test_unsubscribe_leaves_other_queues(self):
        """unsubscribe() should only remove the specified queue, not others."""
        bus = EventBus()
        q1 = bus.subscribe("task-001")
        q2 = bus.subscribe("task-001")
        bus.unsubscribe("task-001", q1)
        assert q1 not in bus._subscribers["task-001"]
        assert q2 in bus._subscribers["task-001"]

    def test_unsubscribe_nonexistent_task_is_noop(self):
        """unsubscribe() with unknown task_id should not raise."""
        bus = EventBus()
        queue = asyncio.Queue()
        # Should not raise
        bus.unsubscribe("nonexistent", queue)

    def test_unsubscribe_nonexistent_queue_is_noop(self):
        """unsubscribe() with a queue not in the list should not raise."""
        bus = EventBus()
        bus.subscribe("task-001")
        other_queue = asyncio.Queue()
        # Should not raise
        bus.unsubscribe("task-001", other_queue)


# ---------------------------------------------------------------------------
# publish
# ---------------------------------------------------------------------------


class TestEventBusPublish:
    """Tests for EventBus.publish()."""

    @pytest.mark.asyncio
    async def test_publish_delivers_event_to_subscriber(self):
        """publish() should put the event into the subscriber's queue."""
        bus = EventBus()
        queue = bus.subscribe("task-001")
        event = {"agent": "translation", "stage": "analysis", "progress": 10}

        await bus.publish("task-001", event)

        result = queue.get_nowait()
        assert result == event

    @pytest.mark.asyncio
    async def test_publish_delivers_to_all_subscribers(self):
        """publish() should deliver the event to all subscribers of the task."""
        bus = EventBus()
        q1 = bus.subscribe("task-001")
        q2 = bus.subscribe("task-001")
        event = {"stage": "translating", "progress": 50}

        await bus.publish("task-001", event)

        assert q1.get_nowait() == event
        assert q2.get_nowait() == event

    @pytest.mark.asyncio
    async def test_publish_does_not_cross_tasks(self):
        """publish() to one task should not affect subscribers of another task."""
        bus = EventBus()
        q1 = bus.subscribe("task-001")
        q2 = bus.subscribe("task-002")
        event = {"stage": "complete", "progress": 100}

        await bus.publish("task-001", event)

        assert q1.get_nowait() == event
        assert q2.empty()

    @pytest.mark.asyncio
    async def test_publish_no_subscribers_is_noop(self):
        """publish() to a task with no subscribers should not raise."""
        bus = EventBus()
        # Should not raise
        await bus.publish("nonexistent", {"stage": "test"})

    @pytest.mark.asyncio
    async def test_publish_after_unsubscribe_does_not_deliver(self):
        """After unsubscribe(), the queue should no longer receive events."""
        bus = EventBus()
        queue = bus.subscribe("task-001")
        bus.unsubscribe("task-001", queue)

        await bus.publish("task-001", {"stage": "test"})

        assert queue.empty()

    @pytest.mark.asyncio
    async def test_publish_multiple_events_in_order(self):
        """Multiple publish() calls should deliver events in FIFO order."""
        bus = EventBus()
        queue = bus.subscribe("task-001")

        events = [
            {"stage": "analysis", "progress": 10},
            {"stage": "translating", "progress": 50},
            {"stage": "complete", "progress": 100},
        ]
        for event in events:
            await bus.publish("task-001", event)

        received = []
        while not queue.empty():
            received.append(queue.get_nowait())

        assert received == events


# ---------------------------------------------------------------------------
# get_event_bus singleton
# ---------------------------------------------------------------------------


class TestGetEventBus:
    """Tests for the module-level get_event_bus() singleton."""

    def setup_method(self):
        """Reset the module-level singleton before each test."""
        event_bus_module._bus = None

    def test_get_event_bus_returns_event_bus(self):
        """get_event_bus() should return an EventBus instance."""
        bus = get_event_bus()
        assert isinstance(bus, EventBus)

    def test_get_event_bus_returns_same_instance(self):
        """get_event_bus() should return the same instance on repeated calls."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_get_event_bus_creates_new_after_reset(self):
        """After resetting _bus to None, get_event_bus() should create a new instance."""
        bus1 = get_event_bus()
        event_bus_module._bus = None
        bus2 = get_event_bus()
        assert bus1 is not bus2
