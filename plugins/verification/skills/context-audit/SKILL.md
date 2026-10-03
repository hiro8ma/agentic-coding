---
name: context-audit
description: プロジェクトのエージェント向け指示、Skill、接続設定を監査し、コンテキスト肥大化、重複、配置や呼び出し設定の不一致を根拠付きで指摘する。コンテキスト監査、Skill整理、Skillが見つからない／呼ばれない原因の確認で使う。
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
- 起動ディレクトリからルートまでの`.agents/skills/`
- `.codex/config.toml`と`.codex/agents/`
- `.agents/plugins/marketplace.json`と`.claude-plugin/marketplace.json`
- 対象Pluginの`plugin.json` / `.codex-plugin/plugin.json` / `.claude-plugin/plugin.json`

SkillやPluginの探索、導入状態、呼び出し方針、実行環境を調べる場合は、[配置と呼び出し設定の確認](references/skill-deployment.md)を読む
参照先、設定、有効な一覧を根拠として示し、実際の呼び出しを観測していなければ未確認とする

### 2. レイヤーごとに分類する

| レイヤー | 置き場所 | 監査観点 |
|---|---|---|
| Project rules | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | 恒久ルールだけか。長い手順や例が混ざっていないか |
| Task procedures | `SKILL.md`, `.claude/skills/*.md` | 再利用手順か。発動条件 / 探索先 / 有効化状態 / 呼び出し方針が一致しているか |
| External state | MCP, CLI, browser tools | 必要時取得になっているか。出力上限と根拠があるか |
| Delegated work | `.claude/agents/*.md`, `.codex/agents/` | 入力範囲と出力形式が明確か |
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

- **Deployment mismatch** は、正典 / 探索先 / 導入状態 / 有効化状態の不一致
- **Invocation mismatch** は、自動選択 / 明示呼び出し限定 / 無効化の混同
- **Metadata duplication** は、有効な探索先でSkillが重複して初期一覧を消費する状態
- **Unverified package** は、参照先 / 依存関係 / 副作用 / 再配布条件の未確認

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
