# BLE Key Agent - Copilot Instructions

このリポジトリで GitHub Copilot がコード変更を行う際の共通ルール。

## プロジェクト概要

- mac のキー入力を BLE GATT 通信で Raspberry Pi に送信するシステム
- このリポジトリは通信ライブラリ提供を中心とし、GUIアプリは別リポジトリで実装
- Pi 側: ライブラリ + LCD アプリ

## 実装前に読むドキュメント

- 全体要件: `docs/requirements.md`
- アーキテクチャ: `docs/architecture.md`
- BLE 通信仕様: `docs/spec-ble-protocol.md`
- Mac 側仕様: `docs/spec-mac-agent.md`
- Pi 側仕様: `docs/spec-raspi-receiver.md`
- 開発ガイド: `docs/development-guide.md`

技術的に判断に迷った場合は `reports/` 配下を参照する。
既存機能の設計判断は `docs/spec/` 配下を先に確認する。

## ディレクトリ運用ルール

- `src/common/`: Mac/Pi 共有（UUID, プロトコル）
- `src/ble_sender/`: BLE 送信側ライブラリ/CLI
- `src/ble_receiver/lib/`: BLE 受信側ライブラリ（BLE 通信 + キー受信 hook）
- `sample/raspi_receiver/apps/`: Pi 側サンプルアプリ実装（LCD 等ハードウェア依存）
- `poc/`, `reports/` は参照用。原則直接変更しない

## コーディング規約

- 型ヒント必須（関数引数・戻り値）
- クラスと公開メソッドに Google style docstring
- async/await ベース（同期 API は極力避ける）
- import 順序: 標準ライブラリ → サードパーティ → ローカル

## 実装上の重要制約

- Pi 側 BLE サーバーは `bless` を利用する
- 低レイテンシ優先で Write Without Response を優先
- `pynput` のイベントは別スレッド前提で `asyncio.Queue` で橋渡し
- UUID は `src/common/uuids.py` で一元管理（UUIDv5 による決定論的生成）
- キーデータフォーマットは JSON UTF-8（詳細は `docs/spec-ble-protocol.md`）

## テスト方針

- `pytest` + `pytest-asyncio`
- BLE 通信 / `pynput` 部分はモックを使用
- `src/common/protocol.py` は単体テストを重視
- 結合テストは実デバイスで手動確認

## 推奨実装順

1. `common/`（UUID, プロトコル）
2. `ble_receiver/lib/`（BLE サーバー, キー受信）
3. `sample/raspi_receiver/apps/lcd_display/`（LCD 表示サンプル）
4. `ble_sender/` コア（BLE + キー監視）
5. 外部GUI/利用アプリへの統合（別リポジトリ）
6. 結合テスト

## Claude 設定との差分メモ

- `.claude/settings.local.json` の権限 allowlist は Copilot Instructions では直接再現不可
- `.claude/commands/*.md` のような「スラッシュコマンド定義」も 1:1 では移植不可
- 必要なら別途、`tasks.json` やスクリプトで運用フローを補完する
