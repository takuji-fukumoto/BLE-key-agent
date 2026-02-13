# Phase 3: Pi側LCD表示アプリ

## 概要

Phase 2で構築した`ble-key-receiver`ライブラリのコールバックを利用し、受信キーをLCD HAT（ST7789, 240x240）に表示するアプリケーションを実装する。

## アーキテクチャ

```
BLE write received (sync, bless context)
  → KeyReceiver._handle_write (sync)
    → app callback (sync)
      → asyncio.Queue (call_soon_threadsafe)
        → async render loop
          → update ScreenState
          → PIL Image composition
          → ST7789.ShowImage (SPI)
```

ポイント:
- blessコールバックは同期 → `asyncio.Queue` + `call_soon_threadsafe`で非同期レンダーループに橋渡し
- LCD描画もSPI同期処理 → 描画頻度をスロットリング（50ms間隔、20FPS上限）
- 複数イベントのバッチ処理で不要な再描画を抑制

## 変更対象ファイル

| ファイル | 種別 | 概要 |
|---------|------|------|
| `src/raspi_receiver/apps/__init__.py` | 新規 | 空パッケージinit |
| `src/raspi_receiver/apps/lcd_display/__init__.py` | 新規 | パッケージinit（docstring） |
| `src/raspi_receiver/apps/lcd_display/config.py` | 新規 | GPIO/SPI/レイアウト/色/フォント/タイミング定数 |
| `src/raspi_receiver/apps/lcd_display/display.py` | 新規 | ScreenState + LCDDisplay（PIL描画、ST7789統合） |
| `src/raspi_receiver/apps/lcd_display/main.py` | 新規 | LCDApp（KeyReceiver統合、イベントキュー、ボタン制御） |
| `tests/test_lcd_display.py` | 新規 | 単体テスト |

**既存ファイルの変更なし** — ライブラリ層（`raspi_receiver/lib/`）は修正しない。

## 主要クラス設計

### ScreenState (display.py)
```python
@dataclass
class ScreenState:
    connected: bool = False
    last_key: str = ""
    last_key_type: str = ""
    modifier_text: str = ""
    input_buffer: str = ""
    dirty: bool = True
```

### LCDDisplay (display.py)
- `init()` — ST7789ハードウェア初期化、フォント読み込み
- `shutdown()` — バックライトOFF、GPIOクリーンアップ
- `update_connection(connected)` / `update_key(...)` / `append_buffer(char)` / `handle_backspace()` / `clear_buffer()` — 状態更新
- `render()` — dirtyフラグチェック → PIL全画面描画 → `image.rotate(270)` → SPI送信
- `cycle_backlight()` — バックライト輝度サイクル（0→25→50→75→100→0）

### LCDApp (main.py)
- `run()` — KeyReceiver起動、レンダーループ/ボタンポーリングをasyncio.create_task
- sync callbacks → `loop.call_soon_threadsafe(queue.put_nowait, event)` でキューに投入
- `_render_loop()` — キュードレイン → バッチ処理 → スロットリング → render()
- `_button_poll_loop()` — 100ms間隔ポーリング、エッジ検出でデバウンス
- `_signal_shutdown()` — SIGINT/SIGTERM → asyncio.Event設定

### ST7789ドライバ統合
- `example/1.3inch_LCD_HAT_python/`を`sys.path`に追加してインポート（コピーしない）
- `display.py`の`init()`内でのみ実行（遅延インポート）

## 画面レイアウト

```
┌────────────────────────┐  Y=0
│  BLE Key Agent         │  Y=8   タイトル（水色）
│  ● Connected           │  Y=32  接続状態（緑/赤）
├────────────────────────┤  Y=55  セパレータ
│  Last Key:             │  Y=65  ラベル
│        A               │  Y=85  キー値（大フォント48pt、黄色、中央寄せ）
│  [Shift + A]           │  Y=140 モディファイア（灰色）
├────────────────────────┤  Y=165 セパレータ
│  > Hello World_        │  Y=175 入力バッファ（カーソル付き）
└────────────────────────┘  Y=240
背景: 黒
```

