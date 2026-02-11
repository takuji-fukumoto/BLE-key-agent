# Raspberry PiでのBLE GATTサーバー実装（BlueZ/D-Bus）

## 1. BlueZの概要

### BlueZとは

BlueZはLinux公式のBluetoothプロトコルスタックです。

```
┌─────────────────────────────────────────────────────────────┐
│                      アプリケーション                        │
│              (Python, C, Node.js など)                      │
├─────────────────────────────────────────────────────────────┤
│                       D-Bus API                             │
│            (アプリケーションとの通信インターフェース)          │
├─────────────────────────────────────────────────────────────┤
│                        BlueZ                                │
│    ┌─────────┬──────────┬─────────┬─────────────┐          │
│    │  GATT   │   GAP    │  L2CAP  │    HCI      │          │
│    └─────────┴──────────┴─────────┴─────────────┘          │
├─────────────────────────────────────────────────────────────┤
│                    Linuxカーネル                            │
├─────────────────────────────────────────────────────────────┤
│                 Bluetoothハードウェア                        │
└─────────────────────────────────────────────────────────────┘
```

| 特徴 | 説明 |
|------|------|
| **対応プロトコル** | BLE (4.0+), Bluetooth Classic |
| **API提供方式** | D-Bus経由 |
| **管理ツール** | bluetoothctl, hciconfig, btmgmt |
| **設定ファイル** | `/etc/bluetooth/main.conf` |

### D-Bus APIの構造

D-Busは**システムバス**上でプロセス間通信を行う仕組みです。

```
┌─────────────────────────────────────────────────────────────┐
│                     D-Bus System Bus                        │
├───────────────────┬───────────────────┬─────────────────────┤
│    org.bluez      │  org.bluez.GattManager1  │ org.bluez.LEAdvertisingManager1 │
├───────────────────┴───────────────────┴─────────────────────┤
│                                                             │
│  オブジェクトパス構造:                                       │
│  /org/bluez                                                 │
│  └── /org/bluez/hci0                    (アダプター)        │
│      └── /org/bluez/hci0/dev_XX_XX_XX   (デバイス)         │
│                                                             │
│  アプリケーション側オブジェクト:                             │
│  /org/example                                               │
│  └── /org/example/service0              (Service)          │
│      └── /org/example/service0/char0    (Characteristic)   │
│          └── /org/example/service0/char0/desc0 (Descriptor)│
└─────────────────────────────────────────────────────────────┘
```

**主要なD-Busインターフェース:**

| インターフェース | 役割 |
|------------------|------|
| `org.bluez.Adapter1` | Bluetoothアダプターの制御 |
| `org.bluez.GattManager1` | GATTサービスの登録 |
| `org.bluez.LEAdvertisingManager1` | アドバタイズの管理 |
| `org.bluez.GattService1` | GATTサービスの定義 |
| `org.bluez.GattCharacteristic1` | Characteristicの定義 |
| `org.bluez.GattDescriptor1` | Descriptorの定義 |

---

## 2. GATTサーバー構築

### 必要なパッケージ

```bash
# BlueZとD-Bus関連パッケージ
sudo apt update
sudo apt install -y bluez bluetooth pi-bluetooth

# Python D-Bus バインディング
sudo apt install -y python3-dbus python3-gi

# 開発用（任意）
sudo apt install -y libdbus-1-dev libglib2.0-dev
pip3 install dbus-python PyGObject
```

**バージョン確認:**
```bash
bluetoothctl --version  # BlueZ 5.55以上推奨
```

### D-Busオブジェクト構成

GATTサーバーは以下のオブジェクト構成で作成します：

```python
"""
D-Busオブジェクト階層構造:

Application (ObjectManager)
├── Service1 (GattService1)
│   ├── Characteristic1 (GattCharacteristic1)
│   │   └── Descriptor1 (GattDescriptor1)
│   └── Characteristic2 (GattCharacteristic1)
└── Service2 (GattService1)
    └── ...
"""
```

### Service/Characteristicの定義方法

