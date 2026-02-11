# pynput によるキー入力監視 詳細リサーチレポート

## 1. pynputの概要と特徴

### 1.1 ライブラリの目的

**pynput** は、Pythonでキーボードとマウスを**監視（listen）および制御（control）**するためのクロスプラットフォームライブラリです。

```python
# インストール
pip install pynput
```

### 1.2 対応OS

| OS | 対応状況 | 備考 |
|---|---|---|
| **macOS** | ✅ 完全対応 | Quartz フレームワーク使用 |
| **Windows** | ✅ 完全対応 | Win32 API 使用 |
| **Linux** | ✅ 対応 | Xlib (X11) / uinput 使用 |

### 1.3 主要機能

```
pynput
├── keyboard
│   ├── Listener   → キーボードイベントの監視
│   └── Controller → キーボード入力のシミュレート
└── mouse
    ├── Listener   → マウスイベントの監視
    └── Controller → マウス操作のシミュレート
```

---

## 2. キーボード入力監視の仕組み

### 2.1 グローバルキーフックの仕組み

pynputは**グローバルキーフック（グローバルイベントリスナー）**を使用して、OS全体のキーボードイベントを捕捉します。

```
┌─────────────────────────────────────────────────────────────┐
│                        OS レベル                            │
│  ┌─────────┐     ┌─────────────┐     ┌─────────────────┐  │
│  │ キーボード │ ──▶ │  OS イベント  │ ──▶ │ アクティブアプリ   │  │
│  │ ハードウェア│     │   システム    │     │  (エディタ等)    │  │
│  └─────────┘     └──────┬──────┘     └─────────────────┘  │
│                         │                                   │
│                         │ フック                             │
│                         ▼                                   │
│               ┌─────────────────┐                          │
│               │   pynput        │                          │
│               │   Listener      │                          │
│               └─────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Listenerクラスの使い方

`keyboard.Listener`は`threading.Thread`を継承したクラスで、**別スレッドでイベント監視**を行います。

```python
from pynput import keyboard

def on_press(key):
    """キーが押されたときに呼ばれるコールバック"""
    print(f"押された: {key}")

def on_release(key):
    """キーが離されたときに呼ばれるコールバック"""
    print(f"離された: {key}")
    if key == keyboard.Key.esc:
        return False  # Falseを返すとリスナー停止

# リスナーの起動（3つの方法）

# 方法1: コンテキストマネージャー（推奨）
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

# 方法2: 非ブロッキング起動
listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()  # 別スレッドで起動
# ... 他の処理 ...
listener.join()   # 終了を待つ

# 方法3: 明示的な停止
listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()
# ... 何かの条件で ...
listener.stop()   # 明示的に停止
```

### 2.3 on_press / on_release コールバック

```python
def on_press(key):
    """
    引数:
        key: keyboard.Key または keyboard.KeyCode オブジェクト
    
    戻り値:
        None  → 監視を継続
        False → 監視を停止
    """
    pass

def on_release(key):
    """
    on_press と同様の仕様
    """
    pass
```

### 2.4 特殊キーと通常キーの違い

```python
from pynput import keyboard

def on_press(key):
    # 通常の文字キー → KeyCode オブジェクト
    # 特殊キー → Key enum
    
    if isinstance(key, keyboard.KeyCode):
        # 通常キー（a, b, 1, @, など）
        print(f"通常キー: {key.char}")  # key.char で文字を取得
    
    elif isinstance(key, keyboard.Key):
        # 特殊キー（Enter, Shift, Ctrl, など）
        print(f"特殊キー: {key.name}")  # key.name で名前を取得

# より簡潔な方法
def on_press_simple(key):
    try:
        # 通常キー
        key_char = key.char
        print(f"文字: {key_char}")
    except AttributeError:
        # 特殊キー（char属性がない）
        print(f"特殊キー: {key}")
```

---

## 3. 主要なAPI

### 3.1 keyboard.Key（特殊キーのEnum）

```python
from pynput.keyboard import Key

# 主要な特殊キー
Key.enter      # Enter/Return
Key.space      # スペース
Key.backspace  # Backspace
Key.tab        # Tab
Key.esc        # Escape
Key.delete     # Delete

# 修飾キー
Key.shift      # Shift
Key.shift_l    # 左Shift
Key.shift_r    # 右Shift
Key.ctrl       # Control
Key.ctrl_l     # 左Control
Key.ctrl_r     # 右Control
Key.alt        # Alt/Option
Key.alt_l      # 左Alt
Key.alt_r      # 右Alt
Key.cmd        # Command (macOS) / Windows key
Key.cmd_l      # 左Command
Key.cmd_r      # 右Command

# 矢印キー
Key.up, Key.down, Key.left, Key.right

