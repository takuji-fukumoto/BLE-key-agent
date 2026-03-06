# モジュールリネーム: raspi_receiver → ble_receiver, mac_agent → ble_sender

## 概要

デバイス固有名をモジュール名から除去し、BLE通信の役割ベースの命名に統一した。
`src/raspi_receiver/` → `src/ble_receiver/`、`src/mac_agent/` → `src/ble_sender/`。

## 重要事項

### リネーム時のpatch文字列更新漏れ

`unittest.mock.patch()` のターゲット文字列はPythonのimport文とは別に管理される。
モジュールリネーム時、import文の更新だけでは不十分で、patch文字列も全て更新が必要。

```python
# import文とは別にpatch文字列にもモジュールパスが含まれる
@patch("ble_receiver.lib.key_receiver.GATTServer")  # ← これも更新が必要
```

grepで `patch("旧モジュール名` を検索して漏れを防ぐこと。

### sample/ ディレクトリは変更しない

`sample/raspi_receiver/` はRaspberry Pi固有のサンプルアプリであり、
デバイス固有であることが正しいため変更しない。
ただし、sample内のimport文は `from ble_receiver.lib import ...` に更新する
（`PYTHONPATH=src` で実行されるため、src配下のモジュール名に合わせる必要がある）。

### pyproject.toml の optional-dependency 名

`pyproject.toml` の `[project.optional-dependencies]` セクションの
キー名（例: `raspi`, `mac`）はデプロイ先を示すものであり、
モジュール名とは独立しているため変更不要。

## 関連ファイル

- `src/ble_sender/` — 旧 `src/mac_agent/`
- `src/ble_receiver/` — 旧 `src/raspi_receiver/`
- `plan/20260306091131_rename-receiver-module.md` — 実装計画
