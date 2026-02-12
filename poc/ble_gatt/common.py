"""
BLE GATT PoC - 共通定数

Mac (Central) と Raspberry Pi (Peripheral) で共有するUUID定数。
UUIDv5を使用し、プロジェクト固有の一意なUUIDを体系的に生成する。
"""

import uuid

# プロジェクト固有のNamespace（UUIDv5のベース）
PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")

# Service UUID: キー送信サービス
KEY_SERVICE_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-service"))

# Characteristic UUID: キー入力データ
KEY_CHAR_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-char"))

# デバイス名: スキャン時の識別に使用
DEVICE_NAME = "RasPi-KeyAgent"


if __name__ == "__main__":
    print(f"KEY_SERVICE_UUID: {KEY_SERVICE_UUID}")
    print(f"KEY_CHAR_UUID:    {KEY_CHAR_UUID}")
    print(f"DEVICE_NAME:      {DEVICE_NAME}")
