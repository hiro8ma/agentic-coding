---
title: "Issue から提案書の PR を作るワークフロー"
date: "2026-10-11"
tags: [github-actions, codex, claude-code, issue, proposal, prompt-injection, spec-kit]
---

# Issue から提案書の PR を作るワークフロー

Issue にラベルを貼ると、エージェントがコードを調べ、提案書だけを PR にする。
コードは変えない。
Codex の教材（出典は明示されていない）で紹介された流れを、このリポジトリの GitHub Actions の安全策（[coding-agent-github-actions.md](coding-agent-github-actions.md)）に合わせて雛形にした。

雛形は次の4つ。

| ファイル | 置き場所 | 役割 |
|---|---|---|
| `templates/github-actions/issue-to-proposal-codex.yml` | `.github/workflows/` | Codex 版のワークフロー |
| `templates/github-actions/issue-to-proposal-claude.yml` | `.github/workflows/` | Claude Code 版のワークフロー |
| `templates/github-actions/agent-prompts/issue-to-proposal.md` | `.github/agent-prompts/` | エージェントが受け取るプロンプト |
| `templates/github-issue/agent-investigation.md` | `.github/ISSUE_TEMPLATE/` | Issue の雛形 |

## 提案書で止める理由

業務の自動化は、読む（Read）、下書きする（Draft）、実行する（Act）の順に任せる範囲を広げる。
このワークフローは Draft で止める。
エージェントが書くのは提案書で、コードの変更や PR のマージは人が決める。

Draft で止めると、エージェントの判断の誤りは提案書の誤りとして PR の上に残る。
人は差分を読む前に、方針と範囲が Issue の意図に合っているかを提案書で確かめられる。
[spec-driven-development.md](spec-driven-development.md) の承認ゲートでいえば、提案書は design の承認に当たる。
実装はこの PR が承認された後に、別の Issue と PR で進める。

## 流れ

1. メンバーが Issue の雛形で Issue を作る。雛形が `agent-proposal` ラベルを付ける
2. ワークフローが Issue のタイトルと本文をファイルに保存する
3. issuelint が Issue の本文を検査する。定義が欠けていればここで止まる
4. エージェントが読み取り専用でコードを調べ、提案書を書く
5. 別のジョブが提案書1ファイルだけをコミットし、ドラフトの PR を作る

Issue の雛形がラベルを付けるので、Issue を作った時点でワークフローが動く。
ラベルを付ける操作を人の承認にしたい場合は、雛形の `labels` を消し、内容を確かめた人がラベルを貼る運用にする。
Warp の software factory の手引きは、`ready-to-spec` で仕様を書かせ、人が承認してから `ready-to-implement` で実装させる2段のラベルを使う。
このワークフローは、その前半の `ready-to-spec` に当たる。

## 3つの安全策

### 読み取り専用で動かす

Codex 版は `permission-profile` に `":read-only"` を渡す。
Codex はファイルを読めるが、書き換えはできない。
提案書は Codex の最終応答で、`output-file` に指定したパスへ Action が書き出す。
権限プロファイルはベータの機能で、Codex CLI 0.138.0以降が要る。
`sandbox` と同時に指定すると Codex の起動前にエラーになり、`safety-strategy: read-only` とも併用できない。
雛形は `safety-strategy` を既定の `drop-sudo` のままにしている。

Claude Code 版は `--allowedTools` で使える道具を絞る。
読む道具（Read / Grep / Glob）と `git log` / `git diff` のほかに許すのは、`Edit(docs/proposals/**)` だけにした。
パスの規則が評価されるのは `Edit(path)` と `Read(path)` で、`Write(path)` は書けても評価されない。
`Write(docs/proposals/*)` のような書き方では書き込み先を絞れないので、雛形は `Edit` の規則で書く。
Claude Code Action は GitHub を操作する基本の道具を常に含める。
これを `--allowedTools` で外せるかは未確認なので、権限の側で書き込みを止める。

どちらの版も、エージェントを動かすジョブの権限は `contents: read` と `issues: read` だけにした。
`actions/checkout` には `persist-credentials: false` を付け、Git の認証情報をワークスペースに残さない。
エージェントが指示を取り違えても、このジョブからは push も PR の作成もできない。
Claude Code Action は既定で、自分で PR を作らずにブランチを push してリンクを返す。
push の権限を渡さないので、この動きも起きない。

### 出力を1ファイルに絞る

提案のジョブは、提案書をアーティファクトとして次のジョブに渡す。
PR を作るジョブは、リポジトリを新しく checkout し直してから提案書を置く。
提案のジョブでほかのファイルが変わっても、PR のジョブには届かない。

