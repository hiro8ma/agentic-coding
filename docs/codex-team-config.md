---
title: "Codexの設定をチームで共有し、承認の境界をそろえる"
date: "2026-10-18"
tags: [codex, claude-code, rules, execpolicy, permissions, team-config, sandbox]
---

# Codexの設定をチームで共有し、承認の境界をそろえる

チームで同じ境界を使うなら、`templates/codex-team/`をリポジトリのルートへコピーする
マージ、push、削除、本番環境への反映のような操作に、人の承認を挟む
同じディレクトリにClaude Code版の設定も入れ、どちらのエージェントを使っても同じ操作で止まるようにした
`config.toml`の階層とAGENTS.mdの探索順序は[codex-project-configuration.md](codex-project-configuration.md)にあるので、ここでは繰り返さない

| ファイル | 役割 |
|---|---|
| `.codex/config.toml` | サンドボックスを`workspace-write`、承認を`on-request`にする |
| `.codex/rules/team.rules` | 人の承認が要るコマンドと、禁止するコマンド |
| `AGENTS.md` | 変更時の注意と、レビューの観点 |
| `.claude/settings.json` | Claude Code向けに、同じ境界を`deny` / `ask`で書いたもの |
| `scripts/check-codex-rules.sh` | 規則の判定を`codex execpolicy check`で確かめる |

規則の判定はCodex CLI 0.162.0で確かめた
Rulesは公式の文書で実験的な機能とされ、仕様が変わりうる
Codexを更新したら検証スクリプトを流し直す

## 置き場所を分ける

AGENTS.mdはモデルへの指示で、モデルが従わなかったときにコマンドを止める力はない
AGENTS.mdに「マージしない」と書くだけでは、モデルが指示を取り違えたときにマージが実行されうる
止めたい操作はRulesに書き、Codexがコマンドを実行する前に評価させる

| 仕組み | 置き場所 | 書くもの |
|---|---|---|
| AGENTS.md | リポジトリのルートと各ディレクトリ | ログに個人情報を出さない、マイグレーションは追加だけ、のような判断の基準とレビューの観点 |
| Rules | `.codex/rules/*.rules` | コマンドの前置きごとの判定（`allow` / `prompt` / `forbidden`） |
| config.toml | `.codex/config.toml` | サンドボックスと承認の既定値 |
| Skills | `.agents/skills/` | 必要なときだけ読み込む作業の手順 |

逆に、ログに個人情報を出さないといった判断はコマンドの形では書けない
こうした基準はAGENTS.mdに置き、レビューでも確かめる
雛形のAGENTS.mdでは、`Review guidelines`の節にレビューで確かめる観点を書いた
GitHubのCodexレビューでAGENTS.mdをどう使うかは[codex-review-security.md](codex-review-security.md)にある

## 規則の判定と層の重なり

規則は`prefix_rule`で、コマンドの先頭のトークン列に対する判定を書く
判定の意味は次のとおり

| 判定 | Codexの動き |
|---|---|
| `allow` | サンドボックスの外で、承認なしに実行する |
| `prompt` | 当てはまるたびに承認を求める |
| `forbidden` | 承認を求めずに拒否する |

規則のファイルは複数の層から読まれる
利用者の`~/.codex/rules/`、信頼済みのプロジェクトの`.codex/rules/`、管理者の`requirements.toml`の`[rules]`である
1つのコマンドに複数の規則が当たると、層を問わず最も厳しい判定が使われる（`forbidden` > `prompt` > `allow`）

このため、チームの規則はほかの層の規則では緩められない下限になる
利用者が承認の画面でコマンドを許可リストに足すと、Codexは`~/.codex/rules/default.rules`に`allow`の規則を足す
それでも、チームの規則が`prompt`なら承認を求め、`forbidden`なら拒否する
検証スクリプトは、`gh pr`や`git push`を個人の層で`allow`にした規則を重ね、チームの判定が変わらないことを確かめている

規則を緩めるには規則のファイルそのものを変える必要があり、その変更はPRの差分としてレビューに出る
サンドボックスの中のエージェントは、このファイルを書き換えられない
`codex sandbox -P :workspace`で`.codex/`と`.agents/`に書き込むと、`Operation not permitted`で失敗した
同じ条件でAGENTS.mdと`.claude/settings.json`は書き込めたので、これらの変更はPRの差分で確かめる

