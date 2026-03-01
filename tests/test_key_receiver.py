"""Unit tests for raspi_receiver.lib.key_receiver module.

Tests use a mocked GATTServer to verify KeyReceiver's deserialization
and callback dispatch logic without BLE hardware.
"""

import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.protocol import KeyEvent, KeyType, Modifiers
from raspi_receiver.lib.key_receiver import (
    DISCONNECT_TIMEOUT_SEC,
    KeyReceiver,
    KeyReceiverConfig,
    ReceiverStats,
)
from raspi_receiver.lib.types import ConnectionEvent


@pytest.fixture
def mock_gatt_server():
    """Create a mocked GATTServer that captures the on_write callback."""
    with patch("raspi_receiver.lib.key_receiver.GATTServer") as mock_cls:
        instance = AsyncMock()
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.is_running = False
        mock_cls.return_value = instance
        yield mock_cls, instance


class TestKeyReceiverInit:
    """Tests for KeyReceiver initialization."""

    def test_default_device_name(self, mock_gatt_server) -> None:
        mock_cls, _ = mock_gatt_server
        KeyReceiver()
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["device_name"] == "RasPi-KeyAgent"

    def test_custom_device_name(self, mock_gatt_server) -> None:
        mock_cls, _ = mock_gatt_server
        KeyReceiver(device_name="TestDevice")
        assert mock_cls.call_args.kwargs["device_name"] == "TestDevice"

    def test_callbacks_initially_none(self, mock_gatt_server) -> None:
        receiver = KeyReceiver()
        assert receiver.on_key_press is None
        assert receiver.on_key_release is None
        assert receiver.on_connect is None
        assert receiver.on_disconnect is None

    def test_not_connected_initially(self, mock_gatt_server) -> None:
        receiver = KeyReceiver()
        assert receiver.is_connected is False

    def test_config_exposed(self, mock_gatt_server) -> None:
        """Receiver should expose immutable config object."""
        receiver = KeyReceiver(config=KeyReceiverConfig(device_name="CfgDevice"))
        assert receiver.config.device_name == "CfgDevice"

    def test_config_timeout_override(self, mock_gatt_server) -> None:
        """Custom timeout config should be stored."""
        receiver = KeyReceiver(
            config=KeyReceiverConfig(disconnect_timeout_sec=7.5)
        )
        assert receiver.config.disconnect_timeout_sec == 7.5

    def test_register_callbacks(self, mock_gatt_server) -> None:
        """register_callbacks should set provided handlers only."""
        receiver = KeyReceiver()
        on_press = MagicMock()
        on_disconnect = MagicMock()

        receiver.register_callbacks(
            on_key_press=on_press,
            on_disconnect=on_disconnect,
        )

        assert receiver.on_key_press is on_press
        assert receiver.on_disconnect is on_disconnect
        assert receiver.on_key_release is None
        assert receiver.on_connect is None

    def test_clear_callbacks(self, mock_gatt_server) -> None:
        """clear_callbacks should unset all handlers."""
        receiver = KeyReceiver()
        receiver.register_callbacks(
            on_key_press=MagicMock(),
            on_key_release=MagicMock(),
            on_connect=MagicMock(),
            on_disconnect=MagicMock(),
        )

        receiver.clear_callbacks()

        assert receiver.on_key_press is None
        assert receiver.on_key_release is None
        assert receiver.on_connect is None
        assert receiver.on_disconnect is None