**基本的なGATTサーバー実装:**

```python
#!/usr/bin/env python3
"""
raspi_gatt_server.py - Raspberry Pi BLE GATTサーバー
"""

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

# BlueZ D-Bus定数
BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
GATT_DESC_IFACE = "org.bluez.GattDescriptor1"


class Application(dbus.service.Object):
    """
    GATTアプリケーション - サービスのコンテナ
    org.freedesktop.DBus.ObjectManager を実装
    """
    def __init__(self, bus):
        self.path = "/org/bluez/example"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        """登録された全オブジェクトを返す"""
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.get_characteristics():
                response[chrc.get_path()] = chrc.get_properties()
                for desc in chrc.get_descriptors():
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(dbus.service.Object):
    """
    GATTサービス基底クラス
    org.bluez.GattService1 を実装
    """
    PATH_BASE = "/org/bluez/example/service"

    def __init__(self, bus, index, uuid, primary=True):
        self.path = f"{self.PATH_BASE}{index}"
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
                    signature="o"
                )
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException(
                "org.bluez.Error.InvalidArguments",
                "Invalid interface"
            )
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    """
    GATTキャラクタリスティック基底クラス
    org.bluez.GattCharacteristic1 を実装
    """
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                "Service": self.service.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags,
                "Descriptors": dbus.Array(
                    [d.get_path() for d in self.descriptors],
                    signature="o"
                )
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException(
                "org.bluez.Error.InvalidArguments",
                "Invalid interface"
            )
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        """Centralからの読み取り要求"""
        print(f"ReadValue: {self.value}")
        return self.value

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        """Centralからの書き込み要求"""
        self.value = value
        print(f"WriteValue: {bytes(value).decode('utf-8', errors='ignore')}")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        """Notify開始"""
        print("StartNotify called")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        """Notify停止"""
        print("StopNotify called")

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        """プロパティ変更シグナル（Notify用）"""
        pass


class Descriptor(dbus.service.Object):
    """
    GATTディスクリプタ基底クラス
    org.bluez.GattDescriptor1 を実装
    """
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = f"{characteristic.path}/desc{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.characteristic = characteristic
        self.value = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_DESC_IFACE: {
                "Characteristic": self.characteristic.get_path(),
                "UUID": self.uuid,
                "Flags": self.flags
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_DESC_IFACE:
            raise dbus.exceptions.DBusException(
                "org.bluez.Error.InvalidArguments",
                "Invalid interface"
            )
        return self.get_properties()[GATT_DESC_IFACE]

    @dbus.service.method(GATT_DESC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        return self.value

    @dbus.service.method(GATT_DESC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        self.value = value
```

**カスタムサービス実装例:**

```python
# UUIDの定義
KEY_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
KEY_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"


class KeyService(Service):
    """キー受信サービス"""
    def __init__(self, bus, index):
        super().__init__(bus, index, KEY_SERVICE_UUID, primary=True)
        self.add_characteristic(KeyCharacteristic(bus, 0, self))


class KeyCharacteristic(Characteristic):
    """キー受信キャラクタリスティック"""
    def __init__(self, bus, index, service):
        super().__init__(
            bus, index, KEY_CHAR_UUID,
            ["write", "write-without-response"],  # Writeプロパティ
            service
        )

    def WriteValue(self, value, options):
        """書き込まれたキー情報を処理"""
        key_data = bytes(value).decode("utf-8", errors="ignore")
        print(f"受信キー: {key_data}")
        # ここでキー処理を実行
        self.process_key(key_data)

    def process_key(self, key_data):
        """キー情報の処理"""
        # 例: JSONパースしてキーイベントを再現
        import json
        try:
            event = json.loads(key_data)
            print(f"キーイベント: {event}")
        except json.JSONDecodeError:
            print(f"生データ: {key_data}")
```

---

## 3. Advertisementの設定

### アドバタイズの役割

