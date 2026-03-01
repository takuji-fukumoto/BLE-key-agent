"""Subprocess-based SPI renderer for LCD display.

Isolates SPI I/O from the main process to prevent GIL-level freezes.
The spidev C extension holds the Python GIL during ioctl() calls, so
a blocking SPI write freezes all threads in the same process.  By
running SPI in a separate subprocess, the main process (asyncio, bless,
watchdog) remains responsive even if SPI hangs.

Architecture::

    Main process                          Subprocess (spi-renderer)
    ─────────────                         ────────────────────────
    PIL composition                       ST7789 init (SPI + GPIO)
    RGB565 conversion                     ↓
    ↓                                     Pipe recv → SPI write
    Pipe send ─────────────────────────→  (4KB chunks)
    conn.poll(timeout) ←────────────────  Pipe send("done")
       ↑ GIL released during poll()
       ↑ Other threads keep running

If the subprocess hangs (SPI timeout), the main process kills it
and spawns a fresh one with re-initialized hardware.
"""

from __future__ import annotations

import logging
import multiprocessing
import threading
from multiprocessing.connection import Connection
from typing import Any

from .config import (
    SPI_RENDER_TIMEOUT_SEC,
    SPI_SPEED_HZ,
)

logger = logging.getLogger(__name__)

# Use 'spawn' to avoid fork-safety issues with bless/D-Bus threads.
_mp_ctx = multiprocessing.get_context("spawn")


# --- PWM fallback (duplicated from display.py for subprocess isolation) ---


class _DigitalBacklightFallback:
    """Drop-in replacement for PWMOutputDevice using on/off only.

    Used when no PWM-capable pin factory (lgpio/RPi.GPIO/pigpio) is
    available.  Backlight becomes simple on/off (no dimming).
    """

    def __init__(self, pin: int, frequency: int = 1000, **kwargs: Any) -> None:
        from gpiozero import DigitalOutputDevice

        self._device = DigitalOutputDevice(pin)
        self._value = 0.0

    @property
    def value(self) -> float:
        """Current duty cycle value."""
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        self._value = float(v)
        if v > 0:
            self._device.on()
        else:
            self._device.off()

    @property
    def frequency(self) -> int:
        """PWM frequency (no-op for digital fallback)."""
        return 1000

    @frequency.setter
    def frequency(self, f: int) -> None:
        pass  # no-op

    def close(self) -> None:
        """Release the GPIO pin."""
        self._device.close()


# --- Subprocess worker ---


def _render_worker(conn: Connection, spi_speed: int) -> None:
    """Subprocess entry point for SPI rendering.

    Initializes the ST7789 driver and processes render/button/backlight
    commands received via pipe.  Runs until a shutdown command (None)
    is received or the pipe is closed.

    Args:
        conn: Pipe connection for receiving commands and sending responses.
        spi_speed: SPI bus speed in Hz.
    """
    import sys
    import types
    from pathlib import Path

    # Minimal logging in subprocess (stderr only)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    sub_logger = logging.getLogger("render_worker")

    # Add LCD HAT driver directory to sys.path
    driver_dir = str(
        Path(__file__).resolve().parents[4]
        / "reports"
        / "1.3inch_LCD_HAT_python"
    )
    if driver_dir not in sys.path:
        sys.path.insert(0, driver_dir)

    # Numpy stub if not installed (common on ARM)
    has_numpy = "numpy" in sys.modules
    if not has_numpy:
        try:
            import numpy  # noqa: F401

            has_numpy = True
        except ImportError:
            stub = types.ModuleType("numpy")
            stub.uint8 = None  # type: ignore[attr-defined]
            sys.modules["numpy"] = stub
            sub_logger.info("numpy not available in render subprocess")

    # PWM fallback if needed
    patch_pwm = False
    original_pwm: Any = None
    try:
        import gpiozero

        test_pwm = gpiozero.PWMOutputDevice(24)
        test_pwm.close()
    except Exception:
        patch_pwm = True
        import gpiozero

        original_pwm = gpiozero.PWMOutputDevice
        gpiozero.PWMOutputDevice = _DigitalBacklightFallback  # type: ignore[assignment,misc]
        sub_logger.warning("PWM not supported, backlight will be on/off only")

    import ST7789

    disp = ST7789.ST7789()

    # Override SPI speed
    if disp.SPI is not None:
        disp.SPI.max_speed_hz = spi_speed

    # Restore original PWMOutputDevice if we patched it
    if patch_pwm and original_pwm is not None:
        import gpiozero as _gz

        _gz.PWMOutputDevice = original_pwm  # type: ignore[assignment,misc]

    disp.Init()
    disp.clear()

    sub_logger.info(
        "Render subprocess ready (PID=%d, SPI=%dHz)",
        multiprocessing.current_process().pid,
        spi_speed,
    )
    conn.send(("ready",))

    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break

        if msg is None:
            break

        cmd = msg[0]

        if cmd == "render":
            _, buf_bytes, width, height = msg
            disp.SetWindows(0, 0, width, height)
            disp.digital_write(disp.GPIO_DC_PIN, True)
            for i in range(0, len(buf_bytes), 4096):
                disp.spi_writebyte(buf_bytes[i : i + 4096])
            conn.send(("done",))

        elif cmd == "backlight":
            _, duty = msg
            disp.bl_DutyCycle(duty)
            conn.send(("done",))

        elif cmd == "buttons":
            k1 = disp.digital_read(disp.GPIO_KEY1_PIN) == 0
            k2 = disp.digital_read(disp.GPIO_KEY2_PIN) == 0
            conn.send(("buttons", k1, k2))

        elif cmd == "clear":
            disp.clear()
            conn.send(("done",))

    sub_logger.info("Render subprocess shutting down")
    disp.bl_DutyCycle(0)
    disp.module_exit()


