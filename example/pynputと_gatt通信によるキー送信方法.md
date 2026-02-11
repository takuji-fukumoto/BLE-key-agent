# Copilot Chat Conversation Export: PynputとGATT通信によるキー送

**User:** @takuji-fukumoto
**Thread URL:** https://github.com/copilot/c/000f0b27-fec0-4501-a45c-bf929afa9747

## @takuji-fukumoto

bluetooth経由でmacからラズパイにキー情報を送る方法について、実現方法を推奨度と合わせていくつか提示してみて

## Copilot

# Bluetooth経由でMacからRaspberry Piにキー情報を送る方法

以下に、実現方法を推奨度順に整理して提示します。

---

## ⭐⭐⭐ 推奨度：高

### 1. Bluetooth RFCOMM（SPP: Serial Port Profile）経由のソケット通信

**概要**: Bluetoothの仮想シリアルポート（RFCOMM）を使い、Mac側からPython等でキー情報をソケット送信し、ラズパイ側で受信する方法。

**Mac側（送信）例:**
```python name=mac_sender.py
import bluetooth

target_address = "XX:XX:XX:XX:XX:XX"  # ラズパイのBluetooth MACアドレス
port = 1

sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
sock.connect((target_address, port))

try:
    while True:
        key = input("送信するキー: ")
        sock.send(key)
except KeyboardInterrupt:
    pass
finally:
    sock.close()
```

**ラズパイ側（受信）例:**
```python name=raspi_receiver.py
import bluetooth

server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
server_sock.bind(("", bluetooth.PORT_ANY))
server_sock.listen(1)

port = server_sock.getsockname()[1]
print(f"RFCOMMチャンネル {port} で待機中...")

bluetooth.advertise_service(server_sock, "KeyService",
    service_classes=[bluetooth.SERIAL_PORT_CLASS],
    profiles=[bluetooth.SERIAL_PORT_PROFILE])

client_sock, client_info = server_sock.accept()
print(f"接続: {client_info}")

try:
    while True:
        data = client_sock.recv(1024)
        if not data:
            break
        print(f"受信キー: {data.decode()}")
except Exception as e:
    print(e)
finally:
    client_sock.close()
    server_sock.close()
```

| 項目 | 詳細 |
|---|---|
| **メリット** | シンプル・軽量。双方向通信可能。低レイテンシ |
| **デメリット** | `PyBluez` ライブラリのインストールが必要。macOSでの `PyBluez` ビルドにやや手間がかかる場合あり |
| **必要ライブラリ** | `pybluez` (`pip install pybluez`) |

---

### 2. BLE（Bluetooth Low Energy）GATT通信

**概要**: Mac側をBLE Central、ラズパイ側をBLE Peripheral（GATTサーバー）として構成。Characteristicにキー情報を書き込む形で送信する。

**ラズパイ側（BLE GATTサーバー）例:**
```python name=raspi_ble_server.py
import dbus
import dbus.mainloop.glib
from gi.repository import GLib
from advertisement import Advertisement
from service import Application, Service, Characteristic

CUSTOM_SVC_UUID = "00001234-0000-1000-8000-00805f9b34fb"
KEY_CHAR_UUID   = "00005678-0000-1000-8000-00805f9b34fb"

class KeyCharacteristic(Characteristic):
    def __init__(self, service):
        super().__init__(KEY_CHAR_UUID, ["write"], service)

    def WriteValue(self, value, options):
        key = bytes(value).decode()
        print(f"受信キー: {key}")

class KeyService(Service):
    def __init__(self):
        super().__init__(CUSTOM_SVC_UUID, True)
        self.add_characteristic(KeyCharacteristic(self))

# GATTサーバー起動
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
app = Application()
app.add_service(KeyService())
app.register()

adv = Advertisement(0, "peripheral")
adv.add_service_uuid(CUSTOM_SVC_UUID)
adv.register()

GLib.MainLoop().run()
```

**Mac側（BLE Central / 送信）例:**
```python name=mac_ble_sender.py
import asyncio
from bleak import BleakClient, BleakScanner

KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"
DEVICE_NAME = "raspi-ble"

async def main():
    device = await BleakScanner.find_device_by_name(DEVICE_NAME)
    if not device:
        print("デバイスが見つかりません")
        return

    async with BleakClient(device) as client:
        while True:
            key = input("送信するキー: ")
            await client.write_gatt_char(KEY_CHAR_UUID, key.encode())
            print(f"送信完了: {key}")

asyncio.run(main())
```

