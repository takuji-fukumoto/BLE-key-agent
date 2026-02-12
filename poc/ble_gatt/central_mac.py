#!/usr/bin/env python3
"""
Mac側 (Central): BLE GATTクライアント PoC

Raspberry Piで動作するGATTサーバーに接続し、キー入力をBLE経由で送信する。
bleakライブラリを使用し、asyncioベースで非同期通信を行う。

使用方法:
    # デフォルト: スキャン → デバイス選択 → 接続 → 送信
    python central_mac.py

    # スキャンのみ（周辺デバイスの一覧表示）
    python central_mac.py --scan

    # デバイス名を指定して直接接続（選択をスキップ）
    python central_mac.py --device "RasPi-KeyAgent"

必要パッケージ:
    pip install bleak
"""

import argparse
import asyncio
import signal
import sys

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

from common import DEVICE_NAME, KEY_CHAR_UUID, KEY_SERVICE_UUID


async def scan_devices(timeout: float = 5.0, show_only: bool = False):
    """周辺のBLEデバイスをスキャンして一覧表示する。

    Args:
        timeout: スキャン秒数
        show_only: Trueなら一覧表示のみ。Falseならデバイスリストを返す。

    Returns:
        show_only=False の場合、RSSI降順にソートされたデバイスリスト。
    """
    print(f"BLEデバイスをスキャン中... ({timeout}秒)")
    print("-" * 60)

    devices = await BleakScanner.discover(timeout=timeout)
    if not devices:
        print("デバイスが見つかりませんでした")
        return []

    sorted_devices = sorted(devices, key=lambda d: d.rssi or -100, reverse=True)

    for i, device in enumerate(sorted_devices, 1):
        rssi = device.rssi or "N/A"
        name = device.name or "(名前なし)"
        print(f"  [{i:2d}] {name:30s}  {device.address}  RSSI: {rssi}")

    print("-" * 60)
    print(f"合計 {len(sorted_devices)} デバイス")

    if show_only:
        return []

    return sorted_devices


async def select_device(timeout: float = 10.0):
    """スキャン → ユーザーが番号で選択 → 選択デバイスを返す。"""
    loop = asyncio.get_event_loop()

    devices = await scan_devices(timeout=timeout)
    if not devices:
        return None

    print("\n接続先を選択してください (番号 / 'r'で再スキャン / 'q'で終了): ", end="", flush=True)

    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        choice = line.strip().lower()

        if choice == "q":
            return None

        if choice == "r":
            print()
            devices = await scan_devices(timeout=timeout)
            if not devices:
                return None
            print("\n接続先を選択してください (番号 / 'r'で再スキャン / 'q'で終了): ", end="", flush=True)
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(devices):
                return devices[idx]
            print(f"  1〜{len(devices)} の番号を入力してください: ", end="", flush=True)
        except ValueError:
            print("  番号を入力してください: ", end="", flush=True)


async def discover_services(client: BleakClient) -> None:
    """接続先デバイスのサービスとCharacteristicを一覧表示する。"""
    print("\nサービス一覧:")
    print("-" * 60)
    for service in client.services:
        print(f"  Service: {service.uuid}")
        for char in service.characteristics:
            props = ", ".join(char.properties)
            print(f"    Char: {char.uuid} [{props}]")
            for desc in char.descriptors:
                print(f"      Desc: {desc.uuid}")
    print("-" * 60)


async def send_interactive(client: BleakClient) -> None:
    """インタラクティブモードでキー入力をBLE送信する。"""
    print("\nインタラクティブモード")
    print("テキストを入力してEnterで送信します。'quit'で終了。")
    print("-" * 60)

    loop = asyncio.get_event_loop()

    while True:
        try:
            # stdinからの非同期読み取り
            line = await loop.run_in_executor(None, sys.stdin.readline)
            line = line.strip()

            if not line:
                continue
            if line.lower() == "quit":
                print("終了します")
                break

            data = line.encode("utf-8")

            # MTU内に収まるかチェック（デフォルト20bytes）
            if len(data) > 512:
                print(f"  データが大きすぎます ({len(data)} bytes)")
                continue

            await client.write_gatt_char(
                KEY_CHAR_UUID,
                data,
                response=False,  # Write Without Response（高速）
            )
            print(f"  送信: {line} ({len(data)} bytes)")

        except BleakError as e:
            print(f"  BLEエラー: {e}")
            break
        except EOFError:
            break


def on_disconnect(client: BleakClient) -> None:
    """接続切断時のコールバック。"""
    print("\n接続が切断されました")


async def connect_and_send_to(device) -> None:
    """指定デバイスに接続してインタラクティブ送信を行う。"""
    name = device.name or device.address
    print(f"\n'{name}' に接続中...")

    async with BleakClient(
        device, disconnected_callback=on_disconnect
    ) as client:
        print(f"接続成功 (MTU: {client.mtu_size} bytes)")

        # サービス一覧を表示
        await discover_services(client)

        # キーサービスのCharacteristicが存在するか確認
        target_char = None
        for service in client.services:
            if service.uuid == KEY_SERVICE_UUID:
                for char in service.characteristics:
                    if char.uuid == KEY_CHAR_UUID:
                        target_char = char
                        break

        if not target_char:
            print(f"キーサービス ({KEY_SERVICE_UUID}) が見つかりません")
            return

        print(f"\nキーCharacteristic発見: {target_char.uuid}")
        print(f"  Properties: {', '.join(target_char.properties)}")

        # インタラクティブ送信
        await send_interactive(client)


async def connect_by_name(device_name: str, timeout: float = 10.0) -> None:
    """デバイス名を指定して直接接続する（--device オプション用）。"""
    print(f"デバイス '{device_name}' をスキャン中...")
    device = await BleakScanner.find_device_by_name(device_name, timeout=timeout)

    if not device:
        print(f"デバイス '{device_name}' が見つかりませんでした")
        print("ヒント:")
        print("  - Raspberry Pi側のperipheral_raspi.pyが起動しているか確認")
        print("  - --scan オプションで周辺デバイスを確認")
        return

    print(f"デバイスを発見: {device.name} ({device.address})")
    await connect_and_send_to(device)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mac側 BLE GATT Central - キー送信 PoC"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="周辺BLEデバイスをスキャンして終了",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="接続先デバイス名を指定して直接接続（選択をスキップ）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="スキャンタイムアウト秒数 (デフォルト: 10.0)",
    )
    args = parser.parse_args()

    if args.scan:
        # スキャンのみ
        await scan_devices(timeout=args.timeout, show_only=True)
    elif args.device:
        # デバイス名を指定して直接接続
        await connect_by_name(device_name=args.device, timeout=args.timeout)
    else:
        # デフォルト: スキャン → 選択 → 接続
        device = await select_device(timeout=args.timeout)
        if device:
            await connect_and_send_to(device)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n中断されました")
