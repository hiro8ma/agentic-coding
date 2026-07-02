---
name: spec-workflow
description: 実装前に docs/ と .steering/ の仕様駆動開発ドキュメントを作成・更新する。
---

次の対象について、スペック駆動開発ワークフローを実行する: $ARGUMENTS

可搬 Skill の正典は `skills/spec-workflow/SKILL.md`。

次の範囲で進める。

1. 依頼を初回セットアップ / 機能仕様 / バグ修正仕様 / 仕様更新に分類する
2. 既存の `docs/` と `.steering/` があれば確認する
3. `.steering/YYYYMMDD-kebab-title/` 配下に `requirements.md`、`design.md`、`tasklist.md` を作成・更新する
4. `skills/spec-workflow/assets/` のテンプレートを使う
5. ユーザーが明示的に実装まで求めていない限り、実装前に承認待ちで止める
6. 実装まで求められた場合は `tasklist.md` に沿って進め、進捗を更新し、プロジェクトの検証コマンドを実行する
