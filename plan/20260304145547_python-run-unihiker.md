# run_unihiker.sh の Python ラッパー

## 概要

`sample/scripts/run_unihiker.sh` を Python から呼び出せるようにする。
`subprocess.run()` でシェルスクリプトを実行する薄いラッパー関数を提供し、Python ファイル内から `run_unihiker()` を呼べるようにする。

## 変更対象ファイル

| ファイル | 変更種別 | 概要 |
|---|---|---|
| `sample/scripts/run_unihiker.py` | 新規作成 | subprocess ラッパー関数 |
| `sample/scripts/__init__.py` | 新規作成 | パッケージ化（import 用） |
| `tests/test_run_unihiker.py` | 新規作成 | 単体テスト |

## Phase1: 設計

- [x] [Phase1] 変更対象ファイルの洗い出し
- [x] [Phase1] 既存コードの影響範囲調査（既存ファイルへの変更なし）
- [x] [Phase1] インターフェース設計

### インターフェース設計

```python
def run_unihiker(
    debug: bool = False,
    log_dir: str = "/tmp/ble-key-agent",
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """シェルスクリプト run_unihiker.sh を実行する。

    Args:
        debug: --debug フラグを付けるか
        log_dir: --log-dir の値
        extra_args: 追加の CLI 引数

    Returns:
        subprocess.CompletedProcess
    """
```

## Phase2: 実装（コア）

- [ ] [Phase2] `sample/scripts/__init__.py` 作成（空ファイル）
- [ ] [Phase2] `sample/scripts/run_unihiker.py` 作成
  - `run_unihiker()` 関数: subprocess でシェルスクリプトを呼ぶ
  - `_resolve_script_path()`: シェルスクリプトのパスを解決
  - `if __name__ == "__main__"`: CLI からも実行可能に

## Phase3: 実装（結合）

- [ ] [Phase3] `run_unihiker()` のエラーハンドリング確認
  - `subprocess.CalledProcessError` の伝搬
  - スクリプト未発見時の `FileNotFoundError`

## Phase4: テスト

- [ ] [Phase4] `tests/test_run_unihiker.py` 作成
  - `run_unihiker()` がコマンドを正しく組み立てるかテスト（subprocess をモック）
  - `debug=True` 時に `--debug` が含まれるか
  - `log_dir` 指定時に `--log-dir` が含まれるか
  - `extra_args` が正しく追加されるか
- [ ] [Phase4] テスト実行・パス確認

## Phase5: 仕上げ

- [ ] [Phase5] CLAUDE.md 規約準拠チェック（型ヒント、docstring、import 順）
- [ ] [Phase5] 動作確認

## 検証方法

1. テスト: `pytest tests/test_run_unihiker.py -v`
2. 手動確認（Pi 上）: `python -c "from sample.scripts.run_unihiker import run_unihiker; run_unihiker()"`

---

# UNIHIKER GUI 停止ボタン追加

## 概要

UNIHIKER の GUI 画面に「Stop」ボタンを追加し、タッチ操作でサンプルアプリを停止できるようにする。

## 変更対象ファイル

| ファイル | 変更種別 | 概要 |
|---|---|---|
| `sample/unihiker_receiver/config.py` | 変更 | 停止ボタンのレイアウト座標を追加 |
| `sample/unihiker_receiver/display.py` | 変更 | `add_button` で停止ボタンを配置、`on_stop` コールバック |
| `sample/unihiker_receiver/main.py` | 変更 | ボタン押下時に `_signal_shutdown()` を呼ぶ接続 |
| `tests/test_unihiker_receiver.py` | 変更 | 停止ボタン関連テスト追加 |

## 設計

### GUI API

```python
gui.add_button(x=120, y=300, w=80, h=30, text="Stop",
               origin="center", onclick=lambda: on_stop_callback())
```

### 変更方針

- `UnihikerDisplayAdapter` に `on_stop` コールバック属性を追加
- `init()` で `add_button` を呼び、`onclick` で `on_stop` を呼ぶ
- `UnihikerReceiverApp` の `run()` で `display.on_stop = self._signal_shutdown` を設定
- ボタン位置は画面下部 (y=300 付近、240x320 画面)

## Phase2: 実装（コア）- 停止ボタン

- [ ] [Phase2] `config.py` にボタンレイアウト座標追加
- [ ] [Phase2] `display.py` に `on_stop` コールバックと `add_button` 追加
- [ ] [Phase2] `main.py` で `on_stop` コールバックを `_signal_shutdown` に接続

## Phase3: 実装（結合）- 停止ボタン

- [ ] [Phase3] ボタン押下→シャットダウンのフロー確認

## Phase4: テスト - 停止ボタン

- [ ] [Phase4] 停止ボタン関連テスト追加
- [ ] [Phase4] 全テスト実行・パス確認

## Phase5: 仕上げ - 停止ボタン

- [ ] [Phase5] CLAUDE.md 規約準拠チェック
- [ ] [Phase5] 動作確認