| 項目 | 詳細 |
|---|---|
| **メリット** | 省電力。macOSとの相性が良い（`bleak`ライブラリがCoreBluetooth対応）。ペアリング不要で手軽 |
| **デメリット** | 1回に送れるデータ量が小さい（通常20〜512バイト）。Classic BTに比べスループットは低い |
| **必要ライブラリ** | Mac側: `bleak`、ラズパイ側: `dbus-python` + BlueZ |

---

## ⭐⭐ 推奨度：中

### 3. Bluetooth HID（Human Interface Device）プロファイル

**概要**: ラズパイをBluetoothキーボードデバイスとしてエミュレートし、Mac→ラズパイ間ではなく**ラズパイ→Macにキー入力を送る**のが本来の使い方。逆方向（Mac→ラズパイ）の場合は、Mac側をHIDデバイスに見せる必要があり、実装が複雑になる。

| 項目 | 詳細 |
|---|---|
| **メリット** | OS標準のHID入力として扱えるため、ラズパイ側でアプリ不要（逆方向の場合） |
| **デメリット** | Mac→ラズパイ方向は非標準的で実装が複雑。macOSのHID制限が厳しい |
| **向いている用途** | ラズパイ→Mac方向のキー送信（逆方向） |

---

### 4. Bluetooth PAN（Personal Area Network）+ TCP/IP ソケット

**概要**: BluetoothでPANネットワークを構築し、その上でTCP/IPソケット通信を行う。

```python name=tcp_key_sender.py
# Bluetooth PAN確立後は通常のソケット通信と同じ
import socket

# Mac側（送信）
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.1.x", 9999))  # PAN上のラズパイIP
sock.send(b"key_a")
sock.close()
```

| 項目 | 詳細 |
|---|---|
| **メリット** | TCP/IPの上で動くので既存のネットワークプログラムがそのまま使える |
| **デメリット** | PAN設定が手間。Wi-Fiが使えるなら、わざわざBluetoothを使う意味が薄い |

---

## ⭐ 推奨度：低

### 5. OBEX（Object Exchange）経由のファイル転送

**概要**: Bluetoothファイル転送でキー情報をファイルとして送る方法。

| 項目 | 詳細 |
|---|---|
| **メリット** | OS標準機能で使える |
| **デメリット** | リアルタイム性が低い。ファイル単位の送受信のため、キー入力のようなストリーム的用途には不向き |

---

## 📊 比較まとめ

| 方法 | 推奨度 | リアルタイム性 | 実装の容易さ | 省電力性 | macOS対応 |
|---|---|---|---|---|---|
| **RFCOMM (SPP)** | ⭐⭐⭐ | ◎ | ○ | △ | △（PyBluezのビルドに注意） |
| **BLE GATT** | ⭐⭐⭐ | ○ | ○ | ◎ | ◎（bleakが安定） |
| **HID** | ⭐⭐ | ◎ | △ | ○ | △（方向が逆なら◎） |
| **PAN + TCP** | ⭐⭐ | ○ | △ | △ | ○ |
| **OBEX** | ⭐ | ✕ | ○ | △ | ○ |

---

## 🎯 結論・おすすめ

| ユースケース | おすすめ |
|---|---|
| **手軽に始めたい・macOSとの相性重視** | **BLE GATT**（`bleak` ライブラリ） |
| **データ量が多い・双方向でストリーム通信したい** | **RFCOMM (SPP)** |
| **ラズパイからMacにキーを送りたい（逆方向）** | **Bluetooth HID** |

最も汎用的でmacOSとの互換性が高いのは **BLE GATT通信（方法2）** です。`bleak` ライブラリはmacOSのCoreBluetoothをネイティブに使うため、セットアップも比較的簡単です。

## @takuji-fukumoto

GATT通信についてよく知らないのですが、以下2点教えてください

## Copilot

もちろんです！ただ、質問の内容が途中で切れているようです。

GATT通信について知りたい **2点** をお聞かせいただけますか？

例えば、以下のような内容でしょうか？

