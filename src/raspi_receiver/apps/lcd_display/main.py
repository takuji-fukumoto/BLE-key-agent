"""Entry point for the LCD display application.

Integrates KeyReceiver (BLE library) with LCDDisplay (rendering),
using asyncio.Queue to bridge sync BLE callbacks to async LCD updates.

Run with: python -m raspi_receiver.apps.lcd_display.main
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import logging
import os
import resource
import signal
import threading
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Union

from common.protocol import KeyEvent, KeyType, Modifiers
from raspi_receiver.lib import ConnectionEvent, KeyReceiver

from raspi_receiver.apps.lcd_display.config import (
    BUTTON_POLL_INTERVAL_MS,
    EVENT_QUEUE_MAX_SIZE,
    RENDER_MIN_INTERVAL_MS,
    SPI_SPEED_HZ,
)
from raspi_receiver.apps.lcd_display.display import LCDDisplay

logger = logging.getLogger(__name__)

# Health check interval in seconds
HEALTH_CHECK_INTERVAL_SEC: float = 30.0

# Auto-exit delay when running in no-render fallback mode (seconds).
# The loop script will restart the process and retry display init.
NO_RENDER_FALLBACK_EXIT_SEC: float = 60.0


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

    def __init__(
        self,
        spi_speed: int = SPI_SPEED_HZ,
        no_render: bool = False,
    ) -> None:
        self._receiver = KeyReceiver()
        self._no_render = no_render
        self._fell_back_to_no_render = False
        self._display: LCDDisplay | None = (
            None if no_render else LCDDisplay(spi_speed=spi_speed)
        )
        self._event_queue: asyncio.Queue[DisplayEvent] = asyncio.Queue(
            maxsize=EVENT_QUEUE_MAX_SIZE
        )
        self._shutdown_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._rendering = False
        self._render_start_time: float = 0.0
        self._loop_responsive = False

    async def run(self) -> None:
        """Start the application and run until shutdown signal."""
        self._loop = asyncio.get_running_loop()

        # Initialize LCD hardware (skip in no-render mode)
        # Retry up to 10 times with increasing delay — after a crash the
        # SPI/GPIO hardware may need time to recover.
        if self._display is not None:
            max_retries = 10
            for attempt in range(1, max_retries + 1):
                try:
                    self._display.init()
                    self._display.render()  # Draw initial "Waiting..." screen
                    break
                except Exception:
                    if attempt < max_retries:
                        delay = min(attempt * 2, 10)  # 2,4,6,8,10,10,...s
                        logger.warning(
                            "LCD init failed (attempt %d/%d), "
                            "retrying in %ds...",
                            attempt,
                            max_retries,
                            delay,
                            exc_info=True,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.warning(
                            "LCD init failed after %d attempts, "
                            "falling back to no-render mode",
                            max_retries,
                            exc_info=True,
                        )
                        self._display = None
                        self._no_render = True
                        self._fell_back_to_no_render = True

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

        # Start watchdog thread (independent of asyncio event loop)
        watchdog = threading.Thread(
            target=self._watchdog_thread, daemon=True, name="watchdog"
        )
        watchdog.start()

        # Run concurrent tasks
        tasks = [
            asyncio.create_task(self._health_check_loop(), name="health_check"),
        ]
        if self._no_render:
            tasks.append(
                asyncio.create_task(
                    self._no_render_drain_loop(), name="no_render_drain"
                )
            )
            # If we fell back to no-render due to display init failure,
            # schedule an auto-exit so the loop script can restart us
            # with a fresh hardware reset and retry display init.
            if self._fell_back_to_no_render:
                tasks.append(
                    asyncio.create_task(
                        self._fallback_exit_timer(), name="fallback_exit"
                    )
                )
        else:
            tasks.append(
                asyncio.create_task(self._render_loop(), name="render_loop")
            )
            tasks.append(
                asyncio.create_task(
                    self._button_poll_loop(), name="button_poll"
                )
            )

        if self._no_render:
            logger.info(
                "LCD app started (NO-RENDER mode), "
                "waiting for BLE connections..."
            )
        else:
            logger.info("LCD app started, waiting for BLE connections...")

        # Wait for shutdown
        await self._shutdown_event.wait()

        # Cleanup
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await self._receiver.stop()
        if self._display is not None:
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
        """Thread-safe enqueue of display events.

        Connection events are always enqueued. Key events are silently
        dropped when the queue is full to provide backpressure.
        """
        if self._loop is None or not self._loop.is_running():
            return
        try:
            if isinstance(event, DisplayConnectionEvent):
                self._loop.call_soon_threadsafe(
                    self._event_queue.put_nowait, event
                )
            else:
                self._loop.call_soon_threadsafe(
                    self._safe_enqueue_key, event
                )
        except RuntimeError:
            # Loop closed between is_running() check and call_soon_threadsafe()
            pass

    def _safe_enqueue_key(self, event: DisplayEvent) -> None:
        """Enqueue a key event, dropping silently if queue is full."""
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("Event queue full, dropping key event")

    # --- Async tasks ---

    async def _no_render_drain_loop(self) -> None:
        """Drain event queue and log events (no-render mode).

        Replaces the render loop when --no-render is active.
        Consumes events from the queue and logs them without
        any LCD or SPI operations.
        """
        while not self._shutdown_event.is_set():
            try:
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                self._process_event(event)

                # Drain additional queued events
                while not self._event_queue.empty():
                    try:
                        event = self._event_queue.get_nowait()
                        self._process_event(event)
                    except asyncio.QueueEmpty:
                        break

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in no-render drain loop")
                await asyncio.sleep(0.1)

    async def _render_loop(self) -> None:
        """Process display events and render to LCD.

        Drains the event queue, updates screen state, and triggers
        re-draws at a throttled rate. When the queue is heavily
        backlogged, events are drained without rendering each one
        to prevent memory accumulation.
        """
        min_interval = RENDER_MIN_INTERVAL_MS / 1000.0
        gc_interval = 60  # Seconds between forced GC
        last_gc_time = time.monotonic()

        while not self._shutdown_event.is_set():
            try:
                # Wait for an event (with timeout to check shutdown)
                try:
                    event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    # Periodic GC even when idle
                    now = time.monotonic()
                    if now - last_gc_time > gc_interval:
                        gc.collect()
                        last_gc_time = now
                    continue

                # Process this event
                self._process_event(event)

                # Drain any additional queued events (batch processing)
                drained = 0
                while not self._event_queue.empty():
                    try:
                        event = self._event_queue.get_nowait()
                        self._process_event(event)
                        drained += 1
                    except asyncio.QueueEmpty:
                        break

                if drained > EVENT_QUEUE_MAX_SIZE // 2:
                    logger.warning(
                        "Queue backlog: drained %d events at once", drained
                    )

                # Throttle rendering
                now = time.monotonic()
                elapsed = now - self._display.last_render_time
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

                # Render (offload blocking SPI I/O to thread pool)
                await self._execute_render("render")

                # Periodic GC
                now = time.monotonic()
                if now - last_gc_time > gc_interval:
                    gc.collect()
                    last_gc_time = now

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in render loop")
                await asyncio.sleep(0.1)

    def _process_event(self, event: DisplayEvent) -> None:
        """Update display state from a queued event."""
        if isinstance(event, DisplayConnectionEvent):
            if self._display is not None:
                self._display.update_connection(event.connected)
            if self._no_render:
                logger.info(
                    "[NO-RENDER] connection: %s",
                    "connected" if event.connected else "disconnected",
                )

        elif isinstance(event, DisplayKeyEvent):
            if not event.press:
                return  # Only update display on key press

            if self._no_render:
                logger.info(
                    "[NO-RENDER] key: type=%s value=%s",
                    event.key_type,
                    event.key_value,
                )
                return

            # Update key display
            assert self._display is not None
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

    async def _execute_render(self, label: str = "render") -> None:
        """Execute a render cycle with timing and flag management.

        Guards against concurrent renders via the _rendering flag.
        Offloads blocking SPI I/O to a thread pool executor.

        Args:
            label: Log label to distinguish render call sites.
        """
        if self._rendering:
            return
        self._rendering = True
        self._render_start_time = time.monotonic()
        try:
            logger.debug("%s: start", label)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._display.render)
            render_ms = (time.monotonic() - self._render_start_time) * 1000
            logger.debug("%s: done (%.1fms)", label, render_ms)
        finally:
            self._rendering = False
            self._render_start_time = 0.0

    async def _button_poll_loop(self) -> None:
        """Poll physical buttons and handle presses.

        KEY1: Clear input buffer
        KEY2: Cycle backlight brightness

        Button states are read via the render subprocess to avoid
        opening GPIO pins in the main process.
        """
        interval = BUTTON_POLL_INTERVAL_MS / 1000.0
        loop = asyncio.get_running_loop()

        # Debounce state
        key1_was_pressed = False
        key2_was_pressed = False

        while not self._shutdown_event.is_set():
            try:
                # Read button states via render subprocess
                key1_pressed, key2_pressed = await loop.run_in_executor(
                    None, self._display.read_buttons
                )

                # KEY1: clear buffer (on press edge)
                if key1_pressed and not key1_was_pressed:
                    self._display.clear_buffer()
                    await self._execute_render("render(btn)")
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

    async def _fallback_exit_timer(self) -> None:
        """Auto-exit after running in no-render fallback mode.

        When display init failed and the app fell back to no-render mode,
        this timer triggers a graceful shutdown so the loop script can
        restart the process with a fresh hardware reset and retry display
        initialisation.
        """
        try:
            logger.info(
                "No-render fallback: will auto-exit in %.0fs "
                "for display recovery restart",
                NO_RENDER_FALLBACK_EXIT_SEC,
            )
            await asyncio.sleep(NO_RENDER_FALLBACK_EXIT_SEC)
            logger.info(
                "No-render fallback timeout reached, "
                "shutting down for restart..."
            )
            self._shutdown_event.set()
        except asyncio.CancelledError:
            pass

    async def _health_check_loop(self) -> None:
        """Periodically log system health for diagnostics.

        Logs BLE connection state, receiver statistics, event queue depth,
        memory usage (RSS), and asyncio task count every 30 seconds.
        """
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(HEALTH_CHECK_INTERVAL_SEC)
                if self._shutdown_event.is_set():
                    break

                stats = self._receiver.stats
                queue_size = self._event_queue.qsize()
                rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                # macOS reports in bytes, Linux in KB
                if hasattr(os, "uname") and os.uname().sysname == "Darwin":
                    rss_mb = rss_mb / (1024 * 1024)
                else:
                    rss_mb = rss_mb / 1024
                task_count = len(asyncio.all_tasks())

                logger.info(
                    "[HEALTH] connected=%s | keys=%d hb=%d errs=%d "
                    "conn=%d disconn=%d | queue=%d/%d | "
                    "RSS=%.1fMB | tasks=%d",
                    self._receiver.is_connected,
                    stats.key_events_received,
                    stats.heartbeats_received,
                    stats.deserialize_errors,
                    stats.connections,
                    stats.disconnections,
                    queue_size,
                    EVENT_QUEUE_MAX_SIZE,
                    rss_mb,
                    task_count,
                )

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in health check loop")

    def _watchdog_thread(self) -> None:
        """Independent watchdog thread for freeze detection.

        Runs outside the asyncio event loop to detect process-level hangs.
        Logs every 5 seconds with:
        - Whether the asyncio event loop is responsive
        - Whether a render() call is currently blocked (and for how long)

        If this thread's logs also stop, the freeze is at the GIL/process level.
        """
        watchdog_logger = logging.getLogger(__name__ + ".watchdog")
        while not self._shutdown_event.is_set():
            time.sleep(5.0)
            if self._shutdown_event.is_set():
                break

            # Check asyncio event loop responsiveness
            self._loop_responsive = False
            loop = self._loop
            if loop is not None and loop.is_running():
                try:
                    loop.call_soon_threadsafe(self._mark_loop_responsive)
                except RuntimeError:
                    pass
                # Give the event loop a moment to process the callback
                time.sleep(0.1)

            loop_ok = self._loop_responsive

            # Check render blocking
            render_blocked = ""
            if self._rendering and self._render_start_time > 0:
                blocked_sec = time.monotonic() - self._render_start_time
                render_blocked = f" | render_blocked={blocked_sec:.1f}s"

            watchdog_logger.info(
                "[WATCHDOG] alive | loop_responsive=%s%s",
                loop_ok,
                render_blocked,
            )

    def _mark_loop_responsive(self) -> None:
        """Called from asyncio event loop to confirm responsiveness."""
        self._loop_responsive = True

    def _signal_shutdown(self) -> None:
        """Handle shutdown signal."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()


