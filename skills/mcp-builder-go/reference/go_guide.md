# 公式 Go SDK リファレンス（modelcontextprotocol/go-sdk v1 系）

シグネチャは pkg.go.dev / 公式 Quick Start からの転記。実装前に https://pkg.go.dev/github.com/modelcontextprotocol/go-sdk/mcp で最終確認する。

## 最小サーバー（公式 Quick Start）

```go
package main

import (
	"context"
	"log"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type Input struct {
	Name string `json:"name" jsonschema:"the name of the person to greet"`
}

type Output struct {
	Greeting string `json:"greeting" jsonschema:"the greeting to tell to the user"`
}

func SayHi(ctx context.Context, req *mcp.CallToolRequest, input Input) (
	*mcp.CallToolResult,
	Output,
	error,
) {
	return nil, Output{Greeting: "Hi " + input.Name}, nil
}

func main() {
	server := mcp.NewServer(&mcp.Implementation{Name: "greeter", Version: "v1.0.0"}, nil)
	mcp.AddTool(server, &mcp.Tool{Name: "greet", Description: "say hi"}, SayHi)
	if err := server.Run(context.Background(), &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
```

## 主要シグネチャ

```go
func NewServer(impl *Implementation, options *ServerOptions) *Server

func AddTool[In, Out any](s *Server, t *Tool, h ToolHandlerFor[In, Out])

type ToolHandlerFor[In, Out any] func(ctx context.Context, req *CallToolRequest, args In) (*CallToolResult, Out, error)
```

- `AddTool` はトップレベルのジェネリック関数。入力スキーマ未指定なら `In` 型から JSON Schema を自動導出
- `json` タグ = フィールド名、`jsonschema` タグ = 説明文
- 正常時は `return nil, out, nil`（第 1 戻り値の CallToolResult はメタ情報が必要なときだけ使う）

## アノテーション

```go
type ToolAnnotations struct {
	Title           string
	ReadOnlyHint    *bool
	DestructiveHint *bool
	IdempotentHint  *bool
	OpenWorldHint   *bool
}
```

`*bool` の三状態。未指定（nil）はクライアント側で安全側（readOnly=false / destructive=true）に解釈される。

```go
func ptr[T any](v T) *T { return &v }

mcp.AddTool(server, &mcp.Tool{
	Name:        "get_current_weather",
	Description: "指定都市の現在の天気を取得する",
	Annotations: &mcp.ToolAnnotations{
		Title:        "現在の天気",
		ReadOnlyHint: ptr(true),
		OpenWorldHint: ptr(true),
	},
}, handler)
```

## トランスポート

```go
// stdio
server.Run(ctx, &mcp.StdioTransport{})

// Streamable HTTP（http.Handler としてマウント）
func NewStreamableHTTPHandler(getServer func(*http.Request) *Server, opts *StreamableHTTPOptions) *StreamableHTTPHandler

handler := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return server }, nil)
http.ListenAndServe(addr, handler)

// SSE（旧クライアント互換のみ）
func NewSSEHandler(getServer func(request *http.Request) *Server, opts *SSEOptions) *SSEHandler
```

## テスト

```go
// プロセス内でクライアント・サーバーを直結（ネットワーク・サブプロセス不要）
func NewInMemoryTransports() (*InMemoryTransport, *InMemoryTransport)
```

- CI はハンドラ直接呼び出し + `httptest`（外部 API のフェイク）と InMemoryTransports の結合テスト
- 手動デバッグは MCP Inspector（stdio / HTTP 両対応）

## バージョンメモ（2026-08 時点）

- v1.0.0 = GA（互換保証開始）。v1.5.0 でクライアント OAuth 安定化。v1.7.0-pre.1 は MCP 仕様 2026-07-28 RC 対応ベータ
- 出典 https://github.com/modelcontextprotocol/go-sdk/releases / https://go.sdk.modelcontextprotocol.io/quick_start/
