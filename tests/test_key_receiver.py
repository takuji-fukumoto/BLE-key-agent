"""Unit tests for raspi_receiver.lib.key_receiver module.

Tests use a mocked GATTServer to verify KeyReceiver's deserialization
and callback dispatch logic without BLE hardware.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.protocol import KeyEvent, KeyType, Modifiers
from raspi_receiver.lib.key_receiver import KeyReceiver
from raspi_receiver.lib.types import ConnectionEvent


@pytest.fixture
def mock_gatt_server():
    """Create a mocked GATTServer that captures the on_write callback."""
    with patch("raspi_receiver.lib.key_receiver.GATTServer") as mock_cls:
        instance = AsyncMock()
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
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


class TestKeyReceiverStartStop:
    """Tests for KeyReceiver start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_delegates_to_gatt_server(self, mock_gatt_server) -> None:
        _, instance = mock_gatt_server
        receiver = KeyReceiver()
        await receiver.start()
        instance.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_delegates_to_gatt_server(self, mock_gatt_server) -> None:
        _, instance = mock_gatt_server
        receiver = KeyReceiver()
        await receiver.stop()
        instance.stop.assert_called_once()


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
