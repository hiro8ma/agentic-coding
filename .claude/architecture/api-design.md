# API設計ガイド

Google Cloud API Design Guideに基づくリソース指向API設計。

## リソース指向設計

### 基本原則

1. **リソース中心**: 個別に名前付けされた「リソース」（名詞）とその関係・階層で構成
2. **標準メソッド**: Get、List、Create、Update、Deleteで大半の操作をカバー
3. **ステートレス**: 各リクエストは独立

### リソース設計

```
API = リソースの階層構造

例:
/publishers/{publisher_id}
/publishers/{publisher_id}/books/{book_id}
```

**注意**: APIスキーマとDBスキーマを一致させるのはアンチパターン。

## 標準メソッド

### Get（単一リソース取得）

```
GET /v1/publishers/{publisher}/books/{book}
```

| 項目 | 仕様 |
|------|------|
| HTTP | `GET` |
| リクエスト | リソース名（`name`フィールド） |
| レスポンス | リソース自体 |
| エラー | 存在しない場合 `NOT_FOUND` |

### List（コレクション取得）

```
GET /v1/publishers/{publisher}/books
```

| 項目 | 仕様 |
|------|------|
| HTTP | `GET` |
| リクエスト | `parent`、`page_size`、`page_token` |
| レスポンス | リソース配列 + `next_page_token` |

#### ページネーション

```json
// リクエスト
{
  "parent": "publishers/123",
  "page_size": 50,
  "page_token": "..."
}

// レスポンス
{
  "books": [...],
  "next_page_token": "...",
  "total_size": 100  // オプション
}
```

#### フィルタリング・並び替え

- `filter`: 条件指定
- `order_by`: ソート順（デフォルト昇順）

一覧の RPC には、許すソート順とフィルタの組み合わせをコメントで書く。
実装が受け付けない組み合わせを、呼び出す側が試して見つけることにならないようにする。

#### List と ListAll

| RPC | ページング | 使いどころ |
|------|------|------|
| `ListBooks` | あり | 件数が増えうるコレクション |
| `ListAllBooks` | なし（全件） | 件数に上限があり、全件を一度に使うもの |

名前で分けると、呼び出す側がページングの要否をシグネチャから判断できる。

#### 0 件のとき

該当が 0 件でも `NOT_FOUND` を返さず、空のリストを返す。
一覧は「条件に合うものの集合」を返す操作で、空集合は正常な結果。

#### ページングの方式

| 方式 | 使いどころ | 注意 |
|------|------|------|
| カーソル（`page_token`） | 基本はこちら | 途中で行が増減してもずれない |
| オフセット | 総件数やページ番号の表示が必須で、データが小さい管理画面だけ | OFFSET に上限を置く。深いページほど遅くなる |

トークンの組み立てと解釈はリポジトリ層で行い、ユースケースは受け取った値を渡すだけにする。

### Create（リソース作成）

```
POST /v1/publishers/{publisher}/books
```

| 項目 | 仕様 |
|------|------|
| HTTP | `POST` |
| リクエスト | `parent`、リソース本体、`{resource}_id`（オプション） |
| レスポンス | 作成されたリソース |
| エラー | 重複時 `ALREADY_EXISTS` |

#### ユーザー指定ID

管理プレーンAPIでは、リソースIDをユーザーが指定可能にする。

```json
{
  "parent": "publishers/123",
  "book_id": "my-book",
  "book": {
    "title": "My Book"
  }
}
```

### Update（リソース更新）

```
PATCH /v1/publishers/{publisher}/books/{book}
```

| 項目 | 仕様 |
|------|------|
| HTTP | `PATCH`（`PUT`は非推奨） |
| リクエスト | リソース本体、`update_mask` |
| レスポンス | 更新されたリソース |

#### フィールドマスク

更新対象フィールドを明示。

```json
{
  "book": {
    "title": "New Title"
  },
  "update_mask": "title"
}
```

