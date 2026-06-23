---
title: "Agent Skills — エージェントに手続き的知識を渡すパッケージ形式"
date: "2026-06-11"
source: "https://www.anthropic.com/news/agent-skills"
tags: [claude-code, codex, gemini-cli, cursor, agent-skills, agents-md, progressive-disclosure, mcp, code-execution, open-standard]
---

# Agent Skills

エージェントに「やり方（手続き的知識）」をフォルダ単位で渡す標準形式。`SKILL.md` を中心に、スクリプトと参照資料をまとめて配布する。

## なぜ必要だったか

LLM は学習済みの「宣言的知識」（事実・概念）は持つが、現場固有の「手続き的知識」（この組織での週報の書き方、社内 API の叩き方）は持たない。これを毎回プロンプトやルールファイルに書くと、コンテキストを圧迫する。

### MCP が抱えた3課題

| 課題 | 内容 |
|---|---|
| 手順不足 | MCP はツール（能力）を渡すが「どの順でどう使うか」の手続きは渡せない |
| 通信オーバーヘッド | ツール定義・実行が毎回プロトコル往復を伴う |
| コンテキスト消費 | 接続中の全ツール定義が常時コンテキストに載り続ける |

### 前提が整った

- **サンドボックスの普及**: エージェントが任意コードを安全に実行できる実行環境が一般化
- **Claude Code の普及**: ファイルシステムを直接読み書きするエージェント運用が標準化し、「フォルダを渡せば手順が伝わる」前提が成立

この2つにより、手順を Markdown とスクリプトのフォルダで配り、必要時だけ読み込ませる設計が現実的になった。

## Agent Skills の誕生

- **2025-10-16**: Anthropic が Agent Skills を発表
- **2025-12-18**: `agentskills.io` としてオープン標準化。ベンダー非依存の仕様に

## Agent Skills がもたらす4つのコア能力

| 能力 | 内容 | 例 |
|---|---|---|
| **専門知識のパッケージ化**（Domain expertise） | 暗黙知・最新リファレンスを Skill 化。新人でもベテラン並みの判断 | 「A 社の提案書は予算内訳を細かく」「この API は本番でレート制限が厳しいので必ずキャッシュ」 |
| **新しい能力の付与**（New capabilities） | LLM が苦手な正確な数値計算・集計・ファイル操作をスクリプトに任せる | 売上の合計/前月比、xlsx/pptx 生成、Slack 投稿 |
| **再現可能なワークフロー**（Repeatable workflows） | 多段プロセスを定義し人のばらつきを排除、常に同じ品質・手順 | 週報（収集→整形→レビュー→提出）、リリース（テスト→版→デプロイ→通知） |
| **相互運用性**（Interoperability） | 単純な Markdown + ディレクトリなのでベンダーをまたいで再利用、ロックイン回避 | 1 度作った Skill を Claude / OpenAI / Cursor / VS Code で使い回す |

「LLM が得意（文脈理解・文章生成）」と「苦手（数値計算・集計・ファイル操作）」を Skill のスクリプトで分業するのが②の本質。

## 3つの構成要素

| 要素 | 必須 | 役割 |
|---|---|---|
| `SKILL.md` | 必須 | フロントマター（name/description）+ 本文（手順） |
| `scripts/` | 任意 | 決定論的な処理を担う実行可能スクリプト |
| `references/` `assets/` | 任意 | 参照資料（ガイドライン）・雛形（テンプレート） |

### スクリプト化の利点

- **トークン効率**: 検証ロジックを LLM に推論させず、スクリプト 1 実行で済ませる
- **決定論的信頼性**: 同じ入力に同じ出力。LLM の揺らぎを排除できる箇所はコードに寄せる

## SKILL.md の構造

```markdown
---
name: weekly-report
description: 週次の進捗報告を定型フォーマットで作成する。「週報」「weekly report」等のキーワードで起動。
---

# 本文（手順）
1. 情報収集
2. 構成
3. 執筆ルール
4. 検証
```

`description` は「何をするか」だけでなく「いつ起動するか（トリガー語）」を明示する。エージェントはこの記述だけを見て起動可否を判断するため、トリガーが曖昧だと発火しない。

