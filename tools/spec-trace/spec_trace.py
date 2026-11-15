#!/usr/bin/env python3
"""仕様のファイルの規則の ID と、その ID を参照するテストを結ぶ。

Usage:
    python3 spec_trace.py [ROOT]                     # Markdown で出す
    python3 spec_trace.py --json ROOT                # JSON で出す
    python3 spec_trace.py --spec docs/rules.md ROOT  # 読む仕様を指定する
    python3 spec_trace.py --tests 'src/**/*.py' ROOT # 読むテストを指定する
    python3 spec_trace.py --prefix FR ROOT           # 角括弧のない FR-001 も ID として読む
    python3 spec_trace.py --report-only ROOT         # 見つけても終了コード0

仕様（既定は ROOT/specs/**/*.md と ROOT/.steering/*/requirements.md）の箇条書きと見出しの
先頭にある ID（[SHIP-1] / AC-1 / AC1）を規則として読み、テストのファイルの中で同じ ID に
触れる行を探す。
テストのない規則と、どの仕様も定義していない ID への参照を出す。
ID で結ぶだけで、テストが規則を確かめているかは見ない。

終了コードは、テストのない規則もどの仕様にもない参照もなければ0、あれば1
（--report-only なら0）、ROOT か --spec のパスを読めなければ2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_BARE_PREFIXES = ("AC",)
DEFAULT_TEST_PATTERNS = (
    "test_*.py",
    "*_test.py",
    "*_test.go",
    "*.test.ts",
    "*.spec.ts",
    "*.test.tsx",
    "*.spec.tsx",
    "*.test.js",
    "*.spec.js",
)
SKIP_DIRS = frozenset(
    {
        "node_modules",
        "vendor",
        "venv",
        "dist",
        "build",
        "target",
        "coverage",
        "__pycache__",
        "fixtures",
        "testdata",
    }
)
TEXT_WIDTH = 40
SNIPPET_WIDTH = 50

_FENCE = re.compile(r"^ *(`{3,}|~{3,})")
_LINE_START = re.compile(
    r"^(?P<indent> *)(?:(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?"
    r"|(?P<heading>#{1,6})\s+)(?P<rest>.*)$"
)
_ITEM_LINE = re.compile(r"^( *)(?:[-*+]|\d{1,3}[.)])\s+")
_HEADING_LINE = re.compile(r"^ {0,3}#{1,6}\s")
_TEXT_LEAD = re.compile(r"^[\s:：.)）、,\-—]+")


@dataclass(frozen=True)
class Location:
    file: str
    line: int
    text: str


@dataclass
class Rule:
    id: str
    file: str
    line: int
    text: str
    tests: list[Location] = field(default_factory=list)


def canonical(prefix: str, number: str) -> str:
    return f"{prefix.upper()}-{int(number)}"


def definition_pattern(bare_prefixes: tuple[str, ...]) -> re.Pattern[str]:
    bare = "|".join(re.escape(p) for p in sorted(bare_prefixes, key=len, reverse=True))
    bare_part = rf"|\[?(?P<bp>{bare})-?(?P<bn>\d+)\]?" if bare else ""
    return re.compile(
        r"^(?:\*\*|__|`)?"
        rf"(?:\[(?P<p>[A-Z][A-Z0-9]*)-(?P<n>\d+)\]{bare_part})"
        r"(?:\*\*|__|`)?(?![A-Za-z0-9(\]])"
    )


def _continuation(lines: list[str], start: int, indent: int, is_heading: bool) -> str:
    parts: list[str] = []
    for raw in lines[start:]:
        if not raw.strip():
            if parts:
                break
            continue
        if _HEADING_LINE.match(raw):
            break
        item = _ITEM_LINE.match(raw)
        if item and (is_heading or len(item.group(1)) <= indent):
            break
        if _FENCE.match(raw):
            continue
        parts.append(_ITEM_LINE.sub("", raw).strip())
    return " ".join(parts)


def parse_spec(text: str, file: str, bare_prefixes: tuple[str, ...]) -> list[Rule]:
    pattern = definition_pattern(bare_prefixes)
    lines = text.splitlines()
    rules: list[Rule] = []
    fence: str | None = None
    for index, raw in enumerate(lines):
        opening = _FENCE.match(raw)
        if fence is not None:
            if (
                opening
                and opening.group(1)[0] == fence[0]
                and len(opening.group(1)) >= len(fence)
            ):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            continue
        start = _LINE_START.match(raw)
        if not start:
            continue
        rest = start.group("rest").strip()
        found = pattern.match(rest)
        if not found:
            continue
        if found.group("p"):
            rule_id = canonical(found.group("p"), found.group("n"))
        else:
            rule_id = canonical(found.group("bp"), found.group("bn"))
        body = _TEXT_LEAD.sub("", rest[found.end() :])
        if start.group("heading"):
            body = body.rstrip(" #")
        if not body:
            body = _continuation(
                lines,
                index + 1,
                len(start.group("indent")),
                bool(start.group("heading")),
            )
        rules.append(Rule(rule_id, file, index + 1, body))
    return rules


def reference_pattern(prefixes: set[str]) -> re.Pattern[str] | None:
    if not prefixes:
        return None
    names = "|".join(re.escape(p) for p in sorted(prefixes, key=len, reverse=True))
    # test_ship_1 と TestAC1 を拾うため _ と Test の後も境界にし、区切りのない形は16進に当たらないよう大文字だけにする
    return re.compile(
        rf"(?:(?<![A-Za-z0-9])|(?<=Test))"
        rf"(?:(?P<p>(?i:{names}))[-_]|(?P<q>{names}))(?P<n>\d+)"
    )


def find_references(
    text: str, file: str, pattern: re.Pattern[str] | None
) -> list[tuple[str, Location]]:
    if pattern is None:
        return []
    found: list[tuple[str, Location]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        seen: set[str] = set()
        for match in pattern.finditer(line):
            prefix = match.group("p") or match.group("q")
            rule_id = canonical(prefix, match.group("n"))
            if rule_id in seen:
                continue
            seen.add(rule_id)
            found.append((rule_id, Location(file, number, line.strip())))
    return found


def _walk(directory: Path) -> list[Path]:
    paths: list[Path] = []
    for current, dirs, files in os.walk(directory):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS
        )
        paths.extend(Path(current) / name for name in files)
    return paths


def _resolve(root: Path, path: str) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else root / candidate


def find_spec_files(root: Path, specs: list[str]) -> list[Path]:
    if specs:
        found: list[Path] = []
        for spec in specs:
            target = _resolve(root, spec)
            if target.is_dir():
                found.extend(p for p in _walk(target) if p.suffix == ".md")
            else:
                found.append(target)
        return sorted(set(found))
    found = []
    if (root / "specs").is_dir():
        found.extend(p for p in _walk(root / "specs") if p.suffix == ".md")
    steering = root / ".steering"
    if steering.is_dir():
        found.extend(p for p in steering.glob("*/requirements.md") if p.is_file())
    return sorted(set(found))


def find_test_files(root: Path, globs: list[str]) -> list[Path]:
    if globs:
        found = {p for pattern in globs for p in root.glob(pattern) if p.is_file()}
    else:
        found = {
            p
            for p in _walk(root)
            if any(
                fnmatch.fnmatchcase(p.name, pattern)
                for pattern in DEFAULT_TEST_PATTERNS
            )
        }
    return sorted(found)


def _display(root: Path, path: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build_report(
    root: Path,
    root_label: str,
    specs: list[str],
    tests: list[str],
    extra_prefixes: list[str],
) -> dict:
    bare = tuple(dict.fromkeys([*DEFAULT_BARE_PREFIXES, *extra_prefixes]))
    spec_files = find_spec_files(root, specs)
    spec_set = {p.resolve() for p in spec_files}
    test_files = [
        p for p in find_test_files(root, tests) if p.resolve() not in spec_set
    ]

    rules: list[Rule] = []
    for path in spec_files:
        rules.extend(parse_spec(_read(path), _display(root, path), bare))

    defined = {rule.id for rule in rules}
    prefixes = {rule.id.rsplit("-", 1)[0] for rule in rules} | set(extra_prefixes)
    pattern = reference_pattern(prefixes)
    references: list[tuple[str, Location]] = []
    for path in test_files:
        references.extend(find_references(_read(path), _display(root, path), pattern))

    by_id: dict[str, list[Location]] = {}
    for rule_id, location in references:
        by_id.setdefault(rule_id, []).append(location)
    for rule in rules:
        rule.tests = by_id.get(rule.id, [])

    tested = sorted({rule.id for rule in rules if rule.tests})
    untested = [rule for rule in rules if not rule.tests]
    stale = [
        {"id": rule_id, **asdict(location)}
        for rule_id, location in references
        if rule_id not in defined
    ]
    definitions: dict[str, list[Rule]] = {}
    for rule in rules:
        definitions.setdefault(rule.id, []).append(rule)
    duplicates = [
        {
            "id": rule_id,
            "definitions": [{"file": r.file, "line": r.line} for r in found],
        }
        for rule_id, found in sorted(definitions.items())
        if len(found) > 1
    ]

    return {
        "root": root_label,
        "spec_files": [_display(root, p) for p in spec_files],
        "test_files": [_display(root, p) for p in test_files],
        "summary": {
            "rules": len(defined),
            "tested": len(tested),
            "coverage": round(len(tested) / len(defined), 4) if defined else None,
            "untested": len({rule.id for rule in untested}),
            "stale": len(stale),
            "duplicated": len(duplicates),
        },
        "rules": [
            {
                "id": rule.id,
                "file": rule.file,
                "line": rule.line,
                "text": rule.text,
                "tests": [{"file": t.file, "line": t.line} for t in rule.tests],
            }
            for rule in rules
        ],
        "untested": [
            {"id": rule.id, "file": rule.file, "line": rule.line, "text": rule.text}
            for rule in untested
        ],
        "stale": stale,
        "duplicates": duplicates,
    }


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width] + "…"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _test_cell(tests: list[dict]) -> str:
    if not tests:
        return "なし"
    lines: dict[str, list[str]] = {}
    for test in tests:
        lines.setdefault(test["file"], []).append(str(test["line"]))
    return " / ".join(f"{file}:{','.join(numbers)}" for file, numbers in lines.items())


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    out = [
        "# spec-trace",
        "",
        f"ルート {report['root']}",
        f"読んだ仕様{len(report['spec_files'])}件 / テスト{len(report['test_files'])}件",
    ]
    if not report["spec_files"]:
        out.append("仕様のファイルが見つからない")
    if summary["rules"]:
        out.append(
            f"規則{summary['rules']}件のうち、テストが ID で参照する規則"
            f"{summary['tested']}件（{summary['tested'] / summary['rules'] * 100:.1f}%）"
        )
    else:
        out.append("規則0件")
    out += [
        f"テストのない規則{summary['untested']}件",
        f"どの仕様にもない ID への参照{summary['stale']}件",
        f"複数の場所で定義された ID {summary['duplicated']}件",
        "",
        "ID で結ぶだけで、テストが規則を確かめているかは見ない",
    ]
    if report["rules"]:
        out += [
            "",
            "## 規則とテスト",
            "",
            "| ID | 仕様 | 規則 | テスト |",
            "|---|---|---|---|",
        ]
        for rule in report["rules"]:
            out.append(
                f"| {rule['id']} | {rule['file']}:{rule['line']} | "
                f"{_cell(_truncate(rule['text'], TEXT_WIDTH))} | {_cell(_test_cell(rule['tests']))} |"
            )
    if report["untested"]:
        out += ["", "## テストのない規則", ""]
        for rule in report["untested"]:
            out.append(
                f"- {rule['id']} {rule['file']}:{rule['line']}"
                f"「{_truncate(rule['text'], TEXT_WIDTH)}」"
            )
    if report["stale"]:
        out += ["", "## どの仕様にもない ID への参照", ""]
        for ref in report["stale"]:
            out.append(
                f"- {ref['id']} {ref['file']}:{ref['line']}"
                f"「{_truncate(ref['text'], SNIPPET_WIDTH)}」"
            )
    if report["duplicates"]:
        out += ["", "## 複数の場所で定義された ID", ""]
        for duplicate in report["duplicates"]:
            places = " / ".join(
                f"{d['file']}:{d['line']}" for d in duplicate["definitions"]
            )
            out.append(f"- {duplicate['id']} {places}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "root", nargs="?", default=".", help="リポジトリのルート（既定は .）"
    )
    parser.add_argument(
        "--spec",
        action="append",
        default=[],
        help="読む仕様のファイルかディレクトリ。ROOT からの相対。何度でも付けられ、付けると既定の場所を読まない",
    )
    parser.add_argument(
        "--tests",
        action="append",
        default=[],
        help="読むテストの glob。ROOT からの相対。何度でも付けられ、付けると既定の形を読まない",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[],
        help="ID の接頭辞として扱う名前。角括弧のない形も仕様から読み、テストでも探す",
    )
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    parser.add_argument(
        "--report-only", action="store_true", help="見つけても終了コード0を返す"
    )
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"spec-trace: ディレクトリを読めない: {args.root}", file=sys.stderr)
        return 2
    missing = [spec for spec in args.spec if not _resolve(root, spec).exists()]
    if missing:
        print(
            f"spec-trace: 仕様のパスを読めない: {', '.join(missing)}", file=sys.stderr
        )
        return 2
    absolute = [glob for glob in args.tests if Path(glob).is_absolute()]
    if absolute:
        print(
            f"spec-trace: --tests は ROOT からの相対の glob にする: {', '.join(absolute)}",
            file=sys.stderr,
        )
        return 2
    bad = [p for p in args.prefix if not re.fullmatch(r"[A-Z][A-Z0-9]*", p)]
    if bad:
        print(
            f"spec-trace: 接頭辞は英大文字で始まる英大文字と数字にする: {', '.join(bad)}",
            file=sys.stderr,
        )
        return 2

    report = build_report(root, args.root, args.spec, args.tests, args.prefix)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_markdown(report))
    if args.report_only:
        return 0
    found = report["summary"]["untested"] or report["summary"]["stale"]
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
