"""Keyboard monitoring with pynput and asyncio integration.

Monitors global keyboard input using pynput and bridges events to an
asyncio event loop via queue for thread-safe communication.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from pynput import keyboard

from common.protocol import KeyEvent, KeyType, Modifiers

logger = logging.getLogger(__name__)


class KeyMonitor:
    """Monitors keyboard input and publishes events to asyncio queue.

    Uses pynput for global keyboard monitoring. Events are pushed to an
    asyncio.Queue via run_coroutine_threadsafe() since pynput runs in a
    separate thread.

    Based on poc/pynput/pynput_key_monitor.py with API adjustments per
    docs/spec-mac-agent.md section 4.1.

    Args:
        queue: asyncio.Queue to receive KeyEvent objects.

    Example:
        >>> queue = asyncio.Queue()
        >>> monitor = KeyMonitor(queue)
        >>> await monitor.start()
        >>> # Process events from queue
        >>> event = await queue.get()
        >>> await monitor.stop()
    """

    # Modifier key mapping (from pynput to protocol names)
    MODIFIER_KEYS = {
        keyboard.Key.shift: 'shift',
        keyboard.Key.shift_l: 'shift',
        keyboard.Key.shift_r: 'shift',
        keyboard.Key.ctrl: 'ctrl',
        keyboard.Key.ctrl_l: 'ctrl',
        keyboard.Key.ctrl_r: 'ctrl',
        keyboard.Key.alt: 'alt',
        keyboard.Key.alt_l: 'alt',
        keyboard.Key.alt_r: 'alt',
        keyboard.Key.cmd: 'cmd',
        keyboard.Key.cmd_l: 'cmd',
        keyboard.Key.cmd_r: 'cmd',
    }

    def __init__(self, queue: asyncio.Queue) -> None:
        """Initialize KeyMonitor.

        Args:
            queue: asyncio.Queue to receive KeyEvent objects.
        """
        self._queue = queue
        self._listener: Optional[keyboard.Listener] = None
        self._running = False

        # Event loop reference (set on start)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Modifier key states
        self._modifiers = {
            'shift': False,
            'ctrl': False,
            'alt': False,
            'cmd': False,
        }

    @property
    def is_running(self) -> bool:
        """Return True if keyboard monitoring is active."""
        return self._running

    async def start(self) -> None:
        """Start keyboard monitoring.

        Starts the pynput listener in a separate thread and begins
        queuing key events to the asyncio event loop.

        Raises:
            RuntimeError: If already running.
        """
        if self._running:
            raise RuntimeError("KeyMonitor is already running")

        self._loop = asyncio.get_running_loop()
        self._running = True

        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self._listener.start()

        logger.info("KeyMonitor started")

    async def stop(self) -> None:
        """Stop keyboard monitoring.

        Stops the pynput listener and cleans up resources.
        """
        if not self._running:
            return

        if self._listener is not None:
            self._listener.stop()
            self._listener = None

        self._running = False
        self._loop = None

        logger.info("KeyMonitor stopped")

    @staticmethod
    def check_accessibility() -> bool:
        """Check if macOS accessibility permissions are granted.

        Returns:
            True if permissions are granted or platform is not macOS.
            False if permissions are definitely missing.

        Note:
            This check may not be 100% reliable. If False is returned,
            the user should check System Settings → Privacy & Security
            → Accessibility.
        """
        if sys.platform != 'darwin':
            return True

        # pynput's IS_TRUSTED attribute (may not always be accurate)
        if hasattr(keyboard.Listener, 'IS_TRUSTED'):
            return bool(keyboard.Listener.IS_TRUSTED)

        # Cannot determine, assume granted
        return True

    def _classify_key(self, key) -> tuple[KeyType, str]:
        """Classify a pynput key and return (KeyType, value string).

        Args:
            key: pynput key object (keyboard.Key or keyboard.KeyCode).

        Returns:
            Tuple of (KeyType, value string) for protocol encoding.
        """
        # Modifier keys
        if key in self.MODIFIER_KEYS:
            return KeyType.MODIFIER, self.MODIFIER_KEYS[key]

        # Character keys (has .char attribute)
        if isinstance(key, keyboard.KeyCode):
            if key.char is not None:
                return KeyType.CHAR, key.char
            # Virtual key code only
            return KeyType.SPECIAL, f"vk:{key.vk}"

        # Special keys (Key enum: enter, tab, etc.)
        if isinstance(key, keyboard.Key):
            return KeyType.SPECIAL, key.name

        # Fallback
        return KeyType.SPECIAL, str(key)

    def _update_modifier(self, key, is_press: bool) -> None:
        """Update modifier key state.

        Args:
            key: pynput key object.
            is_press: True if key was pressed, False if released.
        """
        if key in self.MODIFIER_KEYS:
            mod_name = self.MODIFIER_KEYS[key]
            self._modifiers[mod_name] = is_press

    def _create_event(self, key, is_press: bool) -> KeyEvent:
        """Create a KeyEvent from a pynput key.

        Args:
            key: pynput key object.
            is_press: True for press, False for release.

        Returns:
            KeyEvent instance with current modifier states.
        """
        key_type, key_value = self._classify_key(key)

        # Create Modifiers object if any modifier is active
        modifiers = None
        if any(self._modifiers.values()):
            modifiers = Modifiers(
                cmd=self._modifiers['cmd'],
                ctrl=self._modifiers['ctrl'],
                alt=self._modifiers['alt'],
                shift=self._modifiers['shift'],
            )

        return KeyEvent(
            key_type=key_type,
            value=key_value,
            press=is_press,
            modifiers=modifiers,
            timestamp=None,  # Timestamp omitted per spec (optional)
        )

    def _on_press(self, key) -> Optional[bool]:
        """Callback for pynput key press events (runs in pynput thread).

        Args:
            key: pynput key object.

        Returns:
            None to continue listening.
        """
        # Update modifier state first
        self._update_modifier(key, True)

        # Create event
        event = self._create_event(key, is_press=True)

        # Bridge to asyncio event loop
        if self._loop and self._queue:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(event),
                    self._loop
                )
            except Exception:
                logger.exception("Failed to queue key press event")

        return None  # Continue listening

    def _on_release(self, key) -> Optional[bool]:
        """Callback for pynput key release events (runs in pynput thread).

        Args:
            key: pynput key object.

        Returns:
            None to continue listening.
        """
        # Update modifier state first
        self._update_modifier(key, False)

        # Create event
        event = self._create_event(key, is_press=False)

        # Bridge to asyncio event loop
        if self._loop and self._queue:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._queue.put(event),
                    self._loop
                )
            except Exception:
                logger.exception("Failed to queue key release event")

        return None  # Continue listening
