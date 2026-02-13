# BLE Key Agent

Mac のキー入力を BLE GATT 通信で Raspberry Pi に送信し、LCD に表示するシステム。

## システム概要

```
┌──────────────────────┐        BLE GATT Write        ┌──────────────────────┐
│     Mac (Central)    │ ──────────────────────────▶  │  Raspberry Pi        │
│                      │                              │  (Peripheral)        │
│  Flet GUI            │                              │                      │
│  + pynput キー監視   │                              │  BLE受信ライブラリ    │
│  + bleak BLE通信     │                              │  + LCD表示アプリ      │
└──────────────────────┘                              └──────────────────────┘
```

| デバイス | BLE 役割 | 主な機能 |
|---|---|---|
| Mac | Central（親） | キー入力監視 → BLE送信、Flet GUIで接続管理 |
| Raspberry Pi | Peripheral（子） | BLE受信 → LCD表示（1.3inch LCD HAT） |

### 主な特徴

- **低レイテンシ**: Write Without Response による高速キー送信（目標 100ms 以下）
- **自動再接続**: 接続断時の指数バックオフ再接続（1s → 2s → 4s → ... → 最大 60s）
- **ライブラリ分離**: Pi 側の BLE 受信部分はライブラリとして再利用可能
- **決定論的 UUID**: UUIDv5 による Mac/Pi 共通の UUID 生成

## 技術スタック

### Mac 側
| ライブラリ | 用途 |
|---|---|
| bleak >= 0.21.0 | BLE Central 通信 |
| pynput >= 1.7.6 | グローバルキー監視 |
| flet | GUI フレームワーク |
| asyncio | 非同期 I/O |

### Raspberry Pi 側
| ライブラリ | 用途 |
|---|---|
| bless >= 0.3.0 | BLE Peripheral（GATT サーバー） |
| Pillow | LCD 描画 |
| spidev | SPI 通信（LCD） |
| gpiozero | GPIO 制御 |

## ディレクトリ構成

```
BLE-key-agent/
├── docs/                          # 仕様書
├── reports/                       # 技術調査レポート
├── example/                       # ハードウェアサンプル
├── poc/                           # PoC 実装（参照用）
├── src/
│   ├── common/                    # Mac/Pi 共有定義
│   │   ├── uuids.py              #   UUID 定数
│   │   └── protocol.py           #   キーデータフォーマット
│   ├── mac_agent/                 # Mac 側 Flet エージェントアプリ
│   │   ├── main.py               #   エントリポイント
│   │   ├── ble_client.py         #   BLE Central 管理
│   │   ├── key_monitor.py        #   キー入力監視
│   │   └── views/                #   GUI 画面
│   └── raspi_receiver/            # Raspberry Pi 側
│       ├── lib/                   #   BLE 受信ライブラリ（再利用可能）
│       │   ├── gatt_server.py     #     GATT サーバー
│       │   ├── key_receiver.py    #     キー受信 + コールバック
│       │   └── types.py           #     型定義
│       └── apps/
│           └── lcd_display/       #   LCD 表示アプリ
│               ├── main.py        #     エントリポイント
│               ├── display.py     #     LCD 描画ロジック
│               └── config.py      #     GPIO/SPI 設定
└── tests/                         # テスト
```

## 開発環境構築

### 前提条件

- Python 3.10 以上
- Mac: macOS（Bluetooth 対応）
- Raspberry Pi: Raspberry Pi OS、Bluetooth アダプタ有効、1.3inch LCD HAT（ST7789, 240x240, SPI）

### Mac 側セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/takuji-fukumoto/BLE-key-agent.git
cd BLE-key-agent

# 仮想環境の作成・有効化
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージのインストール
pip install bleak>=0.21.0 pynput>=1.7.6 flet

# テスト用
pip install pytest pytest-asyncio
```

**macOS 権限設定:**

1. **アクセシビリティ権限**（pynput のグローバルキー監視に必要）
   - システム設定 → プライバシーとセキュリティ → アクセシビリティ
   - ターミナルまたは使用する IDE を追加
2. **Bluetooth 権限** — 初回スキャン時にシステムダイアログが表示される

### Raspberry Pi 側セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/takuji-fukumoto/BLE-key-agent.git
cd BLE-key-agent

# BlueZ と Bluetooth サービスのセットアップ
sudo chmod +x poc/ble_gatt/setup_raspi.sh
sudo ./poc/ble_gatt/setup_raspi.sh

# 仮想環境の作成・有効化
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージのインストール
pip install bless>=0.3.0 Pillow spidev gpiozero

# SPI の有効化（未設定の場合）
sudo raspi-config nonint do_spi 0
```

## 利用方法

### 1. Raspberry Pi 側（受信・LCD 表示）

Pi 側を先に起動し、BLE アドバタイズを開始させる。

```bash
cd BLE-key-agent
source .venv/bin/activate

# LCD 表示アプリの起動
sudo python -m src.raspi_receiver.apps.lcd_display.main
```

> `sudo` は BLE アドバタイズと GPIO/SPI アクセスに必要。

起動すると `RasPi-KeyAgent` としてアドバタイズが開始され、LCD に接続待ちが表示される。

### 2. Mac 側（キー送信 GUI）

```bash
cd BLE-key-agent
source .venv/bin/activate

# Mac エージェントアプリの起動
python -m src.mac_agent.main
```

GUI が起動したら:
1. **スキャン** ボタンで BLE デバイスを検索
2. デバイス一覧から `RasPi-KeyAgent` を選択して **接続**
3. **キーモニタ ON** でキー入力の送信を開始

Mac でのキー入力がリアルタイムに Pi の LCD に表示される。

### テストの実行

```bash
pytest tests/
```

## BLE 通信仕様（概要）

| 項目 | 値 |
|---|---|
| Service UUID | `6e3f9c05-56c2-5b6e-9b00-8d85c2e85f2f` |
| Characteristic UUID | `d8c7b1e4-42a3-5d2c-a100-9e96d3f96a3f` |
| デバイス名 | `RasPi-KeyAgent` |
| データ形式 | JSON UTF-8（例: `{"t":"c","v":"a","p":true}`） |
| 書き込み方式 | Write Without Response（低レイテンシ優先） |

詳細は [docs/spec-ble-protocol.md](docs/spec-ble-protocol.md) を参照。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | システム要件 |
| [docs/architecture.md](docs/architecture.md) | アーキテクチャ設計 |
| [docs/spec-ble-protocol.md](docs/spec-ble-protocol.md) | BLE 通信プロトコル仕様 |
| [docs/spec-mac-agent.md](docs/spec-mac-agent.md) | Mac エージェントアプリ仕様 |
| [docs/spec-raspi-receiver.md](docs/spec-raspi-receiver.md) | Pi レシーバー仕様 |
| [docs/development-guide.md](docs/development-guide.md) | 開発ガイド |

## ライセンス

MIT
