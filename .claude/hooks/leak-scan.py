#!/usr/bin/env python3
"""PreToolUse hook: 公開リポへの git commit 前に、ステージ済み差分の追加行をリーク検査する。

検出したら exit 2 で commit をブロックし、該当箇所を stderr で Claude に返す。
git commit 以外のコマンド、JSON でない入力、git 差分が取れない場合は何もせず通す。
社名や個人情報の形はこのファイルに書くと公開されるので、リポジトリの外のファイルから読む。
"""

import json
import os
import re
import subprocess
import sys

# 形そのものを公開してよいものだけをここに書く
PATTERNS = {
    "API キー (Google)": r"AIzaSy[0-9A-Za-z_\-]{20,}",
    "API キー (Gemini)": r"AQ\.[0-9A-Za-z_\-]{40,}",
    "API キー (OpenAI/Anthropic)": r"sk-[A-Za-z0-9]{20,}",
    "ローカルパス": r"/Users/[A-Za-z0-9._\-]+",
}

PRIVATE_PATTERNS_ENV = "LEAK_SCAN_PATTERNS"
PRIVATE_PATTERNS_DEFAULT = "~/.config/leak-scan/patterns.tsv"


def load_private_patterns(path):
    """「ラベル<TAB>正規表現」の行を読む。ファイルが無いときと、壊れた行は飛ばす。"""
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    patterns = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#") or "\t" not in line:
            continue
        label, regex = line.split("\t", 1)
        try:
            patterns.append((label.strip(), re.compile(regex)))
        except re.error:
            continue
    return patterns


def all_patterns():
    public = [(label, re.compile(regex)) for label, regex in PATTERNS.items()]
    path = os.environ.get(PRIVATE_PATTERNS_ENV, PRIVATE_PATTERNS_DEFAULT)
    return public + load_private_patterns(path)


def added_lines(diff):
    """追加行だけを返す。削除行とファイルヘッダは除く。"""
    return "\n".join(
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def scan(added, patterns):
    hits = set()
    for label, pattern in patterns:
        for match in pattern.finditer(added):
            hits.add(f"  - {label}: {match.group(0)}")
    return hits


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    command = payload.get("tool_input", {}).get("command", "")
    if "git commit" not in command:
        sys.exit(0)

    # 検査のスクリプトとテストはパターンの文字列を含むので、検査の対象から外す
    try:
        diff = subprocess.run(
            [
                "git",
                "diff",
                "--cached",
                "--",
                ".",
                ":!.claude/hooks/leak-scan.py",
                ":!.claude/hooks/test_leak_scan.py",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        sys.exit(0)

    hits = scan(added_lines(diff), all_patterns())
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
