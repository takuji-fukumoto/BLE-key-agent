"""CLI sample application for BLE key receiver library.

This sample demonstrates how to use `KeyReceiver` without LCD hardware.
It builds a small text buffer from incoming key events and commits the
buffer when Enter is pressed.

Run with:
    python -m sample.raspi_receiver.apps.cli_receiver.main
"""

from __future__ import annotations

import argparse
import asyncio
import signal
from dataclasses import dataclass
from typing import Optional

from common.protocol import KeyEvent, KeyType
from ble_receiver.lib import ConnectionEvent, KeyReceiver, KeyReceiverConfig


@dataclass(frozen=True)
class CliEvent:
    """Event enqueued from synchronous receiver callbacks.

    Attributes:
        kind: Event kind. One of ``key_press``, ``key_release``, ``connect``,
            or ``disconnect``.
        key_event: Optional key event payload.
    """

    kind: str
    key_event: Optional[KeyEvent] = None


class CliReceiverApp:
    """CLI text-buffer sample for `KeyReceiver`.

    Maintains a text buffer from received key presses:
    - Character keys append to buffer
    - Backspace deletes one character
    - Space appends a space
    - Enter commits current buffer and clears it

    Args:
        config: Receiver configuration.
        max_buffer_length: Maximum in-memory text buffer length.
        queue_max_size: Maximum queued callback events.
    """

    def __init__(
        self,
        config: KeyReceiverConfig,
        max_buffer_length: int = 512,
        queue_max_size: int = 512,
    ) -> None:
        self._receiver = KeyReceiver(config=config)
        self._event_queue: asyncio.Queue[CliEvent] = asyncio.Queue(
            maxsize=queue_max_size
        )
        self._buffer: str = ""
        self._max_buffer_length = max_buffer_length
        self._shutdown_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def run(self) -> None:
        """Start receiver and process events until shutdown."""
        self._loop = asyncio.get_running_loop()
        self._register_callbacks()

        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._shutdown_event.set)

        await self._receiver.start()

        print("CLI receiver started. Press Ctrl+C to stop.")
        print("Enter commits buffer, Backspace deletes one character.")

        try:
            await self._process_loop()
        finally:
            await self._receiver.stop()
            print("CLI receiver stopped.")

    def _register_callbacks(self) -> None:
        """Register receiver callbacks via unified registration API."""
        self._receiver.register_callbacks(
            on_key_press=self._on_key_press,
            on_key_release=self._on_key_release,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
        )

    def _on_key_press(self, event: KeyEvent) -> None:
        """Handle key press callback (sync context)."""
        self._enqueue(CliEvent(kind="key_press", key_event=event))

    def _on_key_release(self, event: KeyEvent) -> None:
        """Handle key release callback (sync context)."""
        self._enqueue(CliEvent(kind="key_release", key_event=event))

    def _on_connect(self, _event: ConnectionEvent) -> None:
        """Handle connect callback (sync context)."""
        self._enqueue(CliEvent(kind="connect"))

    def _on_disconnect(self, _event: ConnectionEvent) -> None:
        """Handle disconnect callback (sync context)."""
        self._enqueue(CliEvent(kind="disconnect"))

    def _enqueue(self, event: CliEvent) -> None:
        """Thread-safe enqueue from callback context."""
        if self._loop is None or not self._loop.is_running():
            return
        try:
            self._loop.call_soon_threadsafe(self._safe_enqueue, event)
        except RuntimeError:
            return

    def _safe_enqueue(self, event: CliEvent) -> None:
        """Enqueue event, dropping silently when queue is full."""
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            return

    async def _process_loop(self) -> None:
        """Process queued events and update CLI buffer state."""
        while not self._shutdown_event.is_set():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if event.kind == "connect":
                print("[BLE] connected")
                continue
            if event.kind == "disconnect":
                print("[BLE] disconnected")
                continue
            if event.kind != "key_press" or event.key_event is None:
                continue

            self._handle_key_press(event.key_event)

    def _handle_key_press(self, event: KeyEvent) -> None:
        """Apply key press to text buffer and print result."""
        if event.key_type == KeyType.CHAR:
            if len(self._buffer) < self._max_buffer_length:
                self._buffer += event.value
            print(f"[BUFFER] {self._buffer}")
            return

        if event.key_type != KeyType.SPECIAL:
            return

        if event.value == "backspace":
            self._buffer = self._buffer[:-1]
            print(f"[BUFFER] {self._buffer}")
            return

        if event.value in {"space", "spacebar"}:
            if len(self._buffer) < self._max_buffer_length:
                self._buffer += " "
            print(f"[BUFFER] {self._buffer}")
            return

        if event.value == "enter":
            print(f"[COMMIT] {self._buffer}")
            self._buffer = ""


def main() -> None:
    """CLI entry point for receiver sample app."""
    parser = argparse.ArgumentParser(
        description="CLI sample for raspi_receiver KeyReceiver"
    )
    parser.add_argument(
        "--device-name",
        default="BLEKeyReceiver",
        help="BLE device name to advertise",
    )
    parser.add_argument(
        "--disconnect-timeout",
        type=float,
        default=10.0,
        help="Disconnect timeout in seconds",
    )
    parser.add_argument(
        "--max-buffer-length",
        type=int,
        default=512,
        help="Maximum text buffer length",
    )
    args = parser.parse_args()

    config = KeyReceiverConfig(
        device_name=args.device_name,
        disconnect_timeout_sec=args.disconnect_timeout,
    )
    app = CliReceiverApp(
        config=config,
        max_buffer_length=args.max_buffer_length,
    )
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
