"""LCD display manager for BLE Key Agent.

Manages screen state, composes PIL images, and drives the ST7789 LCD
via a subprocess-based SPI renderer.

The display is divided into three regions:
- Title region: app name + connection status
- Key region: latest key (large font) + modifier info
- Buffer region: accumulated character input

SPI writes are executed in a separate subprocess to prevent GIL-level
freezes.  The spidev C extension holds the GIL during blocking ioctl()
calls; by isolating SPI in its own process, the main process (asyncio,
bless, watchdog) stays responsive even if SPI hangs.

See docs/spec-raspi-receiver.md section 4 for the screen layout specification.
"""

from __future__ import annotations

import gc
import logging
import struct
import time
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from raspi_receiver.apps.lcd_display.config import (
    BACKLIGHT_DEFAULT,
    BACKLIGHT_LEVELS,
    COLORS,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    FONT_DEFAULT,
    FONT_SIZE_BUFFER,
    FONT_SIZE_KEY_LARGE,
    FONT_SIZE_MODIFIER,
    FONT_SIZE_STATUS,
    FONT_SIZE_TITLE,
    INPUT_BUFFER_MAX_LENGTH,
    LAYOUT,
    SPI_SPEED_HZ,
)
from raspi_receiver.apps.lcd_display.render_process import RenderProxy

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

    Handles screen composition using PIL and delegates SPI
    communication to a subprocess-based renderer.

    Args:
        backlight: Initial backlight duty cycle (0-100).
        spi_speed: SPI bus speed in Hz.
    """

    def __init__(
        self,
        backlight: int = BACKLIGHT_DEFAULT,
        spi_speed: int = SPI_SPEED_HZ,
    ) -> None:
        self._state = ScreenState()
        self._backlight = backlight
        self._spi_speed = spi_speed
        self._render_proxy: RenderProxy | None = None
        self._image: Optional[Image.Image] = None
        self._draw: Optional[ImageDraw.ImageDraw] = None
        self._fonts: dict[str, ImageFont.FreeTypeFont] = {}
        self._last_render_time: float = 0.0
        self._rgb565_buf: bytearray = bytearray(
            DISPLAY_WIDTH * DISPLAY_HEIGHT * 2
        )
        self._render_count: int = 0

    @property
    def state(self) -> ScreenState:
        """Current screen state."""
        return self._state

    def time_since_render(self) -> float:
        """Return seconds elapsed since the last render."""
        return time.monotonic() - self._last_render_time

    def init(self) -> None:
        """Initialize LCD hardware and fonts.

        Starts the SPI render subprocess which initializes the ST7789
        driver, then sets up PIL image and fonts for composition.

        Raises:
            RuntimeError: If the render subprocess fails to start.
        """
        # Start render subprocess (handles all hardware init)
        self._render_proxy = RenderProxy(spi_speed=self._spi_speed)
        self._render_proxy.start()
        self._render_proxy.set_backlight(self._backlight)

        # Create PIL image for composition
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
            "LCD display initialized (%dx%d, SPI=%dHz)",
            DISPLAY_WIDTH,
            DISPLAY_HEIGHT,
            self._spi_speed,
        )

    def shutdown(self) -> None:
        """Shutdown LCD hardware and cleanup resources."""
        if self._render_proxy is not None:
            self._render_proxy.set_backlight(0)
            self._render_proxy.stop()
            self._render_proxy = None
            logger.info("LCD display shut down")

    def set_backlight(self, duty: int) -> None:
        """Set backlight brightness.

        Args:
            duty: Duty cycle percentage (0-100).
        """
        self._backlight = max(0, min(100, duty))
        if self._render_proxy is not None:
            self._render_proxy.set_backlight(self._backlight)

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

    def read_buttons(self) -> tuple[bool, bool]:
        """Read physical button states via render subprocess.

        Returns:
            Tuple of (key1_pressed, key2_pressed).
        """
        if self._render_proxy is None:
            return False, False
        return self._render_proxy.read_buttons()

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

        PIL composition happens in the main process.  The resulting
        RGB565 buffer is sent to the render subprocess for SPI write.

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

        # Rotate for correct LCD orientation
        rotated = self._image.transpose(Image.Transpose.ROTATE_270)

        # Convert to RGB565 and send to subprocess for SPI write
        _convert_to_rgb565(rotated, self._rgb565_buf)
        del rotated  # Free 172KB PIL Image immediately

        if self._render_proxy is not None:
            self._render_proxy.render(
                self._rgb565_buf, DISPLAY_WIDTH, DISPLAY_HEIGHT
            )

        self._state.mark_clean()
        self._last_render_time = time.monotonic()

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


def _convert_to_rgb565(
    image: Image.Image, buf: bytearray | None = None
) -> bytearray:
    """Convert RGB888 PIL Image to RGB565 bytearray.

    Uses struct.pack_into for in-place buffer writes to minimize
    memory allocations.

    Args:
        image: PIL Image in RGB mode.
        buf: Optional pre-allocated bytearray for output.
             If None, a new buffer is created.

    Returns:
        Bytearray containing RGB565 pixel data.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")

    pixels = image.tobytes()
    num_pixels = image.size[0] * image.size[1]
    pix = buf if buf is not None else bytearray(num_pixels * 2)

    for i in range(num_pixels):
        off = i * 3
        r, g, b = pixels[off], pixels[off + 1], pixels[off + 2]
        struct.pack_into(
            ">H",
            pix,
            i * 2,
            ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3),
        )

    del pixels  # Free 172KB tobytes() result immediately
    return pix