class TestKeyReceiverStartStop:
    """Tests for KeyReceiver start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_delegates_to_gatt_server(self, mock_gatt_server) -> None:
        _, instance = mock_gatt_server
        receiver = KeyReceiver()
        instance.is_running = True
        await receiver.start()
        instance.start.assert_called_once()
        assert receiver.is_running is True

    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(self, mock_gatt_server) -> None:
        """start should raise when receiver is already running."""
        _, instance = mock_gatt_server
        receiver = KeyReceiver()
        instance.is_running = True
        await receiver.start()

        with pytest.raises(RuntimeError, match="already running"):
            await receiver.start()

    @pytest.mark.asyncio
    async def test_stop_delegates_to_gatt_server(self, mock_gatt_server) -> None:
        _, instance = mock_gatt_server
        receiver = KeyReceiver()
        instance.is_running = True
        await receiver.start()
        instance.is_running = False
        await receiver.stop()
        instance.stop.assert_called_once()
        assert receiver.is_running is False


class TestKeyReceiverHandleWrite:
    """Tests for KeyReceiver write handling and callback dispatch."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        """Create a KeyReceiver and extract the on_write handler passed to GATTServer."""
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    def test_key_press_callback_fires(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        press_handler.assert_called_once()
        received_event = press_handler.call_args[0][0]
        assert received_event.key_type == KeyType.CHAR
        assert received_event.value == "a"
        assert received_event.press is True

    def test_key_release_callback_fires(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        release_handler = MagicMock()
        receiver.on_key_release = release_handler

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=False)
        on_write(event.serialize())

        release_handler.assert_called_once()
        received_event = release_handler.call_args[0][0]
        assert received_event.press is False

    def test_special_key_event(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        event = KeyEvent(key_type=KeyType.SPECIAL, value="enter", press=True)
        on_write(event.serialize())

        received_event = press_handler.call_args[0][0]
        assert received_event.key_type == KeyType.SPECIAL
        assert received_event.value == "enter"

    def test_modifier_key_event(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        event = KeyEvent(key_type=KeyType.MODIFIER, value="shift", press=True)
        on_write(event.serialize())

        received_event = press_handler.call_args[0][0]
        assert received_event.key_type == KeyType.MODIFIER
        assert received_event.value == "shift"

    def test_event_with_modifiers(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        event = KeyEvent(
            key_type=KeyType.CHAR,
            value="A",
            press=True,
            modifiers=Modifiers(shift=True),
            timestamp=1700000000.0,
        )
        on_write(event.serialize())

        received_event = press_handler.call_args[0][0]
        assert received_event.modifiers is not None
        assert received_event.modifiers.shift is True
        assert received_event.timestamp == 1700000000.0

    def test_no_callback_set_does_not_raise(self, mock_gatt_server) -> None:
        _, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())  # Should not raise

    def test_invalid_data_skipped(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        on_write(b"invalid json data")

        press_handler.assert_not_called()

    def test_empty_data_skipped(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        on_write(b"")

        press_handler.assert_not_called()

    def test_callback_exception_is_caught(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        receiver.on_key_press = MagicMock(side_effect=RuntimeError("app error"))

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())  # Should not propagate


class TestKeyReceiverConnection:
    """Tests for KeyReceiver connection state tracking."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    def test_first_write_sets_connected(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        assert receiver.is_connected is False

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        assert receiver.is_connected is True

    def test_on_connect_callback_fires_on_first_write(
        self, mock_gatt_server
    ) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        connect_handler = MagicMock()
        receiver.on_connect = connect_handler

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        connect_handler.assert_called_once()
        conn_event = connect_handler.call_args[0][0]
        assert isinstance(conn_event, ConnectionEvent)
        assert conn_event.connected is True

    def test_on_connect_only_fires_once(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        connect_handler = MagicMock()
        receiver.on_connect = connect_handler

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        on_write(event.serialize())
        on_write(event.serialize())

        connect_handler.assert_called_once()

    def test_connect_callback_exception_is_caught(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        receiver.on_connect = MagicMock(side_effect=RuntimeError("connect error"))

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())  # Should not propagate

    @pytest.mark.asyncio
    async def test_stop_resets_connected_state(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        assert receiver.is_connected is True

        await receiver.stop()
        assert receiver.is_connected is False


class TestKeyReceiverHeartbeat:
    """Tests for heartbeat event filtering."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    def test_heartbeat_not_propagated_to_key_press(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        press_handler = MagicMock()
        receiver.on_key_press = press_handler

        hb = KeyEvent.heartbeat()
        on_write(hb.serialize())

        press_handler.assert_not_called()

    def test_heartbeat_not_propagated_to_key_release(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        release_handler = MagicMock()
        receiver.on_key_release = release_handler

        hb = KeyEvent.heartbeat()
        on_write(hb.serialize())

        release_handler.assert_not_called()

    def test_heartbeat_triggers_connect_on_first_write(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        connect_handler = MagicMock()
        receiver.on_connect = connect_handler

        hb = KeyEvent.heartbeat()
        on_write(hb.serialize())

        connect_handler.assert_called_once()
        assert receiver.is_connected is True

    def test_heartbeat_updates_last_receive_time(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        before = time.monotonic()
        hb = KeyEvent.heartbeat()
        on_write(hb.serialize())
        after = time.monotonic()

        assert before <= receiver._last_receive_time <= after


class TestKeyReceiverTimeout:
    """Tests for timeout-based disconnect detection."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    @pytest.mark.asyncio
    async def test_timeout_fires_on_disconnect(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        disconnect_handler = MagicMock()
        receiver.on_disconnect = disconnect_handler

        # Simulate a connection
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        assert receiver.is_connected is True

        # Simulate time passing beyond timeout
        receiver._last_receive_time = time.monotonic() - DISCONNECT_TIMEOUT_SEC - 1

        # Start the timeout monitor and let it run one cycle
        receiver._loop = MagicMock()
        task = receiver._timeout_monitor()

        # Run one iteration (sleep(1.0) will actually run)
        # Use asyncio to run just enough for one check
        import asyncio

        monitor_task = asyncio.create_task(task)
        await asyncio.sleep(1.5)  # Let monitor run one cycle
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        assert receiver.is_connected is False
        disconnect_handler.assert_called_once()
        conn_event = disconnect_handler.call_args[0][0]
        assert isinstance(conn_event, ConnectionEvent)
        assert conn_event.connected is False

    @pytest.mark.asyncio
    async def test_no_timeout_when_receiving_data(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        disconnect_handler = MagicMock()
        receiver.on_disconnect = disconnect_handler

        # Simulate a connection with recent data
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        receiver._loop = MagicMock()
        import asyncio

        monitor_task = asyncio.create_task(receiver._timeout_monitor())
        await asyncio.sleep(1.5)
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        assert receiver.is_connected is True
        disconnect_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_after_timeout(self, mock_gatt_server) -> None:
        """After timeout disconnect, a new write should trigger on_connect again."""
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        connect_handler = MagicMock()
        disconnect_handler = MagicMock()
        receiver.on_connect = connect_handler
        receiver.on_disconnect = disconnect_handler

        # First connection
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        assert connect_handler.call_count == 1

        # Simulate timeout disconnect
        receiver._connected = False

        # New write should re-trigger on_connect
        on_write(event.serialize())
        assert connect_handler.call_count == 2
        assert receiver.is_connected is True

    @pytest.mark.asyncio
    async def test_start_creates_timeout_task(self, mock_gatt_server) -> None:
        receiver, _ = self._get_receiver_with_write_handler(mock_gatt_server)
        await receiver.start()

        assert receiver._timeout_task is not None
        assert not receiver._timeout_task.done()

        await receiver.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_timeout_task(self, mock_gatt_server) -> None:
        receiver, _ = self._get_receiver_with_write_handler(mock_gatt_server)
        await receiver.start()

        timeout_task = receiver._timeout_task
        await receiver.stop()

        assert receiver._timeout_task is None
        assert timeout_task.cancelled()


class TestKeyReceiverConnLock:
    """Tests for Fix 4: _conn_lock thread safety on _connected flag."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    def test_conn_lock_exists(self, mock_gatt_server) -> None:
        """Test that KeyReceiver has a _conn_lock attribute."""
        receiver = KeyReceiver()
        assert hasattr(receiver, "_conn_lock")
        assert isinstance(receiver._conn_lock, type(threading.Lock()))

    def test_concurrent_write_and_timeout_no_duplicate_callbacks(
        self, mock_gatt_server
    ) -> None:
        """Test that on_connect does not fire twice under concurrent access."""
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        connect_handler = MagicMock()
        receiver.on_connect = connect_handler

        # Simulate many concurrent writes from different threads
        barrier = threading.Barrier(10)
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        data = event.serialize()

        def write_from_thread() -> None:
            barrier.wait()
            on_write(data)

        threads = [threading.Thread(target=write_from_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # on_connect should fire exactly once despite concurrent writes
        connect_handler.assert_called_once()

    def test_stop_with_conn_lock(self, mock_gatt_server) -> None:
        """Test stop() properly resets _connected under lock."""
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        assert receiver.is_connected is True

        import asyncio
        asyncio.run(receiver.stop())
        assert receiver.is_connected is False


class TestReceiverStats:
    """Tests for ReceiverStats counter tracking."""

    def _get_receiver_with_write_handler(self, mock_gatt_server):
        mock_cls, _ = mock_gatt_server
        receiver = KeyReceiver()
        on_write = mock_cls.call_args.kwargs["on_write"]
        return receiver, on_write

    def test_initial_stats_are_zero(self, mock_gatt_server) -> None:
        receiver = KeyReceiver()
        stats = receiver.stats
        assert stats.key_events_received == 0
        assert stats.heartbeats_received == 0
        assert stats.deserialize_errors == 0
        assert stats.connections == 0
        assert stats.disconnections == 0
        assert stats.last_receive_time == 0.0

    def test_stats_returns_copy(self, mock_gatt_server) -> None:
        receiver = KeyReceiver()
        stats1 = receiver.stats
        stats1.key_events_received = 999
        stats2 = receiver.stats
        assert stats2.key_events_received == 0

    def test_key_event_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        on_write(event.serialize())

        stats = receiver.stats
        assert stats.key_events_received == 2

    def test_key_release_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=False)
        on_write(event.serialize())

        stats = receiver.stats
        assert stats.key_events_received == 1

    def test_heartbeat_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        hb = KeyEvent.heartbeat()
        on_write(hb.serialize())
        on_write(hb.serialize())
        on_write(hb.serialize())

        stats = receiver.stats
        assert stats.heartbeats_received == 3
        assert stats.key_events_received == 0

    def test_deserialize_error_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        on_write(b"invalid json")
        on_write(b"also bad")

        stats = receiver.stats
        assert stats.deserialize_errors == 2

    def test_connection_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        stats = receiver.stats
        assert stats.connections == 1

    def test_reconnection_increments_counter(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        assert receiver.stats.connections == 1

        # Simulate disconnect
        receiver._connected = False

        # Reconnect
        on_write(event.serialize())
        assert receiver.stats.connections == 2

    @pytest.mark.asyncio
    async def test_timeout_disconnect_increments_counter(
        self, mock_gatt_server
    ) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())

        # Force timeout
        receiver._last_receive_time = time.monotonic() - DISCONNECT_TIMEOUT_SEC - 1
        receiver._loop = MagicMock()

        import asyncio

        monitor_task = asyncio.create_task(receiver._timeout_monitor())
        await asyncio.sleep(1.5)
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        assert receiver.stats.disconnections == 1

    def test_last_receive_time_updated(self, mock_gatt_server) -> None:
        receiver, on_write = self._get_receiver_with_write_handler(mock_gatt_server)

        before = time.monotonic()
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        on_write(event.serialize())
        after = time.monotonic()

        stats = receiver.stats
        assert before <= stats.last_receive_time <= after
