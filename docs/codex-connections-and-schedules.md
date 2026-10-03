---
title: "Codexの外部接続と定期実行を分けて設計する"
date: "2026-10-04"
tags: [codex, plugins, apps, MCP, automations, permissions]
---

# Codexの外部接続と定期実行を分けて設計する

Driveの資料を読んで週報を作るなら、接続、作成手順、実行時刻を別々に決める
接続にAppやMCP、手順にSkill、繰り返し実行にスケジュールを使い、関連する機能をPluginとして配布できる
Pluginを入れただけで、資料の読み取りや報告の送信まで許可されたと判断しない

## 作業から必要な機能を選ぶ

| 作業の例 | 接続先で確認すること |
|---|---|
| GitHubのPRをレビューする | リポジトリの閲覧権限と、コメントを投稿する権限 |
| LinearのIssueを整理する | 対象チームと、閲覧か更新か |
| Slackの情報を集める | 読めるチャンネルと、投稿先や送信の承認 |
| NotionやDriveの資料をまとめる | 対象文書の共有範囲と、本文の閲覧か編集か |
| Figmaの仕様を抽出する | 対象ファイルのアクセス権と、使えるツール |
| Sentryのエラーを調べる | 対象プロジェクトと、取得できる情報の範囲 |

実際の操作は、導入するPluginが提供するツールと接続先の権限で確認する
同じサービス名でも、すべての環境で同じ操作が提供されるとは限らない
公開カタログの提供元と、導入済みの接続を分けて見る

## App、MCP、Pluginの関係

MCPはモデルをツールやデータへ接続するプロトコルである
Appという名前で扱う接続もMCPサーバーを利用する場合があり、両者を排他的な方式として分類しない
PluginはSkillや接続設定をまとめて配布する単位である

既存Pluginに必要な機能があれば、同梱内容と権限を確認して利用する
独自ツール、直接設定したい接続、Pluginを使えない実行面では、MCPを直接設定する選択肢がある
常にPluginを優先するのではなく、利用する面、配布する手順、接続の管理方法で選ぶ

共通形式ではMCP接続をルートの`mcp.json`へ置く
登録済みの接続を対応付ける互換用ファイルは`.app.json`で、マニフェストから参照する
`app.json`を置けば自動的に認証が済む仕組みではない

## 設定と権限を照合する

表示用の`Read` / `Write`は、実効権限を付与する設定ではない
接続先サービスのアクセス権、認証で付与されたスコープ、アクション制御、ホストの承認設定を照合する
どのアカウントで処理するかも確認し、個人の接続と共有アカウントの接続を同一視しない

PluginがMCPの起動設定を供給する場合、同じ接続を`[mcp_servers.*]`へ重複登録する必要はない
同梱MCPの有効化やツール承認を調整する場合は、`plugins.<plugin>.mcp_servers.<server>`を使う
追加の認証や実行環境の準備が要る場合は、導入後に確認する

```toml
[plugins."example@sample-market".mcp_servers.docs]
enabled = true
default_tools_approval_mode = "prompt"
enabled_tools = ["read", "search"]
```

これは設定の形を示す例であり、実在する接続の権限や動作を検証したものではない
Skillに投稿や更新の手順があっても、操作の承認が済んだことにはならない

## 利用する環境を確認する

| 環境 | Plugin | 直接設定するMCP |
|---|---|---|
| ChatGPTのWeb | 利用できるPluginの接続を使う | 通常のホスト型Workはローカルのconfig.tomlを読まない |
| デスクトップアプリのCodex | 対応 | 対応 |
| Codex CLI | Plugin browserに対応 | config.tomlやcodex mcpで設定 |
| IDE拡張 | 現行のPlugin説明では非対応 | 対応 |

ローカルのデスクトップ、CLI、IDEは、同じCodexホストのMCP設定を共有する
Web側の接続や認証まで、その共有に含まれるとは判断しない
Work Cloudのローカルアクセスは別の実行形態なので、そのモードの接続条件を確認する

直接のMCP設定を調べるときは、`codex mcp list`で設定済みサーバーを、TUIの`/mcp`で有効な接続を確認する
STDIOはローカルプロセスを起動し、Streamable HTTPはURLへ接続する
HTTPの認証にはBearerトークンやOAuthがあり、設定の共有と認証済みの状態を分けて確認する

## ローカルとクラウドの定期タスクを分ける

Skillは作業手順を、スケジュールは開始するタイミングを持つ
繰り返す処理はSkillに置き、タスクには入力、利用する接続、時刻や開始条件、終了条件を記述する
定期実行でも、送信や更新の権限はタスクごとに設計する

| 実行形態 | 使える入力と実行条件 |
|---|---|
| デスクトップのローカルプロジェクト | ローカルのディレクトリやworktree。マシン、アプリ、対象フォルダが利用可能であること |
| Webのタスク | アップロードした資料や接続済みツール。ローカルフォルダを直接参照しない |
| Team Tasks | チームのサービスアカウントと設定済み接続。利用者個人の認証とは区別する |

CLIとIDEにはスケジュール管理画面がなく、Webかデスクトップで設定する
ローカル常駐の条件を、クラウド側のタスクにも一律に当てはめない
予定を設定する前に通常の対話で同じ入力と手順を試し、実行を開始した後も最初の結果を確認する

## このリポジトリでの確認

`context-audit`でSkillの導入、Pluginの接続設定、利用する実行面を照合できる
実効権限や定期タスクの稼働を示す情報がなければ、設定から確認できる範囲と未確認事項を分けて報告する
この文書の例は導入や定期実行の依頼ではなく、設定を検討するときの参照例である

## 出典

- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [接続と権限の関係](https://learn.chatgpt.com/docs/enterprise/apps-and-connectors#understand-the-capability-chain)
- [Scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