# ファンクションキー
Key.f1, Key.f2, ..., Key.f20

# その他
Key.caps_lock  # Caps Lock
Key.num_lock   # Num Lock
Key.scroll_lock # Scroll Lock
Key.insert     # Insert
Key.home, Key.end
Key.page_up, Key.page_down
Key.print_screen
Key.pause
```

### 3.2 keyboard.KeyCode（通常キー）

```python
from pynput.keyboard import KeyCode

# KeyCodeの生成方法
key_a = KeyCode.from_char('a')
key_at = KeyCode.from_char('@')

# 属性
key.char    # 文字（'a', '1', '@', など）
key.vk      # 仮想キーコード（OS依存の数値）
```

### 3.3 keyboard.Controller（キー送信）

```python
from pynput.keyboard import Controller, Key

keyboard_controller = Controller()

# 単一キーの押下と解放
keyboard_controller.press('a')
keyboard_controller.release('a')

# 便利メソッド
keyboard_controller.tap('a')  # press + release を一度に

# 文字列の入力
keyboard_controller.type('Hello, World!')

# 特殊キー
keyboard_controller.press(Key.enter)
keyboard_controller.release(Key.enter)

# 修飾キーとの組み合わせ（Ctrl+C）
with keyboard_controller.pressed(Key.ctrl):
    keyboard_controller.tap('c')
```

### 3.4 ホットキー検出（HotKey / GlobalHotKeys）

```python
from pynput import keyboard

# 方法1: HotKey クラス
def on_activate():
    print("Ctrl+Alt+H が押されました！")

hotkey = keyboard.HotKey(
    keyboard.HotKey.parse('<ctrl>+<alt>+h'),
    on_activate
)

def on_press_for_hotkey(key):
    # canonical で正規化してからチェック
    hotkey.press(listener.canonical(key))

def on_release_for_hotkey(key):
    hotkey.release(listener.canonical(key))

with keyboard.Listener(
    on_press=on_press_for_hotkey,
    on_release=on_release_for_hotkey
) as listener:
    listener.join()

# 方法2: GlobalHotKeys（より簡潔）
def on_ctrl_alt_h():
    print("Ctrl+Alt+H が押されました！")

def on_ctrl_shift_q():
    print("終了します")
    return False

with keyboard.GlobalHotKeys({
    '<ctrl>+<alt>+h': on_ctrl_alt_h,
    '<ctrl>+<shift>+q': on_ctrl_shift_q,
}) as hotkeys:
    hotkeys.join()
```

---

## 4. macOSでの利用時の注意点

### 4.1 アクセシビリティ権限の設定

macOSでは、pynputがグローバルキーイベントを取得するために**アクセシビリティ権限**が必要です。

```
設定手順:
1. システム設定を開く
2. プライバシーとセキュリティ → アクセシビリティ
3. 実行するアプリケーションを許可リストに追加
   - ターミナル.app
   - iTerm.app
   - VS Code
   - PyCharm
   など
```

### 4.2 権限の確認

```python
from pynput import keyboard

# macOSでの権限確認
if hasattr(keyboard.Listener, 'IS_TRUSTED'):
    if keyboard.Listener.IS_TRUSTED:
        print("✅ アクセシビリティ権限があります")
    else:
        print("❌ アクセシビリティ権限がありません")
        print("   システム設定 → プライバシーとセキュリティ → アクセシビリティ で許可してください")
```

### 4.3 よくある問題

| 症状 | 原因 | 対処法 |
|---|---|---|
| キーが検出されない | 権限なし | アクセシビリティ設定を確認 |
| 最初は動いたが突然動かなくなった | アプリ更新で権限がリセット | 再度許可を追加 |
| IDEで動かない | IDEに権限がない | IDE自体を許可リストに追加 |

---

## 5. 非同期処理との組み合わせ

### 5.1 スレッドモデル

pynputの`Listener`は**別スレッドで動作**します。asyncioと組み合わせる場合、スレッドセーフな方法でデータを受け渡す必要があります。

```
┌─────────────────┐         ┌─────────────────┐
│  メインスレッド    │         │  Listenerスレッド │
│  (asyncio)       │         │  (pynput)        │
│                  │         │                  │
│  ◀───────────── │  Queue  │ ◀──── キー入力   │
│  await queue.get│ ◀────── │  queue.put()    │
│                  │         │                  │
└─────────────────┘         └─────────────────┘
```

### 5.2 asyncio.Queue を使った連携

```python
import asyncio
from pynput import keyboard

# グローバル変数
loop: asyncio.AbstractEventLoop = None
key_queue: asyncio.Queue = None

