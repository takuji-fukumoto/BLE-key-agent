# BLE GATT通信によるキー送信 詳細リサーチレポート

## 1. BLE GATTの基礎

### 1.1 GATTとは

**GATT（Generic Attribute Profile）** は、BLE（Bluetooth Low Energy）デバイス間でデータをやり取りするための標準プロトコルです。データを**階層構造**で整理し、小さな単位で読み書きする仕組みを提供します。

### 1.2 階層構造

```
┌─────────────────────────────────────────────────────────────┐
│                      Profile                                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Service                               │  │
│  │  UUID: 例 "00001234-0000-1000-8000-00805f9b34fb"      │  │
│  │                                                        │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │           Characteristic                        │  │  │
│  │  │  UUID: 例 "00005678-0000-1000-8000-00805f9b34fb"│  │  │
│  │  │  Properties: Read / Write / Notify              │  │  │
│  │  │  Value: 実際のデータ (バイト列)                   │  │  │
│  │  │                                                  │  │  │
│  │  │  ┌─────────────────────────────────────────┐   │  │  │
│  │  │  │        Descriptor (オプション)           │   │  │  │
│  │  │  │  例: CCCD (Client Characteristic        │   │  │  │
│  │  │  │       Configuration Descriptor)         │   │  │  │
│  │  │  └─────────────────────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

| 階層 | 説明 | 例え |
|---|---|---|
| **Profile** | サービスの集合体。デバイス全体の機能を定義 | 「このデバイスはキーボードです」 |
| **Service** | 関連する機能のグループ。UUIDで識別 | 「キー送信機能」「バッテリー情報」 |
| **Characteristic** | 実際のデータの入れ物。読み書きの対象 | 「キーコード」「バッテリー残量」 |
| **Descriptor** | Characteristicの付加情報 | 「通知の有効/無効設定」 |

### 1.3 UUID体系

#### 標準UUID（Bluetooth SIG定義）

```
0000xxxx-0000-1000-8000-00805f9b34fb
    ^^^^
   16bit 短縮形

例:
0x180F → Battery Service
0x180D → Heart Rate Service
0x1812 → HID Service
```

#### カスタムUUID（独自定義）

```python
# ❌ 避けるべき: 標準UUID範囲
"00001234-0000-1000-8000-00805f9b34fb"  # SIG予約範囲

# ✅ 推奨: ランダム生成したUUIDv4
"f47ac10b-58cc-4372-a567-0e02b2c3d479"

# UUIDv4の生成方法
import uuid
custom_uuid = str(uuid.uuid4())
```

#### UUIDv5による体系的な生成

```python
import uuid

# 会社固有のNamespace（一度だけ生成して共有）
COMPANY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "your-company.co.jp")

def generate_service_uuid(project_name: str) -> str:
    """プロジェクト名からService UUIDを生成"""
    return str(uuid.uuid5(COMPANY_NAMESPACE, f"{project_name}/service"))

def generate_char_uuid(project_name: str, char_name: str) -> str:
    """プロジェクト名とCharacteristic名からUUIDを生成"""
    return str(uuid.uuid5(COMPANY_NAMESPACE, f"{project_name}/{char_name}"))

