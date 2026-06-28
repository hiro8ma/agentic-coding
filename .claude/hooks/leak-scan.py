#!/usr/bin/env python3
"""PreToolUse hook: 公開リポへの git commit 前に、ステージ済み差分の追加行をリーク検査する。

検出したら exit 2 で commit をブロックし、該当箇所を stderr で Claude に返す。
git commit 以外のコマンド、JSON でない入力、git 差分が取れない場合は何もせず通す。
"""
import json
import re
import subprocess
import sys

# 公開リポに出してはいけないパターン
PATTERNS = {
    "API キー (Google)": r"AIzaSy[0-9A-Za-z_\-]{20,}",
    "API キー (OpenAI/Anthropic)": r"sk-[A-Za-z0-9]{20,}",
    "ローカルパス": r"/Users/[A-Za-z0-9._\-]+",
    "現職 org / リポ名": r"SSK-TBD",
    "個人メール": r"hiro8masu@",
}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    command = payload.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        sys.exit(0)

    # 検出スクリプト自身はパターン文字列を含むため、スキャン対象から除外する
    try:
        diff = subprocess.run(
            ["git", "diff", "--cached", "--", ".", ":!.claude/hooks/leak-scan.py"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        sys.exit(0)

    # 追加行だけを対象にする（削除行・ファイルヘッダは除く）
    added = "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )

    hits = set()
    for label, pattern in PATTERNS.items():
        for match in re.finditer(pattern, added):
            hits.add(f"  - {label}: {match.group(0)}")

    if hits:
        print(
            "リーク検査で公開禁止の内容を検出した。commit を中止する。\n"
            + "\n".join(sorted(hits))
            + "\n該当箇所を削除してから再度 commit する。",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
