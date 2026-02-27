"""LCD display manager for BLE Key Agent.

Manages screen state, composes PIL images, and drives the ST7789 LCD.
Uses the example LCD HAT driver for SPI communication.

The display is divided into three regions:
- Title region: app name + connection status
- Key region: latest key (large font) + modifier info
- Buffer region: accumulated character input

See docs/spec-raspi-receiver.md section 4 for the screen layout specification.
"""

from __future__ import annotations

import gc
import logging
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import types

from PIL import Image, ImageDraw, ImageFont

from raspi_receiver.apps.lcd_display.config import (
    BACKLIGHT_DEFAULT,
    BACKLIGHT_LEVELS,
    COLORS,
    DISPLAY_HEIGHT,
    DISPLAY_ROTATION,
    DISPLAY_WIDTH,
    FONT_DEFAULT,
    FONT_SIZE_BUFFER,
    FONT_SIZE_KEY_LARGE,
    FONT_SIZE_MODIFIER,
    FONT_SIZE_STATUS,
    FONT_SIZE_TITLE,
    INPUT_BUFFER_MAX_LENGTH,
    LAYOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class ScreenState:
    """Mutable state for the LCD display.

    Tracks all information needed to render the current screen.
    Uses a dirty flag to avoid unnecessary re-draws.
    """

    connected: bool = False
    last_key: str = ""
    last_key_type: str = ""
    modifier_text: str = ""
    input_buffer: str = ""
    dirty: bool = True  # Start dirty to draw initial screen

    def mark_dirty(self) -> None:
        """Mark the screen as needing a re-draw."""
        self.dirty = True

    def mark_clean(self) -> None:
        """Mark the screen as up-to-date."""
        self.dirty = False


class LCDDisplay:
    """LCD display manager for the 1.3inch LCD HAT.

    Handles hardware initialization, screen composition using PIL,
    and SPI communication via the ST7789 driver.

    Args:
        backlight: Initial backlight duty cycle (0-100).
    """

    def __init__(self, backlight: int = BACKLIGHT_DEFAULT) -> None:
        self._state = ScreenState()
        self._backlight = backlight
        self._disp: Any = None  # ST7789 instance, set in init()
        self._image: Optional[Image.Image] = None
        self._draw: Optional[ImageDraw.ImageDraw] = None
        self._fonts: dict[str, ImageFont.FreeTypeFont] = {}
        self.last_render_time: float = 0.0
        self._has_numpy: bool = False
        self._rgb565_buf: bytearray | None = None
        self._render_count: int = 0

    @property
    def state(self) -> ScreenState:
        """Current screen state."""
        return self._state

    def init(self) -> None:
        """Initialize LCD hardware and fonts.

        Adds the example driver directory to sys.path, imports ST7789,
        and runs hardware initialization sequence.

        If numpy is not available, the ST7789 driver's ShowImage method
        is replaced with a pure-Python RGB565 conversion to avoid the
        numpy dependency (pip install numpy often fails on ARM/Raspberry Pi).

        Raises:
            RuntimeError: If hardware initialization fails.
        """
        driver_dir = str(
            Path(__file__).resolve().parents[4]
            / "example"
            / "1.3inch_LCD_HAT_python"
        )
        if driver_dir not in sys.path:
            sys.path.insert(0, driver_dir)

        # --- Workaround: numpy optional ---
        # config.py does `import numpy as np` at top level.
        # Inject a stub if numpy is not installed (common on ARM).
        _has_numpy = "numpy" in sys.modules
        if not _has_numpy:
            try:
                import numpy  # noqa: F401
                _has_numpy = True
            except ImportError:
                _stub = types.ModuleType("numpy")
                _stub.uint8 = None  # type: ignore[attr-defined]
                sys.modules["numpy"] = _stub
                logger.info("numpy not available, using pure-Python RGB565")

        # --- Workaround: PWM fallback ---
        # config.py uses gpiozero.PWMOutputDevice for backlight.
        # If no PWM-capable pin factory is available (lgpio/RPi.GPIO/pigpio),
        # gpiozero raises PinPWMUnsupported. Replace with on/off fallback.
        _patch_pwm = False
        try:
            import gpiozero
            _test = gpiozero.PWMOutputDevice(24)
            _test.close()
        except Exception:
            _patch_pwm = True
            import gpiozero
            gpiozero.PWMOutputDevice = _DigitalBacklightFallback  # type: ignore[attr-defined]
            logger.warning(
                "PWM not supported, backlight will be on/off only"
            )

        import ST7789

        self._disp = ST7789.ST7789()

        self._has_numpy = _has_numpy
        if not _has_numpy:
            self._rgb565_buf = bytearray(DISPLAY_WIDTH * DISPLAY_HEIGHT * 2)

        # Restore original PWMOutputDevice if we patched it
        if _patch_pwm:
            import gpiozero as _gz
            _gz.PWMOutputDevice = _OriginalPWM  # type: ignore[attr-defined]

        self._disp.Init()
        self._disp.clear()
        self._disp.bl_DutyCycle(self._backlight)

        self._image = Image.new(
            "RGB",
            (DISPLAY_WIDTH, DISPLAY_HEIGHT),
            COLORS.BACKGROUND,
        )
        self._draw = ImageDraw.Draw(self._image)

        self._fonts = {
            "title": ImageFont.truetype(FONT_DEFAULT, FONT_SIZE_TITLE),
            "status": ImageFont.truetype(FONT_DEFAULT, FONT_SIZE_STATUS),
            "key_large": ImageFont.truetype(FONT_DEFAULT, FONT_SIZE_KEY_LARGE),
            "modifier": ImageFont.truetype(FONT_DEFAULT, FONT_SIZE_MODIFIER),
            "buffer": ImageFont.truetype(FONT_DEFAULT, FONT_SIZE_BUFFER),
        }

        logger.info(
            "LCD display initialized (%dx%d)", DISPLAY_WIDTH, DISPLAY_HEIGHT
        )

    def shutdown(self) -> None:
        """Shutdown LCD hardware and cleanup GPIO resources."""
        if self._disp is not None:
            self._disp.bl_DutyCycle(0)
            self._disp.module_exit()
            logger.info("LCD display shut down")

    def set_backlight(self, duty: int) -> None:
        """Set backlight brightness.

        Args:
            duty: Duty cycle percentage (0-100).
        """
        self._backlight = max(0, min(100, duty))
        if self._disp is not None:
            self._disp.bl_DutyCycle(self._backlight)

    def cycle_backlight(self) -> int:
        """Cycle through predefined backlight levels.

        Returns:
            The new backlight duty cycle value.
        """
        current_idx = -1
        for i, level in enumerate(BACKLIGHT_LEVELS):
            if level >= self._backlight:
                current_idx = i
                break
        next_idx = (current_idx + 1) % len(BACKLIGHT_LEVELS)
        new_level = BACKLIGHT_LEVELS[next_idx]
        self.set_backlight(new_level)
        return new_level

    # --- State update methods ---

    def update_connection(self, connected: bool) -> None:
        """Update connection status display.

        Args:
            connected: Whether a BLE client is connected.
        """
        if self._state.connected != connected:
            self._state.connected = connected
            self._state.mark_dirty()

    def update_key(
        self, key_value: str, key_type: str, modifier_text: str
    ) -> None:
        """Update the displayed key information.

        Args:
            key_value: The key value to display (e.g., "A", "Enter").
            key_type: The key type code ("c", "s", "m").
            modifier_text: Formatted modifier string (e.g., "Shift + A").
        """
        self._state.last_key = key_value
        self._state.last_key_type = key_type
        self._state.modifier_text = modifier_text
        self._state.mark_dirty()

    def append_buffer(self, char: str) -> None:
        """Append a character to the input buffer.

        Args:
            char: Single character to append.
        """
        if len(self._state.input_buffer) < INPUT_BUFFER_MAX_LENGTH:
            self._state.input_buffer += char
            self._state.mark_dirty()

    def handle_backspace(self) -> None:
        """Remove the last character from the input buffer."""
        if self._state.input_buffer:
            self._state.input_buffer = self._state.input_buffer[:-1]
            self._state.mark_dirty()

    def clear_buffer(self) -> None:
        """Clear the input buffer."""
        if self._state.input_buffer:
            self._state.input_buffer = ""
            self._state.mark_dirty()

    # --- Rendering ---

    def render(self) -> bool:
        """Compose and display the current screen state.

        Returns:
            True if the screen was actually re-drawn, False if skipped.
        """
        if not self._state.dirty or self._draw is None:
            return False

        # Clear canvas
        self._draw.rectangle(
            (0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT),
            fill=COLORS.BACKGROUND,
        )

        self._draw_title_region()
        self._draw_separator(LAYOUT.SEP1_Y)
        self._draw_key_region()
        self._draw_separator(LAYOUT.SEP2_Y)
        self._draw_buffer_region()

        # Rotate and send to display
        rotated = self._image.transpose(Image.Transpose.ROTATE_270)
        if self._has_numpy:
            self._disp.ShowImage(rotated)
        else:
            _show_image_rgb565(self._disp, rotated, self._rgb565_buf)
        del rotated  # Free 172KB PIL Image immediately

        self._state.mark_clean()
        self.last_render_time = time.monotonic()

        # Periodic GC to prevent memory accumulation on Pi
        self._render_count += 1
        if self._render_count % 50 == 0:
            gc.collect()

        return True

    def _draw_title_region(self) -> None:
        """Draw title and connection status."""
        assert self._draw is not None

        self._draw.text(
            (LAYOUT.MARGIN_LEFT, LAYOUT.TITLE_Y),
            "BLE Key Agent",
            fill=COLORS.TITLE,
            font=self._fonts["title"],
        )

        if self._state.connected:
            status_text = "(*) Connected"
            status_color = COLORS.CONNECTED
        else:
            status_text = "( ) Waiting..."
            status_color = COLORS.DISCONNECTED

        self._draw.text(
            (LAYOUT.MARGIN_LEFT, LAYOUT.STATUS_Y),
            status_text,
            fill=status_color,
            font=self._fonts["status"],
        )

    def _draw_key_region(self) -> None:
        """Draw the last key and modifier information."""
        assert self._draw is not None

        if not self._state.last_key:
            self._draw.text(
                (LAYOUT.MARGIN_LEFT, LAYOUT.KEY_VALUE_Y),
                "No key received",
                fill=COLORS.MODIFIER,
                font=self._fonts["modifier"],
            )
            return

        # "Last Key:" label
        self._draw.text(
            (LAYOUT.MARGIN_LEFT, LAYOUT.KEY_LABEL_Y),
            "Last Key:",
            fill=COLORS.TEXT,
            font=self._fonts["modifier"],
        )

        # Large key display (centered)
        display_value = self._format_key_display(
            self._state.last_key, self._state.last_key_type
        )
        bbox = self._fonts["key_large"].getbbox(display_value)
        text_width = bbox[2] - bbox[0] if bbox else 0
        x_centered = (DISPLAY_WIDTH - text_width) // 2
        self._draw.text(
            (x_centered, LAYOUT.KEY_VALUE_Y),
            display_value,
            fill=COLORS.KEY_VALUE,
            font=self._fonts["key_large"],
        )

        # Modifier text
        if self._state.modifier_text:
            self._draw.text(
                (LAYOUT.MARGIN_LEFT, LAYOUT.MODIFIER_Y),
                f"[{self._state.modifier_text}]",
                fill=COLORS.MODIFIER,
                font=self._fonts["modifier"],
            )

    def _draw_buffer_region(self) -> None:
        """Draw the input buffer."""
        assert self._draw is not None

        buffer_text = self._state.input_buffer
        if buffer_text:
            display_text = f"> {buffer_text}_"
            # Truncate from left if too long for display
            max_chars = (DISPLAY_WIDTH - 2 * LAYOUT.MARGIN_LEFT) // 8
            if len(display_text) > max_chars:
                display_text = (
                    "> ..." + buffer_text[-(max_chars - 6) :] + "_"
                )
        else:
            display_text = "> _"

        self._draw.text(
            (LAYOUT.MARGIN_LEFT, LAYOUT.BUFFER_Y),
            display_text,
            fill=COLORS.BUFFER_TEXT,
            font=self._fonts["buffer"],
        )

    def _draw_separator(self, y: int) -> None:
        """Draw a horizontal separator line."""
        assert self._draw is not None

        self._draw.line(
            [(LAYOUT.MARGIN_LEFT, y), (LAYOUT.MARGIN_RIGHT, y)],
            fill=COLORS.SEPARATOR,
            width=1,
        )

    @staticmethod
    def _format_key_display(key_value: str, key_type: str) -> str:
        """Format key value for large display.

        Args:
            key_value: Raw key value from KeyEvent.
            key_type: Key type code ("c", "s", "m").

        Returns:
            Formatted string for display.
        """
        if key_type == "c":
            if key_value == " ":
                return "Space"
            return key_value
        elif key_type == "s":
            return key_value.capitalize()
        elif key_type == "m":
            return key_value.capitalize()
        return key_value


# --- PWM fallback for environments without lgpio/RPi.GPIO/pigpio ---
# gpiozero's NativeFactory doesn't support PWM. When no PWM-capable pin
# factory is available, we temporarily swap PWMOutputDevice with this
# DigitalOutputDevice wrapper so that ST7789() construction succeeds.
# Backlight becomes simple on/off (no dimming) but the app still works.

_OriginalPWM: Any = None  # Saved before patching, restored after

try:
    import gpiozero as _gz

    _OriginalPWM = _gz.PWMOutputDevice
except Exception:
    pass


class _DigitalBacklightFallback:
    """Drop-in replacement for PWMOutputDevice using on/off only."""

    def __init__(self, pin: int, frequency: int = 1000, **kwargs: Any) -> None:
        from gpiozero import DigitalOutputDevice

        self._device = DigitalOutputDevice(pin)
        self._value = 0.0

    @property
    def value(self) -> float:
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
        return 1000

    @frequency.setter
    def frequency(self, f: int) -> None:
        pass  # no-op

    def close(self) -> None:
        self._device.close()


def _show_image_rgb565(
    disp: Any, image: Image.Image, buf: bytearray | None = None
) -> None:
    """Pure-Python ShowImage replacement (no numpy required).

    Converts an RGB888 PIL Image to RGB565 and sends it to the
    ST7789 LCD via SPI. Uses struct.pack_into for in-place buffer
    writes and passes bytearray slices directly to SPI (no list copy).

    Args:
        disp: ST7789 driver instance.
        image: PIL Image in RGB mode, must match display dimensions.
        buf: Optional pre-allocated bytearray for RGB565 output.
             If None, a new buffer is created each call.
    """
    imwidth, imheight = image.size
    if imwidth != disp.width or imheight != disp.height:
        raise ValueError(
            f"Image must be {disp.width}x{disp.height}, "
            f"got {imwidth}x{imheight}"
        )

    if image.mode != "RGB":
        image = image.convert("RGB")

    pixels = image.tobytes()
    num_pixels = disp.width * disp.height
    pix = buf if buf is not None else bytearray(num_pixels * 2)

    for i in range(num_pixels):
        off = i * 3
        r, g, b = pixels[off], pixels[off + 1], pixels[off + 2]
        struct.pack_into(
            ">H", pix, i * 2,
            ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3),
        )

    del pixels  # Free 172KB tobytes() result immediately

    disp.SetWindows(0, 0, disp.width, disp.height)
    disp.digital_write(disp.GPIO_DC_PIN, True)
    for i in range(0, len(pix), 4096):
        disp.spi_writebyte(pix[i:i + 4096])
