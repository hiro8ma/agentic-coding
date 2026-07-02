---
title: "Spec-Driven Development — AI協働開発のための仕様駆動ワークフロー"
date: "2026-07-02"
tags: [spec-driven-development, sdd, specs, steering, claude-code, codex, kiro, spec-kit]
---

# Spec-Driven Development

Spec-Driven Development は、AIに実装を任せる前に「何を作るか」と「どう作るか」を明文化し、仕様を開発の基準点にする進め方である。

ドキュメントを増やすことが目的ではない。
AIとの合意事項を固定し、実装中の判断を一貫させるための記憶装置として使う。

## What と How

仕様駆動では、What と How を分ける。

| 軸 | 内容 | 主なドキュメント |
|---|---|---|
| What | 何を作るか。誰のどんな課題を解くか | product requirements, feature requirements |
| How | どう作るか。どの構造・技術・品質基準で作るか | architecture, design, development guidelines |

What が曖昧なまま実装すると、AIはそれらしい補完を始める。
How が曖昧なまま実装すると、局所的には動くが、既存設計から外れたパッチワークになりやすい。

## 永続ドキュメントとステアリングドキュメント

仕様を2種類に分ける。

| 種類 | 保存場所 | ライフサイクル | 役割 |
|---|---|---|---|
| 永続ドキュメント | `docs/` | プロダクトや基本設計が変わるまで維持 | プロジェクト全体の北極星 |
| ステアリングドキュメント | `.steering/<date>-<title>/` | 作業単位で作成し、完了後は履歴化 | 今回の変更範囲と実装計画 |

Kiroの steering docs は、プロダクト概要、技術スタック、プロジェクト構造のような基礎情報を常時コンテキストとして扱う。
このリポジトリでは、ツール非依存にするため `docs/` と `.steering/` を標準形として扱う。

## 推奨ファイル構成

```text
docs/
  product-requirements.md
  functional-design.md
  architecture.md
  repository-structure.md
  development-guidelines.md
  glossary.md

.steering/
  20260702-add-priority-filter/
    requirements.md
    design.md
    tasklist.md
```

### `docs/`

| ファイル | 目的 |
|---|---|
| `product-requirements.md` | プロダクトビジョン、対象ユーザー、課題、成功条件 |
| `functional-design.md` | 機能一覧、データモデル、画面、API、ユースケース |
| `architecture.md` | 技術スタック、制約、非機能要件、品質方針 |
| `repository-structure.md` | ディレクトリ構成、配置ルール、命名規則 |
| `development-guidelines.md` | コーディング規約、テスト規約、Git運用 |
| `glossary.md` | ドメイン用語、UI用語、コード命名との対応 |

### `.steering/`

| ファイル | 目的 |
|---|---|
| `requirements.md` | 今回の変更で満たす要求、ユーザーストーリー、受け入れ条件 |
| `design.md` | 実装方針、影響範囲、変更するコンポーネント、テスト方針 |
| `tasklist.md` | 実装タスク、依存関係、完了条件、検証コマンド |

## ワークフロー

### 1. 初回セットアップ

1. `docs/` と `.steering/` を作る
2. `docs/` に永続ドキュメントを作る
3. 初回実装用に `.steering/<date>-initial-implementation/` を作る
4. `requirements.md`、`design.md`、`tasklist.md` を作る
5. `tasklist.md` に沿って実装する
6. 実装後に `docs/` とコードがずれていないか確認する

### 2. 機能追加

1. 既存 `docs/` を読み、What / How の制約を確認する
2. `.steering/<date>-<feature>/requirements.md` を作る
3. `requirements.md` から `design.md` を作る
4. `design.md` から `tasklist.md` を作る
5. タスク単位で実装する
6. 基本設計が変わった場合だけ `docs/` を更新する

### 3. バグ修正

バグ修正は Feature Spec と分ける。

`requirements.md` には次を明記する。

- 再現手順
- 現在の挙動
- 期待する挙動
- 変えてはいけない挙動
- 回帰テストの条件

Kiroの Bugfix Specs でも、修正対象だけでなく「維持すべき挙動」を明示して回帰を防ぐ考え方が採られている。

## AI を壁打ち相手にした仕様づくり

仕様を書く前段には、アイデアの発散と絞り込みがある。
ここで AI は、時間や回数を気にせず対話できる壁打ち相手として機能する。

- 複数案の比較と優先順位付けを支援できる
- 対話履歴をそのまま設計資料に落とし込める
- MVP の絞り込みにも使える

ただし役割分担を崩さないことが前提になる。
AI は提案者であり、事業性・実装可能性・優先順位の最終判断は人間が行う。
AI 壁打ちは発散が得意な分、「作るべきか」を人間が握らないと、よくできた不要品の仕様書が量産される。

