---
name: document-processing
description: PDF と Word 文書（.docx）の作成・編集・結合・抽出の手順とライブラリ選定。「PDF を作成 / 結合 / 分割 / 抽出」「レポートを PDF に」「Word 文書を作成 / 編集」「docx を直して」等で起動。日本語文書のフォント対応を含む。
---

# Document Processing

PDF と .docx を扱うときの手順とライブラリ選定の規範。
公式スキル（anthropics/skills の pdf / docx）が導入済みの環境ではそちらを優先し、本スキルは手順知識の補完として使う。

## PDF のタスク別ツール選択

| タスク | ツール | 選定理由 |
|---|---|---|
| テキスト抽出 | pdfplumber | 表のレイアウトを保持して抽出できる |
| 結合・分割・回転 | pypdf | 依存が少なく高速 |
| 新規作成 | reportlab | レイアウトの自由度が高い |
| OCR | pytesseract + pdf2image | スキャン PDF を画像化して認識 |
| 暗号化・復号 | pypdf / qpdf | パスワード保護の付与・解除 |

ツール名の指定がないリクエストでは、この表に従って自動選択する。

## 日本語 PDF の必須事項（最優先で確認）

- reportlab はデフォルトで日本語グリフを持たない。**フォント登録なしで日本語を描画すると豆腐（□）になる**
- 対応は 2 択。TTF 登録（Noto Sans JP 等を `TTFont` で登録）か、CID フォント（`HeiseiKakuGo-W5` + `UnicodeCIDFont`）
- HTML 経由の生成（weasyprint 等）も CJK フォント未導入の環境では文字化けする。生成後に必ず日本語部分を目視確認する
- OCR で日本語を扱うときは tesseract の `jpn` 言語データが必要（`tesseract --list-langs` で確認）

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont("NotoSansJP", "NotoSansJP-Regular.ttf"))
```

## PDF レポート生成の手順

1. データを pandas で読み込み、集計（合計・前月比・ランキング）を**コードで**計算する。LLM の暗算で数値を出すことは禁止
2. 構成（タイトル・セクション・表・グラフ）を確認してから reportlab で組み立てる
3. ヘッダー・フッター・ページ番号を付与する
4. 生成後に開いて、数値の一致と日本語の描画を確認する

## PDF の結合・分割

```python
from pypdf import PdfWriter
writer = PdfWriter()
for path in ["report_01.pdf", "report_02.pdf"]:
    writer.append(path)
writer.write("combined_report.pdf")
```

- 結合後は合計ページ数が元ファイルの和と一致することを確認する
- パスワード付き PDF は先に `decrypt()` してから操作する

## .docx の使い分け — 新規はライブラリ、編集は XML

| 場面 | 手段 | 理由 |
|---|---|---|
| 新規作成 | docx-js（または python-docx） | 見出し・表・目次を構造的に組み立てられる |
| 既存文書の編集 | ZIP 展開 + XML 直接編集 | 元のフォーマット・スタイルを完全に保持できる |

ライブラリで既存文書を読み込んで書き戻すと、ライブラリが解釈できない書式が欠落することがある。
テンプレートへの差し込みや一括置換は XML 直接編集を選ぶ。

## .docx 編集の手順（Unpack → Edit → Repack）

1. **Unpack** — .docx を ZIP として展開する（本文は `word/document.xml`）
2. **Edit** — XML を編集する。テキスト置換は `<w:t>` 要素の中身だけを対象にし、タグ構造を壊さない
3. **Repack** — ZIP に戻して .docx として保存する

```bash
mkdir unpacked && cd unpacked && unzip -q ../input.docx
# word/document.xml を編集
zip -q -r ../output.docx . -x ".*" && cd ..
```

- 編集後は必ず開いて（または python-docx でロードして）壊れていないことを確認する
- 追跡変更（Track Changes）が残った文書は、一括承認してから内容編集に入る

## 新規 .docx 作成の注意（docx-js）

- ページサイズは明示的に指定する（デフォルト任せにしない）
- 見出しは見出しスタイル ID（`Heading1` 等）で付ける。装飾だけの疑似見出しは目次生成が壊れる
- 箇条書きは numbering 定義を使う。ハイフン手打ちはインデントが崩れる

## 出力前チェックリスト

- [ ] 数値はすべてスクリプトで計算したか（LLM の暗算が混ざっていないか）
- [ ] 日本語が正しく描画されているか（豆腐・文字化けなし）
- [ ] 生成ファイルを開いて確認したか
- [ ] 元ファイルを上書きしていないか（編集は別名保存が既定）
