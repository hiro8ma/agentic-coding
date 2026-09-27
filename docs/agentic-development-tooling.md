---
title: "AI駆動開発ツールの変化と判断の境界"
date: "2026-09-27"
tags: [agentic-coding, codex, agent-skills, spec-driven-development, evaluation]
---

# AI駆動開発ツールの変化と判断の境界

GitHub Copilotが個人開発者向けに一般提供されたのは2022年6月だった
当時の中心はエディター内のコード提案だったが、現在のコーディングエージェントはファイルを読み、編集し、コマンドで結果を確かめられる
モデルが改善しても、エージェントができることはモデルだけで決まらない
利用できるツール、渡す文脈、権限、実行後の検証も結果を左右する

## 共通点をどこまで移せるか

AWSのAI-DLC、GitHub Spec Kit、AnthropicのAgent Skillsは、異なる目的からエージェントの作業を構造化している
AI-DLCは開発の段階を複数のコーディングツールで実行できる形に分ける
Spec Kitは仕様、計画、タスク、実装の成果物をつなぐ
Agent Skillsは指示と参照資料をまとめ、必要なときに読み込む

これらから、作業のたびに同じ長い指示を貼る代わりに、情報の役割を分ける設計は読み取れる
ただし、各社が同じアーキテクチャや同じ設定仕様へ収束したとは言えない

| 情報の役割 | このリポジトリでの置き場所 | 移植時に確かめること |
| --- | --- | --- |
| 恒常的な規約 | `AGENTS.md`、製品固有のルールファイル | 読み込みの範囲と優先順位 |
| 作業ごとの手順 | `skills/*/SKILL.md` | Skillの検出場所、使えるツールと権限 |
| 外部のデータと操作 | MCP、CLI、ブラウザ | 接続方法、認証と認可、返却値の扱い |
| 必ず行う検証 | スクリプト、Hooks、CI | 発火条件と、迂回できない確認の場所 |

Agent Skillsの本文を再利用できても、Skillが呼ぶツールの名前や権限は製品ごとに異なる
Hooksもイベント名と信頼設定が異なる
ツールを替える際はMarkdownをコピーするだけで終えず、実際にどの処理が動き、どこで拒否されるかを試す

## 自律性が増えたときに人間が決めること

自然言語でコードを作ることと、検証を省くことは同じではない
「Vibe Coding」と「Agentic Engineering」は製品の公式な二分類ではなく、人間が成果をどう管理するかを考えるための言葉として使う

たとえば既存APIの不具合修正なら、開発者は再現手順、守るべき互換性、変更範囲、完了条件を先に定める
エージェントには調査と実装を任せ、最後に差分、テスト、実際のリクエストとレスポンスを確認する
権限や秘密情報を扱う操作では、実行前の認可と実行後の結果確認も必要になる
依頼に含める情報と作業の分け方は[タスク設計](task-design.md)にまとめた

このリポジトリでは、[コンテキスト設計](context-design.md)が規約、Skills、外部ツール、Hooksの責務を分けている
[仕様駆動開発](spec-driven-development.md)は要求、設計、タスクと受け入れ条件を作業単位で残す
新しい共通層を増やす前に、この二つで表現できるかを確かめる

## 変わりやすい記述の扱い

製品の機能、モデル名、速度、料金は利用時点の一次情報を確認する
2026年9月時点のOpenAI公式資料にはGPT-6系が掲載され、2026年7月のモデル一覧だけでは現在の選択肢を示せない
APIのFast modeは`service_tier`で指定できるが、Codexの操作との対応は別の資料で確認する
出典を特定できない移植事例や改善率は、効果を示す根拠として使わない

## 参照資料

- [GitHub Copilotの一般提供](https://github.blog/changelog/2022-06-21-github-copilot-is-now-available-to-individual-developers/)
- [AWS AI-DLC workflows](https://github.com/awslabs/aidlc-workflows)
- [GitHub Spec Kit](https://github.com/github/spec-kit/blob/main/docs/index.md)
- [Anthropicの組織向けSkillsとAgent Skills標準](https://claude.com/blog/organization-skills-and-directory)
- [OpenAIのSkillsと指示を見直す指針](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
- [OpenAIのモデル案内](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI APIのFast mode](https://developers.openai.com/api/docs/guides/fast-mode)
