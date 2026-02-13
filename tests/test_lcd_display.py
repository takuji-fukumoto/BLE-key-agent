"""Unit tests for raspi_receiver.apps.lcd_display module.

Tests cover screen state management, display state updates,
key formatting, modifier formatting, and event processing
without requiring LCD hardware (ST7789/SPI mocked).
"""

from unittest.mock import MagicMock, patch

import pytest

from common.protocol import KeyType, Modifiers
from raspi_receiver.apps.lcd_display.display import LCDDisplay, ScreenState
from raspi_receiver.apps.lcd_display.main import (
    DisplayConnectionEvent,
    DisplayKeyEvent,
    LCDApp,
)


# --- TestScreenState ---


class TestScreenState:
    """Tests for ScreenState dirty flag behavior and state transitions."""

    def test_initial_state_is_dirty(self) -> None:
        state = ScreenState()
        assert state.dirty is True

    def test_initial_state_defaults(self) -> None:
        state = ScreenState()
        assert state.connected is False
        assert state.last_key == ""
        assert state.last_key_type == ""
        assert state.modifier_text == ""
        assert state.input_buffer == ""

    def test_mark_clean(self) -> None:
        state = ScreenState()
        state.mark_clean()
        assert state.dirty is False

    def test_mark_dirty(self) -> None:
        state = ScreenState()
        state.mark_clean()
        state.mark_dirty()
        assert state.dirty is True

    def test_mark_dirty_idempotent(self) -> None:
        state = ScreenState()
        state.mark_dirty()
        state.mark_dirty()
        assert state.dirty is True


# --- TestLCDDisplayStateUpdates ---


