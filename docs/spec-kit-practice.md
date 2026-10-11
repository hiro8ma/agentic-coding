---
title: "Spec Kitで仕様を具体化し、計画と検証の対応を確認する"
date: "2026-10-11"
tags: [spec-kit, specification, codex, planning, validation]
---

# Spec Kitで仕様を具体化し、計画と検証の対応を確認する

日本語ToDoアプリに「追加、一覧、完了、削除」だけを依頼しても、保存するか、壊れた保存データをどう扱うかは決まらない
仕様で利用者に見える結果を決め、計画で実現方法を選び、タスクと検証へ対応付ける
生成した文書があることだけで、仕様との整合性や実装完了は保証されない

## 現在のCodexでの呼び出し

2026年10月11日に確認したSpec Kitのmainでは、Codex向けの手順は`.agents/skills/`へ生成される
教材の`/speckit.*`は共通説明で使われる表記で、現行のCodexでは次のSkill名を使う

| 工程 | Codexの明示呼び出し | 主な確認 |
|---|---|---|
| 開発方針 | `$speckit-constitution` | 原則と品質基準 |
| 機能仕様 | `$speckit-specify` | 利用者の操作、優先順位、受け入れ条件 |
| 曖昧さの解消 | `$speckit-clarify` | 判断に必要な未決事項。Plan前の任意の確認 |
| 技術計画 | `$speckit-plan` | 技術選定、モデル、実装と検証の方針 |
| タスク分解 | `$speckit-tasks` | 依存関係、ストーリー、対象ファイル、必要なテスト |
| 文書間の照合 | `$speckit-analyze` | Tasks後、Implement前に仕様と計画とタスクを読み取り専用で照合 |
| 実装 | `$speckit-implement` | 確定したタスクを実装して進捗を更新 |
| 実装後の確認 | `$speckit-converge` | 現行READMEが案内する実装後の確認 |

導入例は次のとおりで、このリポジトリでは実行していない

```shell
uv tool install specify-cli
specify init todo-app --integration codex
```

利用する版、既存の設定、生成されたSkillの一覧を確認する
このリポジトリのtool-neutralな[spec-workflow](../skills/spec-workflow/SKILL.md)とは別の仕組みで、Spec Kitの導入を必須にはしない

## SpecifyとClarify

ストーリーは利用者の操作として書き、優先順位と単独で確認できる結果を添える
例えば日本語のタスクを1件登録し、一覧に表示されることをGiven / When / Thenで確認できるようにする
状態、操作、期待する結果を分けると、後でテストが何を証明するかを確認できる

Clarifyでは、保存、完了状態の保持、削除後の復元など、設計や受け入れ条件を変える判断を具体化する
回答はClarificationsだけでなく、関係する要件にも反映する
ログに回答だけを残し、仕様が古いままにならないようにする

教材のレビュー項目にある「更新」は、完了状態や保存内容の更新なのか、タスク本文の編集機能なのかを確認する
最初の要求にない編集機能を、レビューを理由に追加しない

## Planと計画レビュー

Vite、React、CSS、localStorageは教材のアプリで指定した方針で、Spec Kitの必須技術ではない
既存のアプリなら、その依存関係、責務分担、起動方法を先に読む
UIと状態管理を分ける場合も、今回の検証に必要な境界を作り、将来の用途だけを理由に層を増やさない

Planには実現方法、データモデル、調査結果、起動手順を残す
現行テンプレートはresearch.md、data-model.md、quickstart.mdを扱い、contracts/は外部インターフェースがある場合に生成する
Tasksの入力として必須なのはspec.mdとplan.mdで、補助資料は必要なものだけを参照する

教材のPlan後、Tasks前の計画レビューは、手戻りを減らすための追加確認である
公式のanalyzeと同じ工程とは扱わない

| 観点 | 確認する内容 |
|---|---|
| 対象 | 文書のブランチや機能名が実際の作業対象と一致するか |
| 永続化 | 読み取り失敗、JSON破損、必須項目の欠落、型不一致、保存失敗で何を表示し、既存データをどう保つか |
| モデル | 各フィールドが要件か検証に必要か。createdAtやupdatedAtも用途を説明できるか |
| 対応 | 受け入れ条件がモデルや処理、タスク、検証へつながっているか |
| 範囲 | 仕様にない機能や不要な依存関係が増えていないか |

例えば壊れた保存データを自動で空配列に上書きすると、回復できる情報まで失う可能性がある
期待する挙動を仕様に決め、モデルの思いつきで回復方針を実装しない
レビューで決めた内容はspec.md、plan.md、data-model.mdなど関係する文書へ反映する

## Tasksから実装へ

タスクはストーリーに対応付け、対象ファイルと完了条件を記す
典型的な形式は`- [ ] T001 [P] [US1] 説明とパス`で、並列で進められない作業に[P]を付けない
共通準備など、ストーリーのラベルが適用されないタスクもある
テストタスクは要求とリスクに合わせ、Spec Kitがいつも自動生成すると期待しない

仕様、計画、タスクをanalyzeで照合してから実装する
その後、実装したファイルと完了扱いにしたタスク、実行した検証の対応を確認する
未実行の検証があるなら、コードができたことと受け入れ条件を確認できたことを分けて報告する

## 起動して確認する

Viteの起動例はnpm run devだが、実際には対象プロジェクトのpackage.jsonと実行手順に従う
開発サーバーが起動しただけでは、受け入れ条件を満たしたとは判断しない
日本語の登録、一覧、完了切り替え、削除、再読み込み後の保持、入力と保存の異常系を確認する

ブラウザの注釈は修正箇所を伝える補助に使える
コンソールやターミナルのエラーは、再現手順と期待する結果と合わせて原因を調べる材料にする
修正したら同じ再現条件で確認する
教材のViteの版や起動時間、画面、レビュー結果は、今回の実行結果としては扱わない

## このリポジトリへの適用

既存のdocs/と.steering/は維持し、spec-workflowに要求の具体化とTasks前の設計レビューを追加する
Spec Kitを採用済みのリポジトリでは、そのspecs/や.specify/を使い、別の形式へ自動で移行しない
教材末尾の工程表はPlanの行で切れており、欠落した記述を元の教材として復元しない
今回はSpec Kitの導入、ToDoアプリの生成、Viteの起動を行っていない

## 出典

- ユーザー提供教材「Spec Kitによる仕様駆動開発の実践」
- [Spec Kit](https://github.com/github/spec-kit)
- [CodexなどのIntegration](https://github.com/github/spec-kit/blob/main/docs/reference/integrations.md)
- [Installation](https://github.com/github/spec-kit/blob/main/docs/installation.md)
- [Agentic SDD](https://github.com/github/spec-kit/blob/main/docs/reference/agentic-sdd.md)
- [Spec template](https://github.com/github/spec-kit/blob/main/templates/spec-template.md)
- [Clarify](https://github.com/github/spec-kit/blob/main/templates/commands/clarify.md)
- [Plan](https://github.com/github/spec-kit/blob/main/templates/commands/plan.md)
- [Tasks](https://github.com/github/spec-kit/blob/main/templates/commands/tasks.md)
