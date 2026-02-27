# レガシーコード対応ガイド

テストのないコードを安全にリファクタリングするためのテクニック集。

## レガシーコードの定義

> テストのないコードは悪いコードである。どれだけうまく書かれているかは関係ない。
> — Michael Feathers『レガシーコード改善ガイド』

## レガシーコードのジレンマ

> コードを変更するためにはテストを整備する必要がある。
> でも多くの場合、テストを整備するためにはコードを変更する必要がある。

**解決策**: 最小限の安全な変更でテスト可能な状態を作る

---

## 1. Characterization Test（特性テスト）

### 概要

既存コードの**実際の振る舞い**を記録するテスト。仕様ではなく、現在の動作を守る。

**別名**: Pinning Test（固定テスト）

### 目的

- 現在の振る舞いを固定する
- リファクタリング時の安全網を提供
- 仕様書がなくても動作を保証

### 作成手順

1. **対象コードを呼び出すテストを書く**
   - 最初はアサーションなしでOK

2. **実際の出力を確認**
   - テストを実行し、戻り値やログを観察

3. **観察した動作をアサーションに**
   - 「undefinedでなければOK」程度の雑さで開始

4. **段階的に詳細化**
   - 必要に応じてアサーションを増やす

### 例

```javascript
// Step 1: まず呼び出すだけ
describe('pickQuestion', () => {
  it('returns something', () => {
    const result = pickQuestion(testData);
    // まずは動くことだけ確認
  });
});

// Step 2: 観察した動作をアサーション化
describe('pickQuestion', () => {
  it('returns an object with question property', () => {
    const result = pickQuestion(testData);
    assert(result !== undefined);
    assert(result.question !== undefined);
  });
});
```

### ポイント

- **仕様と実装が異なる場合、実装を信じる**
  - ユーザーはその動作に依存している
- **網羅性より「動くテスト」を優先**
  - 0件→1件が最大の関門
- **Happy Pathから始める**
  - 正常系でまず1本通す

---

## 2. Seam（継ぎ目）

### 概要

> Seamとは、コードを変更せずに振る舞いを変えられる場所

テストコードから介入する口を作り、動きを変える場所。

### 種類

| 種類 | 説明 | 用途 |
|------|------|------|
| **Object Seam** | インターフェース経由で置換 | 依存オブジェクトのモック化 |
| **Preprocessing Seam** | プリプロセッサで置換 | C/C++向け |
| **Link Seam** | リンク時に実装を置換 | 低レベル言語向け |

### Object Seamの作成

**問題**: ランダム性や現在時刻など、テストが困難な要素

```javascript
// Before: 内部でランダム - テスト困難
function pickQuestion(data) {
  const index = Math.floor(Math.random() * data.length);
  return data[index];
}

// After: 外から関数を渡せる - Seam作成
function pickQuestion(data, picker = (d) => d[Math.floor(Math.random() * d.length)]) {
  return picker(data);
}

// テストでは固定値を返す関数を渡す
test('pickQuestion returns first item when picker selects index 0', () => {
  const data = ['a', 'b', 'c'];
  const result = pickQuestion(data, (d) => d[0]);
  assert.equal(result, 'a');
});
```

### Seam作成の最小変更

1. **パラメータ追加**: デフォルト値で既存動作を維持
2. **インターフェース抽出**: 依存をインターフェース経由に
3. **コンストラクタ注入**: 依存をコンストラクタで受け取る

---

## 3. Humble Object パターン

### 概要

テストしにくい部分を**薄く隔離**し、残りをテスト可能にする。

```
┌─────────────────────────────────┐
│  テストしにくい要素              │ ← 薄く切り出す（Humble Object）
│  （ランダム性、現在時刻、I/O）   │
└─────────────────────────────────┘
           ↓ 分離
┌─────────────────────────────────┐
│  テストしたいロジック            │ ← 自動テスト可能に
│  （大部分のビジネスロジック）    │
└─────────────────────────────────┘
```

### テストしにくい要素

- ランダム性（`Math.random()`）
- 現在時刻（`Date.now()`、`new Date()`）
- ファイルI/O
- ネットワーク通信
- UIレンダリング

### 適用手順

1. **テストしにくい要素を特定**
2. **その要素を薄いラッパーに隔離**
3. **ロジックはラッパーを呼び出すだけに**
4. **テスト時はラッパーをモック化**

### 例

```javascript
// Before: 時刻がハードコード
function isBusinessHour() {
  const hour = new Date().getHours();
  return hour >= 9 && hour < 17;
}

// After: 時刻取得を分離
function isBusinessHour(getCurrentHour = () => new Date().getHours()) {
  const hour = getCurrentHour();
  return hour >= 9 && hour < 17;
}

// テスト
test('9時は営業時間内', () => {
  assert(isBusinessHour(() => 9) === true);
});

test('17時は営業時間外', () => {
  assert(isBusinessHour(() => 17) === false);
});
```

---

## 4. テスト戦略: リクエスト/レスポンス境界

### 概要

リクエスト/レスポンスレベルでテストを書くと、実装から距離を取りつつ安定したテストになる。

```
[ユーザー] ←→ [UI] ←→ [Handler] ←→ [ロジック]
                       ↑
                  ここを砦にする
```

### 理由

- 実装から距離を取りつつ安定
- 内部設計が変わっても壊れにくい
- 細かいユニットテストより先に書くべき

### 適用

1. **エントリポイントを特定**（Handler、Controller、API等）
2. **入力と期待出力を定義**
3. **内部実装を気にせずテスト**

---

## 5. ソフトウェア開発の3本柱

t-wada氏による優先順位:

| 優先度 | 柱 | 理由 |
|--------|-----|------|
| 1位 | **バージョン管理** | ないと危険すぎる。まず現状をGitに |
| 2位 | **自動化** | レバレッジが効く。一人の自動化が全員を救う |
| 3位 | **テスト** | 0件→1件が最大の関門。網羅性より動くテストを優先 |

---

## レガシーコードリファクタリングのフロー

```
1. バージョン管理の確認
   └─ Gitに入っていない → まずコミット

2. テストの有無を確認
   └─ テストなし → Characterization Test作成

3. Seamの作成（必要に応じて）
   └─ テストしにくい要素 → パラメータ化やDI

4. リファクタリング実行
   └─ 小さなステップ、1変更1コミット

5. テストで振る舞い保存を確認
```

---

## 参考文献

- Michael Feathers『レガシーコード改善ガイド』
- [t-wada - 実録レガシーコード改善](https://speakerdeck.com/twada/working-with-legacy-code-the-true-record)
- [Key Points of Working Effectively with Legacy Code](https://understandlegacycode.com/blog/key-points-of-working-effectively-with-legacy-code/)
