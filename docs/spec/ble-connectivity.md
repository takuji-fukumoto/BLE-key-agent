# BLE接続性向上

## 概要

Mac⇔Pi/Unihiker間のBLE接続信頼性を向上させるための改善。
Service UUIDベースのスキャンフィルタ、接続リトライ、Advertising UUID明示の3点を実装。

## 重要事項

### macOS CoreBluetoothとService UUIDフィルタ

macOSのCoreBluetooth（bleakバックエンド）はMACアドレスではなくUUIDでデバイスを識別する。
`BleakScanner.discover(service_uuids=[...])`を使うとOSレベルでフィルタが効き、
デバイス発見率が大幅に向上する。デバイス名マッチよりも確実。

Peripheral側が`BlessAdvertisementData(service_uuids=[...])`でService UUIDを
Advertisingパケットに含めていないと、Central側のUUIDフィルタが機能しない。
Mac側・Pi側は必ずセットで対応する必要がある。

### find_device_by_filter vs find_device_by_address

`BleakScanner.find_device_by_address`はmacOSでは信頼性が低い（CoreBluetoothが
MACアドレスを直接公開しないため）。`find_device_by_filter`に`service_uuids`ヒントを
付けて使う方が安定する。

```python
device = await BleakScanner.find_device_by_filter(
    filterfunc=lambda d, adv: d.address == address,
    timeout=10.0,
    service_uuids=[KEY_SERVICE_UUID],
)
```

### 接続リトライと再接続の関係

2つのリトライ層がある:

1. **`connect()`のリトライ**: 1回の接続試行 = 最大3回の`_connect_once()`（1秒間隔）
   - BLEの一時的な接続失敗に対応
   - ユーザーが明示的に呼ぶ`connect()`に内蔵

2. **`_reconnect_loop()`の再接続**: 接続断後の自動再接続 = `connect()`を指数バックオフで繰り返し
   - 1ラウンド = 3回の高速リトライ → バックオフ待機 → 3回の高速リトライ → ...
   - バックオフ: 1s → 2s → 4s → ... → max 60s

### bless Advertising Interval

bless PR #111でデフォルトが100msに変更済み。明示的な設定は不要。
詳細は`reports/bless_advertising_interval.md`を参照。

### テストでのblessモック

blessはPi専用依存のため、テスト時は`sys.modules.setdefault()`でモックする。
`bless.backends.advertisement`のサブモジュールも個別にモックが必要。

```python
_bless_mock = MagicMock()
_adv_mock = MagicMock()
sys.modules.setdefault("bless", _bless_mock)
sys.modules.setdefault("bless.backends", MagicMock())
sys.modules.setdefault("bless.backends.advertisement", _adv_mock)
```

モジュールレベルモックは複数テストで共有されるため、
テスト内で`reset_mock()`を呼んでクロス汚染を防ぐ必要がある。

## 関連ファイル

- `src/mac_agent/ble_client.py` - UUIDフィルタ、リトライ、find_device_by_filter
- `src/mac_agent/api_types.py` - connect_max_attempts, connect_retry_delay設定
- `src/mac_agent/agent.py` - 設定パラメータの受け渡し
- `src/raspi_receiver/lib/gatt_server.py` - BlessAdvertisementDataでUUID明示
- `tests/test_ble_client.py` - リトライ・フィルタテスト
- `tests/test_gatt_server.py` - AdvertisementDataテスト
