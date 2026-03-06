# モジュール名リネーム: raspi_receiver → ble_receiver, mac_agent → ble_sender

## 概要

プロジェクトはBLE通信・入力監視ツールとして汎用化されたが、送受信モジュール名にデバイス固有の名残がある。
- `src/raspi_receiver/` → Raspberry Pi 非依存なのに `raspi` がついている
- `src/mac_agent/` → macOS 非依存なのに `mac` がついている

デバイス非依存の抽象的な名前にリネームし、ライブラリとしての汎用性を明確にする。
サンプルコード（`sample/raspi_receiver/`）やスクリプト類はデバイス固有のため変更しない。

## 変更対象ファイル

### A. ble_receiver（旧 raspi_receiver）

#### ディレクトリリネーム
- `src/raspi_receiver/` → `src/ble_receiver/`

#### ソースコード
| ファイル | 変更内容 |
|---|---|
| `src/ble_receiver/__init__.py` | docstring更新 |
| `src/ble_receiver/lib/__init__.py` | import文3箇所・docstring・Usage例更新 |
| `src/ble_receiver/lib/key_receiver.py` | import文2箇所更新 |
| `sample/raspi_receiver/apps/cli_receiver/main.py` | import文1箇所更新 |
| `sample/raspi_receiver/apps/lcd_display/main.py` | import文1箇所更新 |
| `sample/unihiker_receiver/main.py` | import文2箇所・docstring更新 |

#### テスト
| ファイル | 変更内容 |
|---|---|
| `tests/test_key_receiver.py` | import文2箇所・docstring更新 |
| `tests/test_gatt_server.py` | import文1箇所・docstring更新 |
| `tests/test_unihiker_receiver.py` | import文1箇所更新 |

### B. ble_sender（旧 mac_agent）

#### ディレクトリリネーム
- `src/mac_agent/` → `src/ble_sender/`

#### ソースコード
| ファイル | 変更内容 |
|---|---|
| `src/ble_sender/__init__.py` | import文5箇所・docstring更新 |
| `src/ble_sender/agent.py` | import文2箇所更新 |
| `src/ble_sender/keyboard_monitor.py` | import文1箇所・docstring更新 |
| `src/ble_sender/main.py` | import文3箇所・docstring・Usage例更新 |

#### テスト
| ファイル | 変更内容 |
|---|---|
| `tests/test_ble_client.py` | import文1箇所・patch文字列6箇所・docstring更新 |
| `tests/test_key_monitor.py` | import文1箇所・patch文字列12箇所・docstring更新 |
| `tests/test_key_ble_agent.py` | import文3箇所・docstring更新 |
| `tests/test_keyboard_monitor_wrapper.py` | import文1箇所・patch文字列1箇所・docstring更新 |

#### スクリプト
| ファイル | 変更内容 |
|---|---|
| `scripts/run_mac.sh` | `mac_agent.main` → `ble_sender.main` |

### C. ドキュメント（両方）
| ファイル | 変更内容 |
|---|---|
| `docs/architecture.md` | ディレクトリ構成・依存関係図・コンポーネント表のパス更新 |
| `docs/development-guide.md` | 実装順序・PoC対応表のパス更新 |
| `docs/spec-raspi-receiver.md` | モジュールパス参照更新 |
| `docs/spec-mac-agent.md` | モジュールパス・Usage例更新 |
| `docs/spec/raspi-receiver-lib.md` → `docs/spec/ble-receiver-lib.md` | リネーム＋内容更新 |
| `docs/spec/mac-agent-core.md` → `docs/spec/ble-sender-core.md` | リネーム＋内容更新 |
| `docs/spec/ble-connectivity.md` | パス参照更新 |
| `CLAUDE.md` | ディレクトリ構成・説明更新 |
| `.github/copilot-instructions.md` | パス更新 |
| `README.md` | ディレクトリ構成・import例・コマンド例更新 |

### 変更しないファイル
- `sample/raspi_receiver/` ディレクトリ（Raspi固有サンプル）
- `sample/scripts/` 各種スクリプト
- `scripts/setup_raspi.sh`
- `pyproject.toml`（optional-dependency名はデプロイ先を示すため維持）
- `tests/test_lcd_display.py`（`sample.raspi_receiver.*` 参照のみ）
- `plan/` 配下の過去プランファイル（参照用のため変更不要）

## Phase1: 設計
- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査
- [x] [Phase1] 新モジュール名の決定（ble_receiver, ble_sender）

## Phase2: 実装（コア）
- [ ] [Phase2] `src/raspi_receiver/` → `src/ble_receiver/` ディレクトリリネーム（git mv）
- [ ] [Phase2] `src/ble_receiver/__init__.py` docstring更新
- [ ] [Phase2] `src/ble_receiver/lib/__init__.py` import文・docstring更新
- [ ] [Phase2] `src/ble_receiver/lib/key_receiver.py` import文更新
- [ ] [Phase2] `src/mac_agent/` → `src/ble_sender/` ディレクトリリネーム（git mv）
- [ ] [Phase2] `src/ble_sender/__init__.py` import文・docstring更新
- [ ] [Phase2] `src/ble_sender/agent.py` import文更新
- [ ] [Phase2] `src/ble_sender/keyboard_monitor.py` import文・docstring更新
- [ ] [Phase2] `src/ble_sender/main.py` import文・docstring更新

## Phase3: 実装（結合）
- [ ] [Phase3] `sample/raspi_receiver/apps/cli_receiver/main.py` import文更新
- [ ] [Phase3] `sample/raspi_receiver/apps/lcd_display/main.py` import文更新
- [ ] [Phase3] `sample/unihiker_receiver/main.py` import文・docstring更新
- [ ] [Phase3] `tests/test_key_receiver.py` import文・docstring更新
- [ ] [Phase3] `tests/test_gatt_server.py` import文・docstring更新
- [ ] [Phase3] `tests/test_unihiker_receiver.py` import文更新
- [ ] [Phase3] `tests/test_ble_client.py` import文・patch文字列・docstring更新
- [ ] [Phase3] `tests/test_key_monitor.py` import文・patch文字列・docstring更新
- [ ] [Phase3] `tests/test_key_ble_agent.py` import文・docstring更新
- [ ] [Phase3] `tests/test_keyboard_monitor_wrapper.py` import文・patch文字列・docstring更新
- [ ] [Phase3] `scripts/run_mac.sh` モジュールパス更新
- [ ] [Phase3] `docs/spec/raspi-receiver-lib.md` → `docs/spec/ble-receiver-lib.md` リネーム＋内容更新
- [ ] [Phase3] `docs/spec/mac-agent-core.md` → `docs/spec/ble-sender-core.md` リネーム＋内容更新

## Phase4: テスト
- [ ] [Phase4] pytest 全テスト実行・パス確認
- [ ] [Phase4] import エラーがないことを確認

## Phase5: 仕上げ
- [ ] [Phase5] `docs/architecture.md` パス参照更新
- [ ] [Phase5] `docs/development-guide.md` パス参照更新
- [ ] [Phase5] `docs/spec-raspi-receiver.md` モジュールパス参照更新
- [ ] [Phase5] `docs/spec-mac-agent.md` モジュールパス参照更新
- [ ] [Phase5] `docs/spec/ble-connectivity.md` パス参照更新
- [ ] [Phase5] `CLAUDE.md` ディレクトリ構成・説明更新
- [ ] [Phase5] `.github/copilot-instructions.md` パス更新
- [ ] [Phase5] `README.md` パス・import例・コマンド例更新
- [ ] [Phase5] CLAUDE.md規約準拠チェック
- [ ] [Phase5] 最終テスト実行・動作確認
