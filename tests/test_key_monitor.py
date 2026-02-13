"""Unit tests for mac_agent.key_monitor module.

Uses mocks for the pynput library since keyboard monitoring requires
platform-specific permissions. The pynput module is mocked to avoid
dependency on actual keyboard hardware.
"""

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock the pynput module before importing key_monitor
_pynput_mock = MagicMock()
sys.modules.setdefault("pynput", _pynput_mock)
sys.modules.setdefault("pynput.keyboard", _pynput_mock.keyboard)

from mac_agent.key_monitor import KeyMonitor  # noqa: E402
from common.protocol import KeyEvent, KeyType  # noqa: E402


class TestKeyMonitorInit:
    """Tests for KeyMonitor initialization."""

    @pytest.mark.asyncio
    async def test_initialization(self) -> None:
        """Test KeyMonitor initializes with correct defaults."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        assert monitor._queue is queue
        assert monitor._running is False
        assert monitor._listener is None
        assert monitor._loop is None
        assert monitor._modifiers == {
            'shift': False,
            'ctrl': False,
            'alt': False,
            'cmd': False,
        }

    @pytest.mark.asyncio
    async def test_is_running_initially_false(self) -> None:
        """Test is_running property is False initially."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        assert monitor.is_running is False


class TestKeyClassification:
    """Tests for _classify_key() method."""

    @pytest.mark.asyncio
    async def test_classify_char_key(self) -> None:
        """Test classification of character keys."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Mock character key
        mock_key = MagicMock()
        mock_key.char = 'a'
        type(mock_key).__name__ = 'KeyCode'

        # Use isinstance check workaround
        with patch('mac_agent.key_monitor.keyboard.KeyCode', type(mock_key)):
            key_type, value = monitor._classify_key(mock_key)

        assert key_type == KeyType.CHAR
        assert value == 'a'

    @pytest.mark.asyncio
    async def test_classify_special_key(self) -> None:
        """Test classification of special keys."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Mock special key (Key enum)
        mock_key = MagicMock()
        mock_key.name = 'enter'
        type(mock_key).__name__ = 'Key'

        with patch('mac_agent.key_monitor.keyboard.Key', type(mock_key)):
            key_type, value = monitor._classify_key(mock_key)

        assert key_type == KeyType.SPECIAL
        assert value == 'enter'

    @pytest.mark.asyncio
    async def test_classify_modifier_key(self) -> None:
        """Test classification of modifier keys."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Mock shift key (in MODIFIER_KEYS)
        mock_shift = MagicMock()
        with patch.dict(monitor.MODIFIER_KEYS, {mock_shift: 'shift'}):
            key_type, value = monitor._classify_key(mock_shift)

        assert key_type == KeyType.MODIFIER
        assert value == 'shift'


class TestModifierTracking:
    """Tests for _update_modifier() method."""

    @pytest.mark.asyncio
    async def test_update_modifier_press(self) -> None:
        """Test modifier state updates on press."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        mock_shift = MagicMock()
        with patch.dict(monitor.MODIFIER_KEYS, {mock_shift: 'shift'}):
            monitor._update_modifier(mock_shift, True)

        assert monitor._modifiers['shift'] is True

    @pytest.mark.asyncio
    async def test_update_modifier_release(self) -> None:
        """Test modifier state updates on release."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Set shift to True first
        monitor._modifiers['shift'] = True

        mock_shift = MagicMock()
        with patch.dict(monitor.MODIFIER_KEYS, {mock_shift: 'shift'}):
            monitor._update_modifier(mock_shift, False)

        assert monitor._modifiers['shift'] is False

    @pytest.mark.asyncio
    async def test_multiple_modifiers(self) -> None:
        """Test multiple modifiers can be active simultaneously."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        mock_shift = MagicMock()
        mock_ctrl = MagicMock()

        with patch.dict(monitor.MODIFIER_KEYS, {
            mock_shift: 'shift',
            mock_ctrl: 'ctrl'
        }):
            monitor._update_modifier(mock_shift, True)
            monitor._update_modifier(mock_ctrl, True)

        assert monitor._modifiers['shift'] is True
        assert monitor._modifiers['ctrl'] is True
        assert monitor._modifiers['alt'] is False
        assert monitor._modifiers['cmd'] is False


