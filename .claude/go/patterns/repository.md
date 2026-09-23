# リポジトリ層

[ヘキサゴナルアーキテクチャ](../../architecture/hexagonal.md) の Repository 実装を、Go で書くときの型。

## 引数

ID が 1 つならそのまま渡し、2 つ以上なら Params の構造体にまとめる。

```go
// ID が 1 つ
func (r *BookRepository) GetBook(ctx context.Context, id string) (*model.Book, error)

// 2 つ以上
type ListBooksParams struct {
    PublisherID string
    Status      model.BookStatus
    PageSize    int
    PageToken   string
}

func (r *BookRepository) ListBooks(ctx context.Context, p *ListBooksParams) ([]*model.Book, string, error)
```

引数の並び順の取り違えを防ぎ、条件を足してもシグネチャが変わらない。

## クエリの分割

クエリの組み立て、パラメータ、DTO の変換を分ける。

| 置き場 | 中身 |
|------|------|
| `listBooksSQL()` | SQL の文字列を返す |
| `listBooksParams(p)` | プレースホルダに渡す値を返す |
| `book_dto.go` | DB の行とドメインのモデルの変換 |

SQL だけを読みたいとき、値の組み立てだけを直したいときに、見る場所が決まる。

## DB 操作の動詞

関数名の動詞を次にそろえ、名前と処理を一致させる。

| 動詞 | 処理 |
|------|------|
| `Create` | 新しく作る。既にあればエラー |
| `Get` | 1 件を取る。なければエラー |
| `List` | 条件に合うものを取る。0 件でもエラーにしない |
| `Update` | 既存を更新する。なければエラー |
| `Delete` | 消す |

`Update` の中で、なければ作る（Upsert）処理をしない。両方が要るなら、呼び出す側が `Get` の結果で `Create` と `Update` を呼び分ける。
