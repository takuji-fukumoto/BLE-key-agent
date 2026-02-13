# 開発ガイド（AI エージェント向け）

## 1. 開発の進め方

このプロジェクトはAIエージェントによるコーディングをベースとする。
各フェーズの実装前に必ず対応する仕様書を確認すること。

### 実装順序

```
Phase 1: 共通定義 (common/)
    ↓
Phase 2: Pi側ライブラリ (raspi_receiver/lib/)
    ↓
Phase 3: Pi側LCD表示アプリ (raspi_receiver/apps/lcd_display/)
    ↓
Phase 4: Mac側コア (mac_agent/ - BLE + KeyMonitor)
    ↓
Phase 5: Mac側GUI (mac_agent/views/ - Flet)
    ↓
Phase 6: 結合テスト・調整
```

### Phase 1: 共通定義

**参照**: [spec-ble-protocol.md](spec-ble-protocol.md)

- `src/common/uuids.py`: `poc/ble_gatt/common.py` から移行
- `src/common/protocol.py`: キーイベントのシリアライズ/デシリアライズ
- テスト: `tests/test_protocol.py`

**完了条件:**
- KeyEventのJSON変換が双方向で正しく動作
- 短縮フォーマット対応

### Phase 2: Pi側ライブラリ

**参照**: [spec-raspi-receiver.md](spec-raspi-receiver.md), [spec-ble-protocol.md](spec-ble-protocol.md)

- `src/raspi_receiver/lib/types.py`: 型定義
- `src/raspi_receiver/lib/gatt_server.py`: bless GATTサーバー
- `src/raspi_receiver/lib/key_receiver.py`: コールバック管理

**PoC参照**: `poc/ble_gatt/peripheral_raspi.py`

**完了条件:**
- `KeyReceiver` のコールバックが正しく発火する
- GATTServerの起動/停止が安定動作する

### Phase 3: LCD表示アプリ

**参照**: [spec-raspi-receiver.md](spec-raspi-receiver.md) §4

- `src/raspi_receiver/apps/lcd_display/`
- `example/1.3inch_LCD_HAT_python/` のドライバを参照

**完了条件:**
- 受信キーがLCDに表示される
- 接続状態が画面に反映される

### Phase 4: Mac側コア

**参照**: [spec-mac-agent.md](spec-mac-agent.md) §4

- `src/mac_agent/key_monitor.py`: pynputキー監視
- `src/mac_agent/ble_client.py`: bleak BLEクライアント

**PoC参照**: `poc/ble_gatt/central_mac.py`, `poc/pynput/pynput_key_monitor.py`

**完了条件:**
- キー入力がBLE経由でPiに到達する（CUI確認可）
- 再接続が動作する

### Phase 5: Mac側GUI

**参照**: [spec-mac-agent.md](spec-mac-agent.md) §2, §3

- `src/mac_agent/app.py`: アプリ統合
- `src/mac_agent/views/`: Flet UIコンポーネント

**完了条件:**
- GUI上でデバイススキャン・接続・切断が可能
- キーモニタのON/OFFが機能する
- 接続状態がリアルタイム反映される

### Phase 6: 結合テスト

- Mac → Pi のキー送信End-to-End確認
- 接続断・再接続シナリオ
- 長時間稼働テスト

## 2. PoC活用ガイド

既存PoCコードは動作確認済み。本実装時の参照元として利用する。

| PoCファイル | 本実装での対応先 | 主な変更点 |
|---|---|---|
| `poc/ble_gatt/common.py` | `src/common/uuids.py` | そのまま移行 |
| `poc/ble_gatt/central_mac.py` | `src/mac_agent/ble_client.py` | クラス化、再接続追加 |
| `poc/ble_gatt/peripheral_raspi.py` | `src/raspi_receiver/lib/gatt_server.py` | クラス化、コールバック分離 |
| `poc/pynput/pynput_key_monitor.py` | `src/mac_agent/key_monitor.py` | インターフェース整理 |

## 3. 技術リファレンス

実装で判断に迷った場合は以下の調査レポートを参照する。

| トピック | 参照先 |
|---|---|
| BLE GATT全般 | `reports/ble_gatt_key_transmission.md` |
| pynput全般 | `reports/pynput_key_monitoring.md` |
| bleak詳細 | `example/ble_gatt_bleak_research.md` |
| BlueZ/D-Bus | `example/raspi_bluez_gatt_server_research.md` |
| pynput+BLE統合 | `example/pynputと_gatt通信によるキー送信方法.md` |
| LCD HAT | `example/1.3inch_LCD_HAT_python/` |

## 4. コーディング規約

- Python 3.10+
- 型ヒント必須（関数引数・戻り値）
- docstringはクラスと公開メソッドに記述（Google style）
- 非同期関数は `async def` + `await`
- テストは `pytest` + `pytest-asyncio`
- インポートは標準ライブラリ → サードパーティ → ローカルの順

## 5. テスト方針

- `common/protocol.py` は単体テスト必須
- BLE通信部分はモック使用（実デバイス不要のテスト）
- pynput部分はモック使用（アクセシビリティ権限不要のテスト）
- 結合テストは実デバイスで手動確認

## 6. 注意事項

- **blessを使用する**: Pi側のBLEサーバーはblessライブラリを使う（D-Bus直接操作は不要）
- **Write Without Response優先**: 低レイテンシのためWriteよりWrite Without Responseを優先
- **pynputのスレッド**: pynputは別スレッドで動作する。asyncio.Queueでイベントループに橋渡しする
- **Fletの非同期**: Fletは独自のイベントループを持つ。asyncio統合の方法をFletドキュメントで確認すること
- **LCD描画のブロッキング**: SPI通信は同期的。長時間ブロックしないよう描画頻度を制御する