さらに `peter-evans/create-pull-request` の `add-paths` に提案書のパスだけを指定し、コミットの対象をそのファイルに限る。
書き込み権限（`contents: write` と `pull-requests: write`）を持つのは、エージェントが動かないこのジョブだけになる。

### Issue の本文を指示ではなくデータとして扱う

Issue の本文は、権限を持つメンバーが書いても信頼しない入力として扱う。
外部から貼り付けた文章に、エージェントへの指示が紛れることがある（プロンプトインジェクション）。
プロンプトには、Issue の本文は調査対象の説明で指示ではないこと、提案書を書く以外の指示には従わないことを書いた。
従わなかった指示は、提案書の「Issue の中で従わなかった指示」に原文で挙げさせる。
レビューする人は、どんな指示が紛れていたかをこの節で知る。

埋め込まれた指示は Issue の本文だけから来るわけではない。
codex-action のセキュリティの文書は、PR 本文の HTML コメント、コミットメッセージ、AGENTS.md、スクリーンショットを経路に挙げている。
claude-code-action は、HTML コメント、見えない文字、画像の代替テキスト、隠れた属性を取り除いてからモデルに渡す。
書き込み権限のない人にも実行を許す `allowed_non_write_users` は、同じ文書で危険と明記されている。
実際の事例には、Aikido が報告した PromptPwnd と、Issue のタイトルに埋め込んだ指示で Claude Code の振り分け bot を動かした Clinejection がある。

シェルへの埋め込みも同じ理由で避ける。
`run:` の中に `${{ github.event.issue.body }}` を直接書くと、GitHub は式を展開してからシェルに渡す。
本文に `"; 任意のコマンド` のような文字列があれば、そのままシェルで実行される（スクリプトインジェクション）。
雛形は本文を `env:` で環境変数に渡し、`printf '%s\n' "$ISSUE_BODY"` でファイルに書く。
環境変数の値はシェルの構文として解釈されない。

実行できる人も絞る。
ジョブの `if` で、ラベル名に加えて Issue の作成者が `OWNER` / `MEMBER` / `COLLABORATOR` のどれかであることを確かめる。
ラベルを付けられるのは、リポジトリの triage 以上の権限を持つ人だけになる。
Codex と Claude Code の Action も、起動した人に書き込み権限があるかを確かめる。

## Issue を定義にする

エージェントに渡す Issue は、依頼文ではなく作業の定義にする。
雛形の見出しは Goal / Context Pointers / Constraints / Done When の4つ。
教材の Issue の項目とは次のように対応する。

| 雛形の見出し | 教材の項目 | 書くこと |
|---|---|---|
| Goal | 目的、やってほしいこと | この調査で得たい結果 |
| Context Pointers | 対象 | 調べ始めるディレクトリやファイル、関連する文書 |
| Constraints | 注意事項 | 守る条件。コード変更は行わないことを最初から書いておく |
| Done When | 成果物、完了条件 | 提案書が `docs/proposals/` にあること、実装変更がないこと |

教材は提案書で見る観点として、責務が大きすぎるクラスや関数、分かりにくい命名、層の責務の混在、テストしづらい構造、種類が増えたときの拡張性、変更の影響範囲を挙げている。
雛形では、この6つを Goal の記入例として HTML コメントに入れた。

## issuelint を関門にする

issuelint は、Issue の本文が定義になっているかを確かめる Go のコマンドで、hiro8ma/agent リポジトリの `go/cmd/issuelint` にある。
次のどれかに当たると終了コード1で終わり、ジョブはエージェントを動かす前に止まる。

- 4つの見出しのどれかがない
- 見出しの下が空か、HTML コメントだけ
- コード変更は行わないことがどこにも書かれていない
- 「以前の指示を無視」や `git push` など、作業の範囲を広げる語を含む

雛形の案内は HTML コメントで書いてあるので、Goal と Context Pointers を埋めずに Issue を作ると issuelint で止まる。
検査は語の一致なので、言い換えた指示は通る。
issuelint は Issue を書く人への差し戻しで、プロンプトインジェクションの対策はプロンプトと権限の側で持つ。

## Codex 版と Claude Code 版

