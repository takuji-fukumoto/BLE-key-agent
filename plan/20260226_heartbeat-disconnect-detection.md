# ハートビートによる切断検知の実装

## 概要

Mac側が定期的にハートビートメッセージをBLE送信し、Pi側が受信タイムアウトで切断を検知する仕組みを追加する。
これにより、Mac側の正常終了・異常終了どちらの場合もPi側LCDが「Disconnected」状態に正しく遷移する。

## 背景・課題

- 現在のPi側は「最初のGATT Write受信」で接続を検知しているが、切断検知ロジックがない
- `KeyReceiver.on_disconnect` コールバックは登録可能だが、一度も呼ばれない
- Mac側が終了してもPi側LCDは「Connected」表示のまま固まる

## 設計方針

- **プロトコル拡張**: 既存の `KeyEvent` JSONフォーマットに新しい `key_type` として `"h"` (heartbeat) を追加
- **Mac側**: BLE接続中にキー入力がなくても一定間隔でheartbeatを送信
- **Pi側**: 最後の受信（key/heartbeat問わず）からタイムアウト超過で `on_disconnect` を発火
- heartbeatはGATT Writeの既存パスをそのまま流用するため、新しいCharacteristic等は不要

## 定数設計

| 定数 | 値 | 場所 | 説明 |
|------|------|------|------|
| `HEARTBEAT_INTERVAL_SEC` | 3.0 | `mac_agent/main.py` | heartbeat送信間隔 |
| `DISCONNECT_TIMEOUT_SEC` | 10.0 | `raspi_receiver/lib/key_receiver.py` | 切断判定タイムアウト |

- タイムアウトは `HEARTBEAT_INTERVAL_SEC × 3` 以上にし、BLE通信のジッターを吸収する
- heartbeat間隔が短すぎるとBLE帯域を消費するため3秒を基本とする

## 変更対象ファイル

### 1. `src/common/protocol.py`（変更）

- `KeyType` enumに `HEARTBEAT = "h"` を追加
- heartbeat用のファクトリメソッドを `KeyEvent` に追加

```python
class KeyType(str, Enum):
    CHAR = "c"
    SPECIAL = "s"
    MODIFIER = "m"
    HEARTBEAT = "h"  # 追加

class KeyEvent:
    # ... 既存 ...

    @classmethod
    def heartbeat(cls) -> KeyEvent:
        """Create a heartbeat event."""
        return cls(key_type=KeyType.HEARTBEAT, value="", press=False)
```

### 2. `src/mac_agent/main.py`（変更）

- `MacAgent` に heartbeat送信タスクを追加
- `_forward_loop` と並行して `_heartbeat_loop` を実行
- キー送信時にもタイマーをリセットし、アクティブ入力中は無駄なheartbeatを抑制

```python
HEARTBEAT_INTERVAL_SEC = 3.0

class MacAgent:
    def __init__(self, ...):
        # ... 既存 ...
        self._last_send_time: float = 0.0  # 追加

    async def run(self):
        # ... 既存のtry内 ...
        # _forward_loop と _heartbeat_loop を並行実行
        await asyncio.gather(
            self._forward_loop(),
            self._heartbeat_loop(),
        )

    async def _heartbeat_loop(self):
        """Send periodic heartbeat while connected."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
            if self._shutdown_event.is_set():
                break
            elapsed = time.monotonic() - self._last_send_time
            if elapsed >= HEARTBEAT_INTERVAL_SEC:
                if self._ble_client.status == STATUS_CONNECTED:
                    await self._ble_client.send_key(KeyEvent.heartbeat())
                    self._last_send_time = time.monotonic()

    async def _forward_loop(self):
        # ... 既存 ...
        # send_key成功後に self._last_send_time = time.monotonic() を追加
```

### 3. `src/raspi_receiver/lib/key_receiver.py`（変更）

- 最終受信時刻 `_last_receive_time` を記録
- タイムアウト監視タスク `_timeout_monitor` を追加
- heartbeatイベントはコールバックに伝播せず、受信時刻更新のみ

```python
DISCONNECT_TIMEOUT_SEC = 10.0

class KeyReceiver:
    def __init__(self, ...):
        # ... 既存 ...
        self._last_receive_time: float = 0.0
        self._timeout_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self):
        self._loop = asyncio.get_running_loop()
        await self._server.start()
        # タイムアウト監視タスクを起動
        self._timeout_task = asyncio.create_task(self._timeout_monitor())

    async def stop(self):
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            # ...
        await self._server.stop()

    def _handle_write(self, data: bytes):
        self._last_receive_time = time.monotonic()  # 追加

        # 接続検知（既存ロジック）
        if not self._connected:
            self._connected = True
            # on_connect 発火...

        event = KeyEvent.deserialize(data)

        # heartbeatはアプリに伝播しない
        if event.key_type == KeyType.HEARTBEAT:
            logger.debug("Heartbeat received")
            return

        # 既存のkey_press/key_release処理...

    async def _timeout_monitor(self):
        """Monitor for receive timeout and fire on_disconnect."""
        while True:
            await asyncio.sleep(1.0)  # 1秒ごとにチェック
            if not self._connected:
                continue
            elapsed = time.monotonic() - self._last_receive_time
            if elapsed > DISCONNECT_TIMEOUT_SEC:
                self._connected = False
                logger.info("Client disconnected (timeout: %.1fs)", elapsed)
                if self.on_disconnect is not None:
                    try:
                        self.on_disconnect(ConnectionEvent(connected=False))
                    except Exception:
                        logger.exception("Error in on_disconnect callback")
```

### 4. `src/raspi_receiver/apps/lcd_display/main.py`（変更なし）

- 既に `_on_disconnect` → `DisplayConnectionEvent(connected=False)` → 画面更新の配線が完成している
- `KeyReceiver` が `on_disconnect` を正しく呼ぶようになれば、LCD側の変更は不要

### 5. テスト

#### `tests/test_protocol.py`（変更）
- `KeyType.HEARTBEAT` のシリアライズ/デシリアライズテスト追加
- `KeyEvent.heartbeat()` ファクトリメソッドのテスト追加

#### `tests/test_key_receiver.py`（変更）
- heartbeat受信時にon_key_pressが呼ばれないことのテスト
- タイムアウト切断検知のテスト（`_last_receive_time` を操作してタイムアウト発火を確認）
- 再接続シナリオ: 切断後に再度writeを受信すると `on_connect` が再発火することのテスト

## 実装順序

- [ ] [Step 1] `common/protocol.py`: `KeyType.HEARTBEAT` + `KeyEvent.heartbeat()` 追加
- [ ] [Step 2] `tests/test_protocol.py`: heartbeatのテスト追加 → テスト通過確認
- [ ] [Step 3] `raspi_receiver/lib/key_receiver.py`: タイムアウト監視 + heartbeatフィルタ追加
- [ ] [Step 4] `tests/test_key_receiver.py`: タイムアウト切断・heartbeatフィルタのテスト追加 → テスト通過確認
- [ ] [Step 5] `mac_agent/main.py`: heartbeat送信タスク追加
- [ ] [Step 6] 結合動作確認（Mac起動→接続→キー送信→Mac終了→Pi側が10秒後にDisconnected表示）

## プロトコル仕様への影響

`docs/spec-ble-protocol.md` §3.3 のフィールド説明テーブルに追記が必要：

| `t` | 説明 |
|------|------|
| `"h"` | ハートビート（接続維持確認用、Piはアプリに伝播しない） |

heartbeatのJSONペイロード例：
```json
{"t":"h","v":"","p":false}
```
→ 約24バイト。MTU内に収まる。
