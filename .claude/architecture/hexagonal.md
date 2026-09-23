# ヘキサゴナルアーキテクチャ

クリーンアーキテクチャ/ヘキサゴナルアーキテクチャに基づく設計。

## レイヤー構成

```
Domain（内側） ← Usecase ← Adapter（外側）
```

依存性は**外から内**へ向かう。

### Domain層（ビジネスロジック）

ビジネスルールとドメイン知識を表現。

```
domain/
├── model/            # エンティティ、値オブジェクト、コレクション
├── repository/       # リポジトリインターフェース
├── externalservice/  # 外部サービスインターフェース
├── service/          # ドメインサービスインターフェース
└── factory/          # ファクトリ
```

#### Model

- ドメインオブジェクト（エンティティ、値オブジェクト）の定義
- オブジェクトの振る舞いを定義
- データモデル固有の`createdAt`等はUIで不要なら含めない

#### Factory

- エンティティ生成はファクトリ経由のみ（生成条件の強制）
- 複雑な生成ロジックにはバリデーションを含める
- 別集約からの再生成は`Recreate`メソッドとして定義
  - 命名規則: `RecreateEntityName`

#### Repository/ExternalService

- インターフェースのみ定義
- 実装はAdapter層

#### Service

- ドメインサービスのインターフェース
- **極力使わない**（エンティティに振る舞いを持たせる）

### Usecase層（アプリケーションサービス）

Domain層の操作を組み合わせてアプリケーションを実現。

```
usecase/
├── interface        # インターフェース定義
├── impl             # 実装
├── dto              # DTOとバリデーション
└── mock/            # モック（テスト用）
```

#### メソッドの形

メソッド名は、対応する RPC の名前と同じにする。
引数と戻り値は次の形に固定し、中身が空でもリクエストとレスポンスの構造体を定義する。

```go
func (u *Book) GetBook(ctx context.Context, req *GetBookRequest) (*GetBookResponse, error)
```

形がそろうと、RPC からユースケースを機械的にたどれる。後からフィールドを足しても、シグネチャが変わらない。

#### 責務

- `repository`、`externalservice`、`domain service`の呼び出し・調整
- `factory`を用いたドメインオブジェクト生成
- DBトランザクション処理
- Adapter層との変換処理（DTO）

#### アンチパターン

**ドメインモデル貧血症**

```
// Bad - usecase層でビジネスロジック
user = userFactory.NewUser(id, firstName, lastName)
fullname = firstName + " " + lastName  // ロジックがusecase層にある

// Good - domain層に振る舞いを持たせる
user = userFactory.NewUser(id, firstName, lastName)
fullname = user.FullName()  // ロジックがdomain層にある
```

**その他の禁止事項**

- 特定クライアントへの依存（APIとして公開を意識）
- ユースケースからユースケースの呼び出し（全体像把握が困難）

### Adapter層（プレゼンテーション・インフラ）

外部との入出力を担当。

```
adapter/
├── infrastructure/
│   ├── repository/       # リポジトリ実装 + DTO
│   ├── externalservice/  # 外部サービス実装
│   └── service/          # ドメインサービス実装
└── handler/
    ├── rest/             # REST API
    ├── grpc/             # gRPC
    └── pubsub/           # メッセージング
```

#### Repository実装規約

- 集約の範囲を表現することに特化
- カプセル化した永続化処理のみ実装
- 集約単位でCRUD処理
- 集約の一部変更メソッドは定義しない
- 複数責務のメソッド禁止（例: `saveUsers`, `upsertUsers`）
- トランザクション内呼び出しは命名で区別（例: `UpdateUserInTx`）

#### DTO変換

```
repository(impl) → dto → DB
repository(impl) ← dto ← DB
```

エンティティをファットにしないためDTOで変換処理を分離。

## データフロー

```
request → adapter → dto → usecase → domain
response ← adapter ← dto ← usecase ← domain
```

## 共通規約

### 前提

- **責務の明確化**: 疎結合・高凝集
- **テスト容易性**
- **拡張性**
- **問題特定の容易化**
- **依存関係を明確にする**

### レイヤー間のデータ受け渡し

- 内側のレイヤーに構造体を配置
- レイヤーを超えた構造体の引き渡しはしない
- 一貫性を優先（コンストラクタは多くなるが許容）
