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

## 注意点

- これは `/.claude` のスラッシュコマンド定義の代替テンプレートであり、完全な 1:1 実行環境ではない
- ブランチ作成・PR作成・push など破壊的/外部依存操作は、実行前に現在の状態を確認すること
- `.claude` 配下は変更していない
