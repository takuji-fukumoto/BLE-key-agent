# UNIHIKER Receiver サンプルアプリ

## 概要

UNIHIKER M10 の GUI ライブラリを使った BLE キー受信表示サンプル。
`ble_receiver/lib` の `KeyReceiver` を利用し、受信したキーイベントを UNIHIKER の画面に表示する。

## 重要事項

### UNIHIKER 実行環境の制約

- UNIHIKER M10 のデフォルト OS は Debian Buster + Python 3.7 だが、本プロジェクトは Python 3.10+ を要求する
- pyenv でプリビルド版 Python 3.11+ を導入して使用する（`setup_unihiker_sample.sh` が自動検出）
- Debian Buster の apt リポジトリは `archive.debian.org` に移行済み。セットアップスクリプトで案内を表示する
- セキュリティリポジトリのパスは `/debian-security`（`/debian` ではない）
- `Acquire::Check-Valid-Until "false"` の設定がアーカイブ利用時に必要

### PYTHONPATH と import パスの整合性（重大な注意点）

- 実行時に `PYTHONPATH=src` を設定するため、sample コードからのインポートは `src.` プレフィックスなしで行う必要がある
  - 正: `from common.protocol import KeyEvent`
  - 誤: `from src.common.protocol import KeyEvent`
- `src.` 付きでインポートすると、同じファイルが 2 つの異なるモジュールパスでロードされ、Python が別のクラスとして扱う
- 結果として `isinstance()` チェックや enum 比較が全て失敗し、イベント処理が動作しない
- テストコードも同様に `src.` なしでインポートする必要がある
- LCD サンプル (`sample/raspi_receiver/apps/`) は正しく `src.` なしで統一されている

### UNIHIKER GUI ライブラリ（`unihiker`）

- `from unihiker import GUI` → `gui = GUI()` で初期化
- 画面座標: 240x320（origin は左上、x 右方向 / y 下方向）
- `gui.draw_text(...)` でテキストオブジェクト生成、`object.config(...)` で更新
- GUI は tkinter ベースで、内部で別スレッドの mainloop を起動する
- UNIHIKER 本体にデフォルト導入済みだが、pyenv Python には `pip install unihiker` が必要

### UNIHIKER GUI ボタン（`add_button`）

- `gui.add_button(x, y, w, h, text, origin, state, onclick)` でボタンを配置
- `onclick` にはコールバック関数を渡す（引数なし）
- GUI は tkinter ベースのため、`onclick` 内で長時間ブロックすると画面が固まる
- 複雑な処理を行う場合は `gui.start_thread(func)` を使用する
- 停止ボタンは `display.on_stop` コールバックで `UnihikerReceiverApp._signal_shutdown` に接続し、asyncio.Event 経由でグレースフルシャットダウンを実行する

### Python ラッパー（`run_unihiker.py`）

- `sample/scripts/run_unihiker.py` は `subprocess.run()` で `run_unihiker.sh` を呼ぶ薄いラッパー
- シェルスクリプトがマスター（Python 検出・venv 有効化・Bluetooth 設定）
- Python 側は引数組み立てと `check=True` でのエラー伝搬のみ担当
- `_resolve_script_path()` は `Path(__file__)` 相対でスクリプトを解決するため、任意の作業ディレクトリから呼び出し可能

### bless ライブラリのバージョン互換性

- `bless>=0.3.0` は `bleak>=1.1.1` を要求し、Python 3.8+ が必須
- `bless==0.2.6` は bleak バージョン制約なし（Python 3.7 でも動作するが非推奨）
- pyenv で Python 3.11+ を使えば `bless>=0.3.0` がそのまま利用可能

### スクリプトの POSIX sh 互換性

- `setup_unihiker_sample.sh` は `#!/bin/bash` だが、`sudo sh` で実行されることがある
- `$EUID`（bash 固有）→ `$(id -u)`（POSIX 互換）に置換済み
- `${var:0:1}`（bash 部分文字列）→ `case` 文に置換済み

## 関連ファイル

- `sample/unihiker_receiver/main.py` — アプリ本体（KeyReceiver 統合・ログ設定）
- `sample/unihiker_receiver/display.py` — GUI アダプタ（draw_text/config + add_button ベース）
- `sample/unihiker_receiver/config.py` — 画面レイアウト・定数（停止ボタン座標含む）
- `sample/scripts/setup_unihiker_sample.sh` — 環境セットアップ（pyenv 検出・apt 対応）
- `sample/scripts/run_unihiker.sh` — 起動スクリプト（Python 自動検出）
- `sample/scripts/run_unihiker.py` — Python ラッパー（subprocess 経由）
- `tests/test_unihiker_receiver.py` — 単体テスト
- `tests/test_run_unihiker.py` — Python ラッパーテスト
