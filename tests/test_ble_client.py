"""Unit tests for mac_agent.ble_client module.

Uses mocks for the bleak library since BLE hardware is not available
in the test environment. The bleak module is mocked to avoid dependency
on actual Bluetooth adapters.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the bleak module before importing ble_client
_bleak_mock = MagicMock()
sys.modules.setdefault("bleak", _bleak_mock)
sys.modules.setdefault("bleak.backends.device", _bleak_mock.backends.device)

from mac_agent.ble_client import (  # noqa: E402
    BleClient,
    BleDevice,
    STATUS_CONNECTED,
    STATUS_CONNECTING,
    STATUS_DISCONNECTED,
    STATUS_RECONNECTING,
    STATUS_SCANNING,
)
from common.protocol import KeyEvent, KeyType  # noqa: E402
from common.uuids import KEY_CHAR_UUID, KEY_SERVICE_UUID  # noqa: E402


class TestBleClientInit:
    """Tests for BleClient initialization."""

    def test_initialization(self) -> None:
        """Test BleClient initializes with correct defaults."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        assert client._on_status_change is callback
        assert client._status == STATUS_DISCONNECTED
        assert client._client is None
        assert client._connected_device is None
        assert client._reconnect_task is None
        assert client._last_address is None

    def test_status_property(self) -> None:
        """Test status property returns current status."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        assert client.status == STATUS_DISCONNECTED

    def test_connected_device_property_none(self) -> None:
        """Test connected_device is None when not connected."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        assert client.connected_device is None


class TestBleDeviceDataclass:
    """Tests for BleDevice dataclass."""

    def test_ble_device_creation(self) -> None:
        """Test BleDevice can be created with fields."""
        device = BleDevice(name="TestDevice", address="AA:BB:CC:DD:EE:FF", rssi=-50)

        assert device.name == "TestDevice"
        assert device.address == "AA:BB:CC:DD:EE:FF"
        assert device.rssi == -50


class TestBleClientScan:
    """Tests for scan() method."""

    @pytest.mark.asyncio
    async def test_scan_returns_devices(self) -> None:
        """Test scan() returns sorted devices."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        # Mock BleakScanner.discover
        mock_device1 = MagicMock()
        mock_device1.name = "Device1"
        mock_device1.address = "AA:BB:CC:DD:EE:FF"

        mock_adv1 = MagicMock()
        mock_adv1.local_name = "Device1"
        mock_adv1.rssi = -50

        mock_device2 = MagicMock()
        mock_device2.name = "Device2"
        mock_device2.address = "11:22:33:44:55:66"

        mock_adv2 = MagicMock()
        mock_adv2.local_name = "Device2"
        mock_adv2.rssi = -70

        with patch('bleak.BleakScanner') as mock_scanner:
            mock_scanner.discover = AsyncMock(return_value={
                "key1": (mock_device1, mock_adv1),
                "key2": (mock_device2, mock_adv2),
            })

            devices = await client.scan(timeout=5.0)

        assert len(devices) == 2
        # Should be sorted by RSSI (strongest first)
        assert devices[0].name == "Device1"
        assert devices[0].rssi == -50
        assert devices[1].name == "Device2"
        assert devices[1].rssi == -70

    @pytest.mark.asyncio
    async def test_scan_updates_status(self) -> None:
        """Test scan() updates status during operation."""
        status_changes = []

        def track_status(status: str):
            status_changes.append(status)

        client = BleClient(on_status_change=track_status)

        with patch('bleak.BleakScanner') as mock_scanner:
            mock_scanner.discover = AsyncMock(return_value={})

            await client.scan(timeout=5.0)

        assert STATUS_SCANNING in status_changes
        assert STATUS_DISCONNECTED in status_changes


class TestBleClientConnect:
    """Tests for connect() method."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Test successful connection flow."""
        status_changes = []

        def track_status(status: str):
            status_changes.append(status)

        client = BleClient(on_status_change=track_status)

        # Mock device discovery
        mock_device = MagicMock()
        mock_device.name = "TestDevice"
        mock_device.address = "AA:BB:CC:DD:EE:FF"

        # Mock BleakClient instance
        mock_bleak_client = AsyncMock()
        mock_bleak_client.connect = AsyncMock()
        mock_bleak_client.is_connected = True
        mock_bleak_client.mtu_size = 247

        # Mock services to include KEY_SERVICE_UUID
        mock_service = MagicMock()
        mock_service.uuid = KEY_SERVICE_UUID
        mock_char = MagicMock()
        mock_char.uuid = KEY_CHAR_UUID
        mock_char.properties = ["write", "write-without-response"]
        mock_service.characteristics = [mock_char]
        mock_bleak_client.services = [mock_service]

        with patch('bleak.BleakScanner') as mock_scanner, \
             patch('bleak.BleakClient', return_value=mock_bleak_client):

            mock_scanner.find_device_by_address = AsyncMock(return_value=mock_device)

            success = await client.connect("AA:BB:CC:DD:EE:FF")

        assert success is True
        assert client.status == STATUS_CONNECTED
        assert client._last_address == "AA:BB:CC:DD:EE:FF"
        assert client.connected_device is not None
        assert client.connected_device.address == "AA:BB:CC:DD:EE:FF"

        assert STATUS_CONNECTING in status_changes
        assert STATUS_CONNECTED in status_changes

    @pytest.mark.asyncio
    async def test_connect_device_not_found(self) -> None:
        """Test connection fails when device not found."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        with patch('bleak.BleakScanner') as mock_scanner:
            mock_scanner.find_device_by_address = AsyncMock(return_value=None)

            success = await client.connect("AA:BB:CC:DD:EE:FF")

        assert success is False
        assert client.status == STATUS_DISCONNECTED

    @pytest.mark.asyncio
    async def test_connect_missing_key_service(self) -> None:
        """Test connection fails when KEY_SERVICE_UUID not found."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        mock_device = MagicMock()
        mock_device.name = "TestDevice"
        mock_device.address = "AA:BB:CC:DD:EE:FF"

        mock_bleak_client = AsyncMock()
        mock_bleak_client.connect = AsyncMock()
        mock_bleak_client.disconnect = AsyncMock()
        mock_bleak_client.is_connected = True

        # Services without KEY_SERVICE_UUID
        mock_service = MagicMock()
        mock_service.uuid = "00000000-0000-0000-0000-000000000000"
        mock_bleak_client.services = [mock_service]

        with patch('bleak.BleakScanner') as mock_scanner, \
             patch('bleak.BleakClient', return_value=mock_bleak_client):

            mock_scanner.find_device_by_address = AsyncMock(return_value=mock_device)

            success = await client.connect("AA:BB:CC:DD:EE:FF")

        assert success is False
        assert client.status == STATUS_DISCONNECTED
        mock_bleak_client.disconnect.assert_called_once()


