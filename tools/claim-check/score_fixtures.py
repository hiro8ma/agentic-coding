#!/usr/bin/env python3
"""fixture の Markdown で claim_check の適合率と再現率を測る。

Usage:
    python3 score_fixtures.py [DIR ...]   # 既定は fixtures/dev と fixtures/blind

正解は、拾うべき主張が始まる行の末尾に `<!-- expect: absence, number -->` の形で書く。
印のない行は、何も拾わないのが正解。claim_check は HTML のコメントを読む前に除く。
行と種類の組で比べる。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import claim_check as cc

_EXPECT = re.compile(r"<!--\s*expect:\s*([a-z,\s]+?)\s*-->")


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


def expectations(text: str) -> set[tuple[int, str]]:
    found: set[tuple[int, str]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in _EXPECT.finditer(line):
            for kind in match.group(1).split(","):
                kind = kind.strip()
                if kind not in cc.KINDS:
                    raise ValueError(f"{lineno}行目の種類 {kind!r} を読めない")
                found.add((lineno, kind))
    return found


def score_files(paths: list[Path]) -> dict[str, Score]:
    scores = {kind: Score() for kind in cc.KINDS}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        want = expectations(text)
        got = {(flag.line, flag.kind) for flag in cc.check_text(text).flags}
        for line, kind in sorted(got | want):
            score = scores[kind]
            if (line, kind) in got and (line, kind) in want:
                score.tp += 1
            elif (line, kind) in got:
                score.fp += 1
                score.misses.append(f"誤検知 {path.name}:{line}")
            else:
                score.fn += 1
                score.misses.append(f"見逃し {path.name}:{line}")
    return scores


def format_scores(name: str, scores: dict[str, Score]) -> str:
    total = Score(
        sum(s.tp for s in scores.values()),
        sum(s.fp for s in scores.values()),
        sum(s.fn for s in scores.values()),
    )
    rows = [
        f"## {name}",
        "",
        "| 種類 | TP | FP | FN | 適合率 | 再現率 |",
        "|---|---|---|---|---|---|",
    ]
    for label, score in [*scores.items(), ("合計", total)]:
        rows.append(
            f"| {label} | {score.tp} | {score.fp} | {score.fn} "
            f"| {score.precision:.2f} | {score.recall:.2f} |"
        )
    misses = [miss for score in scores.values() for miss in score.misses]
    if misses:
        rows.append("")
        rows.extend(f"- {miss}" for miss in misses)
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    dirs = [Path(arg) for arg in (argv if argv is not None else sys.argv[1:])]
    if not dirs:
        dirs = [HERE / "fixtures" / "dev", HERE / "fixtures" / "blind"]
    for index, directory in enumerate(dirs):
        if index:
            print()
        paths = sorted(directory.glob("*.md"))
        print(format_scores(f"{directory.name}（{len(paths)}件）", score_files(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