# 使用例
KEY_SERVICE_UUID = generate_service_uuid("ble-keyboard")
KEY_CHAR_UUID = generate_char_uuid("ble-keyboard", "key-input")
```

### 1.4 Central / Peripheral の役割

```
┌────────────────────┐                      ┌────────────────────┐
│        Mac         │                      │   Raspberry Pi      │
│     (Central)      │                      │   (Peripheral)      │
│                    │         BLE          │                     │
│  ・デバイスをスキャン │ ◀──────────────────▶ │  ・アドバタイズ       │
│  ・接続を開始       │    GATT Protocol     │  ・GATTサーバー      │
│  ・データを読み書き  │                      │  ・データを保持       │
│                    │                      │                     │
│    bleak           │                      │    BlueZ + D-Bus    │
└────────────────────┘                      └────────────────────┘
```

| 役割 | 説明 | 今回の構成 |
|---|---|---|
| **Peripheral** | GATTサーバー。データを保持し、アドバタイズ（自分の存在を通知）する | Raspberry Pi |
| **Central** | GATTクライアント。Peripheralを探し、接続してデータを読み書きする | Mac |

---

## 2. Characteristicの詳細

### 2.1 Properties（操作の種類）

| Property | 方向 | 説明 | 用途例 |
|---|---|---|---|
| **Read** | Central ← Peripheral | Centralがデータを読み取る | バッテリー残量の取得 |
| **Write** | Central → Peripheral | Centralがデータを書き込む（応答あり） | キー情報の送信 |
| **Write Without Response** | Central → Peripheral | 書き込み（応答なし、高速） | 連続キー送信 |
| **Notify** | Central ← Peripheral | 変更時に自動通知（応答なし） | センサー値の定期送信 |
| **Indicate** | Central ← Peripheral | 変更時に自動通知（応答あり） | 確実な通知が必要な場合 |

### 2.2 キー送信での推奨設定

```python
# キー送信用のCharacteristic Properties
["write", "write-without-response"]

# Write Without Response を使う理由:
# - 高速なタイピングに対応可能
# - ACKを待たないため遅延が少ない
# - キー情報は小さいので再送不要
```

### 2.3 Descriptor

| Descriptor | UUID | 説明 |
|---|---|---|
| **CCCD** | 0x2902 | Client Characteristic Configuration Descriptor。Notify/Indicateの有効化に使用 |
| **CUD** | 0x2901 | Characteristic User Description。人間が読める説明文 |

```python
# Notifyを有効化する場合（Central側）
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
await client.write_gatt_char(CCCD_UUID, bytearray([0x01, 0x00]))  # Notify有効
```

---

## 3. Mac側（Central）の実装 - bleak

### 3.1 bleakの概要

**bleak** は、Python用のクロスプラットフォームBLEクライアントライブラリです。

```bash
# インストール
pip install bleak
```

| 特徴 | 詳細 |
|---|---|
| **対応OS** | macOS, Windows, Linux |
| **非同期** | asyncio ベース |
| **macOS対応** | CoreBluetooth をネイティブ使用 |

### 3.2 デバイススキャン

```python
import asyncio
from bleak import BleakScanner

async def scan_devices():
    """周辺のBLEデバイスをスキャン"""
    print("スキャン中...")
    
    # 方法1: 一定時間スキャン
    devices = await BleakScanner.discover(timeout=5.0)
    for device in devices:
        print(f"  {device.name}: {device.address}")
    
    # 方法2: 名前でデバイスを検索
    device = await BleakScanner.find_device_by_name("RasPi-KeyReceiver", timeout=10.0)
    if device:
        print(f"発見: {device.name} ({device.address})")
    else:
        print("デバイスが見つかりません")
    
    return device

asyncio.run(scan_devices())
```

### 3.3 接続と切断

```python
from bleak import BleakClient

async def connect_example():
    # 方法1: コンテキストマネージャー（推奨）
    async with BleakClient(device) as client:
        if client.is_connected:
            print("接続成功")
        # ... 処理 ...
        # ブロックを抜けると自動切断
    
    # 方法2: 明示的な接続/切断
    client = BleakClient(device)
    try:
        await client.connect()
        print("接続成功")
        # ... 処理 ...
    finally:
        await client.disconnect()
```

### 3.4 サービス / Characteristic 探索

```python
async def discover_services(client: BleakClient):
    """サービスとCharacteristicの一覧を取得"""
    for service in client.services:
        print(f"Service: {service.uuid}")
        for char in service.characteristics:
            print(f"  Characteristic: {char.uuid}")
            print(f"    Properties: {char.properties}")
            for descriptor in char.descriptors:
                print(f"      Descriptor: {descriptor.uuid}")
```

### 3.5 データの読み書き

```python
KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"

