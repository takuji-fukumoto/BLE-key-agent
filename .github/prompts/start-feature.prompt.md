# 機能実装開始

ユーザーの指示内容: `<ここに要件を入力>`

## 手順

以下を順番に実行する。実装コードのコミット・プッシュは行わない（PR作成用の空コミットは許可）。

### Step 1: 仕様書確認

`CLAUDE.md` と `.github/copilot-instructions.md` のルールに従い、関連仕様書を読む。

- `docs/requirements.md`
- `docs/architecture.md`
- 関連する `docs/spec-*.md`

### Step 2: ブランチ作成

- `main` から `feature/<短い英語名>` を作成してチェックアウト

### Step 3: 空コミット作成

- `git commit --allow-empty -m "chore: start feature <短い英語名>"` を実行
- `git push -u origin feature/<短い英語名>` を実行

### Step 4: Draft PR 作成

- `gh pr create --draft` で Draft PR を作成
- PR本文はひとまず最小で作成し、作成直後に概要・変更予定・フェーズ別チェックリストを追記

### Step 5: 実装 plan 作成

- `plan/[YYYYMMDDHHMMSS]_<plan概要>.md` を作成
- タスクはチェックボックスで具体的に分解
- タスク名に `[PhaseX]` プレフィックスを付与
- Todo リストにも同内容を反映

### Step 6: PR チェックリスト更新

- plan / TODO と 1:1 で PR チェックリストを更新

### Step 7: レビュー待ち

- 計画を提示してレビュー依頼
- 承認前は実装開始しない
