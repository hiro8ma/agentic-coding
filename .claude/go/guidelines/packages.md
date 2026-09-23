# パッケージ設計

## パッケージ命名

汎用的な名前を避ける。

```go
// Bad
package util
package common
package helper
package base
package misc

// Good - 目的を示す名前
package httputil
package stringconv
package validator
```

小文字のみ。アンダースコアなし。

```go
// Good
package tabwriter
package httputil

// Bad
package tabWriter
package http_util
```

標準ライブラリと同じ名前のパッケージは作らない。import のたびに別名が要り、どちらを指しているか読み違える。

```go
// Bad
package log
package errors

// Good - 接頭辞で区別する
package liblog
package apperrors
```

サブパッケージは、親の文脈が分かる名前にする。`internal/payment/client` の中身が汎用の `client` なのか、決済の `client` なのかを名前で区別できるようにする。

## 名前の重複を避ける

```go
// Bad - パッケージ名と関数名の重複
package yamlconfig
func ParseYAMLConfig() {}  // yamlconfig.ParseYAMLConfig()

// Good
package yamlconfig
func Parse() {}  // yamlconfig.Parse()
```

## パッケージサイズ

結合の判断:
- 2つのパッケージを常に一緒にインポートする → 結合を検討
- 実装が密結合 → パッケージプライベートアクセスを活用
- 概念的に異なる機能 → 分離

## ファイル構成

「1型1ファイル」規則はない。

```go
// 大きなパッケージの例
// package http
client.go      // Client型と関連メソッド
server.go      // Server型と関連メソッド
cookie.go      // Cookie処理
header.go      // Headerの操作
```

## グローバル状態の回避

ライブラリはグローバル状態に依存しない。

```go
// Bad
package db

var defaultDB *Database

func Query(q string) (*Result, error) {
    return defaultDB.Query(q)
}

// Good - 依存性注入
package db

type Database struct {
    conn *sql.DB
}

func (d *Database) Query(q string) (*Result, error) {
    return d.conn.Query(q)
}
```

## 内部パッケージ

外部に公開すべきでない実装を隠す。

```go
myproject/
├── pkg/
│   └── public/      // 公開API
└── internal/
    └── private/     // 内部実装のみ
```

## cmd パターン

実行可能ファイルは`cmd/`ディレクトリに。

```go
myproject/
├── cmd/
│   ├── myapp/
│   │   └── main.go
│   └── mytool/
│       └── main.go
├── pkg/             // ライブラリコード
└── internal/        // 内部パッケージ
```

## 循環依存の回避

```go
// Bad
package a
import "b"

package b
import "a"

// Good - インターフェースで分離
package a
type Doer interface { Do() }

package b
type Impl struct{}
func (Impl) Do() {}
```

## デフォルトの提供

簡略化APIを提供する場合:

1. クライアントが独立インスタンスを作成可能
2. 公開APIはインスタンスメソッドのラッパー
3. グローバルAPIはバイナリのみ使用

```go
package logger

// グローバルロガー（mainのみ使用）
var defaultLogger = New(os.Stderr)

func Info(msg string) {
    defaultLogger.Info(msg)
}

// インスタンス生成（ライブラリはこちらを使用）
func New(w io.Writer) *Logger {
    return &Logger{w: w}
}
```
