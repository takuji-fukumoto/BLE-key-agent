# BLE Key Agent - AI開発ルール

## プロジェクト概要

macのキー入力をBLE GATT通信でRaspberry Piに送信するシステム。
Mac側はFlet GUIアプリ、Pi側はライブラリ+LCDアプリ。

## ドキュメント参照ルール

**実装前に必ず対応する仕様書を読むこと:**

- 全体要件: `docs/requirements.md`
- アーキテクチャ: `docs/architecture.md`
- BLE通信仕様: `docs/spec-ble-protocol.md`
- Mac側仕様: `docs/spec-mac-agent.md`
- Pi側仕様: `docs/spec-raspi-receiver.md`
- 開発ガイド: `docs/development-guide.md`

技術的に判断に迷った場合は `reports/` 配下の調査レポートを参照する。

**実装済み機能のドメイン知識も参照すること:**

- `docs/spec/` 配下に機能ごとの設計判断・制約・注意点をまとめている
- 関連機能の実装・修正時は対応するファイルを事前に読むこと

## ディレクトリ構成

```
src/
├── common/           # Mac/Pi共有（UUID, プロトコル）
├── mac_agent/        # Mac側Fletエージェントアプリ
│   └── views/        # Flet UIコンポーネント
└── raspi_receiver/   # Pi側
    ├── lib/          # ライブラリ（再利用可能）
    └── apps/         # アプリケーション実装
```

- `poc/` は参照用。直接変更しない
- `example/` はハードウェアサンプル。参照用
- `reports/` は技術調査レポート。参照用

## 技術スタック

- **Mac**: bleak (BLE), pynput (キー監視), flet (GUI), asyncio
- **Pi**: bless (BLE GATT Server), Pillow/spidev/gpiozero (LCD)
- **共通**: Python 3.10+, pytest

## コーディング規約

- 型ヒント必須（関数引数・戻り値）
- docstring: クラスと公開メソッドにGoogle style
- async/awaitベース（同期APIは避ける）
- インポート順: 標準ライブラリ → サードパーティ → ローカル

## 実装時の注意

- **Pi側ライブラリ分離**: `raspi_receiver/lib/` はBLE通信+キー受信hookのみ。LCD等のハードウェア依存は `apps/` に置く
- **bless使用**: Pi側BLEサーバーはblessライブラリを使う（D-Bus直接操作は不要）
- **Write Without Response優先**: 低レイテンシのためGATT Writeより優先
- **pynputスレッド安全性**: pynputは別スレッド動作。asyncio.Queueでイベントループに橋渡し
- **UUID管理**: UUIDv5で決定論的生成。`src/common/uuids.py` で一元管理
- **キーデータフォーマット**: JSON UTF-8。詳細は `docs/spec-ble-protocol.md` §3参照

## テスト

- `pytest` + `pytest-asyncio`
- BLE通信/pynput部分はモック使用
- `common/protocol.py` は単体テスト必須
- 結合テストは実デバイスで手動確認

## 実装フェーズ

1. common/ (UUID, プロトコル)
2. raspi_receiver/lib/ (BLEサーバー, キー受信)
3. raspi_receiver/apps/lcd_display/ (LCD表示)
4. mac_agent/ コア (BLE + キー監視)
5. mac_agent/views/ (Flet GUI)
6. 結合テスト
