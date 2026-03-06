# デバイス名リネーム: RasPi-KeyAgent → BLEKeyReceiver

## Context

BLEデバイス名のデフォルト値が `RasPi-KeyAgent` のままになっており、
Raspberry Pi固有の名前がコードベース全体に残っている。
レシーバーはRaspberry Pi以外（UNIHIKER等）でも動作するため、
デバイス非依存の抽象的な名前 `BLEKeyReceiver` に変更する。

## 変更内容

`RasPi-KeyAgent` → `BLEKeyReceiver` の文字列置換。
コメント・docstring内の `Raspberry Pi peripheral` 等の記述も汎用的な表現に修正。

## 変更対象ファイル

### A. ソースコード
| ファイル | 変更内容 |
|---|---|
| `src/common/uuids.py` | `DEVICE_NAME` 定数値 + コメント |
| `src/ble_sender/api_types.py` | `device_name` デフォルト値 |
| `src/ble_sender/main.py` | docstring, デフォルト値, help文字列 |

### B. テスト
| ファイル | 変更内容 |
|---|---|
| `tests/test_key_receiver.py` | assertion文字列 |
| `tests/test_gatt_server.py` | assertion文字列 |

### C. サンプルアプリ・スクリプト
| ファイル | 変更内容 |
|---|---|
| `sample/raspi_receiver/apps/cli_receiver/main.py` | argparse default |
| `sample/unihiker_receiver/main.py` | デフォルト値, argparse default |
| `scripts/run_mac.sh` | コメント内の例 |
| `sample/scripts/run_raspi.sh` | echo メッセージ |
| `sample/scripts/run_unihiker.sh` | echo メッセージ |

### D. ドキュメント
| ファイル | 変更内容 |
|---|---|
| `docs/spec-ble-protocol.md` | デバイス名テーブル, シーケンス図 |
| `docs/spec-raspi-receiver.md` | デフォルト値の例 |
| `docs/spec-mac-agent.md` | UI モックアップ |
| `README.md` | 実行例, コード例, BLE仕様テーブル |

### 変更しないファイル
- `poc/` 配下（参照用のため変更不要）
- `plan/` 配下の過去プランファイル

## Phase1: 設計
- [ ] [Phase1] 変更対象ファイルの洗い出し
- [ ] [Phase1] 影響範囲の確認

## Phase2: 実装（コア）
- [ ] [Phase2] `src/common/uuids.py` DEVICE_NAME定数変更
- [ ] [Phase2] `src/ble_sender/api_types.py` デフォルト値変更
- [ ] [Phase2] `src/ble_sender/main.py` デフォルト値・docstring・help文字列変更

## Phase3: 実装（結合）
- [ ] [Phase3] `tests/test_key_receiver.py` assertion文字列更新
- [ ] [Phase3] `tests/test_gatt_server.py` assertion文字列更新
- [ ] [Phase3] `sample/raspi_receiver/apps/cli_receiver/main.py` argparseデフォルト更新
- [ ] [Phase3] `sample/unihiker_receiver/main.py` デフォルト値・argparse更新
- [ ] [Phase3] `scripts/run_mac.sh` コメント更新
- [ ] [Phase3] `sample/scripts/run_raspi.sh` echoメッセージ更新
- [ ] [Phase3] `sample/scripts/run_unihiker.sh` echoメッセージ更新

## Phase4: テスト
- [ ] [Phase4] pytest全テスト実行・パス確認
- [ ] [Phase4] `grep -r "RasPi-KeyAgent"` で残存参照チェック（poc/plan以外）

## Phase5: 仕上げ
- [ ] [Phase5] `docs/spec-ble-protocol.md` デバイス名・シーケンス図更新
- [ ] [Phase5] `docs/spec-raspi-receiver.md` デフォルト値更新
- [ ] [Phase5] `docs/spec-mac-agent.md` UIモックアップ更新
- [ ] [Phase5] `README.md` 実行例・コード例・BLE仕様テーブル更新
- [ ] [Phase5] CLAUDE.md規約準拠チェック
- [ ] [Phase5] 最終テスト実行・動作確認

## 検証方法
1. `pytest` で全テスト通過を確認
2. `grep -r "RasPi-KeyAgent" src/ tests/ scripts/ sample/ docs/` でpoc/plan以外に残存参照がないことを確認
