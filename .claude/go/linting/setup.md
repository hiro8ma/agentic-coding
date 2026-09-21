# リンティング設定

## golangci-lint v2

推奨のリントランナー
staticcheck / modernize / gosec などを 1 回の実行でまとめて動かす

### インストール

golangci-lint は、ビルドに使った Go より新しい `go` 指定のモジュールを読めない
配布バイナリや Homebrew 版が古い Go でビルドされていると、次のエラーで止まる

```
the Go language version (go1.26) used to build golangci-lint is lower than the targeted Go version (1.27.0)
```

手元の Go でビルドし、版をリポジトリで固定する

```makefile
BIN_DIR := $(abspath ./bin)
GOLANGCI_LINT_VERSION := v2.13.2
GOLANGCI_LINT := $(BIN_DIR)/golangci-lint

lint-tools:
	GOBIN=$(BIN_DIR) go install github.com/golangci/golangci-lint/v2/cmd/golangci-lint@$(GOLANGCI_LINT_VERSION)

$(GOLANGCI_LINT):
	@$(MAKE) lint-tools

lint: $(GOLANGCI_LINT)
	$(GOLANGCI_LINT) run ./...

fmt: $(GOLANGCI_LINT)
	$(GOLANGCI_LINT) fmt ./...
```

モジュールのパスは `/v2/` を含む
v1 のパスで `go install` すると v1 が入る

### 実行

```bash
golangci-lint run                          # lint
golangci-lint fmt                          # 整形（formatters 節の設定で動く）
golangci-lint run --fix                    # 自動で直せる指摘を直す
golangci-lint run --new-from-rev=HEAD~1    # 差分だけを見る
golangci-lint config verify                # 設定ファイルを検証する
golangci-lint migrate                      # v1 の設定を v2 に変換する
```

## lint の失敗を握りつぶさない

次の書き方は、道具が入っていても実行に失敗すると「未インストール」と表示して成功扱いになる

```makefile
lint:
	@which staticcheck > /dev/null 2>&1 && staticcheck ./... || echo "staticcheck not installed, skipping"
```

`a && b || c` は `b` が失敗したときも `c` を実行する
Go を上げたときに staticcheck が export data を読めなくなり、lint が何も検査しないまま通り続けた実例がある
道具が無ければ入れる、失敗したら止める、の 2 つだけにする

## 設定ファイル

`.golangci.yml`

```yaml
version: "2"

run:
  timeout: 5m

linters:
  default: standard        # errcheck / govet / ineffassign / staticcheck / unused
  enable:
    - bodyclose
    - errorlint
    - gosec
    - modernize            # slices.Contains / maps.Copy / range over int などへの書き換え
    - noctx
    - usetesting           # テストの context.Background / os.MkdirTemp を t.Context / t.TempDir へ
  settings:
    gosec:
      excludes:
        - G104             # errcheck と重複する
  exclusions:
    generated: strict
    presets:
      - std-error-handling
    rules:
      - path: _test\.go
        linters:
          - gosec

formatters:
  enable:
    - gofumpt
    - goimports
  settings:
    goimports:
      local-prefixes:
        - github.com/yourorg/yourrepo
```

### v1 からの主な変更

| v1 | v2 |
| --- | --- |
| `linters-settings` | `linters.settings` |
| `gosimple` / `stylecheck` | `staticcheck` に統合 |
| linter としての `gofmt` / `goimports` / `gofumpt` | `formatters` 節に移動し、`golangci-lint fmt` で実行 |
| `issues.exclude-use-default` | `linters.exclusions.presets` |
| `disable-all` / `enable-all` | `linters.default`（`none` / `standard` / `all` / `fast`） |
| `--out-format` | `--output.text.path` / `--output.json.path` など |

### 既存コードに入れるとき

1. 設定と Makefile を 1 コミットにする
2. `golangci-lint run --fix` の自動修正を 1 コミットにする。挙動を変えないので、レビューは差分の形だけを見ればよい
3. 残りを手で直す。直さない指摘は、誤検知の理由を設定かコメントに 1 行で残す

`nolint` に理由を書かないと、なぜ外したのか後から分からない

```go
//nolint:gosec // DSN は運用者が .env で与える値で、利用者の入力ではない
```

## CI 統合

```yaml
- uses: golangci/golangci-lint-action@v9   # v7 以降が golangci-lint v2 に対応
  with:
    version: v2.13.2
```

Makefile と CI で版を揃える

## 個別ツール

```bash
go vet ./...                                            # go test でも一部が既定で動く
go fix -diff ./...                                      # Go 1.26 以降の modernizer の差分を確認する
go run golang.org/x/vuln/cmd/govulncheck@latest ./...   # 呼ばれる経路のある脆弱性だけを報告する
```

## エディタ設定

保存時に整形する

```json
{
  "editor.formatOnSave": true,
  "[go]": {
    "editor.defaultFormatter": "golang.go"
  }
}
```
