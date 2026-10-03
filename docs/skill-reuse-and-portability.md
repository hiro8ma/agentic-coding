---
title: "Skillを選び、CodexとClaude Codeで再利用する"
date: "2026-10-04"
tags: [skills, codex, claude-code, portability, plugins]
---

# Skillを選び、CodexとClaude Codeで再利用する

同じレビュー手順を繰り返すなら、既存のSkillを調べてから足りない部分を自作できる
Skillの名前や導入件数だけでなく、作業範囲、実行する処理、必要な接続を確認する
公開されていること、インストール済みであること、今のセッションで利用できることは別の状態である

## 配布元と利用状態を分ける

| 分類 | 導入の入口 | 確認すること |
|---|---|---|
| System同梱 | ホストが組み込む | 対象の版とセッションで使えるか |
| Plugin同梱 | Plugins Directoryやカタログ | 同梱Skill、接続、権限、導入範囲 |
| 公開された単独Skill | skill-installerなどでリポジトリから導入 | 本文、スクリプト、参照先、ライセンス |
| 自作 | ローカル配置またはPlugin化 | 繰り返す作業と正典、検証方法 |

Codexの`$skill-creator`は作成や更新を支援し、`$skill-installer`は既存Skillを導入する
`imagegen`は画像生成、`openai-docs`はOpenAIの公式資料の参照に使う
利用可能なSystem Skillの一覧は固定とみなさず、その環境の一覧で確認する

`plugin-creator`はCodex CLI 0.159.0で組み込みから削除された
一部のパッケージ解説には組み込みとしての記述が残るため、使えることを前提に手順を作らない
現在の公式文書には単独のCurated Skillsの導入も残り、すべてがPluginへ移ったとは確認できない

2026年10月4日の公開一覧には`gh-address-comments`と`yeet`がある
前者はPRコメント対応、後者はステージ、コミット、プッシュ、PR作成をまとめた作業に使う
配布されているSkillの指示だけで、投稿やプッシュの承認が得られたとは扱わない

## 導入前にパッケージを読む

`description`で対象の作業が合うかを判断し、本文で手順と操作を確認する
スクリプトは実行環境、依存関係、書き込み、外部通信まで読み、参照ファイルが実在するかも確認する
スクリプトがないSkillでも、本文が外部操作を指示する場合がある
ライセンスはfrontmatter、`LICENSE.txt`などの同梱ファイル、リポジトリのライセンスを照合する
素材やコードのライセンスが別なら、その条件も確認し、不明な点は未確認として残す

手順が繰り返され、公開Skillでは固有の判断を表現できない場合は自作を検討する
一度だけの依頼や、まだ変化している手順はプロンプトで進め、繰り返しが観測できてから切り出す
本文は判断を変える情報に絞り、必要なときだけ読む詳細を`references/`へ分ける
同じ処理を何度も書き直している場合は、`scripts/`での自動化を検討する

## 本文とホスト固有の設定を分ける

| 観点 | Codex | Claude Code |
|---|---|---|
| プロジェクト配置 | `.agents/skills/` | `.claude/skills/` |
| ユーザー配置 | `$HOME/.agents/skills/` | `$HOME/.claude/skills/` |
| 明示呼び出し | CLIやIDEの`$skill` / `/skills` | `/skill-name` |
| 自動呼び出しを止める | `agents/openai.yaml`の`policy.allow_implicit_invocation: false` | frontmatterの`disable-model-invocation: true` |
| 削除せず無効化する | `config.toml`の`[[skills.config]]`で`enabled = false` | 通常のSkillは`skillOverrides`の`off`。PluginのSkillはPluginを無効化 |
| ホスト固有の拡張 | `agents/openai.yaml` | `context: fork`、`user-invocable`など |

自動呼び出しを止めても、明示呼び出しは可能な設定がある
移植時は、自動選択、ユーザーの明示呼び出し、完全な無効化を区別する
Claude Codeの`allowed-tools`は事前許可の設定で、使えるツールを限定する一覧とは異なる
本文を共有しても、ツール名、スクリプトの起動場所、依存関係、認証は移植先で確認する

Codexは`AGENTS.md`を作業方針として読む
Claude Codeもv2.1.277以降は条件付きで`AGENTS.md`を直接読む
既定では、作業ディレクトリや上位に`CLAUDE.md`などがあると`AGENTS.md`を読まないため、両方へ同じ規約を複製する前に読み込み方針を確認する

## 段階的な読み込みと検証

Codexは初期一覧に名前、説明、パスを載せ、選んだSkillの本文と必要な資料を読む
初期一覧はコンテキストウィンドウの最大2%で、サイズ不明なら8,000文字に制限される
多数のSkillがあると説明が短縮され、一部が省かれる場合もある
本文を分割する改善と、初期一覧の重複や長い説明を減らす改善は分ける

導入したら一覧で検出を確認し、対象の依頼と対象外の依頼を試す
配置やfrontmatterの検査だけで、実際の選択や出力品質を検証したとは判断しない
このリポジトリの`context-audit`は、これらの配置と呼び出し設定も監査する

## 出典

- [Codex Build skills](https://learn.chatgpt.com/docs/build-skills)
- [Codex changelog](https://learn.chatgpt.com/docs/changelog)
- [OpenAIの公開Skill](https://github.com/openai/skills/tree/main/skills/.curated)
- [Claude Code Skills](https://code.claude.com/docs/en/skills)
- [Claude Code AGENTS.md対応](https://code.claude.com/docs/en/memory#agents-md)