```
┌───────────────┐                     ┌───────────────┐
│    Central    │  ←── 周期的に送信 ──  │  Peripheral   │
│   (Scanner)   │      Advertising     │   (Server)    │
│               │      Packets         │               │
│   "誰かいる?" │                      │  "私はここ!"   │
└───────────────┘                     └───────────────┘

アドバタイズパケットに含まれる情報:
- デバイス名
- サービスUUID（どんなサービスを提供しているか）
- 製造者データ
- 送信電力レベル
```

### 設定項目

**Advertisement実装:**

```python
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


class Advertisement(dbus.service.Object):
    """
    BLEアドバタイズメント
    org.bluez.LEAdvertisement1 を実装
    """
    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index, advertising_type):
        self.path = f"{self.PATH_BASE}{index}"
        self.bus = bus
        self.ad_type = advertising_type  # "peripheral" or "broadcast"
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = None
        self.include_tx_power = False
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = {
            LE_ADVERTISEMENT_IFACE: {
                "Type": self.ad_type
            }
        }
        if self.service_uuids is not None:
            properties[LE_ADVERTISEMENT_IFACE]["ServiceUUIDs"] = dbus.Array(
                self.service_uuids, signature="s"
            )
        if self.local_name is not None:
            properties[LE_ADVERTISEMENT_IFACE]["LocalName"] = dbus.String(
                self.local_name
            )
        if self.include_tx_power:
            properties[LE_ADVERTISEMENT_IFACE]["Includes"] = dbus.Array(
                ["tx-power"], signature="s"
            )
        if self.manufacturer_data is not None:
            properties[LE_ADVERTISEMENT_IFACE]["ManufacturerData"] = dbus.Dictionary(
                self.manufacturer_data, signature="qv"
            )
        if self.service_data is not None:
            properties[LE_ADVERTISEMENT_IFACE]["ServiceData"] = dbus.Dictionary(
                self.service_data, signature="sv"
            )
        return properties

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(
                "org.bluez.Error.InvalidArguments",
                "Invalid interface"
            )
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        """アドバタイズ解放時に呼ばれる"""
        print(f"Advertisement {self.path} Released")


class KeyServiceAdvertisement(Advertisement):
    """キーサービス用アドバタイズメント"""
    def __init__(self, bus, index):
        super().__init__(bus, index, "peripheral")
        self.local_name = "RasPi-KeyServer"
        self.service_uuids = [KEY_SERVICE_UUID]
        self.include_tx_power = True
```

**アドバタイズ設定項目一覧:**

| プロパティ | 型 | 説明 |
|------------|-----|------|
| `Type` | string | "peripheral" / "broadcast" |
| `ServiceUUIDs` | array[string] | 公開するサービスUUID |
| `LocalName` | string | デバイス名 |
| `ManufacturerData` | dict | 製造者固有データ |
| `ServiceData` | dict | サービス固有データ |
| `Includes` | array[string] | 追加情報 ("tx-power", "appearance") |
| `Appearance` | uint16 | デバイス外観コード |
| `Duration` | uint16 | アドバタイズ期間（秒） |
| `Timeout` | uint16 | タイムアウト（秒） |

---

## 4. 実装の流れ

### 完全なメインスクリプト