1. **GATTの基本的な仕組み・アーキテクチャ**について
2. **GATTのセキュリティ（暗号化・認証）**について
3. **GATTのデータサイズ制限や通信速度**について
4. **GATTとClassic Bluetoothの違い**について
5. **実装時の具体的な手順・注意点**について

ご質問の2点を教えていただければ、

## @takuji-fukumoto

1と4について

## Copilot

# GATT通信について

## 1. GATTの基本的な仕組み・アーキテクチャ

### GATTとは

**GATT（Generic Attribute Profile）** は、BLE（Bluetooth Low Energy）デバイス間でデータをやり取りするための標準的なプロトコルです。データを**階層構造**で整理し、小さな単位で読み書きする仕組みを提供します。

### 階層構造

GATTのデータは以下の **3層構造** で整理されています。

```
┌─────────────────────────────────────────┐
│              Profile                     │
│  ┌───────────────────────────────────┐  │
│  │          Service (サービス)        │  │
│  │  UUID: 例 0x180D (Heart Rate)     │  │
│  │                                    │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ Characteristic (特性)       │  │  │
│  │  │ UUID: 例 0x2A37              │  │  │
│  │  │ Properties: Read/Write/Notify│  │  │
│  │  │ Value: 実際のデータ          │  │  │
│  │  └─────────────────────────────┘  │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ Characteristic (特性)       │  │  │
│  │  │ ...                         │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │          Service (サービス)        │  │
│  │  ...                              │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

| 階層 | 説明 | 例え |
|---|---|---|
| **Profile** | サービスの集合体。デバイス全体の機能を定義 | 「このデバイスは心拍計です」 |
| **Service** | 関連する機能のグループ。UUIDで識別 | 「心拍測定機能」「バッテリー情報」 |
| **Characteristic** | 実際のデータの入れ物。読み書きの対象 | 「心拍数の値」「バッテリー残量」 |

### 通信の役割分担（Central と Peripheral）

```
  ┌──────────────┐                    ┌──────────────────┐
  │     Mac      │                    │   Raspberry Pi    │
  │  (Central)   │ ──── BLE ────▶    │  (Peripheral)     │
  │              │                    │                   │
  │  データを     │   Read/Write/     │  GATTサーバー      │
  │  読み書きする  │    Notify         │  (データを保持)    │
  └──────────────┘                    └──────────────────┘
```

| 役割 | 説明 |
|---|---|
| **Peripheral（周辺機器）** | GATTサーバーとして動作。データを保持し、アドバタイズ（自分の存在を通知）する |
| **Central（中央機器）** | GATTクライアントとして動作。Peripheralを探し、接続してデータを読み書きする |

### 操作の種類

Characteristicに対して行える操作は主に以下の4つです：

| 操作 | 方向 | 説明 |
|---|---|---|
| **Read** | Central ← Peripheral | Centralがデータを読み取る |
| **Write** | Central → Peripheral | Centralがデータを書き込む |
| **Notify** | Central ← Peripheral | Peripheral側からデータ変更を自動通知（購読型） |
| **Indicate** | Central ← Peripheral | Notifyと同様だが、受信確認（ACK）あり |

### キー送信の場合の流れ

```
Mac (Central)                          Raspberry Pi (Peripheral)
    │                                         │
    │  1. スキャン (アドバタイズを探す)          │
    │ ◀──────── アドバタイズ ─────────────────│
    │                                         │
    │  2. 接続                                 │
    │ ─────────── 接続要求 ──────────────────▶ │
    │                                         │
    │  3. サービス/Characteristic 探索          │
    │ ─────────── ディスカバリ ──────────────▶ │
    │ ◀────── サービス一覧を返す ──────────── │
    │                                         │
    │  4. キー情報を書き込み (Write)            │
    │ ──── Write("key_a") ──────────────────▶ │
    │                                    受信処理│
    │  5. 繰り返し                             │
    │ ──── Write("key_b") ──────────────────▶ │
    │                                         │
