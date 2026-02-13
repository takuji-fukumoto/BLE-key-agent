# Phase 2: Pi側BLEライブラリ (raspi_receiver/lib/)

## 概要
Raspberry Pi側のBLE GATTサーバーライブラリを実装する。
PoC (`poc/ble_gatt/peripheral_raspi.py`) をベースに、blessライブラリを使用してGATTサーバーをクラス化し、
コールバック管理のKeyReceiverを提供する。アプリケーション（LCD表示等）はこのライブラリのコールバックを実装するだけでキー受信機能を構築できる。

## 変更対象ファイル

| ファイル | 操作 | 概要 |
|---|---|---|
| `src/raspi_receiver/__init__.py` | 新規 | パッケージ初期化 |
| `src/raspi_receiver/lib/__init__.py` | 新規 | ライブラリ公開API（KeyReceiver, ConnectionEvent等のre-export） |
| `src/raspi_receiver/lib/types.py` | 新規 | ConnectionEvent定義、common.protocolからのre-export |
| `src/raspi_receiver/lib/gatt_server.py` | 新規 | bless GATTサーバーラッパークラス |
| `src/raspi_receiver/lib/key_receiver.py` | 新規 | 高レベルAPI（GATTServer + デシリアライズ + コールバック管理） |
| `tests/test_gatt_server.py` | 新規 | GATTServerの単体テスト（blessモック） |
| `tests/test_key_receiver.py` | 新規 | KeyReceiverの単体テスト（GATTServerモック） |
| `docs/spec/raspi-receiver-lib.md` | 新規 | 設計判断・制約のドメイン知識ドキュメント |

## 設計方針

### types.py の方針
- `KeyEvent`, `KeyType`, `Modifiers` は `common.protocol` から re-export する（重複定義しない）
- `ConnectionEvent` のみ新規定義する（Pi側固有の型）
- 仕様書の `types.py` の `KeyEvent` は field名が異なるが、`common.protocol.KeyEvent` をそのまま使用する
  - 仕様書: `key_value` / `is_press` → 実装: `value` / `press`（Phase 1で確定済み）

### gatt_server.py の方針
- PoCの `peripheral_raspi.py` をクラス化
- `BlessServer` をラップし、GATT定義・起動・停止を管理
- コールバック: `on_write(data: bytes)`, `on_connect()`, `on_disconnect()`
- blessの接続/切断検出は `read_request_func` / サーバー状態の変化で検出を試みる。
  確実な検出が困難な場合は、接続状態の追跡はアプリ側で行う設計とする（ログ出力で対応）
- UUID定数は `common.uuids` から import

### key_receiver.py の方針
- `GATTServer` をコンポジションで保持
- 受信バイト列を `common.protocol.KeyEvent.deserialize()` でデコード
- press/releaseを判定し、対応するコールバックを呼び出す
- デシリアライズ失敗時はログ出力して無視（仕様通り）

## Phase1: 設計
- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査（common.protocol, common.uuids の公開API確認）
- [x] [Phase1] インターフェース・データ構造の設計（types.py, gatt_server.py, key_receiver.py）

## Phase2: 実装（コア）
- [x] [Phase2] `src/raspi_receiver/__init__.py` 作成（パッケージ初期化）
- [x] [Phase2] `src/raspi_receiver/lib/__init__.py` 作成（公開APIの re-export）
- [x] [Phase2] `src/raspi_receiver/lib/types.py` 実装（ConnectionEvent定義 + common re-export）
- [x] [Phase2] `src/raspi_receiver/lib/gatt_server.py` 実装（GATTServerクラス）
- [x] [Phase2] `src/raspi_receiver/lib/key_receiver.py` 実装（KeyReceiverクラス）

## Phase3: 実装（結合）
- [x] [Phase3] GATTServer → KeyReceiver の結合（on_write → deserialize → callback の流れ）
- [x] [Phase3] エラーハンドリング実装（デシリアライズ失敗時のログ出力・スキップ）

## Phase4: テスト
- [x] [Phase4] `tests/test_gatt_server.py` 作成（blessモックでGATTServer単体テスト）
- [x] [Phase4] `tests/test_key_receiver.py` 作成（GATTServerモックでKeyReceiver単体テスト）
- [x] [Phase4] テスト実行・全パス確認

## Phase5: 仕上げ
- [x] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順）
- [x] [Phase5] `docs/spec/raspi-receiver-lib.md` 作成（設計判断ドキュメント）
- [x] [Phase5] 動作確認（テスト全パス + import可能性確認）
