# モック

gomock（`go.uber.org/mock`）を使う場合の書き方。
モックを使う範囲（外部依存の分離に限る、呼び出しの回数や順序はそれ自体が契約のときだけ固定する）は、グローバルのルールに従う。

## 生成

インターフェースの定義のそばに `go:generate` を置き、`mock/` に生成する。

```go
//go:generate mockgen -typed -package=mock -source=./repository.go -destination=./mock/repository.go
```

## 期待値

- 引数は具体的に書く。`gomock.Any()` は、そのテストで関係ない引数だけに使う
- 回数を固定するのは、回数そのものを確かめたいときだけにする（`Times(1)`）
- 順序を固定するのは、順序が契約のときだけにする（`gomock.InOrder`）
- 引数の中身を細かく確かめたいときは、Matcher を書くか `DoAndReturn` で受け取って比べる

```go
repo.EXPECT().
    GetBook(gomock.Any(), "book-1").
    Return(&model.Book{ID: "book-1"}, nil)
```

## テストのアンチパターン

- 固定時間の `time.Sleep` で待つ。条件がそろうまで待つ
- テストの間で状態を共有する。各テストで用意する
- テストデータの ID を固定する。並列に動かすと衝突するので、テストごとに一意の ID を作る
- 補助関数で `t.Helper()` を呼ばない。失敗の行が補助関数の中を指してしまう
- 結果のキャッシュに気づかない。確かめ直すときは `-count=1` を付ける
