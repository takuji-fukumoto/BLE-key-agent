"""High-level reusable BLE key agent.

Composes keyboard monitoring and BLE sender into a single reusable API:
initialize once, call start(), and stop() on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from common.protocol import KeyEvent
from mac_agent.api_types import AgentConfig, ErrorCallback, KeyEventCallback, StatusCallback
from mac_agent.ble_client import BleSender, BleStatus
from mac_agent.keyboard_monitor import KeyboardMonitor

logger = logging.getLogger(__name__)


class KeyBleAgent:
    """Reusable orchestrator for keyboard input to BLE transmission.

    Args:
        config: Runtime configuration for reconnection/heartbeat/rate-limit.
        on_status_change: Optional callback invoked when BLE status changes.
        on_error: Optional callback invoked when runtime errors occur.
        on_key_event: Optional callback invoked for each consumed key event.
        ble_sender: Optional sender instance for dependency injection/testing.
        keyboard_monitor: Optional monitor instance for dependency injection/testing.
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        on_status_change: StatusCallback | None = None,
        on_error: ErrorCallback | None = None,
        on_key_event: KeyEventCallback | None = None,
        ble_sender: BleSender | None = None,
        keyboard_monitor: KeyboardMonitor | None = None,
    ) -> None:
        self._config = config or AgentConfig()
        self._on_status_change = on_status_change
        self._on_error = on_error
        self._on_key_event = on_key_event
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._last_send_time: float = 0.0

        self._keyboard_monitor = keyboard_monitor or KeyboardMonitor(
            queue_max_size=self._config.key_queue_max_size
        )
        self._ble_sender = ble_sender or BleSender(
            on_status_change=self._handle_status_change,
            reconnect_initial_delay=self._config.reconnect_initial_delay,
            reconnect_max_delay=self._config.reconnect_max_delay,
            reconnect_backoff_multiplier=self._config.reconnect_backoff_multiplier,
        )

    @property
    def status(self) -> BleStatus:
        """Current BLE connection status."""
        return self._ble_sender.status

    @property
    def queue(self) -> asyncio.Queue[KeyEvent | None]:
        """Queue from which key events are consumed."""
        return self._keyboard_monitor.queue

    @property
    def keyboard_monitor(self) -> KeyboardMonitor:
        """Return the underlying keyboard monitor instance."""
        return self._keyboard_monitor

    @property
    def ble_sender(self) -> BleSender:
        """Return the underlying BLE sender instance."""
        return self._ble_sender

    async def scan(self, timeout: float = 5.0):
        """Scan BLE devices via the sender.

        Args:
            timeout: Scan timeout in seconds.

        Returns:
            List of discovered BLE devices.
        """
        return await self._ble_sender.scan(timeout=timeout)

    async def connect(self, address: str) -> bool:
        """Connect BLE sender to the target address."""
        return await self._ble_sender.connect(address)

    async def start(self) -> None:
        """Start keyboard monitoring and forwarding loops.

        Note:
            This method does not initiate a BLE connection automatically.
            Call `connect()` first, or run `start()` before connecting and
            the loops will begin forwarding once connected.
        """
        if self._tasks:
            raise RuntimeError("KeyBleAgent is already running")

        self._shutdown_event.clear()
        await self._keyboard_monitor.start()

        self._tasks = [
            asyncio.create_task(self._forward_loop()),
            asyncio.create_task(self._heartbeat_loop()),
        ]

    async def stop(self) -> None:
        """Stop all loops and release resources."""
        self._shutdown_event.set()

        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

        await self._keyboard_monitor.stop()
        await self._ble_sender.disconnect()

    def _handle_status_change(self, status: BleStatus) -> None:
        """Forward status changes to optional callback."""
        if self._on_status_change is not None:
            try:
                self._on_status_change(status)
            except Exception:
                logger.exception("Error in on_status_change callback")

    def _handle_error(self, error: Exception) -> None:
        """Forward runtime errors to optional callback."""
        if self._on_error is not None:
            try:
                self._on_error(error)
            except Exception:
                logger.exception("Error in on_error callback")

    async def _forward_loop(self) -> None:
        """Forward keyboard events to BLE sender with rate limiting."""
        while not self._shutdown_event.is_set():
            try:
                event = await self._keyboard_monitor.next_event(timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.exception("Forward loop error")
                self._handle_error(exc)
                continue

            if event is None:
                continue

            if self._on_key_event is not None:
                try:
                    self._on_key_event(event)
                except Exception:
                    logger.exception("Error in on_key_event callback")

            now = time.monotonic()
            elapsed = now - self._last_send_time
            if elapsed < self._config.min_send_interval_sec:
                await asyncio.sleep(self._config.min_send_interval_sec - elapsed)

            if self._ble_sender.status == BleStatus.CONNECTED:
                sent = await self._ble_sender.send_key(event)
                if sent:
                    self._last_send_time = time.monotonic()

    async def _heartbeat_loop(self) -> None:
        """Send heartbeats periodically while connected."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self._config.heartbeat_interval_sec)
            if self._shutdown_event.is_set():
                return

            elapsed = time.monotonic() - self._last_send_time
            if elapsed < self._config.heartbeat_interval_sec:
                continue

            if self._ble_sender.status != BleStatus.CONNECTED:
                continue

            sent = await self._ble_sender.send_key(KeyEvent.heartbeat())
            if sent:
                self._last_send_time = time.monotonic()
