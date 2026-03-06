# BLE Sender 再接続ロジック バグ修正

## 概要

`BleClient` の再接続ロジックに存在する4つのバグを修正する。
再接続が一度も成功しない原因となりうる致命的な問題を含む。

## 対象バグ

| # | 重要度 | 概要 |
|---|--------|------|
| 1 | 致命的 | 明示的 `disconnect()` がゾンビ再接続タスクを生む |
| 2 | 致命的 | `_reconnect_loop` 中のステータス不整合（RECONNECTING→DISCONNECTED） |
| 3 | 高 | `_on_disconnect` に例外処理がなく、再接続が開始されない可能性 |
| 4 | 高 | `_reconnect_loop` に例外処理がなく、ループがサイレントに死ぬ |

## 変更対象ファイル

| ファイル | 変更概要 |
|----------|----------|
| `src/ble_sender/ble_client.py` | 4つのバグ修正（`__init__`, `disconnect`, `_on_disconnect`, `_reconnect_loop`） |
| `tests/test_ble_client.py` | 新規テスト10件追加 |

## Phase1: 設計

- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査
- [x] [Phase1] 修正方針の設計

## Phase2: 実装（コア）

### Bug 1: `_intentional_disconnect` フラグ追加

`disconnect()` が bleak の `disconnected_callback` を発火させても再接続が始まらないようにする。

- [x] [Phase2] `__init__` に `self._intentional_disconnect: bool = False` 追加
- [x] [Phase2] `disconnect()` 冒頭で `self._intentional_disconnect = True` を設定
- [x] [Phase2] `disconnect()` 末尾で `self._intentional_disconnect = False` をフォールバックリセット
- [x] [Phase2] `_on_disconnect()` でフラグチェック — True なら再接続スキップし DISCONNECTED に遷移

変更箇所:
```python
# __init__ に追加
self._intentional_disconnect: bool = False

# disconnect() 冒頭に追加
self._intentional_disconnect = True

# disconnect() 末尾に追加（フォールバック）
self._intentional_disconnect = False

# _on_disconnect() にガード追加
if self._intentional_disconnect:
    self._intentional_disconnect = False
    self._set_status(STATUS_DISCONNECTED)
    return
```

### Bug 3: `_on_disconnect` 例外ハンドリング

Bug 1 のフラグチェックと合わせて `_on_disconnect` 全体を try/except で囲む。

- [x] [Phase2] `_on_disconnect()` 全体を `try/except Exception` で囲む
- [x] [Phase2] except 節で `logger.exception()` + `_set_status(STATUS_DISCONNECTED)`

### Bug 2 + Bug 4: `_reconnect_loop` 修正

Bug 2（ステータス復元）と Bug 4（例外ハンドリング）は同じメソッドなので同時に修正。

- [x] [Phase2] `_reconnect_loop()` の while ループを `try/except` で囲む
- [x] [Phase2] `asyncio.CancelledError` を catch して re-raise
- [x] [Phase2] 一般 `Exception` を catch して `logger.exception()` + `STATUS_DISCONNECTED`
- [x] [Phase2] `connect()` 失敗後に `self._set_status(STATUS_RECONNECTING)` を追加

## Phase3: 実装（結合）

- [x] [Phase3] 4つのバグ修正が相互に干渉しないことを確認（`_on_disconnect` 内で Bug1 ガード → Bug3 例外処理の順序）

## Phase4: テスト

### Bug 1 テスト
- [ ] [Phase4] `test_disconnect_sets_intentional_flag` — disconnect 中にフラグが True であることを検証
- [ ] [Phase4] `test_on_disconnect_skips_reconnect_when_intentional` — フラグ True 時に再接続タスクが作られないことを検証
- [ ] [Phase4] `test_on_disconnect_starts_reconnect_when_not_intentional` — フラグ False 時に再接続が開始されることを検証
- [ ] [Phase4] `test_intentional_disconnect_flag_reset_after_disconnect` — disconnect 後にフラグがリセットされることを検証

### Bug 2 テスト
- [ ] [Phase4] `test_reconnect_loop_restores_reconnecting_status` — connect 失敗後にステータスが RECONNECTING に戻ることを検証

### Bug 3 テスト
- [ ] [Phase4] `test_on_disconnect_handles_get_running_loop_error` — get_running_loop 例外時にクラッシュしないことを検証
- [ ] [Phase4] `test_on_disconnect_handles_create_task_error` — create_task 例外時にクラッシュしないことを検証

### Bug 4 テスト
- [ ] [Phase4] `test_reconnect_loop_handles_unexpected_exception` — 予期せぬ例外でクラッシュしないことを検証
- [ ] [Phase4] `test_reconnect_loop_reraises_cancelled_error` — CancelledError が re-raise されることを検証

### 既存テスト更新
- [ ] [Phase4] `test_initialization` に `_intentional_disconnect` のデフォルト値チェック追加
- [ ] [Phase4] 全テスト実行・パス確認

## Phase5: 仕上げ

- [ ] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順等）
- [ ] [Phase5] 動作確認
