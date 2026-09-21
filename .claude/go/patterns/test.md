# テストパターン

## テーブル駆動テスト

繰り返しのテストロジックにはテーブル駆動テストを使用。

```go
func TestAdd(t *testing.T) {
    tests := []struct {
        name string
        a, b int
        want int
    }{
        {"positive", 1, 2, 3},
        {"negative", -1, -2, -3},
        {"zero", 0, 0, 0},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got := Add(tt.a, tt.b)
            if got != tt.want {
                t.Errorf("Add(%d, %d) = %d, want %d", tt.a, tt.b, got, tt.want)
            }
        })
    }
}
```

フィールド名を使用（特に垂直スペースや同じ型が隣接する場合）。

## テスト関数の命名

`Test<対象>_<シナリオ>`形式。

```go
func TestUser_Create(t *testing.T) {}
func TestUser_Create_DuplicateEmail(t *testing.T) {}
func TestUser_Delete(t *testing.T) {}
func TestUser_Delete_NotFound(t *testing.T) {}
```

## 失敗メッセージ

関数名、入力、実際値、期待値を含める。

```go
// Good
t.Errorf("Process(%q) = %v, want %v", input, got, want)

// Bad
t.Error("wrong result")
```

## アサーションライブラリ

標準の方法を使用。DSLを避ける。

```go
// Good
if got != want {
    t.Errorf("Process() = %v, want %v", got, want)
}

// Bad
assert.Equal(t, want, got)
```

## 比較

`cmp.Equal`と`cmp.Diff`を優先。

```go
import "github.com/google/go-cmp/cmp"

if diff := cmp.Diff(want, got); diff != "" {
    t.Errorf("Process() mismatch (-want +got):\n%s", diff)
}
```

## エラーセマンティクス

文字列比較ではなく`errors.Is`を使用。

```go
// Good
if !errors.Is(err, ErrNotFound) {
    t.Errorf("got error %v, want ErrNotFound", err)
}

// Bad
if err.Error() != "not found" {
    t.Error("wrong error")
}
```

## Keep Going

可能な限り`t.Error`を使用（`t.Fatal`ではなく）。

```go
// Good - 複数のプロパティをテスト
if got.Name != want.Name {
    t.Errorf("Name = %q, want %q", got.Name, want.Name)
}
if got.Age != want.Age {
    t.Errorf("Age = %d, want %d", got.Age, want.Age)
}
```

## テーブルテスト内での条件分岐禁止

別のテストに分割する。

```go
// Good - エラーケースは別テストに
func TestProcess_Success(t *testing.T) { ... }
func TestProcess_Error(t *testing.T) { ... }
```

## サブテスト

説明的な名前。スペースと特殊文字を避ける。

```go
func TestUser(t *testing.T) {
    t.Run("Create", func(t *testing.T) { ... })
    t.Run("Delete", func(t *testing.T) { ... })
}
```

サブテストは独立して実行可能に。

## 並列テスト

独立したテストは`t.Parallel()`で並列実行。

```go
for _, tt := range tests {
    tt := tt  // ループ変数をキャプチャ
    t.Run(tt.name, func(t *testing.T) {
        t.Parallel()
        // テストロジック
    })
}
```

## ヘルパー関数

`t.Helper()`でマーク。

```go
func mustCreateTempFile(t *testing.T, content string) string {
    t.Helper()
    f, err := os.CreateTemp("", "test")
    if err != nil {
        t.Fatalf("failed to create temp file: %v", err)
    }
    return f.Name()
}
```

## ゴルーチンでのテスト

テスト関数以外のゴルーチンから`t.Fatal()`を呼ばない。

```go
// Good
func TestConcurrent(t *testing.T) {
    errCh := make(chan error, 1)
    go func() {
        errCh <- process()
    }()
    if err := <-errCh; err != nil {
        t.Fatal(err)  // テストゴルーチンから
    }
}
```

## テストパッケージ

- 同じパッケージ: 未エクスポート識別子にアクセス可能
- `_test`サフィックス: 統合テストや循環依存の場合

```go
// unit_test.go
package mypackage

// integration_test.go
package mypackage_test
```

## セットアップのスコープ

必要なテストでのみセットアップを呼び出す。

```go
// Good
func TestWithData(t *testing.T) {
    data := mustLoadDataset(t)
    // ...
}

func TestWithoutData(t *testing.T) {
    // dataは不要
}
```

## HTTP サーバのテスト

Go 1.27 以降は `httptest.NewTestServer` を使う。
ポートを取らないプロセス内の仮想ネットワークで動き、`testing/synctest` とも組み合わせられる。

```go
srv := httptest.NewTestServer(t, mux)
client := agentv1connect.NewAgentServiceClient(srv.Client(), srv.URL)
```

- 後片付けは `t.Cleanup` に自動で登録されるので、`defer srv.Close()` は要らない
- `srv.Client()` 以外の `http.Client` では届かない。`http.DefaultClient` を使うコードには、クライアントを渡せる口を作る
- `Close` した後の接続は拒否されず、待ち続ける。「接続先が止まっている」状態を作るなら、閉じたループバックのポートを使い、context に期限を付ける

```go
l, err := (&net.ListenConfig{}).Listen(t.Context(), "tcp", "127.0.0.1:0")
if err != nil {
    t.Fatal(err)
}
url := "http://" + l.Addr().String()
_ = l.Close() // 以後この URL への接続は connection refused になる
```

## 実際の API を呼ぶテスト

API キーがあるときだけ走るテストは、Makefile が `.env` を読み込むと `make test` でも走る。
無料枠の上限や一時的な混雑で落ち、コードの不具合と見分けがつかなくなる。
既定のテストではキーを外し、実際に呼ぶテストは別の口にする。

```makefile
test:
	env -u GEMINI_API_KEY -u GOOGLE_API_KEY go test -race -timeout 5m ./...

test-live:
	go test -timeout 10m ./...
```

`-timeout` は既定の 10 分より短くする。
待ち続けるテストがあっても、どのテストで止まったかがすぐ出る。