def _setup_logging(debug: bool, log_dir: str) -> str:
    """Configure logging with console and file handlers.

    File logs default to /tmp to avoid SD card I/O which can cause
    process-wide freezes when the SD card has bad sectors.  Use
    ``--log-dir logs`` to write to the SD card instead.

    Args:
        debug: If True, set console log level to DEBUG.
        log_dir: Directory for log files.

    Returns:
        Path to the log file.
    """
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File handler (INFO level to reduce write frequency)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "raspi_receiver.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=150 * 1024,  # ~150KB ≈ 1000行
        backupCount=3,
    )
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    return log_file


def _write_crash_log(log_dir: str, message: str) -> None:
    """Write crash info to a dedicated crash log file.

    Uses direct file I/O (not logging module) to maximise
    the chance of recording the crash even if the logging
    system itself is broken.

    Args:
        log_dir: Directory for log files.
        message: Crash message to write.
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
        crash_file = os.path.join(log_dir, "crash.log")
        with open(crash_file, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass  # SD card may be unwritable


def main() -> None:
    """Application entry point."""
    import faulthandler
    import sys
    import traceback

    # Enable faulthandler to dump tracebacks on SIGSEGV/SIGBUS/SIGABRT
    faulthandler.enable(file=sys.stderr, all_threads=True)

    parser = argparse.ArgumentParser(
        description="BLE Key Agent - Raspberry Pi LCD App",
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
    parser.add_argument(
        "--spi-speed",
        type=int,
        default=SPI_SPEED_HZ,
        help=f"SPI bus speed in Hz (default: {SPI_SPEED_HZ})",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Disable LCD rendering (BLE + logging only, for diagnostics)",
    )
    args = parser.parse_args()

    log_file = _setup_logging(debug=args.debug, log_dir=args.log_dir)
    logger.info("Log file: %s", log_file)

    app = LCDApp(spi_speed=args.spi_speed, no_render=args.no_render)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass
    except SystemExit:
        pass
    except BaseException:
        msg = traceback.format_exc()
        logger.critical("FATAL CRASH:\n%s", msg)
        _write_crash_log(args.log_dir, f"CRASH:\n{msg}")
        print(f"FATAL CRASH:\n{msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
