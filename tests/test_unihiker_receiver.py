"""Unit tests for sample.unihiker_receiver module."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from common.protocol import KeyEvent, KeyType, Modifiers
from ble_receiver.lib.types import ConnectionEvent
from sample.unihiker_receiver.display import (
    UnihikerDisplayAdapter,
    UnihikerScreenState,
)
from sample.unihiker_receiver.main import UnihikerReceiverApp


class _DummyWidget:
    """Simple GUI widget mock that stores latest config values."""

    def __init__(self) -> None:
        self.props: dict[str, object] = {}

    def config(self, **kwargs: object) -> None:
        self.props.update(kwargs)


class _DummyButton:
    """Simple button mock that stores onclick callback."""

    def __init__(self, onclick: object = None) -> None:
        self.onclick = onclick


class _DummyGUI:
    """Simple GUI mock compatible with adapter usage."""

    def __init__(self) -> None:
        self.widgets: list[_DummyWidget] = []
        self.buttons: list[_DummyButton] = []

    def draw_text(self, **_kwargs: object) -> _DummyWidget:
        widget = _DummyWidget()
        self.widgets.append(widget)
        return widget

    def add_button(self, **kwargs: object) -> _DummyButton:
        button = _DummyButton(onclick=kwargs.get("onclick"))
        self.buttons.append(button)
        return button

    def clear(self) -> None:
        self.widgets.clear()
        self.buttons.clear()


class TestUnihikerScreenState:
    """Tests for screen state default values and dirty flags."""

    def test_initial_state(self) -> None:
        state = UnihikerScreenState()
        assert state.connected is False
        assert state.last_key == ""
        assert state.key_type == ""
        assert state.modifier_text == ""
        assert state.input_buffer == ""
        assert state.dirty is True

    def test_mark_clean_and_dirty(self) -> None:
        state = UnihikerScreenState()
        state.mark_clean()
        assert state.dirty is False
        state.mark_dirty()
        assert state.dirty is True


class TestUnihikerDisplayAdapter:
    """Tests for adapter state transitions and render output."""

    @pytest.fixture
    def adapter(self) -> UnihikerDisplayAdapter:
        gui = _DummyGUI()
        adapter = UnihikerDisplayAdapter(gui=gui)
        adapter.init()
        return adapter

    def test_update_connection(self, adapter: UnihikerDisplayAdapter) -> None:
        adapter.state.mark_clean()
        adapter.update_connection(True)
        assert adapter.state.connected is True
        assert adapter.state.dirty is True

    def test_apply_char_key_event_updates_buffer(
        self, adapter: UnihikerDisplayAdapter
    ) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        adapter.apply_key_event(event)
        assert adapter.state.last_key == "a"
        assert adapter.state.input_buffer == "a"

    def test_apply_special_enter_clears_buffer(
        self, adapter: UnihikerDisplayAdapter
    ) -> None:
        adapter.append_buffer("h")
        adapter.append_buffer("i")
        event = KeyEvent(key_type=KeyType.SPECIAL, value="enter", press=True)
        adapter.apply_key_event(event)
        assert adapter.state.input_buffer == ""

    def test_apply_special_backspace(
        self, adapter: UnihikerDisplayAdapter
    ) -> None:
        adapter.append_buffer("a")
        adapter.append_buffer("b")
        event = KeyEvent(
            key_type=KeyType.SPECIAL, value="backspace", press=True
        )
        adapter.apply_key_event(event)
        assert adapter.state.input_buffer == "a"

    def test_format_modifiers(self) -> None:
        text = UnihikerDisplayAdapter.format_modifiers(
            "A", Modifiers(shift=True, ctrl=True)
        )
        assert text == "Ctrl + Shift + A"

    def test_render_updates_widget_text(
        self, adapter: UnihikerDisplayAdapter
    ) -> None:
        adapter.update_connection(True)
        adapter.update_key("A", "c", "Shift + A")
        adapter.append_buffer("A")

        updated = adapter.render()

        assert updated is True
        assert adapter.state.dirty is False

    def test_build_buffer_text_truncates(self) -> None:
        text = UnihikerDisplayAdapter._build_buffer_text("x" * 80)
        assert text.startswith("> ...")
        assert text.endswith("_")

    def test_stop_button_created(self) -> None:
        gui = _DummyGUI()
        adapter = UnihikerDisplayAdapter(gui=gui)
        adapter.init()
        assert len(gui.buttons) == 1

    def test_stop_button_calls_on_stop(self) -> None:
        gui = _DummyGUI()
        adapter = UnihikerDisplayAdapter(gui=gui)
        callback = MagicMock()
        adapter.on_stop = callback
        adapter.init()
        adapter._handle_stop_click()
        callback.assert_called_once()

    def test_stop_button_no_callback(self) -> None:
        gui = _DummyGUI()
        adapter = UnihikerDisplayAdapter(gui=gui)
        adapter.init()
        # Should not raise when on_stop is None
        adapter._handle_stop_click()


class TestUnihikerReceiverApp:
    """Tests for event processing and queue behavior."""

    @pytest.fixture
    def app(self) -> UnihikerReceiverApp:
        app = UnihikerReceiverApp()
        app._display = MagicMock()
        return app

    def test_process_connection_event(self, app: UnihikerReceiverApp) -> None:
        app._process_event(ConnectionEvent(connected=True))
        app._display.update_connection.assert_called_once_with(True)

    def test_process_key_event(self, app: UnihikerReceiverApp) -> None:
        event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
        app._process_event(event)
        app._display.apply_key_event.assert_called_once_with(event)

    def test_safe_enqueue_counts_drop(self, app: UnihikerReceiverApp) -> None:
        app._event_queue = asyncio.Queue(maxsize=1)
        app._safe_enqueue(ConnectionEvent(connected=True))
        app._safe_enqueue(ConnectionEvent(connected=False))
        assert app.stats.dropped_events == 1