```

---

## 4. GATTとClassic Bluetoothの違い

### 基本的な違い

そもそも **BLE（GATT）** と **Classic Bluetooth（RFCOMM等）** は、同じ「Bluetooth」という名前でも **別の通信規格** です。

| 項目 | Classic Bluetooth (RFCOMM/SPP) | BLE (GATT) |
|---|---|---|
| **Bluetooth規格** | Bluetooth 2.0〜3.0 | Bluetooth 4.0以降 |
| **設計思想** | 大容量データの連続転送 | 少量データの間欠的な通信 |
| **消費電力** | 高い | **非常に低い** |
| **通信モデル** | ストリーム型（ソケット通信） | **属性ベース（Read/Write/Notify）** |
| **ペアリング** | 基本的に必要 | **不要な場合も多い** |
| **最大データサイズ** | 大きい（ストリーム） | 小さい（1回あたり20〜512バイト） |
| **スループット** | 最大 2〜3 Mbps | 最大 約1 Mbps（実効はもっと低い） |
| **接続確立の速度** | 遅い（数秒） | **速い（ミリ秒〜数百ミリ秒）** |
| **同時接続数** | 通常7台まで | **多数接続可能** |

### 通信モデルの違い（最も重要な違い）

```
【Classic Bluetooth (RFCOMM)】
  ストリーム型 ── 電話のようなイメージ
  
  Mac ════════════════════════ Raspberry Pi
       連続的なデータの流れ（パイプ）
       "aaa" → "bbb" → "ccc" → ...
  
  → 一度接続したら、自由にデータを流し続けられる


【BLE (GATT)】
  属性ベース ── 掲示板のようなイメージ
  
  Mac ──── Write("key_a") ───▶ [Characteristic] ← Raspberry Pi が読む
  Mac ──── Write("key_b") ───▶ [Characteristic] ← Raspberry Pi が読む
  
  → Characteristicという「箱」にデータを出し入れする
```

### どちらを選ぶべきか

| ユースケース | 推奨 | 理由 |
|---|---|---|
| **キー入力を1つずつ送る** | ✅ **BLE (GATT)** | データ量が小さく、省電力。macOSとの相性◎ |
| **キーログを大量にストリーム送信** | ✅ **Classic (RFCOMM)** | 大量データの連続送信に向いている |
| **ペアリングなしで手軽に接続** | ✅ **BLE (GATT)** | ペアリング不要で接続が速い |
| **バッテリー駆動のラズパイ** | ✅ **BLE (GATT)** | 消費電力が圧倒的に少ない |
| **複数デバイスと同時接続** | ✅ **BLE (GATT)** | 同時接続数が多い |

---

## まとめ

**GATT通信**は、データを「サービス → Characteristic」という階層構造で整理し、**小さなデータを効率的にやり取りする仕組み**です。Classic Bluetoothの「パイプでデータを流す」モデルとは根本的に異なり、「**データの箱（Characteristic）に値を出し入れする**」というモデルで動作します。

キー情報の送信のように **少量のデータを都度送る** 用途であれば、**BLE（GATT）が最適** です。

## @takuji-fukumoto

macから入力監視して入力されたキーをラズパイに送りたいです。pynputとGATT通信を用いたサンプルコード提示してみて

## Copilot

# pynput + BLE GATT通信によるキー送信サンプル

## 全体構成

```
┌─────────────────────┐          BLE           ┌─────────────────────┐
│        Mac           │ ─────────────────────▶ │   Raspberry Pi       │
│                      │                        │                      │
│  pynput でキー監視    │   GATT Write          │  GATTサーバーで受信    │
│  bleak で BLE送信    │   (Characteristic)     │  BlueZ + dbus        │
└─────────────────────┘                        └─────────────────────┘
```

---

## Mac側（Central / 送信側）

```python name=mac_key_sender.py
"""
Mac側: pynputでキーボード入力を監視し、BLE GATT経由でラズパイに送信する
必要ライブラリ: pip install pynput bleak
"""

import asyncio
import threading
from pynput import keyboard
from bleak import BleakClient, BleakScanner

# ラズパイ側で定義するCharacteristicのUUID（ラズパイ側と一致させること）
KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"
DEVICE_NAME = "RasPi-KeyReceiver"

# 送信キューを用意（pynputのコールバックは同期、bleakは非同期なので橋渡しが必要）
key_queue: asyncio.Queue = None


def on_press(key):
    """キーが押されたときのコールバック"""
    try:
        # 通常の文字キー
        key_str = key.char
    except AttributeError:
        # 特殊キー（Enter, Shift, Ctrl など）
        key_str = str(key)

    if key_str is None:
        return

    print(f"[入力検知] {key_str}")

    # 非同期キューにスレッドセーフに追加
    asyncio.run_coroutine_threadsafe(key_queue.put(key_str), loop)


