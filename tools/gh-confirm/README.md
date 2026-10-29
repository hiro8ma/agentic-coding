# gh-confirm

外に出る GitHub の操作のうち、レビュー依頼とマージを、実行の前に止めて利用者に確かめさせる hook
Claude Code では確認の画面を出し、Codex ではコマンドを止めて利用者に実行を任せる
Python 3.9以降の標準ライブラリだけで動く

## なぜ hook にしたか

プロンプト（CLAUDE.md / AGENTS.md）に「レビュー依頼は、出す直前に毎回利用者の許可を求める」と書いた後にも、エージェントが確認なしに依頼を出すことがある
プロンプトの規則はモデルが読んで判断に使うもので、モデルが取り違えたときにコマンドを止める力はない
レビュー依頼やマージは相手に通知が届き、後から取り消しても届いた通知は消えない
そこで、モデルの外にある実行の層（ハーネス）に置いた hook で、コマンドが走る前に毎回同じ手順で文字列を判定する
失敗をそれが属する層の規則として戻すという考え方は「Harness, Loops, Graphs」（m4lka、2026-10-25）による

## 止めるもの

| 操作 | 止める書き方 | 理由の文に並べるもの |
|---|---|---|
| レビュー依頼 | `gh pr edit` の `--add-reviewer`（`--add-reviewer=x` を含む） | PR と依頼先 |
| レビュー依頼 | `gh pr create` / `gh pr new` の `--reviewer` / `-r` | 依頼先（PR は「新しく作る PR」） |
| レビュー依頼 | `gh api` で `.../pulls/<番号>/requested_reviewers` に POST する（`-X POST` か、`-f` / `-F` / `--input` を付けて POST になる形） | PR と `reviewers[]` / `team_reviewers[]` の値 |
| レビュー依頼 | `gh api graphql` で `requestReviews` を含む | なし（GraphQL の ID で指定するので読めない） |
| マージ | `gh pr merge`（`--auto` と `--admin` は理由の文に書く） | PR |
| マージ | `gh api` で `.../pulls/<番号>/merge` に PUT する | PR |
| マージ | `gh api graphql` で `mergePullRequest` / `enablePullRequestAutoMerge` を含む | なし（GraphQL の ID で指定するので読めない） |

次の形で包んでも見つける

- `&&` / `||` / `;` / `|` / 改行でつないだコマンド
- `$( )` / バッククォート / サブシェルの `( )` / `{ }` / `if` などの制御構文の中
- `bash -c` / `sh -c` / `zsh -c` の文字列、`eval` の文字列、シェルに流すヒアドキュメントとヒアストリング
- `env X=1` / `X=1` / `sudo` / `timeout` / `nice` / `nohup` / `time` / `exec` / `command` / `xargs` を前に付けたもの、`\gh` や `/opt/homebrew/bin/gh` での呼び出し
- 区切りを引用符で囲まないヒアドキュメント（`<<EOF`）の本文にある `$( )`。bash が実行するため

PR は番号、URL、ブランチ名、`-R` / `--repo` から読む
番号を指定しない `gh pr merge` は「現在のブランチの PR」、`xargs` で渡すものは「xargs で渡す PR」と書く

## 止めないもの

コマンドとして実行されない文字列と、読むだけの操作は止めない

| 例 | 止めない理由 |
|---|---|
| `echo "gh pr merge 12"` / `echo gh pr merge 12` | `gh` が `echo` の引数 |
| `grep -rn -- --add-reviewer .` | `--add-reviewer` が `grep` の引数 |
| `gh pr create --body "add --reviewer later"` | `--reviewer` が本文の値 |
| `cat <<'EOF'` の本文に書いた `gh pr merge 12` | ヒアドキュメントの本文 |
| `git status # gh pr merge 12` | コメント |
| `gh pr edit 12 --remove-reviewer alice` / `gh api -X DELETE .../requested_reviewers` | 依頼を外す操作 |
| `gh pr view 12` / `gh api .../requested_reviewers`（GET） | 読むだけ |

## 理由の文

Claude Code の確認の画面に、次の文が出る

```text
利用者の確認が要る GitHub の操作を含む
- レビュー依頼: octo/app#12 に alice, bob
- マージ: #34（--auto 付き。必要な条件が揃った時点で、確認なしにマージされる）
上の対象が意図どおりかを確かめてから承認する
```

## Claude Code に入れる

PreToolUse(Bash) の hook として登録する
確認が要るときは `hookSpecificOutput.permissionDecision` に `"ask"` と理由を返し、それ以外は何も出さずに通す
`"ask"` は auto mode でも確認の画面を出させる
`-p` で動かすときは答える人がいないので、Claude Code は呼び出しを拒否し、理由の文をモデルに渡す

このリポジトリでは `.claude/settings.json` に登録した
全部のリポジトリで効かせるなら、スクリプトをユーザーの設定の場所に置き、`~/.claude/settings.json` に足す
すでに `PreToolUse` があれば、その配列に足す