### MVP を絞る

最初から全機能を作ろうとすると開発は終わらない。
たとえばタスクの優先順位自動推定なら、MVP では「期限までの残り時間・依存タスクの有無・推定作業時間」のルールベースで十分と割り切る。

この判断の型は、デザイン系スキルの「方向性を先に決める」「追加より洗練」（`docs/design-skills.md`）のプロダクト開発版にあたる。
高度な手段（ML 推定等）は、単純な手段で足りない箇所が特定できてから足す。

## 文書化の三段構え

仕様書は一度で完成させず、次の三段で仕上げる。

1. AI がドラフトを生成する
2. AI に品質レビューをさせ、不足点・曖昧な点を洗い出す
3. 人間がレビューし、実装可能な粒度まで具体化する

AI レビューの観点は次の 5 つが基本形になる。

1. プロダクトビジョンは明確か
2. ターゲットユーザーは具体的か
3. 成功指標は測定可能か（測定方法まで定義されているか）
4. 機能要件は実装可能なレベルまで詳細化されているか
5. 非機能要件は網羅され、検証可能な形で書かれているか

AI は自分の生成物の穴を、レビュアーという別ロールを与えられると見つけられる。
これは PR レビュー bot（`docs/pr-review-bot-workflow.md`）が実装に対してやっていることの、設計文書版である。

## 北極星文書は更新しなければ嘘をつく

永続ドキュメントは「北極星」として、迷ったときに戻る判断基準になる。
ただし書いて終わりでは機能しない。
更新されない仕様書は、実装と乖離した嘘の判断基準になる。

仕様変更を伴う PR には対応する文書更新を含める、といったルール化で腐敗を防ぐ。
逆に、探索目的のリポジトリ（学習実装・プロトタイプ）へフル適用すると、更新コストが学習速度を落とす。
適用先は保守前提のプロジェクトに限定する。

## 組織記憶との接続

永続ドキュメントは AI との合意形成の記録であり、「常に最新・正典・構造化済み」という性質を持つ。
この性質は、RAG の知識ベースへ取り込む（ingestion する）対象として最も質が高いクラスにあたる。
Slack ログや議事録と違い、鮮度管理を Git 履歴で解決できる。

つまりスペック駆動開発の成果物は、組織の AI が参照する組織記憶の第一級候補になる。
「文書がプロジェクトと共に進化する」規範は、組織記憶ループ（参照 → 実行 → 書き戻し）の書き戻しと同型で、開発ドキュメントで先にこのループを回せば組織 AI 化の実証パイロットになる。

## 5 つの教訓

| 教訓 | 内容 |
|---|---|
| 行き当たりばったりな実装は負債を生む | What と How の合意なしに進めると仕様の齟齬と技術的負債が生まれる |
| AI は壁打ち相手として最高 | アイデアを広げ、絞り込み、設計資料化する相手として使える |
| AI はレビューにも使う | ドキュメント、コード、テスト、動作検証に活用できる |
| ドキュメントは北極星 | プロジェクトが迷ったときに戻る基準になる |
| 作業単位の記録が重要 | 永続ドキュメントとステアリングドキュメントを分けて管理する |

## 要求の書き方

受け入れ条件は、できるだけテスト可能な形で書く。

```text
WHEN ユーザーが未完了のみフィルタを選択する
THE SYSTEM SHALL 未完了タスクだけを一覧に表示する
```

この形は EARS に近い制約つき自然言語で、人間にもAIにも解釈しやすい。

## 承認ゲート

スペック駆動では、いきなり実装へ進まない。
最低限、次の3ゲートを置く。

| ゲート | 確認すること |
|---|---|
| Requirements approval | 何を作るか、受け入れ条件が明確か |
| Design approval | どう作るか、既存設計と整合しているか |
| Task approval | 実装順序、依存関係、検証方法が明確か |

小さい変更ではゲートを軽くしてよい。
ただし、仕様を省略してよいのは、typo修正や一行修正のような変更に限る。

## Spec Kit との対応

GitHub Spec Kit は、仕様を主成果物として扱い、次の流れを提供する。

| Spec Kit | このリポジトリの標準 |
|---|---|
| constitution | `docs/development-guidelines.md`, `docs/architecture.md` |
| specify | `.steering/<date>-<title>/requirements.md` |
| plan | `.steering/<date>-<title>/design.md` |
| tasks | `.steering/<date>-<title>/tasklist.md` |
| implement | `tasklist.md` に沿った実装 |
| analyze / checklist | 実装前の仕様整合性チェック |

## Vibe Coding との関係

Vibe Codingは探索に強い。
Spec-Driven Developmentは収束に強い。

| 状況 | 向く進め方 |
|---|---|
| アイデア探索、プロトタイプ、捨てる前提の実験 | Vibe Coding |
| 複雑な機能、チーム開発、保守前提、回帰が高コスト | Spec-Driven Development |

