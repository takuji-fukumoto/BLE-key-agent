"""BLE key receiver library for Raspberry Pi.

Provides a callback-based API for receiving key events from Mac agent
over BLE GATT. Applications only need to register callbacks to handle
key press/release and connection events.

Usage:
    from raspi_receiver.lib import KeyReceiver, KeyEvent, ConnectionEvent

    receiver = KeyReceiver()
    receiver.on_key_press = lambda event: print(f"Key: {event.value}")
    await receiver.start()
"""

from raspi_receiver.lib.gatt_server import WriteCallback
from raspi_receiver.lib.key_receiver import KeyReceiver, KeyReceiverConfig, ReceiverStats
from raspi_receiver.lib.types import ConnectionEvent, KeyEvent, KeyType, Modifiers

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
