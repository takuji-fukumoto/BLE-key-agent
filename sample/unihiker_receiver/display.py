"""UNIHIKER GUI display adapter for key receiver sample."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

from common.protocol import KeyEvent, KeyType, Modifiers

from .config import BUFFER_VISIBLE_CHARS, INPUT_BUFFER_MAX_LENGTH, LAYOUT

logger = logging.getLogger(__name__)


@dataclass
class UnihikerScreenState:
    """Mutable screen state for the UNIHIKER sample.

    Attributes:
        connected: BLE connection status.
        last_key: Latest key text for large display.
        key_type: Latest key type code.
        modifier_text: Formatted modifier text.
        input_buffer: Recent input buffer.
        dirty: Whether render update is required.
    """

    connected: bool = False
    last_key: str = ""
    key_type: str = ""
    modifier_text: str = ""
    input_buffer: str = ""
    dirty: bool = True

    def mark_dirty(self) -> None:
        """Mark the state as dirty."""
        self.dirty = True

    def mark_clean(self) -> None:
        """Mark the state as clean."""
        self.dirty = False


class UnihikerDisplayAdapter:
    """Display adapter using UNIHIKER `GUI` widgets.

    This class centralizes GUI updates into `render()`. Callers only update
    state through dedicated methods and never call GUI widget APIs directly.

    Args:
        gui: Optional pre-created GUI instance for testing.
    """

    def __init__(self, gui: Any | None = None) -> None:
        self._gui: Any | None = gui
        self._state = UnihikerScreenState()
        self._initialized = False
        self._title_widget: Any | None = None
        self._status_widget: Any | None = None
        self._key_widget: Any | None = None
        self._modifier_widget: Any | None = None
        self._buffer_widget: Any | None = None
        self._stop_button: Any | None = None
        self.on_stop: Callable[[], None] | None = None

    @property
    def state(self) -> UnihikerScreenState:
        """Return the current screen state."""
        return self._state

    def init(self) -> None:
        """Initialize GUI widgets.

        Raises:
            RuntimeError: If `unihiker` package is unavailable.
        """
        if self._initialized:
            return

        if self._gui is None:
            try:
                gui_module = importlib.import_module("unihiker")
            except ImportError as exc:
                raise RuntimeError(
                    "`unihiker` package is required for UNIHIKER display. "
                    "Install with: pip install -U unihiker"
                ) from exc
            self._gui = gui_module.GUI()

        self._title_widget = self._gui.draw_text(
            x=LAYOUT.title_x,
            y=LAYOUT.title_y,
            text="BLE Key Agent",
            origin="center",
            font_size=20,
            color="#FFFFFF",
        )
        self._status_widget = self._gui.draw_text(
            x=LAYOUT.status_x,
            y=LAYOUT.status_y,
            text="Status: Waiting",
            origin="center",
            font_size=16,
            color="#AAAAAA",
        )
        self._key_widget = self._gui.draw_text(
            x=LAYOUT.key_label_x,
            y=LAYOUT.key_label_y,
            text="Last Key: -",
            origin="top_left",
            font_size=24,
            color="#00E5FF",
        )
        self._modifier_widget = self._gui.draw_text(
            x=LAYOUT.modifier_x,
            y=LAYOUT.modifier_y,
            text="",
            origin="top_left",
            font_size=16,
            color="#FFD54F",
        )
        self._buffer_widget = self._gui.draw_text(
            x=LAYOUT.buffer_x,
            y=LAYOUT.buffer_y,
            text="> _",
            origin="top_left",
            font_size=16,
            color="#FFFFFF",
        )

        self._stop_button = self._gui.add_button(
            x=LAYOUT.stop_button_x,
            y=LAYOUT.stop_button_y,
            w=LAYOUT.stop_button_w,
            h=LAYOUT.stop_button_h,
            text="Stop",
            origin="center",
            onclick=self._handle_stop_click,
        )

        self._initialized = True
        self.render(force=True)

    def _handle_stop_click(self) -> None:
        """Handle stop button click event."""
        logger.info("Stop button clicked")
        if self.on_stop is not None:
            self.on_stop()

    def shutdown(self) -> None:
        """Clear widgets and reset display state."""
        if self._gui is not None:
            self._gui.clear()
        self._initialized = False

    def update_connection(self, connected: bool) -> None:
        """Update connection state.

        Args:
            connected: Current BLE connection state.
        """
        if self._state.connected != connected:
            self._state.connected = connected
            self._state.mark_dirty()

    def update_key(self, key_text: str, key_type: str, modifier_text: str) -> None:
        """Update latest key display state.

        Args:
            key_text: Formatted key display text.
            key_type: Key type code.
            modifier_text: Formatted modifiers.
        """
        self._state.last_key = key_text
        self._state.key_type = key_type
        self._state.modifier_text = modifier_text
        self._state.mark_dirty()

    def append_buffer(self, char: str) -> None:
        """Append one character to input buffer.

        Args:
            char: Character to append.
        """
        if len(self._state.input_buffer) >= INPUT_BUFFER_MAX_LENGTH:
            return
        self._state.input_buffer += char
        self._state.mark_dirty()

    def handle_backspace(self) -> None:
        """Delete one character from input buffer."""
        if not self._state.input_buffer:
            return
        self._state.input_buffer = self._state.input_buffer[:-1]
        self._state.mark_dirty()

    def clear_buffer(self) -> None:
        """Clear input buffer."""
        if not self._state.input_buffer:
            return
        self._state.input_buffer = ""
        self._state.mark_dirty()

    def apply_key_event(self, event: KeyEvent) -> None:
        """Apply a key event to display state.

        Args:
            event: Incoming key event.
        """
        if not event.press:
            return

        key_type_code = event.key_type.value
        key_text = self.format_key_display(event.value, key_type_code)
        modifier_text = self.format_modifiers(event.value, event.modifiers)

        self.update_key(key_text=key_text, key_type=key_type_code, modifier_text=modifier_text)

        if event.key_type == KeyType.CHAR:
            self.append_buffer(event.value)
        elif event.key_type == KeyType.SPECIAL:
            if event.value == "enter":
                self.clear_buffer()
            elif event.value == "backspace":
                self.handle_backspace()
            elif event.value == "space":
                self.append_buffer(" ")

    def render(self, force: bool = False) -> bool:
        """Reflect state to GUI widgets.

        Args:
            force: Whether to update even when not dirty.

        Returns:
            True if widget updates were applied.
        """
        if not self._initialized:
            raise RuntimeError("Display is not initialized. Call init() first.")

        if not force and not self._state.dirty:
            return False

        status_text = "Connected" if self._state.connected else "Waiting"
        status_color = "#00E676" if self._state.connected else "#AAAAAA"

        assert self._status_widget is not None
        assert self._key_widget is not None
        assert self._modifier_widget is not None
        assert self._buffer_widget is not None

        self._status_widget.config(text=f"Status: {status_text}", color=status_color)

        key_text = self._state.last_key if self._state.last_key else "-"
        self._key_widget.config(text=f"Last Key: {key_text}")

        modifier_display = self._state.modifier_text
        self._modifier_widget.config(text=modifier_display)

        self._buffer_widget.config(text=self._build_buffer_text(self._state.input_buffer))

        self._state.mark_clean()
        return True

    @staticmethod
    def format_modifiers(key_value: str, modifiers: Modifiers | None) -> str:
        """Format modifier state.

        Args:
            key_value: Key value.
            modifiers: Modifier state.

        Returns:
            Modifier display text.
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

    @staticmethod
    def format_key_display(key_value: str, key_type: str) -> str:
        """Format latest key text.

        Args:
            key_value: Raw key value.
            key_type: Key type code.

        Returns:
            Display text.
        """
        if key_type == KeyType.CHAR.value:
            return "Space" if key_value == " " else key_value
        if key_type in (KeyType.SPECIAL.value, KeyType.MODIFIER.value):
            return key_value.capitalize()
        return key_value

    @staticmethod
    def _build_buffer_text(buffer_text: str) -> str:
        """Build one-line input buffer display text.

        Args:
            buffer_text: Raw input buffer.

        Returns:
            Formatted buffer text for screen.
        """
        if not buffer_text:
            return "> _"

        if len(buffer_text) <= BUFFER_VISIBLE_CHARS:
            return f"> {buffer_text}_"

        tail = buffer_text[-BUFFER_VISIBLE_CHARS:]
        return f"> ...{tail}_"
