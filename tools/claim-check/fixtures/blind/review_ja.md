# レビューの報告

## 結論

- 入力の検証は API の層にしか無い <!-- expect: absence -->
- 入力の検証は `api/handlers.go` と `internal/service/` を読んだ範囲では API の層にしか無い
- 失敗したときの再試行は実装されていない <!-- expect: absence -->
- 変更で遅くなる処理は1件 <!-- expect: number -->
- 既存の利用者への影響は無いと判断した <!-- expect: absence -->
- テストは `go test ./...` で全部通った
- レビューの指摘は2点
- 1点目は、ログに個人情報が出る経路がないことの裏付けが無い点 <!-- expect: absence -->
- 2点目は、設定の既定値が本番と開発で違う点
- 本番の設定ファイルは見ていない

## 詳細

- エラーの型は3種類あり、どれも呼び出し元で握りつぶされていない <!-- expect: absence -->
- `retry` という名前の関数はリポジトリに存在しない <!-- expect: absence -->
- `rg -n "func .*[Rr]etry" .` の結果は0件
- タイムアウトの値は 30 秒で、`internal/config/default.go@a1b2c3d:12` に書いてある
- 処理時間の95パーセンタイルは 1.8 秒 <!-- expect: number -->
- 計測は手元で10回だけ行った
- 本番の負荷では測っていない
