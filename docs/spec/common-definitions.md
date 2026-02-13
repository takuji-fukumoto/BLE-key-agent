# 共通定義 (common/)

## 概要
Mac/Pi間で共有するUUID定数とキーイベントのシリアライズ/デシリアライズプロトコルを提供する。

## 重要事項

### UUID値と仕様書の不一致
`docs/spec-ble-protocol.md` に記載されたUUID値と、実際にコードで生成される値が異なる。
PoCコード（`poc/ble_gatt/common.py`）と本実装で生成される値は一致しており、動作実績がある。

| 項目 | 仕様書記載値 | 実際の生成値（正） |
|------|-------------|-------------------|
| KEY_SERVICE_UUID | `6e3f9c05-56c2-5b6e-9b00-8d85c2e85f2f` | `d62db9d9-c089-527a-9876-ab4c64a80ba9` |
| KEY_CHAR_UUID | `d8c7b1e4-42a3-5d2c-a100-9e96d3f96a3f` | `25f5c84f-c653-5585-9493-6253f1e1f11e` |

仕様書のUUID値は更新が必要。コード上の`uuid5()`による決定論的生成が正となる。

### KeyType enumの設計判断
- `str, Enum` を使用（Python 3.10互換）。`StrEnum` は3.11+のため不使用。
- enum値はBLEワイヤフォーマットの短縮コード（`"c"`, `"s"`, `"m"`）に直接対応させた。
  これにより `key_type.value` がそのままJSONの `"t"` フィールド値になる。

### Modifiersのイミュータビリティ
- `@dataclass(frozen=True)` を使用。キーイベントの修飾キー状態はイベント発生時のスナップショットであり、後から変更されるべきではない。
- `is_default()` メソッドで全フィールドがFalseかを判定し、短縮フォーマット時の省略判定に使用。

### 短縮フォーマットとMTU制約
- 短縮フォーマット `{"t":"c","v":"a","p":true}` は26バイト。BLE MTUデフォルト20バイトを超えるが、MTUネゴシエーション後は問題なし。
- `json.dumps(separators=(",", ":"))` でスペースを除去しコンパクト化。
- `modifiers` がNoneまたは全デフォルト、`timestamp` がNoneの場合は自動的に省略される。

### pyproject.tomlのpythonpath設定
- `[tool.pytest.ini_options]` に `pythonpath = ["src"]` を設定。
  これにより `pip install -e .` なしでも `pytest` が `from common.protocol import ...` を解決できる。

## 関連ファイル
- `src/common/__init__.py`
- `src/common/uuids.py`
- `src/common/protocol.py`
- `tests/test_protocol.py`
- `pyproject.toml`
