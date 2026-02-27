# スキルの作成・改善

ユーザーの指示内容: $ARGUMENTS

新しいスキルの作成、既存スキルの改善、スキルの性能測定を行います。

---

## 実行手順

1. `.claude/skills/skill-creator/SKILL.md` を読み込む
2. SKILL.mdの指示に従い、ユーザーの要求に対応する

## 参照先

スキル本体と関連リソースは `.claude/skills/skill-creator/` に格納:

```
.claude/skills/skill-creator/
├── SKILL.md              # メインのスキル定義・ワークフロー
├── agents/
│   ├── grader.md         # 採点エージェント
│   ├── comparator.md     # ブラインド比較エージェント
│   └── analyzer.md       # 事後分析エージェント
└── references/
    └── schemas.md        # JSONスキーマ定義
```
