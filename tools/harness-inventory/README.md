# harness-inventory

リポジトリと利用者の設定を読み、コーディングエージェントのハーネスの部品を guide / sensor と computational / inferential の表に棚卸しする
指示ファイルの規則のうち、登録された決定的な sensor の名前が出るものの割合も出す
Python 3.9以降の標準ライブラリだけで動く

## なぜ作ったか

エージェントはモデルとハーネスでできている
ハーネスはモデルの外の仕組みの全部で、ループ / 道具 / 文脈（AGENTS.md、CLAUDE.md、skill）/ 状態 / 壁と検査（permissions、sandbox、hook、CI、linter）に分かれる

Birgitta Böckeler 氏は、ハーネスの部品を2つの軸で分ける

| 軸 | 値 | 中身 |
|---|---|---|
| いつ効くか | guide | 行動の前に、行動を導く（feedforward） |
| | sensor | 行動の後に結果を確かめ、直させる（feedback） |
| 誰が判断するか | computational | 決定的な検査。テスト / linter / 型検査 |
| | inferential | LLM の判断。AI のコードレビュー / LLM as judge |

ハーネスエンジニアリングは、文章の規則で守らせて再発した失敗を、決定的な sensor に移す作業である
移したかどうかを確かめるには、規則と sensor を並べて見る必要がある

同じリポジトリの `tools/rule-loops` は、規則の文面が hook / CI / lint の語に触れるかを見る
ただし settings.json や hook の設定は読まない
「CI が緑になってから出す」のような手順の文も仕組みに数え、hook で止めている規則でも文面に書いていなければ数えない

この道具は逆に、設定の側から部品を数える
そのうえで、規則の本文か Why に、実際に登録された sensor の名前が出るかを見る

## 読むもの

| 部品 | プロジェクト（ROOT） | 利用者（`--user`） |
|---|---|---|
| 指示ファイル | `AGENTS.md` / `AGENTS.override.md` / `CLAUDE.md` / `CLAUDE.local.md` / `GEMINI.md`（6段下まで）/ `.claude/CLAUDE.md` / `.claude/rules/**/*.md` | `~/.claude/CLAUDE.md` / `~/.claude/rules/**/*.md` / `~/.codex/AGENTS.md` / `~/.codex/AGENTS.override.md` / `~/.gemini/GEMINI.md` |
| skill | `.claude/skills/*/SKILL.md` / `.agents/skills/*/SKILL.md` | 左に加えて `~/.codex/skills/*/SKILL.md` |
| コマンド | `.claude/commands/**/*.md` | 左に加えて `~/.codex/prompts/*.md` |
| サブエージェント | `.claude/agents/*.md` / `.codex/agents/*.toml` | 同じ |
| hook / permissions / sandbox / plugin | `.claude/settings.json` / `.claude/settings.local.json` | `~/.claude/settings.json` |
| Codex の設定 | `.codex/config.toml`（sandbox_mode / approval_policy / approvals_reviewer / mcp_servers）/ `.codex/hooks.json` / `.codex/rules/*.rules` | 同じ |
| MCP サーバー | `.mcp.json` | `~/.claude.json` の `mcpServers` |
| CI | `.github/workflows/*.yml` | — |
| linter と pre-commit | golangci-lint / ruff / eslint / prettier / biome / clippy / rustfmt / markdownlint / textlint / mypy / shellcheck / staticcheck の設定（6段下まで）、`pyproject.toml` の `[tool.ruff` と `[tool.mypy`、`.pre-commit-config.yaml` / lefthook / `.husky/` | — |

下の階層を読むときは、`.` で始まるディレクトリと `node_modules` / `vendor` / `dist` / `build` / `target` / `venv` / `coverage` / `__pycache__` / `fixtures` / `testdata` を飛ばす
同じファイルへのリンク（`~/.codex/AGENTS.md` が `~/.claude/CLAUDE.md` を指すなど）は、規則を1回だけ数える

## 2x2 の分け方

