#!/usr/bin/env python3
"""
Raspberry Pi側 (Peripheral): BLE GATTサーバー PoC

BlueZ D-Bus APIを使用してGATTサーバーを構築し、
Mac (Central) からのキー入力をBLE経由で受信する。

使用方法:
    sudo python3 peripheral_raspi.py

前提条件:
    - Raspberry Pi Zero 2W + Raspberry Pi OS
    - BlueZがインストール済み
    - sudo権限で実行

セットアップ:
    sudo apt update
    sudo apt install -y python3-dbus python3-gi bluez
    sudo systemctl enable bluetooth
    sudo systemctl start bluetooth
"""

import signal
import sys

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

# common.pyと同じUUID値をハードコード（ラズパイではcommon.pyを直接importできない場合に備える）
# python3 -c "from common import *; print(KEY_SERVICE_UUID, KEY_CHAR_UUID)" で確認可能
import uuid

_PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")
KEY_SERVICE_UUID = str(uuid.uuid5(_PROJECT_NAMESPACE, "key-service"))
KEY_CHAR_UUID = str(uuid.uuid5(_PROJECT_NAMESPACE, "key-char"))
DEVICE_NAME = "RasPi-KeyAgent"

# BlueZ D-Bus 定数
BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"


class Advertisement(dbus.service.Object):
    """BLE LEアドバタイズメント。

    Peripheralの存在をCentralに通知するためのアドバタイズパケットを定義する。
    """

    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = "peripheral"
        self.service_uuids = [KEY_SERVICE_UUID]
        self.local_name = DEVICE_NAME
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

    @dbus.service.method(
        DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}"
    )
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(
        LE_ADVERTISEMENT_IFACE, in_signature="", out_signature=""
    )
    def Release(self):
        print(f"[ADV] Released: {self.path}")


class Service(dbus.service.Object):
    """GATTサービス。

    関連するCharacteristicをグループ化し、UUIDで識別される機能単位を定義する。
    """

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

    @dbus.service.method(
        DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}"
    )
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[GATT_SERVICE_IFACE]


class KeyCharacteristic(dbus.service.Object):
    """キー受信用Characteristic。

    Mac (Central) からのWrite操作でキー情報を受信する。
    write / write-without-response の両方をサポート。
    """

    def __init__(self, bus, index, service):
        self.path = service.path + "/char" + str(index)
        self.bus = bus
        self.uuid = KEY_CHAR_UUID
        self.service = service
        self.flags = ["write", "write-without-response"]
        self.value = []
        self.write_count = 0
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

    @dbus.service.method(
        DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}"
    )
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException(
                "org.freedesktop.DBus.Error.InvalidArgs",
                f"Unknown interface: {interface}",
            )
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(
        GATT_CHRC_IFACE, in_signature="aya{sv}", out_signature=""
    )
    def WriteValue(self, value, options):
        """Centralからキーが書き込まれたときに呼ばれるコールバック。"""
        self.write_count += 1
        try:
            key_str = bytes(value).decode("utf-8")
            self.value = value
            print(f"  [{self.write_count:4d}] 受信: {key_str} ({len(value)} bytes)")
            self.handle_key(key_str)
        except UnicodeDecodeError:
            hex_str = bytes(value).hex()
            print(f"  [{self.write_count:4d}] 受信 (raw): {hex_str}")

    def handle_key(self, key_str):
        """受信したキーに応じた処理。

        ここをカスタマイズしてGPIO制御やコマンド実行などを追加できる。
        """
        pass


class Application(dbus.service.Object):
    """GATTアプリケーション。

    BlueZに登録するサービス群をまとめるコンテナ。
    GetManagedObjectsでBlueZに全サービス/Characteristicの情報を提供する。
    """

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


def find_adapter(bus):
    """BlueZのBLEアダプタを検索する。"""
    remote_om = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE
    )
    objects = remote_om.GetManagedObjects()

    for path, interfaces in objects.items():
        if GATT_MANAGER_IFACE in interfaces:
            return path

    return None


def main():
    # D-Busメインループの初期化
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # アダプタを検索
    adapter_path = find_adapter(bus)
    if not adapter_path:
        print("BLEアダプタが見つかりません")
        print("ヒント:")
        print("  - hciconfig でアダプタの状態を確認")
        print("  - sudo hciconfig hci0 up でアダプタを有効化")
        sys.exit(1)

    print(f"アダプタ: {adapter_path}")

    adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)

    # アダプタの電源をON
    adapter_props = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)
    adapter_props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))

    # マネージャーを取得
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
    ad_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    # GATTアプリケーションをセットアップ
    app = Application(bus)
    service = Service(bus, 0, KEY_SERVICE_UUID, True)
    key_char = KeyCharacteristic(bus, 0, service)
    service.add_characteristic(key_char)
    app.add_service(service)

    # アドバタイズをセットアップ
    adv = Advertisement(bus, 0)

    mainloop = GLib.MainLoop()

    # シグナルハンドラ（Ctrl+Cで安全に終了）
    def signal_handler(sig, frame):
        print("\n終了中...")
        mainloop.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

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
    print("BLE GATTサーバー起動")
    print(f"  デバイス名:     {DEVICE_NAME}")
    print(f"  Service UUID:   {KEY_SERVICE_UUID}")
    print(f"  Char UUID:      {KEY_CHAR_UUID}")
    print(f"  アダプタ:       {adapter_path}")
    print("=" * 50)
    print("Macからの接続を待機しています... (Ctrl+Cで終了)")
    print()

    mainloop.run()

    print("GATTサーバーを停止しました")


if __name__ == "__main__":
    main()
