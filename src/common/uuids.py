"""BLE GATT UUID constants shared between Mac and Raspberry Pi.

UUIDs are generated deterministically using UUIDv5, ensuring both
devices produce identical values without configuration sync.
"""

import uuid

# Project namespace for UUIDv5 generation
PROJECT_NAMESPACE: uuid.UUID = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")

# GATT Service UUID for the key transmission service
KEY_SERVICE_UUID: str = str(uuid.uuid5(PROJECT_NAMESPACE, "key-service"))

# GATT Characteristic UUID for key event data
KEY_CHAR_UUID: str = str(uuid.uuid5(PROJECT_NAMESPACE, "key-char"))

# Default BLE device name for the Raspberry Pi peripheral
DEVICE_NAME: str = "RasPi-KeyAgent"


if __name__ == "__main__":
    print(f"KEY_SERVICE_UUID: {KEY_SERVICE_UUID}")
    print(f"KEY_CHAR_UUID:    {KEY_CHAR_UUID}")
    print(f"DEVICE_NAME:      {DEVICE_NAME}")
