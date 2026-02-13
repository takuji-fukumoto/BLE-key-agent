# bless ライブラリのアドバタイズ間隔カスタマイズ調査

## 結論

blessライブラリは**アドバタイズ間隔を公開APIとして提供していない**。
内部的にはLinux (BlueZ) バックエンドで100msがハードコードされている。
macOSではCoreBluetooth自体が間隔制御を許可しない。

本プロジェクトではPi側のみ関係するため、Linux上での対応方法を中心にまとめる。

## 現状の仕様

### bless公開API (`BlessAdvertisementData`)

```python
@dataclass
class BlessAdvertisementData:
    local_name: Optional[str] = None
    service_uuids: Optional[List[str]] = None
    manufacturer_data: Optional[Dict[int, bytes]] = None
    service_data: Optional[Dict[str, bytes]] = None
    is_connectable: Optional[bool] = None
    is_discoverable: Optional[bool] = None
    tx_power: Optional[int] = None
```

`min_interval` / `max_interval` フィールドは存在しない。

### 内部実装 (BlueZ/D-Bus)

`bless/backends/bluezdbus/dbus/advertisement.py` の `BlueZLEAdvertisement`:

```python
class BlueZLEAdvertisement(ServiceInterface):
    def __init__(self, advertising_type, index, app):
        # hardcoded defaults
        self._min_interval: int = 100  # ms, range [20ms, 10,485s]
        self._max_interval: int = 100  # ms
        self._tx_power: int = 20
```

- PR #111 (2023年8月) で 1200ms → 100ms に変更された
- D-Busプロパティとして `MinInterval` / `MaxInterval` を公開するが、blessの上位APIには露出していない
- BlueZの `org.bluez.LEAdvertisement1` インターフェースの仕様に準拠

### BlueZの制約

- `MinInterval` / `MaxInterval` はBlueZで **Experimental** 扱い
- 有効化に必要な条件:
  - Kernel 5.11+
  - BlueZ 5.65+（5.63-5.64はバグあり）
  - `bluetoothd` を `--experimental` フラグ付きで起動
  - `/etc/bluetooth/main.conf` に `Experimental = true`
- **既知の問題**: BlueZ側で値が無視されるケースが報告されている ([bluez/bluez#833](https://github.com/bluez/bluez/issues/833))

### macOS (CoreBluetooth)

- `CBPeripheralManager.startAdvertising()` にアドバタイズ間隔のパラメータは存在しない
- Apple がOS側で制御しており、アプリからの設定不可
- 本プロジェクトではPi側のみblessを使うため**影響なし**

## カスタマイズ方法（Linux限定）

### 方法A: モンキーパッチ（推奨）

blessの内部メソッドをパッチして、RegisterAdvertisement呼び出し前にintervalを設定する。

```python
from bless.backends.bluezdbus.dbus.advertisement import BlueZLEAdvertisement

# BlueZLEAdvertisement のコンストラクタをパッチ
_original_init = BlueZLEAdvertisement.__init__

def _patched_init(self, advertising_type, index, app):
    _original_init(self, advertising_type, index, app)
    self._min_interval = 1000  # 1000ms に変更
    self._max_interval = 2000  # 2000ms に変更

BlueZLEAdvertisement.__init__ = _patched_init
```

- メリット: blessのフォーク不要、数行で実装可能
- デメリット: blessのバージョンアップで動かなくなる可能性

### 方法B: blessをフォーク

`BlessAdvertisementData` に `min_interval`, `max_interval` を追加し、
`BlueZGattApplication.start_advertising()` で値を伝播させる。

- メリット: 最もクリーンな実装
- デメリット: フォークのメンテナンスコスト

### 方法C: GATTServerクラスでラップ

本プロジェクトの `gatt_server.py` で方法Aのパッチを適用する:

```python
class GATTServer:
    def __init__(self, ..., adv_interval_ms: int = 100):
        self._adv_interval_ms = adv_interval_ms

    async def start(self) -> None:
        # bless import 後、interval をパッチ
        if self._adv_interval_ms != 100:
            self._patch_adv_interval(self._adv_interval_ms)
        # ... 既存の start 処理 ...

    @staticmethod
    def _patch_adv_interval(interval_ms: int) -> None:
        try:
            from bless.backends.bluezdbus.dbus.advertisement import BlueZLEAdvertisement
            _original_init = BlueZLEAdvertisement.__init__

            def _patched_init(self, advertising_type, index, app):
                _original_init(self, advertising_type, index, app)
                self._min_interval = interval_ms
                self._max_interval = interval_ms

            BlueZLEAdvertisement.__init__ = _patched_init
        except ImportError:
            pass  # macOS等では利用不可
```

## 推奨事項

### 現時点では対応不要

- blessのデフォルト 100ms は高速な検出に適しており、キーエージェントの用途に合っている
- 省電力のために間隔を広げたい場合（例: 1000-2000ms）は**方法C**で対応可能
- ただし BlueZ が Experimental として扱う機能に依存するため、**best-effort**（確実に効くとは限らない）

### 対応する場合のチェックリスト

1. Raspberry Pi の BlueZ バージョン確認（5.65+）
2. `bluetoothd` に `--experimental` フラグを追加（`setup_raspi.sh`）
3. `gatt_server.py` に `adv_interval_ms` パラメータを追加
4. モンキーパッチで内部値を差し替え
5. 実機で `btmon` や `hcitool lescan` で実際の間隔を確認

## 参考資料

- [kevincar/bless](https://github.com/kevincar/bless)
- [bless PR #111: Decrease default Advertisement interval](https://github.com/kevincar/bless/pull/111)
- [BlueZ Issue #833: Advertising interval min/max ignored](https://github.com/bluez/bluez/issues/833)
- [org.bluez.LEAdvertisement1 D-Bus API](https://manpages.opensuse.org/Tumbleweed/bluez/org.bluez.LEAdvertisement.5.en.html)
- [Apple CBPeripheralManager.startAdvertising](https://developer.apple.com/documentation/corebluetooth/cbperipheralmanager/1393252-startadvertising)
