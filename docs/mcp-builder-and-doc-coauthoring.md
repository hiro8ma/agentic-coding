---
title: "mcp-builder / doc-coauthoring — 構築ガイド型と対話プロセス型のスキル設計"
date: "2026-08-01"
tags: [agent-skills, mcp-builder, doc-coauthoring, fastmcp, tool-annotations, reader-testing]
---

# mcp-builder / doc-coauthoring

anthropics/skills の MCP サーバー構築スキルと文書共同執筆スキルを設計例として読む。
ドキュメント処理 4 スキルは `document-skills.md`、Web アプリ構築と E2E は `webapp-skills.md` を参照。

## mcp-builder — 開発プロセスそのものをスキル化する

FastMCP（Python）と MCP SDK（Node.js）で外部サービス連携の MCP サーバーを作るガイドスキル。
これまでのスキルが「操作の手順」だったのに対し、mcp-builder は Research → Implementation → Review → Evaluation という**開発プロセス全体**を規範化している。

```
skills/mcp-builder/
├── SKILL.md              # 全体方針と 4 段階プロセス
├── reference/
│   ├── python_guide.md   # FastMCP 実装ガイド
│   └── node_guide.md     # Node.js SDK 実装ガイド
└── scripts/
    ├── connections.py    # MCP 接続テスト
    └── evaluation.py     # サーバー評価ツール
```

言語別ガイドを reference/ に分離する段階的開示と、検証をスクリプトに寄せる設計はこれまでの公式スキルと同じ型。

### ツールアノテーションはリスクラベルの標準形

SKILL.md のツール設計原則でいちばん重要なのはアノテーション。

| アノテーション | 意味 | エージェント側の判断 |
|---|---|---|
| readOnlyHint | 読み取り専用 | 自動実行してよい |
| destructiveHint | 破壊的操作 | 実行前にユーザー確認 |
| idempotentHint | 冪等 | リトライしてよい |
| openWorldHint | 外部環境へ影響 | 影響範囲の告知 |

これは「どのツールを自動実行し、どれに人間の承認を挟むか」という承認フロー設計の入力になる。
agent リポの genkit-agent で実装した承認付きツール実行（書き込み系だけ pending → 人間承認）は、このアノテーションをサーバー側が宣言し、クライアント側が解釈する形の自前版と言える。
組織 AI 設計のリスクレベル分類（L0-L3）を、MCP はプロトコルの語彙として持っている。

### 自分の mcp/ リポとの接続

mcp/ の 14 サーバー（FastMCP）は mcp-builder が出力するものと同じ形。
取り込む価値があるのは次の 3 点。

1. アノテーションの明示 — 既存サーバーのツールに readOnlyHint / destructiveHint を付与する
2. evaluation.py 型の検証 — サーバーごとの応答形式・エラー処理の機械チェック
3. エラーは is_error: true + LLM が読める形式 — genkit-agent の「エラーを結果に畳み込む」toolResult パターンと同じ原則が MCP 仕様側にもある

## doc-coauthoring — SKILL.md 1 本で成立するプロセススキル

```
skills/doc-coauthoring/
└── SKILL.md
```

スクリプトなし、リファレンスなし。対話プロセスの定義だけで成立するスキルで、「スキル = スクリプト同梱」ではないことを示す例。

3 段階のワークフローを持つ。

1. **コンテキスト収集** — 目的・読者・前提・避けたい表現をヒアリングで引き出す（1 回で終わらず回答に応じて深掘り）
2. **構造化と推敲** — セクション単位でドラフトと修正を反復。全体の書き直しをせず、ユーザーの表現を残す
3. **読者テスト** — 執筆に関与していない別の Claude（サブエージェント）に読ませ、暗黙の前提・略語・飛躍を洗い出す

### 読者テストは「生成と検証の分離」の文書版

pptx スキルのビジュアル検査（サブエージェント委任）、webapp-testing の E2E と同じ原理が文書にも適用されている。
執筆者と同じコンテキストを持つレビュアーは盲点も共有する。だから検証者はコンテキストを持たない別プロセスにする。
人間レビューの前段に置く品質ゲートとして、そのまま実務に使える。

### 手持ちスキルとの関係

japanese-tech-writing / cognitive-rhythm-writing は**文体の規範**、doc-coauthoring は**執筆のプロセス**で、レイヤーが違う。
組み合わせると「doc-coauthoring のプロセスで進め、文体は japanese-tech-writing に従い、最後に読者テスト」という 3 層になる。

## このリポジトリへの反映

- `skills/mcp-builder-go/` — 公式 mcp-builder は Python / Node.js のみで Go ガイドがない。公式 Go SDK（modelcontextprotocol/go-sdk）ベースの Go 版を追加（詳細はスキル本体）
- 検証実装は `../mcp/weather_go/`（Open-Meteo、API キー不要）。agent リポ genkit-agent の MCP 接続テストの相手も兼ねる

## 出典・参考

- https://github.com/anthropics/skills/tree/main/skills/mcp-builder
- https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring
- https://modelcontextprotocol.io/
- https://github.com/modelcontextprotocol/go-sdk