| 部品 | 区分 | 分けた理由 |
|---|---|---|
| 指示ファイル / rules / skill / コマンド / サブエージェント | guide / inferential | モデルが読んで行動を決める |
| 名前に review / verify / check / audit / judge / eval / qa などの語があるサブエージェント | sensor / inferential | 結果を LLM が確かめる役。名前の語だけで決めた目安 |
| SessionStart / UserPromptSubmit / SubagentStart / PreCompact / PostCompact / InstructionsLoaded などの hook | guide | 行動の前に文脈を足す |
| PreToolUse / PostToolUse / PostToolUseFailure / PermissionRequest / PermissionDenied / Stop / SubagentStop / TeammateIdle / TaskCreated / TaskCompleted / PostToolBatch / ConfigChange の hook | sensor | 道具の呼び出しか答えを見てから、止めるか直させる |
| Notification / StopFailure / SessionEnd / MessageDisplay の hook | 2x2 の外（知らせる） | 通知と記録で、行動を変えない |
| hook の型 | `command` / `http` / `mcp_tool` は computational、`prompt` / `agent` は inferential | Claude Code の hooks の説明で、LLM を使う型は prompt と agent |
| permissions の ask / deny、Codex の execpolicy の prompt / forbidden | sensor / computational | 道具の呼び出しを、実行の前に決まった規則で確かめる |
| `defaultMode` が `auto` | sensor / inferential | 別のモデル（分類器）が道具の呼び出しを確かめる |
| Codex の `approvals_reviewer` が `user` 以外 | sensor / inferential | 承認の判断をモデルに任せる設定として数える |
| permissions の allow、execpolicy の allow | 2x2 の外（検査を飛ばす許可） | 確認を出さずに通す |
| sandbox / MCP サーバー / plugin | 2x2 の外 | 壁と道具で、guide でも sensor でもない |
| `pull_request` / `pull_request_target` / `merge_group` で動く CI | sensor | PR の段階で結果を返す |
| それ以外の CI（push / 定期 / 手動 / ほかの workflow から呼ばれる） | 2x2 の外（PR で動かない CI） | デプロイや掃除のように、結果を確かめないものが多い |
| CI の中身 | `anthropics/claude-code-action` / `openai/codex-action` / `run-gemini-cli` / `claude -p` / `codex exec` / `gemini -p` があれば inferential、なければ computational | |
| linter と pre-commit | sensor / computational | 補足の欄に、CI / hook / pre-commit のどこに名前が出るかを書く |

## 規則と sensor の結び方

規則の単位と Why の取り方は `tools/rule-loops` と同じ（`rule_loops.py` を読み込んで使う）

次の名前を「登録された決定的な sensor」とする

| sensor | 名前 |
|---|---|
| sensor のイベントの、computational な hook | コマンドの中のスクリプトのファイル名（拡張子なし）と、`tools/` などでない親のディレクトリ名。スクリプトがなければ `npx` のパッケージ名か最初の語 |
| permissions の ask / deny | 括弧の中（`Bash(gh pr merge:*)` なら `gh pr merge`） |
| execpolicy の prompt / forbidden | `pattern` の先頭の文字列を空白でつないだもの（2語以上） |
| PR で動く computational な CI | workflow のファイル名（`lint.yml`） |
| linter と pre-commit | 道具の名前。linter は CI / hook / pre-commit のどこかに名前が出るものだけ |

規則の本文か Why に名前が出れば「名前が出る規則」に数える

- 大文字と小文字、`_` と `-` を区別しない
- 英数字と `-` の境界で区切る（`push-guard` は `push-guardian` に当たらない）
- 4文字より短い名前と、`hook` / `main` / `default` / `python3` のような一般の語は使わない
- 見出しの節の規則は、節の中の箇条書きの行を除いて読む。箇条書きと節で同じ名前を2回数えないため
- 複数のルートを渡したときは、全部のルートの sensor を合わせて結ぶ。利用者の設定とリポジトリを一緒に渡すと、その組み合わせで効くハーネスになる

名前が出ることは、その sensor がその規則の失敗を止めることを示さない
逆に、規則を止めている sensor でも、規則の文面にその名前がなければ数えない
規則の本文か Why に sensor の名前を書いておくと、規則と仕組みの対応を後から辿れ、この道具でも数えられる

## 確かめること

部品のうち、決定的に確かめられる誤りを出す