### フロントマター全フィールド仕様（agentskills.io）

| フィールド | 必須 | 制約 |
|---|---|---|
| `name` | **Yes** | 最大 64 文字、小文字英数字とハイフンのみ。先頭/末尾ハイフン・連続ハイフン禁止。**親ディレクトリ名と完全一致** |
| `description` | **Yes** | 最大 1024 文字。内容 + **発動条件（トリガー）**を記述 |
| `license` | No | ライセンス名 or ファイル参照 |
| `compatibility` | No | 最大 5000 文字。動作環境要件（必要ツール・ネットワーク等） |
| `metadata` | No | 任意の key-value（作者・バージョン等） |
| `allowed-tools` | No | 使用ツールの事前承認リスト（実験的） |

### ディレクトリ構成と参照の規約

- **本文は 500 行以内・5000 トークン以下**（強く推奨）。Activation 時のコンテキスト圧迫を防ぐ防護策。収まらない詳細は `references/` に分割
- **ファイル参照は 1 階層まで**。SKILL.md → `references/REFERENCE.md` / `scripts/extract.py` は OK だが、そこからさらに多段参照させない（エージェントが深読みで迷走・トークン浪費するのを防ぐ）
- **スクリプトは単体動作**。外部ライブラリに暗黙依存せず、依存はコメントに明記、エラー時は原因が特定できるメッセージを出す

### ディレクトリ構成

```
skills/
  weekly-report/
    SKILL.md          # 必須
    scripts/
      validate.py     # 任意
    references/
      guidelines.md   # 任意
    assets/
      template.md     # 任意
```

## 段階的開示（Progressive Disclosure）

Skill は全文を一度に読み込まない。3段階で必要分だけ展開する。

| 段階 | 読み込む内容 | 目安トークン |
|---|---|---|
| Discovery | name + description のみ | 約 100 |
| Activation | SKILL.md 本文 | 5000 未満 |
| Execution | references / assets / scripts を必要分だけ | 必要分のみ |

起動前は description だけが常時メモリに載るため、Skill を多数登録してもコンテキストはほぼ増えない。

## 類似技術との違い

| 方式 | 渡すもの | ロード | 主な用途 |
|---|---|---|---|
| Agent Skills | 手続き＋スクリプト＋資料 | 段階的 | 再現性のあるワークフロー |
| Skills/Projects/GPTs・Gems | 設定・指示文 | 常時 | チャットの人格・前提固定 |
| MCP | ツール（能力） | 常時 | 外部システム接続・データ取得 |
| ルールファイル | 指示文 | 常時 | プロジェクト全体の規約 |

### Skills と MCP は補完関係

MCP は「能力（どこに繋ぐか）」を提供し、Skill は「手続き（どう使うか）」を提供する。MCP で社内 API に繋ぎ、Skill でその API を使う手順とテンプレートを渡す、という組み合わせが噛み合う。能力レイヤー（MCP サーバー側）と手順レイヤー（Skill）の分離。

### クイック判断基準

- **手順・やり方** → Skills
- **知識・背景** → Projects
- **特化型カスタム AI を作る** → GPTs / Gems
- **外部接続・アクセス** → MCP
- **プロジェクト全体のルール・規約** → ルールファイル（CLAUDE.md 等）

**ルールファイルと Skills の一貫性**: 「git ブランチ作成ルール」「命名規則」のような全体規約は CLAUDE.md に集約し、Skill 側はそのルールを含んだ手続きを実行する形にする。両者で矛盾を起こさない整理が重要。

## 設計思想

- **ファイルベース（サーバー不要）**: 実体は単なるファイル+フォルダ。常駐プロセス/専用サーバー不要 → Git でバージョン管理・PR レビュー・変更履歴追跡と好相性
- **LLM ネイティブ**: XML/JSON スキーマでなく LLM が直接理解できる Markdown（自然文）で記述
- **AI ツール非依存**: 2026 現在 Claude Code / OpenAI Codex / Cursor / VS Code / Gemini CLI など 27+ が対応。「どう読み込むか/実行するか」を各ツール実装に委ねる割り切りが広い採用を実現
- **プログラムからの利用**: API（Messages API 等）経由で skill ID 指定 → 自社アプリ・独自エージェントに組み込み可能

