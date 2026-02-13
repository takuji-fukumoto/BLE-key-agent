# BLE通信プロトコル仕様

## 1. GATT構成

### Service

| 項目 | 値 |
|---|---|
| Service Name | Key Service |
| UUID | `uuid5(PROJECT_NAMESPACE, "key-service")` |
| UUID値 | `6e3f9c05-56c2-5b6e-9b00-8d85c2e85f2f` |

### Characteristic

| 項目 | 値 |
|---|---|
| Characteristic Name | Key Characteristic |
| UUID | `uuid5(PROJECT_NAMESPACE, "key-char")` |
| UUID値 | `d8c7b1e4-42a3-5d2c-a100-9e96d3f96a3f` |
| Properties | Write, Write Without Response |

### UUID生成ルール

```python
import uuid

PROJECT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ble-key-agent.example.com")
KEY_SERVICE_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-service"))
KEY_CHAR_UUID = str(uuid.uuid5(PROJECT_NAMESPACE, "key-char"))
```

UUIDv5を使用することで、Mac/Pi両方で同一のUUIDを決定論的に生成できる。

## 2. デバイス識別

| 項目 | 値 |
|---|---|
| デバイス名 | `RasPi-KeyAgent`（デフォルト） |
| アドバタイズ | デバイス名 + KEY_SERVICE_UUID |

Mac側はスキャン時にKEY_SERVICE_UUIDでフィルタリング可能。

## 3. キーデータフォーマット

### 3.1 バイナリフォーマット

キーイベントはJSON文字列をUTF-8エンコードしたバイト列として送信する。

```
[JSON UTF-8 bytes]
```

### 3.2 JSONスキーマ

```json
{
  "t": "c",           // type: "c"=char, "s"=special, "m"=modifier
  "v": "a",           // value: キー値
  "p": true,          // press: true=押下, false=リリース
  "mod": {            // modifiers (省略可)
    "cmd": false,
    "ctrl": false,
    "alt": false,
    "shift": false
  },
  "ts": 1700000000.0  // timestamp (省略可)
}
```

### 3.3 フィールド説明

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `t` | string | Yes | キー種別。`c`=通常文字, `s`=特殊キー, `m`=修飾キー |
| `v` | string | Yes | キー値。文字キーはそのまま(`"a"`, `"1"`)。特殊キーは名前(`"enter"`, `"space"`, `"backspace"`) |
| `p` | bool | Yes | `true`=押下, `false`=リリース |
| `mod` | object | No | 修飾キーの状態。省略時は全てfalse |
| `ts` | float | No | 送信元のタイムスタンプ（`time.time()`） |

### 3.4 キー値の例

| カテゴリ | `t` | `v` の例 |
|---|---|---|
| 通常文字 | `c` | `"a"`, `"Z"`, `"1"`, `"@"`, `" "` |
| 特殊キー | `s` | `"enter"`, `"tab"`, `"backspace"`, `"escape"`, `"up"`, `"down"`, `"left"`, `"right"`, `"f1"`～`"f12"` |
| 修飾キー | `m` | `"shift"`, `"ctrl"`, `"alt"`, `"cmd"` |

### 3.5 データサイズ

- 通常キーイベント: 約30～60バイト
- BLE MTUデフォルト: 20バイト（ペイロード）

**MTU 20バイト超の場合の対応:**
- bleakは自動的にATT長書き込み（Long Write）を使用
- MTUネゴシエーション対応（bleak/blessが自動処理）
- 短縮フォーマット（modやts省略）で20バイト以内に収めることも可能

### 3.6 短縮フォーマット（オプション）

MTU制約が厳しい場合の最小フォーマット:

```json
{"t":"c","v":"a","p":true}
```

→ 約25バイト。MTUネゴシエーション後は問題なし。

## 4. 通信シーケンス

### 4.1 接続確立

```
Mac (Central)                    Pi (Peripheral)
     │                                │
     │     BLE Scan                   │
     │──────────────────────────────▶│ (Advertising)
     │                                │
     │     Advertisement Response     │
     │◀──────────────────────────────│
     │     (name: RasPi-KeyAgent)     │
     │                                │
     │     Connection Request         │
     │──────────────────────────────▶│
     │                                │
     │     Connection Established     │
     │◀──────────────────────────────│
     │                                │
     │     Service Discovery          │
     │──────────────────────────────▶│
     │                                │
     │     Service + Char Response    │
     │◀──────────────────────────────│
     │                                │
     │     (Ready for key transmission)
```

### 4.2 キー送信

```
Mac (Central)                    Pi (Peripheral)
     │                                │
     │  GATT Write (Key Char UUID)    │
     │  payload: {"t":"c","v":"a",..} │
     │──────────────────────────────▶│
     │                                │ on_write() callback
     │                                │ → KeyEvent生成
     │                                │ → on_key_press() 呼び出し
     │                                │
```

Write Without Response使用時はACKなし（低レイテンシ優先）。

### 4.3 再接続

```
Mac (Central)                    Pi (Peripheral)
     │                                │
     │     Connection Lost            │
     │         ╳                      │
     │                                │
     │  Wait (1s, 2s, 4s backoff)     │
     │                                │
     │     Reconnect Attempt          │
     │──────────────────────────────▶│
     │                                │
```

## 5. エラーケース

| ケース | Mac側対応 | Pi側対応 |
|---|---|---|
| Write失敗 | 1回リトライ→ログ | - |
| 接続断 | 自動再接続（指数バックオフ） | アドバタイズ再開 |
| MTU不足 | 短縮フォーマットへフォールバック | - |
| 不正データ受信 | - | デシリアライズ失敗時にログ出力、無視 |
