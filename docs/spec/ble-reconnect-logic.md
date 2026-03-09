# BLE Sender 再接続ロジック

## 概要

Mac側BLEクライアント（`ble_client.py`）の再接続ロジックに関する設計判断と注意点。

## 重要事項

### macOS CoreBluetooth の disconnected_callback

macOSのCoreBluetoothは、明示的な`disconnect()`呼び出し時にも`didDisconnectPeripheral`を発火する。
bleakはこれを`disconnected_callback`に伝播するため、明示切断と予期せぬ切断を区別する仕組みが必要。

`_intentional_disconnect`フラグで制御する:
- `disconnect()`冒頭で`True`に設定
- `_on_disconnect()`でフラグを確認し、`True`なら再接続をスキップ
- `disconnect()`末尾で`False`にリセット（フォールバック）

### _on_disconnect コールバックの例外安全性

`_on_disconnect`はbleakライブラリから同期的に呼ばれるコールバック。
内部で`asyncio.get_running_loop()`や`loop.create_task()`を呼ぶため、
これらが例外を投げると再接続が開始されない。

全体を`try/except Exception`で囲み、失敗時は`STATUS_DISCONNECTED`にフォールバックする。

### _reconnect_loop のステータス管理

`_reconnect_loop`内で`connect()`を呼ぶと、`connect()`が内部でステータスを
`CONNECTING` → `CONNECTED`/`DISCONNECTED`に変更する。
`connect()`失敗後にループを継続する場合、ステータスを`RECONNECTING`に復元しないと
UIに不正確な状態が表示される。

### _reconnect_loop の例外安全性

`_reconnect_loop`はfire-and-forget型のasyncioタスクとして実行される。
予期せぬ例外でサイレントに終了すると、以降の再接続が永久に行われなくなる。

- `asyncio.CancelledError`: re-raise（タスクキャンセルのセマンティクスを保持）
- 一般`Exception`: ログ出力 + `STATUS_DISCONNECTED`にフォールバック

### bless 0.3.0 の公開API制約

PyPIリリース版の bless 0.3.0 には `bless.backends.advertisement` モジュールが存在しない。
`BlessAdvertisementData` クラスはGitHub mainブランチのみの未リリースAPI。

bless 0.3.0 での正しい使い方:
- `BlessServer(name=device_name, loop=loop)` でデバイス名を設定
- `add_gatt(gatt)` でサービス・キャラクタリスティックを登録
- `start()` を引数なしで呼び出し（登録済みサービスが自動的にAdvertisingされる）

バージョンは `==0.3.0` で固定し、未リリースAPIへの依存を防止する。

## 関連ファイル

- `src/ble_sender/ble_client.py` - 再接続ロジック（`_on_disconnect`, `_reconnect_loop`, `disconnect`）
- `src/ble_receiver/lib/gatt_server.py` - BLE GATTサーバー（bless API使用）
- `tests/test_ble_client.py` - 再接続テスト
- `tests/test_gatt_server.py` - GATTサーバーテスト
- `docs/spec/ble-connectivity.md` - BLE接続性向上の設計判断
