"""Entry point for the LCD display application.

Integrates KeyReceiver (BLE library) with LCDDisplay (rendering),
using asyncio.Queue to bridge sync BLE callbacks to async LCD updates.

Run with: python -m raspi_receiver.apps.lcd_display.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from typing import Union

from common.protocol import KeyEvent, KeyType, Modifiers
from raspi_receiver.lib import ConnectionEvent, KeyReceiver

from raspi_receiver.apps.lcd_display.config import (
    BUTTON_POLL_INTERVAL_MS,
    GPIO_KEY1,
    GPIO_KEY2,
    RENDER_MIN_INTERVAL_MS,
)
from raspi_receiver.apps.lcd_display.display import LCDDisplay

logger = logging.getLogger(__name__)


# --- Internal event types for the async queue ---


@dataclass
class DisplayKeyEvent:
    """Key event ready for display processing."""

    key_value: str
    key_type: str
    press: bool
    modifiers: Modifiers | None


@dataclass
class DisplayConnectionEvent:
    """Connection state change event."""

    connected: bool


DisplayEvent = Union[DisplayKeyEvent, DisplayConnectionEvent]


class LCDApp:
    """LCD display application orchestrator.

    Wires KeyReceiver callbacks to LCDDisplay updates via asyncio.Queue,
    manages physical button input, and controls the application lifecycle.
    """

    def __init__(self) -> None:
        self._receiver = KeyReceiver()
        self._display = LCDDisplay()
        self._event_queue: asyncio.Queue[DisplayEvent] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def run(self) -> None:
        """Start the application and run until shutdown signal."""
        self._loop = asyncio.get_running_loop()

        # Initialize LCD hardware
        self._display.init()
        self._display.render()  # Draw initial "Waiting..." screen

        # Register KeyReceiver callbacks
        self._receiver.on_key_press = self._on_key_press
        self._receiver.on_key_release = self._on_key_release
        self._receiver.on_connect = self._on_connect
        self._receiver.on_disconnect = self._on_disconnect

        # Start BLE receiver
        await self._receiver.start()

        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._signal_shutdown)

        # Run concurrent tasks
        tasks = [
            asyncio.create_task(self._render_loop(), name="render_loop"),
            asyncio.create_task(self._button_poll_loop(), name="button_poll"),
        ]

        logger.info("LCD app started, waiting for BLE connections...")

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Cleanup
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await self._receiver.stop()
        self._display.shutdown()

        logger.info("LCD app shut down")

    # --- Sync callbacks (called from bless context) ---

    def _on_key_press(self, event: KeyEvent) -> None:
        """Handle key press from KeyReceiver (sync callback)."""
        display_event = DisplayKeyEvent(
            key_value=event.value,
            key_type=event.key_type.value,
            press=True,
            modifiers=event.modifiers,
        )
        self._enqueue(display_event)

    def _on_key_release(self, event: KeyEvent) -> None:
        """Handle key release from KeyReceiver (sync callback)."""
        display_event = DisplayKeyEvent(
            key_value=event.value,
            key_type=event.key_type.value,
            press=False,
            modifiers=event.modifiers,
        )
        self._enqueue(display_event)

    def _on_connect(self, event: ConnectionEvent) -> None:
        """Handle BLE connection (sync callback)."""
        self._enqueue(DisplayConnectionEvent(connected=True))

    def _on_disconnect(self, event: ConnectionEvent) -> None:
        """Handle BLE disconnection (sync callback)."""
        self._enqueue(DisplayConnectionEvent(connected=False))

    def _enqueue(self, event: DisplayEvent) -> None:
        """Thread-safe enqueue of display events."""
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._event_queue.put_nowait, event
            )

    # --- Async tasks ---

    async def _render_loop(self) -> None:
        """Process display events and render to LCD.

        Drains the event queue, updates screen state, and triggers
        re-draws at a throttled rate.
        """
        min_interval = RENDER_MIN_INTERVAL_MS / 1000.0

        while not self._shutdown_event.is_set():
            try:
                # Wait for an event (with timeout to check shutdown)
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                # Process this event
                self._process_event(event)

                # Drain any additional queued events (batch processing)
                while not self._event_queue.empty():
                    try:
                        event = self._event_queue.get_nowait()
                        self._process_event(event)
                    except asyncio.QueueEmpty:
                        break

                # Throttle rendering
                now = time.monotonic()
                elapsed = now - self._display.last_render_time
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

                # Render
                self._display.render()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in render loop")
                await asyncio.sleep(0.1)

    def _process_event(self, event: DisplayEvent) -> None:
        """Update display state from a queued event."""
        if isinstance(event, DisplayConnectionEvent):
            self._display.update_connection(event.connected)

        elif isinstance(event, DisplayKeyEvent):
            if not event.press:
                return  # Only update display on key press

            # Update key display
            modifier_text = self._format_modifiers(
                event.key_value, event.modifiers
            )
            self._display.update_key(
                event.key_value, event.key_type, modifier_text
            )

            # Update input buffer
            if event.key_type == KeyType.CHAR.value:
                self._display.append_buffer(event.key_value)
            elif event.key_type == KeyType.SPECIAL.value:
                if event.key_value == "enter":
                    self._display.clear_buffer()
                elif event.key_value == "backspace":
                    self._display.handle_backspace()
                elif event.key_value == "space":
                    self._display.append_buffer(" ")

    @staticmethod
    def _format_modifiers(
        key_value: str, modifiers: Modifiers | None
    ) -> str:
        """Format modifier keys into display string.

        Args:
            key_value: The key value.
            modifiers: Active modifier state, or None.

        Returns:
            Formatted string like "Shift + Ctrl + A", or empty string.
        """
        if modifiers is None or modifiers.is_default():
            return ""

        parts: list[str] = []
        if modifiers.cmd:
            parts.append("Cmd")
        if modifiers.ctrl:
            parts.append("Ctrl")
        if modifiers.alt:
            parts.append("Alt")
        if modifiers.shift:
            parts.append("Shift")
        parts.append(key_value)
        return " + ".join(parts)

    async def _button_poll_loop(self) -> None:
        """Poll physical buttons and handle presses.

        KEY1: Clear input buffer
        KEY2: Cycle backlight brightness
        """
        interval = BUTTON_POLL_INTERVAL_MS / 1000.0

        # Debounce state
        key1_was_pressed = False
        key2_was_pressed = False

        while not self._shutdown_event.is_set():
            try:
                disp = self._display._disp
                if disp is None:
                    await asyncio.sleep(interval)
                    continue

                # Read button states (active low: 0 = pressed)
                key1_pressed = disp.digital_read(GPIO_KEY1) == 0
                key2_pressed = disp.digital_read(GPIO_KEY2) == 0

                # KEY1: clear buffer (on press edge)
                if key1_pressed and not key1_was_pressed:
                    self._display.clear_buffer()
                    self._display.render()
                    logger.debug("KEY1 pressed: buffer cleared")

                # KEY2: cycle backlight (on press edge)
                if key2_pressed and not key2_was_pressed:
                    new_level = self._display.cycle_backlight()
                    logger.debug("KEY2 pressed: backlight -> %d%%", new_level)

                key1_was_pressed = key1_pressed
                key2_was_pressed = key2_pressed

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in button poll loop")
                await asyncio.sleep(interval)

    def _signal_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()


def main() -> None:
    """Application entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    app = LCDApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
