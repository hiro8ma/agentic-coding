#!/usr/bin/env python3
"""エージェントの指示ファイルのルールを、指摘がどう取り込まれたかで並べる。

Usage:
    python3 rule_loops.py PATH [PATH ...]            # Markdown で出す
    python3 rule_loops.py --json PATH [PATH ...]     # JSON で出す
    python3 rule_loops.py --glob 'feedback_*.md' DIR # ディレクトリで読むファイルを絞る
    python3 rule_loops.py --tool my-guard PATH       # 仕組みとして数える道具の名前を足す

PATH は Markdown のファイルかディレクトリ（CLAUDE.md / AGENTS.md / メモリのディレクトリなど）。
ルールごとに、Why の有無、Why に書いた日付、日付が2つ以上あるか（再発）、
hook / CI / lint / スクリプト / 道具に触れているか、直し方の札を出す。
札と仕組みは語の一致で付けた目安で、分類の正しさは示さない。

終了コードは0。読めないパスを渡したときだけ2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

RECURRENCE_MIN_DATES = 2
TITLE_WIDTH = 40
SNIPPET_WIDTH = 60

_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_ITEM = re.compile(r"^( *)(?:[-*+]|\d{1,3}[.)])\s+(\S.*)$")
_FENCE = re.compile(r"^ *(`{3,}|~{3,})")
_WHY = re.compile(r"^\*{0,2}(?:why|理由|なぜ)\*{0,2}\s*[:：]\s*\**\s*", re.IGNORECASE)
_LABEL = re.compile(r"^\*\*[^*\n]{1,40}?(?:\*\*\s*[:：]|[:：]\s*\*\*)")
_LINK_ITEM = re.compile(r"^\[[^\]]+\]\([^)]*\)")
_NOT_PROSE = re.compile(r"^(?:\||>|<!--)")
_FRONTMATTER_KEY = re.compile(r"^(description|name)\s*:\s*(.*)$")

_FULL_DATE = re.compile(r"(?<![0-9])(\d{4})([-/])(\d{1,2})\2(\d{1,2})(?![0-9])")
# 年のない M/D は、文中だと事実の日付であることが多いので、Why と文の書き出しだけで拾う
_SHORT_DATE = re.compile(
    r"(?:^|(?<=[。．！？])|(?<=[.!?]\s))\s*(?:on\s+)?(\d{1,2})/(\d{1,2})(?![0-9/])",
    re.MULTILINE | re.IGNORECASE,
)

# 和文の文字も \w に入るので、英字の語の境界は ASCII だけで判定する
_A = r"(?<![A-Za-z0-9_])"
_Z = r"(?![A-Za-z0-9_])"

STRUCTURAL: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "hook",
        re.compile(
            rf"{_A}(?:hooks?|pre-commit|PreToolUse|PostToolUse|UserPromptSubmit"
            rf"|SessionStart|SubagentStop){_Z}|フック",
            re.IGNORECASE,
        ),
    ),
    ("CI", re.compile(rf"{_A}(?:CI|GitHub Actions){_Z}|\.github/workflows")),
    (
        "lint",
        re.compile(
            rf"{_A}(?:[A-Za-z]+-)?lint(?:ers?|ing)?{_Z}"
            rf"|{_A}(?:ruff|eslint|staticcheck|clippy|prettier|go vet){_Z}|リンター|リント",
            re.IGNORECASE,
        ),
    ),
    (
        "script",
        re.compile(
            rf"{_A}scripts?{_Z}|スクリプト|{_A}[A-Za-z0-9_./-]+\.(?:sh|py|ts|js|mjs){_Z}",
            re.IGNORECASE,
        ),
    ),
    (
        "tool",
        re.compile(
            rf"{_A}(?:tools/[A-Za-z0-9_.-]+|settings(?:\.local)?\.json|execpolicy"
            rf"|[A-Za-z0-9_-]+\.rules){_Z}"
        ),
    ),
)

CRITERION = "criterion"
ACTION = "action"
UNLABELED = "unlabeled"
FIX_LABELS = {CRITERION: "条件", ACTION: "行動", UNLABELED: "なし"}

CRITERION_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("毎回", re.compile("毎回")),
    ("直前に", re.compile("直前に")),
    ("〜だけを〜と読む", re.compile(r"だけを[^。\n]{0,40}?と(?:読|みな|扱)")),
    ("〜と読まない", re.compile(r"と(?:読まない|みなさない|扱わない)")),
    ("許可", re.compile("許可")),
    ("承認", re.compile("承認")),
    ("基準", re.compile("基準")),
    ("every time", re.compile(rf"{_A}(?:every|each) time{_Z}", re.IGNORECASE)),
    (
        "right before",
        re.compile(rf"{_A}(?:right|immediately|just) before{_Z}", re.IGNORECASE),
    ),
    (
        "approval",
        re.compile(rf"{_A}(?:approv[a-z]*|permission|consent){_Z}", re.IGNORECASE),
    ),
    (
        "counts as",
        re.compile(
            rf"{_A}(?:counts? as|treat(?:s|ed)? .{{1,30}}? as){_Z}", re.IGNORECASE
        ),
    ),
)

ACTION_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("禁止", re.compile("禁止")),
    ("必ず", re.compile("必ず")),
    ("〜ない（文末）", re.compile(r"ない(?=\s*(?:$|[。、）)」]))")),
    (
        "〜する（文末）",
        re.compile(r"(?:[うくぐすつぬぶむ]|(?<![いあ])る)(?=\s*(?:$|。))"),
    ),
    (
        "do not",
        re.compile(rf"{_A}(?:never|do not|don't|must not|avoid){_Z}", re.IGNORECASE),
    ),
    ("always", re.compile(rf"{_A}(?:always|must){_Z}", re.IGNORECASE)),
)


class SourceLine(NamedTuple):
    no: int
    text: str
    after_blank: bool


@dataclass(eq=False)
class Item:
    line: int
    indent: int
    content_indent: int
    lines: list[SourceLine] = field(default_factory=list)
    children: list[Item] = field(default_factory=list)

    def all_lines(self) -> list[tuple[int, str]]:
        found = [(no, text) for no, text, _ in self.lines]
        for child in self.children:
            found.extend(child.all_lines())
        return found


@dataclass(eq=False)
class Section:
    heading: str
    path: list[str]
    line: int
    paragraphs: list[list[SourceLine]] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)


@dataclass
class Why:
    line: int
    parts: list[tuple[int, str]]

    def text(self) -> str:
        return "\n".join(text for _, text in self.parts)


@dataclass
class Evidence:
    name: str
    match: str
    line: int
    text: str


@dataclass(eq=False)
class Rule:
    file: str
    line: int
    heading: str
    heading_path: list[str]
    kind: str
    title: str
    body: list[tuple[int, str]]
    whys: list[Why]
    why_scope: str = "none"
    dates: list[str] = field(default_factory=list)
    structural: list[Evidence] = field(default_factory=list)
    fix_kind: str = UNLABELED
    fix_markers: list[Evidence] = field(default_factory=list)
    section_key: tuple[str, int] = ("", 0)

    @property
    def recurring(self) -> bool:
        return len(self.dates) >= RECURRENCE_MIN_DATES

    def to_json(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "heading": self.heading,
            "heading_path": self.heading_path,
            "kind": self.kind,
            "title": self.title,
            "has_why": self.why_scope != "none",
            "why_scope": self.why_scope,
            "why_lines": [why.line for why in self.whys],
            "incident_dates": self.dates,
            "recurring": self.recurring,
            "structural": [vars(e) for e in self.structural],
            "fix_kind": self.fix_kind,
            "fix_markers": [vars(e) for e in self.fix_markers],
        }


def parse(text: str) -> list[Section]:
    """Markdown を見出しの節に分け、節ごとに段落と箇条書きの木を作る"""
    lines = text.splitlines()
    start, preamble = _frontmatter(lines)
    sections = [Section(heading=preamble, path=[], line=start + 1)]
    headings: list[tuple[int, str]] = []
    stack: list[Item] = []
    paragraph: list[SourceLine] | None = None
    blank = True
    fence = ""
    for index in range(start, len(lines)):
        no = index + 1
        raw = lines[index].expandtabs(4)
        stripped = raw.strip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        opened = _FENCE.match(raw)
        if opened:
            fence = opened.group(1)
            paragraph = None
            continue
        if not stripped:
            blank = True
            paragraph = None
            continue
        heading = _HEADING.match(raw)
        if heading:
            level = len(heading.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading.group(2)))
            sections.append(
                Section(
                    heading=heading.group(2), path=[t for _, t in headings], line=no
                )
            )
            stack.clear()
            paragraph = None
            blank = False
            continue
        item = _ITEM.match(raw)
        if item:
            indent = len(item.group(1))
            node = Item(line=no, indent=indent, content_indent=item.start(2))
            node.lines.append(SourceLine(no, item.group(2).strip(), True))
            while stack and stack[-1].indent >= indent:
                stack.pop()
            (stack[-1].children if stack else sections[-1].items).append(node)
            stack.append(node)
            paragraph = None
            blank = False
            continue
        lead = len(raw) - len(raw.lstrip())
        if stack and blank:
            while stack and stack[-1].content_indent > lead:
                stack.pop()
        if stack:
            stack[-1].lines.append(SourceLine(no, stripped, blank))
            blank = False
            continue
        blank = False
        if _NOT_PROSE.match(stripped):
            paragraph = None
            continue
        if paragraph is None:
            paragraph = []
            sections[-1].paragraphs.append(paragraph)
            paragraph.append(SourceLine(no, stripped, True))
        else:
            paragraph.append(SourceLine(no, stripped, False))
    return sections


def _frontmatter(lines: list[str]) -> tuple[int, str]:
    if not lines or lines[0].strip() != "---":
        return 0, ""
    end = next(
        (i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), 0
    )
    if not end:
        return 0, ""
    values = {}
    for line in lines[1:end]:
        found = _FRONTMATTER_KEY.match(line.strip())
        if found:
            values[found.group(1)] = found.group(2).strip().strip("\"'")
    return end + 1, values.get("description") or values.get("name") or ""


def split_why(
    lines: list[SourceLine],
) -> tuple[list[tuple[int, str]], list[Why]]:
    """Why の行から、空行か次の太字の札までを Why にし、残りを本文にする"""
    body: list[tuple[int, str]] = []
    whys: list[Why] = []
    current: Why | None = None
    for no, text, new_block in lines:
        label = _WHY.match(text)
        if current is not None and not label and (new_block or _LABEL.match(text)):
            current = None
        if label:
            current = Why(line=no, parts=[(no, text[label.end() :])])
            whys.append(current)
        elif current is not None:
            current.parts.append((no, text))
        else:
            body.append((no, text))
    return body, whys


def _why_item(item: Item) -> Why | None:
    label = _WHY.match(item.lines[0].text)
    if not label:
        return None
    parts = item.all_lines()
    parts[0] = (parts[0][0], parts[0][1][label.end() :])
    return Why(line=item.line, parts=parts)


def _collect(item: Item, body: list[tuple[int, str]], whys: list[Why]) -> None:
    why = _why_item(item)
    if why is not None:
        whys.append(why)
        return
    own_body, own_whys = split_why(item.lines)
    body.extend(own_body)
    whys.extend(own_whys)
    for child in item.children:
        _collect(child, body, whys)


def extract_dates(text: str) -> list[str]:
    """YYYY-MM-DD / YYYY/M/D と、文の書き出しの M/D を、出てきた順に重複なしで返す"""
    full: list[tuple[int, int, int, int]] = []
    for found in _FULL_DATE.finditer(text):
        year, month, day = int(found.group(1)), int(found.group(3)), int(found.group(4))
        if _valid(year, month, day):
            full.append((found.start(), year, month, day))
    masked = _FULL_DATE.sub(lambda m: "#" * len(m.group(0)), text)
    found_dates: list[tuple[int, str]] = [
        (pos, _format(year, month, day)) for pos, year, month, day in full
    ]
    for found in _SHORT_DATE.finditer(masked):
        month, day = int(found.group(1)), int(found.group(2))
        if not _valid(None, month, day):
            continue
        start = found.start(1)
        before = [year for pos, year, _, _ in full if pos < start]
        after = [year for pos, year, _, _ in full if pos > start]
        year = before[-1] if before else (after[0] if after else None)
        if year is not None and not _valid(year, month, day):
            continue
        found_dates.append((start, _format(year, month, day)))
    ordered: list[str] = []
    for _, value in sorted(found_dates):
        if value not in ordered:
            ordered.append(value)
    return ordered


def _valid(year: int | None, month: int, day: int) -> bool:
    try:
        # 年のない日付は、2月29日を通すため閏年で確かめる
        datetime.date(year if year is not None else 2000, month, day)
    except ValueError:
        return False
    return True


def _format(year: int | None, month: int, day: int) -> str:
    prefix = f"{year:04d}" if year is not None else "-"
    return f"{prefix}-{month:02d}-{day:02d}"


def _search(
    body: list[tuple[int, str]], patterns: tuple[tuple[str, re.Pattern[str]], ...]
) -> list[Evidence]:
    found: list[Evidence] = []
    seen: set[tuple[str, int]] = set()
    for no, text in body:
        for name, pattern in patterns:
            match = pattern.search(text)
            if match and (name, no) not in seen:
                seen.add((name, no))
                found.append(
                    Evidence(name, match.group(0), no, _shorten(text, SNIPPET_WIDTH))
                )
    return found


def _shorten(text: str, width: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _plain(text: str) -> str:
    return re.sub(r"\*\*|__|`", "", text).strip()


def _tool_patterns(tools: list[str]) -> tuple[tuple[str, re.Pattern[str]], ...]:
    extra = tuple(("tool", re.compile(rf"{_A}{re.escape(name)}{_Z}")) for name in tools)
    return STRUCTURAL + extra


def audit_text(text: str, file: str, tools: list[str] | None = None) -> list[Rule]:
    """1つのファイルからルールを取り出し、Why / 日付 / 仕組み / 札を付ける"""
    patterns = _tool_patterns(tools or [])
    rules: list[Rule] = []
    for index, section in enumerate(parse(text)):
        key = (file, index)
        section_body: list[tuple[int, str]] = []
        section_whys: list[Why] = []
        for paragraph in section.paragraphs:
            body, whys = split_why(paragraph)
            section_body.extend(body)
            section_whys.extend(whys)
        has_prose = bool(section_body)
        item_rules: list[Rule] = []
        for item in section.items:
            why = _why_item(item)
            if why is not None:
                section_whys.append(why)
                continue
            if _LINK_ITEM.match(item.lines[0].text):
                continue
            body: list[tuple[int, str]] = []
            whys: list[Why] = []
            _collect(item, body, whys)
            section_body.extend(body)
            item_rules.append(
                Rule(
                    file=file,
                    line=item.line,
                    heading=section.heading,
                    heading_path=section.path,
                    kind="item",
                    title=_shorten(_plain(item.lines[0].text), TITLE_WIDTH),
                    body=body,
                    whys=whys,
                    section_key=key,
                )
            )
        if has_prose or section_whys:
            line = section.line
            if not section.path:
                line = min(
                    [no for no, _ in section_body] + [why.line for why in section_whys]
                )
            title = section.heading or (section_body[0][1] if section_body else "")
            heading_line = [(line, section.heading)] if section.heading else []
            rules.append(
                Rule(
                    file=file,
                    line=line,
                    heading=section.heading,
                    heading_path=section.path,
                    kind="section",
                    title=_shorten(_plain(title), TITLE_WIDTH),
                    body=heading_line + section_body,
                    whys=section_whys,
                    section_key=key,
                )
            )
        for rule in item_rules:
            if not rule.whys and section_whys:
                rule.why_scope = "section"
        rules.extend(item_rules)
    for rule in rules:
        if rule.whys:
            rule.why_scope = "rule"
        dates: list[str] = []
        for why in rule.whys:
            for value in extract_dates(why.text()):
                if value not in dates:
                    dates.append(value)
        rule.dates = sorted(dates)
        rule.structural = _search(rule.body, patterns)
        criteria = _search(rule.body, CRITERION_MARKERS)
        actions = _search(rule.body, ACTION_MARKERS)
        if criteria:
            rule.fix_kind, rule.fix_markers = CRITERION, criteria
        elif actions:
            rule.fix_kind, rule.fix_markers = ACTION, actions
    rules.sort(key=lambda r: (r.file, r.line))
    return rules


def section_overlaps(rules: list[Rule]) -> list[dict[str, object]]:
    """同じ節の2つ以上のルールが、合わせて2つ以上の日付を持つ節を返す"""
    groups: dict[tuple[str, int], list[Rule]] = {}
    for rule in rules:
        groups.setdefault(rule.section_key, []).append(rule)
    found: list[dict[str, object]] = []
    for members in groups.values():
        dated = [rule for rule in members if rule.dates]
        dates = sorted({value for rule in dated for value in rule.dates})
        if len(dated) < 2 or len(dates) < RECURRENCE_MIN_DATES:
            continue
        first = min(members, key=lambda r: r.line)
        found.append(
            {
                "file": first.file,
                "line": first.line,
                "heading": first.heading,
                "dates": dates,
                "rules": [
                    {"line": r.line, "title": r.title, "dates": r.dates} for r in dated
                ],
            }
        )
    return found


def summarize(files: list[str], rules: list[Rule]) -> dict[str, object]:
    overlaps = section_overlaps(rules)
    recurring = [rule for rule in rules if rule.recurring]
    return {
        "files": files,
        "summary": {
            "files": len(files),
            "rules": len(rules),
            "item_rules": sum(rule.kind == "item" for rule in rules),
            "section_rules": sum(rule.kind == "section" for rule in rules),
            "rules_with_why": sum(rule.why_scope == "rule" for rule in rules),
            "rules_with_section_why_only": sum(
                rule.why_scope == "section" for rule in rules
            ),
            "rules_without_why": sum(rule.why_scope == "none" for rule in rules),
            "recurring_rules": len(recurring),
            "recurring_without_structural": sum(
                not rule.structural for rule in recurring
            ),
            "sections_with_dates_across_rules": len(overlaps),
        },
        "rules": [rule.to_json() for rule in rules],
        "section_overlaps": overlaps,
    }


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _where(rule: dict[str, object]) -> str:
    return _cell(f"{rule['file']}:{rule['line']}")


def _structural_cell(rule: dict[str, object]) -> str:
    evidence = rule["structural"]
    if not evidence:
        return "なし"
    assert isinstance(evidence, list)
    first: dict[str, dict[str, object]] = {}
    for found in evidence:
        first.setdefault(str(found["name"]), found)
    return " / ".join(
        _cell(f"{e['name']} L{e['line']}「{e['match']}」") for e in first.values()
    )


def _fix_cell(rule: dict[str, object]) -> str:
    label = FIX_LABELS[str(rule["fix_kind"])]
    markers = rule["fix_markers"]
    assert isinstance(markers, list)
    names: list[str] = []
    for marker in markers:
        if marker["name"] not in names:
            names.append(marker["name"])
    return _cell(f"{label}（{' / '.join(names)}）" if names else label)


def _dates_cell(dates: object) -> str:
    assert isinstance(dates, list)
    return " / ".join(dates) if dates else "-"


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    rules = report["rules"]
    overlaps = report["section_overlaps"]
    assert isinstance(summary, dict) and isinstance(rules, list)
    assert isinstance(overlaps, list)
    out = [
        "# rule-loops",
        "",
        f"読んだファイル{summary['files']}件",
        (
            f"ルール{summary['rules']}件（箇条書き{summary['item_rules']}件 / "
            f"見出しの節{summary['section_rules']}件）"
        ),
        (
            f"自分の Why があるルール{summary['rules_with_why']}件 / "
            f"節の Why だけがあるルール{summary['rules_with_section_why_only']}件 / "
            f"Why がないルール{summary['rules_without_why']}件"
        ),
        (
            f"再発したルール（Why の日付が{RECURRENCE_MIN_DATES}つ以上）"
            f"{summary['recurring_rules']}件"
        ),
        (
            "再発していて、hook / CI / lint / スクリプト / 道具に触れていないルール"
            f"{summary['recurring_without_structural']}件"
        ),
        (
            "同じ節の複数のルールに日付が分かれている節"
            f"{summary['sections_with_dates_across_rules']}件"
        ),
        "",
        "仕組みと札の欄は語の一致で付けた目安で、分類の正しさは示さない",
        "",
    ]
    recurring = [rule for rule in rules if rule["recurring"]]
    out += ["## 再発したルール", ""]
    if recurring:
        out += [
            "| 場所 | 見出し | ルール | 日付 | 仕組み | 札 |",
            "|---|---|---|---|---|---|",
        ]
        out += [
            f"| {_where(r)} | {_cell(r['heading'])} | {_cell(r['title'])} | "
            f"{_dates_cell(r['incident_dates'])} | {_structural_cell(r)} | {_fix_cell(r)} |"
            for r in recurring
        ]
    else:
        out.append("なし")
    out += ["", "## 再発していて、文章だけで守らせているルール", ""]
    text_only = [rule for rule in recurring if not rule["structural"]]
    out += [
        f"- {_where(r)} {_cell(r['heading'])}「{_cell(r['title'])}」" for r in text_only
    ]
    if not text_only:
        out.append("なし")
    out += ["", "## Why がないルール", ""]
    missing = [rule for rule in rules if rule["why_scope"] == "none"]
    if missing:
        out += ["| 場所 | 見出し | ルール |", "|---|---|---|"]
        out += [
            f"| {_where(r)} | {_cell(r['heading'])} | {_cell(r['title'])} |"
            for r in missing
        ]
    else:
        out.append("なし")
    out += ["", "## 同じ節の複数のルールに日付が分かれている節", ""]
    if overlaps:
        out += ["| 場所 | 見出し | 日付 | ルール |", "|---|---|---|---|"]
        for overlap in overlaps:
            members = " / ".join(
                f"L{member['line']}「{member['title']}」" for member in overlap["rules"]
            )
            out.append(
                f"| {_where(overlap)} | {_cell(overlap['heading'])} | "
                f"{_dates_cell(overlap['dates'])} | {_cell(members)} |"
            )
    else:
        out.append("なし")
    out += [
        "",
        "## すべてのルール",
        "",
        "| 場所 | 見出し | ルール | Why | 日付 | 再発 | 仕組み | 札 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    why_labels = {"rule": "あり", "section": "節", "none": "なし"}
    out += [
        f"| {_where(r)} | {_cell(r['heading'])} | {_cell(r['title'])} | "
        f"{why_labels[str(r['why_scope'])]} | {_dates_cell(r['incident_dates'])} | "
        f"{'あり' if r['recurring'] else '-'} | {_structural_cell(r)} | {_fix_cell(r)} |"
        for r in rules
    ]
    return "\n".join(out) + "\n"


def collect_files(paths: list[str], pattern: str) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files.extend(
                found
                for found in sorted(path.rglob(pattern))
                if found.is_file()
                and not any(
                    part.startswith(".") for part in found.relative_to(path).parts
                )
            )
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(raw)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("paths", nargs="+", help="Markdown のファイルかディレクトリ")
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    parser.add_argument(
        "--glob", default="*.md", help="ディレクトリの中で読むファイル（既定は *.md）"
    )
    parser.add_argument(
        "--tool",
        action="append",
        default=[],
        metavar="NAME",
        help="仕組みとして数える道具の名前。何度でも付けられる",
    )
    args = parser.parse_args(argv)
    try:
        files = collect_files(args.paths, args.glob)
        rules: list[Rule] = []
        for path in files:
            rules.extend(
                audit_text(
                    path.read_text(encoding="utf-8", errors="replace"),
                    str(path),
                    args.tool,
                )
            )
    except OSError as error:
        print(f"rule-loops: 入力を読めない: {error}", file=sys.stderr)
        return 2
    report = summarize([str(path) for path in files], rules)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
