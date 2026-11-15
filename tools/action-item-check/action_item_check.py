#!/usr/bin/env python3
"""会議の議事録のアクションの項目ごとに、担当 / 期限 / 理由が書いてあるかを数える。

Usage:
    python3 action_item_check.py minutes.md
    python3 action_item_check.py minutes/ notes.md
    python3 action_item_check.py --json minutes/
    python3 action_item_check.py --report-only minutes/
    pbpaste | python3 action_item_check.py -

見出しか太字の行が Next Action / NA / アクション / 宿題 / TODO / やること / Action Items などの
節の箇条書きと、どの節にあってもチェックボックスの行を、アクションの項目として読む。
入れ子の箇条書きは親の項目の一部として読む。
期限の形と理由の語は tools/deadline-brief-check の規則を読み込んで使い、アクションに要る語だけを足す。
LLM は使わない。
終了コードは、欠けが無ければ0、欠けがあれば1（--report-only なら0）、パスが無いか読めなければ2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "deadline-brief-check"))

import deadline_brief_check as dbc

OWNER = "owner"
DUE = "due"
REASON = "reason"
KINDS = (OWNER, DUE, REASON)
LABELS = {OWNER: "担当", DUE: "期限", REASON: "理由"}

SECTION = "section"
CHECKBOX = "checkbox"
TEXT_FORM = "text"
COLUMN_FORM = "columns"
PERSON = "person"
GROUP = "group"
TEXT_WIDTH = 60

_A = r"(?<![A-Za-z0-9_])"
_Z = r"(?![A-Za-z0-9_])"

# 私用領域の文字で印を付け、mask がタグを消した後もメンションの種類を残す
_USER = ""
_OTHER_OPEN = ""
_OTHER_CLOSE = ""
_MENTION = re.compile(
    r"<mention-(?P<kind>[a-z][a-z-]*)\b(?P<attrs>[^<>]*?)"
    r"(?:/>|>(?P<body>[^<>]*)</mention-(?P=kind)\s*>)"
)
_DATE_ATTR = re.compile(r'\bstart\s*=\s*"(\d{4}-\d{2}-\d{2})')

_ACTION_LABEL = re.compile(
    _A
    + r"(?:next[ \t]*actions?|na|to[- \t]?dos?|action[ \t]*items?)"
    + _Z
    + r"|(?<!リ)アクション|宿題|やること",
    re.IGNORECASE,
)
_HEADING_ATTRS = re.compile(r"\s*\{[^{}]*\}\s*$")
_BOLD_ONLY = re.compile(r"^(\*\*|__)(?P<text>.+?)\1[ \t]*[:：]?[ \t]*$")
_LIST = re.compile(
    r"^(?P<indent> *)(?:(?:[-*+]|\d{1,3}[.)])(?: +|$)|[・•] *)"
    r"(?P<check>\[[ xX]\](?: +|$))?(?P<rest>.*)$"
)

_KANJI = "㐀-䶿一-鿿豈-﫿々"
_KATAKANA = "ァ-ヺー"
_SAN = re.compile(f"[{_KANJI}{_KATAKANA}A-Za-z]+さん")
_NOT_SAN = frozenset({"皆さん", "客さん"})
_AT = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[@＠](?!(?:channel|here|everyone)" + _Z + r")"
    r"[^\s@＠、。,，:：;；()（）\[\]［］【】「」<>]+",
    re.IGNORECASE,
)
_OWNER_WORD = re.compile(
    r"担当|" + _A + r"(?:owners?|assignees?|assigned to)" + _Z, re.IGNORECASE
)
_GROUP = re.compile(
    r"側|先方|お客さま|お客様|弊社|当社|御社|貴社|全員|両者|双方|各位|チーム|一同"
)
_JOINERS = ("・", "、")
_BRACKETS = {"(": ")", "（": "）", "【": "】", "[": "]", "［": "］"}
_LEADING = re.compile(r"^([(（【\[［])([^()（）【】\[\]［］]*)([)）】\]］])")
_TRAILING = re.compile(r"([(（【\[［])([^()（）【】\[\]［］]*)([)）】\]］])$")
_NAME_SPLIT = re.compile(r"[\s/／・、,，&＆]+")
_NAME_TOKEN = re.compile(
    f"(?:[{_KANJI}]{{1,3}}|[{_KATAKANA}]{{2,10}}|[A-Za-z][A-Za-z.\\-]{{1,19}})"
    "(?:さん|くん|様|氏)?"
)
NOT_NAMES = frozenset(
    {
        *"月火水木金土日",
        *("済", "済み", "未", "未定", "未着手", "着手", "完了", "中止", "延期"),
        *("対応", "対応中", "対応済", "確認", "確認中", "要確認", "未確認"),
        *("検討", "検討中", "進行中", "継続", "保留", "相談", "要相談"),
        *("任意", "必須", "不要", "仮", "案", "例", "注", "他", "等", "全体"),
        *("再掲", "優先", "重要", "緊急", "至急", "参考", "備考", "補足"),
        *("新規", "追加", "変更", "削除", "修正", "共有", "宿題", "議題", "決定"),
        *("今日", "本日", "担当"),
        *("done", "wip", "tbd", "todo", "na", "ok", "ng", "memo", "note"),
        *("optional", "draft", "fyi", "asap"),
    }
)

OWNER_WORD_RULE = "担当の語"
BRACKET_RULE = "括弧の名前"
COLUMN_OWNER_RULE = "欄の形の担当"
COLUMN_DUE_RULE = "欄の形の期限"
_COLUMN_SPLIT = re.compile(r"[ \t]*(?:(?<=[ \t])|^)/(?=[ \t]|$)[ \t]*")
_PLACEHOLDERS = frozenset({"", "未定", "tbd", "-"})

DUE_FORM_RULE = "日付 / 締切の語"
RELATIVE_RULE = "相対の期限"
_RELATIVE_DUE = re.compile(
    r"明日|明後日|今週|来週|再来週|翌週|来月|翌月|週末|月初|次回"
    r"|週内|月内|年内|年度内"
    r"|次の(?:定例|会議|ミーティング|打ち合わせ|打合せ|mtg)"
    r"|(?:今日|本日|今月)まで"
    r"|[(（][月火水木金土日][)）]"
    r"|" + _A + r"(?:today|tomorrow|tonight|this week|next week|next time"
    r"|next meeting|end of (?:the )?(?:day|week|month)"
    r"|(?:mon|tues|wednes|thurs|fri|satur|sun)day)" + _Z,
    re.IGNORECASE,
)

# アクションの「前に / 後に」は理由ではなく順番や時機を表すので、既存の理由の規則から外す
TIMING_RULE = "前に / 後に"
PURPOSE_RULE = "目的 / 背景"
REASON_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (rule, pattern)
    for rule, pattern in dbc.TEXT_RULES[dbc.REASON]
    if rule != TIMING_RULE
) + (
    (
        PURPOSE_RULE,
        re.compile(
            r"目的|背景|狙い|意図|なぜ|" + _A + r"(?:why|purpose|goal)" + _Z,
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class Evidence:
    rule: str
    match: str


@dataclass(frozen=True)
class Item:
    start: int
    end: int
    text: str
    source: str
    section: str | None
    form: str
    info: dict[str, tuple[Evidence, ...]]

    def missing(self) -> list[str]:
        return [kind for kind in KINDS if not self.info[kind]]

    def owner_kind(self) -> str | None:
        return owner_kind(self.info[OWNER])


@dataclass(frozen=True)
class Line:
    indent: int
    blank: bool
    heading: dbc.Heading | None
    bold: str | None
    is_list: bool
    checkbox: bool
    content: str


@dataclass
class Region:
    start: int
    end: int
    label: str
    base: int | None = None


@dataclass
class Span:
    start: int
    end: int
    indent: int
    source: str
    section: str | None
    after_blank: bool = False


def replace_mentions(line: str) -> str:
    """Notion のメンションのタグを、担当の印 / 日付 / 印で囲んだ中の文に置き換える"""

    def replace(found: re.Match[str]) -> str:
        kind = found.group("kind")
        if kind == "user":
            return f" {_USER} "
        if kind == "date":
            start = _DATE_ATTR.search(found.group("attrs"))
            return f" {start.group(1)} " if start else " "
        return f"{_OTHER_OPEN}{found.group('body') or ''}{_OTHER_CLOSE}"

    return _MENTION.sub(replace, line)


def readable(line: str) -> str:
    """表示のために、Notion のメンションのタグを中の文か日付に置き換える"""

    def replace(found: re.Match[str]) -> str:
        if found.group("kind") == "date":
            start = _DATE_ATTR.search(found.group("attrs"))
            return start.group(1) if start else ""
        return found.group("body") or f"@{found.group('kind')}"

    return _MENTION.sub(replace, line).strip()


def _label(text: str) -> str:
    return text.strip().rstrip(":：").strip()


def classify(masked: str) -> Line:
    text = masked.expandtabs(4)
    stripped = text.strip()
    indent = len(text) - len(text.lstrip(" "))
    if not stripped:
        return Line(indent, True, None, None, False, False, "")
    heading = dbc.parse_heading(stripped)
    if heading is not None:
        heading = dbc.Heading(
            heading.level, _label(_HEADING_ATTRS.sub("", heading.text))
        )
        return Line(indent, False, heading, None, False, False, heading.text)
    listed = _LIST.match(text)
    content = listed.group("rest").strip() if listed else stripped
    bold = _BOLD_ONLY.match(content)
    return Line(
        indent,
        False,
        None,
        _label(bold.group("text")) if bold else None,
        listed is not None,
        bool(listed and listed.group("check")),
        content,
    )


def _is_action_label(line: Line) -> bool:
    if line.heading is not None:
        return bool(_ACTION_LABEL.search(line.heading.text))
    return line.bold is not None and bool(_ACTION_LABEL.search(line.bold))


def action_regions(lines: list[Line]) -> list[Region]:
    """アクションの節の本文の範囲を返す。見出しや太字の行そのものは含めない"""
    regions: list[Region] = []
    for index, line in enumerate(lines):
        if not _is_action_label(line):
            continue
        end = index + 1
        while end < len(lines):
            following = lines[end]
            if line.heading is not None:
                if following.heading and following.heading.level <= line.heading.level:
                    break
            elif following.heading is not None:
                break
            elif line.is_list:
                if not following.blank and following.indent <= line.indent:
                    break
            elif (
                following.bold is not None
                and not following.is_list
                and following.indent <= line.indent
            ):
                break
            end += 1
        label = line.heading.text if line.heading is not None else line.bold
        regions.append(Region(index + 1, end, label or ""))
    return regions


def item_spans(lines: list[Line]) -> list[Span]:
    region_at: list[Region | None] = [None] * len(lines)
    for region in sorted(action_regions(lines), key=lambda region: region.start):
        for index in range(region.start, region.end):
            region_at[index] = region
    spans: list[Span] = []
    current: Span | None = None
    for index, line in enumerate(lines):
        if line.blank:
            if current is not None:
                current.after_blank = True
            continue
        if current is not None:
            deeper = line.heading is None and line.indent > current.indent
            lazy = (
                line.heading is None
                and not line.is_list
                and line.bold is None
                and not current.after_blank
            )
            if deeper or lazy:
                current.end = index + 1
                current.after_blank = False
                continue
            spans.append(current)
            current = None
        if not line.is_list or _is_action_label(line):
            continue
        region = region_at[index]
        if region is not None:
            if region.base is None:
                region.base = line.indent
            if line.indent <= region.base:
                current = Span(index + 1, index + 1, line.indent, SECTION, region.label)
                continue
        if line.checkbox:
            current = Span(index + 1, index + 1, line.indent, CHECKBOX, None)
    if current is not None:
        spans.append(current)
    return spans


def is_name(token: str) -> bool:
    if not _NAME_TOKEN.fullmatch(token) or token.casefold() in NOT_NAMES:
        return False
    if token.isascii() and token.isupper() and len(token) >= 3:
        return False
    if dbc.deadline_matches(token) or _RELATIVE_DUE.search(token):
        return False
    return not any(pattern.search(token) for _, pattern in REASON_RULES)


def bracket_names(content: str) -> list[str]:
    """行頭か行末の括弧ごとに、人名らしい語か組織の語を「・」でつないで返す"""
    names: list[str] = []
    for pattern in (_LEADING, _TRAILING):
        found = pattern.search(content)
        if found is None or _BRACKETS[found.group(1)] != found.group(3):
            continue
        link = content[found.end() : found.end() + 1] in ("(", "（")
        if pattern is _LEADING and found.group(1) in "[［" and link:
            continue
        tokens = _NAME_SPLIT.split(found.group(2).strip())
        owners = [t for t in tokens if t and (is_name(t) or _GROUP.search(t))]
        if owners:
            names.append("・".join(owners))
    return names


def columns(content: str) -> list[str] | None:
    """行が「担当 / 内容 / 期限」の3つの欄に分かれるなら、欄の文を返す"""
    fields = _COLUMN_SPLIT.split(content)
    return [_show(field) for field in fields] if len(fields) == 3 else None


def _show(text: str) -> str:
    text = text.replace(_USER, "@user")
    return text.replace(_OTHER_OPEN, "").replace(_OTHER_CLOSE, "").strip()


def owner_kind(evidence: tuple[Evidence, ...]) -> str | None:
    """担当が組織か複数の当事者なら group、そうでなければ person を返す"""
    if not evidence:
        return None
    for found in evidence:
        if _GROUP.search(found.match) or any(j in found.match for j in _JOINERS):
            return GROUP
    return PERSON


def _owners(contents: list[str]) -> list[Evidence]:
    text = "\n".join(contents)
    owners = [
        Evidence("Notion のユーザー", "mention-user") for _ in re.finditer(_USER, text)
    ]
    owners.extend(Evidence("@名前", m.group(0)) for m in _AT.finditer(text))
    owners.extend(
        Evidence(OWNER_WORD_RULE, m.group(0)) for m in _OWNER_WORD.finditer(text)
    )
    owners.extend(
        Evidence("〇〇さん", m.group(0))
        for m in _SAN.finditer(text)
        if m.group(0) not in _NOT_SAN
    )
    for content in contents:
        owners.extend(Evidence(BRACKET_RULE, name) for name in bracket_names(content))
    return owners


def _dues(contents: list[str]) -> list[Evidence]:
    dues: list[Evidence] = []
    for content in contents:
        found = dbc.deadline_matches(content)
        dues.extend(Evidence(DUE_FORM_RULE, match) for match in found)
        dues.extend(
            Evidence(RELATIVE_RULE, m.group(0))
            for m in _RELATIVE_DUE.finditer(content)
            if not any(m.group(0) in match for match in found)
        )
    return dues


def _reasons(contents: list[str]) -> list[Evidence]:
    text = "\n".join(contents)
    return [
        Evidence(rule, m.group(0))
        for rule, pattern in REASON_RULES
        for m in pattern.finditer(text)
    ]


def _column(rule: str, field: str) -> list[Evidence]:
    return [] if field.casefold() in _PLACEHOLDERS else [Evidence(rule, field)]


def judge(
    contents: list[str], fields: list[str] | None = None
) -> dict[str, tuple[Evidence, ...]]:
    """項目の行（入れ子を含む）から、担当 / 期限 / 理由の手がかりを集める

    fields があれば、担当は1つ目の欄、期限は3つ目の欄だけで決め、
    理由は2つ目の欄と入れ子の行から探す
    """
    if fields is None:
        info = {
            OWNER: _owners(contents),
            DUE: _dues(contents),
            REASON: _reasons(contents),
        }
    else:
        info = {
            OWNER: _column(COLUMN_OWNER_RULE, fields[0]),
            DUE: _column(COLUMN_DUE_RULE, fields[2]),
            REASON: _reasons([fields[1], *contents[1:]]),
        }
    return {kind: tuple(dict.fromkeys(items)) for kind, items in info.items()}


def analyze(text: str) -> list[Item]:
    original = text.splitlines()
    masked = dbc.mask([replace_mentions(line) for line in original])
    lines = [classify(line) for line in masked]
    items: list[Item] = []
    for span in item_spans(lines):
        contents = [
            lines[index].content
            for index in range(span.start - 1, span.end)
            if not lines[index].blank
        ]
        first = lines[span.start - 1]
        fields = columns(first.content) if first.checkbox else None
        items.append(
            Item(
                span.start,
                span.end,
                readable(original[span.start - 1]),
                span.source,
                span.section,
                TEXT_FORM if fields is None else COLUMN_FORM,
                judge(contents, fields),
            )
        )
    return items


def summarize(items: list[Item]) -> dict:
    return {
        "items": len(items),
        "complete": sum(1 for item in items if not item.missing()),
        "missing": {
            kind: sum(1 for item in items if not item.info[kind]) for kind in KINDS
        },
        "owner_kind": {
            kind: sum(1 for item in items if item.owner_kind() == kind)
            for kind in (PERSON, GROUP)
        },
    }


def item_json(item: Item) -> dict:
    return {
        "start_line": item.start,
        "end_line": item.end,
        "text": item.text,
        "source": item.source,
        "section": item.section,
        "form": item.form,
        "owner_kind": item.owner_kind(),
        "info": {
            kind: {
                "present": bool(item.info[kind]),
                "evidence": [
                    {"rule": e.rule, "match": e.match} for e in item.info[kind]
                ],
            }
            for kind in KINDS
        },
        "missing": item.missing(),
    }


def to_json(reports: list[tuple[str, list[Item]]]) -> dict:
    every = [item for _, items in reports for item in items]
    summary = {"files": len(reports), **summarize(every)}
    return {
        "summary": summary,
        "files": [
            {
                "path": path,
                "summary": summarize(items),
                "items": [item_json(item) for item in items],
            }
            for path, items in reports
        ],
    }


def _summary_line(summary: dict) -> str:
    parts = [f"項目{summary['items']}件", f"3つがそろう{summary['complete']}件"]
    parts += [f"{LABELS[kind]}の欠け{summary['missing'][kind]}件" for kind in KINDS]
    parts.append(f"組織か複数の担当{summary['owner_kind'][GROUP]}件")
    return " / ".join(parts)


def _short(text: str) -> str:
    return text if len(text) <= TEXT_WIDTH else text[:TEXT_WIDTH] + "…"


def render_markdown(reports: list[tuple[str, list[Item]]]) -> str:
    every = [item for _, items in reports for item in items]
    lines = [
        "# action-item-check",
        "",
        f"読んだファイル{len(reports)}件",
        _summary_line(summarize(every)),
    ]
    for path, items in reports:
        lines += ["", f"## {path}", "", _summary_line(summarize(items))]
        lacking = [item for item in items if item.missing()]
        if not lacking:
            continue
        lines += ["", "### 欠けた項目", ""]
        for item in lacking:
            where = f"{item.start}行目"
            if item.end > item.start:
                where = f"{item.start}〜{item.end}行目"
            lines.append(f"- {where}「{_short(item.text)}」")
            lines.append(
                "  - 欠け " + " / ".join(LABELS[kind] for kind in item.missing())
            )
            found = [
                f"{LABELS[kind]}「{' / '.join(dict.fromkeys(e.match for e in item.info[kind]))}」"
                for kind in KINDS
                if item.info[kind]
            ]
            if item.owner_kind() == GROUP:
                found[0] += "（組織か複数）"
            if found:
                lines.append("  - あり " + " / ".join(found))
    return "\n".join(lines) + "\n"


def expand(paths: list[str]) -> tuple[list[tuple[str, Path | None]], list[str]]:
    """渡したパスを読むファイルの並びにする。ディレクトリは下の階層の *.md を読む"""
    files: list[tuple[str, Path | None]] = []
    errors: list[str] = []
    seen: set[object] = set()
    for given in paths:
        if given == "-":
            if "-" not in seen:
                seen.add("-")
                files.append(("-", None))
            continue
        path = Path(given)
        if path.is_dir():
            candidates: list[Path] = []
            for directory, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(
                    name for name in dirnames if not name.startswith(".")
                )
                candidates.extend(
                    Path(directory) / name
                    for name in sorted(filenames)
                    if name.lower().endswith(".md")
                )
        elif path.is_file():
            candidates = [path]
        else:
            errors.append(f"パスが無い: {given}")
            continue
        for candidate in candidates:
            key = candidate.resolve()
            if key not in seen:
                seen.add(key)
                files.append((str(candidate), candidate))
    return files, errors


def read_input(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    with open(path, encoding="utf-8-sig") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="読む Markdown のファイルかディレクトリ（- で標準入力）",
    )
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    parser.add_argument(
        "--report-only", action="store_true", help="欠けがあっても終了コード0を返す"
    )
    args = parser.parse_args(argv)
    files, errors = expand(args.paths)
    texts: list[tuple[str, str]] = []
    for name, path in files:
        try:
            texts.append((name, read_input(path)))
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"読めない: {name}: {error}")
    if errors:
        for error in errors:
            print(f"action-item-check: {error}", file=sys.stderr)
        return 2
    reports = [(name, analyze(text)) for name, text in texts]
    if args.json:
        print(json.dumps(to_json(reports), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_markdown(reports))
    if args.report_only:
        return 0
    return 1 if any(item.missing() for _, items in reports for item in items) else 0


if __name__ == "__main__":
    sys.exit(main())
