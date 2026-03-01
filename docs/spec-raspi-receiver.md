# Raspberry Pi レシーバー仕様

## 1. 概要

Raspberry Pi上でBLE GATTサーバーを起動し、Macから送信されたキーイベントを受信する。
BLE通信とキー受信hookの部分は**ライブラリ（`ble-key-receiver`）**として分離し、
アプリケーション（LCD表示等）はライブラリのコールバックを利用して実装する。

## 2. レイヤー構成

```
┌─────────────────────────────────────────────┐
│          アプリケーション層                    │
│  (LCD表示 / ロガー / カスタムアプリ)           │
│                                             │
│  ライブラリのコールバックを実装するだけで       │
│  キー受信アプリを構築できる                    │
├─────────────────────────────────────────────┤
│          ble-key-receiver ライブラリ          │
│                                             │
│  ┌──────────────┐  ┌────────────────────┐   │
│  │ GATTServer   │  │   KeyReceiver      │   │
│  │              │──▶│                    │   │
│  │ BLE通信管理   │  │  コールバック管理     │   │
│  └──────────────┘  └────────────────────┘   │
├─────────────────────────────────────────────┤
│          共通定義 (common)                    │
│  UUID, プロトコル                             │
└─────────────────────────────────────────────┘
```

## 3. ライブラリ仕様 (`raspi_receiver/lib/`)

### 3.1 types.py - 型定義

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class KeyEvent:
    """受信したキーイベント。"""
    key_type: str       # "char" | "special" | "modifier"
    key_value: str      # "a", "Key.enter", "Key.shift" 等
    is_press: bool      # True=押下, False=リリース
    modifiers: dict     # {"cmd": False, "ctrl": False, "alt": False, "shift": True}
    timestamp: float    # 送信元タイムスタンプ

@dataclass
class ConnectionEvent:
    """BLE接続/切断イベント。"""
    connected: bool
    device_address: Optional[str] = None
```

### 3.2 gatt_server.py - GATTサーバー

PoCの `poc/ble_gatt/peripheral_raspi.py` をベースに実装。

```python
class GATTServer:
    def __init__(
        self,
        device_name: str = "RasPi-KeyAgent",
        on_write: Callable[[bytes], None] = None,
        on_connect: Callable[[], None] = None,
        on_disconnect: Callable[[], None] = None,
    ):
        """GATTサーバーの初期化。"""

    async def start(self) -> None:
        """サーバー起動とアドバタイズ開始。"""

    async def stop(self) -> None:
        """サーバー停止。"""

    @property
    def is_running(self) -> bool:
        """サーバー稼働中かどうか。"""
```

### 3.3 key_receiver.py - キー受信 + hook

GATTServerをラップし、アプリケーション向けの高レベルAPIを提供。

```python
class KeyReceiver:
    """
    BLE経由のキー受信ライブラリ。
    アプリケーションはコールバックを登録するだけでキー入力を受け取れる。

    使用例:
        receiver = KeyReceiver()
        receiver.on_key_press = lambda event: print(f"Key: {event.key_value}")
        await receiver.start()
    """

    def __init__(self, device_name: str = "RasPi-KeyAgent"):
        """レシーバーの初期化。"""

    # --- コールバック (アプリが上書きする) ---
    on_key_press: Callable[[KeyEvent], None] = None
    on_key_release: Callable[[KeyEvent], None] = None
    on_connect: Callable[[ConnectionEvent], None] = None
    on_disconnect: Callable[[ConnectionEvent], None] = None

    async def start(self) -> None:
        """GATTサーバーを起動し、キー受信を開始。"""

    async def stop(self) -> None:
        """停止。"""

    @property
    def is_connected(self) -> bool:
        """クライアントが接続中かどうか。"""
```

### 3.4 利用例（ライブラリを使うアプリ側）

```python
import asyncio
from raspi_receiver.lib import KeyReceiver, KeyEvent

async def main():
    receiver = KeyReceiver(device_name="RasPi-KeyAgent")

    def on_key(event: KeyEvent):
        print(f"[{event.key_type}] {event.key_value} ({'press' if event.is_press else 'release'})")

    receiver.on_key_press = on_key
    receiver.on_key_release = on_key

    await receiver.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await receiver.stop()

asyncio.run(main())
```

## 4. LCD表示アプリ仕様 (`sample/raspi_receiver/apps/lcd_display/`)

### 4.1 画面レイアウト

LCD HAT 240x240 ピクセルに以下を表示:

```
┌────────────────────────┐
│  BLE Key Agent         │  ← タイトル (上部)
│  ● Connected           │  ← 接続状態
├────────────────────────┤
│                        │
│    Last Key: A         │  ← 最新キー (大きいフォント)
│    [Shift + A]         │  ← モディファイア付き表示
│                        │
├────────────────────────┤
│  > Hello World_        │  ← 入力バッファ (直近の入力列)
│                        │
└────────────────────────┘
```

### 4.2 機能

| 機能 | 説明 |
|---|---|
| 接続状態表示 | BLE接続中/待機中をアイコンで表示 |
| 最新キー表示 | 直近に受信したキーを大きく表示 |
| 入力バッファ | 文字キーを連結して入力中テキストとして表示。Enterでクリア |
| HAT物理ボタン | KEY1: バッファクリア, KEY2: バックライト制御 |

### 4.3 ハードウェア構成

`example/1.3inch_LCD_HAT_python/` のドライバとconfigを利用。

| コンポーネント | 仕様 |
|---|---|
| LCD | ST7789, 240x240, SPI接続 |
| 方向キー | GPIO 5ピン (Up/Down/Left/Right/Center) |
| ボタン | KEY1(GPIO21), KEY2(GPIO20), KEY3(GPIO16) |
| バックライト | PWM制御 (GPIO24) |

## 5. セットアップ

```bash
# Raspberry Piの初期設定
sudo ./setup_raspi.sh

# ライブラリと依存パッケージのインストール
pip install -r requirements.txt

# LCD表示アプリの起動
PYTHONPATH=src python -m sample.raspi_receiver.apps.lcd_display.main
```

## 6. ライブラリ設計方針

- **依存の最小化**: ライブラリ部分（`lib/`）は `bless` のみに依存
- **非同期ファースト**: async/awaitベースのAPI
- **コールバックパターン**: アプリケーションは必要なコールバックだけ実装すればよい
- **型安全**: dataclassによる型定義で入出力を明確化
- **テスト容易性**: GATTServerをモック可能な設計
