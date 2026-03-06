# Mac エージェントアプリ仕様

## 1. 概要

macOS上で動作する送信ライブラリ/CLI。
pynputでキー入力を監視し、BLE GATT通信でRaspberry Piにキーイベントを送信する。
GUIアプリケーションへの統合は別リポジトリで行う。

## 2. 画面構成

### 2.1 メイン画面

```
┌─────────────────────────────────────────┐
│  BLE Key Agent                     [─]  │
├─────────────────────────────────────────┤
│                                         │
│  接続状態:  ● 接続中 (RasPi-KeyAgent)   │
│                                         │
│  [スキャン]  [切断]                      │
│                                         │
├─────────────────────────────────────────┤
│  デバイス一覧                            │
│  ┌─────────────────────────────────────┐│
│  │ ● RasPi-KeyAgent  (-45 dBm) [接続] ││
│  │ ○ RasPi-Display   (-62 dBm) [接続] ││
│  │ ○ Unknown         (-78 dBm)        ││
│  └─────────────────────────────────────┘│
│                                         │
├─────────────────────────────────────────┤
│  キーモニタ                [ON/OFF]      │
│  ┌─────────────────────────────────────┐│
│  │ 14:23:01  Press   'a'              ││
│  │ 14:23:01  Release 'a'              ││
│  │ 14:23:02  Press   Key.shift        ││
│  │ 14:23:02  Press   'A'              ││
│  │ ...                                ││
│  └─────────────────────────────────────┘│
│                                         │
├─────────────────────────────────────────┤
│  送信: 142件  エラー: 0件  遅延: ~15ms   │
└─────────────────────────────────────────┘
```

### 2.2 画面要素

| 要素 | 説明 |
|---|---|
| 接続状態インジケータ | 接続中(緑)/切断(赤)/スキャン中(黄)の状態表示 |
| スキャンボタン | BLEデバイスのスキャン開始 |
| 切断ボタン | 現在の接続を切断 |
| デバイス一覧 | スキャン結果。デバイス名、RSSI、接続ボタン表示 |
| キーモニタ ON/OFF | キー監視の有効/無効切り替え |
| キーログ | 直近のキーイベントをリアルタイム表示（最大100件） |
| ステータスバー | 送信件数、エラー件数、推定遅延 |

## 3. 状態遷移

```
[起動] ──▶ [未接続] ──▶ [スキャン中] ──▶ [未接続]
                │                           │
                │         接続成功           │
                ▼                           ▼
           [接続中] ◀─────────────────── [接続中]
                │                           ▲
                │ 切断/接続断                │
                ▼                           │
           [再接続中] ──── 成功 ────────────┘
                │
                │ 失敗(3回)
                ▼
           [未接続] (エラー表示)
```

### 状態定義

| 状態 | 説明 |
|---|---|
| `DISCONNECTED` | BLE未接続。スキャンまたは接続待ち |
| `SCANNING` | BLEデバイスをスキャン中 |
| `CONNECTING` | デバイスへの接続処理中 |
| `CONNECTED` | BLE接続済み。キー送信可能 |
| `RECONNECTING` | 接続断後の自動再接続中 |

## 4. モジュール詳細

### 4.1 key_monitor.py

pynputを使ったキー入力監視。PoCの `poc/pynput/pynput_key_monitor.py` をベースに実装。

**公開インターフェース:**

```python
class KeyMonitor:
    def __init__(self, queue: asyncio.Queue):
        """キー監視の初期化。イベントはqueueに投入される。"""

    async def start(self) -> None:
        """キー監視を開始（pynputスレッドを起動）。"""

    async def stop(self) -> None:
        """キー監視を停止。"""

    @property
    def is_running(self) -> bool:
        """監視中かどうか。"""

    @staticmethod
    def check_accessibility() -> bool:
        """macOS アクセシビリティ権限の確認。"""
```

**キーイベント出力:**

```python
@dataclass
class KeyEvent:
    key_type: str       # "char" | "special" | "modifier"
    key_value: str      # "a", "Key.enter", "Key.shift" 等
    is_press: bool      # True=押下, False=リリース
    modifiers: dict     # {"cmd": False, "ctrl": False, "alt": False, "shift": True}
    timestamp: float    # time.time()
```

### 4.2 ble_client.py

bleak を使ったBLE Central管理。PoCの `poc/ble_gatt/central_mac.py` をベースに実装。

**公開インターフェース:**

```python
class BleClient:
    def __init__(self, on_status_change: Callable[[str], None]):
        """BLEクライアントの初期化。"""

    async def scan(self, timeout: float = 5.0) -> list[BleDevice]:
        """BLEデバイスをスキャン。KEY_SERVICE_UUIDを持つデバイスを優先表示。"""

    async def connect(self, address: str) -> bool:
        """指定アドレスのデバイスに接続。"""

    async def disconnect(self) -> None:
        """現在の接続を切断。"""

    async def send_key(self, event: KeyEvent) -> bool:
        """キーイベントを送信。Write Without Response使用。"""

    @property
    def status(self) -> str:
        """現在の接続状態。"""

    @property
    def connected_device(self) -> Optional[BleDevice]:
        """接続中のデバイス情報。"""
```

### 4.3 agent.py

KeyMonitor と BleClient を統合し、外部アプリから利用しやすい高レベルAPIを提供する。

**責務:**
- KeyMonitor のキューを監視し、BleClient.send_key() を呼ぶ
- 接続状態の変化をUIに通知
- 再接続ロジックの管理

```python
class BleKeyAgentApp:
    def __init__(self):
        self.key_monitor = KeyMonitor(self.key_queue)
        self.ble_client = BleClient(on_status_change=self._on_status_change)

    async def run(self) -> None:
        """アプリケーション起動。"""

    async def _key_sender_loop(self) -> None:
        """キューからキーイベントを取得して送信するループ。"""

    async def _reconnect_loop(self) -> None:
        """接続断時の自動再接続ループ。"""
```

### 4.4 外部GUI連携（別リポジトリ）

GUI連携は本リポジトリ外で実装する。本リポジトリは `ble_sender` の公開APIを提供する。

```python
# 外部GUI側の想定
# - ble_sender.KeyBleAgent を初期化
# - scan/connect/start/stop をUIイベントに紐付け
# - on_status_change / on_error / on_key_event を画面更新に反映
```

## 5. 起動方法

```bash
cd src/ble_sender
pip install -r requirements.txt
python main.py
```

## 6. macOS固有の注意事項

- **アクセシビリティ権限**: pynputのグローバルキー監視に必要
  - システム設定 → プライバシーとセキュリティ → アクセシビリティ
  - ターミナル/IDE/ビルド済みアプリを追加
- **Bluetooth権限**: 初回スキャン時にシステムダイアログが表示される
- **外部GUI連携**: GUI側から `ble_sender` の公開APIを呼び出して統合する
