"""テストと試し実行に使う、決定的なレビューのコマンド。追加した行に目印の語があれば、その行を指摘する。

Usage:
    git show HEAD | python3 fake_reviewer.py
"""

from __future__ import annotations

import json
import re
import sys

FLAG_RE = re.compile(r"\b(TODO|FIXME|sleep|eval)\b")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def review(diff: str) -> list[dict]:
    findings: list[dict] = []
    path: str | None = None
    line = 0
    in_header = False
    for text in diff.splitlines():
        if text.startswith("diff --git "):
            in_header, path = True, None
        elif in_header and text.startswith("+++ "):
            target = text[4:].rstrip("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
        elif match := HUNK_RE.match(text):
            in_header, line = False, int(match[1])
        elif not in_header and path is not None and text[:1] in ("+", " "):
            if text.startswith("+") and (flag := FLAG_RE.search(text)):
                findings.append({"file": path, "line": line, "summary": f"{flag[1]} を含む行がある"})
            line += 1
    return findings


def main() -> int:
    for finding in review(sys.stdin.read()):
        print(json.dumps(finding, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
