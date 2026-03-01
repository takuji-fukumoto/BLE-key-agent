# Copilot Prompt Files

`.claude/commands/*.md` の運用を、GitHub Copilot で再利用しやすい Prompt ファイルに移植したもの。

## 使い方

1. Copilot Chat を開く
2. Prompt files から以下を選択して実行する
   - `dev.prompt.md`
   - `start-feature.prompt.md`
   - `complete-feature.prompt.md`
   - `create-skill.prompt.md`
3. 引数が必要なものは、実行時メッセージ内の `<...>` を具体値に置き換える

## Claude 側との対応関係

- `dev.prompt.md` ↔ `.claude/commands/dev.md`
- `start-feature.prompt.md` ↔ `.claude/commands/start-feature.md`
- `complete-feature.prompt.md` ↔ `.claude/commands/complete-feature.md`
- `create-skill.prompt.md` ↔ `.claude/commands/create-skill.md`

Claude 側の案内ファイルは `.claude/commands/README.md`。

## 相互同期ルール

片方を変更したら、対応するもう片方にも同じ意図の更新を反映する。

1. 先に変更した側の差分を確定
2. 対応ファイルへ同等の変更を反映
3. `.github/prompts/README.md` と `.claude/commands/README.md` の案内内容を必要に応じて更新

### complete-feature のタグ自動化

- `complete-feature.prompt.md` 実行時に、実行メッセージへ「タグプッシュして」「tag push」などを含めると、
   `scripts/create_and_push_date_tag.sh` を使って `vYYYYMMDD.N` 形式タグを自動採番して push する。
- 指示がない場合はタグ作成を行わない。

### complete-feature のRelease公開自動化

- 実行メッセージへ「リリースノート作成して公開して」「release publish」などを含めると、
   `scripts/create_and_push_date_tag.sh --publish-release` を使ってタグ push 後に
   GitHub Release（自動生成ノート付き）を公開する。
- 指示がない場合はRelease公開を行わない。

## 注意点

- これは `/.claude` のスラッシュコマンド定義の代替テンプレートであり、完全な 1:1 実行環境ではない
- ブランチ作成・PR作成・push など破壊的/外部依存操作は、実行前に現在の状態を確認すること
- `.claude/commands/` と `.github/prompts/` は対応関係を保って運用する
