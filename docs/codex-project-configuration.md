---
title: "Codexのプロジェクト設定とAGENTS.md"
date: "2026-09-27"
tags: [codex, configuration, agents-md, sandbox, project-instructions]
---

# Codexのプロジェクト設定とAGENTS.md

Codexでは、実行方法を決める`.codex/config.toml`と、作業時の指示を渡す`AGENTS.md`を分けて管理する
前者はモデル、承認、サンドボックスなどの設定で、後者はビルド手順、設計規約、完了条件などの文章である
設定の優先順位と指示の探索順序は別の仕組みなので、同じ階層に置いても同じようには上書きされない

## プロジェクトごとの設定

ユーザー共通の既定値は`~/.codex/config.toml`に置く
特定のリポジトリやサブディレクトリだけで使う値は、その場所の`.codex/config.toml`に置く

```text
my-project/
├── .codex/config.toml
└── packages/api/.codex/config.toml
```

```toml
# my-project/.codex/config.toml
model = "gpt-6-sol"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
model_reasoning_effort = "high"
```

Codexはプロジェクトルートから現在の作業ディレクトリまで設定を読み、同じキーは作業ディレクトリに近いファイルの値を使う
この例で`packages/api`から起動すると、そこにある設定がルートの設定を上書きする
ただしCLIのフラグと`--config`はプロジェクト設定より優先され、組織が`requirements.toml`で強制する条件も超えられない
利用するモデルや設定キーは更新されるため、設定を追加するときは公式の設定リファレンスを確認する

Codexは信頼済みプロジェクトだけでプロジェクト内の`.codex/`設定を読み込む
信頼していないプロジェクトでは、その場所の設定、Hooks、Rulesの層が無視される
信頼状態はユーザー側の設定に保存される

```toml
# ~/.codex/config.toml
[projects."/absolute/path/to/my-project"]
trust_level = "trusted"
```

リポジトリの`.codex/config.toml`へ秘密情報や個人の絶対パスを書かない
信頼する前に、リポジトリの設定と実行されるHooksを確認する

## 作業時の指示

`AGENTS.md`には、Codexへ繰り返し伝える作業上の規約を書く
たとえばディレクトリ構成、ビルドとテストのコマンド、変更してはいけない境界、完了条件を短く記す
長いタスク別手順はSkillに分け、規約ファイルを際限なく増やさない

Codexはまず`CODEX_HOME`内の`AGENTS.override.md`または`AGENTS.md`を確認する
`CODEX_HOME`を変えていなければ、この場所は通常`~/.codex/`である
次にプロジェクトルートから現在の作業ディレクトリまで各階層をたどり、見つけた指示を上位から順に結合する
同じディレクトリでは`AGENTS.override.md`が`AGENTS.md`より優先され、1つだけ読み込まれる

```text
my-project/
├── AGENTS.md
└── packages/api/AGENTS.md
```

`packages/api`から起動すると、グローバル、ルート、`packages/api`の指示がこの順で追加される
下位の指示は上位より後に入り、同じ対象についてより具体的な規約を示せる
ただしリポジトリの指示は、現在のユーザー指示や上位のシステム制約を上書きする権限ではない

Codexが読み込む指示の合計は`project_doc_max_bytes`で制限され、既定値は32 KiBである
上限に達すると残りのファイルは追加されない
階層別に分けると無関係な作業へ指示を渡さずに済むが、同じ作業ディレクトリで読み込む合計が上限を超えるなら、内容を削るか上限設定を見直す必要がある

Codex CLIの`/init`は現在のディレクトリへ`AGENTS.md`のひな型を作る
生成後は実際のコマンドと規約に合わせて編集し、新しいセッションでどの指示が読まれたか確認する

## このリポジトリでの使い分け

このリポジトリの`AGENTS.md`はリポジトリ全体の作業規約を持つ
細かい設計指針は`.claude/`と`docs/`、繰り返す手順は`skills/`に置いている
Codex固有のモデルや承認設定が必要になったときだけ`.codex/config.toml`を追加し、作業手順を設定ファイルへ混ぜない

## 参照資料

- [Codexの設定の基本](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Codexの設定リファレンス](https://learn.chatgpt.com/docs/config-file/config-reference)
- [AGENTS.mdの探索と階層化](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Codexの`/init`コマンド](https://learn.chatgpt.com/docs/developer-commands)