```python
#!/usr/bin/env python3
"""
main.py - BLE GATTサーバー起動スクリプト
"""

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

# 上記で定義したクラスをインポート
# from gatt_server import Application, KeyService
# from advertisement import KeyServiceAdvertisement

BLUEZ_SERVICE_NAME = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"


def find_adapter(bus):
    """BlueZアダプターを検索"""
    remote_om = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, "/"),
        "org.freedesktop.DBus.ObjectManager"
    )
    objects = remote_om.GetManagedObjects()
    
    for path, interfaces in objects.items():
        if GATT_MANAGER_IFACE in interfaces:
            return path
    return None


def register_app_callback():
    """GATTアプリケーション登録成功コールバック"""
    print("GATTアプリケーション登録成功")


def register_app_error_callback(error):
    """GATTアプリケーション登録エラーコールバック"""
    print(f"GATTアプリケーション登録失敗: {error}")
    mainloop.quit()


def register_ad_callback():
    """アドバタイズ登録成功コールバック"""
    print("アドバタイズ登録成功")


def register_ad_error_callback(error):
    """アドバタイズ登録エラーコールバック"""
    print(f"アドバタイズ登録失敗: {error}")
    mainloop.quit()


def main():
    global mainloop

    # D-Busメインループの初期化
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    
    # アダプターの検索
    adapter_path = find_adapter(bus)
    if not adapter_path:
        print("BlueZアダプターが見つかりません")
        return

    print(f"使用アダプター: {adapter_path}")

    # アダプターの電源ON & Discoverable設定
    adapter_props = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        "org.freedesktop.DBus.Properties"
    )
    adapter_props.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
    adapter_props.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))

    # GATTマネージャーの取得
    gatt_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        GATT_MANAGER_IFACE
    )

    # アドバタイズマネージャーの取得
    ad_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter_path),
        LE_ADVERTISING_MANAGER_IFACE
    )

    # GATTアプリケーションの作成と登録
    app = Application(bus)
    app.add_service(KeyService(bus, 0))

    # GATTサービスの登録
    print("GATTアプリケーションを登録中...")
    gatt_manager.RegisterApplication(
        app.get_path(),
        {},
        reply_handler=register_app_callback,
        error_handler=register_app_error_callback
    )

    # アドバタイズの作成と登録
    advertisement = KeyServiceAdvertisement(bus, 0)
    
    print("アドバタイズを登録中...")
    ad_manager.RegisterAdvertisement(
        advertisement.get_path(),
        {},
        reply_handler=register_ad_callback,
        error_handler=register_ad_error_callback
    )

    # メインループの開始
    mainloop = GLib.MainLoop()
    print("BLE GATTサーバー起動中... (Ctrl+Cで終了)")
    
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print("\nシャットダウン中...")
    finally:
        # クリーンアップ
        try:
            ad_manager.UnregisterAdvertisement(advertisement.get_path())
            gatt_manager.UnregisterApplication(app.get_path())
        except:
            pass
        print("終了")


if __name__ == "__main__":
    main()
```

### 起動手順

```bash
# 1. Bluetoothサービスの確認
sudo systemctl status bluetooth

# 2. 実験モードの有効化（必要に応じて）
sudo nano /etc/bluetooth/main.conf
# [General] セクションに以下を追加:
# Experimental = true

# 3. Bluetoothサービスの再起動
sudo systemctl restart bluetooth

# 4. GATTサーバーの起動（root権限必要）
sudo python3 main.py
```

---

## 5. トラブルシューティング

### よくあるエラーと対処法

| エラー | 原因 | 対処法 |
|--------|------|--------|
| `org.bluez.Error.NotPermitted` | 権限不足 | `sudo`で実行、または適切なグループに追加 |
| `org.bluez.Error.AlreadyExists` | 重複登録 | 既存の登録を解除してから再登録 |
| `org.bluez.Error.InvalidArguments` | パラメータ不正 | UUID形式、フラグ値を確認 |
| `org.bluez.Error.NotReady` | アダプター未準備 | `Powered=True`を設定 |
| `org.bluez.Error.NotSupported` | 機能非対応 | BlueZバージョン確認、Experimental有効化 |
| `org.bluez.Error.Failed` | 汎用エラー | ログ確認、bluetoothctlでテスト |

### デバッグ方法

**1. BlueZのデバッグログ有効化:**
```bash
# BlueZをデバッグモードで起動
sudo systemctl stop bluetooth
sudo /usr/libexec/bluetooth/bluetoothd -n -d
```

**2. D-Busモニタリング:**
```bash
# D-Busメッセージの監視
sudo dbus-monitor --system "sender='org.bluez'"
```

**3. bluetoothctlでの確認:**
```bash
bluetoothctl
# power on
# discoverable on
# show             # アダプター情報
# devices          # 接続デバイス一覧
# menu gatt        # GATTメニュー
# list-attributes  # 登録済み属性一覧
```

