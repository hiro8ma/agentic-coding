---
title: "Claude CodeとCodexで共有するSkillの呼び出し方針をそろえる"
date: "2026-10-18"
tags: [skills, claude-code, codex, portability, github-actions, security]
---

# Claude CodeとCodexで共有するSkillの呼び出し方針をそろえる

片方のエージェントで使ってきたSkillのディレクトリを、もう片方からも読ませると、自動で呼ばせない設定がそろわないことがある
Claude CodeとCodexは、自動呼び出しを止める設定を別のファイルから読み、相手の設定を無視する
デプロイのように人が明示して呼ぶべきSkillが、片方のエージェントでは依頼の内容から自動で選ばれうる
`tools/skill-parity/check_skill_parity.py`は、この食い違いと、片方のエージェントから見えないSkillを検出する

挙動はClaude Code 2.1.302とCodex CLI 0.162.0で確かめた
Skillの配置と呼び出しの設定の一般論は[skill-reuse-and-portability.md](skill-reuse-and-portability.md)にあるので、ここでは繰り返さない

## 方針を2か所に書く理由

| エージェント | 自動呼び出しを止める設定 | 置き場所 |
|---|---|---|
| Claude Code | `disable-model-invocation: true` | `SKILL.md`のfrontmatter |
| Codex | `policy.allow_implicit_invocation: false` | Skillのディレクトリの`agents/openai.yaml` |

どちらの設定も、もう片方のエージェントは読まない
設定の組み合わせが違う4つのSkillを同じディレクトリに置き、モデルに渡る一覧に載ったか（自動で呼ばれうるか）を比べた結果は次のとおり

| 設定 | Claude Code | Codex |
|---|---|---|
| どちらもなし | 載る | 載る |
| Claude Codeの設定だけ | 載らない | 載る |
| Codexの設定だけ | 載る | 載らない |
| 両方 | 載らない | 載らない |

Claude Codeに慣れた人が`disable-model-invocation: true`だけを書くと、Codexでは自動で呼ばれる
共有するSkillには、2つの設定を同じ値で書く

真偽値の読み方も違う

- Codexが`false`と読んだのは`false` / `False` / `FALSE`だけだった。`no` / `0` / `"false"`を書くと設定が無視され、自動で呼ばれる
- Claude Codeは`true`のほかに`yes` / `on` / `1`と、引用符で囲んだ`"true"`も真と読んだ

名前の扱いも違う
`name`がディレクトリ名と違うと、Claude Codeは一覧に`ディレクトリ名 (name)`と出し、文書ではどちらの名前でも呼べる
Codexは一覧に`name`だけを出すので、手順書に書く呼び出しの名前がエージェントごとに変わる

frontmatterの不備に対する扱いも違い、Claude Codeで動くSkillがCodexでは一覧から消える

| frontmatter | Claude Code | Codex |
|---|---|---|
| `description`がない | 本文の最初の行を説明にする | 読み込まない |
| `name`が65文字 | 読み込む | 読み込まない |
| `description`が長い | `description`と`when_to_use`の合計を1,536文字で切る | 1,024文字で切る |

