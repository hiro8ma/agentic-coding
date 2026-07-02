# TypeScript でのスペック駆動実装

スペック駆動開発の実装フェーズを TypeScript プロジェクトで進めるときの規約。
ワークフロー全体は `docs/spec-driven-development.md`、仕様の作り方は `skills/spec-workflow/SKILL.md` を参照。

## 実装順序

design.md の実装順序は、依存の下流から次のレイヤー順で書く。

1. 型定義・定数（`src/types/`, `src/constants/`）
2. ユーティリティ（`src/utils/` — バリデーション、フォーマット）
3. データレイヤー（`src/data/` — 永続化、外部 I/O）
4. サービスレイヤー（`src/services/` — ビジネスロジック）
5. インターフェースレイヤー（`src/cli/` または `src/api/`）

各レイヤーは下位レイヤーだけに依存する。
上位から書き始めると、型が定まらないまま `any` が増える。

## 基盤構築フェーズの標準タスク

tasklist.md の最初のフェーズには次を含める。

- [ ] プロジェクト構造作成（`src/` 配下のレイヤーディレクトリ）
- [ ] package.json（依存関係、build / dev / lint / test スクリプト、bin 設定）
- [ ] tsconfig.json（必要なら `tsconfig.build.json` を分離）
- [ ] ESLint / Prettier 設定
- [ ] .gitignore

## 検証コマンド

tasklist.md の各フェーズ末尾に、完了条件として検証コマンドを書く。

```bash
npm run build          # 型エラーゼロ
npm run lint           # lint エラーゼロ
npm test               # テスト green
node dist/cli/index.js --help   # エントリポイントの動作確認
```

Bun プロジェクトでは `bun run build` / `bun test` に読み替える。

## レビュー単位の目安

- 基盤構築フェーズの完了時（build が通った時点）で 1 回
- 各レイヤーの完了時に 1 回
- CLI / API コマンド 1 つの動作確認ができた時点で 1 回

コーディング規約は `guidelines/` を参照。
