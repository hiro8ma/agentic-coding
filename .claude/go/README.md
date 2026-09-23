# Go開発ガイド

Uber Go Style Guide / Google Go Style Guideに基づくGo開発ガイドライン。

## ディレクトリ構成

```
go/
├── architecture/        # アーキテクチャ（Go固有）
│   └── project-layout.md    # プロジェクトレイアウト
│
├── guidelines/          # ガイドライン（コアルール）
│   ├── interface.md         # インターフェース設計
│   ├── interfaces.md        # インターフェース使用規則
│   ├── concurrency.md       # 並行処理
│   ├── error.md             # エラー処理
│   ├── panic-exit.md        # Panic/Exit
│   ├── enum.md              # 列挙型
│   ├── atomic.md            # アトミック操作
│   ├── globals.md           # グローバル変数
│   ├── init.md              # init()関数
│   ├── field-tags.md        # フィールドタグ
│   ├── principles.md        # 設計原則（明確性・単純性・簡潔性）
│   ├── packages.md          # パッケージ設計
│   ├── protobuf.md          # Protocol Buffers
│   └── logging.md           # ログ
│
├── performance/         # パフォーマンス
│   └── optimization.md      # 最適化
│
├── style/              # スタイル（書き方）
│   ├── naming.md            # 命名規則
│   ├── variable.md          # 変数宣言
│   ├── struct.md            # 構造体
│   ├── formatting.md        # フォーマット
│   ├── literals.md          # リテラル・引数
│   ├── documentation.md     # ドキュメンテーション
│   ├── imports.md           # インポート
│   └── strings.md           # 文字列処理
│
├── patterns/           # パターン
│   ├── test.md              # テストパターン
│   ├── functional-options.md # Functional Options
│   ├── time.md              # 時間処理
│   ├── repository.md        # リポジトリ層
│   └── mock.md              # モック
│
├── linting/            # リンティング
│   └── setup.md             # セットアップ
│
└── commands/           # 開発コマンド
    ├── build.md             # ビルド
    └── test.md              # テスト実行
```

## 言語共通アーキテクチャ

[.claude/architecture/](../architecture/) を参照:
- ヘキサゴナル/クリーンアーキテクチャ
- ドメイン駆動設計 (DDD)
- イベント駆動アーキテクチャ
- モノレポ構成

## 参考

- [Uber Go Style Guide](https://github.com/uber-go/guide)
- [Google Go Style Guide](https://google.github.io/styleguide/go/)
- [golang-standards/project-layout](https://github.com/golang-standards/project-layout)
- [Effective Go](https://go.dev/doc/effective_go)