class TestEventCreation:
    """Tests for _create_event() method."""

    @pytest.mark.asyncio
    async def test_create_event_no_modifiers(self) -> None:
        """Test event creation without active modifiers."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        mock_key = MagicMock()
        mock_key.char = 'a'
        type(mock_key).__name__ = 'KeyCode'

        with patch('mac_agent.key_monitor.keyboard.KeyCode', type(mock_key)):
            event = monitor._create_event(mock_key, is_press=True)

        assert isinstance(event, KeyEvent)
        assert event.key_type == KeyType.CHAR
        assert event.value == 'a'
        assert event.press is True
        assert event.modifiers is None  # No modifiers active

    @pytest.mark.asyncio
    async def test_create_event_with_modifiers(self) -> None:
        """Test event creation with active modifiers."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Set shift active
        monitor._modifiers['shift'] = True

        mock_key = MagicMock()
        mock_key.char = 'A'
        type(mock_key).__name__ = 'KeyCode'

        with patch('mac_agent.key_monitor.keyboard.KeyCode', type(mock_key)):
            event = monitor._create_event(mock_key, is_press=True)

        assert event.modifiers is not None
        assert event.modifiers.shift is True
        assert event.modifiers.ctrl is False


class TestAsyncioIntegration:
    """Tests for asyncio Queue integration."""

    @pytest.mark.asyncio
    async def test_start_creates_listener(self) -> None:
        """Test start() creates pynput listener."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        mock_listener = MagicMock()
        mock_listener.start = MagicMock()

        with patch('mac_agent.key_monitor.keyboard.Listener', return_value=mock_listener):
            await monitor.start()

        assert monitor._listener is mock_listener
        assert monitor._running is True
        mock_listener.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(self) -> None:
        """Test start() raises RuntimeError if already running."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)
        monitor._running = True

        with pytest.raises(RuntimeError, match="already running"):
            await monitor.start()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self) -> None:
        """Test stop() cleans up listener."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        mock_listener = MagicMock()
        mock_listener.stop = MagicMock()
        monitor._listener = mock_listener
        monitor._running = True

        await monitor.stop()

        assert monitor._listener is None
        assert monitor._running is False
        mock_listener.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """Test stop() is safe when not running."""
        queue = asyncio.Queue()
        monitor = KeyMonitor(queue)

        # Should not raise
        await monitor.stop()

        assert monitor._running is False


class TestAccessibilityCheck:
    """Tests for check_accessibility() static method."""

    @pytest.mark.asyncio
    async def test_check_accessibility_non_darwin(self) -> None:
        """Test check_accessibility() returns True on non-macOS."""
        with patch('mac_agent.key_monitor.sys.platform', 'linux'):
            result = KeyMonitor.check_accessibility()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_accessibility_darwin_trusted(self) -> None:
        """Test check_accessibility() returns True if IS_TRUSTED is True."""
        with patch('mac_agent.key_monitor.sys.platform', 'darwin'):
            mock_listener = MagicMock()
            mock_listener.IS_TRUSTED = True

            with patch('mac_agent.key_monitor.keyboard.Listener', mock_listener):
                result = KeyMonitor.check_accessibility()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_accessibility_darwin_not_trusted(self) -> None:
        """Test check_accessibility() returns False if IS_TRUSTED is False."""
        with patch('mac_agent.key_monitor.sys.platform', 'darwin'):
            mock_listener = MagicMock()
            mock_listener.IS_TRUSTED = False

            with patch('mac_agent.key_monitor.keyboard.Listener', mock_listener):
                result = KeyMonitor.check_accessibility()

        assert result is False

    @pytest.mark.asyncio
    async def test_check_accessibility_darwin_no_is_trusted(self) -> None:
        """Test check_accessibility() returns True if IS_TRUSTED not available."""
        with patch('mac_agent.key_monitor.sys.platform', 'darwin'):
            mock_listener = MagicMock()
            # Simulate IS_TRUSTED attribute not existing
            if hasattr(mock_listener, 'IS_TRUSTED'):
                delattr(mock_listener, 'IS_TRUSTED')

            with patch('mac_agent.key_monitor.keyboard.Listener', mock_listener):
                result = KeyMonitor.check_accessibility()

        assert result is True
