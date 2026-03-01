# アーキテクチャ設計

## 1. システム全体構成

```
┌─────────────────────────────────────────────────────────────┐
│                    Mac (BLE Central)                        │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  CLI /       │  │  KeyMonitor  │  │  BLE Client      │  │
│  │  External UI │  │  (pynput)    │  │  (bleak)         │  │
│  │              │  │  (pynput)    │  │  (bleak)         │  │
│  │ - 接続状態    │  │              │  │                  │  │
│  │ - デバイス選択 │  │  Thread      │  │  async           │  │
│  │ - キーログ    │◀─┤      │       ├─▶│  scan/connect/   │  │
│  │              │  │      ▼       │  │  write            │  │
│  │              │  │  asyncio     │  │                  │  │
│  │              │  │  Queue       │  │                  │  │
│  └──────────────┘  └──────────────┘  └────────┬─────────┘  │
└────────────────────────────────────────────────┼────────────┘
                                                 │
                        BLE GATT Write           │
                                                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Raspberry Pi (BLE Peripheral)                   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              ble-key-receiver (ライブラリ)             │   │
│  │  ┌────────────────┐  ┌─────────────────────────┐    │   │
│  │  │  GATT Server   │  │  KeyReceiver            │    │   │
│  │  │  (bless)       │  │                         │    │   │
│  │  │                │  │  - on_key_press callback │    │   │
│  │  │  on_write() ───┼─▶│  - on_key_release       │    │   │
│  │  │                │  │  - on_connect            │    │   │
│  │  │                │  │  - on_disconnect         │    │   │
│  │  └────────────────┘  └────────────┬────────────┘    │   │
│  └───────────────────────────────────┼─────────────────┘   │
│                                      │ callback             │
│                                      ▼                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              アプリケーション層                         │   │
│  │  (例: LCD表示アプリ, ロガー, キーリマッパー等)          │   │
│  │                                                      │   │
│  │  ┌─────────────┐  ┌──────────┐  ┌──────────────┐    │   │
│  │  │ LCD Display │  │  Logger  │  │  Custom App  │    │   │
│  │  │ (ST7789)    │  │          │  │              │    │   │
│  │  └─────────────┘  └──────────┘  └──────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. ディレクトリ構成（実装目標）

```
BLE-key-agent/
├── CLAUDE.md                      # AI開発ルール
├── docs/                          # 仕様書
├── reports/                       # 技術調査レポート
├── example/                       # ハードウェアサンプル
├── poc/                           # PoC実装（既存）
│
├── src/                           # 本実装
│   ├── common/                    # Mac/Pi共有定義
│   │   ├── __init__.py
│   │   ├── uuids.py              # UUID定数 (poc/ble_gatt/common.py から移行)
│   │   └── protocol.py           # キーデータフォーマット定義
│   │
│   ├── mac_agent/                 # Mac側送信ライブラリ/CLI
│   │   ├── __init__.py
│   │   ├── main.py               # エントリポイント (CLI)
│   │   ├── agent.py              # 高レベル統合API
│   │   ├── api_types.py          # 公開設定/コールバック型
│   │   ├── ble_client.py         # BLE Central管理 (bleak)
│   │   ├── key_monitor.py        # キー入力監視 (pynput)
│   │   ├── keyboard_monitor.py   # ライブラリ向け入力監視ラッパー
│   │   └── requirements.txt
│   │
│   └── raspi_receiver/            # Raspberry Pi側ライブラリ
│       ├── lib/                   # ライブラリ部分（再利用可能）
│       │   ├── __init__.py
│       │   ├── gatt_server.py     # BLE GATTサーバー (bless)
│       │   ├── key_receiver.py    # キー受信 + hookコールバック
│       │   └── types.py           # 型定義 (KeyEvent等)
│       └── requirements.txt
├── sample/                        # サンプル実装
│   └── raspi_receiver/apps/
│       ├── cli_receiver/
│       └── lcd_display/
│
└── tests/                         # テスト
    ├── test_protocol.py
    ├── test_key_monitor.py
    └── test_key_receiver.py
