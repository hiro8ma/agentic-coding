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

## 次の段階

アウターループ側（PR ごとにワークロードを複製してプレビュー URL を払い出す）は Signadot が担当する領域で、コントロールプレーンのアカウントと Operator の導入が必要になる。
このラボはインナーループのみを対象にしている。

## 参考

- mirrord — https://mirrord.dev/
- Signadot — https://www.signadot.com/
