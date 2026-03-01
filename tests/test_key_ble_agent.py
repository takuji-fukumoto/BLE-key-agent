"""Unit tests for mac_agent.agent.KeyBleAgent."""

import asyncio
import sys
from unittest.mock import MagicMock

import pytest

# Mock pynput before importing keyboard-dependent modules.
_pynput_mock = MagicMock()
sys.modules.setdefault("pynput", _pynput_mock)
sys.modules.setdefault("pynput.keyboard", _pynput_mock.keyboard)

from mac_agent.agent import KeyBleAgent  # noqa: E402
from mac_agent.api_types import AgentConfig  # noqa: E402
from mac_agent.ble_client import BleStatus  # noqa: E402
from common.protocol import KeyEvent, KeyType  # noqa: E402


class FakeKeyboardMonitor:
    """Test double for KeyboardMonitor."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[KeyEvent | None] = asyncio.Queue(maxsize=8)
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def next_event(self, timeout: float | None = None) -> KeyEvent | None:
        if timeout is None:
            return await self.queue.get()
        return await asyncio.wait_for(self.queue.get(), timeout=timeout)


class FakeBleSender:
    """Test double for BleSender."""

    def __init__(self) -> None:
        self.status = BleStatus.CONNECTED
        self.sent: list[KeyEvent] = []
        self.disconnected = False

    async def scan(self, timeout: float = 5.0):
        return []

    async def connect(self, address: str) -> bool:
        return True

    async def send_key(self, event: KeyEvent) -> bool:
        self.sent.append(event)
        return True

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.asyncio
async def test_start_stop_and_forwarding() -> None:
    """KeyBleAgent should forward key events and stop cleanly."""
    monitor = FakeKeyboardMonitor()
    sender = FakeBleSender()

    forwarded: list[KeyEvent] = []

    agent = KeyBleAgent(
        config=AgentConfig(heartbeat_interval_sec=0.05, min_send_interval_sec=0.0),
        on_key_event=forwarded.append,
        ble_sender=sender,
        keyboard_monitor=monitor,
    )

    await agent.start()

    event = KeyEvent(key_type=KeyType.CHAR, value="a", press=True)
    await monitor.queue.put(event)
    await asyncio.sleep(0.05)

    assert forwarded
    assert sender.sent
    assert sender.sent[0].value == "a"

    await agent.stop()
    assert sender.disconnected is True


@pytest.mark.asyncio
async def test_double_start_raises() -> None:
    """Calling start twice should raise RuntimeError."""
    monitor = FakeKeyboardMonitor()
    sender = FakeBleSender()
    agent = KeyBleAgent(ble_sender=sender, keyboard_monitor=monitor)

    await agent.start()
    with pytest.raises(RuntimeError, match="already running"):
        await agent.start()
    await agent.stop()
