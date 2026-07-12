---
title: "デザイン系スキル — frontend-design / theme-factory / canvas-design と転用できる設計哲学"
date: "2026-06-29"
tags: [claude-code, agent-skills, design, frontend-design, theme-factory, canvas-design, ai-slop, skill-authoring]
---

# デザイン系スキル

## TL;DR

Anthropic 公式のデザイン系スキル（frontend-design / theme-factory / canvas-design）は、成果物を直接作る道具ではなく、AI スロップを避ける方法論をパッケージ化したものである。共通する設計は「成果物より先に方向性を言語化する」こと。この哲学ファイル → 成果物の二段階と「追加より洗練」の原則は、UI やビジュアルだけでなく自作 SKILL.md の設計そのものに転用できる。

## AI スロップとは

LLM は無指示だと最も確率の高い無難な出力に収束する。Web UI なら紫系グラデーション、丸いアバター、均等なカード、ありきたりな配色に寄る。この没個性な出力を AI スロップと呼ぶ。

デザイン系スキルは、コードや画像を生成する前に方向性を決めさせることで、この収束を断つ。frontend-design はこれを次の一文で表す。

> Don't hold back, show what can truly be created when thinking outside the box and committing fully to a distinctive vision.

人間のデザイナーは、あえて常識に逆らう選択で独自性を出す。スキルはその「あえての選択」を LLM に強制する。

## 3 スキルの役割

| スキル | 対象 | 進め方 |
|---|---|---|
| frontend-design | Web ページ / ダッシュボード / React | 方向性を決め、5 分野（書体・配色・モーション・空間構成・ディテール）で実装する |
| theme-factory | 既存文書（スライド / レポート / HTML） | プリセット提示 → 選択 → 適用。URL を渡せば配色やフォントを抽出してカスタム生成 |
| canvas-design | ポスター / カバーアート / コンセプトビジュアル | 哲学 .md を書く → Canvas API でビジュアル化。画像 90% / テキスト 10% |

### frontend-design の 5 分野

| 分野 | 方針 |
|---|---|
| タイポグラフィ | ありきたりなフォントを避け、サイトの個性に合う書体を選ぶ |
| カラー / テーマ | 均等な色使いより、強い主色と鋭いアクセント |
| モーション | 散発的なマイクロインタラクションより、読み込み時の統一アニメーション |
| 空間構成 | 非対称、重なり、グリッド破りで動きを出す |
| ビジュアルディテール | テクスチャ、ノイズ、グラデーションで深みを足す |

### theme-factory は対話前提

frontend-design が「まず方法論を考える」のに対し、theme-factory は「まず選択肢を見せる」。デザインの好みは文脈で変わるため、テーマ一覧の提示 → 選択 → 確認 → 適用という対話フローを取る。

```
> /theme-factory sample.html にテーマを適用して
> /theme-factory https://stripe.com を参考にしたテーマを作って、sample.html に適用して
```

参考サイトはコピーせず、配色やフォントの特徴を抽出してオリジナルテーマにする。

### canvas-design は二段階

第一段階で「美的運動のマニフェスト」を .md に書く。形、空間、色彩の基準、構図の原則を言語化する。第二段階でその哲学を Canvas API でビジュアル化する。写真ではなく幾何学的・抽象的な表現に向く。

## 転用できる設計哲学（スキル作者の視点）

3 スキルは用途が違うが、設計としては同じ骨格を持つ。ここが skill-creator で自作スキルを書くときに効く。

| 原則 | 内容 |
|---|---|
| 方向性を先に決める | 成果物の前に哲学・方針を言語化する（哲学ファイル → 成果物の二段階） |
| 判断基準を明文化する | 何を良しとするかを SKILL.md に書く |
| 追加より洗練 | 要素を足すより、既存の構図を磨く |
| 手続き化 | デザイン作業を段階的プロセスに分解する |
| LLM の癖を補正する | 無難な出力（AI スロップ）に寄る傾向を抑える |

とくに canvas-design が FINAL STEP で強調する「追加より洗練」は、UI でもテーマでもビジュアルでも、そして SKILL.md 設計そのものにも当てはまる。少ない要素を徹底的に磨く。

