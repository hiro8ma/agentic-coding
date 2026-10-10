---
title: "SkillとPluginを導入し、呼び出しと成果を確かめる"
date: "2026-10-11"
tags: [codex, skills, plugins, evaluation]
---

# SkillとPluginを導入し、呼び出しと成果を確かめる

インストール成功だけでは、そのSkillが依頼に使われたことも、成果が改善したことも分からない
配置、認識、呼び出し、外部認証、成果の確認を分ける
次の手順と依頼例は、ユーザー提供教材「Skills / Pluginsの実践活用」を公式資料と照合して整理したものである
教材にある`chatgpt-content-reference`のコードや画像は取得できず、例を復元したものではない

## 導入するものに応じて入口を選ぶ

| 導入物 | 内容 | 導入の入口 |
|---|---|---|
| 単独Skill | 作業手順と判断基準、任意の補助ファイル | skill-installer、探索先への配置 |
| CLIプログラム | 実際に処理を行う実行コード | npm、Homebrew、go install、pipxなど |
| Plugin | Skillと接続などをまとめたパッケージ | Pluginの一覧、codex plugin addなど |
| 外部サービスの接続 | アカウントと権限 | サービスの認証と接続設定 |

Skill利用頻度を調べるdeadskillsやgocccはCLIプログラムで、名前をskill-installerに渡して導入するものではない
Codex Usage TrackerはPythonの実行プログラムとCodex Pluginをそれぞれ導入する
使い方のSkillが別途配布されていれば、そのSkill部分をskill-installerで取得できる
実行プログラムや依存関係の導入まで済んだとは扱わない

## 既存Skillを導入する

Codexの単独Skillは、`$skill-installer`へ名前またはGitHub上の対象ディレクトリを指定して導入できる
公式資料の例は次のとおりで、ここでは実際のインストールは行わない

```text
$skill-installer linear
```

この例はLinearの作業手順を持つ単独Skillの導入である
Linear Pluginの導入や、Linearへの外部接続の完了を意味しない

導入前には、`SKILL.md`の対象範囲と操作、参照ファイル、スクリプトの通信先、認証情報の扱い、書き込み先を確認する
提供元、更新状況、ライセンスも確認する
スクリプトがないSkillでも、本文がツールによる外部操作を指示することはある
詳しい確認基準は[Skillの再利用と移植](skill-reuse-and-portability.md)にある

現在の公式資料では、Codexは新しいSkillと変更を自動検出する
一覧に現れない場合は再起動し、探索先、有効化設定、同名Skillの重複を確認する
`skill-installer`の既定の導入先と公式資料が示すユーザー探索先は、同じ表記とは限らない
導入結果の実パスと、今の環境の一覧を照合する

## Pluginの導入と外部認証を分ける

CLIでは`/plugins`で詳細を開き、Skill、接続、Hooksと必要な設定を確認して導入する
外部サービスを使う場合は、サービスへの認証、利用するアカウント、許可された操作を別に確認する
Pluginを入れたことだけで、外部データへのアクセスや送信の許可が得られたとは扱わない

現在の公式資料では、Pluginの同梱Skillやツールは、新しいチャットまたはCLIセッションで確認する
ローカルの単独Skillの自動検出と混同しない
ChatGPTでは`@`、Codex CLIやIDEの単独Skillでは`$`または`/skills`が明示呼び出しの入口になる
画面のボタン名や接続順序は利用環境により変わるため、教材の画面表示を共通手順として固定しない

このリポジトリのMarketplace追加とPlugin導入は[CodexのPlugin](codex-plugins.md)を参照する
手元のCodex CLI 0.162.0のヘルプでは、導入コマンドは`codex plugin add <PLUGIN@MARKETPLACE>`である
2026年10月11日に、同じCLIでLinear Plugin 5.0.1を導入した

```shell
codex plugin add linear@openai-curated-remote --json
codex plugin list --json
```

導入前は未インストールで、導入後の一覧ではinstalledとenabledが両方trueになった
アカウント側の管理情報でもインストール済みを確認した
この状態確認と、外部のIssueを取得できることは別であり、実データへのアクセスは未確認である
インストールを案内する表示だけで完了とは扱わず、導入後の状態を再取得する
新しいセッションでツールを確認し、接続が必要と表示された場合にサービスへの認証を行う

