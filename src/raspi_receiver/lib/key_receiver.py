"""High-level BLE key receiver with callback-based API.

Wraps GATTServer to provide application-friendly key event handling.
Applications register callbacks for key press/release and connection events,
then call start() to begin receiving.

Includes heartbeat-based disconnect detection: if no data (key events or
heartbeats) is received within DISCONNECT_TIMEOUT_SEC, the client is
considered disconnected and on_disconnect is fired.

See docs/spec-raspi-receiver.md section 3.3 for the interface specification.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from common.protocol import KeyEvent, KeyType
from common.uuids import DEVICE_NAME

from raspi_receiver.lib.gatt_server import GATTServer
from raspi_receiver.lib.types import ConnectionEvent

logger = logging.getLogger(__name__)

# Disconnect if no data received for this many seconds.
# Should be >= 3x the Mac-side heartbeat interval (3s) to absorb jitter.
DISCONNECT_TIMEOUT_SEC: float = 10.0


@dataclass
class ReceiverStats:
    """BLE receiver statistics for monitoring and diagnostics."""

    key_events_received: int = 0
    heartbeats_received: int = 0
    deserialize_errors: int = 0
    connections: int = 0
    disconnections: int = 0
    last_receive_time: float = 0.0


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
        self._conn_lock = threading.Lock()
        self._last_receive_time: float = 0.0
        self._timeout_task: Optional[asyncio.Task[None]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stats = ReceiverStats()

        # Application callbacks (set by user)
        self.on_key_press: Optional[Callable[[KeyEvent], None]] = None
        self.on_key_release: Optional[Callable[[KeyEvent], None]] = None
        self.on_connect: Optional[Callable[[ConnectionEvent], None]] = None
        self.on_disconnect: Optional[Callable[[ConnectionEvent], None]] = None

    @property
    def stats(self) -> ReceiverStats:
        """Return a snapshot copy of receiver statistics."""
        return copy.copy(self._stats)

    async def start(self) -> None:
        """Start the GATT server and begin receiving key events.

        Raises:
            RuntimeError: If the receiver is already running.
        """
        self._loop = asyncio.get_running_loop()
        await self._server.start()
        self._timeout_task = asyncio.create_task(self._timeout_monitor())
        logger.info("KeyReceiver started, waiting for connections...")

    async def stop(self) -> None:
        """Stop the receiver and GATT server.

        Safe to call even if the receiver is not running.
        """
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
            self._timeout_task = None

        await self._server.stop()
        with self._conn_lock:
            was_connected = self._connected
            self._connected = False
        if was_connected:
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
        Heartbeat events update the receive timestamp but are not
        propagated to application callbacks.
        Invalid data is logged and skipped per spec.
        """
        self._last_receive_time = time.monotonic()
        self._stats.last_receive_time = self._last_receive_time

        with self._conn_lock:
            was_connected = self._connected
            if not was_connected:
                self._connected = True

        if not was_connected:
            self._stats.connections += 1
            logger.info("Client connected (first write received)")
            if self.on_connect is not None:
                try:
                    self.on_connect(ConnectionEvent(connected=True))
                except Exception:
                    logger.exception("Error in on_connect callback")

        try:
            event = KeyEvent.deserialize(data)
        except ValueError:
            self._stats.deserialize_errors += 1
            logger.warning("Failed to deserialize key event, skipping: %r", data)
            return

        # Heartbeat: update timestamp only, do not propagate to app
        if event.key_type == KeyType.HEARTBEAT:
            self._stats.heartbeats_received += 1
            logger.debug("Heartbeat received")
            return

        self._stats.key_events_received += 1

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

    async def _timeout_monitor(self) -> None:
        """Monitor for receive timeout and fire on_disconnect.

        Checks every second whether the time since the last received
        data exceeds DISCONNECT_TIMEOUT_SEC. If so, marks the client
        as disconnected and invokes the on_disconnect callback.
        """
        try:
            while True:
                await asyncio.sleep(1.0)
                with self._conn_lock:
                    if not self._connected:
                        continue
                    elapsed = time.monotonic() - self._last_receive_time
                    if elapsed > DISCONNECT_TIMEOUT_SEC:
                        self._connected = False
                        should_notify = True
                    else:
                        should_notify = False
                if should_notify:
                    self._stats.disconnections += 1
                    logger.info(
                        "Client disconnected (timeout: %.1fs)", elapsed
                    )
                    if self.on_disconnect is not None:
                        try:
                            self.on_disconnect(ConnectionEvent(connected=False))
                        except Exception:
                            logger.exception("Error in on_disconnect callback")
        except asyncio.CancelledError:
            return
