# Codexによる生成と外部書き込みの分離

PRの差分を読み取り権限で確認し、投稿を別のジョブへ分けるサンプル
ファイルの配置だけでGitHub Actionsが動き出さないよう、ワークフローを`workflows/`に置く
レビューの対象は公開リポジトリの、信頼された同一リポジトリ内のPRに限定する
Issueから提案書を生成し、別ジョブで文書だけのドラフトPRを作る例も含む
`review-pr-plugin/`はSkill配布の例で、GitHubから取り込む際は中身を独立した配布用リポジトリのルートへ配置する

## 手動で導入する条件

導入先では、API課金と投稿先を含む利用範囲をユーザーが事前に承認する
承認後に次の設定を手動で行う

- このディレクトリを`examples/codex-ci/`へ配置する
- プロンプトを先に既定ブランチへ取り込み、ワークフローのbaseコミットに存在することを確認する
- Repository Secretとして`OPENAI_API_KEY`を登録する
- ワークフローを`.github/workflows/codex-review.yml`へコピーする
- 承認した対象PRへの自動生成と投稿を有効にする

投稿ごとの確認を加える場合は、任意で投稿ジョブにEnvironmentを指定し、必須レビュアーと自己承認の禁止を設定する
Environment名をYAMLに書くだけでは、承認は有効にならない
このサンプルの作成では、Secrets登録 / CIの有効化 / API実行 / コメント投稿 / PR作成は行っていない

## 実行時の責務

| 対象 | 役割と制約 |
| --- | --- |
| 発火条件 | 同一リポジトリのPRで、作成者がOWNER / MEMBER / COLLABORATORに該当する場合だけ生成ジョブへ進む |
| ワークツリー | baseのコミットSHAをcheckoutし、headはfetchしたGitオブジェクトとして読む |
| 設定とプロンプト | baseから読み、PRに追加された設定 / Skill / hooksを実行時設定として採用しない |
| Codex | `contents: read` / `permission-profile: ':read-only'` / `safety-strategy: drop-sudo`で結果を生成する |
| 認証 | APIキーはActionの専用入力だけへ渡し、GitHubの投稿トークンは投稿ジョブに渡す |
| 投稿 | `final-message`を環境変数として受け、事前承認された範囲でPRコメントを作る |

作成者の区分だけで現在の操作権限を保証できないため、Action自身の書き込み権限チェックも使う
`allow-users: '*'`やbotの一括許可は追加しない
forkのPRと`pull_request_target`は対象外
非公開リポジトリでは認証情報を残さないfetchの設計を別途確認する

生成ジョブではcheckoutの認証情報を保存せず、APIキーをジョブ全体の環境変数やプロンプトへ混ぜない
Action内部は`github.token`を操作権限の確認に使うが、Codexのstepへ`GITHUB_TOKEN`を明示的に渡さない
Codexをそのジョブの最後のstepにし、後続処理が同じ実行環境を引き継ぐことを避ける
投稿ジョブはコードをcheckoutせず、生成文をJavaScriptへ直接埋め込まない
生成文の環境変数はデータとして使う

この例は明示したbaseとheadの共通祖先からheadまでをレビューする
生成後にPRのheadが変わった場合やPRが閉じた場合は投稿を省く
レビュー対象のコードやテストは実行しないため、動作確認済みとは扱わない

## 固定したActionと確認範囲

2026-10-11に公式リポジトリのタグから参照先を確認した
Codex Actionの`v1`は注釈付きタグを経てcommitへ解決する

| Action | タグ | 固定したcommit |
| --- | --- | --- |
| openai/codex-action | v1 | `bdf19a4a223ec2549a3e2274a0cf61556bc07675` |
| actions/checkout | v7 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/github-script | v7 | `f28e40c7f34bde8b3046d885e986cb6290c5673b` |
| actions/upload-artifact | v4 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| actions/download-artifact | v5 | `634f93cb2916e3fdff6788551b99b062d0335ce0` |
| peter-evans/create-pull-request | v7 | `22a9089034f40e5a961c8808d113e2c98fb63676` |

固定した[Codex Actionの入力定義](https://github.com/openai/codex-action/blob/bdf19a4a223ec2549a3e2274a0cf61556bc07675/action.yml)には`permission-profile`がある
組み込みのプロファイルは先頭の`:`を含む名前を使い、`sandbox`とは併用しない
[公式解説](https://learn.chatgpt.com/docs/github-action)は`sandbox`を中心に説明しているため、サンプルの入力は固定したソースとも突き合わせた
内部で導入するCodex CLIとResponses API proxyも`codex-version: '0.162.0'`で固定する
固定した版でのCLI実行とAPI呼び出しは未確認

ローカル検証はJSON / YAML / Skillの形式と、発火条件の肯定側 / 否定側を対象にする
発火条件を外した対照ではforkの入力が通ることを確認する
実際のCIでの発火 / 権限拒否 / Secrets隔離 / Environment承認は未確認

## Issueから提案書のPRを作る例

`workflows/codex-proposal.example.yml`は`codex-ready`ラベルの付与を起点にする
ラベルを付けたactorと再実行するactorの現在の権限をAPIで確認し、write / maintain / adminのいずれかが必要
Issue作成者の`author_association`はラベル付与者の権限確認に代用しない

| ジョブ | 生成物と権限 |
| --- | --- |
| generate | 環境変数からIssue本文をJSONへ保存し、読み取りだけで提案書1ファイル分の本文を生成する |
| package | 生成文を評価せず`proposal.md`に保存し、その1ファイルだけをartifactへ渡す |
| create-pr | 事前承認された範囲でartifactの文書だけを保存し、`add-paths`をそのMarkdownへ限定してドラフトPRを作る |

生成ジョブの最後のstepはCodex Actionで、artifact化は別の実行環境で行う
生成したMarkdownは未信頼のデータとして扱い、パッチの適用やシェルでの評価には使わない
提案書にはGoal / Context Pointers / Constraints / Done When / Proposed Change / Open Questionsを記す
実装や既存文書の更新はこの例の対象外で、保存先が存在する場合は停止する

導入時に、`codex-ready`ラベルで提案書の生成と文書PRの作成を自動実行する範囲を承認する
APIキーはレビューの例と同じRepository Secretを使える
Repository Variablesの`CODEX_PR_ASSIGNEE`へ担当者、`CODEX_REVIEW_DEADLINE`へ具体的な日時を設定する
生成ごとの確認を加える場合は、任意で`create-pr`ジョブへ保護されたEnvironmentを指定する
その場合は提案書 / PRタイトル / PR本文を確認してからPR作成を承認する
導入先のActions設定で、GitHub ActionsによるPR作成を明示的に許可する必要がある
ワークフローの有効化は`.github/workflows/codex-proposal.yml`へのコピーで行う

既定の`github.token`で作ったPRは、通常の`pull_request`ワークフローを再発火させない
後続のCIが必要な場合は別途設計し、未実行のChecksを成功として扱わない
この例は新しい提案書を作るだけで、既存の提案書やPR本文の自動更新は行わない
同じrunの再実行は対象外にし、同名ブランチの更新を避ける
失敗時は原因を直してから新しいラベル付与イベントで開始し、既存の提案書PRがある場合は先に人が扱いを判断する
