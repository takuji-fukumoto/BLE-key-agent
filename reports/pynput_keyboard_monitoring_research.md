# pynputライブラリによるキーボード入力監視 完全ガイド

## 目次
1. [概要と特徴](#1-概要と特徴)
2. [キーボード入力監視の仕組み](#2-キーボード入力監視の仕組み)
3. [主要なAPI](#3-主要なapi)
4. [macOSでの利用時の注意点](#4-macosでの利用時の注意点)
5. [非同期処理との組み合わせ](#5-非同期処理との組み合わせ)
6. [実践的なコード例](#6-実践的なコード例)
7. [よくあるエラーと対処法](#7-よくあるエラーと対処法)
8. [ベストプラクティス](#8-ベストプラクティス)
9. [制限事項と代替ライブラリ](#9-制限事項と代替ライブラリ)

---

## 1. 概要と特徴

### ライブラリの目的

**pynput**は、Pythonでキーボードとマウスの入力デバイスを**監視（モニタリング）**および**制御（コントロール）**するためのクロスプラットフォームライブラリです。

主な機能：
- **入力監視**: キーボード/マウスイベントのリアルタイムキャプチャ
- **入力制御**: プログラムからの仮想キー入力・マウス操作の送信
- **グローバルフック**: アプリケーションがフォーカスを持っていなくてもイベントを受信

### 対応OS

| OS | バックエンド | 備考 |
|---|---|---|
| **macOS** | darwin | Quartz Event Services使用 |
| **Windows** | win32 | Windows API使用 |
| **Linux (X11)** | xorg | X11プロトコル使用 |
| **Linux (uinput)** | uinput | root権限必要、キーボードのみ |

### インストール方法

```bash
# pipでインストール
pip install pynput

# condaでインストール
conda install -c conda-forge pynput

# 特定バージョンのインストール
pip install pynput==1.8.1
```

**最新バージョン**: 1.8.1 (2025年3月リリース)

---

## 2. キーボード入力監視の仕組み

### Listenerクラスの使い方

`pynput.keyboard.Listener`はキーボードイベントを監視するためのクラスで、`threading.Thread`を継承しています。

```python
from pynput import keyboard

# 基本的な使い方（コンテキストマネージャー）
with keyboard.Listener(
        on_press=on_press_callback,
        on_release=on_release_callback) as listener:
    listener.join()  # リスナーが停止するまでブロック

# 非ブロッキングモード
listener = keyboard.Listener(
    on_press=on_press_callback,
    on_release=on_release_callback)
listener.start()  # バックグラウンドスレッドで開始
# ... 他の処理 ...
listener.stop()   # 停止
```

### on_press / on_release コールバック

コールバック関数は、キーイベント発生時に呼び出されます。

```python
def on_press(key):
    """キーが押されたときに呼ばれる
    
    Args:
        key: Key（特殊キー）、KeyCode（通常キー）、またはNone（不明なキー）
    
    Returns:
        False を返すとリスナーが停止
    """
    print(f'Key pressed: {key}')

def on_release(key):
    """キーが離されたときに呼ばれる
    
    Args:
        key: Key（特殊キー）、KeyCode（通常キー）、またはNone（不明なキー）
    
    Returns:
        False を返すとリスナーが停止
    """
    print(f'Key released: {key}')
    if key == keyboard.Key.esc:
        return False  # Escキーで停止
```

**バージョン1.8.0以降の新機能**: `injected`パラメータで仮想入力を検出可能

```python
def on_press(key, injected):
    """injected=True の場合、他のプログラムからの仮想入力"""
    if injected:
        print(f'Fake key: {key}')
    else:
        print(f'Real key: {key}')
```

### 特殊キーとchar属性の違い

| キータイプ | クラス | 例 | アクセス方法 |
|---|---|---|---|
| **通常キー** | `KeyCode` | 'a', '1', '@' | `key.char` |
| **特殊キー** | `Key` | Shift, Ctrl, F1 | `key == keyboard.Key.shift` |
| **不明なキー** | `None` | 一部の特殊キー | 直接比較不可 |

```python
def on_press(key):
    try:
        # 通常キー（KeyCode）の場合
        print(f'Alphanumeric key: {key.char}')
    except AttributeError:
        # 特殊キー（Key）の場合
        print(f'Special key: {key}')
```

### グローバルキーフックの仕組み

pynputは各OSのネイティブAPIを使用してシステムレベルでキーイベントをフックします：

```
┌─────────────────────────────────────────────────────────────┐
│                     アプリケーション                          │
├─────────────────────────────────────────────────────────────┤
│                      pynput Listener                        │
├───────────────┬───────────────┬───────────────┬────────────┤
│    darwin     │    win32      │     xorg      │   uinput   │
│  (macOS)      │  (Windows)    │   (Linux X)   │  (Linux)   │
├───────────────┼───────────────┼───────────────┼────────────┤
│ CGEventTap    │ SetWindowsHook│ XRecord       │ /dev/uinput│
│ Quartz        │ Ex            │ Extension     │            │
└───────────────┴───────────────┴───────────────┴────────────┘
```

**特徴**:
- コールバックはOSの操作スレッドから直接呼び出される（特にWindows）
- 長時間実行する処理をコールバック内で行うと、システム全体の入力がフリーズする可能性
- 推奨: キューを使用して別スレッドで処理

---

## 3. 主要なAPI

### keyboard.Listener

```python
class pynput.keyboard.Listener(
    on_press=None,      # キー押下時のコールバック
    on_release=None,    # キー解放時のコールバック  
    suppress=False,     # イベントをシステムに伝播させないか
    **kwargs            # プラットフォーム固有オプション
)
```

**主要なメソッド**:
| メソッド | 説明 |
|---|---|
| `start()` | リスナーを開始（バックグラウンドスレッド） |
| `stop()` | リスナーを停止 |
| `join()` | スレッドの終了を待機 |
| `wait()` | リスナーの準備完了を待機 |
| `running` | 実行中かどうか（プロパティ） |
| `canonical(key)` | キーを正規化（HotKey用） |

**プラットフォーム固有オプション**:
```python
# macOS: イベントの変更・抑制
keyboard.Listener(
    darwin_intercept=lambda event_type, event: event
)

# Windows: イベントフィルタ
keyboard.Listener(
    win32_event_filter=lambda msg, data: None
)
```

### keyboard.Key

特殊キーを表すEnum。全プラットフォームで利用可能なキー：

```python
from pynput.keyboard import Key

# 修飾キー
Key.shift      # 汎用Shift
Key.shift_l    # 左Shift
Key.shift_r    # 右Shift
Key.ctrl       # 汎用Ctrl
Key.ctrl_l     # 左Ctrl
Key.ctrl_r     # 右Ctrl
Key.alt        # 汎用Alt
Key.alt_l      # 左Alt（macOSではOption）
Key.alt_r      # 右Alt
Key.alt_gr     # AltGr
Key.cmd        # Command（macOS）/ Windows（Windows）
Key.cmd_l      # 左Command/Windows
Key.cmd_r      # 右Command/Windows

# ファンクションキー
Key.f1 ~ Key.f20

# ナビゲーションキー
Key.up, Key.down, Key.left, Key.right
Key.home, Key.end
Key.page_up, Key.page_down

# 編集キー
Key.backspace
Key.delete
Key.enter
Key.tab
Key.space
Key.insert

# ロックキー
Key.caps_lock
Key.num_lock
Key.scroll_lock

# その他
Key.esc
Key.print_screen
Key.pause
Key.menu

# メディアキー
Key.media_play_pause
Key.media_volume_up
Key.media_volume_down
Key.media_volume_mute
Key.media_next
Key.media_previous
```

### keyboard.KeyCode

通常のキー（文字キー）を表すクラス：

```python
from pynput.keyboard import KeyCode

# 文字から作成
key = KeyCode.from_char('a')

# 仮想キーコードから作成
key = KeyCode.from_vk(65)  # 'A'のキーコード

# デッドキー（アクセント記号など）から作成
key = KeyCode.from_dead('~')

# 属性
key.char       # 文字（'a', 'A'など）
key.vk         # 仮想キーコード
key.is_dead    # デッドキーかどうか
```

### keyboard.Controller

キーボード入力を送信するためのクラス：

```python
from pynput.keyboard import Key, Controller

keyboard = Controller()

# 単一キーの押下・解放
keyboard.press(Key.space)
keyboard.release(Key.space)

# 文字の入力
keyboard.press('a')
keyboard.release('a')

# tap(): 押して離す
keyboard.tap(Key.enter)

# type(): 文字列を入力
keyboard.type('Hello, World!')

# 修飾キーとの組み合わせ
with keyboard.pressed(Key.ctrl):
    keyboard.press('c')  # Ctrl+C
    keyboard.release('c')

# 複数の修飾キー
with keyboard.pressed(Key.ctrl, Key.shift):
    keyboard.tap('n')  # Ctrl+Shift+N

# 現在押されている修飾キーの確認
with keyboard.modifiers as modifiers:
    if Key.shift in modifiers:
        print("Shift is pressed")
```

---

## 4. macOSでの利用時の注意点

### アクセシビリティ権限の設定方法

macOSではセキュリティ上の理由からキーボード監視に**アクセシビリティ権限**が必要です。

#### 権限確認コード

```python
from pynput import keyboard

# IS_TRUSTED属性で権限を確認
if keyboard.Listener.IS_TRUSTED:
    print("アクセシビリティ権限が付与されています")
else:
    print("アクセシビリティ権限が必要です")
```

#### 権限付与手順

1. **システム設定を開く**
   - Apple メニュー → システム設定（または環境設定）

2. **プライバシーとセキュリティに移動**
   - プライバシーとセキュリティ → アクセシビリティ

3. **アプリケーションを追加**
   - 鍵アイコンをクリックしてロック解除
   - 「+」ボタンでアプリケーションを追加

4. **追加すべきアプリケーション**
   - **ターミナルから実行する場合**: Terminal.app または iTerm.app
   - **VS Codeから実行する場合**: Visual Studio Code.app
   - **PyCharmから実行する場合**: PyCharm.app
   - **パッケージ化されたアプリ**: そのアプリ自体

#### 自動的に権限リクエストを表示

```python
import subprocess
import sys

def request_accessibility_permission():
    """アクセシビリティ権限のリクエストダイアログを表示"""
    script = '''
    tell application "System Preferences"
        activate
        set current pane to pane "com.apple.preference.security"
        reveal anchor "Privacy_Accessibility" of pane "com.apple.preference.security"
    end tell
    '''
    subprocess.run(['osascript', '-e', script])
```

### セキュリティ制限

| macOSバージョン | 制限事項 |
|---|---|
| Mojave以前 | アクセシビリティ権限のみ必要 |
| Mojave以降 | ターミナルアプリへの権限も必要 |
| Monterey以降 | 入力監視の許可も別途必要な場合あり |

### よくある問題と解決策

```python
# 問題: 権限があるのにイベントを受信できない
# 解決: Python環境自体に権限が必要

# ターミナルの権限確認
# システム設定 → プライバシーとセキュリティ → アクセシビリティ
# Terminal.app にチェックが入っているか確認

# IDEの権限確認
# VS Code.app や PyCharm.app にもチェックが必要
```

---

## 5. 非同期処理との組み合わせ

### スレッドモデル

pynputの`Listener`は`threading.Thread`を継承しており、コールバックは専用スレッドで実行されます。

```
┌─────────────────────┐     ┌─────────────────────┐
│    Main Thread      │     │   Listener Thread   │
│                     │     │                     │
│  listener.start() ──┼────►│  OS Event Loop      │
│                     │     │       │             │
│  listener.join()    │     │       ▼             │
│       │             │     │  on_press()         │
│       ▼             │     │  on_release()       │
│  (waiting...)       │     │       │             │
│                     │◄────┼───────┘             │
└─────────────────────┘     └─────────────────────┘
```

### asyncioとの連携方法

#### 方法1: キューを使用した連携

```python
import asyncio
import queue
from pynput import keyboard

# スレッドセーフなキュー
key_queue = queue.Queue()

def on_press(key):
    """コールバックでキューに追加"""
    key_queue.put(('press', key))

def on_release(key):
    """コールバックでキューに追加"""
    key_queue.put(('release', key))
    if key == keyboard.Key.esc:
        key_queue.put(None)  # 終了シグナル
        return False

async def process_keys():
    """非同期でキーイベントを処理"""
    loop = asyncio.get_event_loop()
    
    while True:
        # ブロッキング操作をスレッドプールで実行
        event = await loop.run_in_executor(None, key_queue.get)
        
        if event is None:
            break
            
        event_type, key = event
        print(f'Async processing: {event_type} - {key}')
        
        # ここで非同期処理を実行
        await asyncio.sleep(0.01)

async def main():
    # リスナーを開始
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)
    listener.start()
    
    # キー処理タスクを実行
    await process_keys()
    
    listener.stop()

if __name__ == '__main__':
    asyncio.run(main())
```

#### 方法2: asyncio.Queue を使用

```python
import asyncio
from pynput import keyboard

class AsyncKeyboardListener:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.listener = None
        self.loop = None
    
    def _on_press(self, key):
        """同期コールバック → 非同期キューへ"""
        if self.loop:
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait, ('press', key))
    
    def _on_release(self, key):
        """同期コールバック → 非同期キューへ"""
        if self.loop:
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait, ('release', key))
        if key == keyboard.Key.esc:
            if self.loop:
                self.loop.call_soon_threadsafe(
                    self.queue.put_nowait, None)
            return False
    
    async def start(self):
        """リスナーを開始"""
        self.loop = asyncio.get_event_loop()
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release)
        self.listener.start()
    
    async def stop(self):
        """リスナーを停止"""
        if self.listener:
            self.listener.stop()
    
    async def get_event(self):
        """次のイベントを非同期で取得"""
        return await self.queue.get()
    
    async def __aiter__(self):
        """非同期イテレータとして使用"""
        while True:
            event = await self.get_event()
            if event is None:
                break
            yield event

# 使用例
async def main():
    listener = AsyncKeyboardListener()
    await listener.start()
    
    print("Press ESC to exit")
    async for event_type, key in listener:
        print(f'{event_type}: {key}')
    
    await listener.stop()

asyncio.run(main())
```

#### 方法3: janus ライブラリを使用

```python
# pip install janus
import asyncio
import janus
from pynput import keyboard

async def main():
    queue = janus.Queue()
    
    def on_press(key):
        queue.sync_q.put(('press', key))
    
    def on_release(key):
        queue.sync_q.put(('release', key))
        if key == keyboard.Key.esc:
            queue.sync_q.put(None)
            return False
    
    listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release)
    listener.start()
    
    while True:
        event = await queue.async_q.get()
        if event is None:
            break
        print(f'Event: {event}')
    
    listener.stop()
    queue.close()
    await queue.wait_closed()

asyncio.run(main())
```

---

## 6. 実践的なコード例

### 基本的なキー監視

```python
from pynput import keyboard

def on_press(key):
    try:
        print(f'Key pressed: {key.char}')
    except AttributeError:
        print(f'Special key pressed: {key}')

def on_release(key):
    print(f'Key released: {key}')
    if key == keyboard.Key.esc:
        print('Exiting...')
        return False

# リスナーを開始
with keyboard.Listener(
        on_press=on_press,
        on_release=on_release) as listener:
    print('Listening for keyboard events. Press ESC to exit.')
    listener.join()
```

### 特定キーの検出

```python
from pynput import keyboard

# 検出したいキーを定義
TARGET_KEYS = {'a', 'b', 'c'}
SPECIAL_TARGETS = {keyboard.Key.enter, keyboard.Key.space}

def on_press(key):
    # 通常キーの検出
    try:
        if key.char in TARGET_KEYS:
            print(f'Target key detected: {key.char}')
    except AttributeError:
        pass
    
    # 特殊キーの検出
    if key in SPECIAL_TARGETS:
        print(f'Special target detected: {key}')

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
```

### 修飾キーの扱い

```python
from pynput import keyboard

class ModifierTracker:
    def __init__(self):
        self.current_modifiers = set()
    
    def on_press(self, key):
        # 修飾キーを追跡
        if key in {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}:
            self.current_modifiers.add('shift')
        elif key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            self.current_modifiers.add('ctrl')
        elif key in {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r}:
            self.current_modifiers.add('alt')
        elif key in {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r}:
            self.current_modifiers.add('cmd')
        else:
            # 通常キーが押された場合、現在の修飾キーと共に表示
            try:
                if self.current_modifiers:
                    print(f'Modifiers: {self.current_modifiers} + {key.char}')
                else:
                    print(f'Key: {key.char}')
            except AttributeError:
                print(f'Special key: {key}')
    
    def on_release(self, key):
        # 修飾キーを解除
        if key in {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}:
            self.current_modifiers.discard('shift')
        elif key in {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}:
            self.current_modifiers.discard('ctrl')
        elif key in {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r}:
            self.current_modifiers.discard('alt')
        elif key in {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r}:
            self.current_modifiers.discard('cmd')
        
        if key == keyboard.Key.esc:
            return False

tracker = ModifierTracker()
with keyboard.Listener(
        on_press=tracker.on_press,
        on_release=tracker.on_release) as listener:
    listener.join()
```

### 組み合わせキー（ホットキー）の検出

#### 方法1: HotKeyクラスを使用

```python
from pynput import keyboard

def on_activate():
    print('Hotkey activated: Ctrl+Alt+H')

def for_canonical(f):
    """キーを正規化してからコールバックに渡す"""
    return lambda k: f(listener.canonical(k))

hotkey = keyboard.HotKey(
    keyboard.HotKey.parse('<ctrl>+<alt>+h'),
    on_activate)

with keyboard.Listener(
        on_press=for_canonical(hotkey.press),
        on_release=for_canonical(hotkey.release)) as listener:
    print('Press Ctrl+Alt+H to activate. Press Ctrl+C to exit.')
    listener.join()
```

#### 方法2: GlobalHotKeysを使用

```python
from pynput import keyboard

def on_ctrl_alt_h():
    print('Ctrl+Alt+H pressed!')

def on_ctrl_alt_s():
    print('Ctrl+Alt+S pressed!')

def on_cmd_q():
    print('Cmd+Q pressed! Exiting...')
    return False

# 複数のホットキーを一度に登録
hotkeys = keyboard.GlobalHotKeys({
    '<ctrl>+<alt>+h': on_ctrl_alt_h,
    '<ctrl>+<alt>+s': on_ctrl_alt_s,
    '<cmd>+q': on_cmd_q,
})

with hotkeys as h:
    print('Hotkeys registered. Press Cmd+Q to exit.')
    h.join()
```

#### 方法3: 手動での組み合わせキー検出

```python
from pynput import keyboard

class HotkeyDetector:
    def __init__(self):
        self.pressed_keys = set()
    
    def on_press(self, key):
        self.pressed_keys.add(key)
        
        # Ctrl + Shift + A の検出
        if (keyboard.Key.ctrl in self.pressed_keys or 
            keyboard.Key.ctrl_l in self.pressed_keys or
            keyboard.Key.ctrl_r in self.pressed_keys):
            if (keyboard.Key.shift in self.pressed_keys or
                keyboard.Key.shift_l in self.pressed_keys or
                keyboard.Key.shift_r in self.pressed_keys):
                try:
                    if key.char == 'a':
                        print('Ctrl+Shift+A detected!')
                except AttributeError:
                    pass
    
    def on_release(self, key):
        try:
            self.pressed_keys.remove(key)
        except KeyError:
            pass
        
        if key == keyboard.Key.esc:
            return False

detector = HotkeyDetector()
with keyboard.Listener(
        on_press=detector.on_press,
        on_release=detector.on_release) as listener:
    listener.join()
```

### キーログの記録（タイムスタンプ付き）

```python
from pynput import keyboard
from datetime import datetime
import json

class KeyLogger:
    def __init__(self, output_file='keylog.json'):
        self.events = []
        self.output_file = output_file
    
    def on_press(self, key):
        event = {
            'timestamp': datetime.now().isoformat(),
            'event': 'press',
            'key': self._key_to_string(key)
        }
        self.events.append(event)
        print(f"[{event['timestamp']}] Press: {event['key']}")
    
    def on_release(self, key):
        event = {
            'timestamp': datetime.now().isoformat(),
            'event': 'release',
            'key': self._key_to_string(key)
        }
        self.events.append(event)
        
        if key == keyboard.Key.esc:
            self.save()
            return False
    
    def _key_to_string(self, key):
        try:
            return key.char
        except AttributeError:
            return str(key)
    
    def save(self):
        with open(self.output_file, 'w') as f:
            json.dump(self.events, f, indent=2)
        print(f'Saved {len(self.events)} events to {self.output_file}')

logger = KeyLogger()
with keyboard.Listener(
        on_press=logger.on_press,
        on_release=logger.on_release) as listener:
    print('Logging keys. Press ESC to stop and save.')
    listener.join()
```

### Eventsクラスを使った同期的なイベント処理

```python
from pynput import keyboard

# 単一イベントの取得（タイムアウト付き）
with keyboard.Events() as events:
    print('Press any key within 5 seconds...')
    event = events.get(5.0)  # 5秒待機
    
    if event is None:
        print('No key pressed')
    else:
        print(f'Event: {event}')

# イベントの反復処理
with keyboard.Events() as events:
    print('Press ESC to exit')
    for event in events:
        if event.key == keyboard.Key.esc:
            break
        print(f'Event: {event}')
```

---

## 7. よくあるエラーと対処法

### エラー1: アクセシビリティ権限エラー (macOS)

```
This process is not trusted! Input event monitoring will not be possible 
until it is added to accessibility clients.
```

**対処法**:
```python
# 権限確認
from pynput import keyboard
print(f"Trusted: {keyboard.Listener.IS_TRUSTED}")

# システム設定 → プライバシーとセキュリティ → アクセシビリティ
# で実行するアプリケーション（Terminal, VS Code等）を追加
```

### エラー2: AttributeError: 'Key' object has no attribute 'char'

```python
# 問題のあるコード
def on_press(key):
    print(key.char)  # 特殊キーで AttributeError

# 解決策
def on_press(key):
    try:
        print(f'Character: {key.char}')
    except AttributeError:
        print(f'Special key: {key}')
```

### エラー3: リスナーが即座に終了する

```python
# 問題のあるコード
listener = keyboard.Listener(on_press=on_press)
listener.start()
# プログラムがすぐ終了

# 解決策1: join() を使用
listener = keyboard.Listener(on_press=on_press)
listener.start()
listener.join()  # リスナーが停止するまで待機

# 解決策2: コンテキストマネージャーを使用
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
```

### エラー4: コールバックで例外が発生するとリスナーが停止する

```python
# 問題
def on_press(key):
    raise ValueError("Error!")  # リスナーが停止

# 解決策: 例外をキャッチしてログ出力
def on_press(key):
    try:
        # 処理
        pass
    except Exception as e:
        print(f'Error in callback: {e}')
        # return False しなければリスナーは継続
```

### エラー5: ImportError（パッケージャー使用時）

```
ImportError: cannot import name '_darwin' from 'pynput.keyboard'
```

**対処法** (PyInstaller):
```python
# spec ファイルまたは --hidden-import で明示的に追加
# pyinstaller --hidden-import pynput.keyboard._darwin your_script.py

# または spec ファイルに追加
hiddenimports = [
    'pynput.keyboard._darwin',
    'pynput.mouse._darwin',
    'pynput._util.darwin',
]
```

### エラー6: X11/Xorgエラー (Linux)

```
Xlib.error.DisplayNameError: Bad display name ""
```

**対処法**:
```bash
# DISPLAY環境変数を設定
export DISPLAY=:0
python your_script.py

# または uinput バックエンドを使用（root権限必要）
sudo PYNPUT_BACKEND_KEYBOARD=uinput python your_script.py
```

### エラー7: 文字が正しく取得できない

```python
# 一部の言語や特殊文字で問題が発生する場合

def on_press(key):
    # vk (virtual key code) を使用
    if hasattr(key, 'vk'):
        print(f'Virtual key code: {key.vk}')
    
    # または KeyCode.from_vk() で変換
    if hasattr(key, 'vk') and key.vk is not None:
        reconstructed = keyboard.KeyCode.from_vk(key.vk)
        print(f'Reconstructed: {reconstructed}')
```

---

## 8. ベストプラクティス

### 1. コールバックは軽量に保つ

```python
import queue
import threading

# ❌ 悪い例：コールバック内で重い処理
def on_press(key):
    time.sleep(1)  # システム入力がフリーズ！
    process_heavy_task(key)

# ✅ 良い例：キューを使って別スレッドで処理
event_queue = queue.Queue()

def on_press(key):
    event_queue.put(key)  # 即座に返る

def worker():
    while True:
        key = event_queue.get()
        if key is None:
            break
        process_heavy_task(key)

# ワーカースレッドを開始
worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()
```

### 2. 適切なリソース管理

```python
# ✅ コンテキストマネージャーを使用
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()

# または明示的なstart/stop
listener = keyboard.Listener(on_press=on_press)
try:
    listener.start()
    # 処理
finally:
    listener.stop()
```

### 3. 例外処理を適切に行う

```python
def on_press(key):
    try:
        # メイン処理
        handle_key(key)
    except Exception as e:
        # ログに記録してリスナーは継続
        logging.exception(f'Error handling key {key}')
        # return False しなければリスナーは継続

# 例外を main スレッドで受け取る
listener = keyboard.Listener(on_press=on_press)
listener.start()
try:
    listener.join()
except MyCustomException as e:
    print(f'Custom exception: {e}')
```

### 4. クロスプラットフォーム対応

```python
import platform

def get_modifier_key():
    """OSに応じた主要修飾キーを返す"""
    if platform.system() == 'Darwin':
        return keyboard.Key.cmd  # macOSはCommand
    else:
        return keyboard.Key.ctrl  # Windows/LinuxはCtrl

# プラットフォーム検出
def on_press(key):
    if platform.system() == 'Darwin':
        # macOS固有の処理
        pass
    elif platform.system() == 'Windows':
        # Windows固有の処理
        pass
    else:
        # Linux固有の処理
        pass
```

### 5. デバッグとログ出力

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def on_press(key):
    logging.debug(f'Key pressed: {key}, type: {type(key)}')
    if hasattr(key, 'vk'):
        logging.debug(f'Virtual key: {key.vk}')
    if hasattr(key, 'char'):
        logging.debug(f'Character: {key.char}')
```

### 6. 状態管理にクラスを使用

```python
from dataclasses import dataclass, field
from typing import Set
from pynput import keyboard

@dataclass
class KeyboardState:
    pressed_keys: Set = field(default_factory=set)
    modifiers: Set[str] = field(default_factory=set)
    running: bool = True
    
    def update_modifiers(self, key, pressed: bool):
        modifier_map = {
            keyboard.Key.shift: 'shift',
            keyboard.Key.shift_l: 'shift',
            keyboard.Key.shift_r: 'shift',
            keyboard.Key.ctrl: 'ctrl',
            keyboard.Key.ctrl_l: 'ctrl',
            keyboard.Key.ctrl_r: 'ctrl',
            keyboard.Key.alt: 'alt',
            keyboard.Key.alt_l: 'alt',
            keyboard.Key.alt_r: 'alt',
            keyboard.Key.cmd: 'cmd',
            keyboard.Key.cmd_l: 'cmd',
            keyboard.Key.cmd_r: 'cmd',
        }
        if key in modifier_map:
            if pressed:
                self.modifiers.add(modifier_map[key])
            else:
                self.modifiers.discard(modifier_map[key])

state = KeyboardState()

def on_press(key):
    state.pressed_keys.add(key)
    state.update_modifiers(key, True)

def on_release(key):
    state.pressed_keys.discard(key)
    state.update_modifiers(key, False)
```

---

## 9. 制限事項と代替ライブラリ

### pynputの制限事項

| プラットフォーム | 制限事項 |
|---|---|
| **macOS** | アクセシビリティ権限必須、サンドボックス化されたアプリでは動作しない場合あり |
| **Windows** | 他プロセスからの仮想イベントを受信できない場合あり、キーの長押し状態が正しく再現されない |
| **Linux (X11)** | Xサーバーが必要、Waylandでは制限的にしか動作しない |
| **Linux (uinput)** | root権限必要、キーボードのみ対応 |
| **全般** | 一度stopしたListenerは再利用不可（新規作成が必要） |

### 代替ライブラリとの比較

| ライブラリ | 特徴 | 対応OS | 用途 |
|---|---|---|---|
| **pynput** | クロスプラットフォーム、監視+制御 | Windows/macOS/Linux | 汎用 |
| **keyboard** | シンプルなAPI、ホットキー重視 | Windows/Linux | ホットキー |
| **pyautogui** | GUI自動化全般 | Windows/macOS/Linux | 自動化 |
| **pyHook** | Windows専用、低レベルAPI | Windows | Windows開発 |
| **Quartz** | macOS専用、ネイティブAPI | macOS | macOS開発 |

### keyboard ライブラリとの比較

```python
# pynputでの実装
from pynput import keyboard

def on_press(key):
    try:
        if key.char == 'a':
            print('A pressed')
    except AttributeError:
        pass

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()

# keyboard ライブラリでの実装
import keyboard  # pip install keyboard

keyboard.on_press_key('a', lambda _: print('A pressed'))
keyboard.wait('esc')
```

| 機能 | pynput | keyboard |
|---|---|---|
| キー監視 | ✅ | ✅ |
| キー制御 | ✅ | ✅ |
| マウス監視 | ✅ | ❌ |
| マウス制御 | ✅ | ❌ |
| macOS対応 | ✅ | ⚠️ (制限あり) |
| root不要 (Linux) | ✅ (X11) | ❌ |
| シンプルなAPI | ⚠️ | ✅ |

### 選定ガイドライン

```
Q: macOSでキーボード監視が必要？
├─ Yes → pynput を使用
└─ No
    Q: マウス監視も必要？
    ├─ Yes → pynput を使用
    └─ No
        Q: シンプルなホットキー登録のみ？
        ├─ Yes → keyboard を検討
        └─ No → pynput を使用
```

---

## 参考リンク

- [pynput公式ドキュメント](https://pynput.readthedocs.io/en/latest/)
- [PyPI - pynput](https://pypi.org/project/pynput/)
- [GitHub - moses-palmer/pynput](https://github.com/moses-palmer/pynput)
- [Apple Developer - Quartz Event Services](https://developer.apple.com/documentation/coregraphics/quartz_event_services)
- [Microsoft Docs - Keyboard Input](https://docs.microsoft.com/en-us/windows/win32/inputdev/keyboard-input)
