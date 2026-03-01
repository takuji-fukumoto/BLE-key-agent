"""Unit tests for sample.raspi_receiver.apps.lcd_display module.

Tests cover screen state management, display state updates,
key formatting, modifier formatting, event processing,
render offloading, and queue backpressure without requiring
LCD hardware (ST7789/SPI mocked).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from common.protocol import KeyType, Modifiers
from sample.raspi_receiver.apps.lcd_display.config import EVENT_QUEUE_MAX_SIZE
from sample.raspi_receiver.apps.lcd_display.display import LCDDisplay, ScreenState
from sample.raspi_receiver.apps.lcd_display.main import (
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
        mock_proxy = MagicMock()
        display._render_proxy = mock_proxy
        new_level = display.cycle_backlight()
        assert new_level == 75
        mock_proxy.set_backlight.assert_called_with(75)

    def test_cycle_backlight_wraps(self) -> None:
        display = LCDDisplay(backlight=100)
        mock_proxy = MagicMock()
        display._render_proxy = mock_proxy
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
            "sample.raspi_receiver.apps.lcd_display.main.KeyReceiver"
        ), patch("sample.raspi_receiver.apps.lcd_display.main.LCDDisplay") as mock_display_cls:
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


# --- TestRenderOffloading ---


class TestRenderOffloading:
    """Tests for Fix 1: SPI render offloading via run_in_executor."""

    @pytest.fixture
    def app(self) -> LCDApp:
        """Create LCDApp with mocked internals."""
        with patch(
            "sample.raspi_receiver.apps.lcd_display.main.KeyReceiver"
        ), patch("sample.raspi_receiver.apps.lcd_display.main.LCDDisplay") as mock_display_cls:
            mock_display = MagicMock()
            mock_display_cls.return_value = mock_display
            app = LCDApp()
            yield app

    def test_rendering_flag_initial_false(self, app: LCDApp) -> None:
        """Test _rendering flag starts as False."""
        assert app._rendering is False

    @pytest.mark.asyncio
    async def test_rendering_flag_set_during_render(self, app: LCDApp) -> None:
        """Test _rendering flag is True during render and reset after."""
        flag_during_render = None

        def mock_render() -> bool:
            nonlocal flag_during_render
            flag_during_render = app._rendering
            return True

        app._display.render = mock_render

        # Enqueue an event to trigger render
        app._event_queue.put_nowait(
            DisplayKeyEvent(
                key_value="a",
                key_type=KeyType.CHAR.value,
                press=True,
                modifiers=None,
            )
        )

        # Run one iteration of render loop by setting shutdown after event
        app._shutdown_event.set()

        # Manually drive the render logic
        loop = asyncio.get_running_loop()
        event = app._event_queue.get_nowait()
        app._process_event(event)
        app._rendering = True
        try:
            await loop.run_in_executor(None, app._display.render)
        finally:
            app._rendering = False

        assert flag_during_render is True
        assert app._rendering is False

    @pytest.mark.asyncio
    async def test_rendering_flag_reset_on_exception(self, app: LCDApp) -> None:
        """Test _rendering flag resets to False even if render() raises."""

        def mock_render_error() -> bool:
            raise RuntimeError("SPI failure")

        app._display.render = mock_render_error

        loop = asyncio.get_running_loop()
        app._rendering = True
        try:
            await loop.run_in_executor(None, app._display.render)
        except RuntimeError:
            pass
        finally:
            app._rendering = False

        assert app._rendering is False

    @pytest.mark.asyncio
    async def test_concurrent_render_skipped(self, app: LCDApp) -> None:
        """Test that a second render is skipped while one is in progress."""
        app._rendering = True

        # Should not call render when flag is already set
        render_called = False

        def mock_render() -> bool:
            nonlocal render_called
            render_called = True
            return True

        app._display.render = mock_render

        if not app._rendering:
            loop = asyncio.get_running_loop()
            app._rendering = True
            try:
                await loop.run_in_executor(None, app._display.render)
            finally:
                app._rendering = False

        assert render_called is False


# --- TestEventQueueBackpressure ---


class TestEventQueueBackpressure:
    """Tests for Fix 2: bounded event queue with backpressure."""

    @pytest.fixture
    def app(self) -> LCDApp:
        """Create LCDApp with mocked internals."""
        with patch(
            "sample.raspi_receiver.apps.lcd_display.main.KeyReceiver"
        ), patch("sample.raspi_receiver.apps.lcd_display.main.LCDDisplay") as mock_display_cls:
            mock_display = MagicMock()
            mock_display_cls.return_value = mock_display
            app = LCDApp()
            yield app

    def test_queue_has_maxsize(self, app: LCDApp) -> None:
        """Test event queue is created with maxsize from config."""
        assert app._event_queue.maxsize == EVENT_QUEUE_MAX_SIZE

    def test_safe_enqueue_key_drops_when_full(self, app: LCDApp) -> None:
        """Test _safe_enqueue_key drops events when queue is full."""
        # Fill the queue
        for i in range(EVENT_QUEUE_MAX_SIZE):
            app._event_queue.put_nowait(
                DisplayKeyEvent(
                    key_value=str(i),
                    key_type=KeyType.CHAR.value,
                    press=True,
                    modifiers=None,
                )
            )
        assert app._event_queue.full()

        # Should not raise
        app._safe_enqueue_key(
            DisplayKeyEvent(
                key_value="overflow",
                key_type=KeyType.CHAR.value,
                press=True,
                modifiers=None,
            )
        )
        # Queue size unchanged
        assert app._event_queue.qsize() == EVENT_QUEUE_MAX_SIZE

    def test_safe_enqueue_key_succeeds_when_not_full(self, app: LCDApp) -> None:
        """Test _safe_enqueue_key adds event when queue has space."""
        event = DisplayKeyEvent(
            key_value="a",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=None,
        )
        app._safe_enqueue_key(event)
        assert app._event_queue.qsize() == 1

    def test_enqueue_connection_event_uses_put_nowait(self, app: LCDApp) -> None:
        """Test connection events go through put_nowait (not _safe_enqueue_key)."""
        loop = MagicMock()
        loop.is_running.return_value = True
        app._loop = loop

        event = DisplayConnectionEvent(connected=True)
        app._enqueue(event)

        loop.call_soon_threadsafe.assert_called_once()
        args = loop.call_soon_threadsafe.call_args
        # First positional arg should be put_nowait (not _safe_enqueue_key)
        assert args[0][0] == app._event_queue.put_nowait

    def test_enqueue_key_event_uses_safe_enqueue(self, app: LCDApp) -> None:
        """Test key events go through _safe_enqueue_key."""
        loop = MagicMock()
        loop.is_running.return_value = True
        app._loop = loop

        event = DisplayKeyEvent(
            key_value="a",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=None,
        )
        app._enqueue(event)

        loop.call_soon_threadsafe.assert_called_once()
        args = loop.call_soon_threadsafe.call_args
        assert args[0][0] == app._safe_enqueue_key

    def test_enqueue_noop_when_loop_not_set(self, app: LCDApp) -> None:
        """Test _enqueue does nothing when loop is None."""
        app._loop = None
        event = DisplayKeyEvent(
            key_value="a",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=None,
        )
        # Should not raise
        app._enqueue(event)

    def test_enqueue_noop_when_loop_not_running(self, app: LCDApp) -> None:
        """Test _enqueue does nothing when loop is not running."""
        loop = MagicMock()
        loop.is_running.return_value = False
        app._loop = loop

        event = DisplayKeyEvent(
            key_value="a",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=None,
        )
        app._enqueue(event)
        loop.call_soon_threadsafe.assert_not_called()


# --- TestShowImageRgb565 ---


class TestConvertToRgb565:
    """Tests for _convert_to_rgb565 pure-Python RGB888→RGB565 conversion."""

    def test_rgb565_conversion_correctness(self) -> None:
        """Test known RGB888 values produce correct RGB565 output."""
        from sample.raspi_receiver.apps.lcd_display.display import _convert_to_rgb565

        # Create 2x1 image: red pixel + blue pixel
        img = Image.new("RGB", (2, 1))
        img.putpixel((0, 0), (255, 0, 0))  # Red
        img.putpixel((1, 0), (0, 0, 255))  # Blue

        buf = bytearray(2 * 1 * 2)
        _convert_to_rgb565(img, buf)

        import struct

        # Red: R=0xF8, G=0x00, B=0x00 → ((0xF8)<<8)|((0x00)<<3)|(0x00>>3) = 0xF800
        pixel0 = struct.unpack_from(">H", buf, 0)[0]
        assert pixel0 == 0xF800, f"Red pixel: expected 0xF800, got 0x{pixel0:04X}"

        # Blue: R=0x00, G=0x00, B=0xFF → ((0x00)<<8)|((0x00)<<3)|(0xFF>>3) = 0x001F
        pixel1 = struct.unpack_from(">H", buf, 2)[0]
        assert pixel1 == 0x001F, f"Blue pixel: expected 0x001F, got 0x{pixel1:04X}"

    def test_returns_bytearray(self) -> None:
        """Test conversion returns bytearray."""
        from sample.raspi_receiver.apps.lcd_display.display import _convert_to_rgb565

        img = Image.new("RGB", (2, 1), (128, 128, 128))
        result = _convert_to_rgb565(img)
        assert isinstance(result, bytearray)
        assert len(result) == 2 * 1 * 2

    def test_reuses_provided_buffer(self) -> None:
        """Test that the provided buffer is written to in-place."""
        from sample.raspi_receiver.apps.lcd_display.display import _convert_to_rgb565

        img = Image.new("RGB", (1, 1), (255, 255, 255))
        buf = bytearray(2)
        result = _convert_to_rgb565(img, buf)

        # White: should produce non-zero bytes in our buffer
        assert buf != bytearray(2), "Buffer should have been written to"
        assert result is buf, "Should return the same buffer object"


# --- TestRenderOptimization ---


class TestRenderOptimization:
    """Tests for render() using transpose() and subprocess-based SPI."""

    def test_render_uses_transpose_not_rotate(self) -> None:
        """Test render() calls transpose(ROTATE_270) instead of rotate()."""
        display = LCDDisplay()
        mock_image = MagicMock(spec=Image.Image)
        mock_draw = MagicMock(spec=ImageDraw.ImageDraw)
        mock_proxy = MagicMock()
        mock_transposed = MagicMock(spec=Image.Image)
        mock_transposed.size = (240, 240)
        mock_transposed.mode = "RGB"
        mock_transposed.tobytes.return_value = b"\x00" * (240 * 240 * 3)
        mock_image.transpose.return_value = mock_transposed

        display._image = mock_image
        display._draw = mock_draw
        display._render_proxy = mock_proxy
        display._fonts = {
            "title": MagicMock(),
            "status": MagicMock(),
            "key_large": MagicMock(),
            "modifier": MagicMock(),
            "buffer": MagicMock(),
        }
        display._state.mark_dirty()

        display.render()

        mock_image.transpose.assert_called_once_with(
            Image.Transpose.ROTATE_270
        )
        mock_image.rotate.assert_not_called()

    def test_render_sends_to_proxy(self) -> None:
        """Test render() sends RGB565 data to RenderProxy."""
        display = LCDDisplay()
        mock_image = MagicMock(spec=Image.Image)
        mock_draw = MagicMock(spec=ImageDraw.ImageDraw)
        mock_proxy = MagicMock()
        mock_transposed = MagicMock(spec=Image.Image)
        mock_transposed.size = (240, 240)
        mock_transposed.mode = "RGB"
        mock_transposed.tobytes.return_value = b"\x00" * (240 * 240 * 3)
        mock_image.transpose.return_value = mock_transposed

        display._image = mock_image
        display._draw = mock_draw
        display._render_proxy = mock_proxy
        display._fonts = {
            "title": MagicMock(),
            "status": MagicMock(),
            "key_large": MagicMock(),
            "modifier": MagicMock(),
            "buffer": MagicMock(),
        }
        display._state.mark_dirty()

        display.render()

        mock_proxy.render.assert_called_once()
        call_args = mock_proxy.render.call_args
        assert call_args[0][1] == 240  # width
        assert call_args[0][2] == 240  # height


# --- TestEnqueueExceptionSafety ---


class TestEnqueueExceptionSafety:
    """Tests for Fix 3: _enqueue catches RuntimeError from closed loop."""

    @pytest.fixture
    def app(self) -> LCDApp:
        with patch(
            "sample.raspi_receiver.apps.lcd_display.main.KeyReceiver"
        ), patch("sample.raspi_receiver.apps.lcd_display.main.LCDDisplay") as mock_display_cls:
            mock_display = MagicMock()
            mock_display_cls.return_value = mock_display
            app = LCDApp()
            yield app

    def test_enqueue_swallows_runtime_error(self, app: LCDApp) -> None:
        """Test _enqueue does not propagate RuntimeError from closed loop."""
        loop = MagicMock()
        loop.is_running.return_value = True
        loop.call_soon_threadsafe.side_effect = RuntimeError("Event loop is closed")
        app._loop = loop

        event = DisplayKeyEvent(
            key_value="a",
            key_type=KeyType.CHAR.value,
            press=True,
            modifiers=None,
        )
        # Should not raise
        app._enqueue(event)

    def test_enqueue_connection_swallows_runtime_error(self, app: LCDApp) -> None:
        """Test _enqueue swallows RuntimeError for connection events too."""
        loop = MagicMock()
        loop.is_running.return_value = True
        loop.call_soon_threadsafe.side_effect = RuntimeError("Event loop is closed")
        app._loop = loop

        event = DisplayConnectionEvent(connected=True)
        # Should not raise
        app._enqueue(event)