# --- Main-process proxy ---


class RenderProxy:
    """Proxy for the SPI render subprocess.

    Provides methods that mirror the ST7789 driver interface but
    execute SPI operations in a separate subprocess.  Detects
    subprocess hangs via timeout and automatically restarts.

    Args:
        spi_speed: SPI bus speed in Hz.
    """

    def __init__(self, spi_speed: int = SPI_SPEED_HZ) -> None:
        self._spi_speed = spi_speed
        self._process: multiprocessing.Process | None = None
        self._conn: Connection | None = None
        self._lock = threading.Lock()

    @property
    def is_alive(self) -> bool:
        """Whether the render subprocess is running."""
        return self._process is not None and self._process.is_alive()

    def start(self) -> None:
        """Start the render subprocess.

        Raises:
            RuntimeError: If the subprocess fails to start within 10s.
        """
        parent_conn, child_conn = _mp_ctx.Pipe()
        self._conn = parent_conn
        self._process = _mp_ctx.Process(
            target=_render_worker,
            args=(child_conn, self._spi_speed),
            daemon=True,
            name="spi-renderer",
        )
        self._process.start()
        child_conn.close()

        # Wait for ready signal from subprocess
        if not self._conn.poll(timeout=10.0):
            raise RuntimeError("Render subprocess did not start within 10s")
        msg = self._conn.recv()
        if msg[0] != "ready":
            raise RuntimeError(f"Unexpected subprocess message: {msg}")

        logger.info(
            "Render subprocess started (PID=%d, SPI=%dHz)",
            self._process.pid,
            self._spi_speed,
        )

    def render(
        self, rgb565_buf: bytes | bytearray, width: int, height: int
    ) -> bool:
        """Send RGB565 data to subprocess for SPI write.

        Args:
            rgb565_buf: Pre-converted RGB565 pixel data.
            width: Display width in pixels.
            height: Display height in pixels.

        Returns:
            True on success, False on timeout (subprocess restarted).
        """
        with self._lock:
            return self._render_locked(rgb565_buf, width, height)

    def _render_locked(
        self, rgb565_buf: bytes | bytearray, width: int, height: int
    ) -> bool:
        """Render implementation (must be called with lock held)."""
        if self._conn is None:
            return False

        try:
            self._conn.send(
                ("render", bytes(rgb565_buf), width, height)
            )
        except (BrokenPipeError, OSError):
            logger.error("Render pipe broken, restarting subprocess")
            self._restart()
            return False

        if self._conn is not None and self._conn.poll(
            timeout=SPI_RENDER_TIMEOUT_SEC
        ):
            try:
                msg = self._conn.recv()
                return msg[0] == "done"
            except (EOFError, OSError):
                self._restart()
                return False

        logger.error(
            "Render subprocess timed out (%.1fs), restarting",
            SPI_RENDER_TIMEOUT_SEC,
        )
        self._restart()
        return False

    def read_buttons(self) -> tuple[bool, bool]:
        """Read physical button states from subprocess.

        Returns:
            Tuple of (key1_pressed, key2_pressed).
        """
        with self._lock:
            return self._read_buttons_locked()

    def _read_buttons_locked(self) -> tuple[bool, bool]:
        """Button read implementation (must be called with lock held)."""
        if self._conn is None:
            return False, False

        try:
            self._conn.send(("buttons",))
            if self._conn.poll(timeout=1.0):
                msg = self._conn.recv()
                if msg[0] == "buttons":
                    return msg[1], msg[2]
        except (BrokenPipeError, EOFError, OSError):
            pass
        return False, False

    def set_backlight(self, duty: int) -> None:
        """Set backlight brightness via subprocess.

        Args:
            duty: Duty cycle percentage (0-100).
        """
        with self._lock:
            self._set_backlight_locked(duty)

    def _set_backlight_locked(self, duty: int) -> None:
        """Backlight implementation (must be called with lock held)."""
        if self._conn is None:
            return
        try:
            self._conn.send(("backlight", duty))
            if self._conn.poll(timeout=1.0):
                self._conn.recv()
        except (BrokenPipeError, EOFError, OSError):
            pass

    def clear(self) -> None:
        """Clear the LCD display via subprocess."""
        with self._lock:
            self._clear_locked()

    def _clear_locked(self) -> None:
        """Clear implementation (must be called with lock held)."""
        if self._conn is None:
            return
        try:
            self._conn.send(("clear",))
            if self._conn.poll(timeout=SPI_RENDER_TIMEOUT_SEC):
                self._conn.recv()
        except (BrokenPipeError, EOFError, OSError):
            pass

    def stop(self) -> None:
        """Stop the render subprocess gracefully."""
        if self._conn is not None:
            try:
                self._conn.send(None)
            except (BrokenPipeError, OSError):
                pass
            self._conn.close()
            self._conn = None

        if self._process is not None:
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                logger.warning(
                    "Render subprocess did not exit, killing (PID=%d)",
                    self._process.pid,
                )
                self._process.kill()
                self._process.join(timeout=1.0)
            self._process = None

    def _restart(self) -> None:
        """Kill and restart the render subprocess."""
        logger.info("Restarting render subprocess...")
        self.stop()
        try:
            self.start()
        except RuntimeError:
            logger.exception("Failed to restart render subprocess")