```

## 3. モジュール依存関係

```
common/uuids          ←── mac_agent/ble_client
common/protocol       ←── mac_agent/key_monitor
                      ←── raspi_receiver/lib/key_receiver

mac_agent/key_monitor ──▶ mac_agent/app (asyncio.Queue経由)
mac_agent/ble_client  ──▶ mac_agent/agent (接続状態管理)
mac_agent/agent       ──▶ external GUI/CLI (別リポジトリUI連携)

raspi_receiver/lib/gatt_server   ──▶ raspi_receiver/lib/key_receiver
raspi_receiver/lib/key_receiver  ──▶ sample/raspi_receiver/apps/* (callback)
```

## 4. コンポーネント責務

### 4.1 common/

| モジュール | 責務 |
|---|---|
| `uuids.py` | Service/Characteristic UUID定数、デバイス名 |
| `protocol.py` | キーイベントのシリアライズ/デシリアライズ定義 |

### 4.2 mac_agent/

| モジュール | 責務 |
|---|---|
| `main.py` | エントリポイント（CLI） |
| `agent.py` | アプリ全体のライフサイクル管理、各モジュールの統合 |
| `api_types.py` | 設定・コールバック型の公開API |
| `ble_client.py` | BLEスキャン、接続、キーデータ送信、再接続 |
| `key_monitor.py` | pynputによるグローバルキー監視、KeyEvent生成 |
| `keyboard_monitor.py` | キー監視のライブラリ向けラッパー |

### 4.3 raspi_receiver/lib/ （ライブラリ）

| モジュール | 責務 |
|---|---|
| `gatt_server.py` | bless GATTサーバーの起動・管理・アドバタイズ |
| `key_receiver.py` | 受信データのデコード、コールバック呼び出し |
| `types.py` | KeyEvent, ConnectionEvent等の型定義 |

### 4.4 sample/raspi_receiver/apps/ （サンプルアプリケーション）

| モジュール | 責務 |
|---|---|
| `lcd_display/` | LCD HAT上にキー情報を描画するアプリ |

## 5. データフロー

### キー入力 → Pi表示の流れ

```
1. [Mac] pynput Listener がキーイベントを検知
2. [Mac] KeyMonitor が KeyEvent を生成し asyncio.Queue に投入
3. [Mac] App が Queue から KeyEvent を取得
4. [Mac] BleClient が KeyEvent をバイト列にシリアライズ
5. [Mac] bleak で GATT Write (or Write Without Response)
6. [BLE] 無線送信
7. [Pi]  bless GATTサーバーの on_write コールバック発火
8. [Pi]  KeyReceiver がバイト列をデシリアライズ → KeyEvent
9. [Pi]  登録されたコールバック (on_key_press等) を呼び出し
10.[Pi]  LCD表示アプリがコールバック内で画面を更新
```

## 6. 非同期処理モデル

### Mac側
- **メインスレッド**: CLI/外部アプリのイベントループ
- **pynputスレッド**: キー監視（threading.Thread）
- **asyncioイベントループ**: BLE通信、キューからの読み取り
- スレッド間通信: `asyncio.Queue` + `call_soon_threadsafe`

### Pi側
- **asyncioイベントループ**: bless GATTサーバー、コールバック処理
- LCD描画は同期処理（コールバック内で実行）

## 7. エラーハンドリング方針

| エラー | 対応 |
|---|---|
| BLE接続断 | 自動再接続（指数バックオフ、最大3回→UIに通知） |
| デバイス未発見 | スキャンタイムアウト後にUIでエラー表示 |
| pynput権限エラー | 起動時チェック、設定手順をGUIで案内 |
| GATT Write失敗 | リトライ1回、失敗時はログ出力 |
