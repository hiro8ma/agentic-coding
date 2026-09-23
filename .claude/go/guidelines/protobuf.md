# Protocol Buffers

API の契約として proto を書くときの規約。
Go に限らず、gRPC / ConnectRPC / gRPC-Gateway のどれで公開する場合も同じ。

## ファイルの分け方

リソースの定義（message）とサービスの定義（service と Request / Response）を別のファイルに分ける。

```
proto/library/v1/
├── resources.proto   # Book、Publisher などのリソース
└── service.proto     # LibraryService と Request / Response
```

## 命名

- パッケージ名に区切り文字を使わない（`library.v1`。`library_service.v1` にしない）
- repeated のフィールド名は複数形にする（`repeated Book books`）
- enum の値には型名を前に付け、ゼロ値を `_UNSPECIFIED` にする

```protobuf
enum BookStatus {
  BOOK_STATUS_UNSPECIFIED = 0;
  BOOK_STATUS_PUBLISHED = 1;
  BOOK_STATUS_ARCHIVED = 2;
}
```

## 書き方

- コメントはフィールドの上に書く（行末に書かない）
- Request と Response は、RPC ごとに対で並べる
- message のネストは 2 階層までにする。深くなるなら別の message に切り出す

## 互換性

- フィールドは末尾に足す。既存のフィールドの番号は変えない
- 消したフィールドは、番号と名前の両方を `reserved` にし、message の先頭に置く。再利用しない

```protobuf
message Book {
  reserved 3;
  reserved "subtitle";

  string name = 1;
  string title = 2;
}
```

- フィールド名の変更は、バイナリの通信では互換だが、JSON（gRPC-Gateway、ConnectRPC の JSON、保存した JSON）では壊れる。使う形式を確かめてから判断する
- 互換を壊す変更は、メジャーバージョンを上げる。バージョンはパッケージ名と URL の両方に入れる（`library.v2`、`/v2/...`）
- 互換の検査は `buf breaking` で行う

## 値の定義

- ドメインで使う離散的な値（状態、種別）は、共有の proto に enum として 1 か所で定義する。サービスごとに同じ enum を定義し直さない
- 数値や文字列のマジックナンバーで受け渡さない
- 時刻、期間、空の値などは well-known types（`google.protobuf.Timestamp`、`Duration`、`Empty`、`FieldMask`）を使う
