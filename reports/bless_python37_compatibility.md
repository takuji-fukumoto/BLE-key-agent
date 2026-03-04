# bless ライブラリ Python 3.7 互換性調査

## 調査日: 2026-03-04

## 背景

UNIHIKER M10 (デフォルト Python 3.7) で `bless>=0.3.0` をインストールしようとすると、
`bleak>=1.1.1` の依存解決に失敗する。bleak 1.x 系は Python 3.8+ が必要なため。

---

## 1. bless 各バージョンの bleak 依存バージョン

PyPI JSON API および GitHub タグから確認した結果:

| bless バージョン | リリース日 | Python 要件 | bleak 依存 | Linux 追加依存 |
|---|---|---|---|---|
| **0.3.0** | 2025-12-23 | >=3.7 | **>=1.1.1** | dbus_next |
| **0.2.6** | 2024-03-06 | >=3.7 | **制約なし** (任意) | dbus_next |
| **0.2.5** | 2023-01-05 | >=3.7 | **制約なし** (任意) | - |
| **0.2.4** | 2022-06-06 | >=3.7 | **制約なし** (任意) | dbus_next |
| **0.2.3** | 2021-11-01 | >=3.6 | **制約なし** (任意) | twisted, txdbus |
| **0.2.2** | 2021-07-18 | - | bleak | - |
| **0.2.1** | 2021-06-18 | - | bleak | - |
| **0.2.0** | 2021-05-17 | - | bleak | - |

### bleak 側の Python サポート状況

| bleak バージョン | Python 要件 | 備考 |
|---|---|---|
| **0.20.2** | >=3.7,<4.0 | **Python 3.7 をサポートする最終版** |
| **0.21.0** | >=3.8,<3.13 | Python 3.7 サポート終了 |
| **1.0.0+** | >=3.8 | bless 0.3.0 が要求するバージョン |

---

## 2. bless 0.2.6 + bleak 0.20.2 で Python 3.7 は使えるか？

### 結論: インストール自体は可能だが、動作の保証はない

- **bless 0.2.6** は `python_requires=">=3.7"` かつ bleak のバージョン制約なし
- **bleak 0.20.2** は `python_requires=">=3.7,<4.0"` で Python 3.7 をサポート
- pip での依存解決は成功するはず

### インストール方法

```bash
# bleak のバージョンを固定してインストール
pip install "bleak==0.20.2" "bless==0.2.6"
```

### リスク

1. **bless 0.2.6 は bleak 0.20.x との互換性をテストしていない可能性がある**
   - bless 0.2.6 のリリース時 (2024-03-06) には bleak は既に 0.21+ に進んでいた
   - bleak の内部 API 変更が bless に影響する可能性あり
2. **bless 0.2.4 で Linux バックエンドが txdbus から dbus-next に移行**
   - 0.2.4 以降を使用するのが望ましい
3. **bless はメンテナンス非活発**
   - 0.2.6 → 0.3.0 で約1年9ヶ月の空白がある

---

## 3. bless GitHub リポジトリの Python 3.7 サポート状況

- **リポジトリ**: https://github.com/kevincar/bless
- **setup.py** (main ブランチ / v0.3.0): `python_requires=">=3.7"` と記載あり
- ただし、bleak>=1.1.1 を要求するため、事実上 Python 3.7 は非対応
- **v0.2.6 タグの setup.py**: `python_requires=">=3.7"` かつ bleak バージョン制約なし
- Python 3.7 に関する issue や明示的なサポート終了アナウンスは見つからなかった
- bless 0.3.0 のリリースノートには bleak 1.1.1 対応が主な変更点として記載

### 結論

bless は `python_requires` で 3.7 を宣言しているが、0.3.0 では bleak>=1.1.1 を要求するため
実質 Python 3.8+ が必要。これは意図的ではなく、bleak のメジャーアップデートへの追従の結果。

---

## 4. 代替手段

### 方策A: bless 0.2.6 + bleak 0.20.2 を使う (最も手軽)

```bash
pip install "bleak==0.20.2" "bless==0.2.6" "dbus-next>=0.2.3"
```

- メリット: 既存コードの変更が不要 (bless API は 0.2.x と 0.3.0 でほぼ同一)
- デメリット: bleak 0.20.x との組み合わせが十分テストされていない可能性
- dbus-next は `python_requires=">=3.6.0"` なので Python 3.7 で問題なし

### 方策B: UNIHIKER M10 の Python バージョンを上げる (推奨)

UNIHIKER M10 は pyenv で Python バージョンを変更可能。

```bash
# pyenv で Python 3.11.4 をインストール (プリビルド版あり)
# 参照: https://github.com/liliang9693/unihiker-pyenv-python
wget https://github.com/liliang9693/unihiker-pyenv-python/releases/download/v3.11.4/Python-3.11.4.tar.gz
mkdir -p ~/.pyenv/versions/
tar -xzf Python-3.11.4.tar.gz -C ~/.pyenv/versions/
pyenv global 3.11.4

# その後 bless 0.3.0 を通常インストール
pip install "bless>=0.3.0"
```

- メリット: 最新の bless/bleak を使える、長期的に安定
- デメリット: pyenv のセットアップが必要、他のシステム依存パッケージとの整合性確認が必要
- プリビルド版として 3.8.5, 3.11.4, 3.12.7 が利用可能

### 方策C: bluez-peripheral を使う (bless の代替)

```bash
pip install bluez-peripheral
```

- **bluez-peripheral**: BlueZ D-Bus API を使った BLE GATT サーバーライブラリ
  - 依存: `dbus-next` のみ (Python 3.6+)
  - Linux (BlueZ) 専用
  - PyPI: https://pypi.org/project/bluez-peripheral/
- メリット: bleak に依存しない、Python 3.7 で動作する
- デメリット: bless とは API が異なるため、`raspi_receiver/lib/` のコード書き換えが必要

### 方策D: BlueZ D-Bus API を直接使う

BlueZ の `example-gatt-server` をベースに D-Bus API を直接呼ぶ方式。

- 依存: `dbus-python` (システムパッケージ) + `gi` (GLib)
- メリット: 追加の pip パッケージ不要、Python 3.7 で動作
- デメリット: 低レベルで実装量が多い、CLAUDE.md の方針 (bless 使用) から逸脱

---

## 5. 推奨

### 短期的 (すぐ動かしたい場合)

**方策A: `bless==0.2.6` + `bleak==0.20.2`** を使う。

```
pip install "bleak==0.20.2" "bless==0.2.6" "dbus-next"
```

既存の `raspi_receiver/lib/` のコードはそのまま動く可能性が高い。
bless 0.2.x と 0.3.0 の間に大きな API 変更はない (0.3.0 の変更は主に bleak 1.1.1 対応と Windows 3.12 サポート)。

### 中長期的 (安定運用)

**方策B: Python バージョンを 3.11 以上に上げる** のが最善。

- UNIHIKER M10 にはプリビルドの Python 3.11.4 が用意されている
- Python 3.7 は 2023年6月に EOL を迎えており、セキュリティ修正もない
- bless/bleak の最新版が使えるため、バグ修正やパフォーマンス改善の恩恵を受けられる

---

## 参考リンク

- bless PyPI: https://pypi.org/project/bless/
- bless GitHub: https://github.com/kevincar/bless
- bleak PyPI: https://pypi.org/project/bleak/
- bluez-peripheral PyPI: https://pypi.org/project/bluez-peripheral/
- UNIHIKER M10 pyenv: https://github.com/liliang9693/unihiker-pyenv-python
- BlueZ example-gatt-server: https://github.com/bluez/bluez/blob/master/test/example-gatt-server
