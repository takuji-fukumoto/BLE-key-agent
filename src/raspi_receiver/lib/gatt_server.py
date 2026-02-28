"""BLE GATT server wrapper using the bless library.

Manages the BLE GATT server lifecycle (start/stop/advertise) and
delegates write events to a registered callback. Based on the PoC
implementation at poc/ble_gatt/peripheral_raspi.py.

The bless library is imported lazily at runtime since it is a
Raspberry Pi-only dependency (not available on Mac dev environments).

See docs/spec-raspi-receiver.md section 3.2 for the interface specification.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from common.uuids import DEVICE_NAME, KEY_CHAR_UUID, KEY_SERVICE_UUID

if TYPE_CHECKING:
    from bless import BlessGATTCharacteristic, BlessServer

logger = logging.getLogger(__name__)


class GATTServer:
    """BLE GATT server for receiving key events from Mac agent.

    Wraps the bless BlessServer to provide a simplified interface for
    the key receiver library. Handles GATT service/characteristic setup,
    advertising, and write event dispatch.

    Args:
        device_name: BLE advertised device name.
        on_write: Callback invoked when data is written to the key characteristic.
        on_connect: Callback invoked when a client connects (future use).
        on_disconnect: Callback invoked when a client disconnects (future use).
    """

    def __init__(
        self,
        device_name: str = DEVICE_NAME,
        on_write: Optional[Callable[[bytes], None]] = None,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._device_name = device_name
        self._on_write = on_write
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._server: Optional[BlessServer] = None
        self._running = False

    async def start(self) -> None:
        """Start the GATT server and begin advertising.

        Sets up the GATT service with the key characteristic
        (Write + Write Without Response) and starts the BLE server.

        Raises:
            RuntimeError: If the server is already running.
        """
        if self._running:
            raise RuntimeError("GATT server is already running")

        from bless import (
            BlessServer,
            GATTAttributePermissions,
            GATTCharacteristicProperties,
        )

        loop = asyncio.get_running_loop()

        gatt: dict[str, Any] = {
            KEY_SERVICE_UUID: {
                KEY_CHAR_UUID: {
                    "Properties": (
                        GATTCharacteristicProperties.write
                        | GATTCharacteristicProperties.write_without_response
                    ),
                    "Permissions": (
                        GATTAttributePermissions.readable
                        | GATTAttributePermissions.writeable
                    ),
                    "Value": None,
                },
            },
        }

        self._server = BlessServer(name=self._device_name, loop=loop)
        self._server.write_request_func = self._handle_write

        await self._server.add_gatt(gatt)
        await self._server.start()
        self._running = True

        logger.info(
            "GATT server started: name=%s, service=%s",
            self._device_name,
            KEY_SERVICE_UUID,
        )

    async def stop(self) -> None:
        """Stop the GATT server and cease advertising.

        Safe to call even if the server is not running.
        """
        if self._server is not None and self._running:
            await self._server.stop()
            self._running = False
            logger.info("GATT server stopped")

    @property
    def is_running(self) -> bool:
        """Whether the GATT server is currently running."""
        return self._running

    def _handle_write(
        self, characteristic: BlessGATTCharacteristic, value: Any, **kwargs: Any
    ) -> None:
        """Internal bless write callback.

        Delegates to the user-provided on_write callback with raw bytes.
        Clears characteristic.value after reading to avoid holding
        references to accumulated BLE write data.
        """
        data = bytes(value)
        characteristic.value = b""  # Clear to prevent data accumulation

        logger.debug("Write received: %d bytes", len(data))

        if self._on_write is not None:
            try:
                self._on_write(data)
            except Exception:
                logger.exception("Error in on_write callback")
