---
title: "CodexのPluginを作り、カタログから共有する"
date: "2026-10-03"
tags: [codex, plugins, skills, marketplace, mcp, hooks]
---

# CodexのPluginを作り、カタログから共有する

日本語ライティングやレビューのSkillを別の環境でも使うなら、関連するSkillをPluginにまとめて配布できる
PluginはSkill、MCP接続の設定、Hooksなどを1つの単位として導入するためのパッケージである
外部サービスの認証と操作の権限は、利用する接続先で別に設定する

## 作業と配布の役割を分ける

| 仕組み | 担当すること | 配置や設定の例 |
|---|---|---|
| AGENTS.md | 作業場所に適用する方針を示す | リポジトリと各ディレクトリのAGENTS.md |
| Skill | 特定の作業手順と判断基準を示す | `.agents/skills/` / `$HOME/.agents/skills/` |
| App / MCP | 外部データや操作へ接続する | 登録済みの接続 / `[mcp_servers.*]` / Plugin内の`mcp.json` |
| Hook | 対応するイベントで処理を実行する | Plugin内の`hooks/hooks.json` |
| Plugin | 関連する機能をまとめて配布する | Pluginルートの`plugin.json` |
| サブエージェント | 入力を限定して別コンテキストへ作業を委譲する | 依頼時の指示 / `.codex/agents/` |
| Automation | 指定したタイミングから作業を開始する | デスクトップアプリのスケジュール |

たとえば文章を作る手順はSkillに、毎週の実行はAutomationに、独立した読者レビューはサブエージェントに任せられる
これらを全部Pluginへ入れる必要はなく、同じ利用者へ配る構成要素をまとめる
自然言語の指示と、認可や検査結果による操作の遮断も別に設計する

## 最小のPluginを作る

新規のパッケージは、ルートの`plugin.json`でAgent Pluginsのスキーマを指定する
ルートの`skills/`は自動検出されるため、共通形式のマニフェストに`skills`フィールドは不要である

```text
plugins/writing-ja/
├── plugin.json
├── .claude-plugin/plugin.json
└── skills/
    └── japanese-tech-writing/
        └── SKILL.md
```

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "writing-ja",
  "version": "1.1.0",
  "description": "日本語の技術文書を書くための手順"
}
```

既存の`.codex-plugin/plugin.json`も互換形式として使える
OpenAI固有の表示、登録済み接続への対応付け、Hooksの設定は、共通形式の`extensions.com.openai`へ置く
このオブジェクトを指定すると、互換マニフェストの設定とは統合されない

登録済み接続の対応付けに使う互換用ファイルは`.app.json`である
共通形式でMCPサーバーを同梱する場合は、ルートの`mcp.json`にスキーマと各サーバーのtransportの`type`を記述する
`.mcp.json`を名前だけ変えて共通形式に移行したことにはならない

## 教材の互換形式でレビューPluginを作る

教材のreview-prは、互換形式のマニフェストを使う例である
ディレクトリごと別のGitリポジトリへ移せる[サンプル](../examples/codex-ci/review-pr-plugin/)を用意した
READMEは導入と利用、marketplace.jsonは発見と配布、plugin.jsonは構成、SKILL.mdはレビューの判断基準を担当する

```text
review-pr-plugin/
├── README.md
├── .agents/plugins/marketplace.json
└── plugins/review-pr/
    ├── .codex-plugin/plugin.json
    └── skills/review/SKILL.md
