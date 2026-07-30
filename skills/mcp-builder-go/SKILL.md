---
name: mcp-builder-go
description: Go で MCP サーバーを設計・実装・検証するときのガイド。公式 SDK（modelcontextprotocol/go-sdk）の型付きツール定義、アノテーション、Stdio / Streamable HTTP、テストまでをカバー。「Go で MCP サーバーを作る」「go-sdk で MCP」「MCP サーバーを Go 実装」等で起動。
---

# MCP Builder (Go)

公式 mcp-builder スキル（Python / Node.js）の Go 版。
開発は Research → Implementation → Review → Evaluation の 4 段階で進める。
API の正確なシグネチャは `reference/go_guide.md` を参照。

## SDK の選択（2026 年時点）

- **新規開発は公式 SDK `github.com/modelcontextprotocol/go-sdk` を使う**。v1.0.0 で GA、以後の v1 系は互換保証あり。Google との共同メンテ
- mark3labs/mcp-go（コミュニティ製、約 9k stars）は既存資産がある場合のみ。公式と API 非互換

## Research — ツールを絞り込む

1. 対象 API のドキュメントを読み、エンドポイントを列挙する
2. **最初に公開するツールは 1〜2 個に絞る**。利用状況を見てから増やす
3. 各ツールについて「読み取り専用か / 破壊的か / 冪等か / 外部世界に影響するか」を決める（Implementation でアノテーションになる）

## Implementation — 型付きハンドラで実装する

- ツール名はスネークケース（`get_current_weather`）
- 入出力は Go の構造体で定義し、`json` タグ（フィールド名）と `jsonschema` タグ（説明文）を付ける。JSON Schema は構造体から自動導出される
- ハンドラは `func(ctx, req *mcp.CallToolRequest, in In) (*mcp.CallToolResult, Out, error)` のジェネリック形式。`mcp.AddTool` はトップレベル関数
- **アノテーションを必ず宣言する**。各ヒントは `*bool` の三状態（true / false / 未指定）

| アノテーション | 付ける基準 | クライアント側の使われ方 |
|---|---|---|
| ReadOnlyHint: true | 参照のみ | 自動実行してよい判断材料 |
| DestructiveHint | 上書き・削除を伴うなら true | 実行前のユーザー確認 |
| IdempotentHint | 同じ入力の再実行が安全なら true | リトライ可否 |
| OpenWorldHint | 外部システムに触るなら true | 影響範囲の告知 |

未指定時のクライアント解釈は安全側（readOnly=false / destructive=true）に倒れる。読み取り専用ツールに ReadOnlyHint を付け忘れると、承認が必要なツールとして扱われ UX が落ちる。

- エラーは LLM が読んで次の行動を判断できる文にする（「city not found: Xanadu。都市名を確認してください」）。スタックトレースを返さない
- 外部 API 呼び出しは `http.Client` にタイムアウトを設定し、ベース URL はテストで差し替えられるようフィールド化する

## トランスポートの選択

| 用途 | トランスポート |
|---|---|
| ローカル / エディタ組み込み | `&mcp.StdioTransport{}` |
| リモート / 他プロセスからの接続 | `mcp.NewStreamableHTTPHandler`（`http.Handler` としてマウント） |
| 旧クライアント互換 | SSE（新規では使わない） |

1 バイナリで両対応にする（`-http :PORT` フラグ、未指定なら stdio）。

## Review — チェックリスト

- [ ] ツール名はスネークケースで、名前だけで機能が推測できるか
- [ ] 全ツールにアノテーションが宣言されているか
- [ ] `jsonschema` タグの説明文だけ読んで、モデルが正しい引数を組み立てられるか
- [ ] エラーメッセージは行動可能か（原因 + 次にすべきこと）
- [ ] タイムアウト・リトライの方針があるか

## Evaluation — 機械検証

1. **単体テスト** — ハンドラ関数を直接呼ぶ。外部 API は `httptest` のフェイクサーバーに差し替える
2. **結合テスト** — `mcp.NewInMemoryTransports()` でクライアント・サーバーをプロセス内接続し、MCP 層込みで検証
3. **手動疎通** — MCP Inspector（stdio / HTTP 両対応）でツール一覧・スキーマ・呼び出しを確認
4. 実クライアント（Claude Code の `.mcp.json`、genkit の MCP プラグイン等）から呼んで E2E 確認

## 実装例

このガイドどおりに実装した実例が `../../mcp/weather_go/`（Open-Meteo、API キー不要、stdio + Streamable HTTP 両対応、httptest による検証付き）。
