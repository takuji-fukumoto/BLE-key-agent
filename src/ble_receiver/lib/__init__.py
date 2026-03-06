"""BLE key receiver library.

Provides a callback-based API for receiving key events over BLE GATT.
Applications only need to register callbacks to handle key press/release
and connection events.

Usage:
    from ble_receiver.lib import KeyReceiver, KeyEvent, ConnectionEvent

    receiver = KeyReceiver()
    receiver.on_key_press = lambda event: print(f"Key: {event.value}")
    await receiver.start()
"""

from ble_receiver.lib.gatt_server import WriteCallback
from ble_receiver.lib.key_receiver import KeyReceiver, KeyReceiverConfig, ReceiverStats
from ble_receiver.lib.types import ConnectionEvent, KeyEvent, KeyType, Modifiers

__all__ = [
    "KeyReceiver",
    "KeyReceiverConfig",
    "ReceiverStats",
    "WriteCallback",
    "ConnectionEvent",
    "KeyEvent",
    "KeyType",
    "Modifiers",
]
