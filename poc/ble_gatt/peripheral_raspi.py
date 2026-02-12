#!/usr/bin/env python3
"""
Raspberry Pi側 (Peripheral): BLE GATTサーバー PoC

blessライブラリを使用してGATTサーバーを構築し、
Mac (Central) からのキー入力をBLE経由で受信する。

blessはpipだけでインストール可能（python3-dbus等のシステムパッケージ不要）。

使用方法:
    sudo python3 peripheral_raspi.py

セットアップ:
    pip install bless
    sudo systemctl enable bluetooth
    sudo systemctl start bluetooth
"""

import asyncio
import signal
import sys
import uuid
from typing import Any

from bless import (
    BlessGATTCharacteristic,
    BlessServer,
    GATTAttributePermissions,
    GATTCharacteristicProperties,
)

# --- UUID定数 (common.pyと同じ生成ロジック) ---
_PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")
KEY_SERVICE_UUID = str(uuid.uuid5(_PROJECT_NAMESPACE, "key-service"))
KEY_CHAR_UUID = str(uuid.uuid5(_PROJECT_NAMESPACE, "key-char"))
DEVICE_NAME = "RasPi-KeyAgent"

write_count = 0


def on_write(characteristic: BlessGATTCharacteristic, value: Any, **kwargs) -> None:
    """Centralからキーが書き込まれたときに呼ばれるコールバック。"""
    global write_count
    characteristic.value = value
    write_count += 1

    try:
        key_str = bytes(value).decode("utf-8")
        print(f"  [{write_count:4d}] 受信: {key_str} ({len(value)} bytes)")
        handle_key(key_str)
    except UnicodeDecodeError:
        hex_str = bytes(value).hex()
        print(f"  [{write_count:4d}] 受信 (raw): {hex_str}")


def handle_key(key_str: str) -> None:
    """受信したキーに応じた処理。

    ここをカスタマイズしてGPIO制御やコマンド実行などを追加できる。
    """
    pass


async def run(loop: asyncio.AbstractEventLoop) -> None:
    # GATT定義
    gatt = {
        KEY_SERVICE_UUID: {
            KEY_CHAR_UUID: {
                "Properties": (
                    GATTCharacteristicProperties.write
                    | GATTCharacteristicProperties.write_without_response
                ),
                "Permissions": (
                    GATTAttributePermissions.readable
                    | GATTAttributePermissions.writable
                ),
                "Value": None,
            },
        },
    }

    # サーバー作成・GATT登録
    server = BlessServer(name=DEVICE_NAME, loop=loop, on_write=on_write)
    await server.add_gatt(gatt)

    # サーバー開始（アドバタイズも自動で開始）
    await server.start()

    print("=" * 50)
    print("BLE GATTサーバー起動 (bless)")
    print(f"  デバイス名:     {DEVICE_NAME}")
    print(f"  Service UUID:   {KEY_SERVICE_UUID}")
    print(f"  Char UUID:      {KEY_CHAR_UUID}")
    print("=" * 50)
    print("Macからの接続を待機しています... (Ctrl+Cで終了)")
    print()

    # Ctrl+Cまで待機
    stop_event = asyncio.Event()

    def _signal_handler():
        print("\n終了中...")
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, _signal_handler)
    loop.add_signal_handler(signal.SIGTERM, _signal_handler)

    await stop_event.wait()

    await server.stop()
    print("GATTサーバーを停止しました")


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run(loop))


if __name__ == "__main__":
    main()
