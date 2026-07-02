# Go でのスペック駆動実装

スペック駆動開発の実装フェーズを Go プロジェクトで進めるときの規約。
ワークフロー全体は `docs/spec-driven-development.md`、仕様の作り方は `skills/spec-workflow/SKILL.md` を参照。

## 実装順序

design.md の実装順序は、依存の下流から次のレイヤー順で書く。

1. ドメイン型・定数（`internal/entity/` または `pkg/<domain>/` — struct、enum 相当の定数）
2. ユーティリティ（バリデーション、変換）
3. リポジトリレイヤー（`internal/repository/` — DB、ファイル、外部 API）
4. サービス / ユースケースレイヤー（`internal/service/` または `internal/usecase/`）
5. インターフェースレイヤー（`cmd/` の CLI、または handler / RPC adapter）

依存は内側（entity）に向ける。
interface はまず利用側パッケージに定義し、実装側に置かない（`guidelines/interfaces.md` 参照）。

## 基盤構築フェーズの標準タスク

- [ ] `go mod init` とディレクトリ構造（`cmd/`, `internal/`）
- [ ] Makefile または task 定義（build / test / lint）
- [ ] golangci-lint 設定（`.golangci.yml`）
- [ ] .gitignore

## 検証コマンド

tasklist.md の各フェーズ末尾に、完了条件として検証コマンドを書く。

```bash
go build ./...         # コンパイルエラーゼロ
go vet ./...           # vet 警告ゼロ
golangci-lint run      # lint エラーゼロ
go test ./...          # テスト green
go run ./cmd/<app> --help   # エントリポイントの動作確認
```

## レビュー単位の目安

- `go build ./...` が通る最小骨格ができた時点で 1 回
- リポジトリレイヤー完了時（テスト込み）で 1 回
- ユースケース 1 つが end-to-end で動いた時点で 1 回

コーディング規約は `guidelines/`、パッケージ設計は `packages.md` を参照。