```bash
mkdir -p ~/.claude/hooks
cp tools/gh-confirm/gh_confirm.py ~/.claude/hooks/
```

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 \"$HOME/.claude/hooks/gh_confirm.py\"" }
        ]
      }
    ]
  }
}
```

## Codex に入れる

Codex にも PreToolUse の hook がある
ただし Codex の PreToolUse は `permissionDecision: "ask"` を受け付けない
公式の文書とソースでは、`ask` を返すと hook の失敗として扱い、コマンドをそのまま実行する
そこで `--codex` を付けると `deny` を返し、同じ理由の文を `systemMessage` で利用者にも見せる
利用者は理由の文を見て承認するかを決め、承認するなら自分でコマンドを実行する

```bash
mkdir -p ~/.codex/hooks
cp tools/gh-confirm/gh_confirm.py ~/.codex/hooks/
```

`~/.codex/hooks.json` に次を書く

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "^Bash$",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.codex/hooks/gh_confirm.py\" --codex",
            "statusMessage": "GitHub の操作を確かめている"
          }
        ]
      }
    ]
  }
}
```

Codex は、管理者が配っていない hook を、利用者が `/hooks` で中身を確かめて信頼するまで動かさない
書いたら Codex を起動し、`/hooks` でこの hook を信頼する

### Rules で確認の画面を出す

Codex の Rules の `prefix_rule` は、`decision = "prompt"` で確認の画面を出せる
ただし、コマンドの先頭のトークン列としか比べられない
引数の途中にある `--add-reviewer` や、`gh pr --repo octo/app merge` のように前にフラグを置いた形は見られない

| ファイル | 規則 | 入れる場面 |
|---|---|---|
| `gh-merge.rules` | `gh pr merge` で始まるコマンドを `prompt` にする | hook と一緒に入れてよい。hook が効いていないとき（未信頼、無効）の下限になる |
| `gh-pr-write.rules` | `gh pr create` / `gh pr new` / `gh pr edit` で始まるコマンドを `prompt` にする | hook を使えないときだけ入れる。タイトルや本文の編集でも確認が出る |

```bash
mkdir -p ~/.codex/rules
cp tools/gh-confirm/gh-merge.rules ~/.codex/rules/
codex execpolicy check --rules ~/.codex/rules/gh-merge.rules -- gh pr merge 12
```

最後のコマンドは `"decision":"prompt"` を含む JSON を出す

openai/codex のソースを読んだ範囲では、PreToolUse の hook はツールを呼ぶ前に走り、`deny` ならツールを呼ばない
Rules による承認の判定はツールの処理の中で起きる
このため、hook と `gh-merge.rules` を両方入れると hook が先に止め、Rules の確認の画面は出ない
この順序は実際の Codex のセッションでは確かめていない

## 試す

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"gh pr edit 12 --add-reviewer alice"}}' \
  | python3 tools/gh-confirm/gh_confirm.py
```

## テスト

```bash
python3 -m unittest discover -s tools/gh-confirm
```

止める例と止めない例を表にして判定を確かめ、hook の入出力（`ask` / `deny`、壊れた JSON を通すこと）も確かめる
Codex CLI があれば、Rules の判定も `codex execpolicy check` で確かめる
無ければその検査は飛ばす

## 限界

- コマンドの文字列しか読まない
  - スクリプトのファイル（`bash release.sh` / `source x.sh`）、`gh api --input` や `-F query=@file` で渡すファイル、`xargs` やパイプで後から渡す引数の中身は見ない
- `gh` 以外の経路の GitHub API の呼び出しは見ない
  - `curl` で叩く REST API、各言語の SDK、MCP サーバーのツール、ブラウザの操作
  - MCP のツールは Bash の呼び出しではないので、この hook の matcher に当たらない
- `gh alias set` で作った `gh` のエイリアス、シェルの関数やエイリアスで包んだ `gh` は見ない
- bash の文法を全部は読まない
  - `case` の分岐、`arr=(...)` の配列、`env -S` で分ける文字列、変数に入れて展開するコマンド（`cmd="gh pr merge 1"; $cmd`）は見ない
- モデルの取り違えを止めるためのもので、悪意のある入力を防ぐ境界ではない
  - 変数で組み立てる（`c=g; ${c}h pr merge 1`）、符号化した文字列を復号して実行する、といった書き方は止めない
- 解析に失敗したとき（入れ子が深すぎる、など）は通す。ガードの不具合で全部の Bash を止めないため
- Codex では確認の画面を出せず、止めるだけになる。承認した操作は利用者が自分で実行する

## 確かめていないこと

- Claude Code と Codex の実際のセッションで、この hook が確認の画面を出すことと止めること。出力の形は公式の文書と Codex の出力のスキーマに合わせ、テストでは標準入出力だけを確かめた
- Claude Code の `bypassPermissions` のモードで、`"ask"` が確認の画面を出すか
- Codex の hook の信頼が、`hooks.json` の定義を変えたときだけでなく、スクリプトの中身を変えたときにも外れるか

## 参照資料

- [Claude Code の hooks](https://code.claude.com/docs/en/hooks)
- [Codex の hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex の Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [Codex の hook の入出力のスキーマ](https://github.com/openai/codex/tree/main/codex-rs/hooks/schema/generated)
- [Codex の PreToolUse で `ask` を受け付けない実装](https://github.com/openai/codex/blob/8fdf6472955749a731fd9e4b8ffc218e8e80c51d/codex-rs/hooks/src/engine/output_parser.rs)
- [Codex で PreToolUse の hook をツールの処理より前に走らせる実装](https://github.com/openai/codex/blob/8fdf6472955749a731fd9e4b8ffc218e8e80c51d/codex-rs/core/src/tools/registry.rs)
