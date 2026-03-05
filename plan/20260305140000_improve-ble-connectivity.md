# BLE接続性向上

## 概要

BLE接続の信頼性を向上させるため、優先度の高い3つの改善を実装する:

1. **Service UUIDベースのスキャン**: `BleakScanner`にService UUIDフィルタを追加し、デバイス発見率を向上
2. **接続リトライ**: `connect()`にリトライロジック（デフォルト3回）を追加し、接続成功率を向上
3. **AdvertisingへのService UUID明示**: Pi/Unihiker側の`BlessAdvertisementData`にService UUIDを含め、スキャンフィルタが確実に機能するようにする

**補足**: Advertising Interval短縮は不要（bless PR #111でデフォルト100msに変更済み。`reports/bless_advertising_interval.md`参照）

## 変更対象ファイル

| ファイル | 変更種別 | 変更概要 |
|----------|----------|----------|
| `src/mac_agent/api_types.py` | 修正 | `AgentConfig`に`connect_max_attempts`, `connect_retry_delay`追加 |
| `src/mac_agent/ble_client.py` | 修正 | スキャンのUUIDフィルタ、接続リトライ、`find_device_by_filter`移行 |
| `src/mac_agent/agent.py` | 修正 | 新設定パラメータの`BleSender`への受け渡し |
| `src/raspi_receiver/lib/gatt_server.py` | 修正 | `BlessAdvertisementData`でService UUID明示 |
| `tests/test_ble_client.py` | 修正 | UUIDフィルタ・リトライ・filter関数のテスト追加、既存テスト更新 |
| `tests/test_gatt_server.py` | 修正 | AdvertisementDataのテスト追加 |

## Phase1: 設計

- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査（`ble_client.py`のscan/connect、`gatt_server.py`のstart）
- [x] [Phase1] bleakのService UUIDフィルタAPI確認（`BleakScanner.discover(service_uuids=...)`, `find_device_by_filter`）
- [x] [Phase1] blessのAdvertisementData API確認（`BlessAdvertisementData`、import path）
- [x] [Phase1] 既存テストパターン確認（bleak/blessモック手法）

## Phase2: 実装（コア）

- [ ] [Phase2] `api_types.py`: `AgentConfig`に`connect_max_attempts: int = 3`と`connect_retry_delay: float = 1.0`を追加
- [ ] [Phase2] `ble_client.py`: `BleClient.__init__`に`connect_max_attempts`, `connect_retry_delay`パラメータ追加
- [ ] [Phase2] `ble_client.py`: `scan()`に`service_uuids=[KEY_SERVICE_UUID]`フィルタ追加
- [ ] [Phase2] `ble_client.py`: 既存`connect()`のロジックを`_connect_once()`に抽出
- [ ] [Phase2] `ble_client.py`: `_connect_once()`で`find_device_by_address`→`find_device_by_filter`に変更（`service_uuids`ヒント付き）
- [ ] [Phase2] `ble_client.py`: `connect()`にリトライループ実装（max_attempts回、retry_delay間隔）
- [ ] [Phase2] `gatt_server.py`: `start()`で`BlessAdvertisementData(local_name=..., service_uuids=[KEY_SERVICE_UUID])`を作成し`server.start(advertisement_data=...)`に渡す

## Phase3: 実装（結合）

- [ ] [Phase3] `agent.py`: `KeyBleAgent.__init__`で`connect_max_attempts`, `connect_retry_delay`を`BleSender`に渡す

## Phase4: テスト

- [ ] [Phase4] `test_ble_client.py`: `test_scan_uses_service_uuid_filter` — `discover()`が`service_uuids`付きで呼ばれることを検証
- [ ] [Phase4] `test_ble_client.py`: `test_connect_retries_on_failure` — 2回失敗→3回目成功のリトライ動作を検証
- [ ] [Phase4] `test_ble_client.py`: `test_connect_all_retries_exhausted` — 全試行失敗時にDISCONNECTED&Falseを検証
- [ ] [Phase4] `test_ble_client.py`: `test_connect_retry_delay_applied` — リトライ間の`asyncio.sleep`呼び出しを検証
- [ ] [Phase4] `test_ble_client.py`: `test_connect_first_attempt_succeeds_no_retry` — 初回成功時にリトライなしを検証
- [ ] [Phase4] `test_ble_client.py`: `test_connect_uses_find_device_by_filter` — `find_device_by_filter`が`service_uuids`付きで呼ばれることを検証
- [ ] [Phase4] `test_ble_client.py`: 既存`test_connect_success`を`find_device_by_filter`モックに更新
- [ ] [Phase4] `test_ble_client.py`: 既存`test_connect_device_not_found`を`find_device_by_filter`モックに更新
- [ ] [Phase4] `test_ble_client.py`: 既存`test_connect_missing_key_service`を`find_device_by_filter`モックに更新
- [ ] [Phase4] `test_gatt_server.py`: `test_start_passes_advertisement_data` — `server.start()`が`advertisement_data`付きで呼ばれることを検証
- [ ] [Phase4] テスト実行・全パス確認

## Phase5: 仕上げ

- [ ] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順等）
- [ ] [Phase5] 動作確認

## 設計詳細

### 1. Service UUIDスキャンフィルタ（Mac側）

**`scan()`の変更**:
```python
# Before
devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

# After
devices = await BleakScanner.discover(
    timeout=timeout, return_adv=True, service_uuids=[KEY_SERVICE_UUID]
)
```

### 2. 接続リトライ（Mac側）

**`connect()` → `_connect_once()` 抽出 + リトライループ**:
```python
async def connect(self, address: str) -> bool:
    if self._client is not None:
        await self.disconnect()
    self._set_status(STATUS_CONNECTING)
    self._last_address = address

    for attempt in range(1, self._connect_max_attempts + 1):
        logger.info("Connection attempt %d/%d to %s", attempt, self._connect_max_attempts, address)
        success = await self._connect_once(address)
        if success:
            return True
        if attempt < self._connect_max_attempts:
            await asyncio.sleep(self._connect_retry_delay)

    self._set_status(STATUS_DISCONNECTED)
    return False

async def _connect_once(self, address: str) -> bool:
    # 既存connect()の中身を移動（find_device_by_filter使用）
    # ステータス変更はconnect()側で管理するため_connect_once内では行わない
```

**`_connect_once()`内で`find_device_by_filter`使用**:
```python
device = await BleakScanner.find_device_by_filter(
    filterfunc=lambda d, adv: d.address == address,
    timeout=10.0,
    service_uuids=[KEY_SERVICE_UUID],
)
```

### 3. AdvertisingへのService UUID明示（Pi側）

```python
from bless.backends.advertisement import BlessAdvertisementData

adv_data = BlessAdvertisementData(
    local_name=self._device_name,
    service_uuids=[KEY_SERVICE_UUID],
)
await self._server.start(advertisement_data=adv_data)
```

### リトライと再接続の関係

- `connect()`: 1回の接続試行 = 最大3回の`_connect_once()`（1秒間隔）
- `_reconnect_loop()`: 接続断後の再接続 = `connect()`を指数バックオフで繰り返し
- つまり再接続1ラウンド = 3回の高速リトライ → バックオフ待機 → 3回の高速リトライ → ...
