---
title: "Loop Engineering — プロンプトを書く段階から、エージェントに指示を出すループを設計する段階へ"
date: "2026-07-06"
tags: [loop-engineering, claude-code, automation, worktree, subagents, state-management]
---

# Loop Engineering

## TL;DR

Loop Engineering は、AI コーディングエージェントへの個別プロンプト作成から、「エージェントを継続的に指示する自動化ループの構築」へ焦点を移す方法論である。
Boris Cherny の「I don't prompt Claude anymore. I have loops running that prompt Claude」が中核の哲学で、cobusgreyling/loop-engineering がパターン集 + CLI + テンプレートとして体系化した。
ループ自体を LOOP.md（宣言）と STATE.md（状態）で管理し、L1（レポートのみ）→ L2（支援修正）→ L3（無人化）と段階展開する。

## 5 つの構成要素

| 要素 | 役割 |
|---|---|
| Automations / Scheduling | 定期的な検出とトリアージ |
| Worktrees | 安全な並列実行環境 |
| Skills | プロジェクト知識の永続化 |
| Plugins & Connectors | MCP を通じた外部ツール連携 |
| Sub-agents | メーカー / チェッカーの役割分離 |
| + Memory / State | 会話の外に置く耐久的な状態管理 |

Claude Code の拡張ポイント（[[plugins-and-extension-points]]）がそのまま部品になっており、Loop Engineering はそれらの組み合わせ方の設計論にあたる。

## ループを「宣言 + 状態」で管理する

このリポジトリの設計で最も重要なのは、ループ自体をコードと同じ管理対象にしている点である。

- `LOOP.md` — ループ設計の宣言的記述。何を、いつ、どの権限で回すか
- `STATE.md` — 耐久的な外部状態。ループは会話をまたぐため、状態をコンテキストウィンドウに持てない
- `loop-sync` — 宣言（LOOP.md）と実態（STATE.md）の乖離検出

これはスペック駆動開発（[[spec-driven-development]]）の「北極星文書 + ステアリングファイル」と同じ構造で、LOOP.md がループの正典になる。
リポジトリ自身が自分の LOOP.md でメンテナンスループを回している（dogfooding）。

## 実行フロー

```
Schedule/Automation
→ Triage Skill
→ STATE/Memory 読み書き
→ 隔離 Worktree
→ Implementer Sub-agent
→ Verifier Sub-agent（テスト + ゲート）
→ MCP / Git / Tickets
→ Human Gate（許可リスト判定）
→ Commit/PR/Action または人間へエスカレーション
```

Implementer と Verifier の分離（メーカー / チェッカー）、Human Gate、Worktree 隔離という構成は、エージェント実行系の安全設計（Propose → Verify → Authorize → Execute → Audit の 5 段分離）の開発ワークフロー版になっている。

## 7 つの本番パターン

| パターン | 実行頻度 | トークンコスト |
|---|---|---|
| Daily Triage | 1 日〜2 時間 | 低 |
| PR Babysitter | 5〜15 分 | 高 |
| CI Sweeper | 5〜15 分 | 非常に高 |
| Dependency Sweeper | 6 時間〜1 日 | 中 |
| Changelog Drafter | 1 日またはタグ時 | 低 |
| Post-Merge Cleanup | 1 日〜6 時間 | 低 |
| Issue Triage | 2 時間〜1 日 | 低 |

各パターンに実行頻度とトークンコストの目安が付いている。
2026 年のエージェント運用は常にコスト見積もりとセットで、「タスクの価値がコスト増を正当化する場合に限って自動化する」が原則になる。

## 段階展開と Comprehension Debt

- **Phased Rollout** — L1（レポートのみ）→ L2（支援修正）→ L3（無人化）。書き込み権限は挙動を検証してから段階的に解禁する
- **Comprehension Debt** — ループが出荷するコードを人間が読まないと、技術的負債が加速する。自動化しても「読む工程」は省けない
- **Safety First** — 許可リスト、オートマージ制限、MCP スコープによる制約

「自動化しても人手のレビュー工程は省けない」という結論は、評価フライホイールの「人手トリアージは必須（autopilot ではなく flashlight）」と一致する。

## 提供 CLI

| ツール | 用途 |
|---|---|
| loop-init | スターターテンプレートの生成 |
| loop-audit | Loop Ready Score（1〜100）の診断 |
| loop-cost | トークン消費量の推定 |
| loop-sync | STATE.md と LOOP.md の乖離検出 |
| loop-context | ステートフルなメモリ管理と回路遮断 |
| loop-mcp-server | パターン / スキル / 状態の MCP ランタイム |

## このリポジトリでの適用（実施済み）

- **docs-triage ループを L1 で運用中** — ルート直下の `LOOP.md`（宣言）/ `STATE.md`（状態）/ `loop-budget.md`（上限）/ `loop-run-log.md`（記録）+ `.github/workflows/daily-triage.yml`。ナレッジのリンク切れと README とディレクトリ実態の乖離を週次で検査し、Issue 起票のみ行う（LLM 不使用の決定論的チェック）
- **ループ設計チェックリスト** — 作る前の 10 観点は [[loop-design-checklist]] を参照
- **MCP の safe-write-pattern** — `.claude/mcp/github-readonly.mcp.json`（調査用）と `github-propose.mcp.json`（PR 提案用、マージ不可）を権限レベル別に分離
- 自作エージェント（agent/ts）の Action 層（GitHub Actions 統合）は「ループの器」の自作にあたり、LOOP.md / STATE.md の分離を設計に借りる
- CI でのエージェント運用は [[coding-agent-github-actions]]、Implementer / Verifier 分離は [[subagents]] を参照

## 参考

- cobusgreyling/loop-engineering — https://github.com/cobusgreyling/loop-engineering