### 雛形の判定

| コマンド | 判定 | 理由 |
|---|---|---|
| `gh pr merge` | `prompt` | マージは人がCIとレビューの状態を確かめて決める |
| `git push` | `prompt` | リモートへの反映は人が承認する |
| `git push --force` / `git push -f` | `forbidden` | 他人のコミットを消しうる |
| `rm -rf`（`-fr` / `-Rf` / `-fR`を含む） | `forbidden` | 取り消せない |
| `terraform apply` / `terraform destroy` | `prompt` | planの結果を人が確かめる |
| `kubectl delete` | `prompt` | 接続先のコンテキストと名前空間を人が確かめる |

強制pushは、禁止と承認の2段にした
規則は先頭からトークンを1つずつ比べるので、`git push origin main --force`は`git push --force`の規則に当たらない
そこで`git push`全体を`prompt`にし、フラグを末尾に置いた形も承認なしには通さない
`--force-with-lease`は別のトークンなので禁止の規則に当たらず、`prompt`になる
履歴の上書きが要るときは、人が`--force-with-lease`を承認して使う

`git status`や`git diff`を`allow`にする規則は置かなかった
承認を`on-request`にした`workspace-write`では、これらのコマンドはサンドボックスの中で承認なしに動くので、`allow`を足しても承認の手間は減らない
`allow`はコマンドをサンドボックスの外へ出すので、`git diff --output=<path>`のような書き込みがワークスペースの外にも届く

### 規則で止まらない形

規則は、よくある形のコマンドに人の判断を挟むためのものである
書き込みの範囲を守るのはサンドボックスで、規則はその代わりにならない

- `rm -r -f`、`kubectl -n prod delete`、`terraform -chdir=infra apply`のように、前置きのトークンが規則と違う形は当たらない。サンドボックスと承認の設定で扱われる
- 公式の文書によると、`bash -lc "a && b"`のように`&&` / `||` / `;` / `|`だけでつないだスクリプトは、Codexがコマンドごとに分けて評価する。リダイレクト、`$(...)`、環境変数の代入、ワイルドカードを含むスクリプトは全体を1つのコマンドとして評価するので、`rm -rf`の規則に当たらない
- 管理者が`requirements.toml`に書く規則は`prompt`か`forbidden`だけで、`allow`は書けない

```toml
# requirements.toml（管理者が配布する）
[rules]
prefix_rules = [
  { pattern = [{ token = "gh" }, { token = "pr" }, { token = "merge" }], decision = "prompt", justification = "マージは人が決める" },
]
```

Codexのバイナリには、`requirements.toml`の`allow`を拒否するエラーの文言が含まれている
`requirements.toml`を実際に配置した動作は確かめていない

## 信頼済みのプロジェクトでだけ効く

Codexはプロジェクトの`.codex/`を、信頼済みのプロジェクトでだけ読み込む
信頼していないあいだは、`.codex/config.toml`、Rules、Hooksが無視される
AGENTS.mdとSkillsは信頼の有無にかかわらず読み込まれる

これを`codex debug prompt-input`で確かめた
このコマンドは、モデルへ渡す入力をモデルを呼ばずに表示する
雛形の`approval_policy`を`never`に書き換えたプロジェクトで比べた結果は次のとおり

| 状態 | `sandbox_mode` | 承認 | AGENTS.md |
|---|---|---|---|
| 信頼していない（利用者の設定が空） | `read-only` | プロジェクトの`never`は使われない | 読まれる |
| 信頼済み | `workspace-write` | `never` | 読まれる |

信頼の状態は利用者の`~/.codex/config.toml`に保存され、リポジトリからは設定できない
メンバーは最初の起動で「Trust this folder?」に答えるか、`/permissions`で信頼する
導入の手順は次のとおり

1. リポジトリの`.codex/`とHooksの中身を確かめてから、プロジェクトを信頼する
2. `codex debug prompt-input`を実行し、出力の`sandbox_mode`が`workspace-write`になっていることを確かめる
3. 規則を変えたら、`scripts/check-codex-rules.sh`を流す

