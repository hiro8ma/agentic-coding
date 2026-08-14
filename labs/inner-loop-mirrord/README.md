# inner-loop-mirrord

ローカルプロセスを Kubernetes クラスタの文脈で動かす mirrord を、最小構成で検証するラボ。
「AI エージェントに開発環境を与える」文脈で、インナーループ（PR を作るまで）のフィードバックを数十秒に縮めるための道具立てを実測する。

検証日 2026-08-14 / mirrord 3.247.0 / minikube k8s v1.34.0 / macOS Apple Silicon

## 何を確かめるラボか

ローカルで動かしたプロセスに、クラスタの環境変数、Secret、マウント済みファイル、クラスタ内 DNS を「そのまま」見せられるかを比較で確かめる。
さらに steal モードで、クラスタ内から来たリクエストをローカルプロセスが処理できるかまで見る。

## 安全上の前提

mirrord は kubectl の**現在のコンテキスト**に対して動く。
steal モードは対象 Pod の実トラフィックを横取りするため、共有クラスタや本番に向けて実行してはいけない。

このラボでは設定ファイルの `kube_context` でローカルクラスタに固定している。
実行前に必ず確認する。

```bash
kubectl config current-context   # agentlab であること
```

## セットアップ

```bash
# 1. ローカルクラスタ
minikube start -p agentlab --cpus=4 --memory=6g --driver=docker

# 2. mirrord CLI
brew install metalbear-co/mirrord/mirrord

# 3. イメージをビルドしてクラスタへ渡す
cd app
docker build --load -t labdemo:local .
minikube -p agentlab image load labdemo:local
cd ..

# 4. デプロイ
kubectl --context=agentlab apply -f k8s/manifests.yaml
kubectl --context=agentlab -n agentlab wait --for=condition=available --timeout=180s \
  deploy/upstream deploy/demo-app
```

`docker build` に `--load` が要る点に注意する。
buildx のビルダーを使うと、付けない限りイメージがビルドキャッシュに残ったまま docker のイメージストアに現れない。

## 検証 1 — クラスタ内の基準を取る

```bash
kubectl --context=agentlab -n agentlab run c --rm -i --restart=Never \
  --image=curlimages/curl:8.11.1 -- -s http://demo-app.agentlab.svc.cluster.local
```

Pod 名、ConfigMap の値、Secret（環境変数とマウントファイルの両方）、upstream への到達が JSON で返る。

## 検証 2 — mirrord なしのローカル実行

```bash
cd app && go build -o /tmp/labdemo . && cd ..
PORT=18080 /tmp/labdemo &
curl -s localhost:18080
```

ConfigMap も Secret も取得できず、クラスタ内 DNS の名前解決も失敗する。
これがインナーループが遅くなる原因そのもの。

## 検証 3 — mirror モード

```bash
MIRRORD_CONFIG_FILE=.mirrord/mirrord.json PORT=8080 mirrord exec -- /tmp/labdemo &
curl -s localhost:8080
```

プロセスはローカル（`hostname` は自分のマシン）のまま、ConfigMap、Secret、マウントファイル、`KUBERNETES_SERVICE_HOST`、クラスタ内 DNS 経由の upstream 応答がすべて取得できる。

| 実行方法 | ConfigMap | Secret(env) | Secret(file) | クラスタ内 DNS |
|---|---|---|---|---|
| 素のローカル実行 | 取得できず | 取得できず | 取得できず | timeout |
| mirrord (mirror) | 取得できた | 取得できた | 取得できた | 到達できた |

## 検証 4 — steal モード

```bash
MIRRORD_CONFIG_FILE=.mirrord/steal.json PORT=18080 mirrord exec -- /tmp/labdemo &

kubectl --context=agentlab -n agentlab run c --rm -i --restart=Never \
  --image=curlimages/curl:8.11.1 -- -s http://demo-app.agentlab.svc.cluster.local
```

クラスタ内から Service を叩いた応答の `hostname` がローカルマシン名になり、Pod ではなく手元のプロセスが処理したことが分かる。

## 検証 5 — フィルタ付き steal（共有クラスタでも使える形）

フィルタなしの steal は対象 Pod への全リクエストを奪うため、共有クラスタでは使えない。
`http_filter` で自分のセッションのヘッダを持つリクエストだけを横取りすれば、他人のトラフィックは Pod が処理し続ける。

```bash
MIRRORD_CONFIG_FILE=.mirrord/steal-filtered.json PORT=18080 mirrord exec -- /tmp/labdemo &

# A. ヘッダなし（他人のリクエスト相当）→ Pod が応答
kubectl --context=agentlab -n agentlab run f1 --rm -i --restart=Never \
  --image=curlimages/curl:8.11.1 -- -s http://demo-app.agentlab.svc.cluster.local

# B. 自分のセッションヘッダあり → ローカルが応答
kubectl --context=agentlab -n agentlab run f2 --rm -i --restart=Never \
  --image=curlimages/curl:8.11.1 -- -s \
  -H "baggage: mirrord-session=lab-session" http://demo-app.agentlab.svc.cluster.local
```

