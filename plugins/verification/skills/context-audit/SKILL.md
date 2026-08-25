---
name: context-audit
description: プロジェクトの CLAUDE.md / AGENTS.md / Skills / Commands / MCP / Hooks / Subagents を点検し、コンテキスト肥大化・重複・責務混在を減らす。「コンテキスト監査」「context audit」「CLAUDE.mdを整理」「Skillsに切り出す」等のキーワードで起動。
---

# コンテキスト監査スキル

プロジェクトのエージェント向けコンテキストを点検し、常時ルール、タスク手順、外部接続、作業分離、決定論的検査の責務を整理する。

## 手順

### 1. 対象ファイルを確認する

存在するものだけを読む。

- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- `.claude/commands/`
- `.claude/skills/`
- `skills/`
- `.claude/agents/`
- `.claude/mcp/`
- `.claude/hooks/`
- `.claude/settings*.json`
- `.gitignore`

### 2. レイヤーごとに分類する

| レイヤー | 置き場所 | 監査観点 |
|---|---|---|
| Project rules | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | 恒久ルールだけか。長い手順や例が混ざっていないか |
| Task procedures | `SKILL.md`, `.claude/skills/*.md` | 再利用手順になっているか。発動条件が明確か |
| External state | MCP, CLI, browser tools | 必要時取得になっているか。出力上限と根拠があるか |
| Delegated work | `.claude/agents/*.md` | 入力範囲と出力形式が明確か |
| Deterministic gates | hooks, scripts, CI | LLMに任せるべきでない検査を機械化しているか |

### 3. 問題を分類する

以下の分類で指摘する。

- **Overloaded rule**: ルールファイルに長い手順・テンプレート・例が入りすぎている
- **Skill candidate**: Skill に切り出すべき繰り返し手順がある
- **Weak trigger**: Skill の `description` が発動条件を十分に含んでいない
- **Missing reference split**: `SKILL.md` が長く、詳細を `references/` に逃がせる
- **Tool context bloat**: MCP / CLI / ブラウザ出力が長く、要約・上限・根拠がない
- **Subagent mismatch**: 重い調査をメイン会話で抱えている
- **Scriptable gate**: secret scan、format、lint、validation などを LLM 判断に任せている
- **Ignored noise missing**: `node_modules`、`dist`、巨大ログ、生成物の除外が弱い

### 4. 改善案を出す

出力は次の形式にする。

```markdown
## Findings

| Severity | Type | File | Issue | Recommendation |
|---|---|---|---|---|

## Proposed Moves

| Move | From | To | Reason |
|---|---|---|---|

## Minimal Patch Plan

1. ...
2. ...
3. ...

## Residual Risk

- ...
```

### 5. 変更する場合

ユーザーが実装も求めている場合は、次の優先順で小さく編集する。

1. READMEやdocsの索引更新
2. Skillの追加・分割
3. ルールファイルから長い手順を削って参照へ置換
4. hooks/scriptsの追加
5. MCP出力設計の修正

既存のルールを消すときは、同じ内容が移動先で読める状態にしてから削る。