## 自分の資産との接続

- `agentic-coding/skills/` の自作スキル（knowledge-note / weekly-report / japanese-tech-writing）も、この「方向性を先に決める / 判断基準を明文化する / 追加より洗練」で設計強度を上げられる
- japanese-tech-writing は「方法論を先に置いて出力の癖を補正する」点でデザイン系スキルと同型。文章版の AI スロップ対策にあたる
- `portfolio/`（Next.js）の UI 改善に frontend-design、ブログのカバー画像に canvas-design、資料に theme-factory を充てられる
- 公式スキルの導入と一覧は [[plugins-and-extension-points]]、Skill の仕様は [[agent-skills]] を参照

## brand-guidelines — ガードレール型スキルという別の型

brand-guidelines は、ロゴ・カラーパレット・タイポグラフィを SKILL.md に定義し、ドキュメント生成時に自動適用するスキル。
theme-factory が「選択肢を提示して選ばせる」対話型なのに対し、brand-guidelines は**選択肢を出さずに事前定義ルールを自動適用する「ガードレール型」**である。

| 観点 | theme-factory | brand-guidelines |
|---|---|---|
| 選択 | ユーザーがテーマを選ぶ | 自動適用 |
| 目的 | 見た目の選択肢を提供 | ブランド統一 |
| 運用 | 対話的 | ガードレール型 |

本質は「ブランドガイドラインが『読むもの』から『実行されるもの』に変わる」こと。
人が PDF を読んで手動適用していたルールを、AI が自動適用する形に引き上げる。
この変換はブランドに限らず、文書規約・トンマナ・用語集など「守らせたいルール」全般に一般化できる。

### 自社ブランドへのカスタマイズ

SKILL.md の Colors / Typography セクションの HEX コードとフォント名を書き換えるだけでよい。

```markdown
---
name: my-company-brand
description: 自社のブランドカラーとタイポグラフィを適用します。
---
# Colors
- Primary Dark: #1E3A5F
- Accent: #2563EB
# Typography
- Headings: Noto Sans JP (bold)
- Body: Noto Sans JP (regular)
```

Markdown なのでデザイナーでなくても編集でき、リポジトリで共有すればチーム全員の成果物が揃う。

### CLAUDE.md とスキルの使い分け（ブランドに限らない判断表）

| 条件 | 推奨 |
|---|---|
| プロジェクト内の全成果物へ必ず適用する | CLAUDE.md |
| 複数プロジェクトで再利用する | スキル |
| 必要なときだけ適用する | スキル |
| 適用漏れを避けたい | CLAUDE.md |
| コンテキストを必要最小限にしたい | スキル |

両取りしたい場合は「グローバル CLAUDE.md で適用を必須化 + スキル本体は再利用可能に分離」というハイブリッドが使える（japanese-tech-writing の運用がこの形）。

## canvas-design × brand-guidelines の組み合わせ

役割分担は「独自性 = canvas-design、一貫性 = brand-guidelines」。

- 固定する要素（brand 側） — ロゴ、コーポレートカラー、書体、最小余白、禁止表現
- 可変にする要素（canvas 側） — 構図、テクスチャ、視覚的リズム、キャンペーン固有のアクセント

全要素をブランドで固定すると作品固有の表現が死ぬため、固定と可変の境界を先に決める。

### 哲学ファイルは「デザインの Prompt Registry」

canvas-design の哲学ファイルはセクション分割（色彩 / 空間構成 / タイポグラフィ / リズム）されており、「色彩だけ暖色系へ、空間構成は維持」という部分編集ができる。
「もう少し青くして」を繰り返す曖昧な反復より再現性が高い。
プロンプトを版管理して部分更新する Prompt Registry の発想のデザイン版にあたる。

再現性のため、最終画像だけでなく中間成果物（デザイン哲学・ブランド定義・色コード・Canvas API コード・バージョン）を残す。

## algorithmic-art と slack-gif-creator — スクリプトの要否という設計判断

題材はアートと GIF だが、主題はスキルアーキテクチャの分岐基準にある。

