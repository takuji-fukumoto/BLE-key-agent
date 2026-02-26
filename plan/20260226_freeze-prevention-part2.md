# Pi側フリーズ防止 Part 2: 描画パフォーマンス最適化 & スレッド安全性

## Context

`plan/20260226_freeze-prevention.md` で対処した Fix 1〜4（executor オフロード、バックプレッシャー、レートリミット、GPIO オフロード）は実装済み。
しかし長時間運用でフリーズが再発する。原因は executor に逃がした処理自体が重すぎてスレッドプールを占有し続けること、および例外・スレッド安全性の問題。

---

## 変更対象ファイル

| ファイル | 修正内容 |
|---------|---------|
| `src/raspi_receiver/apps/lcd_display/display.py` | Fix 1, 2 |
| `src/raspi_receiver/apps/lcd_display/main.py` | Fix 3 |
| `src/raspi_receiver/lib/key_receiver.py` | Fix 4 |
| `tests/test_lcd_display.py` | Fix 1, 2, 3 のテスト追加 |
| `tests/test_key_receiver.py` | Fix 4 のテスト追加 |

---

## Fix 1 (P0): RGB565 変換の最適化

**対象:** `src/raspi_receiver/apps/lcd_display/display.py` `_show_image_rgb565()`

### 問題

毎フレーム 172,800 回の Python ループで RGB888→RGB565 変換 + `list(pix)` で 115KB のリストコピー。
スレッドプールを長時間占有。

### 変更内容

- `struct.pack_into` によるインプレース RGB565 変換
- `list(pix)` を除去、`bytearray` スライスを直接 SPI に渡す
- 再利用可能な `buf` パラメータ追加

---

## Fix 2 (P1): render() のメモリ確保削減

**対象:** `src/raspi_receiver/apps/lcd_display/display.py` `render()`, `__init__()`, `init()`

### 問題

毎フレーム 460KB+ のゴミ（rotate, tobytes, bytearray, list）→ GC ストール。

### 変更内容

- `image.rotate(270)` → `image.transpose(Image.Transpose.ROTATE_270)` に変更（アフィン変換→ピクセル再配置で高速化）
- `_has_numpy` フラグで numpy 有無を保持、`render()` 内で分岐
- numpy 不在時: `_rgb565_buf` を `init()` で事前確保して毎フレーム再利用
- numpy 利用時: 従来の `ShowImage()` をそのまま使用

---

## Fix 3 (P2): `_enqueue` の例外安全性

**対象:** `src/raspi_receiver/apps/lcd_display/main.py` `_enqueue()`

### 問題

`loop.is_running()` チェック後に `call_soon_threadsafe()` が `RuntimeError` を投げるとBLEコールバックスレッドが死ぬ。

### 変更内容

- `try/except RuntimeError` でラップ

---

## Fix 4 (P2): `_connected` フラグのスレッド安全性

**対象:** `src/raspi_receiver/lib/key_receiver.py`

### 問題

`_handle_write()`（blessスレッド）と `_timeout_monitor()`（asyncioタスク）が `_connected` を同期なしで読み書き。

### 変更内容

- `threading.Lock` (`_conn_lock`) で check-then-act を保護
- コールバック呼び出しはロック外

---

## 実装順序

- [x] Step 1: Fix 1 — `_show_image_rgb565` を `struct.pack_into` + `list()` 除去に書き換え
- [x] Step 2: Fix 2 — `rotate()` → `transpose()`、RGB565 バッファ再利用、`_has_numpy` フラグ追加
- [x] Step 3: Fix 3 — `_enqueue` に `try/except RuntimeError` 追加
- [x] Step 4: Fix 4 — `_connected` に `threading.Lock` 追加
- [x] Step 5: テスト追加・実行（93 passed）

---

## テスト

### test_lcd_display.py に追加

- `TestShowImageRgb565`: RGB565 変換正当性、bytearray 直接渡し、バッファ再利用、サイズ不一致エラー
- `TestRenderOptimization`: transpose 使用確認、numpy 有無での分岐確認
- `TestEnqueueExceptionSafety`: RuntimeError 吸収確認

### test_key_receiver.py に追加

- `TestKeyReceiverConnLock`: ロック存在確認、並行 write での on_connect 重複防止、stop() のロック使用
