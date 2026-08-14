---
name: cluster-verify
description: Kubernetes 上で動くサービスの変更を、PR を出す前にクラスタの実文脈（環境変数・Secret・クラスタ内 DNS・依存サービス）で検証する。mirrord でローカルプロセスをクラスタに接続し、失敗したら直して再実行するループを回す。「クラスタで検証して」「mirrord で確認」「PR 前に実環境で試して」等で起動。
---

# cluster-verify — PR を出す前にクラスタの実文脈で検証する

ローカルのモックとユニットテストだけで確かめた変更は、クラスタに載った瞬間に壊れる。
環境変数、Secret、クラスタ内 DNS、依存サービスの実挙動がローカルには無いため。
このスキルは mirrord でローカルプロセスをクラスタの文脈に接続し、検証してから PR を出すループを定義する。

正典は agentic-coding リポの `skills/cluster-verify/` で版管理し、`~/.claude/skills/cluster-verify/` にはそのコピーを置く。

## 絶対の前提（この 3 つを破らない）

1. **本番クラスタを対象にしない。** 対象は開発用クラスタかローカルクラスタに限る
2. **設定ファイルの `kube_context` でクラスタを固定する。** mirrord は kubectl の現在のコンテキストで動くため、固定しないと業務クラスタに向く事故が起きる
3. **steal モードは必ず `http_filter` と併用する。** フィルタなしの steal は対象 Pod への全リクエストを奪う

作業を終えたら mirrord のプロセスを必ず止める。
起動したまま引き継がない。

## 手順

### 1. 対象と接続先を確認する

```bash
kubectl config current-context     # 想定したクラスタか
kubectl -n <namespace> get deploy  # 対象ワークロードがあるか
```

現在のコンテキストが本番、または想定と違う場合はここで止めて人間に確認する。

### 2. mirror モードで文脈が見えるか確かめる

最初は必ず読み取りのみの mirror モードで始める。
トラフィックはコピーされるだけで、クラスタ側の処理には影響しない。

```bash
MIRRORD_CONFIG_FILE=.mirrord/<service>.json mirrord exec -- <ローカル起動コマンド>
```

確認すること。

- ConfigMap 由来の環境変数が取得できているか
- Secret（環境変数とマウントファイルの両方）が取得できているか
- クラスタ内 DNS で依存サービスに到達できるか

ここで取得できない値があれば、設定の `feature.env` と `feature.fs` を見直す。

### 3. フィルタ付き steal で実際の疎通を確かめる

自分のセッションだけを横取りする設定に切り替える。

```json
{
  "kube_context": "<開発クラスタのコンテキスト名>",
  "target": { "path": "deployment/<service>", "namespace": "<namespace>" },
  "feature": {
    "env": true,
    "fs": "read",
    "network": {
      "incoming": {
        "mode": "steal",
        "http_filter": {
          "header_filter": "baggage:.*session={{ get_env(name='USER', default='local') }}.*"
        }
      },
      "outgoing": true,
      "dns": true
    }
  }
}
```

検証リクエストにヘッダを付ける。

```bash
curl -H "baggage: session=$USER" <エンドポイント>
```

ヘッダのないリクエストはクラスタ側の Pod が処理し続ける。
これで共有クラスタでも他人の作業を壊さない。

### 4. 失敗したら直して再実行する

終了条件はテストスクリプトの終了コードにする。
「動いているように見える」で止めない。

```bash
./scripts/verify.sh || { echo "失敗。原因を読んで最小の修正を入れて再実行"; }
```

再実行のたびに mirrord のプロセスを起動し直す。

### 5. 片付けてから PR を出す

```bash
pkill -f "mirrord exec"   # または該当プロセスを停止
```

## 設定の要点

| 項目 | 指針 |
|---|---|
| `feature.env.exclude` | 本番相当の Secret を手元に降ろさない。降ろす必要のない値は除外する。**組織導入時の必須検討項目** |
| `feature.fs.mode` | ソースコードはローカル、設定ファイルはリモート、と正規表現で振り分ける（`local` / `read` / `write` / `localwithoverrides`） |
| `feature.network.outgoing.filter.local` | localhost 系を入れておかないと、ローカルの依存サービスへの通信までクラスタ経由になる |
| `agent.ttl` | agent Job の残存秒数。連続実行するなら伸ばすと起動が速くなる |
| ポート衝突 | ローカルの待ち受けポートが埋まっていたら `port_mapping` で `[[local, remote]]` と分ける |

## 落とし穴

- **設定ファイルが CLI フラグを上書きする。** `"incoming": "mirror"` を書いた設定で `--steal` を渡しても mirror のまま。モードごとに設定ファイルを分ける
- **存在しない設定キーは検証で落ちる。** エラーが有効キー一覧を出すのでそこを見る
- **ターゲットの種類で必要なものが変わる。** Pod / Deployment / Rollout は OSS で扱えるが、StatefulSet と Service は Operator（有償）が要る
- **フィルタ付き steal 自体は OSS で使える。** Operator が必要になるのは同一 Pod への同時セッション

## リポジトリ側に用意しておくもの

エージェントが毎回同じ判断をできるよう、リポジトリに置いておく。

```
.mirrord/<service>.json    # サービスごとの設定。フィルタ入り
AGENTS.md                  # 下記のガードレールを明文化
scripts/verify.sh          # 終了コードで合否が決まる検証スクリプト
```

`AGENTS.md` に書く内容の型。

```markdown
## クラスタ検証のルール

- 変更は PR を出す前に mirrord でクラスタ文脈で検証する。モックとユニットテストだけで済ませない
- `kubectl port-forward` を mirrord の代用にしない
- 本番クラスタを対象にしない
- 用意された `.mirrord/*.json` を必ず使う（フィルタが入っている）
- 共有環境のデータベースを直接変更しない
- 作業を終えたら mirrord のプロセスを止める

| サービス | 設定 | 検証コマンド |
|---|---|---|
| <service> | `.mirrord/<service>.json` | `./scripts/verify.sh` |
```

## 参考

- 検証済みの最小構成 — `labs/inner-loop-mirrord/`（mirror / steal / フィルタ付き steal を実測）
- mirrord 公式のエージェント向けガイド — https://metalbear.com/mirrord/docs/guides/ai-guides/running-ai-agents-with-mirrord
- 公式サンプルリポジトリ（AGENTS.md と .mirrord/ の実例） — https://github.com/metalbear-co/playground
