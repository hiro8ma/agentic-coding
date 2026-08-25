#!/usr/bin/env python3
"""週報テキストが必須セクションを含むか検証する。

Usage:
    python validate.py <report-file>

終了コード 0 で合格、1 で不足あり、2 で引数・入力エラー。
"""
import re
import sys

# 表記ゆれを許容するため、各セクションを正規表現の選択肢で定義する。
REQUIRED_SECTIONS = {
    "実績": r"実績|成果|やったこと|done|achievements?",
    "課題": r"課題|問題|ブロッカー|懸念|issues?|blockers?",
    "次週予定": r"次週|来週|予定|計画|next ?week|plan",
}

HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$", re.MULTILINE)


def extract_headings(text: str) -> list[str]:
    return HEADING.findall(text)


def validate(text: str) -> list[str]:
    headings = " \n".join(extract_headings(text))
    missing = []
    for label, pattern in REQUIRED_SECTIONS.items():
        if not re.search(pattern, headings, re.IGNORECASE):
            missing.append(label)
    return missing


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python validate.py <report-file>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"ファイルを開けません: {e}", file=sys.stderr)
        return 2

    missing = validate(text)
    if missing:
        print("不足セクション: " + ", ".join(missing))
        print("週報には実績・課題・次週予定の見出しが必要です。")
        return 1
    print("OK: 必須セクション（実績・課題・次週予定）を確認しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
