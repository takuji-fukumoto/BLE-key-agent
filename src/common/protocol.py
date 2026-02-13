"""Key event serialization protocol for BLE GATT communication.

Defines the data structures and serialization logic for key events
transmitted between Mac (Central) and Raspberry Pi (Peripheral).
Wire format is compact JSON encoded as UTF-8 bytes.

See docs/spec-ble-protocol.md section 3 for the full specification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class KeyType(str, Enum):
    """Key event type classification.

    Values correspond to the short codes used in the BLE wire format:
    - "c": Regular character key (e.g., 'a', '1', '@')
    - "s": Special key (e.g., 'enter', 'tab', 'backspace')
    - "m": Modifier key (e.g., 'shift', 'ctrl', 'alt', 'cmd')
    """

    CHAR = "c"
    SPECIAL = "s"
    MODIFIER = "m"


@dataclass(frozen=True)
class Modifiers:
    """Modifier key states transmitted with key events.

    All fields default to False. When all are False, the modifiers
    object is considered "default" and may be omitted in short format.
    """

    cmd: bool = False
    ctrl: bool = False
    alt: bool = False
    shift: bool = False

    def to_dict(self) -> dict[str, bool]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cmd": self.cmd,
            "ctrl": self.ctrl,
            "alt": self.alt,
            "shift": self.shift,
        }

    @classmethod
    def from_dict(cls, data: dict[str, bool]) -> Modifiers:
        """Create from dictionary (JSON deserialization).

        Args:
            data: Dictionary with modifier key names as keys and boolean values.
                  Missing keys default to False.
        """
        return cls(
            cmd=data.get("cmd", False),
            ctrl=data.get("ctrl", False),
            alt=data.get("alt", False),
            shift=data.get("shift", False),
        )

    def is_default(self) -> bool:
        """Return True if all modifiers are False."""
        return not (self.cmd or self.ctrl or self.alt or self.shift)


@dataclass
class KeyEvent:
    """A key event for BLE transmission.

    Represents a single key press or release event with optional
    modifier state and timestamp. Supports bidirectional JSON
    serialization for BLE GATT communication.

    Attributes:
        key_type: Classification of the key (char, special, or modifier).
        value: The key value string (e.g., "a", "enter", "shift").
        press: True for key press, False for key release.
        modifiers: Optional modifier key states. Omitted in short format.
        timestamp: Optional event timestamp (time.time()). Omitted in short format.
    """

    key_type: KeyType
    value: str
    press: bool
    modifiers: Optional[Modifiers] = None
    timestamp: Optional[float] = None

    def serialize(self) -> bytes:
        """Serialize to JSON UTF-8 bytes for BLE transmission.

        Returns compact JSON. Omits 'mod' and 'ts' fields when they
        are None or default (short format for MTU optimization).

        Returns:
            UTF-8 encoded JSON bytes.
        """
        data: dict[str, Any] = {
            "t": self.key_type.value,
            "v": self.value,
            "p": self.press,
        }
        if self.modifiers is not None and not self.modifiers.is_default():
            data["mod"] = self.modifiers.to_dict()
        if self.timestamp is not None:
            data["ts"] = self.timestamp
        return json.dumps(
            data, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> KeyEvent:
        """Deserialize from JSON UTF-8 bytes.

        Args:
            data: UTF-8 encoded JSON bytes from BLE.

        Returns:
            Parsed KeyEvent instance.

        Raises:
            ValueError: If data is not valid JSON or missing required fields.
        """
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid key event data: {e}") from e

        for field in ("t", "v", "p"):
            if field not in obj:
                raise ValueError(f"Missing required field: '{field}'")

        try:
            key_type = KeyType(obj["t"])
        except ValueError:
            raise ValueError(f"Invalid key type: '{obj['t']}'")

        modifiers = None
        if "mod" in obj:
            modifiers = Modifiers.from_dict(obj["mod"])

        timestamp: Optional[float] = obj.get("ts")

        return cls(
            key_type=key_type,
            value=obj["v"],
            press=obj["p"],
            modifiers=modifiers,
            timestamp=timestamp,
        )