| 観点 | algorithmic-art | slack-gif-creator |
|---|---|---|
| 出力 | p5.js のインタラクティブ HTML | Slack 用アニメーション GIF |
| 構成 | SKILL.md + テンプレートのみ | Python スクリプト 4 本が必須 |
| 再現性 | シード値（同じシードで完全再現） | 固定パラメータ + フレーム生成 |
| 検証 | UI と出力仕様で担保 | validators.py で自動検証 |

分岐基準は出力形式。
LLM が直接生成できる形式（Markdown / HTML / JS / CSS / JSON）はスクリプト不要。
専用処理が要るバイナリ形式（GIF / 動画 / 音声 / 圧縮）はスクリプト必須（エンコード・カラー最適化・サイズ制御は指示だけでは安定しない）。
自作時は「まずスクリプトなしで実現できるか」を検討し、足りるなら単純な構成を選ぶ。

### スキルの 4 層分担（一般則）

| 層 | 担当 | 例 |
|---|---|---|
| 知識・方針 | SKILL.md | Slack の寸法・色数・FPS 制約、アニメーションパターン |
| 構造の統一 | テンプレート | viewer.html の UI 配置（毎回同じ操作感になる理由） |
| 計算・変換 | スクリプト | GIF エンコード、イージング、カラー最適化 |
| 最終判定 | バリデータ | Slack 要件への適合を自動検証 |

「確率的な LLM に任せる部分と、決定的なコードに任せる部分の境界を引く」という原則で、
leak-scan フック（検証はコード）や評価設計（決定的チェックはコード、意味判定は Judge）と同じ構造。

### プラットフォーム制約の内蔵

slack-gif-creator は Slack の寸法（絵文字 128×128 / メッセージ 480×480）・FPS（10〜30）・色数（48〜128）・再生時間を SKILL.md に埋め込み、ユーザーが毎回仕様を調べなくてよい状態にする。
brand-guidelines の「読むものから実行されるものへ」と同じ変換を、ブランドでなくプラットフォーム仕様に適用した形。
特定プラットフォーム向けスキルを作るときは、許容寸法・最大サイズ・命名規則・アップロード要件・バリデーション条件を内蔵する。

### シードランダム性 — 生成系の再現性 2 段階

algorithmic-art の中心はシードランダム性（同じシードなら同じ作品、シードを変えるとバリエーション探索）。
生成系の再現性確保は 2 段階で使い分ける — 哲学ファイル = 方向性の再現、シード = 完全な再現。
評価ハーネスで「サンプリングの seed を固定する」のと同じ規律。

### スキル設計の判断手順

1. 出力形式を明確にする
2. プラットフォーム固有の制約を列挙する
3. LLM が直接生成できる部分 / テンプレートで統一すべき部分 / スクリプトが必要な処理を切り分ける
4. バリデーション条件を定義する
5. 再現性の仕組み（シード・中間成果物）を設ける
6. 保守コストと品質のバランスを確認する

## 注意点

- frontend-design の効果はアニメーションやインタラクションに出るため、紙面では伝わりにくい。ブラウザで確認する
- canvas-design は写真生成ではない。Canvas API のプログラム的描画で、幾何学的・抽象的なビジュアル向き
- theme-factory のカスタムは参照元のコピーではなく特徴の抽出
- 画像生成のたびに共通スタイル指定（配色・トーン）を手書きしているなら、それはブランドスキル化のシグナル

## 参考

- anthropics/skills — frontend-design — https://github.com/anthropics/skills/tree/main/skills/frontend-design
- Improving frontend design through skills — https://claude.com/blog/improving-frontend-design-through-skills
- anthropics/skills — theme-factory — https://github.com/anthropics/skills/tree/main/skills/theme-factory
- anthropics/skills — canvas-design — https://github.com/anthropics/skills/tree/main/skills/canvas-design
- anthropics/skills — algorithmic-art — https://github.com/anthropics/skills/tree/main/skills/algorithmic-art
- anthropics/skills — slack-gif-creator — https://github.com/anthropics/skills/tree/main/skills/slack-gif-creator
