"""Type definitions for the BLE key receiver library.

Re-exports key event types from common.protocol for convenience,
and defines receiver-specific types like ConnectionEvent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from common.protocol import KeyEvent, KeyType, Modifiers

# Re-export common types for library consumers
__all__ = [
    "KeyEvent",
    "KeyType",
    "Modifiers",
    "ConnectionEvent",
]


@dataclass
class ConnectionEvent:
    """BLE connection or disconnection event.

    Attributes:
        connected: True if a client connected, False if disconnected.
        device_address: BLE address of the connected/disconnected device, if available.
    """

    connected: bool
    device_address: Optional[str] = None
