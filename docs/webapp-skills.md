---
title: "web-artifacts-builder / webapp-testing — 構築と検証でループを閉じるスキル設計"
date: "2026-07-31"
tags: [agent-skills, web-artifacts-builder, webapp-testing, playwright, e2e, shadcn-ui, single-html, loop-engineering]
---

# web-artifacts-builder / webapp-testing

anthropics/skills の Web アプリ構築スキルと E2E テストスキルを設計例として読む。
ドキュメント処理 4 スキルの分析は `document-skills.md`、Skills の仕組み全般は `agent-skills.md` を参照。

## web-artifacts-builder — 配布形態から逆算した技術選定

「タスク管理アプリを作って」という指示から、React + TypeScript + Tailwind CSS + shadcn/ui のアプリを構築し、最終的に単一 HTML（bundle.html）へバンドルする。

```
Initialize（init-artifact.sh で環境構築）
→ Develop（コンポーネント実装）
→ Bundle（bundle-artifact.sh で単一 HTML 化）
→ Share（ファイル 1 つで共有）
```

設計の要点は 3 つ。

- **環境構築とバンドルはスクリプト、実装は LLM** という分業。Vite + React + TS のセットアップという決定論的で失敗しやすい工程を init-artifact.sh に固定し、LLM は創造的な実装だけを担う
- **配布形態（単一 HTML）から技術選定が逆算**されている。受け取った人が環境構築なしにブラウザで開けることを最優先し、そのための制約（全インライン化）をスキルが引き受ける
- **利用者はスタックを意識しない**。React も shadcn/ui も内部実装であり、指示は要件だけでよい

### AI スロップを避けるデザイン規範

SKILL.md には AI 生成物にありがちなパターン（中央寄せの多用、紫グラデーション、均一な角丸、テンプレート的 UI）を避ける指示が含まれる。
「ありがちな失敗を規範で先回りして潰す」型で、`design-skills.md` で整理したデザインスキル群と同じ発想。

### 適用限界の明示

ルーティング、API 連携、データベース接続、本番前提の構成が必要なら、このスキルでなくゼロから設計する。
スキル自身が守備範囲外を宣言している点も設計として重要で、モックアップと共有用途に絞ることで品質を保っている。

## webapp-testing — 判断の分岐まで手順化する

Python 版 Playwright で E2E テストを自動化する。設計の中心は 2 つ。

### 意思決定ツリーの内蔵

| テスト対象 | アプローチ |
|---|---|
| 静的 HTML ファイル | 直接読み込んでセレクタを特定 |
| サーバー未起動の動的アプリ | with_server.py でサーバーの起動・停止を自動管理 |
| サーバー起動済みの動的アプリ | 偵察して読み込み完了を待ち、テストだけ実行 |

利用者がアプリの種類を指定する必要はなく、ファイル構成とプロセス状態から経路を自動選択する。
手順だけでなく**状況判断の分岐そのものを SKILL.md に書く**例で、単線的なチェックリストより一段上の手続き知識のエンコードになっている。

### 探索から実行するパターン

1. ページの読み込み完了を待つ
2. 画面上の要素を調べてテスト対象を特定する
3. 特定した要素に操作を実行する

要素の特定は HTML 構造依存のセレクタでなく、役割や表示内容（「ボタン」「テキスト入力欄」）で行う。
Playwright の getByRole 系ロケータの思想で、構造変更に強く保守コストが下がる。
ブラウザ自動化エージェントの「偵察してから操作する」原則と同じ型でもある。

### with_server.py の関心分離

サーバーの起動・停止というテストの前提管理をヘルパーに寄せ、テストコードにはテストロジックだけを書かせる。
fixture の思想をスキルのスクリプトとして提供している。

## 2 スキルの連携 — ループが閉じる

「アプリを作って、テストも書いて」で builder → testing が連続実行される。
この組み合わせの本質は、**E2E テストが機械検証可能なフィードバック信号になり、エージェントの修正ループが閉じる**こと。

- builder 単体では「動くか」の確認が人間の目視に依存する
- testing が入ると「タスク追加が動く / 空文字で追加されない」が pass / fail の信号になり、エージェントが自律的に修正と再検証を反復できる

`loop-engineering.md` / `loop-design-checklist.md` で整理した「ループには検証器が必要」の実例であり、pptx スキルの生成後 QA（`document-skills.md`）と同じ生成・検証分離の構造でもある。

## 実務での継続活用

- **回帰テスト** — 一度書いた E2E テストは機能追加のたびに既存機能の破壊を検知する資産になる
- **スクリーンショット比較** — Playwright の PNG 保存で前回とのレイアウト差分を機械検出できる
- **CI 統合** — 生成物は通常の Python スクリプトなので GitHub Actions に組み込める。push ごとの自動実行で「エージェントが書いたコードをエージェントのテストが守る」構成になる
- **既存アプリへの適用** — URL 指定なら「サーバー起動済み」経路でテストだけ実行できる

## 出典・参考

- https://github.com/anthropics/skills/tree/main/skills/web-artifacts-builder
- https://github.com/anthropics/skills/tree/main/skills/webapp-testing
- https://ui.shadcn.com/
- https://playwright.dev/docs/intro
