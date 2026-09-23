# インポート

## グループ順序

```go
import (
    // 1. 標準ライブラリ
    "context"
    "fmt"
    "io"

    // 2. サードパーティ
    "github.com/pkg/errors"
    "go.uber.org/zap"

    // 3. 自プロジェクト
    "github.com/myorg/myproject/pkg/user"
)
```

空行でグループを分離。

## リネーム

原則として避ける。衝突時のみ使用。

```go
// 衝突時 - ローカルをリネーム
import (
    "encoding/json"

    myjson "myproject/json"
)
```

## ブランクインポート（`import _`）

mainパッケージまたはテストのみ。

```go
// main.go - OK
package main

import (
    _ "github.com/lib/pq"
)

// library.go - NG
package mylib

import (
    _ "github.com/lib/pq"  // ライブラリでは禁止
)
```

## ドットインポート（`import .`）

禁止。機能の出所が不明確になる。

```go
// Bad
import . "fmt"

func main() {
    Println("Hello")  // fmtからか不明
}

// Good
import "fmt"

func main() {
    fmt.Println("Hello")
}
```

## 未使用インポートの禁止

```go
// Bad
import (
    "fmt"
    "os"  // 未使用
)

// Good
import (
    "fmt"
)
```

`goimports`で自動削除。

## 循環インポートの回避

```
// Bad
package a imports package b
package b imports package a

// Good - インターフェースで分離
package a imports package types
package b imports package types
```

## インポートエイリアス

パッケージ名がインポートパスの最後の要素と異なる場合のみ。

```go
import (
    "net/http"

    client "example.com/client-go"  // パッケージ名がclient-go
)
```

別名は小文字だけにする（`userv1`。`userV1` や `user_v1` にしない）。

## ローカルインポートの優先

```go
// goimportsの設定
// -local フラグで自プロジェクトを指定

import (
    "fmt"

    "github.com/external/pkg"

    "github.com/myorg/myproject/internal"  // ローカルは最後
)
```