## 各社の採用実態（2026 時点）

Agent Skills は Anthropic 以外の主要ベンダーに数か月で広がった。SKILL.md の中身は共通でも、検出ディレクトリと呼び出し方法がツールごとに異なる。

| ツール | スキル配置 | 呼び出し | 対応時期 |
|---|---|---|---|
| VS Code / GitHub Copilot | `.github/skills/` | 自動検出（description マッチで本文ロード） | VS Code 1.108（2025-12） |
| OpenAI Codex | `.agents/skills/` | 自動選択 / `/skills` / `$cmd` | CLI・IDE・アプリ全対応 |
| Google Gemini CLI | スキルディレクトリ | `activate_skill` ツールで自律選択 | v0.24.0（2026-01） |
| Google Antigravity | `.agents/skills/` | 自動検出・段階的開示 | — |
| Cursor | `SKILL.md` を検出 | 自動適用・スラッシュコマンド | v2.4（2026-01） |

OpenAI は `openai/skills` リポで 40+ のキュレーション済みスキルを公開（`$skill-installer` で導入）。Anthropic の `anthropics/skills` に相当し、競合が同一フォーマットで配布していること自体がオープン標準の強さを示す。

### 採用が速い理由（MCP との対比）

| | MCP | Agent Skills |
|---|---|---|
| 実装に必要なもの | クライアント・サーバー間の通信プロトコル実装 | 「SKILL.md を読む」だけ（既存のファイル読込を拡張） |
| データ形式 | JSON-RPC スキーマ（専用パーサー） | Markdown（LLM がそのまま読む） |
| 必須仕様 | ツール定義・ハンドシェイク | `name` と `description` の2フィールドだけ |

導入ハードルの低さ（ファイルベース / LLM ネイティブ / 仕様のシンプルさ）が、発表から数か月での主要ツール制覇を可能にした。

## ルールファイルとスキルファイルは別物

混同しやすいが解く問題が異なる補完関係。OpenAI が AGENTS.md と SKILL.md の両方を採用するのはこのため。

| 系統 | ファイル | 役割 | ロード |
|---|---|---|---|
| ルールファイル | CLAUDE.md / AGENTS.md / GEMINI.md | プロジェクト全体の規約・コンテキスト | 常時 |
| スキルファイル | SKILL.md | タスク固有の手順 | オンデマンド（description マッチ時のみ） |

### AGENTS.md の歴史と Claude Code 未対応問題

```
2025-02  CLAUDE.md 登場（Claude Code 公開）
2025-08  OpenAI が AGENTS.md 公開（分散したルール記法の統一規格）
2025-12  AGENTS.md が Linux Foundation 傘下 Agentic AI Foundation へ移管
2026-02  AGENTS.md 採用 60,000+ OSS プロジェクト
```

AGENTS.md は CLAUDE.md / GEMINI.md など分散したルール記法を統一するために生まれた後発規格。だが元祖の Claude Code は 2026-06 時点で AGENTS.md をネイティブ未対応（Issue に 5,200+ reaction、Anthropic はロードマップ非表明）。一方 Cursor / Windsurf / Cline は project-root の AGENTS.md をネイティブ対応済（シンボリックリンク不要）。Claude Code の回避策は CLAUDE.md 内に `@AGENTS.md` インポート、またはシンボリックリンク。

## タイムライン

| 時期 | 出来事 |
|---|---|
| 2024-11 | MCP 公開（能力の標準化） |
| 2025-02 | Claude 3.7 + Claude Code（ファイルシステム直接操作の普及、CLAUDE.md 登場） |
| 2025-05 | Code Execution（サンドボックスでのコード実行） |
| 2025-08 | OpenAI が AGENTS.md 公開 |
| 2025-10 | Agent Skills 発表 |
| 2025-12 | agentskills.io オープン標準化、AGENTS.md が Agentic AI Foundation へ移管 |
| 2026-01 | Gemini CLI v0.24.0 / Cursor v2.4 が Agent Skills 対応 |
| 2026-02 | AGENTS.md 採用 60,000+ OSS プロジェクト |