## 物理ボタン

| ボタン | GPIO | 機能 |
|--------|------|------|
| KEY1 | 21 | 入力バッファクリア |
| KEY2 | 20 | バックライト輝度サイクル |
| KEY3 | 16 | 予約 |

## Phase1: 設計
- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コード（raspi_receiver/lib/）の影響範囲調査
- [x] [Phase1] LCD HATドライバ（example/）の調査
- [x] [Phase1] インターフェース・データ構造の設計（ScreenState, LCDDisplay, LCDApp）

## Phase2: 実装（コア）
- [ ] [Phase2] apps/__init__.py パッケージ作成
- [ ] [Phase2] apps/lcd_display/__init__.py パッケージ作成
- [ ] [Phase2] apps/lcd_display/config.py — GPIO/SPI/レイアウト/色/フォント/タイミング定数
- [ ] [Phase2] apps/lcd_display/display.py — ScreenState dataclass
- [ ] [Phase2] apps/lcd_display/display.py — LCDDisplay.init() / shutdown()（ST7789統合）
- [ ] [Phase2] apps/lcd_display/display.py — LCDDisplay 状態更新メソッド群
- [ ] [Phase2] apps/lcd_display/display.py — LCDDisplay.render()（PIL描画ロジック）

## Phase3: 実装（結合）
- [ ] [Phase3] apps/lcd_display/main.py — DisplayEvent型定義
- [ ] [Phase3] apps/lcd_display/main.py — LCDApp.__init__() / run()（ライフサイクル管理）
- [ ] [Phase3] apps/lcd_display/main.py — sync callback → asyncio.Queue橋渡し
- [ ] [Phase3] apps/lcd_display/main.py — _render_loop()（バッチ処理 + スロットリング）
- [ ] [Phase3] apps/lcd_display/main.py — _process_event()（イベント処理 + バッファ更新）
- [ ] [Phase3] apps/lcd_display/main.py — _button_poll_loop()（ボタンポーリング + デバウンス）
- [ ] [Phase3] apps/lcd_display/main.py — main()エントリポイント + シグナルハンドリング

## Phase4: テスト
- [ ] [Phase4] tests/test_lcd_display.py — TestScreenState（dirty flag、状態遷移）
- [ ] [Phase4] tests/test_lcd_display.py — TestLCDDisplayStateUpdates（モック使用）
- [ ] [Phase4] tests/test_lcd_display.py — TestFormatModifiers（修飾キー表示）
- [ ] [Phase4] tests/test_lcd_display.py — TestFormatKeyDisplay（キー表示フォーマット）
- [ ] [Phase4] tests/test_lcd_display.py — TestProcessEvent（イベント処理）
- [ ] [Phase4] テスト実行・パス確認

## Phase5: 仕上げ
- [ ] [Phase5] CLAUDE.md規約準拠チェック（型ヒント、docstring、import順）
- [ ] [Phase5] docs/spec/lcd-display-app.md 設計判断ドキュメント作成
- [ ] [Phase5] 動作確認

## スコープ外（将来対応）

- **接続デバイス情報の表示**: blessの公開APIでは接続元デバイスアドレスを取得できない。BlueZ D-Bus API直接監視が必要になるため、将来のフェーズで対応する
- **on_disconnect検出**: blessにはdisconnectコールバックがないため、現状は「最初のwrite=接続」のみ。D-Bus監視と合わせて将来対応

## 設計上の注意点

1. **sys.path名前衝突**: `example/`の`config.py`とアプリの`config.py`は名前が同じ → ST7789インポート時に`sys.path[0]`に挿入して優先させる
2. **Unicodeアイコン**: `●`/`○`がFont01.ttfで描画できない場合 → ASCII代替 `(*)` / `( )`
3. **PIL getbbox()**: 空文字列でNone返却 → ガードチェック必須
4. **blessスレッドコンテキスト**: `call_soon_threadsafe`は同一スレッドからも安全に使用可
5. **入力バッファ**: 最大200文字制限、表示は左トランケート + `...`
