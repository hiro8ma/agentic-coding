# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## コマンド

### Go

```bash
go build ./...              # ビルド
go test ./...               # 全テスト
go test -run TestName ./pkg # 単一テスト
go test -race ./...         # レース検出
golangci-lint run           # リント
```

### Rust

```bash
cargo build                 # ビルド
cargo build --release       # リリースビルド
cargo test                  # 全テスト
cargo test test_name        # 単一テスト
cargo clippy                # リント
cargo fmt                   # フォーマット
```

### TypeScript

```bash
tsc                         # コンパイル
tsc --noEmit                # 型チェックのみ
npm test                    # テスト
npm run lint                # リント (ESLint)
npm run format              # フォーマット (Prettier)
```

## 開発ガイド

詳細は `.claude/` を参照。

### 共通（言語非依存）

| カテゴリ | 内容 |
|---------|------|
| [architecture/](.claude/architecture/) | ヘキサゴナル/クリーン、DDD、イベント駆動（CQRS、Saga）、モノレポ、API設計 |

### Go

| カテゴリ | 内容 |
|---------|------|
| [architecture/](.claude/go/architecture/) | プロジェクトレイアウト（cmd, internal, pkg等） |
| [guidelines/](.claude/go/guidelines/) | インターフェース、並行処理、エラー処理、panic/exit、enum、atomic、globals、init、field-tags、設計原則、パッケージ設計、Protocol Buffers、ログ |
| [performance/](.claude/go/performance/) | 最適化（strconv、容量ヒント、文字列連結等） |
| [style/](.claude/go/style/) | 命名規則、変数宣言、構造体、フォーマット、リテラル、ドキュメンテーション、インポート、文字列処理 |
| [patterns/](.claude/go/patterns/) | テスト、Functional Options、時間処理、リポジトリ層、モック |
| [linting/](.claude/go/linting/) | golangci-lint設定 |
| [commands/](.claude/go/commands/) | ビルド、テストコマンド |

### Rust

| カテゴリ | 内容 |
|---------|------|
| [guidelines/](.claude/rust/guidelines/) | 所有権・借用、エラー処理、unsafe、並行処理 |
| [style/](.claude/rust/style/) | フォーマット、命名規則、アイテム、式、文、型 |
| [api/](.claude/rust/api/) | API命名、相互運用性、ドキュメント、予測可能性、柔軟性、型安全性、信頼性、デバッグ可能性、将来対応、マクロ |
| [patterns/](.claude/rust/patterns/) | Builder、Newtype、Typestate、イテレータ |
| [linting/](.claude/rust/linting/) | Clippy/rustfmt設定 |
| [cargo/](.claude/rust/cargo/) | Cargo.toml規約 |
| [commands/](.claude/rust/commands/) | ビルド、テストコマンド |

### TypeScript

| カテゴリ | 内容 |
|---------|------|
| [style/](.claude/typescript/style/) | 命名規則、フォーマット |
| [guidelines/](.claude/typescript/guidelines/) | 変数、関数、クラス、型システム、制御フロー、型定義ファイル、禁止事項 |
| [linting/](.claude/typescript/linting/) | ESLint/Prettier設定 |
| [commands/](.claude/typescript/commands/) | ビルド、テストコマンド |
