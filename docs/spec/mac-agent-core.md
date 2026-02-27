# Mac Agent コア（BLE + キー監視）

## 概要

Mac側のコア機能。pynputによるキーボード入力監視（`KeyMonitor`）と、bleakによるBLE Central通信（`BleClient`）、それらを統合するCLIアプリ（`MacAgent`）で構成。

## 重要事項

### pynputのスレッド安全性

pynputのListenerは別スレッドで動作する。asyncio.Queueにイベントを渡すには`loop.call_soon_threadsafe()`が必須。直接`queue.put_nowait()`を呼ぶとスレッド安全性が保証されない。

```python
# pynputスレッド → asyncioイベントループへの橋渡しパターン
self._loop.call_soon_threadsafe(self._safe_put, event)

def _safe_put(self, event):
    try:
        self._queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # ドロップして非ブロッキングを保証
```

### bleakのlazy importパターン

`ble_client.py`ではbleakを関数内でlazy importしている（`from bleak import BleakScanner`）。これはPi側でもモジュールをimportできるようにするため。

テスト時の注意点:
- `patch('mac_agent.ble_client.BleakScanner')` は**動かない**（モジュールレベルに属性がない）
- `patch('bleak.BleakScanner')` を使うこと
- テストファイル冒頭で `sys.modules.setdefault("bleak", _bleak_mock)` でモジュールモックを登録

### Write Without Response

低レイテンシのため `response=False` でGATT Writeを実行する。bleakの `write_gatt_char()` の第3引数で制御。

```python
await client.write_gatt_char(KEY_CHAR_UUID, data, response=False)
```

### 自動再接続と指数バックオフ

BLE接続が切断された場合、`_on_disconnect` コールバックから `_reconnect_loop()` を非同期タスクとして起動。バックオフは 1s → 2s → 4s → ... → max 60s。明示的な `disconnect()` 呼び出し時はタスクをキャンセルする。

### ハートビートメカニズム

Mac側から3秒間隔でハートビートを送信。Pi側は10秒のタイムアウトで切断検知する（3倍マージン）。キーイベント送信が最近あった場合はハートビートをスキップして不要なBLEトラフィックを削減。

### キーイベントのレート制限

BLE Writeの間隔に最小5ms（`MIN_SEND_INTERVAL_S = 0.005`）を設け、Pi側のバッファオーバーフローを防止。

### macOSアクセシビリティ権限

pynputでグローバルキー監視するには、macOSのシステム設定でアクセシビリティ権限と入力監視権限が必要。`KeyMonitor.check_accessibility()` で簡易チェックを行うが、100%信頼はできない。

### コールバック例外分離

`on_status_change` コールバックで例外が発生してもBleClient内部状態は正常に更新される。try/exceptで分離し、ログ出力のみ行う。

## 関連ファイル

- `src/mac_agent/__init__.py` - パッケージ初期化
- `src/mac_agent/key_monitor.py` - pynputキー監視
- `src/mac_agent/ble_client.py` - bleak BLEクライアント
- `src/mac_agent/main.py` - CLIアプリ（MacAgent）
- `src/mac_agent/requirements.txt` - 依存パッケージ
- `tests/test_key_monitor.py` - KeyMonitorテスト
- `tests/test_ble_client.py` - BleClientテスト
