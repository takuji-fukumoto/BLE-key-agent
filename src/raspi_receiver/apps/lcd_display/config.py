"""Hardware configuration and display layout constants for LCD HAT app.

Centralizes GPIO pin definitions, display parameters, font paths,
layout coordinates, color palette, and timing constants.

Hardware: 1.3inch LCD HAT (ST7789, 240x240, SPI)
Reference: example/1.3inch_LCD_HAT_python/config.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --- GPIO Pin Definitions (BCM numbering) ---

# Physical buttons
GPIO_KEY1: int = 21  # Buffer clear
GPIO_KEY2: int = 20  # Backlight control

# --- Display Constants ---

DISPLAY_WIDTH: int = 240
DISPLAY_HEIGHT: int = 240
DISPLAY_ROTATION: int = 270  # Rotation for correct orientation

# --- Backlight ---

BACKLIGHT_DEFAULT: int = 50  # Duty cycle percentage (0-100)
BACKLIGHT_LEVELS: list[int] = [0, 25, 50, 75, 100]

# --- Font Configuration ---

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # src/../../../..
FONT_DIR: Path = _PROJECT_ROOT / "example" / "1.3inch_LCD_HAT_python" / "Font"
FONT_DEFAULT: str = str(FONT_DIR / "Font01.ttf")

# Font sizes
FONT_SIZE_TITLE: int = 18
FONT_SIZE_STATUS: int = 16
FONT_SIZE_KEY_LARGE: int = 48
FONT_SIZE_MODIFIER: int = 16
FONT_SIZE_BUFFER: int = 16


# --- Color Palette ---

@dataclass(frozen=True)
class Colors:
    """Display color constants (RGB tuples)."""

    BACKGROUND: tuple[int, int, int] = (0, 0, 0)
    TEXT: tuple[int, int, int] = (255, 255, 255)
    TITLE: tuple[int, int, int] = (100, 180, 255)
    CONNECTED: tuple[int, int, int] = (0, 200, 80)
    DISCONNECTED: tuple[int, int, int] = (200, 60, 60)
    KEY_VALUE: tuple[int, int, int] = (255, 255, 100)
    MODIFIER: tuple[int, int, int] = (180, 180, 180)
    BUFFER_TEXT: tuple[int, int, int] = (200, 200, 200)
    SEPARATOR: tuple[int, int, int] = (60, 60, 60)


COLORS = Colors()


# --- Layout Regions (Y coordinates for 240x240 display) ---

@dataclass(frozen=True)
class Layout:
    """Screen layout coordinates."""

    # Title region
    TITLE_Y: int = 8
    STATUS_Y: int = 32

    # Separator line 1
    SEP1_Y: int = 55

    # Key display region
    KEY_LABEL_Y: int = 65
    KEY_VALUE_Y: int = 85
    MODIFIER_Y: int = 140

    # Separator line 2
    SEP2_Y: int = 165

    # Input buffer region
    BUFFER_Y: int = 175

    # Margins
    MARGIN_LEFT: int = 10
    MARGIN_RIGHT: int = 230


LAYOUT = Layout()

# --- Rendering Control ---

RENDER_MIN_INTERVAL_MS: int = 50  # Minimum ms between LCD re-draws (20 FPS cap)
INPUT_BUFFER_MAX_LENGTH: int = 200  # Max characters in input buffer
BUTTON_POLL_INTERVAL_MS: int = 100  # Physical button polling interval
EVENT_QUEUE_MAX_SIZE: int = 128  # Max pending display events (backpressure)

# --- SPI Configuration ---

# SPI bus speed in Hz. Reduced from driver default (40MHz) because the
# ST7789V datasheet specifies a maximum write clock of ~15MHz.  On
# Raspberry Pi the SPI divider rounds to 128MHz/8 ≈ 15.6MHz actual.
SPI_SPEED_HZ: int = 20_000_000

# Timeout for a single render operation in the SPI subprocess.
# If the subprocess does not respond within this time, it is killed
# and restarted automatically.
SPI_RENDER_TIMEOUT_SEC: float = 5.0
