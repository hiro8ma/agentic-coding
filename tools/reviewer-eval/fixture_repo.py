"""reviewer_eval のテストと試し実行に使う、架空の git リポジトリを作る。

Usage:
    python3 fixture_repo.py DIR

DIR/repo にリポジトリを、DIR/keywords.json に revert のケースごとの語を書く。
revert のケースは、検出できる / 一部だけ revert した / 検出できない / revert が取り消された / 対象がない。
clean のケースは、--clean-window 3 で2件になる（指摘が出ないもの1件、出るもの1件）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PRICING = """def subtotal(items):
    return sum(item["price"] * item["qty"] for item in items)


def tax(amount, rate):
    return round(amount * rate, 2)


def total(items, rate):
    amount = subtotal(items)
    return amount + tax(amount, rate)
"""

DISCOUNT = """

def discount(amount, member):
    # TODO confirm the member rate
    return amount * 0.1 if member else amount
"""

CLIENT = """import time


def fetch(session, url, retries=3):
    for attempt in range(retries):
        response = session.get(url, timeout=5)
        if response.ok:
            return response
        time.sleep(1)
    raise RuntimeError(url)
"""

REPORT = """import csv


def write_report(path, rows):
    with open(path, "w", newline="") as handle:
        csv.writer(handle).writerows(rows)
"""

USAGE = "# Usage\n\nCall total(items, rate) to get the amount with tax.\nTODO describe the discount once it ships.\n"

README = "# sample\n\nSynthetic fixture for reviewer-eval.\n"

KEYWORDS = {
    "discount": ["discount", "rate"],
    "backoff": ["sleep", "backoff"],
    "truncate": ["round"],
}


def build(root: Path) -> dict[str, str]:
    """root にリポジトリを作り、ラベルからコミットの sha への辞書を返す。"""
    root.mkdir(parents=True, exist_ok=True)
    # 利用者の署名やフックの設定を読まず、日時を固定して sha を毎回同じにする
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.com",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.com",
    }
    clock = iter(range(1_700_000_000, 1_800_000_000, 60))

    def git(*args: str) -> str:
        stamp = f"{next(clock)} +0000"
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
            capture_output=True,
            text=True,
            check=True,
        )
        return proc.stdout.strip()

    def write(rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(message: str) -> str:
        git("add", "-A")
        git("commit", "-q", "-m", message)
        return git("rev-parse", "HEAD")

    def revert(sha: str) -> str:
        git("revert", "--no-edit", sha)
        return git("rev-parse", "HEAD")

    git("init", "-q", "-b", "main")
    write("app/pricing.py", PRICING)
    write("app/client.py", CLIENT)
    write("README.md", README)
    shas = {"base": commit("Add pricing and client")}

    write("app/report.py", REPORT)
    shas["add_report"] = commit("Add CSV report")

    write("app/pricing.py", PRICING + DISCOUNT)
    shas["discount"] = commit("Add member discount")
    shas["revert_discount"] = revert(shas["discount"])

    write("docs/usage.md", USAGE)
    shas["add_usage"] = commit("Document usage")

    write("app/client.py", CLIENT.replace("time.sleep(1)", "time.sleep(30)"))
    write("README.md", README + "Retries back off for 30 seconds. TODO list the limits.\n")
    shas["backoff"] = commit("Lengthen retry backoff")
    write("app/client.py", CLIENT)
    shas["revert_backoff"] = commit(
        f'Revert "Lengthen retry backoff"\n\nThis reverts commit {shas["backoff"]}.\nThe README change stays.'
    )

    write("app/pricing.py", PRICING.replace("round(amount * rate, 2)", "int(amount * rate)"))
    shas["truncate"] = commit("Truncate tax to whole units")
    shas["revert_truncate"] = revert(shas["truncate"])

    write("app/client.py", CLIENT.replace("retries", "attempts"))
    shas["rename"] = commit("Rename retry parameter")
    write("app/config.py", "TIMEOUT = 5\n")
    shas["add_config"] = commit("Add config")
    shas["revert_rename"] = revert(shas["rename"])
    shas["reland_rename"] = revert(shas["revert_rename"])
    write("app/config.py", "TIMEOUT = 10\n")
    shas["tune_config"] = commit("Raise the default timeout")

    write("README.md", (root / "README.md").read_text(encoding="utf-8") + "\nSee the source for details.\n")
    shas["no_trailer"] = commit('Revert "Drop the old banner"')
    return shas


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python3 fixture_repo.py DIR", file=sys.stderr)
        return 2
    target = Path(argv[0])
    if target.exists() and any(target.iterdir()):
        print(f"空のディレクトリを指定する: {argv[0]}", file=sys.stderr)
        return 2
    shas = build(target / "repo")
    keywords = {shas[label]: words for label, words in KEYWORDS.items()}
    (target / "keywords.json").write_text(json.dumps(keywords, indent=2) + "\n", encoding="utf-8")
    for label, sha in shas.items():
        print(f"{sha[:8]}  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
