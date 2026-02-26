# Pi側フリーズ防止: イベントループブロッキング解消 & バックプレッシャー追加

## Context

`run_mac.sh` と `run_raspi.sh` を起動してしばらくキーを送信し続けると、Pi側がフリーズする。
原因調査の結果、以下の問題が複合していることが判明した：

1. SPI LCD描画（`ShowImage`）がasyncioイベントループを3ms+ブロックし、BLEコールバック処理が滞る
2. イベントキューが無制限で、高速タイピング時にメモリが増加し続ける
3. Mac側にBLE書き込みのレートリミットがなく、Pi側を圧倒する
4. GPIOボタン読み取りもイベントループをブロックする

**注:** 切断検知（ハートビート/タイムアウト）は `plan/20260226_heartbeat-disconnect-detection.md` で別途計画済みのため本planには含めない。

---

## 変更対象ファイル

| ファイル | 修正内容 |
|---------|---------|
| `src/raspi_receiver/apps/lcd_display/main.py` | Fix 1, 2, 4 |
| `src/raspi_receiver/apps/lcd_display/config.py` | 定数追加 |
| `src/mac_agent/main.py` | Fix 3 |
| `src/mac_agent/key_monitor.py` | Fix 3（キュー満杯時の処理） |
| `tests/test_lcd_display.py` | Fix 1, 2 のテスト追加 |
| `tests/test_key_monitor.py` | Fix 3 のテスト追加 |

---

## Fix 1 (P0): SPI描画をスレッドプールにオフロード

**対象:** `src/raspi_receiver/apps/lcd_display/main.py`

`_render_loop()` 内の `self._display.render()` は同期SPI I/O（3ms+）でイベントループをブロックする。
`run_in_executor` でスレッドプールに逃がし、BLEコールバック処理を妨げないようにする。

### 変更内容

**`__init__` にフラグ追加:**
```python
self._rendering = False
```

**`_render_loop()` のrender呼び出しを変更（現在L184）:**
```python
# Before
self._display.render()

# After
if not self._rendering:
    self._rendering = True
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._display.render)
    finally:
        self._rendering = False
```

**`_button_poll_loop()` のrender呼び出しも同様に変更（現在L274）:**
```python
if not self._rendering:
    self._rendering = True
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._display.render)
    finally:
        self._rendering = False
```

**スレッド安全性:** `_rendering` フラグにより同時実行は防止される。状態更新（`_process_event`等）はイベントループスレッドで行われ、`render()` はexecutorスレッドで読み取り専用。`await` の間にイベントループに制御が戻るため、state更新とrender読み取りの競合は起きない。

**注意:** `run()` 内の初期描画（L73 `self._display.render()`）はasyncタスク起動前なのでそのままでOK。

---

## Fix 2 (P1): イベントキューにバックプレッシャー追加

**対象:** `src/raspi_receiver/apps/lcd_display/main.py`, `config.py`

### 変更内容

**`config.py` に定数追加:**
```python
EVENT_QUEUE_MAX_SIZE: int = 128
```

**`__init__` のキュー生成を変更（現在L63）:**
```python
# Before
self._event_queue: asyncio.Queue[DisplayEvent] = asyncio.Queue()

# After
self._event_queue: asyncio.Queue[DisplayEvent] = asyncio.Queue(
    maxsize=EVENT_QUEUE_MAX_SIZE
)
```

**キュー満杯時にQueueFullを安全にキャッチするヘルパー追加:**

`call_soon_threadsafe` は `put_nowait` をイベントループスレッドでスケジュールするため、`QueueFull` は呼び出し側ではなくイベントループスレッドで発生する。そのためヘルパーメソッドで吸収する。

```python
def _safe_enqueue_key(self, event: DisplayEvent) -> None:
    """Enqueue a key event, dropping silently if queue is full."""
    try:
        self._event_queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.debug("Event queue full, dropping key event")
```

**`_enqueue()` を変更（現在L139-144）:**
```python
def _enqueue(self, event: DisplayEvent) -> None:
    """Thread-safe enqueue of display events."""
    if self._loop is None or not self._loop.is_running():
        return
    if isinstance(event, DisplayConnectionEvent):
        # 接続イベントは常にキューイング（発生頻度が極めて低い）
        self._loop.call_soon_threadsafe(
            self._event_queue.put_nowait, event
        )
    else:
        # キーイベントはキュー満杯時に破棄
        self._loop.call_soon_threadsafe(
            self._safe_enqueue_key, event
        )
```

**maxsize=128の根拠:** 描画ループは20FPSで全イベントをドレインする。60key/secの高速タイピングでも1フレームあたり約3イベントしかたまらない。128は十分なバッファ。

