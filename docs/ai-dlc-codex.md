---
title: "AI-DLCをCodexで使う際に、教材の旧版と現行版を分ける"
date: "2026-10-11"
tags: [ai-dlc, codex, specification, workflow]
---

# AI-DLCをCodexで使う際に、教材の旧版と現行版を分ける

教材のcore-workflow.mdを手動でコピーする方法は、公式リポジトリの旧版v1.0.1に対応する
2026年10月11日に確認したmainはcore/とharness/の構成で、旧aidlc-rules/は存在しない
版を分けずにmainを取得すると、教材のコピー元が見つからない

## 旧版の手動ルール配置

旧版を教材として再現する場合は、取得元をv1.0.1へ固定する
既存プロジェクトやAGENTS.mdを上書きせず、ルールだけを配置する
このリポジトリでは実際の取得や導入は行っていない

```text
.aidlc/aidlc-rules/
├── aws-aidlc-rules/core-workflow.md
└── aws-aidlc-rule-details/
    ├── common/
    ├── inception/
    ├── construction/
    ├── extensions/
    └── operations/
```

旧core-workflow.mdは詳細ルールの探索先を規定し、この.aidlc配下の構成を最優先候補にしている
ファイル自身の位置を基準に相対参照する仕組みと決めつけず、指定された階層を保つ
条件付きで読み込む[AGENTSの追記例](../examples/aidlc/AGENTS-v1.fragment.md)は、既存ルールを保つための教材用テンプレートである
AGENTS.mdへ記載したことだけでは、実際に選択されて詳細ルールが読まれた証明にはならない

| 旧版の工程 | 役割と制約 |
|---|---|
| Inception | 目的、要件、前提、未確定事項を整理する |
| Construction | 設計、実装、Build and Testを扱う。手順を生成したことと実行成功を分ける |
| Operations | 将来の運用段階として置かれ、v1.0.1の文書では未実装 |

教材のToDoアプリは、構成、package.json、実装、テスト、既存仕様を確認する例である
その分析結果を、別のプロジェクトでも確認済みの事実として利用しない

## 現行版のCodex対応

確認したmainはInitialization、Ideation、Inception、Construction、Operationの5段階を定義している
Operationにはデプロイや監視などの工程があり、現在も未実装と一括して説明しない
Build and Testでは、実際のコマンド実行と証拠の記録を求める

現行のCodexガイドは、$aidlc、プロジェクト設定、Hooks、Skillsを使う
旧版のcore-workflow.mdへの参照だけを追加して、現行版を導入したとは扱わない
導入時は[確認した版のCodexガイド](https://github.com/awslabs/aidlc-workflows/blob/f995370730eb98fd7338fe9a42738ee3c87c4225/docs/guide/harnesses/codex-cli.md)を読み、変更する設定とHooksを確認する
今回は既存のAGENTS.md、設定、Hooksを変更していない

## Spec Kitとの組み合わせ

Spec Kitは仕様、計画、タスクを工程ごとの成果物にする
AI-DLCは開発ライフサイクルの進め方をまとめるが、現行の利用方法をAGENTS.mdの参照だけとは説明しない
双方を使う場合は、今回使う進め方と仕様の正本を先に決める

Spec Kitの既定の機能仕様は、リポジトリ直下のspecs/<feature>/spec.mdに置かれる
教材の.specify/specs/を、すべてのプロジェクトの既定配置としてコピーしない
specs/、.steering/、AI-DLCの成果物へ、同じ要求を独立した正本として複製しない
既存の要求や設計を参照して分析し、追加と修正が必要な内容だけを正本へ戻す

## 検証範囲

旧v1.0.1と、mainのコミットf995370730eb98fd7338fe9a42738ee3c87c4225を読み比べた
そのコミットの日時は2026年10月10日22:45:13 UTCである
実導入、条件付きルールの発動、詳細ルールの読み取り、ビルド、テスト、運用工程の実行は未確認である

## 出典

- ユーザー提供教材「AI-DLCをCodexに導入する」
- [旧版のルール](https://github.com/awslabs/aidlc-workflows/tree/v1.0.1/aidlc-rules)
- [旧版README](https://github.com/awslabs/aidlc-workflows/blob/v1.0.1/README.md)
- [確認したmain](https://github.com/awslabs/aidlc-workflows/tree/f995370730eb98fd7338fe9a42738ee3c87c4225)
- [現行の工程](https://github.com/awslabs/aidlc-workflows/blob/f995370730eb98fd7338fe9a42738ee3c87c4225/docs/guide/04-phases-and-stages.md)
- [Codex CLIガイド](https://github.com/awslabs/aidlc-workflows/blob/f995370730eb98fd7338fe9a42738ee3c87c4225/docs/guide/harnesses/codex-cli.md)
