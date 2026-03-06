"""Unit tests for ble_receiver.lib.gatt_server module.

Uses mocks for the bless library since BLE hardware is not available
in the test environment. The bless module is mocked via sys.modules
because it is lazily imported inside GATTServer.start().
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the bless module before importing gatt_server
_bless_mock = MagicMock()
_bless_mock.GATTCharacteristicProperties.write = 0x08
_bless_mock.GATTCharacteristicProperties.write_without_response = 0x04
_bless_mock.GATTAttributePermissions.readable = 0x01
_bless_mock.GATTAttributePermissions.writeable = 0x02

_adv_mock = MagicMock()

sys.modules.setdefault("bless", _bless_mock)
sys.modules.setdefault("bless.backends", MagicMock())
sys.modules.setdefault("bless.backends.advertisement", _adv_mock)

from ble_receiver.lib.gatt_server import GATTServer  # noqa: E402


@pytest.fixture
def mock_bless_server():
    """Create a mocked BlessServer instance and patch it into the bless module."""
    server = AsyncMock()
    server.add_gatt = AsyncMock()
    server.start = AsyncMock()
    server.stop = AsyncMock()
    server.write_request_func = None

    with patch.object(_bless_mock, "BlessServer", return_value=server):
        yield server


class TestGATTServerInit:
    """Tests for GATTServer initialization."""

    def test_default_device_name(self) -> None:
        server = GATTServer()
        assert server._device_name == "BLEKeyReceiver"

    def test_custom_device_name(self) -> None:
        server = GATTServer(device_name="TestDevice")
        assert server._device_name == "TestDevice"

    def test_initial_state_not_running(self) -> None:
        server = GATTServer()
        assert server.is_running is False

    def test_callbacks_stored(self) -> None:
        on_write = MagicMock()
        on_connect = MagicMock()
        on_disconnect = MagicMock()
        server = GATTServer(
            on_write=on_write,
            on_connect=on_connect,
            on_disconnect=on_disconnect,
        )
        assert server._on_write is on_write
        assert server._on_connect is on_connect
        assert server._on_disconnect is on_disconnect

    def test_set_write_handler_updates_callback(self) -> None:
        """set_write_handler should replace callback."""
        server = GATTServer()
        callback = MagicMock()

        server.set_write_handler(callback)

        assert server.on_write is callback

    def test_set_write_handler_none_clears_callback(self) -> None:
        """set_write_handler(None) should clear callback."""
        callback = MagicMock()
        server = GATTServer(on_write=callback)

        server.set_write_handler(None)

        assert server.on_write is None


class TestGATTServerStart:
    """Tests for GATTServer start."""

    @pytest.mark.asyncio
    async def test_start_creates_server(self, mock_bless_server) -> None:
        server = GATTServer()
        await server.start()

        assert server.is_running is True
        mock_bless_server.add_gatt.assert_called_once()
        mock_bless_server.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_sets_write_handler(self, mock_bless_server) -> None:
        server = GATTServer()
        await server.start()

        # Bound methods create new objects each access, so compare underlying function
        assert mock_bless_server.write_request_func.__func__ is GATTServer._handle_write

    @pytest.mark.asyncio
    async def test_start_when_already_running_raises(
        self, mock_bless_server
    ) -> None:
        server = GATTServer()
        await server.start()

        with pytest.raises(RuntimeError, match="already running"):
            await server.start()

    @pytest.mark.asyncio
    async def test_gatt_definition_contains_correct_uuids(
        self, mock_bless_server
    ) -> None:
        from common.uuids import KEY_CHAR_UUID, KEY_SERVICE_UUID

        server = GATTServer()
        await server.start()

        gatt_arg = mock_bless_server.add_gatt.call_args[0][0]
        assert KEY_SERVICE_UUID in gatt_arg
        assert KEY_CHAR_UUID in gatt_arg[KEY_SERVICE_UUID]

    @pytest.mark.asyncio
    async def test_start_passes_advertisement_data(
        self, mock_bless_server
    ) -> None:
        """Test start() passes BlessAdvertisementData with service UUID."""
        from common.uuids import KEY_SERVICE_UUID

        # Reset the module-level mock to avoid cross-test contamination
        _adv_mock.BlessAdvertisementData.reset_mock()

        server = GATTServer()
        await server.start()

        mock_bless_server.start.assert_called_once()
        call_kwargs = mock_bless_server.start.call_args.kwargs
        adv_data = call_kwargs.get("advertisement_data")
        assert adv_data is not None

        # Verify BlessAdvertisementData was constructed with correct args
        adv_constructor = _adv_mock.BlessAdvertisementData
        adv_constructor.assert_called_once_with(
            local_name="BLEKeyReceiver",
            service_uuids=[KEY_SERVICE_UUID],
        )


class TestGATTServerStop:
    """Tests for GATTServer stop."""

    @pytest.mark.asyncio
    async def test_stop_running_server(self, mock_bless_server) -> None:
        server = GATTServer()
        await server.start()
        await server.stop()

        assert server.is_running is False
        mock_bless_server.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running_is_safe(self) -> None:
        server = GATTServer()
        await server.stop()  # Should not raise
        assert server.is_running is False


class TestGATTServerHandleWrite:
    """Tests for GATTServer write callback handling."""

    def test_handle_write_calls_on_write(self) -> None:
        on_write = MagicMock()
        server = GATTServer(on_write=on_write)

        mock_char = MagicMock()
        test_data = bytearray(b'{"t":"c","v":"a","p":true}')
        server._handle_write(mock_char, test_data)

        on_write.assert_called_once_with(b'{"t":"c","v":"a","p":true}')
        # characteristic.value is cleared after read to prevent data accumulation
        assert mock_char.value == b""

    def test_handle_write_without_callback(self) -> None:
        server = GATTServer()
        mock_char = MagicMock()

        # Should not raise even without on_write callback
        server._handle_write(mock_char, bytearray(b"test"))

    def test_handle_write_callback_exception_is_caught(self) -> None:
        on_write = MagicMock(side_effect=ValueError("test error"))
        server = GATTServer(on_write=on_write)
        mock_char = MagicMock()

        # Should not propagate the exception
        server._handle_write(mock_char, bytearray(b"test"))
        on_write.assert_called_once()
