# システム要件

## 1. システム概要

macのキー入力をBLE GATT通信でRaspberry Piに送信するシステム。
Mac側はGUIエージェントアプリ（Flet）でキー入力監視とBLE接続管理を行い、Pi側は受信したキー情報をLCDに表示する。
Pi側の受信・処理部分はライブラリとして分離し、他アプリからも再利用可能にする。

## 2. デバイス構成

| デバイス | BLE役割 | OS/環境 |
|---|---|---|
| Mac | Central（親） | macOS |
| Raspberry Pi | Peripheral（子） | Raspberry Pi OS |

## 3. 機能要件

### 3.1 Mac側エージェントアプリ

- **FR-M01**: グローバルキー入力の監視（pynput）
- **FR-M02**: BLEデバイスのスキャン・接続・切断
- **FR-M03**: キー入力イベントのBLE送信（GATT Write）
- **FR-M04**: GUIで接続状態の表示（接続中/切断/スキャン中）
- **FR-M05**: GUIで接続先デバイスの選択・変更
- **FR-M06**: 接続断時の自動再接続（指数バックオフ: 1s→2s→4s→...→最大60s）

### 3.2 Raspberry Pi側レシーバー

- **FR-R01**: BLE GATTサーバーの起動・アドバタイズ
- **FR-R02**: キーデータの受信とデコード
- **FR-R03**: 受信キーのコールバック通知（hookポイント）
- **FR-R04**: LCDモニタへのキー情報表示（アプリ側実装）
- **FR-R05**: BLE通信+キー受信hookのライブラリ提供

### 3.3 BLE通信

- **FR-B01**: GATT Write / Write Without Responseによるキー送信
- **FR-B02**: UUIDv5による決定論的UUID管理（common定義）
- **FR-B03**: UTF-8エンコードでのキーデータ送受信
- **FR-B04**: 接続断時の自動再接続（指数バックオフ）
  - 初回待機: 1秒
  - バックオフ倍率: 2倍
  - 最大待機: 60秒
  - 再接続成功時にバックオフをリセット
  - 再接続中はGUIに状態表示（`RECONNECTING`）
  - Pi側はアドバタイズを再開して接続待ち状態に戻る

## 4. 非機能要件

- **NFR-01**: キー入力からPi表示までのレイテンシ: 100ms以下（目標）
- **NFR-02**: BLE通信範囲: 室内利用想定（~10m）
- **NFR-03**: Pi側ライブラリは外部依存を最小限にする
- **NFR-04**: Mac側GUIはFletで実装し、単一プロセスで動作

## 5. 技術スタック

### Mac側
| ライブラリ | バージョン | 用途 |
|---|---|---|
| bleak | >= 0.21.0 | BLE Central通信 |
| pynput | >= 1.7.6 | グローバルキー監視 |
| flet | 最新安定版 | GUIフレームワーク |
| asyncio | 標準ライブラリ | 非同期I/O |

### Raspberry Pi側
| ライブラリ | バージョン | 用途 |
|---|---|---|
| bless | >= 0.3.0 | BLE Peripheral (GATTサーバー) |
| Pillow | 最新安定版 | LCD描画 |
| spidev | 最新安定版 | SPI通信 (LCD) |
| gpiozero | 最新安定版 | GPIO制御 |

## 6. 前提条件

- macOS: アクセシビリティ権限の付与（pynput用）
- Raspberry Pi: BlueZインストール済み、Bluetoothアダプタ有効化済み
- Pi用LCDモニタ: 1.3inch LCD HAT（ST7789, 240x240, SPI接続）

## 7. 制約事項

- BLE GATT Writeのペイロードは最大20バイト（デフォルトMTU時）
  - キーデータはUTF-8で1～数バイトのため十分
- pynputは一部のシステムキー（Touch Bar等）を取得不可
- BLE接続は1対1（Mac 1台 ↔ Pi 1台）