class TestLCDDisplayStateUpdates:
    """Tests for LCDDisplay state update methods (no hardware needed)."""

    def test_update_connection_sets_dirty(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        display.update_connection(True)
        assert display.state.connected is True
        assert display.state.dirty is True

    def test_update_connection_same_value_not_dirty(self) -> None:
        display = LCDDisplay()
        display.update_connection(False)
        display.state.mark_clean()
        display.update_connection(False)
        assert display.state.dirty is False

    def test_update_key(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        display.update_key("a", "c", "")
        assert display.state.last_key == "a"
        assert display.state.last_key_type == "c"
        assert display.state.modifier_text == ""
        assert display.state.dirty is True

    def test_update_key_with_modifier(self) -> None:
        display = LCDDisplay()
        display.update_key("A", "c", "Shift + A")
        assert display.state.modifier_text == "Shift + A"

    def test_append_buffer(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        display.append_buffer("a")
        assert display.state.input_buffer == "a"
        assert display.state.dirty is True

    def test_append_buffer_accumulates(self) -> None:
        display = LCDDisplay()
        display.append_buffer("H")
        display.append_buffer("i")
        assert display.state.input_buffer == "Hi"

    def test_append_buffer_max_length(self) -> None:
        display = LCDDisplay()
        display.state.input_buffer = "x" * 200
        display.state.mark_clean()
        display.append_buffer("y")
        assert len(display.state.input_buffer) == 200
        assert display.state.dirty is False

    def test_handle_backspace(self) -> None:
        display = LCDDisplay()
        display.append_buffer("a")
        display.append_buffer("b")
        display.state.mark_clean()
        display.handle_backspace()
        assert display.state.input_buffer == "a"
        assert display.state.dirty is True

    def test_handle_backspace_empty_buffer(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        display.handle_backspace()
        assert display.state.input_buffer == ""
        assert display.state.dirty is False

    def test_clear_buffer(self) -> None:
        display = LCDDisplay()
        display.append_buffer("Hello")
        display.state.mark_clean()
        display.clear_buffer()
        assert display.state.input_buffer == ""
        assert display.state.dirty is True

    def test_clear_buffer_already_empty(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        display.clear_buffer()
        assert display.state.dirty is False

    def test_render_skips_when_not_dirty(self) -> None:
        display = LCDDisplay()
        display.state.mark_clean()
        result = display.render()
        assert result is False

    def test_render_skips_when_draw_is_none(self) -> None:
        display = LCDDisplay()
        # _draw is None (init() not called)
        result = display.render()
        assert result is False

    def test_cycle_backlight(self) -> None:
        display = LCDDisplay(backlight=50)
        mock_disp = MagicMock()
        display._disp = mock_disp
        new_level = display.cycle_backlight()
        assert new_level == 75
        mock_disp.bl_DutyCycle.assert_called_with(75)

    def test_cycle_backlight_wraps(self) -> None:
        display = LCDDisplay(backlight=100)
        mock_disp = MagicMock()
        display._disp = mock_disp
        new_level = display.cycle_backlight()
        assert new_level == 0


# --- TestFormatKeyDisplay ---


class TestFormatKeyDisplay:
    """Tests for LCDDisplay._format_key_display static method."""

    def test_char_key(self) -> None:
        assert LCDDisplay._format_key_display("a", "c") == "a"

    def test_char_key_uppercase(self) -> None:
        assert LCDDisplay._format_key_display("A", "c") == "A"

    def test_space_key(self) -> None:
        assert LCDDisplay._format_key_display(" ", "c") == "Space"

    def test_special_key(self) -> None:
        assert LCDDisplay._format_key_display("enter", "s") == "Enter"

    def test_special_key_backspace(self) -> None:
        assert LCDDisplay._format_key_display("backspace", "s") == "Backspace"

    def test_modifier_key(self) -> None:
        assert LCDDisplay._format_key_display("shift", "m") == "Shift"

    def test_unknown_type(self) -> None:
        assert LCDDisplay._format_key_display("x", "?") == "x"


# --- TestFormatModifiers ---


class TestFormatModifiers:
    """Tests for LCDApp._format_modifiers static method."""

    def test_no_modifiers(self) -> None:
        result = LCDApp._format_modifiers("a", None)
        assert result == ""

    def test_default_modifiers(self) -> None:
        result = LCDApp._format_modifiers("a", Modifiers())
        assert result == ""

    def test_shift_only(self) -> None:
        result = LCDApp._format_modifiers("A", Modifiers(shift=True))
        assert result == "Shift + A"

    def test_ctrl_alt(self) -> None:
        result = LCDApp._format_modifiers("c", Modifiers(ctrl=True, alt=True))
        assert result == "Ctrl + Alt + c"

    def test_all_modifiers(self) -> None:
        result = LCDApp._format_modifiers(
            "a", Modifiers(cmd=True, ctrl=True, alt=True, shift=True)
        )
        assert result == "Cmd + Ctrl + Alt + Shift + a"

    def test_cmd_only(self) -> None:
        result = LCDApp._format_modifiers("q", Modifiers(cmd=True))
        assert result == "Cmd + q"


# --- TestProcessEvent ---


class TestProcessEvent:
    """Tests for LCDApp._process_event with mocked display."""

    @pytest.fixture
    def app(self) -> LCDApp:
        """Create LCDApp with mocked internals."""
        with patch(
            "raspi_receiver.apps.lcd_display.main.KeyReceiver"
        ), patch("raspi_receiver.apps.lcd_display.main.LCDDisplay") as mock_display_cls:
            mock_display = MagicMock()
            mock_display_cls.return_value = mock_display
            app = LCDApp()
            yield app

    def test_connection_event_updates_display(self, app: LCDApp) -> None:
        event = DisplayConnectionEvent(connected=True)
        app._process_event(event)
        app._display.update_connection.assert_called_once_with(True)

    def test_disconnection_event(self, app: LCDApp) -> None:
        event = DisplayConnectionEvent(connected=False)
        app._process_event(event)
        app._display.update_connection.assert_called_once_with(False)

    def test_key_press_updates_key_and_buffer(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="a", key_type=KeyType.CHAR.value, press=True, modifiers=None
        )
        app._process_event(event)
        app._display.update_key.assert_called_once_with("a", "c", "")
        app._display.append_buffer.assert_called_once_with("a")

    def test_key_release_ignored(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="a", key_type=KeyType.CHAR.value, press=False, modifiers=None
        )
        app._process_event(event)
        app._display.update_key.assert_not_called()
        app._display.append_buffer.assert_not_called()

    def test_enter_clears_buffer(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="enter",
            key_type=KeyType.SPECIAL.value,
            press=True,
            modifiers=None,
        )
        app._process_event(event)
        app._display.clear_buffer.assert_called_once()

    def test_backspace_removes_char(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="backspace",
            key_type=KeyType.SPECIAL.value,
            press=True,
            modifiers=None,
        )
        app._process_event(event)
        app._display.handle_backspace.assert_called_once()

    def test_space_appends_to_buffer(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="space",
            key_type=KeyType.SPECIAL.value,
            press=True,
            modifiers=None,
        )
        app._process_event(event)
        app._display.append_buffer.assert_called_once_with(" ")

    def test_key_with_modifiers(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="A",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=Modifiers(shift=True),
        )
        app._process_event(event)
        app._display.update_key.assert_called_once_with(
            "A", "c", "Shift + A"
        )

    def test_modifier_key_press(self, app: LCDApp) -> None:
        event = DisplayKeyEvent(
            key_value="shift",
            key_type=KeyType.MODIFIER.value,
            press=True,
            modifiers=None,
        )
        app._process_event(event)
        app._display.update_key.assert_called_once_with("shift", "m", "")
        # Modifier keys should not be appended to buffer
        app._display.append_buffer.assert_not_called()