実務では、vibe session でアイデアを膨らませた後に `Generate spec` のように仕様化し、以後は spec を基準に実装する流れが扱いやすい。

## 実装フェーズの進め方

ステアリングファイル（requirements / design / tasklist）が承認されたら、tasklist に沿って実装する。
このフェーズの要点は、実装そのものより「レビュー単位」と「撤退線」の設計にある。

### レビュー単位を先に決める

どのくらいのタスク単位で人間が確認するかを、実装開始前に指示で固定する。

- 「○○が終わる単位でレビューを依頼してください」
- 「レビューが OK と承認されてから次に進んでください」
- 「初回作業はローカル環境で動作確認できる状態になってから確認する」

初回は環境構築などの作業が多くエラーも発生しやすいため、MVP はできる限り小さい機能スコープに絞る。

### 撤退線を見極める

進みが悪く、同じ事象の解消でループしている場合は、その場での修正を続けない。
上位ドキュメント（design、それでも駄目なら requirements）に戻って前提を見直す。
北極星文書の価値は、この「戻れる場所がある」ことにある。

### 実装順序はレイヤーの依存方向に従う

design.md には実装順序を依存の下流から書く。
型定義・定数 → データレイヤー → サービスレイヤー → インターフェースレイヤー（CLI / API）の順に積むと、各段階で動作確認できる。
言語ごとの具体的な実装順序と検証コマンドは、`.claude/<言語>/spec-driven.md` に定義する。

### Before / After

教材の題材（タスク管理 CLI）での振り返りは次の通り。

| 観点 | Vibe Coding | スペック駆動開発 + CLAUDE.md |
|---|---|---|
| 進め方 | 思いつきで実装、全体像なし | ドキュメントで方向性を明確化 |
| コード品質 | カオスなコード | レイヤー分離された保守可能なコード |
| テスト | テストなし | カバレッジの高い実テストで検証 |
| 成果 | 3 日かけて動かないものができた | 1 日で MVP 達成 |

最大の違いはプロセスの明確化である。
CLAUDE.md がプロセスとルールをオーケストレートすることで、迷いなく作業を進められる。

### 動くものを早く見せる

MVP を重視し、コアな価値を提供する機能から素早くリリースする。
実際に使ってもらうことで早期に問題を発見でき、価値の高い機能の発見にもつながる。
動くものができる達成感は、開発者のモチベーションにもなる。

## 2026 年の動向

2026 年の転換点は SDD のコモディティ化である。
GitHub Spec Kit は v0.11.0 で 30 以上のコーディングエージェント（Copilot / Claude Code / Cursor / Gemini CLI / Codex CLI / Kiro 等）に対応し、Amazon Kiro は 2026 年 5 月に Amazon Q Developer を置き換える形で本格展開された。
SDD は特定ツールの機能ではなく、業界標準ワークフローになった。

差別化軸は「仕様の寿命」に移っている。

| 階層 | 例 | ドキュメント腐敗への耐性 |
|---|---|---|
| セッション内プラン | Claude Code Plan Mode | 低（プランは永続化されるが同期機構なし） |
| リポジトリ内成果物 | Spec Kit / Kiro | 中（Spec Kit はクロスアーティファクト整合性分析を標準搭載） |
| 仕様を正とする常時同期 | Tessl spec-as-source | 高（仕様とコードを常時同期） |

批判側の論点も整理されてきた。
「ウォーターフォールの再来」批判に対しては、フィードバックループが四半期単位だった当時と違い SDD のループは分から時間単位で回る、という反論が主流になっている。
一方で、ソロ開発・5 人未満チーム・要件が高速に変わる探索フェーズでは仕様書作成コストが回収できない、という限界論は共通見解として残る。
Vibe Coding は発見速度、SDD は本番の耐久性を提供する、という使い分けが 2026 年の実務の結論である。

## 関連

- `docs/context-design.md`
- `docs/agent-skills.md`
- `docs/design-skills.md`
- `docs/pr-review-bot-workflow.md`
- `skills/spec-workflow/SKILL.md`
- `skills/context-audit/SKILL.md`

## 参考

- GitHub Spec Kit — https://github.com/github/spec-kit
- Spec Kit 公式ドキュメント — https://github.github.com/spec-kit/
- Kiro Specs — https://kiro.dev/docs/specs/
- Claude Code best practices — https://code.claude.com/docs/en/best-practices
- Codex AGENTS.md — https://developers.openai.com/codex/guides/agents-md
- Vibe Coding vs SDD — https://www.infoworld.com/article/4166817/vibe-coding-or-spec-driven-development-how-to-choose.html
- Tessl spec-as-source — https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry/