def on_release(key):
    """Escキーで終了"""
    if key == keyboard.Key.esc:
        print("[終了] Escキーが押されました")
        asyncio.run_coroutine_threadsafe(key_queue.put(None), loop)
        return False  # リスナーを停止


async def scan_and_connect():
    """ラズパイのBLEデバイスをスキャンして接続"""
    print(f"[スキャン中] デバイス名: {DEVICE_NAME} を探しています...")

    device = None
    while device is None:
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=5.0)
        if device is None:
            print("[スキャン中] デバイスが見つかりません。再スキャンします...")

    print(f"[発見] {device.name} ({device.address})")
    return device


async def send_keys(device):
    """接続してキューからキー情報を送信し続ける"""
    async with BleakClient(device) as client:
        print(f"[接続完了] {device.name}")
        print("=" * 50)
        print("キーボード入力を監視中... (Escで終了)")
        print("=" * 50)

        while True:
            # キューからキー情報を取得（ブロッキング）
            key_str = await key_queue.get()

            # Noneが来たら終了
            if key_str is None:
                print("[送信終了]")
                break

            try:
                data = key_str.encode("utf-8")
                await client.write_gatt_char(KEY_CHAR_UUID, data)
                print(f"[送信完了] {key_str} ({len(data)} bytes)")
            except Exception as e:
                print(f"[送信エラー] {e}")
                break


async def main():
    global key_queue, loop
    loop = asyncio.get_event_loop()
    key_queue = asyncio.Queue()

    # BLEデバイスをスキャン・接続
    device = await scan_and_connect()

    # pynputのキーボードリスナーを別スレッドで起動
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # キー送信ループ
    await send_keys(device)

    listener.stop()
    print("[完了] プログラムを終了します")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Raspberry Pi側（Peripheral / 受信側）

```python name=raspi_key_receiver.py
"""
Raspberry Pi側: BLE GATTサーバーとしてMacからのキー情報を受信する
必要パッケージ: sudo apt install python3-dbus bluez
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

# カスタムUUID（Mac側と一致させること）
KEY_SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
KEY_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"


# ============================================================
#  Advertisement（BLEアドバタイズ）
# ============================================================
class Advertisement(dbus.service.Object):
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
        properties = {
            LE_ADVERTISEMENT_IFACE: {
                "Type": self.ad_type,
                "ServiceUUIDs": dbus.Array(self.service_uuids, signature="s"),
                "LocalName": dbus.String(self.local_name),
                "IncludeTxPower": dbus.Boolean(self.include_tx_power),
            }
        }
        return properties

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


# ============================================================
#  GATT Service
# ============================================================
class Service(dbus.service.Object):
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


# ============================================================
#  GATT Characteristic（キー受信用）
# ============================================================
class KeyCharacteristic(dbus.service.Object):
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
        """Mac側からキー情報が書き込まれたときに呼ばれる"""
        key_str = bytes(value).decode("utf-8")
        print(f"[受信] キー: {key_str}")

        # ============================================
        # ここに受信したキーに応じた処理を追加する
        # 例: GPIO制御、コマンド実行、ログ記録など
        # ============================================
        self.handle_key(key_str)

    def handle_key(self, key_str):
        """受信したキーに応じた処理（カスタマイズ用）"""
        key_actions = {
            "Key.space": lambda: print("  → スペースキーが押されました"),
            "Key.enter": lambda: print("  → Enterキーが押されました"),
            "Key.esc": lambda: print("  → Escキーが押されました"),
        }

        action = key_actions.get(key_str)
        if action:
            action()
        else:
            print(f"  → 文字キー '{key_str}' を受信しました")


# ============================================================
#  Application（GATTサービスの登録管理）
# ============================================================
class Application(dbus.service.Object):
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


# ============================================================
#  メイン処理
# ============================================================
def register_ad_cb():
    print("[ADV] アドバタイズ登録完了")

def register_ad_error_cb(error):
    print(f"[ADV] アドバタイズ登録失敗: {error}")
    mainloop.quit()

def register_app_cb():
    print("[GATT] アプリケーション登録完了")

def register_app_error_cb(error):
    print(f"[GATT] アプリケーション登録失敗: {error}")
    mainloop.quit()


def main():
    global mainloop

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # BlueZのアダプタを取得
    adapter_path = "/org/bluez/hci0"
    adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)

    # アダプタの電源をONにする
    adapter_props = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))

    # GATTマネージャー
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)

    # アドバタイズマネージャー
    ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    # アプリケーション（GATTサービス）をセットアップ
    app = Application(bus)
    service = Service(bus, 0, KEY_SERVICE_UUID, True)
    key_char = KeyCharacteristic(bus, 0, service)
    service.add_characteristic(key_char)
    app.add_service(service)

    # アドバタイズをセットアップ
    adv = Advertisement(bus, 0)

    mainloop = GLib.MainLoop()

    # GATTアプリケーションを登録
    gatt_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=register_app_cb,
        error_handler=register_app_error_cb,
    )

    # アドバタイズを登録
    ad_manager.RegisterAdvertisement(
        adv.get_path(),
        {},
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
        print("\n[終了] サーバーを停止します")
        mainloop.quit()


if __name__ == "__main__":
    main()
```