def on_press(key):
    """キー押下時のコールバック（Listenerスレッドで実行）"""
    try:
        key_str = key.char if hasattr(key, 'char') and key.char else str(key)
    except AttributeError:
        key_str = str(key)
    
    # スレッドセーフにasyncioキューに追加
    asyncio.run_coroutine_threadsafe(key_queue.put(key_str), loop)

def on_release(key):
    if key == keyboard.Key.esc:
        asyncio.run_coroutine_threadsafe(key_queue.put(None), loop)
        return False

async def process_keys():
    """キューからキー情報を取得して処理（メインスレッドで実行）"""
    while True:
        key_str = await key_queue.get()
        if key_str is None:
            break
        print(f"処理: {key_str}")
        # ここでBLE送信などの非同期処理を行う

async def main():
    global loop, key_queue
    loop = asyncio.get_event_loop()
    key_queue = asyncio.Queue()
    
    # Listenerを起動
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    
    # キー処理ループ
    await process_keys()
    
    listener.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### 5.3 janus ライブラリを使った簡潔な方法

```python
import asyncio
import janus  # pip install janus
from pynput import keyboard

async def main():
    queue = janus.Queue()  # sync/asyncの両方に対応したキュー
    
    def on_press(key):
        # 同期側からput
        queue.sync_q.put(str(key))
    
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    while True:
        # 非同期側からget
        key_str = await queue.async_q.get()
        print(f"受信: {key_str}")

asyncio.run(main())
```

---

## 6. 実践的なコード例

### 6.1 基本的なキー監視

```python
from pynput import keyboard

def on_press(key):
    try:
        print(f"押下: '{key.char}'")
    except AttributeError:
        print(f"押下: {key}")

def on_release(key):
    if key == keyboard.Key.esc:
        print("終了")
        return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    print("キー入力を監視中... (Escで終了)")
    listener.join()
```

### 6.2 修飾キーの追跡

```python
from pynput import keyboard

class KeyTracker:
    def __init__(self):
        self.modifiers = {
            'shift': False,
            'ctrl': False,
            'alt': False,
            'cmd': False,
        }
    
    def on_press(self, key):
        # 修飾キーの状態を更新
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self.modifiers['shift'] = True
        elif key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.modifiers['ctrl'] = True
        elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.modifiers['alt'] = True
        elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            self.modifiers['cmd'] = True
        else:
            # 通常キーの処理
            mods = [k for k, v in self.modifiers.items() if v]
            mod_str = '+'.join(mods) + '+' if mods else ''
            
            try:
                key_str = key.char
            except AttributeError:
                key_str = key.name
            
            print(f"入力: {mod_str}{key_str}")
    
    def on_release(self, key):
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            self.modifiers['shift'] = False
        elif key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.modifiers['ctrl'] = False
        elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.modifiers['alt'] = False
        elif key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
            self.modifiers['cmd'] = False
        
        if key == keyboard.Key.esc:
            return False

tracker = KeyTracker()
with keyboard.Listener(on_press=tracker.on_press, on_release=tracker.on_release) as listener:
    listener.join()
```

### 6.3 特定キーのフィルタリング

```python
from pynput import keyboard

# 監視したいキーのセット
MONITORED_KEYS = {
    keyboard.Key.enter,
    keyboard.Key.space,
    keyboard.Key.backspace,
}

def on_press(key):
    # 特殊キーのフィルタリング
    if key in MONITORED_KEYS:
        print(f"監視対象キー: {key}")
        return
    
    # 英数字のみフィルタリング
    try:
        if key.char and key.char.isalnum():
            print(f"英数字: {key.char}")
    except AttributeError:
        pass

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
```

### 6.4 キーストロークのバッファリング

```python
from pynput import keyboard
import time

class KeyBuffer:
    def __init__(self, flush_interval=0.5):
        self.buffer = []
        self.last_key_time = time.time()
        self.flush_interval = flush_interval
    
    def on_press(self, key):
        current_time = time.time()
        
        # 一定時間経過していたらバッファをフラッシュ
        if current_time - self.last_key_time > self.flush_interval and self.buffer:
            self.flush()
        
        self.last_key_time = current_time
        
        try:
            self.buffer.append(key.char)
        except AttributeError:
            if key == keyboard.Key.space:
                self.buffer.append(' ')
            elif key == keyboard.Key.enter:
                self.flush()
                print("--- Enter ---")
            elif key == keyboard.Key.backspace and self.buffer:
                self.buffer.pop()
            elif key == keyboard.Key.esc:
                self.flush()
                return False
    
    def flush(self):
        if self.buffer:
            text = ''.join(self.buffer)
            print(f"バッファ送信: '{text}'")
            # ここでBLE送信などを行う
            self.buffer.clear()

buffer = KeyBuffer()
with keyboard.Listener(on_press=buffer.on_press) as listener:
    listener.join()
```