省略時は空でない全フィールドに適用。

#### オプション

- `allow_missing`: true時、存在しなければ作成（Upsert）
- `etag`: 楽観的ロック

### Delete（リソース削除）

```
DELETE /v1/publishers/{publisher}/books/{book}
```

| 項目 | 仕様 |
|------|------|
| HTTP | `DELETE` |
| リクエスト | リソース名（`name`フィールド） |
| レスポンス | 空（`google.protobuf.Empty`） |
| エラー | 存在しない場合 `NOT_FOUND` |

#### オプション

- `force`: true時、子リソースも削除
- `allow_missing`: true時、存在しなくてもエラーにしない
- `etag`: 楽観的ロック

## AIP から外れるとき

AIP（Google の API 設計規約）から外れる設計にするときは、どの規約から外れるかと理由を、proto のコメントか設計文書に書き残す。
理由が残っていないと、後から読んだ人が誤りだと思って直してしまう。

## Upsert を作らない

作成と更新を兼ねる Upsert の RPC は作らない。作成か更新かは呼び出す側が決め、`Create` か `Update` を呼ぶ。
1 つの RPC が 2 つの意味を持つと、権限、監査、エラーの意味（既にある / まだない）が曖昧になる。

## 命名規則

### 基本原則

- **明確**: 意図が伝わる
- **直感的**: 推測しやすい
- **一貫性**: 同じ概念には同じ用語

### ケース規則

| 対象 | ケース | 例 |
|------|--------|-----|
| サービス名 | UpperCamelCase | `LibraryService` |
| メソッド名 | VerbNoun | `GetBook`、`ListBooks` |
| リソース名 | lower_snake_case | `book_id` |
| フィールド名 | lower_snake_case | `display_name` |

### 避けるべき名前

- `Instance`、`Info`などの曖昧な名前
- 過度に一般的な名前
- 前置詞（`With`、`For`）

## エラー処理

### エラーレスポンス構造

```json
{
  "code": 5,
  "message": "Book not found: publishers/123/books/456",
  "details": [
    {
      "@type": "type.googleapis.com/google.rpc.ErrorInfo",
      "reason": "BOOK_NOT_FOUND",
      "domain": "library.example.com",
      "metadata": {
        "book": "publishers/123/books/456"
      }
    }
  ]
}
```

### 標準エラーコード

| コード | 名前 | 用途 |
|--------|------|------|
| 3 | INVALID_ARGUMENT | 不正なリクエスト |
| 5 | NOT_FOUND | リソース未検出 |
| 6 | ALREADY_EXISTS | リソース重複 |
| 7 | PERMISSION_DENIED | 権限不足 |
| 9 | FAILED_PRECONDITION | 前提条件不満 |
| 10 | ABORTED | 競合（etag不一致等） |
| 16 | UNAUTHENTICATED | 認証エラー |

### 権限エラーの優先

リソースの存在確認より権限チェックを先に行う。

```
権限なし → PERMISSION_DENIED（リソース存在有無を漏らさない）
```

### ErrorInfo

```json
{
  "reason": "QUOTA_EXCEEDED",  // UPPER_SNAKE_CASE、63文字以下
  "domain": "library.example.com",
  "metadata": {
    "limit": "100",
    "current": "150"
  }
}
```

## バージョニング

### URL形式

```
/v1/publishers/{publisher}/books/{book}
/v2/publishers/{publisher}/books/{book}
```

### 下位互換性

以下は破壊的変更:

- フィールドの削除・リネーム
- 必須フィールドの追加
- リソース名形式の変更
- HTTPメソッドの変更

## カスタムメソッド

標準メソッドで表現できない操作に使用。

```
POST /v1/publishers/{publisher}/books/{book}:publish
POST /v1/publishers/{publisher}/books:batchCreate
```

`:` で区切り、動詞（lowerCamelCase）を続ける。
