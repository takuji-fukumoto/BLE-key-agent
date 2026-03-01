# BLE GATT通信の基礎とbleakライブラリ調査

## 1. GATTの基礎概念

### Profile/Service/Characteristicの階層構造

```
┌─────────────────────────────────────────────────┐
│                    Profile                       │
│  (複数のServiceをまとめた上位概念)                │
│  例: Heart Rate Profile, HID Profile            │
│                                                  │
│  ┌─────────────────────────────────────────┐    │
│  │              Service                     │    │
│  │  (機能の単位、UUID で識別)               │    │
│  │  例: Battery Service (0x180F)           │    │
│  │                                          │    │
│  │  ┌─────────────────────────────────┐    │    │
│  │  │       Characteristic            │    │    │
│  │  │  (実際のデータを保持)            │    │    │
│  │  │  例: Battery Level (0x2A19)     │    │    │
│  │  │                                  │    │    │
│  │  │  ┌───────────────────────┐      │    │    │
│  │  │  │     Descriptor        │      │    │    │
│  │  │  │  (補足情報)           │      │    │    │
│  │  │  └───────────────────────┘      │    │    │
│  │  └─────────────────────────────────┘    │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

| 階層 | 説明 | 例 |
|------|------|-----|
| **Profile** | 特定の用途向けServiceの集合 | Heart Rate Profile |
| **Service** | 関連するCharacteristicのグループ | Heart Rate Service (0x180D) |
| **Characteristic** | 実際のデータ値を保持 | Heart Rate Measurement (0x2A37) |
| **Descriptor** | Characteristicの補足情報 | CCCD (0x2902) |

### UUID体系（標準 vs カスタム）

**標準UUID（Bluetooth SIG定義）:**
```
0000XXXX-0000-1000-8000-00805f9b34fb
     ↑
   16bit UUID（短縮形）
```

| 種類 | 形式 | 例 |
|------|------|-----|
| 標準16bit | `0x180F` | Battery Service |
| 標準128bit | `0000180F-0000-1000-8000-00805f9b34fb` | 同上（完全形） |
| カスタム | 任意の128bit | `12345678-1234-5678-1234-56789abcdef0` |

**よく使う標準UUID:**
| UUID | 名称 |
|------|------|
| `0x1800` | Generic Access |
| `0x1801` | Generic Attribute |
| `0x180F` | Battery Service |
| `0x180A` | Device Information |
| `0x2A00` | Device Name (Characteristic) |
| `0x2A19` | Battery Level (Characteristic) |

### Central/Peripheralの役割

```
┌──────────────┐                    ┌──────────────┐
│   Central    │ ────スキャン────→  │  Peripheral  │
│  (クライアント)│                    │  (サーバー)   │
│              │ ←───アドバタイズ───│              │
│  Mac/iPhone  │                    │  ラズパイ等   │
│              │ ────接続要求────→  │              │
│              │ ←───接続承認───── │              │
│              │ ←→──データ通信──→ │              │
└──────────────┘                    └──────────────┘
```

| 役割 | 説明 | 主な動作 |
|------|------|----------|
| **Central** | 接続を開始する側 | スキャン、接続要求、データ読み書き |
| **Peripheral** | アドバタイズして待機する側 | アドバタイズ、GATTサーバー提供 |

---

## 2. Characteristicの詳細

### Properties（プロパティ）

| プロパティ | 説明 | 用途 |
|------------|------|------|
| **Read** | Centralがデータを読み取り可能 | センサー値取得など |
| **Write** | Centralがデータを書き込み可能 | コマンド送信、設定変更 |
| **Write Without Response** | 応答なしで高速書き込み | ストリーミングデータ |
| **Notify** | Peripheralが値変更を通知（応答不要） | リアルタイム更新 |
| **Indicate** | Peripheralが値変更を通知（応答必要） | 確実な通知が必要な場合 |

**Notify vs Indicate:**
```
Notify:   Peripheral ──→ Central (確認応答なし、高速)
Indicate: Peripheral ──→ Central ──→ Peripheral (確認応答あり、確実)
```

### Descriptors（ディスクリプタ）

| UUID | 名称 | 説明 |
|------|------|------|
| `0x2902` | CCCD (Client Characteristic Configuration Descriptor) | Notify/Indicateの有効化 |
| `0x2901` | Characteristic User Description | 説明文 |
| `0x2900` | Characteristic Extended Properties | 拡張プロパティ |

**CCCDの重要性:**
Notify/Indicateを受信するには、CCCDに書き込みが必要：
- `0x0001`: Notifyを有効化
- `0x0002`: Indicateを有効化
- `0x0000`: 無効化

---

## 3. bleakライブラリ（Mac側）

### 概要とインストール

**bleak** = Bluetooth Low Energy platform Agnostic Klient

- クロスプラットフォーム（macOS/Windows/Linux）
- asyncio ベースの非同期API
- Central（クライアント）専用

```bash
pip install bleak
```

### デバイススキャン方法

```python
import asyncio
from bleak import BleakScanner

