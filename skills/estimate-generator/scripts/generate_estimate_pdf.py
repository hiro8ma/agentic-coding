#!/usr/bin/env python3
"""見積書の JSON を受け取り、金額を計算して PDF を出力する。

金額の集計と端数処理はここで完結させる。
LLM に計算させると桁を落としたり消費税を二重に掛けたりするため、
計算結果を検算できる形でスクリプトに閉じ込めている。

PDF 化は Chrome のヘッドレスを既定にしている。
WeasyPrint は glib / pango などのシステムライブラリを要求し、
入っていない環境では import の時点で落ちる。
Chrome は macOS なら大抵入っており、追加の導入が要らない。

使い方:
    python3 generate_estimate_pdf.py input.json output.pdf
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

TAX_RATE = Decimal("0.10")
VALID_DAYS = 30

COMPANY = {
    "name": "株式会社技術評論デザイン",
    "postal": "〒160-0022",
    "address": "東京都新宿区新宿2丁目xx-xx",
    "tel": "03-xxxx-xxxx",
    "email": "info@example.com",
    "bank": "○○銀行 新宿支店 普通 1234567 カ）ギジュツヒョウロンデザイン",
}


@dataclass(frozen=True)
class Line:
    name: str
    unit_price: Decimal
    quantity: Decimal
    unit: str
    note: str = ""

    @property
    def amount(self) -> Decimal:
        # 小数の数量（人日 0.5 など）を許すため Decimal で掛けてから切り捨てる。
        return (self.unit_price * self.quantity).quantize(Decimal("1"), rounding=ROUND_DOWN)


def yen(v: Decimal) -> str:
    return f"{v:,}"


def qty(v: Decimal) -> str:
    """数量を表示用の文字列にする。

    Decimal.normalize() は 40 を 4E+1 に変えてしまうため直接は使えない。
    整数なら整数として、小数なら末尾の 0 を落として返す。
    """
    if v == v.to_integral_value():
        return str(v.quantize(Decimal("1")))
    return str(v.normalize())


def build_lines(items: list[dict]) -> tuple[list[Line], Decimal]:
    """明細を組み立て、比率指定（単位が ％）の品目を後から解決する。

    ディレクション費のように「制作費の 15%」で決まる品目があるため、
    先に固定額の小計を出してから比率行を計算する。
    """
    fixed: list[Line] = []
    ratio_items: list[dict] = []

    for it in items:
        if it.get("unit") == "％":
            ratio_items.append(it)
            continue
        fixed.append(
            Line(
                name=it["name"],
                unit_price=Decimal(str(it["unit_price"])),
                quantity=Decimal(str(it.get("quantity", 1))),
                unit=it.get("unit", "式"),
                note=it.get("note", ""),
            )
        )

    base = sum((l.amount for l in fixed), Decimal("0"))

    lines = list(fixed)
    for it in ratio_items:
        rate = Decimal(str(it["unit_price"])) / Decimal("100")
        amount = (base * rate).quantize(Decimal("1"), rounding=ROUND_DOWN)
        lines.append(
            Line(
                name=it["name"],
                unit_price=amount,
                quantity=Decimal("1"),
                unit="式",
                note=it.get("note") or f"制作費の {it['unit_price']}%",
            )
        )

    subtotal = sum((l.amount for l in lines), Decimal("0"))
    return lines, subtotal


def render_html(data: dict) -> str:
    lines, subtotal = build_lines(data["items"])
    tax = (subtotal * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)
    total = subtotal + tax

    issued = date.fromisoformat(data["issue_date"]) if data.get("issue_date") else date.today()
    valid_until = issued + timedelta(days=data.get("valid_days", VALID_DAYS))

    rows = "\n".join(
        f"""<tr>
          <td class="name">{l.name}{f'<span class="note">{l.note}</span>' if l.note else ''}</td>
          <td class="num">{yen(l.unit_price)}</td>
          <td class="qty">{qty(l.quantity)} {l.unit}</td>
          <td class="num">{yen(l.amount)}</td>
        </tr>"""
        for l in lines
    )

    remarks = data.get("remarks", "")
    remarks_block = (
        f'<section class="remarks"><h2>備考</h2><p>{remarks}</p></section>' if remarks else ""
    )

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<style>
  @page {{ size: A4 portrait; margin: 18mm 16mm; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
    font-size: 10pt; color: #111; line-height: 1.6; margin: 0;
  }}
  h1 {{ font-size: 22pt; letter-spacing: 8px; text-align: center; margin: 0 0 10mm; }}
  .meta {{ display: flex; justify-content: space-between; margin-bottom: 8mm; }}
  .client {{ width: 55%; }}
  .client .to {{ font-size: 14pt; border-bottom: 1.5px solid #111; padding-bottom: 3mm; margin-bottom: 4mm; }}
  .issuer {{ width: 42%; font-size: 9pt; text-align: right; }}
  .issuer .name {{ font-size: 11pt; font-weight: 700; margin-bottom: 1mm; }}
  .nums {{ font-size: 9pt; text-align: right; margin-bottom: 4mm; }}
  .total-box {{
    border: 2px solid #111; padding: 4mm 5mm; margin-bottom: 8mm;
    display: flex; justify-content: space-between; align-items: baseline;
  }}
  .total-box .label {{ font-size: 11pt; font-weight: 700; }}
  .total-box .value {{ font-size: 18pt; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 6mm; }}
  th {{ background: #f0f0f0; border: 1px solid #999; padding: 2.5mm; font-size: 9pt; }}
  td {{ border: 1px solid #999; padding: 2.5mm; }}
  td.num {{ text-align: right; white-space: nowrap; }}
  td.qty {{ text-align: center; white-space: nowrap; }}
  .note {{ display: block; font-size: 8pt; color: #666; }}
  .summary {{ width: 62mm; margin-left: auto; border-collapse: collapse; }}
  .summary td {{ border: 1px solid #999; padding: 2.5mm; }}
  .summary td:last-child {{ text-align: right; white-space: nowrap; }}
  .summary tr.total td {{ font-weight: 700; background: #f0f0f0; }}
  .remarks {{ margin-top: 8mm; }}
  .remarks h2, .terms h2 {{ font-size: 10pt; margin: 0 0 2mm; }}
  .remarks p {{ border: 1px solid #999; padding: 3mm; min-height: 18mm; margin: 0; }}
  .terms {{ margin-top: 8mm; font-size: 9pt; }}
  .terms dl {{ margin: 0; }}
  .terms dt {{ float: left; width: 26mm; clear: left; color: #555; }}
  .terms dd {{ margin: 0 0 1mm 26mm; }}
</style></head><body>

<h1>御 見 積 書</h1>

<div class="meta">
  <div class="client">
    <div class="to">{data['client']} 御中</div>
    <div>件名: {data['subject']}</div>
  </div>
  <div class="issuer">
    <div class="name">{COMPANY['name']}</div>
    <div>{COMPANY['postal']} {COMPANY['address']}</div>
    <div>TEL {COMPANY['tel']}</div>
    <div>{COMPANY['email']}</div>
  </div>
</div>

<div class="nums">
  見積番号: {data['estimate_no']}　／　発行日: {issued:%Y年%m月%d日}
</div>

<div class="total-box">
  <span class="label">御見積金額（税込）</span>
  <span class="value">¥{yen(total)} −</span>
</div>

<table>
  <thead><tr><th>品目</th><th style="width:26mm">単価</th><th style="width:24mm">数量</th><th style="width:30mm">金額</th></tr></thead>
  <tbody>
{rows}
  </tbody>
</table>

<table class="summary">
  <tr><td>小計</td><td>¥{yen(subtotal)}</td></tr>
  <tr><td>消費税（{int(TAX_RATE * 100)}%）</td><td>¥{yen(tax)}</td></tr>
  <tr class="total"><td>合計</td><td>¥{yen(total)}</td></tr>
</table>

{remarks_block}

<section class="terms">
  <h2>お取引条件</h2>
  <dl>
    <dt>有効期限</dt><dd>{valid_until:%Y年%m月%d日}（発行日より {data.get('valid_days', VALID_DAYS)} 日間）</dd>
    <dt>支払条件</dt><dd>検収後 翌月末日 銀行振込</dd>
    <dt>振込先</dt><dd>{COMPANY['bank']}</dd>
    <dt>備考</dt><dd>振込手数料は貴社にてご負担をお願いいたします。</dd>
  </dl>
</section>

</body></html>"""


CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
]


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
        found = shutil.which(c)
        if found:
            return found
    return None


def html_to_pdf(html: str, dst: Path) -> str:
    """HTML を PDF にする。Chrome を優先し、無ければ WeasyPrint に落とす。

    どちらも無い場合は HTML だけ残して落ちる。
    ブラウザから手で印刷すれば同じ結果が得られるため、成果物は無駄にならない。
    """
    chrome = find_chrome()
    if chrome:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "estimate.html"
            src.write_text(html, encoding="utf-8")
            subprocess.run(
                [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                 f"--print-to-pdf={dst}", src.as_uri()],
                check=True, capture_output=True,
            )
        return "chrome"

    try:
        from weasyprint import HTML
    except Exception as e:
        raise SystemExit(
            f"Chrome も WeasyPrint も使えません: {e}\n"
            f"HTML は {dst.with_suffix('.html')} に出力済みです。ブラウザから印刷してください。"
        )
    HTML(string=html).write_pdf(dst)
    return "weasyprint"


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: generate_estimate_pdf.py <input.json> <output.pdf>")

    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))

    html = render_html(data)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # HTML も残す。PDF の崩れを調べるときはブラウザで開くのが速い。
    dst.with_suffix(".html").write_text(html, encoding="utf-8")

    engine = html_to_pdf(html, dst)

    lines, subtotal = build_lines(data["items"])
    tax = (subtotal * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_DOWN)
    print(f"PDF 生成完了: {dst}（{engine}）")
    print(f"  明細 {len(lines)} 行 / 小計 {yen(subtotal)} / 税 {yen(tax)} / 合計 {yen(subtotal + tax)}")


if __name__ == "__main__":
    main()
