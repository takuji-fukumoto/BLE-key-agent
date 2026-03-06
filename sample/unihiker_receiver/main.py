"""Entry point for the UNIHIKER receiver sample application.

This app integrates `ble_receiver.lib.KeyReceiver` with
`UnihikerDisplayAdapter`, using an asyncio queue to bridge sync BLE callbacks
to async GUI updates.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Union

from common.protocol import KeyEvent
from ble_receiver.lib.key_receiver import KeyReceiver, KeyReceiverConfig
from ble_receiver.lib.types import ConnectionEvent

logger = logging.getLogger(__name__)

from .config import EVENT_QUEUE_MAX_SIZE, RENDER_INTERVAL_MS
from .display import UnihikerDisplayAdapter


@dataclass
class AppStats:
    """Runtime statistics for the UNIHIKER receiver app.

    Attributes:
        dropped_events: Number of events dropped due to full queue.
    """

    dropped_events: int = 0


DisplayEvent = Union[KeyEvent, ConnectionEvent]


class UnihikerReceiverApp:
    """UNIHIKER receiver application orchestrator.

    Bridges sync KeyReceiver callbacks to async display updates with an
    `asyncio.Queue`, then batches queued events before each render cycle.

    Args:
        device_name: BLE peripheral device name for advertising.
        render_interval_ms: Minimum render interval in milliseconds.
    """

    def __init__(
        self,
        device_name: str = "RasPi-KeyAgent",
        render_interval_ms: int = RENDER_INTERVAL_MS,
    ) -> None:
        self._receiver = KeyReceiver(
            config=KeyReceiverConfig(device_name=device_name)
        )
        self._display = UnihikerDisplayAdapter()
        self._event_queue: asyncio.Queue[DisplayEvent] = asyncio.Queue(
            maxsize=EVENT_QUEUE_MAX_SIZE
        )
        self._shutdown_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._render_interval_sec = render_interval_ms / 1000.0
        self._stats = AppStats()

    @property
    def stats(self) -> AppStats:
        """Return app statistics."""
        return self._stats

    async def run(self) -> None:
        """Run the app lifecycle until shutdown signal."""
        self._loop = asyncio.get_running_loop()

        logger.info("Initializing display...")
        self._display.on_stop = self._signal_shutdown
        self._display.init()
        logger.info("Display initialized")

        self._register_callbacks()

        logger.info("Starting BLE receiver...")
        await self._receiver.start()
        logger.info("BLE receiver started, waiting for connections...")

        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._signal_shutdown)

        task = asyncio.create_task(self._event_loop(), name="event_loop")
        await self._shutdown_event.wait()

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        await self._receiver.stop()
        self._display.shutdown()

    def _register_callbacks(self) -> None:
        """Register KeyReceiver callbacks."""
        self._receiver.on_key_press = self._on_key_press
        self._receiver.on_key_release = self._on_key_release
        self._receiver.on_connect = self._on_connect
        self._receiver.on_disconnect = self._on_disconnect

    def _signal_shutdown(self) -> None:
        """Set shutdown event from signal handlers."""
        self._shutdown_event.set()

    def _enqueue(self, event: DisplayEvent) -> None:
        """Thread-safe enqueue of display events.

        Args:
            event: Display event to enqueue.
        """
        if self._loop is None or not self._loop.is_running():
            return

        try:
            self._loop.call_soon_threadsafe(self._safe_enqueue, event)
        except RuntimeError:
            return

    def _safe_enqueue(self, event: DisplayEvent) -> None:
        """Enqueue an event, counting drops when queue is full.

        Args:
            event: Display event.
        """
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            self._stats.dropped_events += 1

    def _on_key_press(self, event: KeyEvent) -> None:
        """Handle key press callback from KeyReceiver.

        Args:
            event: Incoming key event.
        """
        self._enqueue(event)

    def _on_key_release(self, event: KeyEvent) -> None:
        """Handle key release callback from KeyReceiver.

        Args:
            event: Incoming key event.
        """
        self._enqueue(event)

    def _on_connect(self, event: ConnectionEvent) -> None:
        """Handle BLE connect callback.

        Args:
            event: Connection event.
        """
        self._enqueue(event)

    def _on_disconnect(self, event: ConnectionEvent) -> None:
        """Handle BLE disconnect callback.

        Args:
            event: Connection event.
        """
        self._enqueue(event)

    def _process_event(self, event: DisplayEvent) -> None:
        """Apply one event to display state.

        Args:
            event: Event from queue.
        """
        if isinstance(event, ConnectionEvent):
            self._display.update_connection(event.connected)
            return

        self._display.apply_key_event(event)

    async def _event_loop(self) -> None:
        """Drain queued events and render with throttling."""
        while not self._shutdown_event.is_set():
            await self._drain_once()
            self._display.render()

    async def _drain_once(self) -> None:
        """Wait for at most one event and batch-drain remaining queue."""
        try:
            event = await asyncio.wait_for(
                self._event_queue.get(), timeout=self._render_interval_sec
            )
            self._process_event(event)
            while True:
                event = self._event_queue.get_nowait()
                self._process_event(event)
        except asyncio.TimeoutError:
            return
        except asyncio.QueueEmpty:
            return


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(description="UNIHIKER receiver sample")
    parser.add_argument(
        "--device-name",
        type=str,
        default="RasPi-KeyAgent",
        help="BLE device name for advertising",
    )
    parser.add_argument(
        "--render-interval-ms",
        type=int,
        default=RENDER_INTERVAL_MS,
        help="Render interval in milliseconds",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG level logging on console",
    )
    parser.add_argument(
        "--log-dir",
        default="/tmp/ble-key-agent",
        help="Directory for log files (default: /tmp/ble-key-agent)",
    )
    return parser.parse_args()


def _setup_logging(debug: bool, log_dir: str) -> str:
    """Configure logging with console and file handlers.

    Args:
        debug: If True, set console log level to DEBUG.
        log_dir: Directory for log files.

    Returns:
        Path to the log file.
    """
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "unihiker_receiver.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=150 * 1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    return log_file


async def _run_async(args: argparse.Namespace) -> None:
    """Run app asynchronously with parsed CLI options."""
    app = UnihikerReceiverApp(
        device_name=args.device_name,
        render_interval_ms=args.render_interval_ms,
    )
    await app.run()


def main() -> None:
    """Program entry point."""
    args = parse_args()
    log_file = _setup_logging(debug=args.debug, log_dir=args.log_dir)
    logger.info("Log file: %s", log_file)

    try:
        asyncio.run(_run_async(args))
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.critical("FATAL CRASH:", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