## 呼び出しと成果を別に検証する

同じ入力資料を使い、次の依頼を独立した会話で試す
自動選択が許可されているSkillでは、対象の依頼と対象外の依頼を両方確認する
明示呼び出し限定なら、その方針に沿った選択を確認する

| 確認 | PRレビューSkillでの例 | 見るもの |
|---|---|---|
| 明示呼び出し | `$evidence-code-review`でこの差分をレビューする | 指定したSkillの本文と必要な資料を読んだか |
| 自動選択 | この差分に、利用者に影響する不具合がないかレビューする | Skill名なしで適切な手順を選んだか |
| 対象外 | この関数の処理を説明する | レビューSkillを不必要に選ばないか |
| 成果 | 既知の不具合を含む小さな差分をレビューする | 不具合の発生条件と影響を根拠付きで説明できるか |

対象外で呼ばれないことだけを確認しても、必要な場面で呼ばれる証明にはならない
発動結果と、成果物の品質を別々に記録する
品質への寄与を比較する場合は、Skillありとなしで同じ資料を使い、検出した不具合、誤った指摘、見落としを比べる
少数の試行から一般的な成功率を主張せず、入力と観測結果を残す

PRレビューでは、重要度、対象箇所、発生条件、影響、根拠、修正方針を確認する
テスト不足だけを理由にバグと断定せず、軽微なスタイルの好みで指摘を増やさない
外部にレビューコメントを投稿する操作は、ローカルのレビュー検証と分ける

## 利用履歴を集計するときの注意

ログでSkill本文を読んだ回数と、実際に作業へ適用した回数を区別する
監査目的の読み取りもあり、本文の直接注入や再読なしの利用は、ファイル読み取りの集計から漏れる
現在のCodexログにはcustom_tool_callもあるため、function_callだけを読む解析器では不足する
履歴に記録がないことだけを理由に、未使用と判断して削除しない
今後の継続集計には、CodexのSkill利用イベントを収集する方法も検討できる

## 作成と共有

`$skill-creator`には、繰り返す作業、呼び出す場面、必要な入力、期待する成果を伝える
本文には判断を変える情報を置き、条件付きの詳細は`references/`へ分ける
同じ処理を繰り返し書く場合や、決定的な処理が必要な場合に`scripts/`を使う
不要なディレクトリは作らない

構文の検証は`quick_validate.py`で行えるが、実際の呼び出しや判断の正しさは別に確かめる
レビューの重要度は既存Skillとプロジェクトの規約に合わせ、教材のラベルを一律に上書きしない

GitHubで単独Skillを共有する場合は、`SKILL.md`を含むディレクトリのURLと確認済みの版を渡す
継続的に配る場合や接続設定をまとめる場合はPluginを検討する
Plugin化しても、参照先や認証、各環境での動作の確認は必要になる
公開Directoryへの掲載と、GitHub上のMarketplaceでの配布は別の手続きである

公式のパッケージ解説には`plugin-creator`の案内があるが、利用可能一覧に存在することを確認してから使う
使えない環境では、[最小のPlugin構成](codex-plugins.md#最小のpluginを作る)を参照する

## 出典

- ユーザー提供教材「Skills / Pluginsの実践活用」
- [Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Plugins](https://learn.chatgpt.com/docs/plugins)
- [Package your plugin](https://developers.openai.com/plugins/build/plugins)
- [deadskillsのCodex解析](https://github.com/anandsaini18/deadskills/blob/main/src/adapters/codex.ts)
- [gocccのTool & Skill Analytics](https://github.com/backstabslash/goccc#tool--skill-analytics)
- [Codex Usage Tracker](https://github.com/douglasmonsky/codex-usage-tracker)
- [Codex 0.162.0のSkill利用イベント](https://github.com/openai/codex/blob/rust-v0.162.0/codex-rs/otel/src/skill_invocation.rs)

公式資料の確認日は2026年10月11日
