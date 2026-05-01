---
title: "コーディングエージェントの GitHub Actions 統合パターン（2026 年）"
date: "2026-05-01"
tags: [claude-code, github-actions, ci, sandbox, agent-automation]
---

# コーディングエージェントの GitHub Actions 統合パターン（2026 年）

Claude Code Action / Cursor Background Agents / OpenHands Cloud Resolver / nano-code 方式など、2026 年に確立されたパターンを比較し、Claude Code 系の運用に転用できるテンプレートを示す。

## 主要な統合方式の比較

| ソリューション | trigger | 実行環境 | PR 化 | 認可 |
|---|---|---|---|---|
| anthropics/claude-code-action | `@claude` メンション、Issue/PR/review コメント | GitHub-hosted runner | 自動 | Bedrock / Vertex / OIDC |
| Cursor Background Agents | Slack / GitHub | リモート VM | 自動 | OAuth |
| OpenHands Cloud Resolver | Issue ラベル | リモート runtime / self-hosted | 自動 | API key |
| nano-code 方式（最小教材） | `workflow_dispatch` + `issues.opened` | GitHub-hosted runner | 手動 commit / push | author_association |

## 最小構成テンプレート

教材として参照しやすい最小形。`permissions: {}` でデフォルト最小化し、job 単位で必要権限を付与する。

```yaml
name: agent-run

on:
  workflow_dispatch:
  issues:
    types: [opened]

permissions: {}  # デフォルト最小、明示で昇格

jobs:
  run:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' ||
      contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
    permissions:
      contents: write
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
      - run: bun install
      - run: bun run bin/agent.ts
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          PROVIDER: ${{ vars.PROVIDER }}
          MODEL: ${{ vars.MODEL }}
          ISSUE_NUMBER: ${{ github.event.issue.number }}
```

## ポイント

### 1. permissions: {} で最小化、明示で昇格

GitHub Actions のデフォルト権限は read/write の組み合わせが緩い。`permissions: {}` を workflow 全体に置き、job 単位で `contents: write` 等を明示する。

```yaml
permissions: {}

jobs:
  run:
    permissions:
      contents: write       # commit / push
      pull-requests: write  # PR 作成
      issues: write         # コメント追加
```

### 2. author_association で実行可能ユーザーを制限

外部からの Issue 起動を悪用されないよう、`author_association` でメンバーのみに制限。

```yaml
if: contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.issue.author_association)
```

`OWNER` / `MEMBER` / `COLLABORATOR` のいずれかでない外部 Issue は無視される。これがないと「fork から PR を投げて実行」のようなパターンで API key を引き抜かれるリスクが残る。

### 3. Secrets と Variables の分離

| 種別 | 例 | 配置 |
|---|---|---|
| API key（機密） | `ANTHROPIC_API_KEY` | Secrets |
| プロバイダ設定（非機密） | `PROVIDER=anthropic`, `MODEL=claude-sonnet-4-6` | Variables |
| 機能フラグ | `MAX_STEPS=10` | Variables |

Secrets は workflow ログにマスクされるが、Variables はそのまま表示される。設定値の見通しを良くしつつ機密だけ Secrets に閉じる。

### 4. Claude Code Action の使い分け

`anthropics/claude-code-action` は `@claude` メンションで起動する公式アクション。OIDC で Bedrock / Vertex 経由の利用も可能。

```yaml
on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

jobs:
  claude:
    if: contains(github.event.comment.body, '@claude')
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
      id-token: write  # OIDC
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

教材的に「自作」する場合は nano-code 方式、production で実際にチームで使うなら公式 Action が運用負荷が低い。

## サンドボックス併用の考え方

CI runner 自体は ephemeral なので追加サンドボックスは不要に見えるが、以下のケースでは検討価値あり:

- **untrusted PR からの実行**: fork PR の差分を取り込んで動かす場合、ホスト runner 上で危険。bwrap / Docker でラップする
- **複数のサブタスク並行実行**: タスクごとに分離した環境を用意する
- **ネットアクセス制限**: 特定 API のみ許可、他は遮断する

ローカル開発では bwrap が起動 100ms 未満で軽量。本番マルチテナント想定なら Firecracker（E2B 等）が kernel 分離で安全。

## レビュー bot との接続

Claude Code Action を PR レビュー用途で使う場合、以下の trigger 設計が定石:

```yaml
on:
  pull_request:
    types: [opened, synchronize]
  issue_comment:
    types: [created]
```

`pull_request.synchronize` を入れておくと、PR に追加 commit した時も再レビューが走る。`issue_comment` で `@claude review again` のような明示再実行をサポートする。

レビューコメントの粒度ルール（規約違反 / 設計判断 / 不要返信の 3 分類）はテンプレ化できる。プロンプトに「コメント分類ルール」を埋め込む形で運用する。

## まとめ

GitHub Actions 統合の選択肢は 2026 年時点で多数あるが、共通するエッセンスは:

1. `permissions: {}` で最小化、job 単位で昇格
2. `author_association` で外部実行を制限
3. Secrets と Variables の分離
4. untrusted 入力には追加サンドボックスを検討

教材として nano-code 方式を理解しておくと、公式 Action（Claude Code Action 等）の挙動も把握しやすい。

## 参考

- anthropics/claude-code-action: https://github.com/anthropics/claude-code-action
- Claude Code GitHub Actions docs: https://code.claude.com/docs/en/github-actions
- nano-code: https://github.com/laiso/nano-code
- OpenHands Cloud Resolver: https://github.com/All-Hands-AI/OpenHands
