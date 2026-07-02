# Rust でのスペック駆動実装

スペック駆動開発の実装フェーズを Rust プロジェクトで進めるときの規約。
ワークフロー全体は `docs/spec-driven-development.md`、仕様の作り方は `skills/spec-workflow/SKILL.md` を参照。

## 実装順序

design.md の実装順序は、依存の下流から次のレイヤー順で書く。

1. ドメイン型（`src/domain/` — struct、enum、newtype。この段階で所有権の設計を決める）
2. エラー型（`src/error.rs` — thiserror によるドメインエラー定義）
3. ユーティリティ（バリデーション、変換）
4. データレイヤー（`src/storage/` — 永続化、外部 I/O）
5. サービスレイヤー（`src/service/`）
6. インターフェースレイヤー（`src/cli/` — clap、または `src/api/`）

型とエラーを最初に固めるのが Rust では特に効く。
上位から書くと、後からの所有権・ライフタイム変更が全レイヤーに波及する。

## 基盤構築フェーズの標準タスク

- [ ] `cargo init` とモジュール構造
- [ ] Cargo.toml（依存関係、features、profile）
- [ ] rustfmt / clippy 設定（`rustfmt.toml`, lint レベル）
- [ ] .gitignore

## 検証コマンド

tasklist.md の各フェーズ末尾に、完了条件として検証コマンドを書く。

```bash
cargo check            # 型エラーゼロ
cargo clippy -- -D warnings   # lint エラーゼロ
cargo test             # テスト green
cargo run -- --help    # エントリポイントの動作確認
```

## レビュー単位の目安

- ドメイン型 + エラー型が `cargo check` を通った時点で 1 回
- データレイヤー完了時（テスト込み）で 1 回
- コマンド 1 つが end-to-end で動いた時点で 1 回

コーディング規約は `guidelines/`（ownership / error / concurrency / unsafe）を参照。
