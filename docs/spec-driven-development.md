---
title: "Spec-Driven Development — AI協働開発のための仕様駆動ワークフロー"
date: "2026-07-02"
tags: [spec-driven-development, sdd, specs, steering, claude-code, codex, kiro, spec-kit]
---

# Spec-Driven Development

Spec-Driven Development は、AIに実装を任せる前に「何を作るか」と「どう作るか」を明文化し、仕様を開発の基準点にする進め方である。

ドキュメントを増やすことが目的ではない。
AIとの合意事項を固定し、実装中の判断を一貫させるための記憶装置として使う。

## What と How

仕様駆動では、What と How を分ける。

| 軸 | 内容 | 主なドキュメント |
|---|---|---|
| What | 何を作るか。誰のどんな課題を解くか | product requirements, feature requirements |
| How | どう作るか。どの構造・技術・品質基準で作るか | architecture, design, development guidelines |

What が曖昧なまま実装すると、AIはそれらしい補完を始める。
How が曖昧なまま実装すると、局所的には動くが、既存設計から外れたパッチワークになりやすい。

## 永続ドキュメントとステアリングドキュメント

仕様を2種類に分ける。

| 種類 | 保存場所 | ライフサイクル | 役割 |
|---|---|---|---|
| 永続ドキュメント | `docs/` | プロダクトや基本設計が変わるまで維持 | プロジェクト全体の北極星 |
| ステアリングドキュメント | `.steering/<date>-<title>/` | 作業単位で作成し、完了後は履歴化 | 今回の変更範囲と実装計画 |

Kiroの steering docs は、プロダクト概要、技術スタック、プロジェクト構造のような基礎情報を常時コンテキストとして扱う。
このリポジトリでは、ツール非依存にするため `docs/` と `.steering/` を標準形として扱う。

## 推奨ファイル構成

```text
docs/
  product-requirements.md
  functional-design.md
  architecture.md
  repository-structure.md
  development-guidelines.md
  glossary.md

.steering/
  20260702-add-priority-filter/
    requirements.md
    design.md
    tasklist.md
```

### `docs/`

| ファイル | 目的 |
|---|---|
| `product-requirements.md` | プロダクトビジョン、対象ユーザー、課題、成功条件 |
| `functional-design.md` | 機能一覧、データモデル、画面、API、ユースケース |
| `architecture.md` | 技術スタック、制約、非機能要件、品質方針 |
| `repository-structure.md` | ディレクトリ構成、配置ルール、命名規則 |
| `development-guidelines.md` | コーディング規約、テスト規約、Git運用 |
| `glossary.md` | ドメイン用語、UI用語、コード命名との対応 |

### `.steering/`

| ファイル | 目的 |
|---|---|
| `requirements.md` | 今回の変更で満たす要求、ユーザーストーリー、受け入れ条件 |
| `design.md` | 実装方針、影響範囲、変更するコンポーネント、テスト方針 |
| `tasklist.md` | 実装タスク、依存関係、完了条件、検証コマンド |

## ワークフロー

### 1. 初回セットアップ

1. `docs/` と `.steering/` を作る
2. `docs/` に永続ドキュメントを作る
3. 初回実装用に `.steering/<date>-initial-implementation/` を作る
4. `requirements.md`、`design.md`、`tasklist.md` を作る
5. `tasklist.md` に沿って実装する
6. 実装後に `docs/` とコードがずれていないか確認する

### 2. 機能追加

1. 既存 `docs/` を読み、What / How の制約を確認する
2. `.steering/<date>-<feature>/requirements.md` を作る
3. `requirements.md` から `design.md` を作る
4. `design.md` から `tasklist.md` を作る
5. タスク単位で実装する
6. 基本設計が変わった場合だけ `docs/` を更新する

### 3. バグ修正

バグ修正は Feature Spec と分ける。

`requirements.md` には次を明記する。

- 再現手順
- 現在の挙動
- 期待する挙動
- 変えてはいけない挙動
- 回帰テストの条件

Kiroの Bugfix Specs でも、修正対象だけでなく「維持すべき挙動」を明示して回帰を防ぐ考え方が採られている。

## 要求の書き方

受け入れ条件は、できるだけテスト可能な形で書く。

```text
WHEN ユーザーが未完了のみフィルタを選択する
THE SYSTEM SHALL 未完了タスクだけを一覧に表示する
```

この形は EARS に近い制約つき自然言語で、人間にもAIにも解釈しやすい。

## 承認ゲート

スペック駆動では、いきなり実装へ進まない。
最低限、次の3ゲートを置く。

| ゲート | 確認すること |
|---|---|
| Requirements approval | 何を作るか、受け入れ条件が明確か |
| Design approval | どう作るか、既存設計と整合しているか |
| Task approval | 実装順序、依存関係、検証方法が明確か |

小さい変更ではゲートを軽くしてよい。
ただし、仕様を省略してよいのは、typo修正や一行修正のような変更に限る。

## Spec Kit との対応

GitHub Spec Kit は、仕様を主成果物として扱い、次の流れを提供する。

| Spec Kit | このリポジトリの標準 |
|---|---|
| constitution | `docs/development-guidelines.md`, `docs/architecture.md` |
| specify | `.steering/<date>-<title>/requirements.md` |
| plan | `.steering/<date>-<title>/design.md` |
| tasks | `.steering/<date>-<title>/tasklist.md` |
| implement | `tasklist.md` に沿った実装 |
| analyze / checklist | 実装前の仕様整合性チェック |

## Vibe Coding との関係

Vibe Codingは探索に強い。
Spec-Driven Developmentは収束に強い。

| 状況 | 向く進め方 |
|---|---|
| アイデア探索、プロトタイプ、捨てる前提の実験 | Vibe Coding |
| 複雑な機能、チーム開発、保守前提、回帰が高コスト | Spec-Driven Development |

実務では、vibe session でアイデアを膨らませた後に `Generate spec` のように仕様化し、以後は spec を基準に実装する流れが扱いやすい。

## 関連

- `docs/context-design.md`
- `docs/agent-skills.md`
- `skills/spec-workflow/SKILL.md`
- `skills/context-audit/SKILL.md`
