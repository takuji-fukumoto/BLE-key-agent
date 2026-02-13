# raspi_receiver/apps/lcd_display/ 設計判断・ドメイン知識

## 概要

LCD HAT（ST7789, 240x240）に受信キーを表示するアプリケーション。
`raspi_receiver/lib/`のKeyReceiverコールバックを利用してキーイベントを受信し、PILで画面を構成してSPI経由で描画する。

## 設計判断

### sync → async橋渡し: asyncio.Queue + call_soon_threadsafe

- blessの`write_request_func`は同期コールバック
- LCD描画もSPI同期処理（1フレーム115,200バイト送信）
- コールバック内で直接描画するとBLEスタックをブロックする
- `loop.call_soon_threadsafe(queue.put_nowait, event)`で非ブロッキングキューイング
- `janus`ではなく標準ライブラリの`asyncio.Queue`を使用（Mac側pynput橋渡しと同パターン）

### 全画面再描画 vs 部分更新

- ST7789は`SetWindows`で部分更新可能だが、全画面再描画を採用
- 理由: PIL Image上での構成が簡単、SPI 40MHzで全画面転送が十分高速（~3ms）
- dirtyフラグで無変更時はSPI転送をスキップ

### 描画スロットリング（50ms / 20FPS上限）

- 高速タイピング時に毎イベント描画するとSPIが飽和する
- キューから全イベントをバッチドレインし、最小間隔後に1回だけrender()
- 50ms間隔は体感上十分なレスポンス

### ST7789ドライバ統合: sys.path方式

- `example/1.3inch_LCD_HAT_python/ST7789.py`をsys.pathに追加してインポート
- コピーしない理由: CLAUDE.mdで`example/`は参照用と明記、複製の保守コスト回避
- `ST7789.py`内部で`import config`するため、sys.path[0]に挿入して名前解決を優先させる
- importは`display.py`の`init()`内でのみ実行（遅延インポート）

### 接続状態アイコン: ASCII代替

- 仕様書のUnicode記号（●/○）ではなく`(*)`/`( )`を使用
- Font01.ttfでのUnicode描画の互換性が不確定なため、確実に描画できるASCIIを選択

### 物理ボタン: asyncポーリング方式

- gpiozeroのGPIO割り込みではなくasyncポーリング（100ms間隔）を採用
- 理由: スレッド追加なし、デバウンスが自然、ボタン操作頻度に対して十分高速
- エッジ検出（`was_pressed`状態追跡）でチャタリング防止

### 入力バッファ仕様

- 文字キー: バッファに追記
- Enter: バッファクリア
- Backspace: 末尾1文字削除
- Space: スペース文字追記（special key "space" → 文字 " "）
- 最大200文字制限（メモリ保護）
- 表示が画面幅を超える場合、左トランケート + `...`プレフィックス

## 制約・注意点

- blessの公開APIでは接続元デバイスアドレスを取得できない
  - `ConnectionEvent.device_address`は現状常にNone
  - 将来BlueZ D-Bus直接監視で対応する可能性あり
- blessにはdisconnectコールバックがない
  - `on_disconnect`は定義済みだが現状発火しない
- `config.py`のモジュール名がexampleドライバの`config.py`と衝突する
  - ST7789インポート時にexampleディレクトリをsys.path[0]に挿入して回避
- フォントファイルは`example/1.3inch_LCD_HAT_python/Font/`を参照
  - Pathで動的解決するため、プロジェクトルートからの相対位置が変わると破綻する

## テストの工夫

- ScreenState, LCDDisplayの状態管理テストはハードウェアなしで実行可能
- LCDApp._process_event()テストではLCDDisplayをMagicMockで差し替え
- LCDApp._format_modifiers()とLCDDisplay._format_key_display()はstaticmethodでテスト容易
- ST7789/SPI/GPIOのモックなしでも42テストが実行可能（Mac上でのCI対応）

## 関連ファイル

- `src/raspi_receiver/apps/lcd_display/config.py` — GPIO/レイアウト/色/フォント/タイミング定数
- `src/raspi_receiver/apps/lcd_display/display.py` — ScreenState + LCDDisplay（PIL描画、ST7789統合）
- `src/raspi_receiver/apps/lcd_display/main.py` — LCDApp（KeyReceiver統合、asyncio.Queue、ボタン制御）
- `tests/test_lcd_display.py` — 単体テスト（42件）
- `scripts/raspi_receiver/setup.sh` — Pi環境セットアップスクリプト
- `example/1.3inch_LCD_HAT_python/ST7789.py` — LCD HATドライバ（参照元、変更不可）