async def read_write_example(client: BleakClient):
    # 読み取り
    value = await client.read_gatt_char(KEY_CHAR_UUID)
    print(f"読み取り: {value}")
    
    # 書き込み（応答あり）
    data = "key_a".encode("utf-8")
    await client.write_gatt_char(KEY_CHAR_UUID, data, response=True)
    
    # 書き込み（応答なし = 高速）
    await client.write_gatt_char(KEY_CHAR_UUID, data, response=False)
```

### 3.6 Notify の購読

```python
async def subscribe_notifications(client: BleakClient):
    def notification_handler(sender, data):
        """Notifyを受信したときのコールバック"""
        print(f"通知: {sender} -> {data.decode()}")
    
    # Notifyを購読開始
    await client.start_notify(KEY_CHAR_UUID, notification_handler)
    
    # 一定時間待機
    await asyncio.sleep(30)
    
    # 購読停止
    await client.stop_notify(KEY_CHAR_UUID)
```

### 3.7 完全なMac側送信コード

```python
"""
Mac側: pynputでキーを監視し、bleakでBLE送信
"""
import asyncio
from pynput import keyboard
from bleak import BleakClient, BleakScanner

KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"
DEVICE_NAME = "RasPi-KeyReceiver"

loop: asyncio.AbstractEventLoop = None
key_queue: asyncio.Queue = None


def on_press(key):
    try:
        key_str = key.char if hasattr(key, 'char') and key.char else str(key)
    except AttributeError:
        key_str = str(key)
    
    asyncio.run_coroutine_threadsafe(key_queue.put(key_str), loop)


def on_release(key):
    if key == keyboard.Key.esc:
        asyncio.run_coroutine_threadsafe(key_queue.put(None), loop)
        return False


async def main():
    global loop, key_queue
    loop = asyncio.get_event_loop()
    key_queue = asyncio.Queue()
    
    # デバイスをスキャン
    print(f"スキャン中: {DEVICE_NAME}")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    if not device:
        print("デバイスが見つかりません")
        return
    
    print(f"接続中: {device.name}")
    async with BleakClient(device) as client:
        print("接続完了")
        
        # キーリスナーを起動
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        
        print("キー入力を監視中... (Escで終了)")
        
        while True:
            key_str = await key_queue.get()
            if key_str is None:
                break
            
            try:
                await client.write_gatt_char(
                    KEY_CHAR_UUID, 
                    key_str.encode("utf-8"),
                    response=False  # 高速送信
                )
                print(f"送信: {key_str}")
            except Exception as e:
                print(f"送信エラー: {e}")
                break
        
        listener.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 4. Raspberry Pi側（Peripheral）の実装 - BlueZ + D-Bus

### 4.1 BlueZの概要

**BlueZ** は、Linux公式のBluetoothプロトコルスタックです。D-Bus APIを通じてBLE GATTサーバーを構築できます。

```bash
# 必要パッケージのインストール
sudo apt update
sudo apt install -y python3-dbus python3-gi bluez

# Bluetoothサービスの状態確認
sudo systemctl status bluetooth

# Bluetoothアダプタの確認
hciconfig
```

### 4.2 D-Bus API の構造

```
┌──────────────────────────────────────────────────────────────┐
│                          D-Bus                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              org.bluez (BlueZ Service)                  │  │
│  │                                                          │  │
│  │  /org/bluez/hci0 (Adapter)                              │  │
│  │    ├── org.bluez.Adapter1                               │  │
│  │    ├── org.bluez.GattManager1      ← GATTサービス登録   │  │
│  │    └── org.bluez.LEAdvertisingManager1 ← アドバタイズ登録│  │
│  │                                                          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │          Application (自作)                             │  │
│  │  /org/bluez/example/service0                            │  │
│  │    └── org.bluez.GattService1                           │  │
│  │        └── /org/bluez/example/service0/char0            │  │
│  │            └── org.bluez.GattCharacteristic1            │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 完全なRaspberry Pi側受信コード

```python
#!/usr/bin/env python3
"""
Raspberry Pi側: BLE GATTサーバーでキー情報を受信
実行: sudo python3 raspi_key_receiver.py
"""

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