実測結果。

| リクエスト | 応答した主体 |
|---|---|
| ヘッダなし | Pod（`demo-app-...` / pid 1） |
| `baggage: mirrord-session=lab-session` あり | ローカル（`mac.lan` / pid 46846） |

セッションキーは `{{ get_env(name='USER') }}` のテンプレートで各自の値に展開できるため、設定ファイルはチームで共有したまま分離キーだけを個人ごとに変えられる。
フィルタ付き steal 自体は OSS 版で使える。
有償の Operator が必要になるのは、同一 Pod に対して複数人が**同時に**セッションを張る場合。

## 躓いた点

1. **設定ファイルが CLI フラグを上書きする。** `"incoming": "mirror"` を書いた設定で `--steal` を渡しても mirror のままになる。モードごとに設定ファイルを分けるのが確実
2. **存在しない設定キーは config 検証で落ちる。** `agent.network_interface` は 3.247.0 に無い。エラーが有効キー一覧を表示するのでそこを見る
3. **ローカルポートの衝突。** 待ち受けポートが他プロセス（SSH トンネル等）に取られていると起動できない。`port_mapping` でローカルとリモートを分ける
4. **`port_mapping` の書式。** オブジェクトではなく `[[local, remote]]` の配列

## 片付け

```bash
kubectl --context=agentlab delete -f k8s/manifests.yaml
minikube stop -p agentlab      # 残す場合
minikube delete -p agentlab    # 消す場合
kubectl config use-context <元のコンテキスト>
```

## 構成

```
app/main.go          # 単一バイナリ。MODE=upstream で上流サービスとして起動する
app/Dockerfile
k8s/manifests.yaml   # namespace / ConfigMap / Secret / upstream / demo-app
.mirrord/mirrord.json  # mirror モード
.mirrord/steal.json    # steal モード + port_mapping
```

## セキュリティ上の検討事項

インナーループの改善は「本番相当の Secret を開発者マシンに降ろす」ことと表裏一体になる。
組織で導入するなら `feature.env.exclude` で降ろさない環境変数を決めるのが必須の設計項目。

```json
"env": {
  "include": "DATABASE_USER;PUBLIC_ENV",
  "exclude": "DATABASE_PASSWORD;SECRET_ENV"
}
```

`feature.fs.mode` も同様に、ソースコードはローカル、設定ファイルはリモート、と正規表現で振り分けられる。

## 次の段階

アウターループ側（PR ごとにワークロードを複製してプレビュー URL を払い出す）は Signadot が担当する領域。
無料の Starter プラン（クラスタ 1 つ、Sandbox 作成 50 回/月）があり、ローカルクラスタでも試せる。
Operator の導入にはダッシュボードでのクラスタトークン発行が要る（トークンは初回のみ表示）。

```bash
helm repo add signadot https://charts.signadot.com
helm install signadot-operator signadot/operator \
  --set controlPlane.clusterToken='<cluster-token>'
```

サービスメッシュ未導入の環境では、Signadot 独自の DevMesh を前提とした構成を選ぶ。

## エージェントに渡す形にする

MetalBear が Agent Skills 形式のスキル集（`metalbear-co/skills`、9 種）と、エージェント前提のサンプルリポジトリ（`metalbear-co/playground`）を公開している。
playground には `AGENTS.md` と `.mirrord/` が最初から入っており、「エージェントがコードを書く前にクラスタ文脈で検証してから PR を出す」ループの実例になっている。

```bash
/plugin marketplace add metalbear-co/skills
/plugin install mirrord@mirrord-skills
```

公式が明示している安全ガードは 3 つ。
本番クラスタを対象にしない。
用意された設定ファイル（フィルタ入り）を必ず使う。
エージェントごとにセッション識別子を分ける。

playground の `AGENTS.md` は、これを禁止事項の列挙ではなく**行為の指示**として書いている点が参考になる。

- `kubectl port-forward` を mirrord の代用にしない
- 作業を終えたら mirrord のプロセスを止める。起動したまま引き継がない
- 共有環境のデータベースを直接変更しない。修正が要るならサービスコード側に入れる

このラボで実測した内容を再利用可能な形にしたものが `skills/cluster-verify/`。
リポジトリに `.mirrord/*.json`（フィルタ入り）と `AGENTS.md` と終了コードで合否が決まる検証スクリプトを置く、という型を定義している。

## 参考

- mirrord — https://mirrord.dev/
- Signadot — https://www.signadot.com/