**4. hcitoolでの確認:**
```bash
# アダプター状態確認
hciconfig hci0

# アドバタイズ状態確認
sudo hcitool -i hci0 cmd 0x08 0x000e
```

**5. Pythonデバッグコード:**
```python
import logging

# デバッグログの設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# D-Busメソッド呼び出しのラップ
def debug_dbus_call(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"D-Bus call: {func.__name__}, args: {args}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"D-Bus result: {result}")
            return result
        except dbus.exceptions.DBusException as e:
            logger.error(f"D-Bus error: {e}")
            raise
    return wrapper
```

---

## 6. ベストプラクティス

### UUID設計

```python
"""
UUID設計のガイドライン

1. カスタムUUIDの生成
   - uuidgen コマンドまたは uuid.uuid4() で生成
   - プロジェクト固有のベースUUIDを決めて派生させる

2. 命名規則
   BASE_UUID = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
   SERVICE_UUID = BASE_UUID の一部を変更
   CHAR_UUID    = SERVICE_UUID の一部を変更
"""

import uuid

# ベースUUID（プロジェクト固有）
PROJECT_BASE = "12345678-0000-1000-8000-00805f9b34fb"

# サービスとキャラクタリスティックのUUID生成
def generate_uuid(base, service_id, char_id=None):
    """
    base:       ベースUUID文字列
    service_id: サービス識別子 (0x0001 - 0xFFFF)
    char_id:    キャラクタリスティック識別子 (オプション)
    """
    parts = base.split("-")
    parts[0] = f"{service_id:08x}"
    if char_id:
        parts[1] = f"{char_id:04x}"
    return "-".join(parts)

# 使用例
KEY_SERVICE_UUID = generate_uuid(PROJECT_BASE, 0x0001)
KEY_WRITE_CHAR_UUID = generate_uuid(PROJECT_BASE, 0x0001, 0x0001)
KEY_NOTIFY_CHAR_UUID = generate_uuid(PROJECT_BASE, 0x0001, 0x0002)
```

### エラーハンドリング

```python
import dbus.exceptions

class GattServerError(Exception):
    """GATTサーバーカスタム例外"""
    pass


class RobustCharacteristic(Characteristic):
    """堅牢なエラーハンドリングを持つCharacteristic"""
    
    def WriteValue(self, value, options):
        try:
            # 値の検証
            if not value:
                raise dbus.exceptions.DBusException(
                    "org.bluez.Error.InvalidValueLength",
                    "Empty value not allowed"
                )
            
            # サイズ制限（例: 512バイト）
            if len(value) > 512:
                raise dbus.exceptions.DBusException(
                    "org.bluez.Error.InvalidValueLength",
                    "Value too long"
                )
            
            # データ処理
            self.value = value
            self.process_value(bytes(value))
            
        except dbus.exceptions.DBusException:
            raise
        except Exception as e:
            print(f"WriteValue内部エラー: {e}")
            raise dbus.exceptions.DBusException(
                "org.bluez.Error.Failed",
                str(e)
            )

    def process_value(self, data):
        """サブクラスでオーバーライド"""
        pass


# 標準BlueZ GATTエラーコード
GATT_ERRORS = {
    "InvalidOffset": "org.bluez.Error.InvalidOffset",
    "InvalidValueLength": "org.bluez.Error.InvalidValueLength", 
    "NotAuthorized": "org.bluez.Error.NotAuthorized",
    "NotPermitted": "org.bluez.Error.NotPermitted",
    "NotSupported": "org.bluez.Error.NotSupported",
    "Failed": "org.bluez.Error.Failed",
}
```

### 再接続ロジック