async def scan_devices():
    """周囲のBLEデバイスをスキャン"""
    print("スキャン中...")
    
    # 方法1: 一定時間スキャン
    devices = await BleakScanner.discover(timeout=5.0)
    for device in devices:
        print(f"  {device.name}: {device.address}")
    
    # 方法2: 特定のデバイスを検索
    device = await BleakScanner.find_device_by_name("MyDevice")
    if device:
        print(f"Found: {device.address}")
    
    # 方法3: アドレスで検索
    device = await BleakScanner.find_device_by_address("XX:XX:XX:XX:XX:XX")

asyncio.run(scan_devices())
```

**フィルタリング付きスキャン:**
```python
async def scan_with_filter():
    """サービスUUIDでフィルタリング"""
    devices = await BleakScanner.discover(
        timeout=5.0,
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"]  # Battery Service
    )
    return devices
```

### 接続と切断

```python
from bleak import BleakClient

async def connect_device():
    address = "XX:XX:XX:XX:XX:XX"
    
    # 方法1: コンテキストマネージャー（推奨）
    async with BleakClient(address) as client:
        print(f"接続状態: {client.is_connected}")
        # 操作を実行
    # 自動的に切断される
    
    # 方法2: 手動接続/切断
    client = BleakClient(address)
    try:
        await client.connect()
        print(f"接続成功: {client.is_connected}")
        # 操作を実行
    finally:
        await client.disconnect()

asyncio.run(connect_device())
```

**切断コールバック:**
```python
def disconnected_callback(client):
    print(f"デバイスが切断されました: {client.address}")

async def connect_with_callback():
    async with BleakClient(address, disconnected_callback=disconnected_callback) as client:
        # ...
        pass
```

### サービス/Characteristic探索

```python
async def explore_services():
    async with BleakClient(address) as client:
        # 全サービスを取得
        for service in client.services:
            print(f"[Service] {service.uuid}: {service.description}")
            
            for char in service.characteristics:
                print(f"  [Char] {char.uuid}")
                print(f"    Properties: {char.properties}")
                print(f"    Handle: {char.handle}")
                
                # Descriptorを取得
                for descriptor in char.descriptors:
                    print(f"    [Desc] {descriptor.uuid}")
```

**出力例:**
```
[Service] 0000180f-0000-1000-8000-00805f9b34fb: Battery Service
  [Char] 00002a19-0000-1000-8000-00805f9b34fb
    Properties: ['read', 'notify']
    Handle: 14
    [Desc] 00002902-0000-1000-8000-00805f9b34fb
```

### データの読み書き方法

```python
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
CUSTOM_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef0"

async def read_write_data():
    async with BleakClient(address) as client:
        
        # === Read ===
        value = await client.read_gatt_char(BATTERY_LEVEL_UUID)
        print(f"Battery Level: {value[0]}%")
        
        # === Write (with response) ===
        data = bytearray([0x01, 0x02, 0x03])
        await client.write_gatt_char(CUSTOM_CHAR_UUID, data, response=True)
        
        # === Write Without Response ===
        await client.write_gatt_char(CUSTOM_CHAR_UUID, data, response=False)
        
        # === Notify ===
        def notification_handler(sender, data):
            print(f"Notification from {sender}: {data.hex()}")
        
        await client.start_notify(CUSTOM_CHAR_UUID, notification_handler)
        await asyncio.sleep(10)  # 10秒間Notifyを受信
        await client.stop_notify(CUSTOM_CHAR_UUID)
```

---

## 4. 通信フローの概要

```
時間 →
────────────────────────────────────────────────────────────→

Peripheral (ラズパイ)
│
│ ①アドバタイズ開始
│   "私はここにいます！"
│   (デバイス名、UUID等を定期的にブロードキャスト)
▼