```

```json
{
  "name": "review-pr",
  "version": "0.1.0",
  "description": "変更の根拠を確認して、修正が必要な不具合を報告する",
  "skills": "./skills/"
}
```

このskillsフィールドは互換形式の指定で、ルートのportable形式へそのまま写さない
Plugin名とSkill名は別で、review-prとreviewの組み合わせはreview-pr:reviewとなる
この例はSkillだけを含み、Apps、MCPサーバー、Hooksは追加しない

公式資料はPlugin Creatorによる作成も案内しているが、利用できるかはその環境の一覧で確認する
今回のセッションにはplugin-creatorがなかったため、サンプルは手作業で作成した
validate_plugin.pyも、実在するスクリプトを確認してから利用する
JSONと参照先の検査、ホストでの発見、Skillの発動、レビュー結果の品質は別々に確認する

## カタログへ登録する

`.agents/plugins/marketplace.json`は、リポジトリで利用できるPluginの一覧である
このリポジトリでは`business-tools`、`verification`、`writing-ja`を登録している
`source.path`は`.agents/plugins/`からではなく、マーケットプレイスのルートから解決する

```json
{
  "name": "hiro8ma-marketplace",
  "plugins": [
    {
      "name": "writing-ja",
      "source": { "source": "local", "path": "./plugins/writing-ja" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

カタログへの登録と、インストールや有効化は別の段階である
この例の`AVAILABLE`は候補として提供する設定で、自動インストールの指定ではない
接続やHooksを持たないPluginに、認証や実行処理を追加する設定でもない

## 導入と有効化を確認する

Codex CLIでは、リポジトリのルートをローカルの取得元として登録してから候補を確認する
手元のCLI 0.160.0では、カタログを配置しただけでは候補一覧に出なかった

```bash
codex plugin marketplace add .
codex plugin marketplace list --json
codex plugin list --marketplace hiro8ma-marketplace --available --json
```

別の作業場所からGitのカタログを登録する場合は、次のコマンドを使う

```bash
codex plugin marketplace add hiro8ma/agentic-coding --ref main
```

利用するローカルマーケットプレイスのPluginを、信頼済みプロジェクトの`.codex/config.toml`で明示できる
`@`を含むキーは引用符で囲み、`enabled`は省略時の動作に依存せず明示する

```toml
[plugins."writing-ja@hiro8ma-marketplace"]
enabled = true
```

`enabled = false`にしても、設定済みPluginのファイルがカタログ更新時に取得されることはある
組織管理のPluginには別の管理状態があるため、この設定で組織の導入ポリシーを上書きするとは限らない

通常のインストール先は`~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`で、ローカルPluginの版部分は`local`となる
実行時はキャッシュ側を読むため、元フォルダの変更だけで稼働中の版が変わったと判断しない
インストール後は新しいセッションで一覧と最小の作業を確認する
Hooksを追加した場合は、実行環境のスクリプト配置とHook定義の信頼確認も必要になる

## GitHubでの共有と公式Directoryへの公開

GitHubのMarketplaceを登録して使う配布と、ChatGPTとCodex共通の公開Directoryへの提出は別の手続きである
現在の公開手順は、提出用ZIPのアップロード、自動検査、レビュー提出、承認後の公開として案内されている
教材の「公開管理機能は今後予定」を、現在も使える説明としては残さない
今回、公開ポータルへのログインや提出は行っていない

GitHubから配る場合は、受け手が確認した版を登録して導入する
--ref mainはブランチの選択であり、同じコミットへ固定したことにはならない
再現可能な配布には確認済みのタグやコミットを指定し、更新と導入後のキャッシュを確認する
チームの判断基準をCIへ渡す方法は[Codex ActionとSkill](codex-skills-in-ci.md)を参照する

## コード以外の作業にも使う

仕様書や表を確認する場合も、何を入力として何を返すかを依頼に書く
次は仕様書の不整合を調べる依頼例である

```text
Goal
仕様書と項目定義の不整合を、判断できる根拠付きで列挙する

Context Pointers
docs/specification.mdとdocs/fields.mdを参照する

Constraints
本文の修正は行わず、記載の不一致と仕様未確定を分ける

Done When
各指摘に両文書の該当箇所と不一致の内容があり、未確認事項が明示される
```

同じ確認を繰り返すようになったら手順をSkillへ移し、関連するSkillをPluginにまとめられる
自作前には共有のPlugins Directoryや既存Skillを確認し、必要な差分だけを実装する
単独Skillのローカル利用と`openai/skills`も、現行の公式ドキュメントで案内されている

## このリポジトリでの検証範囲

共通形式のマニフェストとCodex用カタログを追加し、既存の同じ`skills/`を参照する
Claude Code用のマニフェストとカタログは別の入口として使う
Pluginの発見と、各Skillの実行互換性は分けて確認する
特定ツール名や作業ディレクトリに依存するSkillの実行は、マニフェストの追加だけでは検証できない

## 出典

- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [Submit plugins](https://developers.openai.com/plugins/deploy/submission)
- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
