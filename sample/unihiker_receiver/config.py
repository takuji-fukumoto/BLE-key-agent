"""Configuration constants for UNIHIKER display sample."""

from __future__ import annotations

from dataclasses import dataclass

SCREEN_WIDTH: int = 240
SCREEN_HEIGHT: int = 320
INPUT_BUFFER_MAX_LENGTH: int = 200
BUFFER_VISIBLE_CHARS: int = 28
EVENT_QUEUE_MAX_SIZE: int = 512
RENDER_INTERVAL_MS: int = 50


@dataclass(frozen=True)
class Layout:
    """Pixel layout for the UNIHIKER sample screen."""

    title_x: int = 120
    title_y: int = 16
    status_x: int = 120
    status_y: int = 44
    key_label_x: int = 20
    key_label_y: int = 96
    key_value_x: int = 20
    key_value_y: int = 128
    modifier_x: int = 20
    modifier_y: int = 170
    buffer_x: int = 20
    buffer_y: int = 276


LAYOUT = Layout()
