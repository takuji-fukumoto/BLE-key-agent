# Pi側BLE通信ログ追加

## 概要

BLE通信開始から約10分後にPi側がフリーズする問題が継続している。
過去に2回のフリーズ防止対策（executor offloading、バックプレッシャー、メモリ最適化、スレッド安全性等）を実施済みだが解消していない。

Mac側スクリプトは動作継続しているがPi側LCD画面が固まる症状のため、Pi側で何が起きているかを把握するBLE通信ログを追加する。現状の問題:
- ログはコンソール(stdout)のみ → 画面フリーズ時にログが確認できない
- BLE通信の詳細（ハートビート、キーイベント）はDEBUGレベル → INFOでは見えない
- 定期的なヘルスチェックログがなく、フリーズ直前の状態がわからない

## 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `scripts/run_raspi.sh` | `--debug` オプション追加、ログファイルパスの表示 |
| `src/raspi_receiver/apps/lcd_display/main.py` | CLIオプション対応、ファイルログ出力、ヘルスチェックタスク追加 |
| `src/raspi_receiver/lib/key_receiver.py` | 受信統計カウンタ追加、定期統計ログ出力 |
| `tests/test_key_receiver.py` | 統計カウンタのテスト追加 |

## Phase1: 設計

- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査
- [x] [Phase1] ログ設計（レベル、フォーマット、出力先）

### ログ設計

**ファイルログ:**
- 出力先: `logs/raspi_receiver.log`（プロジェクトルート基準）
- ローテーション: `RotatingFileHandler` (5MB, バックアップ3ファイル)
- フォーマット: `%(asctime)s [%(name)s] %(levelname)s: %(message)s`
- レベル: ファイルは常にDEBUG、コンソールはオプションでDEBUG/INFO切替

**ヘルスチェックログ（30秒間隔）:**
- BLE接続状態（connected/disconnected）
- 受信統計（キーイベント数、ハートビート数、デシリアライズエラー数）
- イベントキュー残量
- メモリ使用量（RSS）
- asyncioタスク数

## Phase2: 実装（コア）

- [ ] [Phase2] `key_receiver.py` に受信統計カウンタ（`ReceiverStats`）を追加
  - `key_events_received: int` — キーイベント受信数
  - `heartbeats_received: int` — ハートビート受信数
  - `deserialize_errors: int` — デシリアライズ失敗数
  - `connections: int` — 接続回数
  - `disconnections: int` — 切断回数
  - `last_receive_time: float` — 最後のデータ受信時刻
  - `stats` プロパティでコピーを返す
  - `_handle_write` 内で適切にカウントアップ

- [ ] [Phase2] `main.py` にCLI引数パーサー追加
  - `--debug`: DEBUGレベルログ有効化
  - `--log-dir`: ログディレクトリ指定（デフォルト: `logs/`）

- [ ] [Phase2] `main.py` にファイルログ設定を追加
  - `RotatingFileHandler` (5MB, backupCount=3)
  - ログディレクトリの自動作成（`os.makedirs`）
  - ファイルはDEBUGレベル固定、コンソールは `--debug` で切替

- [ ] [Phase2] `main.py` にヘルスチェックタスク（`_health_check_loop`）追加
  - 30秒間隔でINFOレベルのヘルスログ出力
  - 内容: BLE接続状態、受信統計、キュー残量、メモリRSS、asyncioタスク数
  - `resource.getrusage` でメモリ取得（Pi互換）

- [ ] [Phase2] `run_raspi.sh` に `--debug` オプションのパススルー追加
  - `$@` でスクリプト引数をPythonに渡す
  - ログファイルパスの表示を追加

## Phase3: 実装（結合）

- [ ] [Phase3] `LCDApp.run()` にヘルスチェックタスクの起動・停止を追加
- [ ] [Phase3] ヘルスチェックから `KeyReceiver.stats` を参照する接続

## Phase4: テスト

- [ ] [Phase4] `test_key_receiver.py` に `ReceiverStats` カウンタのテスト追加
  - キーイベント受信でカウントアップ
  - ハートビート受信でカウントアップ
  - デシリアライズエラーでカウントアップ
  - 接続/切断でカウントアップ
- [ ] [Phase4] テスト実行・パス確認

## Phase5: 仕上げ

- [ ] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順等）
- [ ] [Phase5] 動作確認
