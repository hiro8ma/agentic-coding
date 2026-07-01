---
title: "Context Design — Vibe Codingのためのコンテキスト設計"
date: "2026-07-01"
tags: [context-engineering, vibe-coding, skills, subagents, mcp, claude-code, codex]
---

# Context Design

Vibe Codingは、AIに「コードを書いて」と丸投げする開発ではない。
人間がエンジニアリングマネージャーのように、目的、制約、作業単位、検証条件、参照情報を設計し、AIエージェントに必要な文脈だけを渡す開発である。

この文書は、`CLAUDE.md`、`AGENTS.md`、Skills、Subagents、MCP、Hooks、セッション指示をどう分離するかの基準を定義する。

## TL;DR

- 常時必要なルールだけを `CLAUDE.md` / `AGENTS.md` に置く
- タスク固有の手順は Skills に切り出す
- 外部状態は MCP / CLI / ブラウザツールで必要時に取得する
- 重い調査やレビューは Subagent に分離する
- 強制したい決定論的処理は Hooks / scripts に寄せる
- 長い会話は `/compact`、タスク切り替えは `/clear` で整理する

## コンテキストは増やすほど良いわけではない

長コンテキストモデルでも、入力が長くなるほど必要情報の取り出しが不安定になる。
似た情報、古い履歴、巨大ログ、生成物、無関係なdiffが混ざると、エージェントは重要な前提を見落としやすくなる。

基本方針は次の通り。

| 方針 | 意味 |
|---|---|
| Keep rules small | 常時読むルールは短く、安定した内容に絞る |
| Load just in time | 外部情報や詳細手順は必要時だけ読む |
| Separate workers | 重い調査は別コンテキストに逃がす |
| Summarize tool output | MCPやCLIの結果は要約・上限・根拠つきで扱う |
| Reset stale context | タスクが変わったら古い会話履歴を捨てる |

## レイヤー分離

| レイヤー | 役割 | 置き場所 | ロード |
|---|---|---|---|
| Project rules | プロジェクト全体の恒久ルール | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | 常時 |
| Task procedures | 繰り返し使う作業手順 | `SKILL.md`, `.claude/skills/*.md` | オンデマンド |
| External state | 最新情報、Issue、DB、ブラウザ状態 | MCP, CLI, browser tools | 必要時 |
| Delegated work | 調査、レビュー、並列作業 | Subagents | 分離コンテキスト |
| Deterministic gates | 強制したい検査・整形・禁止事項 | Hooks, scripts, CI | イベント時 |
| Session intent | 今回だけの目的・制約 | ユーザー指示 | 現在セッション |

## どこに何を書くか

### `CLAUDE.md` / `AGENTS.md`

書くもの。

- 技術スタックと標準コマンド
- ディレクトリ構造
- アーキテクチャ方針
- セキュリティ禁止事項
- テスト・lint・build方針
- コミット・PR方針
- 関連リポジトリの責務

書かないもの。

- 長い手順
- 具体例を大量に含むテンプレート
- 頻繁に変わるIssue状況
- 巨大なAPI仕様
- ブラウザ操作ログ
- 生ログや生成物

### Skills

Skills は「何度も貼っている手順」をパッケージ化する。
`SKILL.md` は短い実行手順に絞り、詳細は `references/`、雛形は `assets/`、決定論的処理は `scripts/` に分ける。

向いているもの。

- PRレビュー
- デバッグ
- セキュリティ監査
- 設計書作成
- ドキュメント生成
- リリース手順
- コンテキスト監査

### Subagents

Subagents は「別コンテキストの作業者」である。
メイン会話に大量のファイルやログを読ませず、結果だけを受け取る。

向いているもの。

- 多数ファイルの調査
- セキュリティ観点のレビュー
- パフォーマンス観点のレビュー
- UI崩れ確認
- ライブラリ更新の影響調査
- 実装案の比較

依頼時は、背景を渡しすぎず、次の4点だけを明確にする。

- 目的
- 対象範囲
- 読んでよい情報
- 出力形式

### MCP / CLI / ブラウザツール

MCP は外部システムとの接続口である。
コンテキストを常時増やすためではなく、必要な外部状態を必要時に取りに行くために使う。

MCPサーバーやツールの出力は、次の形にすると扱いやすい。

| 出力項目 | 内容 |
|---|---|
| summary | 短い要約 |
| evidence | 根拠、URL、ファイルパス、行番号 |
| limit | 取得件数・文字数の上限 |
| raw_ref | 生データへの参照。必要時だけ開く |
| next_actions | 次に見るべき候補 |

### Hooks / scripts

LLMに毎回判断させる必要がない処理は scripts に寄せる。
さらに、毎回必ず実行したいものは Hooks や CI に寄せる。

例。

- secret scan
- formatter
- lint
- typecheck
- test
- frontmatter validation
- generated file check

## `/compact` と `/clear`

| 操作 | 使う場面 |
|---|---|
| `/compact` | 同じ目的の長い作業を続けるが、会話履歴が重くなったとき |
| `/clear` | 目的が変わるとき、古い前提を消したいとき |

1つのセッションに、設計、実装、レビュー、修正、ドキュメント化を詰め込みすぎない。
タスク単位を分けた方が、コンテキストの鮮度を保ちやすい。

## プロンプト設計

悪い例。

```text
このコードベース全体を見て改善してください。
```

良い例。

```text
src/api/login.ts の login 関数だけを確認してください。
セッションを明示的にクリアした場合の挙動に限定して、バグがあれば修正し、既存テストに回帰テストを追加してください。
```

対象、観点、制約、検証条件を明示する。
「速くして」ではなく「N+1クエリを解消して」、「きれいにして」ではなく「責務を分離して」のように、技術的に意味のある言葉を使う。

## コンテキスト監査チェックリスト

`/context-audit` Skill で、このチェックリストに沿って監査する。

- `CLAUDE.md` / `AGENTS.md` にタスク固有手順が入りすぎていないか
- Skills に切り出せる長い手順がないか
- Skills の `description` は発動条件を含んでいるか
- `SKILL.md` が長すぎず、詳細を `references/` に逃がしているか
- MCP / CLI の出力は要約・上限・根拠つきになっているか
- Subagent に渡す入力が過剰になっていないか
- Hooks / scripts に寄せるべき決定論的処理を LLM に任せていないか
- `node_modules`、`dist`、巨大ログ、生成物をエージェントが読まない設定になっているか
- タスク切り替え時に `/clear` する運用になっているか

## 関連ドキュメント

- `docs/agent-skills.md`
- `docs/subagents.md`
- `docs/plugins-and-extension-points.md`
- `.claude/hooks/README.md`
- `.claude/mcp/README.md`
- `skills/context-audit/SKILL.md`