---

## セットアップ手順

### Mac側

```bash name=mac_setup.sh
# 必要ライブラリのインストール
pip install pynput bleak

# macOSのアクセシビリティ権限が必要
# システム設定 → プライバシーとセキュリティ → アクセシビリティ
# → ターミナル（または実行するアプリ）を許可

# 実行
python mac_key_sender.py
```

### Raspberry Pi側

```bash name=raspi_setup.sh
# 必要パッケージのインストール
sudo apt update
sudo apt install -y python3-dbus python3-gi bluez

# Bluetoothサービスの設定
# /etc/bluetooth/main.conf を編集して以下を追記・変更
# [General]
# Name = RasPi-KeyReceiver
# DiscoverableTimeout = 0

# Bluetoothサービス再起動
sudo systemctl restart bluetooth

# 実行（root権限が必要）
sudo python3 raspi_key_receiver.py
```

---

## 動作イメージ

```
【Mac側の出力】
==================================================
キーボード入力を監視中... (Escで終了)
==================================================
[入力検知] h
[送信完了] h (1 bytes)
[入力検知] e
[送信完了] e (1 bytes)
[入力検知] l
[送信完了] l (1 bytes)
[入力検知] l
[送信完了] l (1 bytes)
[入力検知] o
[送信完了] o (1 bytes)
[入力検知] Key.enter
[送信完了] Key.enter (9 bytes)
[入力検知] Key.esc
[終了] Escキーが押されました

【Raspberry Pi側の出力】
==================================================
BLE GATTサーバー起動中...
デバイス名: RasPi-KeyReceiver
サービスUUID: 00001234-0000-1000-8000-00805f9b34fb
Macからの接続を待機しています...
==================================================
[GATT] アプリケーション登録完了
[ADV] アドバタイズ登録完了
[受信] キー: h
  → 文字キー 'h' を受信しました
[受信] キー: e
  → 文字キー 'e' を受信しました
[受信] キー: l
  → 文字キー 'l' を受信しました
[受信] キー: l
  → 文字キー 'l' を受信しました
[受信] キー: o
  → 文字キー 'o' を受信しました
[受信] キー: Key.enter
  → Enterキーが押されました
```

---

## 注意点

| 項目 | 詳細 |
|---|---|
| **macOS権限** | pynputによるキーボード監視には**アクセシビリティ権限**が必須。許可しないと入力を検知できません |
| **root権限** | ラズパイ側は BlueZ の D-Bus API を使うため **`sudo`** で実行が必要です |
| **データサイズ** | BLE GATT の1回の Write は最大 **512バイト**（通常は20バイト）。キー1つなら十分ですが、大量データには不向きです |
| **接続距離** | BLE の通信距離は通常 **10〜30m** 程度（障害物により変動） |
| **高速タイピング** | 非常に高速なタイピングでは送信が追いつかない可能性があります。キューで順序は保証されますが、遅延が生じる場合があります |

## @takuji-fukumoto

KEY_CHAR_UUIDとDEVICE_NAMEは自由に変更しても大丈夫？

## Copilot

## KEY_CHAR_UUID と DEVICE_NAME の変更について

### DEVICE_NAME → ✅ 自由に変更OK

単なるラベル（表示名）なので、好きな名前に変更して問題ありません。