| 出すもの | 根拠 |
|---|---|
| 道具のイベントの matcher が、英数字 / `_` / `-` / 空白 / `,` / `\|` 以外を含み、さらに空白 / 引用符 / `=` / `&` / `!` / `<` / `>` を含む（`tool == "Bash"` など） | Claude Code は、許された文字だけの matcher を名前の完全一致として、それ以外を正規表現として読む。道具の名前にこれらの文字は入らないので、どの道具にも一致しない |
| matcher を読まないイベント（Stop / UserPromptSubmit など）の matcher | 黙って無視される |
| 道具のイベント以外の hook の `if` | `if` は道具のイベントでしか読まれず、その hook は動かない |
| hook のスクリプトが見つからない | `$HOME` / `~` / `$CLAUDE_PROJECT_DIR` / プロジェクトの相対のパスを解いて確かめる。ほかの変数を含むものと、利用者の設定の相対のパスは「確かめられない」とする |
| skill のディレクトリに、`SKILL.md` の無い項目がある | skill は `<名前>/SKILL.md` の形でないと読まれない |
| プロジェクトか local の設定の `defaultMode` が `auto` / `bypassPermissions` | この2つは利用者の設定などでしか効かない |
| `disableAllHooks` が true / JSON として読めない設定 | |

## 出力

fixture に流した出力の先頭は次のとおり
この後に「確かめること」「部品」「hook」「許可と sandbox」の表が続く

```text
# harness-inventory

読んだルート2件（~ / tools/harness-inventory/fixtures/repo）

## guide / sensor と computational / inferential

| | computational（決定的な検査） | inferential（LLM の判断） |
|---|---|---|
| guide（行動の前に導く） | hook 1本 | 指示ファイル2件 / skill 2件 / コマンド1件 / サブエージェント1件 |
| sensor（行動と結果を確かめる） | execpolicy の prompt と forbidden 1件 / permissions の ask と deny 2件 / CI 1本 / linter（ruff）1件 / hook 3本 | auto モードの分類器1件 / 承認をモデルに任せる設定1件 / レビュー役のサブエージェント1件 / CI 1本 / hook 1本 |

2x2 の外の部品は 検査を飛ばす許可（allow）5件 / plugin 1件 / MCP サーバー2件 / sandbox 1件 / PR で動かない CI 1本 / 知らせる hook 1本

## 規則と決定的な sensor

規則7件（指示ファイル2件。数え方は tools/rule-loops と同じ）
登録された決定的な sensor の名前が、本文か Why に出る規則4件（57.1%）
文章では hook / CI / lint などに触れるが、登録された sensor の名前が出ない規則1件
再発した規則（Why の日付が2つ以上）3件のうち、sensor の名前が出るもの1件

| 場所 | 規則 | sensor |
|---|---|---|
| ~/.claude/CLAUDE.md:3 | Ask before gh pr merge. The execpolicy … | execpolicy の prompt「gh pr merge」 / permissions の ask「Bash(gh pr merge:*)」 |
| tools/harness-inventory/fixtures/repo/AGENTS.md:5 | Do not commit secrets. The secret-guard… | hook（PreToolUse）「secret_guard」 |
| tools/harness-inventory/fixtures/repo/AGENTS.md:10 | Lint | linter「ruff」 |
| tools/harness-inventory/fixtures/repo/AGENTS.md:18 | gh pr merge needs the user's approval e… | execpolicy の prompt「gh pr merge」 / permissions の ask「Bash(gh pr merge:*)」 |

### 再発していて、sensor の名前が出ない規則

- ~/.claude/CLAUDE.md:4「Write the title and the URL when you me…」
- tools/harness-inventory/fixtures/repo/AGENTS.md:7「Keep commit messages under 72 characters」
```

hook の表には、コマンドごとに登録されたイベントを並べる
同じコマンドが多くのイベントに付いていれば、通知や記録の転送であることが多い
2x2 の数は hook の役割をイベントで決めるので、こうした転送も sensor の hook に数える

`--json` では、`quadrants`（2x2 の各欄）/ `outside` / `parts` / `hooks` / `permissions` / `instruction_files` / `rules` / `sensors` / `unnamed_sensors` / `findings` を出す
`rules` の `backed_ratio` が、名前が出る規則の割合

## 使う

```bash
python3 tools/harness-inventory/harness_inventory.py .
python3 tools/harness-inventory/harness_inventory.py --user .
python3 tools/harness-inventory/harness_inventory.py --user
python3 tools/harness-inventory/harness_inventory.py --json --user . > harness.json
```