---

## 7. よくあるエラーと対処法

### 7.1 アクセシビリティ権限エラー

```
エラー: This process is not trusted! Input event monitoring will not be possible.
```

**対処法:** システム設定 → プライバシーとセキュリティ → アクセシビリティで実行アプリを許可

### 7.2 AttributeError

```python
# エラー: AttributeError: 'Key' object has no attribute 'char'

# 原因: 特殊キーには char 属性がない
def on_press(key):
    print(key.char)  # ← 特殊キーでエラー

# 対処法:
def on_press(key):
    try:
        char = key.char
    except AttributeError:
        char = None  # 特殊キー
```

### 7.3 リスナーが即座に終了する

```python
# 問題: プログラムがすぐ終了する
listener = keyboard.Listener(on_press=on_press)
listener.start()
# プログラム終了

# 対処法: join() で待機
listener = keyboard.Listener(on_press=on_press)
listener.start()
listener.join()  # ← これが必要

# または コンテキストマネージャー
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
```

### 7.4 PyInstallerでのImportError

```python
# PyInstallerやcx_Freezeでパッケージ化した際のエラー対策
# hidden imports を指定

# PyInstaller の場合:
# pyinstaller --hidden-import pynput.keyboard._darwin script.py
```

---

## 8. ベストプラクティス

### 8.1 コールバックは軽量に

```python
# ❌ 悪い例: コールバック内で重い処理
def on_press(key):
    # BLE送信など時間のかかる処理
    await send_via_ble(key)  # ブロックしてしまう

# ✅ 良い例: キューに積んで別で処理
def on_press(key):
    queue.put(key)  # 即座に返る
```

### 8.2 適切なリソース管理

```python
# ✅ コンテキストマネージャーを使用
with keyboard.Listener(...) as listener:
    listener.join()

# ✅ try-finally で確実に停止
listener = keyboard.Listener(...)
try:
    listener.start()
    # ...
finally:
    listener.stop()
```

### 8.3 例外処理

```python
def on_press(key):
    try:
        # 処理
        pass
    except Exception as e:
        print(f"エラー: {e}")
        # エラーが起きてもリスナーは継続
```

---

## 9. 制限事項と代替ライブラリ

### 9.1 pynputの制限

| 制限 | 詳細 |
|---|---|
| 権限が必要 | macOSではアクセシビリティ権限が必須 |
| 一部のキーが取れない | macOSのセキュリティ入力モード中は監視不可 |
| パスワード入力 | セキュリティ保護されたフィールドは監視不可 |
| 仮想環境 | VNC/RDP経由では動作しない場合がある |

### 9.2 代替ライブラリの比較

| ライブラリ | macOS | Windows | Linux | 特徴 |
|---|---|---|---|---|
| **pynput** | ✅ | ✅ | ✅ | クロスプラットフォーム、高機能 |
| **keyboard** | △ | ✅ | ✅ | シンプル、macOSはroot必要 |
| **pyautogui** | ✅ | ✅ | ✅ | GUI操作メイン、監視は限定的 |
| **pyobjc** | ✅ | ❌ | ❌ | macOS専用、低レベルAPI |

### 9.3 用途別の推奨

| 用途 | 推奨ライブラリ |
|---|---|
| macOSでキー監視 | **pynput**（本レポートの内容） |
| Windowsでキー監視 | pynput または keyboard |
| Linuxでキー監視（root可） | keyboard |
| 低レベル制御（macOS） | pyobjc |

---

## 10. まとめ

### pynputの特徴

- ✅ クロスプラットフォーム対応
- ✅ キーボードとマウスの監視・制御が可能
- ✅ 非同期処理との連携が容易
- ✅ macOSのCoreBluetoothと相性が良いbleakとの組み合わせに最適

### BLE送信との連携ポイント

1. **pynputのコールバックは軽量に** → キューに積むだけ
2. **asyncio.Queueでスレッド間通信** → `run_coroutine_threadsafe`を使用
3. **macOSではアクセシビリティ権限を忘れずに**

```
┌─────────────┐      Queue      ┌─────────────┐      BLE       ┌────────────┐
│  pynput     │ ──────────────▶ │   asyncio   │ ──────────────▶│  bleak     │
│  Listener   │   (thread-safe) │   main loop │    write_gatt  │  Client    │
└─────────────┘                 └─────────────┘                └────────────┘
```

---

## 参考リンク

- [pynput 公式ドキュメント](https://pynput.readthedocs.io/)
- [pynput GitHub リポジトリ](https://github.com/moses-palmer/pynput)
- [Python asyncio ドキュメント](https://docs.python.org/3/library/asyncio.html)
