# Claude Command Files

`.claude/commands/*.md` は Claude 向けのコマンド定義です。

## 対応関係（GitHub Copilot 側）

- `dev.md` ↔ `.github/prompts/dev.prompt.md`
- `start-feature.md` ↔ `.github/prompts/start-feature.prompt.md`
- `complete-feature.md` ↔ `.github/prompts/complete-feature.prompt.md`
- `create-skill.md` ↔ `.github/prompts/create-skill.prompt.md`

## 同期ルール

片方を変更したら、同じ意図の変更をもう片方にも必ず反映する。

1. 先に変更した側の差分を確定する
2. 対応ファイルへ同等の内容を反映する
3. 両方の案内ファイル（このファイルと `.github/prompts/README.md`）に必要な運用追記を行う

## 参考

- GitHub Copilot 側の案内: `.github/prompts/README.md`