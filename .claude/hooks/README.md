# Hooks

[Hooks](https://code.claude.com/docs/hooks) allow you to run custom commands at various points during Claude Code execution.

## 実装済み Hook

### leak-scan（公開リポのリーク検査）

`leak-scan.py` は PreToolUse(Bash) で動く。`git commit` を含むコマンドのとき、ステージ済み差分の追加行を検査する。API キー、ローカルパス、現職 org / リポ名、個人メールを検出したら exit 2 で commit をブロックし、該当箇所を Claude へ返す。

`.claude/settings.json` で登録済み。git commit 以外のコマンド、JSON でない入力、git 差分が取れない場合は通す。検出スクリプト自身はパターン文字列を含むため、スキャン対象から除外している。

### gh-confirm（レビュー依頼とマージの確認）

`tools/gh-confirm/gh_confirm.py` は PreToolUse(Bash) で動く。`gh pr edit --add-reviewer` / `gh pr create --reviewer` / `gh pr merge` と、同じ操作をする `gh api` の呼び出しを見つけたら、`permissionDecision: "ask"` と、対象の PR と依頼先を並べた理由を返し、利用者に確認の画面を出させる。`&&` / `$( )` / `bash -c` などで包んだ形も見つけ、`echo` の引数やヒアドキュメントの本文では止めない。

`.claude/settings.json` で登録済み。このリポジトリには Renovate の PR が届き、エージェントがマージを頼まれうるため。Codex 向けの入れ方と限界は `tools/gh-confirm/README.md` にある。

### go-build-overwrite-guard（追跡外のファイルを go build で上書きしない）

`go-build-overwrite-guard.py` は PreToolUse(Bash) で動く。`-o` の無い `go build` が、`.` / `./cmd/foo` / `../x` のような相対のパスで1つの main のパッケージを指すとき、書き出す先（基準のディレクトリにパッケージのディレクトリ名、そのディレクトリに go.mod があれば module の最後の要素）を推定する。そこに git で追跡されていない既存のファイルがあれば exit 2 で止め、そのファイルの絶対パスと、`go vet` か `go build -o <別の場所>` を使う書き方を Claude へ返す。基準は入力の `cwd` で、前の `cd <dir> &&` と `-C <dir>` も読む。`-o` がある、パッケージが複数か `...` を含む、`go run` / `go vet` / `go test`、main でないパッケージ、追跡されているファイルか無視の対象のファイル、git のリポジトリの外、サブシェルと変数の展開を含む形は止めない。追跡されていれば git で戻せ、無視の対象はそのリポジトリが成果物として扱っているため。`go build ./...` が main を1つだけ含むときと `-o <ディレクトリ>` も同じ名前のファイルを書くが、この hook は見ない。

このリポジトリの `.claude/settings.json` には登録していない。使うときは、スクリプトを置き、`.claude/settings.json` か `~/.claude/settings.json` の `PreToolUse` に足す（すでに `"matcher": "Bash"` の項目があれば、その `hooks` の配列に足す）。

```bash
mkdir -p ~/.claude/hooks
cp .claude/hooks/go-build-overwrite-guard.py ~/.claude/hooks/
```

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/go-build-overwrite-guard.py\""
          }
        ]
      }
    ]
  }
}
```

## Configuration

Add hooks to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "echo 'Running Bash command...'"
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [{
          "type": "command",
          "command": "npm run lint --fix"
        }]
      }
    ]
  }
}
```

## Hook Events

| Hook | Trigger | Block? |
|------|---------|--------|
| `SessionStart` | セッション開始時 | No |
| `SessionEnd` | セッション終了時 | No |
| `InstructionsLoaded` | CLAUDE.md読み込み後 | No |
| `UserPromptSubmit` | ユーザー入力送信時 | Yes |
| `PreToolUse` | ツール実行前 | Yes |
| `PostToolUse` | ツール実行後 | Yes |
| `PermissionRequest` | 権限要求時 | Yes |
| `SubagentStart` | サブエージェント開始時 | No (inject only) |
| `SubagentStop` | サブエージェント終了時 | Yes |
| `TeammateIdle` | チームメイトがアイドル化前 | Yes (exit 2 = continue) |
| `TaskCompleted` | タスク完了時 | Yes (exit 2 = block) |
| `Notification` | 通知送信時 | No |

## Hook Types

```json
{
  "hooks": [{
    "type": "command",
    "command": "bash scripts/validate.sh"
  }]
}
```

```json
{
  "hooks": [{
    "type": "agent",
    "agentPath": ".claude/agents/code-quality.md"
  }]
}
```

## Agent Teams 用 Hooks

### TeammateIdle — 品質ゲート

```json
{
  "hooks": {
    "TeammateIdle": [{
      "hooks": [{
        "type": "command",
        "command": "bash scripts/validate-teammate.sh"
      }]
    }]
  }
}
```

Exit code 2 でフィードバックを返して作業を継続させる。

### TaskCompleted — テスト検証

```json
{
  "hooks": {
    "TaskCompleted": [{
      "hooks": [{
        "type": "command",
        "command": "npm test"
      }]
    }]
  }
}
```

## Examples

### Notification (macOS)

```json
{
  "hooks": {
    "Notification": [{
      "hooks": [{
        "type": "command",
        "command": "osascript -e 'display notification \"Claude Code\" with title \"Claude Code\" sound name \"Glass\"'"
      }]
    }]
  }
}
```

### Auto-format on edit

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit",
      "hooks": [{
        "type": "command",
        "command": "npx prettier --write {{filePath}}"
      }]
    }]
  }
}
```

### Pre-commit lint

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash(git commit:*)",
      "hooks": [{
        "type": "command",
        "command": "npm run lint"
      }]
    }]
  }
}
```
