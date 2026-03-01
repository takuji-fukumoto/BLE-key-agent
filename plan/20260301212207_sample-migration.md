# srcの非ライブラリ処理をsampleへ移管する計画

## 背景

- 本リポジトリを BLE 通信 + 入力監視ライブラリ中心に整理する。
- `src/raspi_receiver/apps/lcd_display` はサンプル用途として `sample/` 配下へ移設する。
- `lcd_display` 以外にもコア責務外（BLE受信ライブラリ/入力監視ライブラリ以外）の処理を棚卸しし、必要に応じて sample 化する。

## 対象候補（初期）

- `src/raspi_receiver/apps/lcd_display`
- `src/raspi_receiver/apps/cli_receiver`（デモ/サンプル実行用途）
- `scripts/run_raspi.sh`, `scripts/run_raspi_loop.sh`（サンプル起動導線）
- 関連する README / docs / tests / import path

## 実装チェックリスト

- [ ] [Phase1] 移行対象を棚卸しし、`src` に残す責務と `sample` に移す責務を確定する
- [ ] [Phase2] `lcd_display` を `sample/` 配下へ移設し、実行可能状態を維持する
- [ ] [Phase3] サンプル実行用シェルスクリプトの配置と起動経路を更新する
- [ ] [Phase4] `cli_receiver` を含む非コア処理・テスト・README/Docs・import を新構成へ追従させる
- [ ] [Phase5] 対象テストの回帰確認を行い、結果を PR に記録する

## レビュー依頼ポイント

- `src` に残す最小責務（BLE通信/入力監視ライブラリ）の境界定義
- `sample/` のディレクトリ構成（`sample/raspi_receiver/...` か `sample/lcd_display/...` か）
- 既存ユーザー向け実行導線（後方互換エイリアス有無）
