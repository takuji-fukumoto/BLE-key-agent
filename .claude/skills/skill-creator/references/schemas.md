# JSONスキーマ

skill-creatorで使用されるJSONスキーマを定義します。

---

## evals.json

スキルの評価を定義します。スキルディレクトリ内の `evals/evals.json` に配置。

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "ユーザーのサンプルプロンプト",
      "expected_output": "期待される結果の説明",
      "files": ["evals/files/sample1.pdf"],
      "expectations": [
        "出力にXが含まれる",
        "スキルがスクリプトYを使用した"
      ]
    }
  ]
}
```

**フィールド:**
- `skill_name`: スキルのフロントマターと一致する名前
- `evals[].id`: 一意の整数識別子
- `evals[].prompt`: 実行するタスク
- `evals[].expected_output`: 成功の人間向け説明
- `evals[].files`: オプションの入力ファイルパスリスト（スキルルートからの相対パス）
- `evals[].expectations`: 検証可能な記述のリスト

---

## history.json

改善モードでのバージョン進行を追跡します。ワークスペースルートに配置。

```json
{
  "started_at": "2026-01-15T10:30:00Z",
  "skill_name": "pdf",
  "current_best": "v2",
  "iterations": [
    {
      "version": "v0",
      "parent": null,
      "expectation_pass_rate": 0.65,
      "grading_result": "baseline",
      "is_current_best": false
    },
    {
      "version": "v1",
      "parent": "v0",
      "expectation_pass_rate": 0.75,
      "grading_result": "won",
      "is_current_best": false
    },
    {
      "version": "v2",
      "parent": "v1",
      "expectation_pass_rate": 0.85,
      "grading_result": "won",
      "is_current_best": true
    }
  ]
}
```

**フィールド:**
- `started_at`: 改善開始のISO形式タイムスタンプ
- `skill_name`: 改善対象のスキル名
- `current_best`: 最高成績のバージョン識別子
- `iterations[].version`: バージョン識別子（v0, v1, ...）
- `iterations[].parent`: 派生元の親バージョン
- `iterations[].expectation_pass_rate`: 採点からの合格率
- `iterations[].grading_result`: "baseline", "won", "lost", または "tie"
- `iterations[].is_current_best`: 現在の最高バージョンかどうか

---

## grading.json

採点エージェントの出力。`<run-dir>/grading.json` に配置。

```json
{
  "expectations": [
    {
      "text": "出力に'田中太郎'の名前が含まれる",
      "passed": true,
      "evidence": "トランスクリプトのステップ3で発見: '抽出された名前: 田中太郎、佐藤花子'"
    },
    {
      "text": "スプレッドシートのB10セルにSUM数式がある",
      "passed": false,
      "evidence": "スプレッドシートは作成されなかった。出力はテキストファイルだった。"
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  },
  "execution_metrics": {
    "tool_calls": {
      "Read": 5,
      "Write": 2,
      "Bash": 8
    },
    "total_tool_calls": 15,
    "total_steps": 6,
    "errors_encountered": 0,
    "output_chars": 12450,
    "transcript_chars": 3200
  },
  "timing": {
    "executor_duration_seconds": 165.0,
    "grader_duration_seconds": 26.0,
    "total_duration_seconds": 191.0
  },
  "claims": [
    {
      "claim": "フォームには12の入力フィールドがある",
      "type": "factual",
      "verified": true,
      "evidence": "field_info.jsonで12フィールドを確認"
    }
  ],
  "user_notes_summary": {
    "uncertainties": ["2023年のデータを使用、古い可能性あり"],
    "needs_review": [],
    "workarounds": ["入力不可フィールドにはテキストオーバーレイで対応"]
  },
  "eval_feedback": {
    "suggestions": [
      {
        "assertion": "出力に'田中太郎'の名前が含まれる",
        "reason": "名前を言及するだけの幻覚文書でも合格する"
      }
    ],
    "overall": "アサーションは存在をチェックしているが正確性をチェックしていない。"
  }
}
```

**フィールド:**
- `expectations[]`: 根拠付きの採点済みアサーション
- `summary`: 合格/不合格の集計
- `execution_metrics`: ツール使用量と出力サイズ（実行者のmetrics.jsonから）
- `timing`: 実時間（timing.jsonから）
- `claims`: 出力から抽出・検証された主張
- `user_notes_summary`: 実行者がフラグした問題
- `eval_feedback`: (オプション) 評価項目の改善提案。採点者が問題を発見した場合のみ

---

## metrics.json

実行エージェントの出力。`<run-dir>/outputs/metrics.json` に配置。

```json
{
  "tool_calls": {
    "Read": 5,
    "Write": 2,
    "Bash": 8,
    "Edit": 1,
    "Glob": 2,
    "Grep": 0
  },
  "total_tool_calls": 18,
  "total_steps": 6,
  "files_created": ["filled_form.pdf", "field_values.json"],
  "errors_encountered": 0,
  "output_chars": 12450,
  "transcript_chars": 3200
}
```

**フィールド:**
- `tool_calls`: ツール種類別のカウント
- `total_tool_calls`: 全ツール呼び出しの合計
- `total_steps`: 主要実行ステップの数
- `files_created`: 作成された出力ファイルのリスト
- `errors_encountered`: 実行中に発生したエラーの数
- `output_chars`: 出力ファイルの合計文字数
- `transcript_chars`: トランスクリプトの文字数

---

## timing.json

実行の実時間。`<run-dir>/timing.json` に配置。

**取得方法:** サブエージェントタスクが完了すると、タスク通知に `total_tokens` と `duration_ms` が含まれます。これらを即座に保存してください — 他の場所には保存されず、後から回復できません。

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3,
  "executor_start": "2026-01-15T10:30:00Z",
  "executor_end": "2026-01-15T10:32:45Z",
  "executor_duration_seconds": 165.0,
  "grader_start": "2026-01-15T10:32:46Z",
  "grader_end": "2026-01-15T10:33:12Z",
  "grader_duration_seconds": 26.0
}
```

---

## benchmark.json

ベンチマークモードの出力。`benchmarks/<timestamp>/benchmark.json` に配置。

```json
{
  "metadata": {
    "skill_name": "pdf",
    "skill_path": "/path/to/pdf",
    "executor_model": "claude-sonnet-4-20250514",
    "analyzer_model": "most-capable-model",
    "timestamp": "2026-01-15T10:30:00Z",
    "evals_run": [1, 2, 3],
    "runs_per_configuration": 3
  },

  "runs": [
    {
      "eval_id": 1,
      "eval_name": "Ocean",
      "configuration": "with_skill",
      "run_number": 1,
      "result": {
        "pass_rate": 0.85,
        "passed": 6,
        "failed": 1,
        "total": 7,
        "time_seconds": 42.5,
        "tokens": 3800,
        "tool_calls": 18,
        "errors": 0
      },
      "expectations": [
        {"text": "...", "passed": true, "evidence": "..."}
      ],
      "notes": [
        "2023年のデータを使用、古い可能性あり",
        "入力不可フィールドにはテキストオーバーレイで対応"
      ]
    }
  ],

  "run_summary": {
    "with_skill": {
      "pass_rate": {"mean": 0.85, "stddev": 0.05, "min": 0.80, "max": 0.90},
      "time_seconds": {"mean": 45.0, "stddev": 12.0, "min": 32.0, "max": 58.0},
      "tokens": {"mean": 3800, "stddev": 400, "min": 3200, "max": 4100}
    },
    "without_skill": {
      "pass_rate": {"mean": 0.35, "stddev": 0.08, "min": 0.28, "max": 0.45},
      "time_seconds": {"mean": 32.0, "stddev": 8.0, "min": 24.0, "max": 42.0},
      "tokens": {"mean": 2100, "stddev": 300, "min": 1800, "max": 2500}
    },
    "delta": {
      "pass_rate": "+0.50",
      "time_seconds": "+13.0",
      "tokens": "+1700"
    }
  },

  "notes": [
    "アサーション'出力がPDFファイルである'は両設定で100%合格 — スキルの価値を識別できない可能性",
    "Eval 3は高分散（50% ± 40%） — 不安定またはモデル依存の可能性",
    "スキルなし実行はテーブル抽出アサーションで一貫して不合格",
    "スキルにより平均実行時間が13秒増加するが、合格率は50%向上"
  ]
}
```

**フィールド:**
- `metadata`: ベンチマーク実行に関する情報
  - `skill_name`: スキル名
  - `timestamp`: ベンチマーク実行時刻
  - `evals_run`: eval名またはIDのリスト
  - `runs_per_configuration`: 設定あたりの実行回数（例: 3）
- `runs[]`: 個別の実行結果
  - `eval_id`: 数値のeval識別子
  - `eval_name`: 人間が読めるeval名（ビューアのセクションヘッダーとして使用）
  - `configuration`: `"with_skill"` または `"without_skill"` のみ（ビューアはこの正確な文字列でグルーピングと色分けを行う）
  - `run_number`: 整数の実行番号（1, 2, 3...）
  - `result`: `pass_rate`, `passed`, `total`, `time_seconds`, `tokens`, `errors` を含むネストされたオブジェクト
- `run_summary`: 設定ごとの統計的集計
  - `with_skill` / `without_skill`: それぞれ `pass_rate`, `time_seconds`, `tokens` オブジェクト（`mean` と `stddev` フィールド付き）
  - `delta`: `"+0.50"`, `"+13.0"`, `"+1700"` のような差分文字列
- `notes`: 分析者からの自由形式の観察

**重要:** ビューアはこれらのフィールド名を正確に読み取ります。`configuration` の代わりに `config` を使ったり、`pass_rate` を `result` の下ではなくrunのトップレベルに置くと、ビューアが空/ゼロの値を表示します。benchmark.jsonを手動生成する際は必ずこのスキーマを参照してください。

---

## comparison.json

ブラインド比較者の出力。`<grading-dir>/comparison-N.json` に配置。

```json
{
  "winner": "A",
  "reasoning": "出力Aは適切なフォーマットと全必須フィールドを備えた完全なソリューションを提供。出力Bは日付フィールドが欠落し、フォーマットに不整合がある。",
  "rubric": {
    "A": {
      "content": { "correctness": 5, "completeness": 5, "accuracy": 4 },
      "structure": { "organization": 4, "formatting": 5, "usability": 4 },
      "content_score": 4.7,
      "structure_score": 4.3,
      "overall_score": 9.0
    },
    "B": {
      "content": { "correctness": 3, "completeness": 2, "accuracy": 3 },
      "structure": { "organization": 3, "formatting": 2, "usability": 3 },
      "content_score": 2.7,
      "structure_score": 2.7,
      "overall_score": 5.4
    }
  },
  "output_quality": {
    "A": {
      "score": 9,
      "strengths": ["完全なソリューション", "適切なフォーマット", "全フィールドあり"],
      "weaknesses": ["ヘッダーの軽微なスタイル不整合"]
    },
    "B": {
      "score": 5,
      "strengths": ["可読な出力", "基本構造は正しい"],
      "weaknesses": ["日付フィールドの欠落", "フォーマットの不整合", "データ抽出が部分的"]
    }
  }
}
```

---

## analysis.json

事後分析者の出力。`<grading-dir>/analysis.json` に配置。

```json
{
  "comparison_summary": {
    "winner": "A",
    "winner_skill": "path/to/winner/skill",
    "loser_skill": "path/to/loser/skill",
    "comparator_reasoning": "比較者が勝者を選んだ理由の要約"
  },
  "winner_strengths": [
    "複数ページ文書の処理に関する明確なステップバイステップの指示",
    "フォーマットエラーを検出するバリデーションスクリプトの同梱"
  ],
  "loser_weaknesses": [
    "'文書を適切に処理する'という曖昧な指示が一貫性のない動作につながった",
    "バリデーションスクリプトがなく、エージェントが即興した"
  ],
  "instruction_following": {
    "winner": { "score": 9, "issues": ["軽微: オプションのログステップをスキップ"] },
    "loser": {
      "score": 6,
      "issues": [
        "スキルのフォーマットテンプレートを使用しなかった",
        "ステップ3に従わず独自のアプローチを発明した"
      ]
    }
  },
  "improvement_suggestions": [
    {
      "priority": "high",
      "category": "instructions",
      "suggestion": "'文書を適切に処理する'を明示的なステップに置換",
      "expected_impact": "一貫性のない動作を引き起こす曖昧さを排除"
    }
  ],
  "transcript_insights": {
    "winner_execution_pattern": "スキル読み取り → 5ステッププロセスに従う → バリデーションスクリプト使用",
    "loser_execution_pattern": "スキル読み取り → アプローチが不明確 → 3つの異なる方法を試行"
  }
}
```