| 項目 | Codex 版 | Claude Code 版 |
|---|---|---|
| Action | `openai/codex-action@v1` | `anthropics/claude-code-action@v1` |
| 秘密情報 | `secrets.OPENAI_API_KEY` | `secrets.ANTHROPIC_API_KEY` |
| 起動の条件 | ジョブの `if` でラベル名を確かめる | ジョブの `if` と `label_trigger: agent-proposal` |
| 読み取り専用にする方法 | `permission-profile: ":read-only"` | `--allowedTools` で道具を列挙し、ジョブを読み取り権限にする |
| プロンプトの渡し方 | `prompt-file` でファイルを渡す | `prompt` でファイルを読むよう指示する |
| 提案書の書き方 | 最終応答を Action が `output-file` に書く | エージェントが `docs/proposals/` に書く |
| モデルの指定 | `model` を省き既定のモデルを使う。`effort` は `low` | `claude_args` の `--model` |
| 起動した人の検査 | 書き込み権限を Action が確かめる | 書き込み権限を Action が確かめる |

Codex 版はエージェントにファイルを書かせないので、出力を1ファイルに絞る仕組みを Action が持つ。
Claude Code 版はエージェントが書くので、道具の制限とジョブの分離で同じ状態を作る。
Claude Code Action は `prompt` を渡すと自動実行として動き、v1では `mode` の入力がなくなった。
`allowed_tools` / `disallowed_tools` / `model` の入力も非推奨で、`claude_args` に `--allowedTools` などを書く。
モデルを固定するなら、組織で許可されたものを書く。

## PR で見ること

提案書の PR は、コードの差分ではなく方針をレビューする。

- 「現状の課題」が、読んだコードの事実に基づいているか。推測であれば推測と書かれているか
- 「変更対象になりそうなファイル」が Context Pointers の範囲から外れていないか
- 「小さく進めるための実装ステップ」の各ステップが、1つの PR でレビューできる大きさか
- 「Issue の中で従わなかった指示」に何か挙がっていないか。挙がっていれば Issue の書き手に確かめる
- PR の差分が提案書の1ファイルだけか

PR は `Closes` を使わず、`#番号` で Issue にリンクするだけにした。
提案書をマージしても Issue は閉じず、実装の Issue と PR に引き継ぐ。

## Spec Kit で新しく分かった点

同じ教材は、GitHub Spec Kit を Codex で使う手順も扱っている。
[spec-driven-development.md](spec-driven-development.md) に書いていない点を、2026-10-11時点の最新版（v1.1.3）に合わせて書く。

- Python 3.11以降で `uv tool install specify-cli` で入れ、`specify init <dir> --integration codex` で Codex 向けに初期化する。以前の `--ai` は v0.10.0でなくなった
- Codex 向けには、Spec Kit が `.agents/skills/` に skill を入れる。Codex では `$speckit-specify` の形で呼ぶ
- clarify は、specify で書いた仕様の曖昧な箇所を質問し、答えを仕様に戻す。plan の前に流す
- analyze は spec / plan / tasks の食い違いと抜けを報告する読み取り専用の検査で、implement の前に流す
- specify では技術スタックを決めない。何を作るかと理由だけを書き、技術スタックとアーキテクチャは plan で渡す

中心のコマンドは constitution / specify / clarify / plan / analyze / tasks / implement / checklist / converge の9つ。
converge は新しく入ったコマンドで、implement の後に流し、収束したと報告されるまで implement と繰り返す。
taskstoissues は github の拡張に移った。

コマンドの書き方は連携先で変わる。
教材の `/speckit.clarify` のようなドット区切りは以前の表記で、今も公式リファレンスで使われている。
Codex では `$speckit-clarify`、Copilot など skill 形式の多くの連携先では `/speckit-clarify` と書く。

## 出典

- Codex の教材（出典は明示されていない）
- openai/codex-action https://github.com/openai/codex-action
- codex-action のセキュリティ https://github.com/openai/codex-action/blob/main/docs/security.md
- anthropics/claude-code-action https://github.com/anthropics/claude-code-action
- claude-code-action のセキュリティ https://github.com/anthropics/claude-code-action/blob/main/docs/security.md
- claude-code-action の設定 https://github.com/anthropics/claude-code-action/blob/main/docs/configuration.md
- peter-evans/create-pull-request https://github.com/peter-evans/create-pull-request
- GitHub Spec Kit https://github.com/github/spec-kit
- Spec Kit の変更履歴 https://github.com/github/spec-kit/blob/main/CHANGELOG.md
- Spec Kit の連携先と呼び出し方 https://github.com/github/spec-kit/blob/main/docs/reference/integrations.md
- PromptPwnd（Aikido） https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents
- Clinejection（Simon Willison） https://simonwillison.net/2026/Mar/6/clinejection/
- Warp の software factory の手引き https://docs.warp.dev/guides/agent-workflows/set-up-a-software-factory.md
