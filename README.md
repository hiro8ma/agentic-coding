# agentic-coding

コーディングエージェントを使った開発のナレッジ、スキル、設定テンプレートを蓄積するリポジトリ。

対象エージェントは Claude Code、OpenAI Codex、Google Gemini CLI / Antigravity、Cursor。

## 概要

このリポジトリは、ベンダーをまたいだエージェント駆動開発の再利用可能なナレッジを集める。

扱うのはルールファイル（[CLAUDE.md](https://code.claude.com/docs/memory) / [AGENTS.md](https://agents.md/) / GEMINI.md）、[Agent Skills](https://agentskills.io)（`SKILL.md`）、[コマンド](https://code.claude.com/docs/commands)、[フック](https://code.claude.com/docs/hooks)、[MCP サーバー](https://code.claude.com/docs/mcp)、[設定](https://code.claude.com/docs/settings)。

Skill は Markdown とディレクトリだけで構成するため、同じ Skill を Claude Code、Codex、Cursor、VS Code / GitHub Copilot、Gemini CLI で使い回せる。

## 構成

- **CLAUDE.md** — メインのルールファイル（リポジトリ単位の指示）
- **docs/** — エージェント横断のナレッジ
  - `agent-skills.md` — Agent Skills の仕様、段階的開示、各社の採用実態
  - `context-design.md` — Vibe Coding のためのコンテキスト設計、CLAUDE.md / Skills / MCP / Subagents の責務分離
  - `spec-driven-development.md` — AI協働開発のための仕様駆動ワークフロー、docs / .steering の使い分け
  - `plugins-and-extension-points.md` — Skills / Subagents / Hooks / MCP の役割分担とプラグイン
  - `design-skills.md` — frontend-design / theme-factory / canvas-design と転用できる設計哲学
  - `subagents.md` — サブエージェントのパターン
  - `coding-agent-github-actions.md` — CI でのコーディングエージェント運用
  - `pr-review-bot-workflow.md` — PR レビュー bot
  - `security.md` — セキュリティガイドライン
- **skills/** — 可搬な Agent Skills（`SKILL.md` + scripts / references / assets）
  - `knowledge-note/` — ナレッジノートを書く
  - `weekly-report/` — 週次の進捗報告を作る
  - `japanese-tech-writing/` — 日本語技術文書のライティング規範（出典 [k16shikano 氏の gist](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d)、Unlicense）
  - `context-audit/` — CLAUDE.md / AGENTS.md / Skills / MCP / Hooks / Subagents のコンテキスト監査
  - `spec-workflow/` — docs / .steering を使うスペック駆動開発ワークフロー
  - `brand-template/` — ブランド（配色・書体・トンマナ）を成果物に自動適用するガードレール型スキルのテンプレート
- **.claude/** — Claude Code の設定と言語別ガイドライン
  - `commands/` — カスタムスラッシュコマンド
  - `skills/` — Claude Code の Skill
  - `hooks/` `mcp/` `settings/` — 設定テンプレート
  - `architecture/` — 共通のアーキテクチャパターン
  - `go/` `rust/` `typescript/` — 言語別のスタイル、ガイドライン、パターン

## エージェント間での Skill 可搬性

| エージェント | Skill 配置 | 呼び出し |
|---|---|---|
| Claude Code | `.claude/skills/` | 自動 / スラッシュコマンド |
| OpenAI Codex | `.agents/skills/` | 自動 / `/skills` / `$cmd` |
| VS Code / GitHub Copilot | `.github/skills/` | 自動検出 |
| Google Antigravity | `.agents/skills/` | 自動検出 |
| Cursor | `SKILL.md` を検出 | 自動 / スラッシュコマンド |

`SKILL.md` の本文はツール間で同一で、検出するディレクトリだけが異なる。詳細は `docs/agent-skills.md` を参照。

## コマンド

| コマンド | 説明 |
|---|---|
| `/review` | 現在のブランチの変更をレビューする |
| `/explain` | ファイル内のコードを説明する |
| `/test` | プロジェクトのテストを実行する |
| `/lint` | プロジェクトのリンターを実行する |
| `/format` | プロジェクトのコードを整形する |
| `/build` | プロジェクトをビルドする |
| `/status` | git の状態を表示する |

## スキル

| スキル | 説明 |
|---|---|
| `/refactor <target>` | 指定したコードをリファクタリングする |
| `/fix <issue>` | 報告された問題を修正する |
| `/doc <target>` | ドキュメントを生成する |
| `/add <feature>` | 新機能を追加する |
| `/search <term>` | コードベースを検索する |
| `/rename <old> <new>` | コードベース全体で名前を変更する |
| `/debug <issue>` | 問題をデバッグする |
| `/commit-message` | ステージした変更からコミットメッセージを生成する |
| `/diagram <target>` | ASCII 図を作成する |
| `/migrate <target>` | コードを新しいバージョン/フレームワークへ移行する |
| `/security <target>` | セキュリティ監査を行う |
| `/context-audit <target>` | コンテキスト設計を監査する |
| `/spec-workflow <target>` | 仕様駆動開発の要求・設計・タスクを作成する |

## 使い方

このリポジトリの内容をプロジェクトに適用すると、コーディングエージェントが一貫した規約に従ってコードを生成・レビューする。

可搬なスキルは、対応する任意のエージェントで再利用できる。
