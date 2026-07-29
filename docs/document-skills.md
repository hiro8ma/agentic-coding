---
title: "公式ドキュメント処理スキル（pdf / docx / pptx / xlsx）— 設計例として読む"
date: "2026-07-29"
tags: [agent-skills, pdf, docx, pptx, xlsx, progressive-disclosure, reportlab, pypdf, docx-js, pptxgenjs, openpyxl, ooxml]
---

# 公式ドキュメント処理スキル（pdf / docx / pptx / xlsx）

anthropics/skills の公式ドキュメント処理スキル 4 種を設計例として読む。
Agent Skills の仕組み全般は `agent-skills.md`、実際に使う手順は `skills/document-processing/` を参照。

## スキルの本質はライブラリ選定知識のパッケージ化

pdf スキルの中核は「タスク → 適切なライブラリ」の対応表にある。

| タスク | ツール | 特徴 |
|---|---|---|
| テキスト抽出 | pdfplumber | 表のレイアウトも保持して抽出 |
| 結合・分割 | pypdf | 依存が少なく高速な基本操作 |
| 新規作成 | reportlab | レイアウトの自由度が高い |
| OCR | pytesseract + pdf2image | スキャン PDF を画像化して認識 |
| 暗号化・復号 | pypdf / qpdf | パスワード保護の付与・解除 |

どのライブラリがどの操作に向くかの調査と検証を誰かが一度だけ行い、以後は全エージェントがその判断を再利用する。
「手続き的知識のパッケージ化」のいちばん具体的な実例と言える。

## ディレクトリ分割は段階的開示のスキル内適用

```
skills/pdf/
├── SKILL.md       # 基本操作はここで完結
├── reference.md   # Python ライブラリのリファレンス
├── forms.md       # フォーム操作の詳細
└── scripts/       # ユーティリティ
```

基本操作は SKILL.md だけで完結し、フォーム操作のような高度な用途のときだけ forms.md が読まれる。
Discovery → Activation → Execution の 3 段階ロードを、スキル内部でも繰り返す設計になっている。

自作スキルへの示唆は分割タイミングの目安になる。
本文が 500 行（5,000 トークン）に近づいたら、用途別ファイルへ分割して 1 階層参照にする。
一方 docx スキルは SKILL.md 一本 + scripts/ の構成で、分割は必要になってからで良いことも示している。

## docx スキルの二刀流 — 生成はライブラリ、編集は内部表現

| 場面 | 手段 | 理由 |
|---|---|---|
| 新規作成 | docx-js | 見出し・表・目次を構造的に組み立てる |
| 既存文書の編集 | ZIP 展開 + XML 直接編集（Unpack → Edit → Repack） | 元のフォーマット・スタイルを完全保持 |

ライブラリで既存文書を読んで書き戻すと、ライブラリが解釈できない書式が落ちることがある。
.docx が ZIP + XML（OOXML）である性質を利用した直接編集なら、テンプレート差し込み・追跡変更の一括承認・一括置換を書式を崩さずに実行できる。
「生成は抽象化レイヤー、編集は内部表現」という使い分けは、ドキュメント形式一般に通じるパターン。

もう 1 つの設計点は、SKILL.md が docx-js の「知らないとレイアウトが崩れる癖」（ページサイズの明示指定、見出しスタイル ID、箇条書きの numbering 定義）をルールとして吸収していること。
ライブラリの落とし穴を利用者でなくスキルが覚える、という責務の置き方になっている。

## pptx スキル — 検証者を作成者から分離する QA

3 つの操作モードを持つ。

| モード | 手段 | 用途 |
|---|---|---|
| 読み取り | MarkItDown | スライドを Markdown 化して内容把握 |
| 編集 | XML 直接編集（Unpack → Edit → Repack） | テンプレートのデザインを維持して内容だけ差し替え |
| 新規作成 | PptxGenJS | ゼロから組み立て |

docx の二刀流（生成はライブラリ、編集は内部表現）に読み取りモードが加わった形で、リファレンスも新規用（pptxgenjs.md）と編集用（editing.md）に分離されている。

設計上の注目点は生成後の QA プロセスが必須になっていること。

1. プレースホルダー残存を grep で機械チェック
2. スライドを JPG に変換して目視確認
3. ビジュアル検査は作成者自身でなく**サブエージェントに委任**
4. 問題ゼロまで修正と検証を反復

作成者と検証者を別プロセスに分ける構造は、LLM-as-a-Judge で自己評価バイアスを避けるために評価者を分離するのと同じ原理。デザインガイドライン（配色・コントラスト・レイアウトの多様性・情報量）を SKILL.md に内蔵し、「テキストだけのスライドの連続」のようなありがちな失敗を規範で先回りして潰す。

## xlsx スキル — 数式ファーストという責務設計

他のドキュメントスキルにない明確な原則を持つ。

> 数式は Excel 内に記述し、Python で値を計算して埋め込むことは禁止する。

Python で計算した値をセルに書くと、元データを変えても更新されない死んだ値になる。`=SUM(B2:B10)` を書けば Excel 本来の自動再計算が生きる。

この原則を並べると、計算の責務は成果物の性質で決まることが見える。

| 形式 | 計算の置き場 | 理由 |
|---|---|---|
| 全形式共通 | LLM の暗算は禁止 | 再現性がない |
| PDF / docx（静的文書） | Python スクリプト | 出力時点で値が確定すればよい |
| xlsx（生きたモデル） | Excel 数式 | 受け取った人がデータを変えて再計算する |

検証も同じ思想で、`recalc.py` が LibreOffice ヘッドレスで全数式を再計算し、#REF! や #DIV/0! をゼロにするまで修正する。決定論的なチェックをスクリプトに寄せる Agent Skills の設計原則の実例になっている。

もう 1 つの注目点は財務モデルの色分け慣習（青=入力値、黒=数式、緑=シート間参照、赤=外部リンク、黄背景=仮定値）が SKILL.md に組み込まれていること。投資銀行やコンサルの業界慣習、つまり文書化されにくい暗黙知をスキルがエンコードしている。

## 2026 年時点の状況（リサーチ）

- 公式ドキュメントスキルは docx / pdf / pptx / xlsx の 4 種。production の Claude のドキュメント能力を支える実物で、ライセンスは source-available（他の公式スキル例の多くは Apache 2.0）
- 既知の弱点は日本語（CJK）フォント。HTML 経由の PDF 生成で CJK フォント未導入だと豆腐（□）になる報告が最頻出。コミュニティ製の代替 pdf スキルが CJK 自動フォント対応を売りにするほどで、日本語運用では明示的なフォント指定が必須
- 小フォント多ページや複雑な表の PDF は、読み取りでコンテキストウィンドウを先に使い切ることがある
- MCP との使い分けの公式フレーズは「MCP connects Claude to data; Skills teach Claude what to do with that data」。外部システムに触れないなら Skill を既定にし、live 接続が必要になったら MCP に昇格する整理が定着
- 配布は plugin が単位（skill + hooks + MCP 設定の束）。`/plugin marketplace add <owner>/<repo>` で任意の git リポを marketplace 登録できる

出典
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- https://github.com/anthropics/skills
- https://claude.com/blog/skills-explained
- https://platform.claude.com/docs/en/build-with-claude/pdf-support

## このリポジトリへの反映

- `skills/document-processing/` — pdf / docx 操作の手順スキル。ライブラリ選定表と日本語フォント対応を内蔵し、公式スキルがない環境での補完として使う
- 数値集計は必ずスクリプトで計算する規範は `agent-skills.md` の「LLM が得意 / 苦手の分業」と同じ原則
