# BLE Key Agent

Mac のキー入力を BLE GATT 通信で Raspberry Pi に送信し、LCD に表示するシステム。

## システム概要

```
┌──────────────────────┐        BLE GATT Write        ┌──────────────────────┐
│     Mac (Central)    │ ──────────────────────────▶  │  Raspberry Pi        │
│                      │                              │  (Peripheral)        │
│  pynput キー監視     │                              │                      │
│  + bleak BLE通信     │                              │  BLE受信ライブラリ    │
│                      │                              │  + LCD表示アプリ      │
└──────────────────────┘                              └──────────────────────┘
```

| デバイス | BLE 役割 | 主な機能 |
|---|---|---|
| Mac | Central（親） | キー入力監視 → BLE送信、CLIで接続管理 |
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
├── scripts/                       # スクリプト
│   ├── setup_mac.sh              #   Mac 用セットアップ
│   ├── setup_raspi.sh            #   Raspberry Pi 用セットアップ
│   ├── run_mac.sh                #   Mac エージェント起動
│   └── run_raspi.sh              #   Pi LCD アプリ起動
├── src/                           # メインアプリケーション
│   ├── common/                   #   Mac/Pi 共有定義（UUID, プロトコル）
│   ├── mac_agent/                #   Mac 側エージェント
│   │   ├── main.py               #     エントリポイント
│   │   ├── ble_client.py         #     BLE Central クライアント
│   │   └── key_monitor.py        #     キー入力監視
│   └── raspi_receiver/           #   Raspberry Pi 側
│       ├── lib/                  #     BLE 受信ライブラリ
│       └── apps/lcd_display/     #     LCD 表示アプリ
├── poc/                           # PoC 実装（技術検証用）
├── docs/                          # 仕様書
├── reports/                       # 技術調査レポート
└── tests/                         # テスト
```

## クイックスタート

### 前提条件

- **Python 3.10 以上**
- **Mac**: macOS（Bluetooth 対応）
- **Raspberry Pi**: Raspberry Pi OS（Bookworm 推奨）、Bluetooth アダプタ有効

### Mac 側セットアップ

```bash
# 1. リポジトリのクローン
git clone https://github.com/takuji-fukumoto/BLE-key-agent.git
cd BLE-key-agent

# 2. セットアップスクリプトの実行
chmod +x scripts/setup_mac.sh
./scripts/setup_mac.sh
```

**手動インストールの場合:**
```bash
pip3 install --user bleak>=0.21.0 pynput>=1.7.6
```

**macOS 権限設定（初回のみ）:**

システム設定 → プライバシーとセキュリティ で以下を許可:
- **アクセシビリティ** → ターミナルまたは IDE を追加
- **入力監視** → ターミナルまたは IDE を追加
- **Bluetooth** → 初回スキャン時にダイアログが表示される

### Raspberry Pi 側セットアップ

```bash
# 1. リポジトリのクローン
git clone https://github.com/takuji-fukumoto/BLE-key-agent.git
cd BLE-key-agent

# 2. セットアップスクリプトの実行（sudo 必要）
chmod +x scripts/setup_raspi.sh
sudo ./scripts/setup_raspi.sh

# 3. SPI/GPIO 設定変更時は再起動
sudo reboot
```

**手動インストールの場合:**
```bash
sudo apt install -y bluez python3-pip
pip3 install --break-system-packages bless>=0.3.0 Pillow gpiozero spidev
```

## 利用方法

### 1. Raspberry Pi 側（LCD 表示アプリ）

Pi 側を先に起動し、BLE アドバタイズを開始。

```bash
cd BLE-key-agent
sudo ./scripts/run_raspi.sh
```

起動すると `RasPi-KeyAgent` としてアドバタイズが開始され、LCD に接続待ち画面が表示される。

> **Note**: `sudo` は BLE アドバタイズと GPIO/SPI アクセスに必要

### 2. Mac 側（キー送信エージェント）

```bash
cd BLE-key-agent
./scripts/run_mac.sh
```

対話形式で:
1. BLE デバイスをスキャン
2. デバイス番号を選択して接続
3. キー入力の送信開始（Esc キーで終了）

**デバイス名を指定して直接接続:**
```bash
./scripts/run_mac.sh "RasPi-KeyAgent"
```

接続後、Mac でのキー入力がリアルタイムに Pi の LCD に表示される。

### 3. ライブラリとして利用（送信側）

`mac_agent` はアプリとしての実行だけでなく、他リポジトリから再利用できるAPIを提供する。

```python
import asyncio

from mac_agent import AgentConfig, KeyBleAgent


async def main() -> None:
	agent = KeyBleAgent(
		config=AgentConfig(device_name="RasPi-KeyAgent"),
		on_status_change=lambda s: print(f"status={s.value}"),
	)

	devices = await agent.scan(timeout=5.0)
	if not devices:
		return

	await agent.connect(devices[0].address)
	await agent.start()
	try:
		await asyncio.Event().wait()
	finally:
		await agent.stop()


asyncio.run(main())
```

主な公開API:

- `AgentConfig`: 再接続、heartbeat、送信間隔などの設定
- `KeyBleAgent`: キー監視 + BLE送信の高レベル統合API
- `KeyboardMonitor`: キー監視のみを利用するラッパーAPI
- `BleSender`: BLE送信のみを利用する低レイヤAPI

### 4. ライブラリとして利用（受信側）

`raspi_receiver.lib` は LCD 非依存の受信ライブラリとして利用できる。

```python
import asyncio

from raspi_receiver.lib import KeyReceiver, KeyReceiverConfig


async def main() -> None:
	receiver = KeyReceiver(
		config=KeyReceiverConfig(
			device_name="RasPi-KeyAgent",
			disconnect_timeout_sec=10.0,
		)
	)

	receiver.register_callbacks(
		on_key_press=lambda event: print(f"press: {event.value}"),
		on_key_release=lambda event: print(f"release: {event.value}"),
		on_disconnect=lambda _: print("disconnected"),
	)

	await receiver.start()
	try:
		await asyncio.Event().wait()
	finally:
		await receiver.stop()


asyncio.run(main())
```

**高レベル/低レイヤ選択指針**

- `KeyReceiver`（高レベル）: ほとんどのアプリ向け。デシリアライズ・heartbeat処理・切断監視を内包
- `GATTServer`（低レイヤ）: 独自バイナリや独自プロトコル処理を行う場合に選択

**CLIサンプル**

```bash
PYTHONPATH=src python -m raspi_receiver.apps.cli_receiver.main
```

利用可能オプション:

- `--device-name`
- `--disconnect-timeout`
- `--max-buffer-length`

### テストの実行

```bash
pip3 install --user pytest pytest-asyncio
cd BLE-key-agent
PYTHONPATH=src pytest tests/
```

## トラブルシューティング

### Mac

| 症状 | 対処法 |
|---|---|
| キーが検出されない | システム設定でアクセシビリティ・入力監視を確認 |
| BLE スキャンでデバイスが見つからない | Bluetooth をオン、Pi 側が起動済みか確認 |

### Raspberry Pi

| 症状 | 対処法 |
|---|---|
| hci0 が見つからない | `hciconfig` で確認、`sudo hciconfig hci0 up` |
| アドバタイズが開始されない | `journalctl -u bluetooth -f` でログ確認 |
| Permission denied | `sudo` で実行 |
| LCD が表示されない | SPI 有効化を確認: `ls /dev/spidev*` |

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