```python
# Mac側・ラズパイ側で一致していればOK
DEVICE_NAME = "MyKeyboard"       # ✅ OK
DEVICE_NAME = "takuji-raspi"     # ✅ OK
DEVICE_NAME = "猫キーボード"      # ✅ OK（ただし英数字が無難）
```

**注意点:**
- Mac側とラズパイ側で**同じ名前**にすること
- 長すぎるとアドバタイズパケットに収まらない（**最大29バイト程度**が目安）


---

### KEY_CHAR_UUID / KEY_SERVICE_UUID → ⚠️ 条件付きで変更OK

自由に変更できますが、**UUIDのフォーマットと予約範囲のルール**を守る必要があります。

#### ❌ 避けるべき範囲

```
0000xxxx-0000-1000-8000-00805f9b34fb
    ^^^^
    ここが 0x0000 〜 0xFFFF の範囲
```

この形式は **Bluetooth SIG（標準化団体）が予約** しているUUIDです。例えば：

| UUID (短縮形) | 用途 |
|---|---|
| `0x180D` | Heart Rate Service（心拍計） |
| `0x180F` | Battery Service（バッテリー） |
| `0x2A37` | Heart Rate Measurement |

先ほどのサンプルコードでは `0x1234` / `0x5678` を使っていましたが、実はこれもSIG予約範囲内なので**本来は避けるべき**です。

#### ✅ 正しい方法：ランダムなUUIDv4を生成する

```bash
# Mac/LinuxのターミナルでUUIDを生成
uuidgen
# 例: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

```python
# 生成したUUIDを使う
KEY_SERVICE_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"  # ✅ 安全
KEY_CHAR_UUID    = "8c235bfa-917a-4e72-b5d2-1ab5d3e6f8c0"  # ✅ 安全
```

#### まとめ

| パターン | 安全性 | 例 |
|---|---|---|
| SIG予約範囲の短縮UUID | ❌ 非推奨 | `00001234-0000-1000-8000-00805f9b34fb` |
| ランダム生成したUUIDv4 | ✅ 推奨 | `f47ac10b-58cc-4372-a567-0e02b2c3d479` |

---

### 修正版

```python name=common_constants.py
"""Mac側・ラズパイ側の両方で共通して使う定数"""

# uuidgen で生成したカスタムUUID（自分専用）
KEY_SERVICE_UUID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
KEY_CHAR_UUID    = "8c235bfa-917a-4e72-b5d2-1ab5d3e6f8c0"

# デバイス名（好きな名前でOK）
DEVICE_NAME = "takuji-raspi"
```

Mac側とラズパイ側でこのファイルを共有（またはコピー）して、**UUID とデバイス名を一致させる**ことだけ守ればOKです。

## @takuji-fukumoto

社内で複数の人がまとめて利用する想定ですが、UUIDをバッティングさせない方法ありますか？

## Copilot

## UUID バッティング回避の方法

### 結論：UUIDv4のランダム生成なら衝突はほぼ起きない

UUIDv4は **128ビットのうち122ビットがランダム** で、その組み合わせ数は約 **5.3 × 10³⁶ 通り**です。

```
衝突確率の目安:
・10人で使う   → 衝突確率: ほぼ 0%
・1万人で使う  → 衝突確率: ほぼ 0%
・10億人で使う → 衝突確率: まだ ほぼ 0%

→ 各自が uuidgen で生成すれば、まず衝突しません
```

ただし「ほぼ0%」では不安、という運用上の懸念には以下の方法で対処できます。

---

### 方法1: ✅ 名前ベースUUID（UUIDv5）で体系的に生成する【推奨】

社員のメールアドレスや社員IDから**決定的にUUID**を生成する方法です。同じ入力からは常に同じUUIDが生成され、異なる入力からは必ず異なるUUIDが生成されます。

```python name=generate_uuid.py
import uuid

# 会社固有のNamespace（1回だけ生成して全社で共有する）
COMPANY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "example-corp.co.jp")

def generate_uuids_for_user(user_id: str):
    """社員IDからService UUIDとCharacteristic UUIDを生成"""
    service_uuid = uuid.uuid5(COMPANY_NAMESPACE, f"{user_id}/service")
    char_uuid    = uuid.uuid5(COMPANY_NAMESPACE, f"{user_id}/char")
    return str(service_uuid), str(char_uuid)


