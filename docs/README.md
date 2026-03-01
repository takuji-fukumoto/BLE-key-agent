# BLE Key Agent - ドキュメント

macのキー入力をBLE GATT通信でRaspberry Piに送信するシステムのドキュメント。

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [requirements.md](requirements.md) | システム要件・機能要件 |
| [architecture.md](architecture.md) | アーキテクチャ設計 |
| [spec-ble-protocol.md](spec-ble-protocol.md) | BLE通信プロトコル仕様 |
| [spec-mac-agent.md](spec-mac-agent.md) | Mac側エージェントアプリ仕様 |
| [spec-raspi-receiver.md](spec-raspi-receiver.md) | Raspberry Pi側レシーバー仕様 |
| [development-guide.md](development-guide.md) | 開発ガイド（AI向け） |

## 参考資料

- [reports/ble_gatt_key_transmission.md](../reports/ble_gatt_key_transmission.md) - BLE GATT通信の技術調査
- [reports/pynput_key_monitoring.md](../reports/pynput_key_monitoring.md) - pynputキー監視の技術調査
- [reports/1.3inch_LCD_HAT_python/](../reports/1.3inch_LCD_HAT_python/) - LCD HAT表示サンプル

## PoCコード

- [poc/ble_gatt/](../poc/ble_gatt/) - BLE GATT通信のPoC実装
- [poc/pynput/](../poc/pynput/) - pynputキー監視のPoC実装
