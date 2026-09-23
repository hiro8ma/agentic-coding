# 列挙型（Enum）

## ゼロ値を避けて1から開始

列挙型は1から開始する。ゼロ値がデフォルトの有効な状態でない限り。

```go
// Bad - ゼロ値がUnknownではなくRed
type Color int

const (
    Red Color = iota  // 0
    Green             // 1
    Blue              // 2
)

var c Color  // ゼロ値は0 = Red（意図しない可能性）

// Good - 1から開始
type Color int

const (
    Red Color = iota + 1  // 1
    Green                 // 2
    Blue                  // 3
)

var c Color  // ゼロ値は0 = 無効/未設定
```

## ゼロ値を有効にする場合

ゼロ値がデフォルトとして適切な場合は0から開始。

```go
// OK - ゼロ値がデフォルトとして適切
type LogLevel int

const (
    Info LogLevel = iota  // 0 - デフォルトでInfo
    Warn                  // 1
    Error                 // 2
)
```

## Unknown/Invalid を明示

不明/無効状態を明示的に定義。

```go
type Status int

const (
    StatusUnknown Status = iota  // 0 - 明示的に不明
    StatusActive                 // 1
    StatusInactive               // 2
)

func (s Status) IsValid() bool {
    return s >= StatusActive && s <= StatusInactive
}
```

## 文字列表現

`String()`メソッドでデバッグしやすく。

```go
//go:generate stringer -type=Status

type Status int

const (
    StatusUnknown Status = iota
    StatusActive
    StatusInactive
)

// または手動で実装
func (s Status) String() string {
    switch s {
    case StatusActive:
        return "active"
    case StatusInactive:
        return "inactive"
    default:
        return "unknown"
    }
}
```

## 定数に型名を前置する

Go の定数にも型名を前に付ける。proto の enum の値（`STATUS_ACTIVE`）とも対応が取りやすくなる。

```go
type Status int

// Bad
const (
    Active Status = iota + 1
    Inactive
)

// Good
const (
    StatusActive Status = iota + 1
    StatusInactive
)
```