# BlueZ D-Bus定数
BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"

# カスタムUUID（Mac側と一致させる）
KEY_SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"


class Advertisement(dbus.service.Object):
    """BLEアドバタイズメント"""
    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = "peripheral"
        self.service_uuids = [KEY_SERVICE_UUID]
        self.local_name = "RasPi-KeyReceiver"
        self.include_tx_power = True
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            LE_ADVERTISEMENT_IFACE: {
                "Type": self.ad_type,
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "LocalName": dbus.String(self.local_name),
                "IncludeTxPower": dbus.Boolean(self.include_tx_power),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        print(f"[ADV] Released: {self.path}")


class Service(dbus.service.Object):
    """GATTサービス"""
    PATH_BASE = "/org/bluez/example/service"

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.characteristics],
                    signature="o",
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[GATT_SERVICE_IFACE]


class KeyCharacteristic(dbus.service.Object):
    """キー受信用Characteristic"""

    def __init__(self, bus, index, service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = KEY_CHAR_UUID
        self.service = service
        self.flags = ["write", "write-without-response"]
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Value": self.value,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        """Macからキーが書き込まれたときに呼ばれる"""
        key_str = bytes(value).decode("utf-8")
        print(f"[受信] キー: {key_str}")
        self.handle_key(key_str)

    def handle_key(self, key_str):
        """受信したキーに応じた処理"""
        # ここにカスタム処理を追加
        # 例: GPIO制御、コマンド実行など
        pass


class Application(dbus.service.Object):
    """GATTアプリケーション"""

    def __init__(self, bus):
        self.path = "/"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
        return response


def main():
    global mainloop

    # D-Busメインループの初期化
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # BlueZアダプタを取得
    adapter_path = "/org/bluez/hci0"
    adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)

    # アダプタの電源をON
    adapter_props = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))

    # マネージャーを取得
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    # アプリケーションをセットアップ
    app = Application(bus)
    service = Service(bus, 0, KEY_SERVICE_UUID, True)
    key_char = KeyCharacteristic(bus, 0, service)
    service.add_characteristic(key_char)
    app.add_service(service)

    # アドバタイズをセットアップ
    adv = Advertisement(bus, 0)

    mainloop = GLib.MainLoop()

    # 登録コールバック
    def register_app_cb():
        print("[GATT] アプリケーション登録完了")

    def register_app_error_cb(error):
        print(f"[GATT] 登録失敗: {error}")
        mainloop.quit()

    def register_ad_cb():
        print("[ADV] アドバタイズ登録完了")

    def register_ad_error_cb(error):
        print(f"[ADV] 登録失敗: {error}")
        mainloop.quit()

    # GATTアプリケーションを登録
    gatt_manager.RegisterApplication(
        app.get_path(), {},
        reply_handler=register_app_cb,
        error_handler=register_app_error_cb,
    )

    # アドバタイズを登録
    ad_manager.RegisterAdvertisement(
        adv.get_path(), {},
        reply_handler=register_ad_cb,
        error_handler=register_ad_error_cb,
    )

    print("=" * 50)
    print("BLE GATTサーバー起動中...")
    print(f"デバイス名: RasPi-KeyReceiver")
    print(f"サービスUUID: {KEY_SERVICE_UUID}")
    print("Macからの接続を待機しています...")
    print("=" * 50)

    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\n[終了]")
        mainloop.quit()


if __name__ == "__main__":
    main()
```

---

## 5. 通信フロー

### 5.1 接続確立からデータ送信まで

```
Mac (Central)                              Raspberry Pi (Peripheral)
    │                                              │
    │                                   ┌──────────┴──────────┐
    │                                   │ 1. アドバタイズ開始   │
    │                                   │   "RasPi-KeyReceiver"│
    │ ◀───────── アドバタイズパケット ──────│                     │
    │                                   └──────────┬──────────┘
    │                                              │
    │  2. スキャン                                  │
    │ ─────────────────────────────────────────────│
    │                                              │
    │  3. 接続要求                                  │
    │ ─────────────────────────────────────────────▶
    │                                              │
    │                         接続確立 ◀───────────│
    │                                              │
    │  4. サービス探索 (Discover)                   │
    │ ─────────────────────────────────────────────▶
    │                                              │
    │ ◀───────── サービス/Characteristic一覧 ───────│
    │                                              │
    │  5. キー送信 (Write)                          │
    │ ────────── Write("a") ──────────────────────▶ [WriteValue呼び出し]
    │                                              │
    │ ────────── Write("b") ──────────────────────▶ [WriteValue呼び出し]
    │                                              │
    │  6. 切断                                      │
    │ ─────────────────────────────────────────────▶
    │                                              │
```

### 5.2 再接続処理

```python
# Mac側の再接続ロジック
async def connect_with_retry(device_name: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            device = await BleakScanner.find_device_by_name(device_name, timeout=10.0)
            if device:
                client = BleakClient(device)
                await client.connect()
                return client
        except Exception as e:
            print(f"接続失敗 ({attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(2)
    
    raise ConnectionError("接続できませんでした")
```

---

## 6. データ転送の特性

### 6.1 MTU（Maximum Transmission Unit）

| 項目 | 値 |
|---|---|
| デフォルトMTU | 23 bytes |
| 実効ペイロード | 20 bytes (ATT header 3bytes を除く) |
| 最大MTU | 517 bytes (BLE 4.2以降) |

```python
# MTUの確認（bleak）
async with BleakClient(device) as client:
    mtu = client.mtu_size
    print(f"MTU: {mtu} bytes")
```

### 6.2 キー送信に必要なデータサイズ

| キーの種類 | データサイズ | 備考 |
|---|---|---|
| 通常キー (`a`, `1`) | 1 byte | UTF-8 1文字 |
| 特殊キー (`Key.enter`) | 9-15 bytes | 文字列表現 |
| 修飾キー付き (`ctrl+a`) | 10-20 bytes | 組み合わせ表現 |

**結論**: キー送信にはデフォルトMTU（20 bytes）で十分

### 6.3 スループットと遅延

| 項目 | 典型値 | 備考 |
|---|---|---|
| 理論最大スループット | ~1 Mbps | BLE 5.0 |
| 実効スループット | 10-100 kbps | アプリケーションレベル |
| 書き込み遅延 | 10-50 ms | 1回のWrite |
| 接続間隔 | 7.5ms - 4s | 設定可能 |

---

## 7. セキュリティ

### 7.1 ペアリングとボンディング

| 用語 | 説明 |
|---|---|
| **ペアリング** | 暗号化キーの交換プロセス |
| **ボンディング** | ペアリング情報の永続化 |

```python
# bleakでのペアリング（必要な場合）
async with BleakClient(device) as client:
    await client.pair()
```

### 7.2 暗号化レベル

| レベル | 説明 | 推奨用途 |
|---|---|---|
| **なし** | 平文通信 | ローカルテスト |
| **LE Secure Connections** | AES-CCM暗号化 | 本番環境 |

### 7.3 キー送信での考慮事項

```
⚠️ セキュリティ上の注意:
- パスワードなど機密情報はBLE経由で送信しない
- 社内ネットワーク内など信頼できる環境で使用
- 必要に応じてアプリケーションレベルで暗号化
```

---

## 8. トラブルシューティング

### 8.1 よくあるエラーと対処法

| エラー | 原因 | 対処法 |
|---|---|---|
| `NotPermitted` | root権限がない | `sudo`で実行 |
| `AlreadyExists` | 既に登録済み | Bluetoothサービス再起動 |
| `NotReady` | アダプタがOFF | `hciconfig hci0 up` |
| デバイスが見つからない | アドバタイズしていない | ラズパイ側を先に起動 |
| 接続が切れる | タイムアウト | 接続間隔を調整 |

### 8.2 デバッグコマンド

```bash
# Bluetoothアダプタの状態確認
hciconfig

# アダプタを有効化
sudo hciconfig hci0 up

# BLEスキャン
sudo hcitool lescan

# bluetoothctl でインタラクティブ操作
bluetoothctl
> scan on
> devices
> connect XX:XX:XX:XX:XX:XX

# D-Busモニター
dbus-monitor --system "interface='org.bluez.GattCharacteristic1'"

# BlueZログ確認
journalctl -u bluetooth -f
```

### 8.3 Bluetoothサービスの設定

```bash
# /etc/bluetooth/main.conf を編集
sudo nano /etc/bluetooth/main.conf

# 以下を追記
[General]
Name = RasPi-KeyReceiver
DiscoverableTimeout = 0
PairableTimeout = 0
ControllerMode = le

# サービス再起動
sudo systemctl restart bluetooth
```

---

## 9. ベストプラクティス

### 9.1 UUID設計

```python
import uuid

# プロジェクト固有のNamespace
PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")

# サービスUUID
KEY_SERVICE_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-service"))

# Characteristic UUID
KEY_CHAR_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-char"))
```

### 9.2 エラーハンドリング

```python
# Mac側
async def send_key_with_retry(client, key_str, max_retries=3):
    for attempt in range(max_retries):
        try:
            await client.write_gatt_char(KEY_CHAR_UUID, key_str.encode())
            return True
        except Exception as e:
            print(f"送信失敗 ({attempt + 1}): {e}")
            await asyncio.sleep(0.1)
    return False

# ラズパイ側
@dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature="")
def WriteValue(self, value, options):
    try:
        key_str = bytes(value).decode("utf-8")
        self.handle_key(key_str)
    except UnicodeDecodeError:
        print("[エラー] 不正なデータ形式")
    except Exception as e:
        print(f"[エラー] {e}")
```

### 9.3 切断検知

```python
# bleakでの切断検知
def disconnected_callback(client):
    print("接続が切断されました")
    # 再接続処理など

async with BleakClient(device, disconnected_callback=disconnected_callback) as client:
    # ...
```

---

## 10. まとめ

### BLE GATT通信の特徴

| 項目 | 詳細 |
|---|---|
| **通信モデル** | 属性ベース（Read/Write/Notify） |
| **省電力** | Classic Bluetoothより大幅に省電力 |
| **ペアリング** | 不要な場合も多い |
| **データサイズ** | 小さい（20-512 bytes/回） |
| **遅延** | 低い（10-50ms） |

### キー送信に最適な理由

1. **データサイズが小さい** → キー情報は1-20 bytes程度
2. **低遅延** → リアルタイムのキー入力に対応
3. **省電力** → バッテリー駆動のデバイスに最適
4. **macOS対応** → bleakがCoreBluetoothをネイティブ使用

### 構成図

```
┌─────────────────────────────────────────────────────────────┐
│                        Mac (Central)                         │
│  ┌───────────┐      ┌───────────┐      ┌───────────────┐   │
│  │  pynput   │ ──▶  │  asyncio  │ ──▶  │     bleak     │   │
│  │ Listener  │ Queue│   Queue   │      │ BleakClient   │   │
│  └───────────┘      └───────────┘      └───────┬───────┘   │
└─────────────────────────────────────────────────┼───────────┘
                                                  │ BLE
                                                  │ GATT Write
┌─────────────────────────────────────────────────┼───────────┐
│                  Raspberry Pi (Peripheral)       │           │
│  ┌───────────────┐      ┌───────────────────┐  │           │
│  │    BlueZ      │ ◀─── │ KeyCharacteristic │ ◀┘           │
│  │  D-Bus API    │      │   WriteValue()    │              │
│  └───────────────┘      └───────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

---

## 参考リンク

- [bleak 公式ドキュメント](https://bleak.readthedocs.io/)
- [BlueZ D-Bus API ドキュメント](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc)
- [Bluetooth Core Specification](https://www.bluetooth.com/specifications/specs/core-specification/)
- [Bluetooth GATT Services](https://www.bluetooth.com/specifications/gatt/services/)