# 使用例
users = ["tanaka", "suzuki", "takuji"]

for user in users:
    svc, char = generate_uuids_for_user(user)
    print(f"{user}:")
    print(f"  SERVICE_UUID = \"{svc}\"")
    print(f"  CHAR_UUID    = \"{char}\"")
    print()
```

```
出力例:
tanaka:
  SERVICE_UUID = "a3b1c2d4-1111-5abc-9def-abcdef123456"
  CHAR_UUID    = "b4c2d3e5-2222-5abc-9def-abcdef654321"

suzuki:
  SERVICE_UUID = "c5d3e4f6-3333-5abc-9def-fedcba987654"
  CHAR_UUID    = "d6e4f5a7-4444-5abc-9def-fedcba123456"

takuji:
  SERVICE_UUID = "e7f5a6b8-5555-5abc-9def-abcdef789012"
  CHAR_UUID    = "f8a6b7c9-6666-5abc-9def-abcdef345678"
```

| メリット | デメリット |
|---|---|
| 同じ社員IDからは毎回同じUUIDが生成される | 全社で同じNamespaceを共有する必要がある |
| 絶対に衝突しない（入力が違えば出力も違う） | スクリプトの実行が一手間 |
| UUID管理台帳が不要 | — |

---

### 方法2: ✅ 設定ファイルで自動生成 + 固定化

初回起動時にUUIDを自動生成し、設定ファイルに保存する方法です。各自が意識せずにユニークなUUIDを持てます。

```python name=config_manager.py
import uuid
import json
import os

CONFIG_FILE = "ble_config.json"

def load_or_create_config(user_name: str) -> dict:
    """設定ファイルがなければUUIDを自動生成して保存"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        print(f"[設定読み込み] {CONFIG_FILE}")
    else:
        config = {
            "user_name": user_name,
            "device_name": f"BLE-{user_name}",
            "service_uuid": str(uuid.uuid4()),
            "char_uuid": str(uuid.uuid4()),
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        print(f"[設定生成] {CONFIG_FILE} を作成しました")

    return config


# 使用例
config = load_or_create_config("takuji")
print(json.dumps(config, indent=2))
```

```json name=ble_config.json
{
  "user_name": "takuji",
  "device_name": "BLE-takuji",
  "service_uuid": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "char_uuid": "8c235bfa-917a-4e72-b5d2-1ab5d3e6f8c0"
}
```

この設定ファイルを **Mac側とラズパイ側の両方に配置** して使います。

---

### 方法3: 中央管理台帳で払い出す

スプレッドシートやDBでUUIDを管理する方法です。

```
┌─────────┬──────────────────────────────────────┬──────────┐
│ 社員ID   │ SERVICE_UUID                          │ 割当日    │
├─────────┼──────────────────────────────────────┼──────────┤
│ tanaka  │ a3b1c2d4-1111-4abc-9def-abcdef123456 │ 2026-02-01│
│ suzuki  │ c5d3e4f6-3333-4abc-9def-fedcba987654 │ 2026-02-03│
│ takuji  │ e7f5a6b8-5555-4abc-9def-abcdef789012 │ 2026-02-09│
└─────────┴──────────────────────────────────────┴──────────┘
```

| メリット | デメリット |
|---|---|
| 一覧で管理できる | 手動運用の手間がかかる |
| 確実に衝突を防げる | 管理者がボトルネックになる |

---

## 比較まとめ

| 方法 | 衝突リスク | 運用コスト | スケーラビリティ | おすすめ度 |
|---|---|---|---|---|
| **UUIDv5（名前ベース生成）** | なし（決定的） | 低い | ◎ | ⭐⭐⭐ |
| **設定ファイル自動生成** | ほぼなし | 低い | ○ | ⭐⭐⭐ |
| **UUIDv4を各自生成** | ほぼなし | 最低 | ○ | ⭐⭐ |
| **中央管理台帳** | なし | 高い | △ | ⭐ |

### 🎯 おすすめ

**方法1（UUIDv5）** が最も確実で運用しやすいです。`generate_uuid.py` を社内で共有し、各自が自分の社員IDを入力するだけで、**衝突が絶対に起きないUUIDのペア**を得られます。Mac側・ラズパイ側の両方に同じUUIDを設定すれば完了です。