```python
import time
from gi.repository import GLib


class ConnectionManager:
    """接続管理とリトライロジック"""
    
    def __init__(self, bus, adapter_path):
        self.bus = bus
        self.adapter_path = adapter_path
        self.app = None
        self.advertisement = None
        self.is_registered = False
        self.retry_count = 0
        self.max_retries = 5
        self.retry_delay = 2  # 秒

    def register_with_retry(self):
        """リトライ付き登録"""
        while self.retry_count < self.max_retries:
            try:
                self._register()
                self.is_registered = True
                self.retry_count = 0
                return True
            except dbus.exceptions.DBusException as e:
                self.retry_count += 1
                print(f"登録失敗 ({self.retry_count}/{self.max_retries}): {e}")
                if self.retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
        return False

    def _register(self):
        """実際の登録処理"""
        gatt_manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, self.adapter_path),
            GATT_MANAGER_IFACE
        )
        
        # 同期的に登録（エラーを即座に捕捉）
        gatt_manager.RegisterApplication(
            self.app.get_path(),
            dbus.Dictionary({}, signature="sv")
        )

    def setup_reconnect_handler(self):
        """切断時の再接続ハンドラー設定"""
        self.bus.add_signal_receiver(
            self._on_properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path_keyword="path"
        )

    def _on_properties_changed(self, interface, changed, invalidated, path):
        """プロパティ変更の監視"""
        if interface == "org.bluez.Device1":
            if "Connected" in changed:
                connected = changed["Connected"]
                print(f"デバイス接続状態変更: {path} -> {connected}")
                if not connected:
                    self._handle_disconnect(path)

    def _handle_disconnect(self, device_path):
        """切断処理"""
        print(f"切断検出: {device_path}")
        # 必要に応じてクリーンアップ
        # アドバタイズを再開して新しい接続を待機
        GLib.timeout_add_seconds(1, self._restart_advertising)

    def _restart_advertising(self):
        """アドバタイズ再開"""
        print("アドバタイズを再開中...")
        # 再登録処理
        return False  # GLibタイマーを停止
```

### Notify実装の完全例

```python
class NotifyCharacteristic(Characteristic):
    """Notify対応キャラクタリスティック"""
    
    def __init__(self, bus, index, service):
        super().__init__(
            bus, index,
            "12345678-0001-1000-8000-00805f9b34fb",
            ["notify", "read"],
            service
        )
        self.notifying = False
        self.notify_timer = None

    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        print("Notify開始")
        # 定期的なNotify送信（例: 1秒ごと）
        self.notify_timer = GLib.timeout_add(1000, self._send_notification)

    def StopNotify(self):
        if not self.notifying:
            return
        self.notifying = False
        print("Notify停止")
        if self.notify_timer:
            GLib.source_remove(self.notify_timer)
            self.notify_timer = None

    def _send_notification(self):
        """通知を送信"""
        if not self.notifying:
            return False
        
        # 値を更新
        self.value = dbus.Array([0x01, 0x02, 0x03], signature="y")
        
        # PropertiesChangedシグナルを送信
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {"Value": self.value},
            []
        )
        
        return True  # 継続

    def set_value_and_notify(self, new_value):
        """値を設定してNotify送信"""
        self.value = dbus.Array(new_value, signature="y")
        if self.notifying:
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": self.value},
                []
            )
```

---

## まとめ

| 項目 | ポイント |
|------|----------|
| **BlueZ** | LinuxのBluetooth標準スタック、D-Bus経由で操作 |
| **GATTサーバー** | Application → Service → Characteristic の階層構造 |
| **Advertisement** | 接続前のデバイス発見に必須、サービスUUIDを公開 |
| **実装** | dbus-python + PyGObjectでD-Busオブジェクトを定義 |
| **デバッグ** | bluetoothctl, dbus-monitor, BlueZデバッグモード |
| **エラー処理** | D-Bus例外を適切に処理、リトライロジックを実装 |

---

## 参考リンク

- [BlueZ公式ドキュメント](http://www.bluez.org/)
- [BlueZ D-Bus API (git)](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc)
- [BlueZ example-gatt-server.py](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/test/example-gatt-server)
- [Raspberry Pi Bluetooth設定](https://www.raspberrypi.org/documentation/configuration/bluetooth.md)
