"""Unit tests for mac_agent.keyboard_monitor wrapper."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock pynput before importing keyboard-dependent modules.
_pynput_mock = MagicMock()
sys.modules.setdefault("pynput", _pynput_mock)
sys.modules.setdefault("pynput.keyboard", _pynput_mock.keyboard)

from mac_agent.keyboard_monitor import KeyboardMonitor  # noqa: E402


@pytest.mark.asyncio
async def test_wrapper_uses_external_queue() -> None:
    """KeyboardMonitor should use externally provided queue."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=4)

    with patch("mac_agent.keyboard_monitor.KeyMonitor") as key_monitor_cls:
        instance = key_monitor_cls.return_value
        instance.start = AsyncMock()
        instance.stop = AsyncMock()
        instance.is_running = False

        monitor = KeyboardMonitor(queue=queue)

        assert monitor.queue is queue
        await monitor.start()
        await monitor.stop()

        instance.start.assert_called_once()
        instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_next_event_timeout() -> None:
    """next_event should raise TimeoutError when timeout is exceeded."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)

    with patch("mac_agent.keyboard_monitor.KeyMonitor"):
        monitor = KeyboardMonitor(queue=queue)

    with pytest.raises(asyncio.TimeoutError):
        await monitor.next_event(timeout=0.01)