class TestBleClientSendKey:
    """Tests for send_key() method."""

    @pytest.mark.asyncio
    async def test_send_key_when_connected(self) -> None:
        """Test send_key() succeeds when connected."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        mock_bleak_client = AsyncMock()
        mock_bleak_client.is_connected = True
        mock_bleak_client.write_gatt_char = AsyncMock()

        client._client = mock_bleak_client

        event = KeyEvent(
            key_type=KeyType.CHAR,
            value='a',
            press=True
        )

        success = await client.send_key(event)

        assert success is True
        mock_bleak_client.write_gatt_char.assert_called_once()
        call_args = mock_bleak_client.write_gatt_char.call_args
        assert call_args.args[0] == KEY_CHAR_UUID
        assert call_args.kwargs['response'] is False

    @pytest.mark.asyncio
    async def test_send_key_when_not_connected(self) -> None:
        """Test send_key() returns False when not connected."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        event = KeyEvent(key_type=KeyType.CHAR, value='a', press=True)
        success = await client.send_key(event)

        assert success is False

    @pytest.mark.asyncio
    async def test_send_key_exception_handling(self) -> None:
        """Test send_key() handles exceptions gracefully."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        mock_bleak_client = AsyncMock()
        mock_bleak_client.is_connected = True
        mock_bleak_client.write_gatt_char = AsyncMock(side_effect=Exception("Write failed"))

        client._client = mock_bleak_client

        event = KeyEvent(key_type=KeyType.CHAR, value='a', press=True)
        success = await client.send_key(event)

        assert success is False


class TestBleClientDisconnect:
    """Tests for disconnect() method."""

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self) -> None:
        """Test disconnect() cleans up client and updates status."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        mock_bleak_client = AsyncMock()
        mock_bleak_client.disconnect = AsyncMock()
        client._client = mock_bleak_client
        client._connected_device = BleDevice("Test", "AA:BB:CC:DD:EE:FF", -50)

        await client.disconnect()

        assert client._client is None
        assert client._connected_device is None
        assert client.status == STATUS_DISCONNECTED
        mock_bleak_client.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_cancels_reconnect_task(self) -> None:
        """Test disconnect() cancels any pending reconnection."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        # Create a cancellable task
        async def dummy_coro():
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy_coro())
        client._reconnect_task = task

        await client.disconnect()

        assert task.cancelled()


class TestBleClientReconnection:
    """Tests for automatic reconnection logic."""

    @pytest.mark.asyncio
    async def test_reconnection_backoff(self) -> None:
        """Test reconnection implements exponential backoff."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        client._last_address = "AA:BB:CC:DD:EE:FF"

        reconnect_delays = []

        async def mock_sleep(delay):
            reconnect_delays.append(delay)

        # Simulate failed reconnection attempts
        client.connect = AsyncMock(side_effect=[False, False, True])

        with patch('mac_agent.ble_client.asyncio.sleep', side_effect=mock_sleep):
            await client._reconnect_loop()

        # Verify exponential backoff: 1s, 2s
        assert len(reconnect_delays) == 3
        assert reconnect_delays[0] == 1.0
        assert reconnect_delays[1] == 2.0
        assert reconnect_delays[2] == 4.0

    @pytest.mark.asyncio
    async def test_on_disconnect_triggers_reconnection(self) -> None:
        """Test _on_disconnect() starts reconnection."""
        callback = MagicMock()
        client = BleClient(on_status_change=callback)

        client._last_address = "AA:BB:CC:DD:EE:FF"

        mock_client = MagicMock()

        with patch.object(asyncio, 'get_event_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_task = MagicMock()
            mock_event_loop.create_task = MagicMock(return_value=mock_task)
            mock_loop.return_value = mock_event_loop

            client._on_disconnect(mock_client)

        assert client._reconnect_task is mock_task
        mock_event_loop.create_task.assert_called_once()


class TestCallbackExceptionIsolation:
    """Tests for on_status_change callback exception handling."""

    def test_status_change_callback_exception_isolated(self) -> None:
        """Test exceptions in on_status_change don't crash client."""
        def bad_callback(status: str):
            raise ValueError("Bad callback")

        client = BleClient(on_status_change=bad_callback)

        # Should not raise, exception should be logged
        client._set_status(STATUS_CONNECTED)

        # Status should still be updated
        assert client.status == STATUS_CONNECTED

    def test_status_change_without_callback(self) -> None:
        """Test _set_status works when callback is None."""
        client = BleClient(on_status_change=None)

        client._set_status(STATUS_CONNECTED)

        assert client.status == STATUS_CONNECTED