| 引数 | 動き |
|---|---|
| `ROOT` | リポジトリのルート。何個でも渡せる。ホームを渡すと利用者の設定として読む |
| `--user` | 利用者の設定（ホームの `.claude` / `.codex` など）も読む |
| `--home DIR` | ホームとして読むディレクトリ。既定は利用者のホーム |
| `--json` | JSON で出す |

終了コードは0
読めないディレクトリを渡したときと、ROOT も `--user` も無いときだけ2

## テスト

```bash
python3 -m unittest discover -s tools/harness-inventory
```

fixture は合成のリポジトリとホームで、実在の組織や人の情報と、本物の鍵は含まない
24件のテストが Python 3.9.6と3.15.0で通り、ruff check と ruff format で確かめた

次のように実装を壊すと、テストが落ちることも確かめた
壊した実装は、リポジトリの外の複製で試した

| 壊したところ | 落ちたテスト |
|---|---|
| 式の形の matcher を見逃す | matcher の誤り |
| Stop を sensor のイベントから外す | イベントと型 / fixture の2x2 / 2x2 の外 |
| agent の型を LLM に数えない | イベントと型 |
| push の CI を PR の CI に数える | fixture の2x2 / 2x2 の外 / 起動の条件 / PR の CI だけを sensor にする |
| どこからも呼ばれない linter も sensor にする | linter は呼ばれるものだけ |
| 節の規則が箇条書きの行も読む | 節の規則は箇条書きを数えない |
| `_` と `-` を同じに読まない | 名前と規則 / fixture の規則 / スクリプトの名前 / JSON と Markdown |
| 名前の境界を外す | 名前と規則 |
| `$CLAUDE_PROJECT_DIR` を解かない | スクリプトの名前 |
| 存在するほうのスクリプトを選ばない | スクリプトの名前 |
| リンクの指示ファイルを2回読む | リンクの指示ファイル |
| `fixtures` を読み飛ばさない | 読み飛ばすディレクトリ |
| 導くイベントの hook も sensor の名前にする | sensor のイベントの hook だけ |
| permissions の `:*` を外さない | permissions の名前 / fixture の規則 |
| config.toml の複数行の配列を読み飛ばさない | config.toml |
| `.rules` のコメントの行を読む | execpolicy |
| `SKILL.md` の無い項目も skill に数える | fixture の2x2 / SKILL.md の無い項目 |

## 限界

- 規則と sensor は名前でしか結ばない。名前が出ても、その sensor がその規則を止めるとは限らない（ビルドの workflow の場所を説明しただけの規則も数える）
- hook の中身は読まない。sensor のイベントに付いた hook が、検査をしているか、記録を転送しているだけかは分からない
- plugin の中の hook と skill、managed の設定、`~/.claude.json` のプロジェクトごとの MCP サーバー、Codex の profile ごとの設定、メモリのディレクトリは読まない
- config.toml は、最上位の1行の値と表の見出しだけを読む。値の中の括弧の数で複数行の配列を飛ばすので、文字列の中に括弧があると読み違える
- CI の起動の条件と中身は、YAML を解かずに行の形で読む。`npm run lint` のように別のファイルを通して linter を呼ぶ CI は、「名前が出ない」になる
- レビュー役のサブエージェントは名前の語だけで決める

## 確かめていないこと

- 名前が出る規則が、実際にその sensor で止まる規則かの正しさ。正解を付けたデータで、適合率と再現率を測っていない
- Codex の `approvals_reviewer` の値の一覧。手元の設定の `auto_review` だけを見た
- Gemini CLI の設定（`.gemini/settings.json`）は読まない
- このリポジトリと手元の利用者の設定で試した。ほかの形のリポジトリでの動きは確かめていない

## 参照資料

- Birgitta Böckeler「[Harness engineering for coding agent users](https://martinfowler.com/articles/harness-engineering.html)」（martinfowler.com、2026-04-02）
- [Claude Code の hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code の permissions](https://code.claude.com/docs/en/permissions)
- [Claude Code のメモリと `.claude/rules/`](https://code.claude.com/docs/en/memory)
- [AGENTS.md](https://agents.md/)
