# ble_receiver/lib/ 設計判断・ドメイン知識

## 概要

BLE GATTサーバーライブラリ。
BLE senderからのキーイベント受信をコールバックベースのAPIで提供する。

## 設計判断

### types.py: common.protocol の re-export

- `KeyEvent`, `KeyType`, `Modifiers` は `common.protocol` で定義済み
- 仕様書（spec-raspi-receiver.md §3.1）のフィールド名（`key_value`, `is_press`）と
  common.protocol の実装（`value`, `press`）は異なるが、Phase 1で確定した命名をそのまま採用
- `ConnectionEvent` のみ ble_receiver 固有の型として新規定義

### gatt_server.py: bless の遅延インポート

- bless はレシーバー側専用依存（`pyproject.toml` の `[project.optional-dependencies] raspi`）
- センダー側開発環境ではインストール不要にするため、`TYPE_CHECKING` ガードと `start()` 内での遅延インポートを採用
- テスト時は `sys.modules` に bless モックを登録して対応

### key_receiver.py: 接続検出の方式

- bless はネイティブな connect/disconnect コールバックを直接提供しない
- 暫定策として「初回 write 受信時」に接続と判定し `on_connect` を発火
- `on_disconnect` は現時点では発火しない（将来、bless のイベント監視機能が利用可能になった際に対応）
- `stop()` 呼び出し時に接続状態をリセット

### エラーハンドリング方針

- デシリアライズ失敗: `logger.warning` で記録してスキップ（仕様通り: spec-ble-protocol.md §5）
- コールバック例外: `logger.exception` で記録して握り潰す（サーバー停止を防ぐ）
- GATTServer, KeyReceiver のすべてのコールバック呼び出し箇所に try/except を配置

## 制約・注意点

- bless の `write_request_func` は同期コールバック（async不可）
  - コールバック内で重い処理をするとBLEスタックをブロックする可能性がある
  - LCD描画等の重い処理はアプリ側で非同期キューを介して行うことを推奨
- `asyncio_mode = "auto"` を `pyproject.toml` に追加（pytest-asyncio の設定）

## テストの工夫

- `sys.modules["bless"]` にモジュールレベルのモックを登録し、bless未インストール環境でもテスト実行可能
- GATTServer のテストでは `patch.object` で `BlessServer` コンストラクタをモック
- KeyReceiver のテストでは `GATTServer` クラス全体をモックし、`on_write` コールバックを直接呼び出し
