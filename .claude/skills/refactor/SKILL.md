---
name: refactor
description: 既存コードの安全なリファクタリング。「リファクタリング」「コード改善」「スメル検出」と依頼された時に使用。振る舞いを変えず内部構造を改善する3フェーズワークフロー。
disable-model-invocation: true
---

# Refactor

既存コードを安全にリファクタリングするスキル。振る舞いを変えず、内部構造のみを改善する。

## 核心原則

> リファクタリングとは、外部的な振る舞いを変えずに、内部構造を改善する作業である
> — Martin Fowler

**安全なリファクタリングの4原則**:
1. テストなしでリファクタリングしない
2. 1変更1コミット
3. 変更後即テスト
4. 失敗時は即座にロールバック

## 前提条件

1. リファクタリング対象のコードが存在
2. 対象コードの役割・責務を理解している
3. **テストの有無を確認済み**（Phase 1で判定）

## 実行手順

**重要**: このスキルは計画（Phase 1-2）と実行（Phase 3）が分離されている。
- Phase 2完了時に必ず停止し、ユーザー承認を待つ
- Phase 3はユーザーからの明示的指示があった場合のみ実行

### Phase 1: 安全性評価 + スメル検出（並列）

**必須**: 3つのTask toolを**単一メッセージで並列実行**

| 観点 | モデル | 目的 |
|------|--------|------|
| テストカバレッジ | Haiku | テスト有無の判定 |
| 影響範囲分析 | Sonnet | 変更の波及範囲特定 |
| スメル検出 | Sonnet | コードスメルの特定 |

#### 1.1 テストカバレッジ確認

```
対象コードに対するテストの有無を確認:
1. テストファイルの存在確認（*.test.*, *.spec.*）
2. 対象関数/クラスへのテストの有無
3. カバレッジレベルを判定（HIGH/MEDIUM/LOW/NONE）

結果を報告:
- カバレッジレベル
- テストファイル一覧
- カバーされていない箇所
```

#### 1.2 影響範囲分析

```
対象コードの影響範囲を特定:
1. 参照元（この関数/クラスを呼び出す箇所）
2. 依存先（この関数/クラスが依存する箇所）
3. 影響ファイル数と行数

結果を報告:
- 影響ファイル一覧
- 影響レベル（HIGH: 10ファイル超、MEDIUM: 3-10、LOW: 1-2）
```

#### 1.3 スメル検出

```
対象コードからコードスメルを検出:
→ references/smell-catalog.md を参照

検出したスメルを報告:
- スメル名
- 該当箇所（ファイル:行）
- 深刻度（HIGH/MEDIUM/LOW）
- 推奨手法
```

### Phase 1 結果評価

結果を統合し、リスクレベルを判定:

| 条件 | リスク | アクション |
|------|--------|----------|
| テストNONE + 影響HIGH | CRITICAL | Characterization Test作成を提案 |
| テストLOW + 影響MEDIUM以上 | HIGH | ステップを細分化、ユーザー承認必須 |
| テストMEDIUM以上 | NORMAL | 通常フロー続行 |

#### テストなしコードへの対処

テストがNONEの場合、3つの選択肢をユーザーに提示:

| 選択肢 | 説明 |
|--------|------|
| **Option A（推奨）** | Characterization Test追加 → リファクタリング |
| Option B | リスク受容で続行（ユーザー承認必須） |
| Option C | 中止 |

Option A選択時は `guides/legacy-code.md` を参照してテスト作成を支援。

### Phase 2: 計画分解

検出したスメルと安全性評価をもとに、リファクタリング計画を作成。

#### 2.1 スメル→手法マッピング

各スメルに対して適用する手法を決定:

```
→ references/smell-catalog.md の「対処法」を参照

例:
- Long Method → Extract Method
- Feature Envy → Move Method
- Duplicate Code → Extract Method/Class
```

#### 2.2 ステップ分解

1変更1コミット単位でステップを分解:

**分解の原則**:
- 各ステップは15-30分で完了可能なサイズ
- 各ステップ後にテストが通る状態を維持
- 依存関係を考慮した順序づけ

#### 2.3 refactor-plan.md 生成

`templates/refactor-plan.md` の形式に従い、カレントディレクトリに `refactor-plan.md` を生成。

### Phase 2 完了

refactor-plan.md生成後、以下を出力してユーザー承認を待つ:

