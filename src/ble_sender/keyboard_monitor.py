"""Library-friendly keyboard monitor wrapper for ble_sender."""

from __future__ import annotations

import asyncio
from typing import Optional

from common.protocol import KeyEvent
from ble_sender.key_monitor import KeyMonitor


class KeyboardMonitor:
    """Reusable keyboard monitor facade.

    Wraps `KeyMonitor` and exposes a queue-centric API that is convenient
    for other repositories and higher-level orchestration code.

    Args:
        queue: Optional externally managed queue. If omitted, an internal
            queue is created.
        queue_max_size: Queue max size when creating an internal queue.
    """

    def __init__(
        self,
        queue: Optional[asyncio.Queue[KeyEvent | None]] = None,
        queue_max_size: int = 256,
    ) -> None:
        if queue is None:
            queue = asyncio.Queue(maxsize=queue_max_size)
        self._queue = queue
        self._monitor = KeyMonitor(self._queue)

    @property
    def queue(self) -> asyncio.Queue[KeyEvent | None]:
        """Return the event queue that receives key events."""
        return self._queue

    @property
    def is_running(self) -> bool:
        """Whether monitoring is currently active."""
        return self._monitor.is_running

    async def start(self) -> None:
        """Start keyboard monitoring."""
        await self._monitor.start()

    async def stop(self) -> None:
        """Stop keyboard monitoring."""
        await self._monitor.stop()

    async def next_event(self, timeout: float | None = None) -> KeyEvent | None:
        """Get the next key event from the queue.

        Args:
            timeout: Optional timeout in seconds.

        Returns:
            KeyEvent or sentinel None.

        Raises:
            asyncio.TimeoutError: If timeout is provided and exceeded.
        """
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    @staticmethod
    def check_accessibility() -> bool:
        """Check macOS accessibility permissions."""
        return KeyMonitor.check_accessibility()
