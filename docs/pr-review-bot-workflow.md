---
title: "Claude Code × gh CLI で PR レビュー bot コメントに一括対応するワークフロー"
date: "2026-04-21"
tags: [claude-code, gh-cli, pr-review, automation, code-review]
---

# PR レビュー bot コメント対応ワークフロー

GitHub Actions や自動 bot が PR に大量のレビューコメントを積んだとき、Claude Code + `gh` CLI でコメントを機械的に分類して一括対応するワークフロー

## 前提

- PR に Claude / review bot が 10+ コメント投稿している
- 全部に手で返信すると時間がかかる
- 中には「規約違反で今すぐ直すべき」のと「実装粒度で ADR に書く話ではない」が混在

## 手順

### 1. コメント一覧を取得

```bash
gh api repos/OWNER/REPO/pulls/NUMBER/comments \
  --jq '.[] | {id, path, line, user: .user.login, created_at, body}'
```

Review round ごとに時刻で絞りたいとき

```bash
gh api repos/OWNER/REPO/pulls/NUMBER/comments \
  --jq '.[] | select(.created_at > "2026-04-20T00:00:00Z")'
```

### 2. コメントを 3 分類する

Claude Code に分類させるときのプロンプト目安

> 各コメントを以下の 3 分類に振り分けて、コメント ID とラベルを列挙して
> - `fix`: 規約違反（lint / naming / format）。機械的に直せる
> - `design`: 設計判断が必要。ADR 本文の修正を伴う
> - `skip`: 実装粒度 / 外部参照集中管理 / 意図的な設計。対応不要

分類の判断基準

| ラベル | 例 | 対応 |
|---|---|---|
| `fix` | proto 規約違反、enum プレフィックス漏れ、タイポ | 機械的に修正 + 返信「対応しました（commit hash）」 |
| `design` | 設計判断の指摘、トレードオフ再考要求 | ADR 修正 + 採用理由を本文に追記 |
| `skip` | 実装時決定の粒度、単価集中管理、インフラ構築タスク | 返信「必要じゃない」+ 理由を端的に |

### 3. `fix` を一括修正

Claude Code に修正を任せる。複数ファイルに散らばった場合も Edit / Grep で機械的に処理できる

例：proto enum プレフィックス漏れ

```
Grep: enum FinishReason
Edit: STOP = 1 → FINISH_REASON_STOP = 1
...
```

修正後は 1 commit にまとめる（「proto 規約整合」など指摘の束に合わせた commit message）

### 4. 返信を JSON stdin で投稿

シェルのバッククォート評価事故を避けるため、返信本文は JSON ファイル経由で渡す

```bash
cat > /tmp/reply.json <<'EOF'
{"body":"対応しました（839bcdda2）。`package aiagent.v1;` に変更。","in_reply_to":3110355687}
EOF

gh api repos/OWNER/REPO/pulls/NUMBER/comments \
  -X POST --input /tmp/reply.json --jq '{id, body}'
```

`-F body="... \`...\` ..."` で直接渡すとバッククォート部分がシェル評価されて本文が欠ける事故が起きる（`command not found` エラーが stderr に出つつ、body は空白で POST される）

### 5. `skip` には「必要じゃない」+ 理由を返信

返信文のテンプレート

```
必要じゃない。{理由を 1-2 文}。{ADR でどう扱っているか、またはどこで扱うべきか}
```

例

> 必要じゃない。Vertex AI の単価は MPC-XXX で集中管理しており、ADR ごとに固定値で書くと単価改訂時に複数 ADR を追いかける運用負債になる。本 ADR では規模感（月 15,000 クエリ、1 クエリ ~12,000 tokens）と節減対象まで示しており、単価ベース積算は MPC-XXX 参照で十分

「必要じゃない」と明記することで、次のレビュー round でも bot が同じ指摘を再掲したときに「既に判断済み」のコンテキストが残る

## 返信投稿時の注意

### バッククォート事故

`-F body="... backticks ..."` は避ける。`--input FILE` で JSON を渡すのが安全。実例

```bash
# NG
gh api ... -F body="\`package foo.v1;\` に変更"
# → body = " に変更"（バッククォート内が評価されて消える）

# OK
echo '{"body":"`package foo.v1;` に変更"}' > /tmp/r.json
gh api ... --input /tmp/r.json
```

### in_reply_to を忘れない

`in_reply_to` を省略すると PR 全体への新規コメントになる。レビューコメントへの返信として投稿するには、元コメントの ID を `in_reply_to` に入れる

### 投稿前の確認

私的リポなら直接投稿で良いが、公開リポや業務 PR では

1. 返信案を全件 markdown でダンプ
2. ユーザーに確認依頼
3. OK なら投稿

の 3 ステップを踏む（グローバル規約 `feedback_no_auto_post.md` に従う）

## 派生ワークフロー

### コメント既読管理

```bash
# 解決済みコメントを一覧
gh api graphql -f query='
  query {
    repository(owner: "OWNER", name: "REPO") {
      pullRequest(number: NUMBER) {
        reviewThreads(first: 100) {
          nodes { isResolved id }
        }
      }
    }
  }
'
```

`isResolved = true` のスレッドは既に処理済み。未解決だけに絞って対応する

### PR 概要の reviewer-friendly 化

レビュー前に PR 概要を「レビューのポイント」スタイルに書き直すと、bot も人もレビュー範囲を絞れる

- 決定事項の列挙は避ける（それは ADR 本文の仕事）
- 「ここを見て欲しい」を 3-5 点に絞る
- コミット履歴が散らかっている場合は squash（ただしリモート branch の force-push は個別に許可を取る）

## コミット squash の判断基準

- コミット数が 10+ になり、レビュアーが commit 単位で追えない状態
- 途中の試行錯誤 commit（「WIP」「revert」「もう一度 try」など）が混ざっている
- 最終的な差分として「初期実装」「全面改訂」の 2-3 段階で語れるとき

squash する場合

```bash
git reset --soft <base-commit>
git commit -m "初期実装"  # 差分を新 commit として作り直し
git commit -m "全面改訂"
git push --force-with-lease
```

`--force-with-lease` を使い、`--force` 直は避ける（他者の push を上書きしない保険）

force-push はリポジトリのルールやメモリ規約（`feedback_no_force_push_*.md` 等）に従い、ユーザー許可を取ってから実行する
