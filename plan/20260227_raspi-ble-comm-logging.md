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

- [x] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順等）
- [x] [Phase5] 動作確認

---

## 追加調査: フリーズ箇所の特定

### 調査結果

デバッグログを取得し分析した結果、以下が判明:
- BLEデータ受信は正常（ハートビート3秒間隔で継続）
- HEALTH check正常（queue=0, RSS=42.7MB, tasks=5）
- エラー・例外なし
- ログ出力自体が突然完全停止（ハートビート/HEALTHチェック/全ログ）
- → **asyncioイベントループ + blessコールバックスレッド + 全てが同時にハング**
- → **プロセス全体のフリーズ**（特定レイヤーの問題ではない）

### 原因候補

1. **bless/BlueZ/D-Busデッドロック** — blessがD-Bus経由でBlueZと通信中にデッドロック
2. **SPI通信ハング** — ST7789ドライバのSPIバスが応答しなくなり、executor スレッドが永久ブロック
3. **GILデッドロック** — C拡張経由のblessとSPIスレッドの競合

### 切り分け方針

asyncioに依存しない独立した `threading.Thread` ウォッチドッグを追加し、
どのレイヤーでハングしているか特定する。

- ウォッチドッグスレッドも止まる → プロセスレベルのハング（GIL or システムコール）
- ウォッチドッグは動くがasyncioタスクが止まる → イベントループのブロック
- render() の「開始」ログだけ出て「終了」が出ない → SPI I/Oハング

## Phase2追加: ウォッチドッグスレッド実装

- [ ] [Phase2] `main.py` にウォッチドッグスレッド（`_watchdog_thread`）を追加
  - `threading.Thread(daemon=True)` で独立スレッドとして起動
  - 5秒間隔でログ出力: `[WATCHDOG] alive | loop_responsive=... | render_blocked=...`
  - asyncioイベントループの応答確認: `call_soon_threadsafe` でフラグを更新し、次回チェック時に確認
  - `_rendering` フラグを監視して SPI I/O ブロックを検出
  - ウォッチドッグ自体が止まった場合 → GIL/プロセスレベルのハングと判定可能

- [ ] [Phase2] `main.py` の `_render_loop` と `_button_poll_loop` の render() 前後にタイムスタンプログ追加
  - `logger.debug("render: start")` / `logger.debug("render: done (%.1fms)", elapsed_ms)`
  - SPI I/O ハングの検出に使用

---

## ウォッチドッグログ分析結果

### 判明した事実

ウォッチドッグスレッド付きでログを取得した結果:
- WATCHDOG は `loop_responsive=True` でフリーズ直前まで正常動作
- **最後のログ行が `render: start`（`render: done` なし）**
- その後 WATCHDOG スレッドも停止
- bless コールバックスレッドも停止
- → **`render()` 内の SPI I/O がハングし、spidev C拡張が GIL を保持したまま全スレッドが凍結**

### 根本原因

`spidev.writebytes()` は C 拡張で GIL を解放しない `ioctl()` を実行する。
SPI バスがハードウェアレベルでハングすると、この `ioctl()` が永久ブロックし、
GIL が保持されたまま全 Python スレッド（watchdog含む）が停止する。

`run_in_executor()` でスレッドプールに逃がしても、同一プロセス内の
スレッドは GIL を共有するため効果なし。

### SPI ハングの原因候補

1. **SPI バス速度 (40MHz) が ST7789 仕様超過** — ST7789V データシート上の最大クロックは ~15MHz
2. **DMA バッファ枯渇** — 連続書き込みでカーネルバッファが未解放
3. **ST7789 コントローラの内部 FIFO オーバーフロー**

---

## Phase6: SPI フリーズ対策

### 設計

**対策1: SPI 書き込みをサブプロセスに分離**

`spidev` が GIL を保持する問題を回避するため、SPI I/O を `multiprocessing.Process` で
別プロセスに分離する。別プロセスは独自の GIL を持つため、SPI がハングしても
メインプロセス（asyncio + bless + watchdog）は影響を受けない。

アーキテクチャ:
```
メインプロセス:
  LCDDisplay.render()
    → PIL 合成 (~1ms)
    → RGB565 変換
    → Pipe 経由でサブプロセスに送信
    → conn.poll(timeout=5s) で待機（GIL 解放）
    → タイムアウト時: サブプロセス kill → 再起動

サブプロセス (spi-renderer):
  _render_worker()
    → ST7789 初期化 (SPI + GPIO)
    → Pipe からデータ受信
    → SetWindows + spi_writebyte (4KB チャンク)
    → 完了通知
```

**対策2: SPI バス速度低減**

現在 40MHz → 20MHz に低減。Raspberry Pi の SPI クロック分周により実効 ~15.6MHz。
ST7789V データシートの仕様内（書き込み最大 ~15MHz）に収まる。

フレームレート影響:
- 40MHz: ~23ms/frame → ~43 FPS
- 20MHz: ~46ms/frame → ~21 FPS（RENDER_MIN_INTERVAL_MS=50ms に収まる）

### タスク

- [ ] [Phase6] `config.py` に SPI 定数追加
  - `SPI_SPEED_HZ: int = 20_000_000` — SPI バス速度（20MHz）
  - `SPI_RENDER_TIMEOUT_SEC: float = 5.0` — サブプロセスレンダリングタイムアウト

- [ ] [Phase6] `render_process.py` を新規作成
  - `_DigitalBacklightFallback` クラス（display.py から移動）
  - `_render_worker()` — サブプロセスエントリポイント
    - ST7789 初期化（SPI + GPIO）
    - Pipe コマンドループ（render / buttons / backlight / clear）
    - SPI 速度オーバーライド
  - `RenderProxy` クラス — メインプロセス側プロキシ
    - `start()` — `spawn` コンテキストでサブプロセス起動
    - `render(rgb565_buf, width, height)` — タイムアウト付き SPI 書き込み
    - `read_buttons()` → `(key1, key2)`
    - `set_backlight(duty)`
    - `stop()` — 安全なシャットダウン
    - `_restart()` — ハング検出時の自動復旧
    - `threading.Lock` でパイプアクセスを直列化

- [ ] [Phase6] `display.py` を修正
  - `LCDDisplay.__init__()` に `spi_speed` パラメータ追加
  - `init()`: ST7789 直接初期化 → `RenderProxy.start()` に置換
  - `render()`: `_show_image_rgb565()` → `_convert_to_rgb565()` + `RenderProxy.render()`
  - `shutdown()`: `_disp.module_exit()` → `RenderProxy.stop()`
  - `set_backlight()`: `_disp.bl_DutyCycle()` → `RenderProxy.set_backlight()`
  - `read_buttons()` メソッド追加
  - `_show_image_rgb565()` → `_convert_to_rgb565()` にリネーム（SPI 部分除去）
  - `_DigitalBacklightFallback`, `_OriginalPWM` を `render_process.py` に移動

- [ ] [Phase6] `main.py` を修正
  - `--spi-speed` CLI オプション追加
  - `LCDDisplay(spi_speed=args.spi_speed)` でパラメータ渡し
  - ボタン読み取り: `_display._disp.digital_read()` → `_display.read_buttons()`
  - ボタンポーリングの `_read_buttons()` ローカル関数を削除

- [ ] [Phase6] テスト実行・パス確認