Central (Mac)
│
│ ②スキャン
│   周囲のBLEデバイスを探索
│   →アドバタイズを受信
▼

Central → Peripheral
│
│ ③接続要求
│   "接続したい"
│   →接続確立
▼

Central ←→ Peripheral
│
│ ④サービス探索
│   Centralが利用可能なサービス/Characteristicを取得
▼

Central ←→ Peripheral
│
│ ⑤データ送受信
│   - Read: Central ← Peripheral
│   - Write: Central → Peripheral  
│   - Notify: Central ← Peripheral (購読)
▼

Central → Peripheral
│
│ ⑥切断
│   接続を終了
```

**コード例（完全なフロー）:**

```python
import asyncio
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "RaspberryPi_BLE"
CUSTOM_SERVICE_UUID = "12345678-0000-1000-8000-00805f9b34fb"
KEY_CHAR_UUID = "12345678-0001-1000-8000-00805f9b34fb"

async def full_flow():
    # ② スキャン
    print("デバイスをスキャン中...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    
    if not device:
        print("デバイスが見つかりません")
        return
    
    print(f"デバイス発見: {device.address}")
    
    # ③ 接続
    async with BleakClient(device.address) as client:
        print(f"接続成功: {client.is_connected}")
        
        # ④ サービス探索
        for service in client.services:
            if service.uuid == CUSTOM_SERVICE_UUID:
                print(f"目的のサービス発見: {service.uuid}")
        
        # ⑤ データ送信（キー情報）
        key_data = bytearray([0x04, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00])  # 'a'キー
        await client.write_gatt_char(KEY_CHAR_UUID, key_data, response=True)
        print(f"送信完了: {key_data.hex()}")
        
        # キーリリース
        release_data = bytearray([0x00] * 8)
        await client.write_gatt_char(KEY_CHAR_UUID, release_data, response=True)
    
    # ⑥ 切断（with文を抜けると自動切断）
    print("切断完了")

asyncio.run(full_flow())
```

---

## 5. データ転送の特性

### MTU（Maximum Transmission Unit）

| 項目 | 値 |
|------|-----|
| デフォルトMTU | 23 bytes |
| 最大MTU | 517 bytes（BLE 4.2以降） |
| ヘッダー | 3 bytes |
| **実効ペイロード** | MTU - 3 bytes |

**MTUネゴシエーション:**
```
デフォルト: 23 - 3 = 20 bytes/パケット
最大:       517 - 3 = 514 bytes/パケット
```

**bleakでのMTU確認:**
```python
async def check_mtu():
    async with BleakClient(address) as client:
        # macOSではmtu_sizeが利用可能
        mtu = client.mtu_size
        print(f"MTU: {mtu} bytes")
        print(f"実効ペイロード: {mtu - 3} bytes")
```

### データサイズ制限と対策

| シナリオ | 対策 |
|----------|------|
| データ < 20 bytes | そのまま送信可能 |
| データ > 20 bytes | MTUネゴシエーション or 分割送信 |

**分割送信の例:**
```python
async def send_large_data(client, char_uuid, data: bytes, chunk_size=20):
    """大きなデータを分割して送信"""
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        await client.write_gatt_char(char_uuid, chunk, response=True)
        print(f"送信: {i}/{len(data)} bytes")
```

### HID キーボードレポートの場合

HIDキーボードレポートは通常8バイト：
```
[Modifier][Reserved][Key1][Key2][Key3][Key4][Key5][Key6]
    1         1        1     1     1     1     1     1   = 8 bytes
```

→ デフォルトMTU（20 bytes）で十分送信可能

---

## まとめ

| 項目 | 要点 |
|------|------|
| **GATT構造** | Profile > Service > Characteristic > Descriptor |
| **UUID** | 標準は16bit短縮形、カスタムは128bit |
| **Central** | スキャン・接続する側（Mac） |
| **Peripheral** | アドバタイズ・待機する側（ラズパイ） |
| **bleak** | MacでBLE Centralを実装する非同期ライブラリ |
| **MTU** | デフォルト23bytes、最大517bytes |
| **HID** | 8bytesレポートで十分送信可能 |

---

## 参考リンク

- [bleak公式ドキュメント](https://bleak.readthedocs.io/)
- [Bluetooth SIG GATT仕様](https://www.bluetooth.com/specifications/gatt/)
- [Bluetooth Assigned Numbers](https://www.bluetooth.com/specifications/assigned-numbers/)
