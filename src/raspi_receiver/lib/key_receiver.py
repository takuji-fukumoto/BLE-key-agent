"""High-level BLE key receiver with callback-based API.

Wraps GATTServer to provide application-friendly key event handling.
Applications register callbacks for key press/release and connection events,
then call start() to begin receiving.

See docs/spec-raspi-receiver.md section 3.3 for the interface specification.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from common.protocol import KeyEvent
from common.uuids import DEVICE_NAME

from raspi_receiver.lib.gatt_server import GATTServer
from raspi_receiver.lib.types import ConnectionEvent

logger = logging.getLogger(__name__)


class KeyReceiver:
    """BLE key receiver library.

    Provides a callback-based API for receiving key events over BLE GATT.
    Applications only need to register callbacks and call start().

    Usage:
        receiver = KeyReceiver()
        receiver.on_key_press = lambda event: print(f"Key: {event.value}")
        await receiver.start()

    Args:
        device_name: BLE advertised device name for the GATT server.
    """

    def __init__(self, device_name: str = DEVICE_NAME) -> None:
        self._server = GATTServer(
            device_name=device_name,
            on_write=self._handle_write,
        )
        self._connected = False

        # Application callbacks (set by user)
        self.on_key_press: Optional[Callable[[KeyEvent], None]] = None
        self.on_key_release: Optional[Callable[[KeyEvent], None]] = None
        self.on_connect: Optional[Callable[[ConnectionEvent], None]] = None
        self.on_disconnect: Optional[Callable[[ConnectionEvent], None]] = None

    async def start(self) -> None:
        """Start the GATT server and begin receiving key events.

        Raises:
            RuntimeError: If the receiver is already running.
        """
        await self._server.start()
        logger.info("KeyReceiver started, waiting for connections...")

    async def stop(self) -> None:
        """Stop the receiver and GATT server.

        Safe to call even if the receiver is not running.
        """
        await self._server.stop()
        if self._connected:
            self._connected = False
            logger.info("KeyReceiver stopped, client disconnected")
        else:
            logger.info("KeyReceiver stopped")

    @property
    def is_connected(self) -> bool:
        """Whether a BLE client is currently connected."""
        return self._connected

    def _handle_write(self, data: bytes) -> None:
        """Process raw bytes from GATT write into key events.

        Deserializes the data using common.protocol.KeyEvent and
        dispatches to the appropriate callback (press or release).
        Invalid data is logged and skipped per spec.
        """
        if not self._connected:
            self._connected = True
            logger.info("Client connected (first write received)")
            if self.on_connect is not None:
                try:
                    self.on_connect(ConnectionEvent(connected=True))
                except Exception:
                    logger.exception("Error in on_connect callback")

        try:
            event = KeyEvent.deserialize(data)
        except ValueError:
            logger.warning("Failed to deserialize key event, skipping: %r", data)
            return

        logger.debug(
            "Key event: type=%s, value=%s, press=%s",
            event.key_type.value,
            event.value,
            event.press,
        )

        if event.press:
            if self.on_key_press is not None:
                try:
                    self.on_key_press(event)
                except Exception:
                    logger.exception("Error in on_key_press callback")
        else:
            if self.on_key_release is not None:
                try:
                    self.on_key_release(event)
                except Exception:
                    logger.exception("Error in on_key_release callback")