---

## Fix 3 (P1): Mac側にレートリミット追加

**対象:** `src/mac_agent/main.py`, `src/mac_agent/key_monitor.py`

### main.py の変更

**定数追加:**
```python
MIN_SEND_INTERVAL_S: float = 0.005  # 5ms minimum between BLE writes
```

**`__init__` にフィールド追加:**
```python
self._last_send_time: float = 0.0
```

**`_forward_loop()` にレートリミット追加（現在L133-152）:**
```python
# Send via BLE（既存コードの前にレートリミットを挿入）
now = asyncio.get_event_loop().time()
elapsed = now - self._last_send_time
if elapsed < MIN_SEND_INTERVAL_S:
    await asyncio.sleep(MIN_SEND_INTERVAL_S - elapsed)

if self._ble_client.status == STATUS_CONNECTED:
    await self._ble_client.send_key(event)
    self._last_send_time = asyncio.get_event_loop().time()
    if event.press:
        logger.debug(f"Sent: {event}")
```

**Mac側キューも上限付きに変更（現在L47）:**
```python
# Before
self._key_queue: asyncio.Queue[KeyEvent | None] = asyncio.Queue()

# After
self._key_queue: asyncio.Queue[KeyEvent | None] = asyncio.Queue(maxsize=256)
```

### key_monitor.py の変更

キューに上限を設けたため、`queue.put()` が満杯時にブロックする可能性がある。
pynputスレッドをブロックしないよう、`run_coroutine_threadsafe(queue.put(...))` から `call_soon_threadsafe` + `put_nowait` パターンに変更する。

**`_on_press` の変更（現在L232-237）:**
```python
# Before
asyncio.run_coroutine_threadsafe(
    self._queue.put(event),
    self._loop
)

# After
self._loop.call_soon_threadsafe(self._safe_put, event)
```

**`_on_release` にも同じ変更を適用（現在L259-264）。**

**ヘルパーメソッド追加:**
```python
def _safe_put(self, event: KeyEvent) -> None:
    """Enqueue event, dropping if queue is full."""
    try:
        self._queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning("Key event queue full, dropping event")
```

**注意:** イベントを破棄するのはあくまでキュー満杯時（BLE切断中にタイピングし続けた場合等）のみ。通常運用では5msのレートリミットによりキューは常に空に近い状態。

---

## Fix 4 (P2): GPIOボタン読み取りをスレッドプールにオフロード

**対象:** `src/raspi_receiver/apps/lcd_display/main.py`

### 変更内容

**`_button_poll_loop()` のGPIO読み取りを変更（現在L268-269）:**

```python
# Before
key1_pressed = disp.digital_read(disp.GPIO_KEY1_PIN) == 0
key2_pressed = disp.digital_read(disp.GPIO_KEY2_PIN) == 0

# After
def _read_buttons() -> tuple[bool, bool]:
    return (
        disp.digital_read(disp.GPIO_KEY1_PIN) == 0,
        disp.digital_read(disp.GPIO_KEY2_PIN) == 0,
    )

key1_pressed, key2_pressed = await loop.run_in_executor(
    None, _read_buttons
)
```

`loop` は `_button_poll_loop` の先頭で `asyncio.get_running_loop()` を取得してwhileループ外に置く。

---

## 実装順序

- [ ] Step 1: Fix 1 — `main.py` のrender呼び出しを `run_in_executor` に変更
- [ ] Step 2: Fix 4 — `main.py` のGPIO読み取りを `run_in_executor` に変更（Fix 1と同ファイル、同時実装）
- [ ] Step 3: Fix 2 — `config.py` に定数追加、`main.py` のキューにmaxsize設定 + バックプレッシャー
- [ ] Step 4: Fix 3 — `mac_agent/main.py` にレートリミット追加、`key_monitor.py` のキューイング変更
- [ ] Step 5: テスト追加・実行

---

## テスト方針

### test_lcd_display.py に追加

- `_render_loop` が `run_in_executor` 経由で `render()` を呼ぶことを検証
- `_rendering` フラグにより同時renderが防止されることを検証
- `_rendering` が例外発生時もFalseにリセットされることを検証
- キュー満杯時にキーイベントが破棄されログ出力されることを検証
- 接続イベントはキュー満杯でも常にキューイングされることを検証

### test_key_monitor.py に追加

- `_safe_put` がQueueFull時に例外を飲み込むことを検証
- `_on_press` / `_on_release` が `call_soon_threadsafe` + `_safe_put` パターンを使うことを検証

### 手動結合テスト

- Mac/Pi接続→高速キー連打→Piがフリーズしないことを確認
- Mac/Pi接続→長時間運用（5分以上）→安定動作を確認