Claude Codeの1,536文字は公式の文書にあり、`skillListingMaxDescChars`で変えられる
Codexの1,024文字は公式の文書に書かれておらず、上の版で観測した値である
[Agent Skillsの仕様](https://agentskills.io/specification)も`name`を64文字、`description`を1,024文字までとしている

## どこに置けば両方から見えるか

Codexが公式の文書で挙げるリポジトリの置き場所は`.agents/skills`で、Claude Codeは`.claude/skills`である
一時的なGitリポジトリに最小の`SKILL.md`を置き、それぞれのエージェントの一覧に載るかを確かめた

| 置き方 | Claude Code | Codex |
|---|---|---|
| `.claude/skills/`だけ | 見える | 見えない |
| `.agents/skills/`だけ | 見えない | 見える |
| `.codex/skills/`だけ | 見えない | 見える |
| `.agents/skills`を`.claude/skills`へのシンボリックリンクにする | 見える | 見える |
| `.codex/skills`を`.claude/skills`へのシンボリックリンクにする | 見える | 見える |
| `.claude/skills`を`.agents/skills`へのシンボリックリンクにする | 見える | 見える |
| `.agents/skills/<name>`を`.claude/skills/<name>`へのリンクにする | 見える | 見える |

`skills`のディレクトリ自体をリンクにすると、Codexは解決したパスを一覧に出し、同じディレクトリへ2本のリンクがあっても1回だけ載せた
Codexのプロジェクトを信頼していてもいなくても、一覧は同じだった
サブディレクトリから起動しても、リポジトリのルートの`.agents/skills`と`.codex/skills`を読んだ

`.codex/skills`は公式の文書に載っていない
今の版で読まれても、使い続けられるかは分からないので、Codex側の入口は`.agents/skills`にする
片方のエージェントで使ってきたディレクトリを正本にし、もう片方の置き場所からシンボリックリンクを張ると、ファイルの移動がいらない

Codexの一覧は`codex debug prompt-input`で取った
このコマンドはモデルを呼ばずに、モデルへ渡す入力を表示する
`CODEX_HOME`と`HOME`を一時ディレクトリに向け、利用者の設定とSkillを混ぜなかった
Claude Codeは`claude -p --output-format stream-json`の最初のイベントで読み込んだSkillを見た
モデルへ渡る一覧は、`ANTHROPIC_BASE_URL`を手元のポートに向け、送られる予定だったリクエストの本文を手元で保存して確かめた
どちらの確認でも、モデルのAPIへの通信は起きていない

## チェッカーで食い違いを見つける

`tools/skill-parity/check_skill_parity.py`はPython 3.10以降の標準ライブラリだけで動く
1ファイルなので、チームのリポジトリの`scripts/`などへコピーして使える

```bash
python3 tools/skill-parity/check_skill_parity.py .        # リポジトリのルートを検査する
python3 tools/skill-parity/check_skill_parity.py --fix .  # 足りない agents/openai.yaml を作ってから検査する
python3 -m unittest discover -s tools/skill-parity        # チェッカーのテスト
```

`.claude/skills` / `.agents/skills` / `.codex/skills`を走査し、シンボリックリンクを解決したパスが同じSkillは1つにまとめる
上の観測に基づき、`.claude/skills`から届けばClaude Codeから見え、`.agents/skills`か`.codex/skills`から届けばCodexから見えると判定する

| 判定 | 報告すること |
|---|---|
| NG | 片方のエージェントだけが自動呼び出しを止めている（`agents/openai.yaml`がない場合や、Codexが読まない値を含む） |
| NG | 片方のエージェントから見えない |
| NG | Codexが読み込まない（frontmatterがない、`description`がない、`name`が64文字を超える） |
| warn | `name`がディレクトリ名と違う |
| warn | `description`が`--max-description`（既定1,024）を超える、または`description`と`when_to_use`の合計が`--claude-listing-limit`（既定1,536）を超える |
| warn | Codexから`.codex/skills`経由でだけ見える |
| warn | 真偽値として読めない値がある |

NGが1件でもあれば終了コード1、引数やルートの誤りは2で終わる
warnだけなら0で終わる
`fixtures/drift`に対する出力は次のとおり

```text
skill           claude  codex  claude-auto  codex-auto  result
deploy-sample   yes     yes    off          on          NG
release-sample  yes     yes    off          off         ok
report-sample   yes     yes    on           on          ok
review-sample   yes     yes    on           off         NG

NG    deploy-sample  Claude Code は自動で呼ばないが、Codex は自動で呼ぶ（agents/openai.yaml がない。--fix で作れる）
NG    review-sample  Codex は自動で呼ばないが、Claude Code は自動で呼ぶ（SKILL.md に disable-model-invocation: true がない）

食い違いのある Skill が2件ある
```

この判定は、同じfixtureを2つのエージェントに読ませた一覧と一致した
`--fix`は、`disable-model-invocation: true`があり`agents/openai.yaml`がないSkillにだけ、`allow_implicit_invocation: false`を書いたファイルを作る
既存の`agents/openai.yaml`と`SKILL.md`は書き換えないので、逆向きの食い違いや既存ファイルの値は手で直す

チェッカーが確かめるのは置き場所と設定の静的な食い違いで、実際に依頼でSkillが選ばれるかは確かめない
呼び出しと成果の確かめ方は[skills-plugins-practice.md](skills-plugins-practice.md)にある
YAMLはfrontmatterと`agents/openai.yaml`に出る範囲だけを読み、読めない形はNGかwarnで報告する
同じ名前のSkillをシンボリックリンクではなくコピーで置くと、別々のSkillとして数え、それぞれ片方からしか見えないと報告する

## CIのエージェントも同じSkillを読む

CIのエージェントも、チェックアウトしたリポジトリのSkillを読む
Codex Actionはチェックアウトしたリポジトリを作業ディレクトリにして`codex exec`を動かすので、Codexの文書の探索順序に従えば`.agents/skills`も読まれる
claude-code-actionのソースでは、設定の読み込み元に既定でプロジェクトが入り、Claude Codeの文書ではこの読み込み元が`.claude/skills`を読む
片方だけ自動呼び出しを止めたSkillは、CIのエージェントにも自動で選ばれうる

[issue-to-proposal-workflow.md](issue-to-proposal-workflow.md)の雛形2本は、起動できる人とログへの出力を両方のActionの入力で絞った
入力の名前は、それぞれのActionの`v1`タグの`action.yml`で確かめた

| 目的 | Codex版 | Claude Code版 |
|---|---|---|
| 書き込み権限のない人とbotに起動させない | `allow-users: ""` / `allow-bots: "false"` | `allowed_non_write_users: ""` / `allowed_bots: ""` |
| エージェントの権限を絞る | `permission-profile: ":read-only"` / `safety-strategy: drop-sudo` | `--allowedTools`の列挙と`--disallowedTools "WebFetch,WebSearch"` |
| 秘密情報と中身を外に出さない | `drop-sudo`でメモリ上のAPIキーを読めなくする。ログの出力を絞る入力はない | `show_full_output: "false"` / `display_report: "false"` |

Actionの入力の値はどれも既定値と同じで、挙動は変わらない
既定値を明示しておくと、誰かが緩めたときにワークフローの差分としてレビューに出る
`--disallowedTools`だけは新しく足した
WebFetchとWebSearchは`--allowedTools`に入れていないが、道具の一覧からも外し、外部へ送る経路を減らす
Codex Actionの文書は、`drop-sudo`を外すと読み取り専用でもsudoでメモリ上のAPIキーを読めると説明している
claude-code-actionは、GitHub Actionsのデバッグログ（`ACTIONS_STEP_DEBUG`）を有効にすると`show_full_output`を自動で有効にするので、公開リポジトリではデバッグログを有効にしない
`drop-sudo`は元に戻せない変更をランナーに加えるので、雛形はGitHubのホストするランナーで動かす前提にしている

Codex Actionの文書は、Actionをジョブの最後のステップに置くことを勧めている
雛形はCodexの後に`actions/upload-artifact`を置くが、`:read-only`ではCodexがファイルを書き換えられない
`:workspace`のように書き込める権限に変えるなら、提案書を`final-message`の出力で次のジョブに渡す形に変える
GitHub Actionsの運用全般は[coding-agent-github-actions.md](coding-agent-github-actions.md)、チームで共有する承認の境界は[codex-team-config.md](codex-team-config.md)にある

雛形はRubyのYAMLで読み込めることと、actionlint 1.7.12で新しい行に指摘がないことを確かめた
actionlintはCodex版の`permission-profile`を未定義の入力と報告する
これは変更前からある指摘で、actionlintが持つ入力の一覧が古いために起きる
`v1`タグの`action.yml`には`permission-profile`がある

## 確かめていないこと

- Codexで自動呼び出しを止めたSkillを`$name`で明示して呼べること。`codex debug prompt-input`は`$name`を書いても本文を足した入力を表示しないので、この方法では確かめられなかった
- WindowsでのシンボリックリンクとClaude Code、Codexの探索
- CodexのIDE拡張とアプリが、CLIと同じ置き場所を読むこと
- 雛形の2本をGitHubの上で動かした結果。Secretsを用意しておらず、モデルを呼ぶ実行はしていない
- CIのエージェントの一覧に、リポジトリのSkillが実際に載ること
- `allowed_bots`などの入力の効き方。claude-code-actionとCodex Actionのソースと文書で確かめただけで、botからの起動は試していない

## 参照資料

- [Claude Code Skills](https://code.claude.com/docs/en/skills)
- [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Agent Skillsの仕様](https://agentskills.io/specification)
- [openai/codex-action](https://github.com/openai/codex-action)と[セキュリティの文書](https://github.com/openai/codex-action/blob/main/docs/security.md)
- [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action)と[セキュリティの文書](https://github.com/anthropics/claude-code-action/blob/main/docs/security.md)
- [actionlint](https://github.com/rhysd/actionlint)
