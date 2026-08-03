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

読者テストが検出するのは次の類型。

- 未定義の略語・固有名詞
- 暗黙の前提（読者が知っている保証のない背景知識）
- 論理の飛躍
- 手順の前提環境の欠落（ハンズオン資料で環境構築が書かれていない等）
- 読了後にとるべき行動の不明確さ

この工程だけを既存文書（ADR・README・ナレッジ）に単独適用できるよう、`skills/reader-test/` として切り出した。

### 本質は生成ではなく知識の抽出

一発生成では、モデルが一般論で空白を埋めた「正しいが誰の文書でもない」文章になる。
doc-coauthoring は生成の前にヒアリングを挟み、ユーザーの頭の中にしかない判断基準・経験・固有の文脈を先に言語化させる。
回答が曖昧なら選択肢を提示して問いを具体化し（「試せるレベルまでか、その場で作るところまでか」）、段階的な深掘りでユーザー自身の頭も整理されていく。

SKILL.md には「曖昧な承認をそのまま受け入れず、具体的なフィードバックを求める」指示が含まれる。
ユーザーが「良いですね」と流すことを防ぐ設計で、承認のコストを意図的に上げて品質を担保する。
エージェントの承認付きツール実行が「実行を止める HITL」なら、これは「思考停止を止める HITL」と言える。

推敲は部分編集で行い、全体を書き直さない。
ユーザーが書いた表現と過去の推敲を消さないための制約で、これも「知識はユーザー側にある」という前提の帰結。

### 適するケースの判定基準

ユーザー固有の知識が必要かどうかで分かれる。

| 文書タイプ | 適否 | 理由 |
|---|---|---|
| 引き継ぎ資料 | 適する | 担当者の頭の中の暗黙知を言語化する必要がある |
| オンボーディング資料 | 適する | 前提知識の有無で理解度が大きく変わる |
| 技術選定の意思決定記録 | 適する | 決定の背景と根拠の記録が必要 |
| 競合比較・サービス紹介 | 適さない | 公開情報ベースでユーザー固有の知識が少ない |
| 定型レポート | 適さない | internal-comms のようなフォーマット型スキルの領分 |

### SKILL.md 実物の設計詳細（2026-08 確認）

375 行の SKILL.md を実物確認した。ドキュメント記事には出てこない設計判断が読み取れる。

- **数値の固定** — 初期質問 5 問、追加質問 5-10 問、ブレインストーム選択肢 5-20 個と、全ステージで数を固定している。「適切な数の質問をする」ではなく数で縛るのは、曖昧語を排除する指示プロンプト設計そのもの
- **台本ではなく行為の記述** — ユーザーに見せる文言を verbatim で持たず、`Announce intention to...` `Ask if...` という三人称の行為指示で書く。文言はモデルが都度組み立てる
- **Stage 1 の終了条件が「質問の質」** — "Sufficient context has been gathered when questions show understanding"。集めた情報量ではなく、edge case やトレードオフを聞ける段階に達したかで判定する
- **停滞検知** — 実質的な変更のない反復が 3 回続いたら、追加ではなく削除の提案に転じる
- **"slop" の名指し** — 完成前チェックに "Anything that feels like 'slop' or generic filler" が入っている
- **最終責任の返却** — "they own this document and are responsible for its quality" と、品質責任を人間に戻して終わる
- 読者テストのゴールは "no context bleed" と明示され、サブエージェントには "just the document content and the question" だけを渡す

### 最新動向（2026-08 リサーチ）

**コンテキスト分離の効果は実測で裏付けられた。**
Cross-Context Review（arXiv:2603.12123、2026-03）が、注入誤り 150 件の検出率で 4 条件を比較している。
fresh session 28.6%、自己レビュー 24.6%、親の文脈を渡したサブエージェント 23.8%。
サブエージェント化しても親のコンテキストを渡すと自己レビュー以下に落ち、同一セッションの反復レビューは効果がない（p=0.11）。
doc-coauthoring の「文書だけ渡す」制約は、この結果を先取りしていたことになる。

**製品化はまだ空白地帯。**
Mintlify / ReadMe / Vale / Notion AI 等に「コンテキストを持たない LLM に読ませて曖昧さを検出する」機能は見当たらない（2026-08 時点）。
スキル 1 枚で実装できる領域が製品側で埋まっていない。

**「LLM も読者」が実測で拮抗した。**
Mintlify の自社基盤分析（7.9 億リクエスト、2026-03）で、AI エージェント 45.3% とブラウザ 45.8% がほぼ同数。
Claude Code 単独で全体の 25.2% を占め、Windows 版 Chrome を上回った。
読者テストの「読者」に人間だけでなくエージェントを含める理由が数字で出ている（llms.txt や Diátaxis 再評価も同じ潮流）。

**知識抽出（knowledge elicitation）には副作用の報告がある。**
発散・収束ペルソナの RCT（arXiv:2510.26490、n=105）で、アイデアの独自性は向上した一方、解の所有感（authorship）が有意に低下した（p=.018）。
CHI 2026 の Reactive Writers 研究は「書き手は AI の影響に気づかないまま、編集できるがゆえに制御していると感じる」と報告する。
doc-coauthoring が「ユーザーに直接編集させず口頭で指示させる」「最終読了の責任を人間に戻す」のは、この所有感の喪失への対抗設計と読める。

**方針は 2 派に分岐している。**
Anthropic の doc-coauthoring / Interviewer は人間から引き出す方向、OpenAI の GPT-5.2 プロンプトガイドは「確認質問を避け、曖昧さは指示側で潰す」方向。
対立ではなく、引き出すべき知識が人間の頭の中にあるか（引き継ぎ・意思決定）、外部の文献やコードにあるか（調査・実装）での使い分けと整理できる。

### 手持ちスキルとの関係

japanese-tech-writing / cognitive-rhythm-writing は**文体の規範**、doc-coauthoring は**執筆のプロセス**で、レイヤーが違う。
組み合わせると「doc-coauthoring のプロセスで進め、文体は japanese-tech-writing に従い、最後に読者テスト」という 3 層になる。

## このリポジトリへの反映

- `skills/mcp-builder-go/` — 公式 mcp-builder は Python / Node.js のみで Go ガイドがない。公式 Go SDK（modelcontextprotocol/go-sdk）ベースの Go 版を追加（詳細はスキル本体）
- 検証実装は `../mcp/weather_go/`（Open-Meteo、API キー不要）。agent リポ genkit-agent の MCP 接続テストの相手も兼ねる
- `skills/reader-test/` — doc-coauthoring の Stage 3（読者テスト）を単体スキル化。既に書き上がった文書に、執筆コンテキストを持たないサブエージェントでの盲点検出だけを適用する

## 出典・参考

- https://github.com/anthropics/skills/tree/main/skills/mcp-builder
- https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring
- https://modelcontextprotocol.io/
- https://github.com/modelcontextprotocol/go-sdk
- https://arxiv.org/abs/2603.12123 （Cross-Context Review）
- https://arxiv.org/abs/2310.11589 （GATE、Generative Active Task Elicitation）
- https://arxiv.org/abs/2510.26490 （発散・収束ペルソナ RCT）
- https://code.claude.com/docs/en/best-practices （adversarial review の注意点）
- https://www.mintlify.com/blog/state-of-ai （AI トラフィック実測）
- https://www.anthropic.com/research/anthropic-interviewer
