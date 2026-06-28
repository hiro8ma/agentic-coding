# Hooks

[Hooks](https://code.claude.com/docs/hooks) allow you to run custom commands at various points during Claude Code execution.

## 実装済み Hook

### leak-scan（公開リポのリーク検査）

`leak-scan.py` は PreToolUse(Bash) で動く。`git commit` を含むコマンドのとき、ステージ済み差分の追加行を検査する。API キー、ローカルパス、現職 org / リポ名、個人メールを検出したら exit 2 で commit をブロックし、該当箇所を Claude へ返す。

`.claude/settings.json` で登録済み。git commit 以外のコマンド、JSON でない入力、git 差分が取れない場合は通す。検出スクリプト自身はパターン文字列を含むため、スキャン対象から除外している。

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
