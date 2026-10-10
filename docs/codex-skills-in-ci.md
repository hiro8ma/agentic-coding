---
title: "共有したSkillをCodex Actionで使い、生成と投稿を分ける"
date: "2026-10-11"
tags: [codex, github-actions, skills, plugins, review]
---

# 共有したSkillをCodex Actionで使い、生成と投稿を分ける

同じレビューの判断基準を手元とCIで使うなら、Skillをファイルとして共有し、CIにも入力として渡す
Pluginは配布を担当し、GitHub Actionsは起動と投稿を担当する
Codex ActionはCLIを導入して`codex exec`を実行し、レビューや提案を生成する
Pluginを手元に入れたことだけで、GitHubのRunnerに同じSkillがあるとは扱わない

## CIへ手順を渡す

CIでは、確認済みのSkillをリポジトリへ配置するか、確認済みのPluginの版を取得する
ユーザー環境のSkill、接続、認証をRunnerが引き継ぐ前提にしない
Skillを明示するプロンプトには、対象の差分、参照先、変更の制約、出力の条件を残す

レビューの実行設定と判断基準は、信頼するbase側から読み込む
PR側のコードはレビュー対象のデータとして読む
PRから追加されたAGENTS.md、Skill、スクリプトを、そのまま実行時の指示や処理へ昇格させない

## Codex Actionの入力

2026年10月11日に確認した`openai/codex-action`のv1ソースは、次の入力を受け付ける

| 入力 | 役割 |
|---|---|
| `openai-api-key` | GitHub SecretsからAPIキーを渡す |
| `prompt` / `prompt-file` | インライン指示か、指示ファイルのどちらか一方を渡す |
| `permission-profile` | `:read-only`、`:workspace`、または定義済みの名前付き権限プロファイルを選ぶ |
| `sandbox` | 従来の権限指定。permission-profileとは併用しない |
| `safety-strategy` | Runner上の実行権限を制御する。既定はdrop-sudo |
| `output-file` | 最終出力をファイルへ保存する |
| `codex-version` | 実行するCLIの版を指定する |
| `allow-users` / `allow-bots` | Actionを起動できる利用者やBotを制御する |

教材の`permission-profile: read-only`は、組み込みプロファイルを指すなら`permission-profile: ':read-only'`へ直す
`read-only`だけの名前を使うなら、その名前のプロファイルが別途定義されている必要がある
現在の公式解説はsandboxを中心に説明しているため、利用するActionの版のaction.ymlも確認する
権限プロファイルを使う場合はCLI 0.138.0以降が必要で、safety-strategyのread-onlyとは併用しない

ファイル権限、Runnerの権限、GitHub Tokenの権限は別の境界である
読み取り専用の設定だけでAPIキーが保護されたとは判断しない
生成ジョブは必要な読み取り権限に絞り、投稿やPR作成の権限を別ジョブへ置く

## APIキーを用意する

Actionの例は、APIキーを`OPENAI_API_KEY`としてGitHub Secretsへ登録し、`secrets.OPENAI_API_KEY`から渡す
登録先はリポジトリのSettingsからSecrets and variables、Actions、Repository secretsへ進む
ChatGPTの契約やクレジットと、API認証での利用条件や請求を分けて確認する
料金、予算、必要なAPI権限を確認してからジョブを有効にする
教材の画面上の権限ラベルを固定した設定値として扱わず、利用するAPIに必要な範囲を確認する

キーをYAMLやSkillへ埋め込まず、ログやモデルの出力にも残さない
forkのPRではSecretsが渡らないことがあるため、Secretを渡す目的でpull_request_targetへ置き換えてPRコードを実行しない
このリポジトリのサンプルはSecretsを作成せず、課金されるモデル呼び出しも行っていない

## PRのレビューと投稿

PRの差分はbaseとheadのコミットを指定して取得する
ベースブランチ名だけを書いた依頼や、fetch-depthだけの指定で対象が確定したとは判断しない
生成ジョブでは、変更対象、発生条件、影響、根拠、修正方針をMarkdownへまとめる
PRのタイトルと概要も差分との一致と初見の読みやすさを確認する

最終出力は`final-message`から後続ジョブへ渡せる
投稿は生成とは別ジョブにし、Markdownを環境変数やファイル経由で渡す
モデル出力をGitHub Actionsのscriptへ直接埋め込んで、コードとして評価しない
レビュー生成とGitHubへのコメント投稿が成功したことも別々に確認する

PRコメントはIssueコメントのAPIで作成できる
必要な権限は使用するAPIとActionの仕様で確認し、issues:writeとpull-requests:writeを常に両方付けるとは決めない
自動投稿を有効にする前に、投稿範囲と実行者をチームで合意する

`@codex review`はGitHub連携の入口、ローカルの`/review`はCLIの入口である
自作のGitHub Actionsと同じ認証や実行設定を使う機能ではない

## Issueから提案書のPRを作る

Issueのラベルと、ラベルを付けた信頼できる実行者を条件にする
Issueの作者のauthor_associationは、ラベルを付けた実行者の認可を代替しない
Issue本文は環境変数からファイルへ保存し、シェルのrunへ式で直接埋め込まない
信頼された利用者がラベルを付けても、本文そのものは外部入力として扱う

Codexに渡す指示には、出力する文書、参照先、変更してよい範囲、完了条件を指定する
APIキーだけを渡しても、Codex Actionは生成タスクを実行しない
教材のIssue例にはpromptとprompt-fileがないため、そのままでは提案書を生成する処理が不足する

提案書を生成するジョブと、ファイルをコミットしてドラフトPRにするジョブを分ける
後者は生成物の対象パスだけを受け取り、変更するファイルを限定する
Codex Action自身がIssueのラベル監視やPR作成をすべて担当するものではない

## サンプルと検証範囲

Pluginの互換形式とCIのサンプルは[examples/codex-ci](../examples/codex-ci/)にある
GitHub Actionsが発見する`.github/workflows/`へは配置していない
導入時に確認済みのActionとCLIの版、利用者、投稿先、APIの予算を決め、対象リポジトリへ必要なファイルを移す

ローカルの構文検査と設定の照合だけでは、Runner上の権限が機能した証明にはならない
導入先では、許可するPRと拒否するfork、ラベルや実行者が違うIssue、API失敗時の投稿の有無を確かめる
制限を外した対照と比べ、意図した境界で実行が止まるかを確認する
今回、実CI、モデル生成、コメント投稿、PR作成は未実行である

## 出典

- ユーザー提供教材「Pluginを作成・公開する」「GitHub ActionsにSkillsを組み込む」
- [Codex GitHub Action](https://learn.chatgpt.com/docs/github-action)
- [Codex Actionのv1定義](https://github.com/openai/codex-action/blob/v1/action.yml)
- [Codex Action](https://github.com/openai/codex-action)
- [actions/checkout](https://github.com/actions/checkout)
- [create-or-update-comment](https://github.com/peter-evans/create-or-update-comment)
- [create-pull-request](https://github.com/peter-evans/create-pull-request)
