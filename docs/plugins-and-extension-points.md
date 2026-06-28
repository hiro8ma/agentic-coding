---
title: "Claude Code の拡張ポイントとプラグイン — Skills / Subagents / Hooks / MCP の役割分担"
date: "2026-06-28"
tags: [claude-code, plugins, skills, subagents, hooks, mcp, marketplace, extension-points]
---

# Claude Code の拡張ポイントとプラグイン

## TL;DR

Claude Code には 4 つの拡張ポイントがある。Skills は手順を会話に注入し、Subagents は作業を別コンテキストへ委譲し、Hooks はイベントで決定論的にスクリプトを実行し、MCP は外部サービスへ接続する。プラグインはこの 4 つを詰めて配布する「箱」で、中身は自由に組み合わせられる。公式スキルはマーケットプレイス（`anthropics/skills`）から `/plugin` で導入し、`~/.claude/plugins/cache/` に展開される。

各論は [[agent-skills]]（Skills の仕様と配布）と [[subagents]]（コンテキスト分離）に分ける。本ノートは 4 点の役割分担とプラグインの全体像に絞る。

## 4 つの拡張ポイント

4 点は競合せず補完する。判断の主体と「何を渡すか」で区別すると混ざらない。

| 拡張ポイント | 何を渡すか | 判断の主体 | いつ動くか |
|---|---|---|---|
| Skills | 手続き的知識・ワークフロー | LLM が解釈して実行 | タスクに応じて自動、または `/skill-name` で明示 |
| Subagents | 作業そのものの委譲 | LLM が分割を判断 | 複雑なタスクを分けるとき |
| Hooks | 決定論的なスクリプト | 設定したイベントで自動 | ツール実行の前後など |
| MCP | 外部サービスへの接続 | LLM がツールとして利用 | 外部データ・操作が要るとき |

### Skills と Subagents の違い

Skills は知識の注入で、Subagents は作業の委譲である。

Skills は現在の会話に手順を足す。Subagents は独立した作業者に一部を任せ、結果だけを返させる。多数ファイルの調査やセキュリティ観点のレビューを並列で回すなら Subagents が向く。

### Skills と Hooks の違い

両者は判断の主体が違う。

Skills の指示は LLM が解釈して実行する。Hooks は決まったタイミングで毎回同じスクリプトを走らせる。ファイル保存前の整形やテスト実行のように、揺らぎを許さない処理は Hooks に寄せる。これは Skill の決定論パート（検証スクリプト）を会話の外へ出した形にあたる。

### Skills と MCP の違い

MCP は接続を、Skills は使い方を提供する。

MCP は「何にアクセスできるか」を与える。Skills は「その接続先をどう使うか」という手順を与える。MCP で社内 API へ繋ぎ、Skill でその API を叩く順番とテンプレートを渡すと噛み合う。能力レイヤー（MCP サーバー側）と手順レイヤー（Skill）の分離で、`mcp/` と `agent/` の二層分割と同じ構図になる。

## プラグインは「箱」

プラグインは 4 つの拡張ポイントを詰めて配布するパッケージである。

中身は自由に決められる。Skills だけを入れてもよいし、Skills と Subagents と Hooks と MCP を組み合わせてもよい。プラグインは中身ではなく箱だと捉えると、設計の自由度が見える。

```
feature-dev plugin
├── Skills      コード確認チェックリスト、レビュー観点
├── Subagents   リサーチ担当、レビュー担当
├── Hooks       保存時の書式チェック、テスト実行
└── MCP         GitHub、DB、Slack への接続
```

チームの標準ワークフローを 1 つの箱にまとめれば、全員へ同じ開発環境を配れる。

## 公式スキルのインストール

公式スキルはマーケットプレイス経由で入れる。導入手順は [[agent-skills]] に詳しいので、ここでは要点だけ示す。

```
/plugin marketplace add anthropics/skills   # マーケットプレイスを追加
/plugin                                       # Discover / Installed / Marketplaces タブ
```

導入時にスコープを選ぶ。

| スコープ | 範囲 |
|---|---|
| User | 自分の全プロジェクト |
| Project | このリポジトリの全コラボレーター |
| Local | このリポジトリで自分だけ |

自分の環境で使うなら User を選ぶ。インストール後は Claude Code を再起動し、`/skills` で一覧に出れば完了となる。実体は `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/` に展開される。

## 公式スキルのカタログ

公式スキルは 5 カテゴリに整理できる。

| カテゴリ | スキル |
|---|---|
| デザイン | frontend-design、theme-factory、brand-guidelines |
| クリエイティブ | canvas-design、algorithmic-art、slack-gif-creator |
| ドキュメント | pdf、docx、pptx、xlsx |
| コラボレーション | doc-coauthoring、internal-comms |
| 開発 | web-artifacts-builder、webapp-testing、mcp-builder、skill-creator |

開発カテゴリの `skill-creator` はスキル作成を支援する。`mcp-builder` は MCP サーバー作成を支援する。自作スキルを増やす起点に使える。

## 自分の資産との接続

この 4 点は手元のリポジトリの構造と対応する。

- Skills は `agentic-coding/skills/`（japanese-tech-writing、knowledge-note、weekly-report を user skill 化済み）
- Subagents は実装委譲の implementer など、コンテキスト分離の運用
- MCP は `mcp/` の能力レイヤー（memory、calc、external_api 等）
- Hooks は決定論パートの逃がし先で、weekly-report の `scripts/validate.py` のような検証をイベント駆動にできる

公式の `mcp-builder` と `skill-creator` は、`mcp/` のサーバー追加や `agentic-coding/skills/` の新規スキル作成に直接使える。

## 注意点

スキルの実体が増えると、稼働場所と版管理の正典が分かれる。

user skill は `~/.claude/skills/` に置く。プラグイン経由のスキルは `~/.claude/plugins/cache/` に置く。自作スキルの正典は `agentic-coding/skills/` で版管理する。どこが正典かを決め、編集したら同期する。

## 参考

- Customize Claude Code with plugins — https://claude.com/blog/claude-code-plugins
- Create plugins — https://code.claude.com/docs/en/plugins
- Discover and install prebuilt plugins through marketplaces — https://code.claude.com/docs/en/discover-plugins
- anthropics/skills — https://github.com/anthropics/skills
