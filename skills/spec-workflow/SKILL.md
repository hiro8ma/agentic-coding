---
name: spec-workflow
description: AI協働開発の前に docs/ と .steering/ を使って What / How / tasks を明文化するスペック駆動開発ワークフローを実行する。「スペック駆動」「仕様駆動」「spec workflow」「PRDを作る」「requirements/design/tasklistを作る」等のキーワードで起動。
---

# スペック駆動開発スキル

AIに実装を依頼する前に、What、How、実装タスクを明文化する。
仕様を開発中の記憶装置として使い、実装の一貫性とレビュー可能性を高める。

## 手順

### 1. モードを決める

ユーザーの依頼を見て、次のどれかに分類する。

| モード | 使う場面 |
|---|---|
| 初回セットアップ | 新規プロジェクトで `docs/` と `.steering/` を作る |
| 機能仕様 | 新機能・機能追加 |
| バグ修正仕様 | バグ修正・回帰防止 |
| 仕様更新 | 既存仕様とコードのずれを直す |

### 2. 永続ドキュメントを確認する

存在する場合は読む。
存在しない場合は、必要に応じて `assets/persistent-docs-template.md` を使って作成案を出す。

- `docs/product-requirements.md`
- `docs/functional-design.md`
- `docs/architecture.md`
- `docs/repository-structure.md`
- `docs/development-guidelines.md`
- `docs/glossary.md`

### 3. ステアリングディレクトリを作る

作業単位で次の形式にする。

```text
.steering/YYYYMMDD-kebab-title/
```

作成するファイル。

- `requirements.md`
- `design.md`
- `tasklist.md`

### 4. requirements.md を作る

`assets/steering-requirements-template.md` を使う。

機能仕様では、ユーザーストーリー、受け入れ条件、制約、非対象を明記する。
バグ修正仕様では、再現手順、現在の挙動、期待する挙動、変えてはいけない挙動、回帰テスト条件を明記する。

受け入れ条件は、可能なら次の形にする。

```text
WHEN <condition/event>
THE SYSTEM SHALL <expected behavior>
```

### 5. design.md を作る

`assets/steering-design-template.md` を使う。

設計には、実装アプローチ、影響範囲、変更するファイル候補、データ構造変更、テスト方針、リスクを含める。

### 6. tasklist.md を作る

`assets/steering-tasklist-template.md` を使う。

タスクは、依存関係が分かる粒度に分ける。
各タスクには完了条件と検証コマンドを書く。

### 7. 実装前の確認を入れる

次の観点で整合性を確認する。

- requirements の受け入れ条件がテスト可能か
- design が existing architecture と矛盾していないか
- tasklist が requirements と design を漏れなくカバーしているか
- `docs/` の永続ドキュメント更新が必要か

### 8. 実装する場合

ユーザーが実装まで求めている場合だけ、`tasklist.md` に沿って進める。
実装後は、必要なテスト・lint・型チェックを実行し、`tasklist.md` の進捗を更新する。

## 出力形式

実装前に止める場合は、次を出す。

```markdown
## Created / Updated

- ...

## Approval Needed

- requirements
- design
- tasklist

## Next Action

- ...
```

実装まで行う場合は、最後に変更ファイル、検証結果、残リスクを報告する。