```markdown
## リファクタリング計画作成完了

**保存先**: refactor-plan.md
**検出スメル**: X個
**実施ステップ数**: X
**推定所要時間**: 合計 Xh

**計画内容**:
- [スメル1]: [対処法] - [対象ファイル]
- [スメル2]: [対処法] - [対象ファイル]

**次のステップ**:
計画を確認し、実行する場合は以下を指示してください:
- `refactor-plan.mdを実行して`
- または `/refactor --execute`

中止する場合: `中止`
修正が必要な場合: 修正内容を指示
```

**重要**: この時点で処理を停止し、ユーザーからの指示を待つ。**Phase 3に自動遷移しない**。

### Phase 3: 段階的実行

**開始条件**: ユーザーから以下のいずれかの指示があった場合のみ実行
- `refactor-plan.mdを実行して`
- `/refactor --execute`
- `実行して`
- 明示的な実行指示

**注意**: Phase 2完了時に自動的にこのフェーズに進まない。

refactor-plan.md のステップを順次実行。

#### 3.1 ステップ実行サイクル

```
各ステップで:
1. ベースラインテスト実行（現状が通ることを確認）
2. 単一の変更を実施
3. テスト実行
4. Lint実行
5. 成功 → コミット作成
6. 失敗 → 即座にロールバック（git checkout .）
```

#### 3.2 コミットメッセージ形式

```
refactor: [手法名] - [対象]

- Before: [変更前の状態]
- After: [変更後の状態]
- Technique: [適用した手法]
- Smell: [解消したスメル]
```

#### 3.3 失敗時の対応

テストまたはLint失敗時:
1. `git checkout .` で即座にロールバック
2. 失敗原因を分析
3. ステップを再分割するか、ユーザーに相談

### Phase 3 完了

全ステップ完了後、結果を報告:

```markdown
## リファクタリング完了

**対象**: [ファイル/クラス/関数名]
**実施ステップ数**: X
**解消したスメル**:
- [スメル1]: [箇所]
- [スメル2]: [箇所]

**コミット一覧**:
- abc1234: refactor: Extract Method - calculateTotal
- def5678: refactor: Move Method - validateInput

**品質確認**:
- ✅ 全テスト通過
- ✅ Lint通過
- ✅ 振る舞い保存確認

**次のステップ**:
- /code-review でコードレビュー
```

## 安全性ガードレール

| ガードレール | 実装 |
|------------|----|
| **ユーザー承認必須** | **Phase 2完了時に停止、Phase 3は明示的指示でのみ開始** |
| テスト必須 | Phase 1でテスト有無判定、なければCharacterization Test提案 |
| 1変更1コミット | Phase 3で各ステップ後にコミット |
| 即座のロールバック | テスト/Lint失敗時に`git checkout .`実行 |
| 影響範囲制限 | HIGH判定時にステップ強制分割 |

## コードスメルカタログ

→ `references/smell-catalog.md`

**主要カテゴリ**:
- **Bloaters（肥大化）**: Long Method, Large Class, Long Parameter List
- **Change Preventers（変更の障害）**: Divergent Change, Shotgun Surgery
- **Dispensables（不要な要素）**: Duplicate Code, Dead Code
- **Couplers（結合度の問題）**: Feature Envy, Inappropriate Intimacy

## 安全性チェックリスト

→ `references/safety-checklist.md`

## レガシーコード対応

→ `guides/legacy-code.md`

**主要テクニック**:
- **Characterization Test**: 既存の振る舞いを記録するテスト
- **Seam**: コードを変更せずに振る舞いを変えられる場所
- **Humble Object**: テストしにくい部分を薄く隔離

## 成功基準

1. 検出したスメルが解消されている
2. 全テストが通過している
3. 1変更1コミットで追跡可能
4. 振る舞いが保存されている（外部から見た動作が同一）

## 既存スキルとの連携

```
/refactor（本スキル）
    ↓ 計画生成
refactor-plan.md
    ↓ 大規模な場合
/implement（オプション）
    ↓ 完了後
/code-review（推奨）
```

## よくあるパターン

| パターン | スメル | 手法 |
|---------|-------|------|
| 長すぎるメソッド | Long Method | Extract Method |
| 神クラス | Large Class | Extract Class |
| 機能の横恋慕 | Feature Envy | Move Method |
| データの群れ | Data Clumps | Introduce Parameter Object |
| 重複コード | Duplicate Code | Extract Method/Class |