信頼していないメンバーには、チームの規則も`config.toml`も効かず、利用者の設定のまま動く
信頼済みでも、`--sandbox danger-full-access`のようなCLIのフラグはプロジェクトの設定より優先される
信頼の有無やフラグに関係なく強制したい境界は、管理者が`requirements.toml`で配る
`allowed_sandbox_modes`で使えるサンドボックスを絞り、`[rules]`で規則を足す

## Claude Codeとの対応

| 目的 | Codex | Claude Code |
|---|---|---|
| 作業の指示 | AGENTS.md（上位から順に結合） | CLAUDE.md。CLAUDE.mdが無ければAGENTS.mdを読む（v2.1.277以降） |
| コマンドの境界 | `.codex/rules/*.rules`の`prefix_rule` | `.claude/settings.json`の`permissions`（`deny` / `ask` / `allow`） |
| 判定の重なり | 層を問わず最も厳しい判定 | `deny` > `ask` > `allow`。配列は全スコープで結合される |
| 管理者の強制 | `requirements.toml`（`[rules]`は`prompt`と`forbidden`だけ） | `managed-settings.json`（利用者が上書きできない。`allowManagedPermissionRulesOnly`で管理者の規則だけにできる） |
| 作業の手順 | `.agents/skills/` | `.claude/skills/` |
| サンドボックス | `config.toml`の`sandbox_mode` | `settings.json`の`sandbox.enabled`（既定は無効） |

Claude Codeでも、プロジェクトの`deny`と`ask`は利用者の`allow`で緩められない
雛形の`.claude/settings.json`はCodexの`forbidden`を`deny`に、`prompt`を`ask`に写した
`Bash(git push *)`の`*`は任意の文字列に当たるので、`git push origin main --force`も`ask`になる

雛形はどちらのエージェントにも`allow`を置かない
`git diff --output=<path>`のように、読み取りに見えて書き込むオプションがあるためである
読み取りのコマンドを承認なしにしたいメンバーは、自分のユーザー層に書く。チームの`deny`と`ask`はそれでも緩まない
Claude Codeの文書も、Bashの規則は引数の書き方で回避でき、セキュリティの境界ではないとしている

## 検証スクリプト

`scripts/check-codex-rules.sh`は、規則の判定を表と突き合わせる
CodexとjqのCLIが要る

```bash
cd templates/codex-team
./scripts/check-codex-rules.sh                   # .codex/rules/team.rules を検査する
./scripts/check-codex-rules.sh path/to/x.rules   # 別の規則ファイルを検査する
```

確かめることは3つある

- 規則を読み込めるか。各規則の`match`と`not_match`の例が外れると、Codexは読み込みの時点で失敗する
- 代表的なコマンドの判定が表のとおりか。どの規則にも当たらない形も`none`として表に入れ、規則で止まらない形を明示する
- 個人の層で`allow`を足しても、チームの判定が変わらないか

期待と違う判定が1件でもあれば終了コード1で終わり、CodexかjqのCLIが無ければ2で終わる
規則を変えたら、スクリプトの表も同じ変更で直す
`codex execpolicy check`はシェルのスクリプトを分けないので、`bash -lc`を含む形はこのスクリプトでは確かめられない
このリポジトリのCIはCodex CLIを入れていないので、スクリプトはCIに入れず手元で流す

## 確かめていないこと

- 実際のCodexのセッションで、プロジェクトの規則が読み込まれて承認や拒否が起きること
- `approval_policy`が`never`のとき、`prompt`の規則に当たったコマンドが拒否されること。openai/codexのソース（`codex-rs/core/src/exec_policy.rs`）とテストでは拒否される実装だが、文書には書かれておらず、実際のセッションでは確かめていない
- Claude Codeの規則の当たり方。`Bash(git push -f *)`が引数の無い`git push -f`に当たるかを含め、Claude Codeでは動かしていない

## 参照資料

- [CodexのRules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [Codexの管理者向けの設定](https://learn.chatgpt.com/docs/enterprise/managed-configuration)
- [Codexの設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)
- [CodexのSkills](https://learn.chatgpt.com/docs/build-skills)
- [Claude Codeの権限](https://code.claude.com/docs/en/permissions)
- [Claude Codeの設定](https://code.claude.com/docs/en/settings)
- [Claude Codeの管理者向けの設定](https://code.claude.com/docs/en/managed-settings)
