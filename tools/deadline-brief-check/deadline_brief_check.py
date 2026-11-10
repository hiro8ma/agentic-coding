#!/usr/bin/env python3
"""依頼の文面の締切ごとに、固さ / 影響 / 途中の報告 / 理由が書いてあるかを数える。

Usage:
    python3 deadline_brief_check.py draft.md
    python3 deadline_brief_check.py --section "Review Deadline" body.md
    gh pr view 12 --json body --jq .body \
        | python3 deadline_brief_check.py --section "Review Deadline" --json

締切の記述（日付 / 時刻の形と、期限 / 締切 / までに / deadline / due などの語）がある行を探し、
その行を含む節（--scope paragraph なら段落）の文から、4つの情報を語と形の規則で探す。
LLM は使わない。
終了コードは、締切が無いか全部の締切に4つがそろえば0、欠けがあれば1、入力や節を読めなければ2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass

FIRMNESS = "firmness"
IMPACT = "impact"
INTERIM = "interim_report"
REASON = "reason"
KINDS = (FIRMNESS, IMPACT, INTERIM, REASON)
LABELS = {FIRMNESS: "固さ", IMPACT: "影響", INTERIM: "途中の報告", REASON: "理由"}

SECTION = "section"
PARAGRAPH = "paragraph"
UNIT_LABELS = {SECTION: "節", PARAGRAPH: "段落"}

# 英語の語の境界は ASCII だけで見る。\b は和文の文字も語に数え、「EODまで」を見逃すため
_A = r"(?<![A-Za-z0-9_])"
_Z = r"(?![A-Za-z0-9_])"
_WIDE = str.maketrans("０１２３４５６７８９／：", "0123456789/:")


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


DEADLINE_FORMS: tuple[re.Pattern[str], ...] = (
    _rx(r"(?<!\d)\d{4}[/-]\d{1,2}[/-]\d{1,2}(?!\d)"),
    _rx(r"(?<!\d)\d{4}年\d{1,2}月\d{1,2}日"),
    _rx(r"(?<![\d/.])(?:1[0-2]|0?[1-9])/(?:3[01]|[12]\d|0?[1-9])(?![\d/])"),
    _rx(r"(?<!\d)\d{1,2}月(?:\d{1,2}日|末|中|内|上旬|中旬|下旬)"),
    _rx(
        _A + r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
        r"[a-z]*\.?\s+\d{1,2}" + _Z
    ),
    _rx(r"(?<![\d:])(?:[01]?\d|2[0-3]):[0-5]\d(?![\d:])"),
    _rx(r"(?<!\d)(?:[01]?\d|2[0-4])時(?!間|点)"),
    _rx(r"[月火水木金土日]曜"),
    _rx(
        r"(?:今日|本日|明日|明後日|今週|来週|週内|今月|来月|月内|年内)中"
        r"|週明け|月末|年度末|" + _A + r"(?:eod|eow|cob)" + _Z
    ),
    _rx(
        r"期限|期日|締め?切り?|〆切り?|納期|までに|deadline"
        r"|" + _A + r"due" + _Z + r"(?!\s+to" + _Z + ")"
    ),
)

_REPORT_VERB = _rx(
    r"連絡|知らせ|教えて|相談|共有|報告|一声|声(?:を)?かけ|言って|伝えて|メンション"
    r"|let me know|tell me|reach out|heads[- ]?up"
    r"|" + _A + r"(?:ping|notify)" + _Z
)
_MISS_RISK = _rx(
    r"間に合わな|間に合いそうにな|遅れ(?:そう|る|た)|遅延|過ぎそう"
    r"|(?:難し|厳し)(?:そう|い場合|ければ|いとき|くなりそう)"
    r"|無理(?:そう|な場合|なら|なとき)|ずれ(?:そう|る場合|込みそう)"
    r"|延ば(?:し|す)|延長|守れな|終わらな|詰まっ"
    r"|can'?t make|cannot make|won'?t make"
    r"|" + _A + r"(?:miss|slip|slips|delay|delayed|behind|extension)" + _Z
)
_MISS_CONDITION = _rx(
    r"(?:間に合わ|守れ|入ら|終わら|出せ|でき|進め)な(?:いと|ければ|かったら|いなら|い場合)"
    r"|(?:遅れ|過ぎ|ずれ)(?:ると|たら|れば|る場合)|逃(?:すと|したら|せば)"
    r"|if (?:we|you|it|this|they) (?:miss|slip|can'?t make|cannot make)"
)
_SENTENCE_END = re.compile(r"[。！？!?\n]+|(?<=\.)\s+")

TEXT_RULES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    FIRMNESS: (
        (
            "動かせない",
            _rx(
                r"動かせない|ずらせない|延ばせない|延期できない|厳守|必着|必達|遅くとも"
                r"|最終(?:の)?(?:期限|締め?切り?|〆切|期日)"
                r"|hard deadline|no later than|at the latest"
                r"|" + _A + r"(?:strict|firm)" + _Z
            ),
        ),
        (
            "目安 / 仮",
            _rx(
                r"目安|暫定|仮(?:の|で|置き|決め|押さえ)|できれば|可能なら|可能であれば"
                r"|なるべく|理想は|(?:ずれ|遅れ|延び)ても|前後して|相談(?:可|でき|に応じ)|未定"
                r"|tentative|soft deadline|target date|if possible"
                r"|" + _A + r"(?:ideally|flexible|tbd)" + _Z
            ),
        ),
        (
            "急ぎ",
            _rx(
                r"急ぎ|急いで|至急|緊急|早め|早いほど|なるはや|優先度|最優先"
                r"|no rush|" + _A + r"(?:asap|urgent|urgently)" + _Z
            ),
        ),
    ),
    IMPACT: (
        (
            "止まる / ずれる",
            _rx(
                r"なくなる|止ま(?:る|って|り)|ブロック|延期|後ろ倒し|ずれ込|持ち越|見送"
                r"|待ちにな|これ待ち|に回(?:る|す)|遅れが出|[てで]しまう"
                r"|would slip|be delayed"
                r"|" + _A + r"(?:block|blocks|blocked|blocking|otherwise)" + _Z
            ),
        ),
        (
            "影響",
            _rx(
                r"影響|支障|困る|困り"
                r"|" + _A + r"(?:impact|impacts|affect|affects)" + _Z
            ),
        ),
    ),
    INTERIM: (
        (
            "途中経過",
            _rx(
                r"途中経過|中間報告|進捗(?:を|の)?(?:共有|報告|連絡|教え)"
                r"|status update|check-?in"
            ),
        ),
    ),
    REASON: (
        (
            "ため / ので",
            _rx(
                r"(?<!ら)ため|ので(?!は)"
                r"|(?<=[るたいだすくうつむぶぬぐ])から(?=[、。,.)）\s]|$)"
                r"|なぜなら|というのも|理由"
                r"|" + _A + r"(?:because|so that|in order to)" + _Z
            ),
        ),
        (
            "前に / 後に",
            _rx(
                r"(?:の|より)前|より先|(?<=[^\s、。,(（名以午事])前(?:に|まで)"
                r"|(?<=[^\s、。,(（最前今午背])後(?:に|で|から)|[てで]から"
                r"|" + _A + r"(?:before|after|ahead of)" + _Z
            ),
        ),
        ("合わせる", _rx(r"に(?:間に合|合わせ|向け)|逆算")),
    ),
}

MISS_RESULT_RULE = "間に合わないときの結果"
MISS_REPORT_RULE = "間に合わないときの連絡"

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_TAG = re.compile(r"<[^<>\n]*>")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*))?$")
_HEADING_CLOSE = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")


@dataclass(frozen=True)
class Mention:
    line: int
    text: str
    matches: tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    rule: str
    match: str


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    heading: str
    mentions: tuple[Mention, ...]
    info: dict[str, tuple[Evidence, ...]]

    def missing(self) -> list[str]:
        return [kind for kind in KINDS if not self.info[kind]]


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


def _strip_comments(line: str, inside: bool) -> tuple[str, bool]:
    parts: list[str] = []
    pos = 0
    while pos < len(line):
        if inside:
            end = line.find("-->", pos)
            if end < 0:
                return "".join(parts), True
            parts.append(" ")
            pos = end + 3
            inside = False
            continue
        start = line.find("<!--", pos)
        if start < 0:
            parts.append(line[pos:])
            break
        parts.append(line[pos:start])
        pos = start + 4
        inside = True
    return "".join(parts), inside


def mask(lines: list[str]) -> list[str]:
    """コード / HTML のコメントとタグ / URL を空白に置き換え、全角の数字を半角にする。行の数は変えない"""
    masked: list[str] = []
    fence: str | None = None
    in_comment = False
    for line in lines:
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            masked.append("")
            continue
        if not in_comment:
            opening = _FENCE.match(line)
            if opening and not (
                opening.group(1)[0] == "`" and "`" in line[opening.end() :]
            ):
                fence = opening.group(1)
                masked.append("")
                continue
        text, in_comment = _strip_comments(line, in_comment)
        text = _CODE_SPAN.sub(" ", text)
        text = _URL.sub(" ", text)
        text = _TAG.sub(" ", text)
        masked.append(text.translate(_WIDE))
    return masked


def parse_heading(line: str) -> Heading | None:
    found = _HEADING.match(line)
    if not found:
        return None
    text = _HEADING_CLOSE.sub("", found.group(2) or "").strip().rstrip(":：").strip()
    return Heading(len(found.group(1)), text)


def _normalize(name: str) -> str:
    return " ".join(name.split()).casefold()


def section_regions(masked: list[str], name: str) -> list[tuple[int, int]]:
    """見出しの文が name の節を、見出しの行から次の同じか上の階層の見出しの前まで返す"""
    want = _normalize(name)
    regions: list[tuple[int, int]] = []
    index = 0
    while index < len(masked):
        heading = parse_heading(masked[index])
        if heading is None or _normalize(heading.text) != want:
            index += 1
            continue
        end = index + 1
        while end < len(masked):
            following = parse_heading(masked[end])
            if following is not None and following.level <= heading.level:
                break
            end += 1
        regions.append((index, end))
        index = end
    return regions


def _trim(masked: list[str], start: int, end: int) -> tuple[int, int]:
    while end > start and not masked[end - 1].strip():
        end -= 1
    return start, end


def split_contexts(
    masked: list[str], start: int, end: int, scope: str
) -> list[tuple[int, int, str]]:
    """範囲を節か段落に分ける。段落に分けるときは見出しの行を含めない"""
    contexts: list[tuple[int, int, str]] = []
    heading_text = ""
    block_start: int | None = None
    block_heading = ""
    for index in range(start, end):
        heading = parse_heading(masked[index])
        boundary = heading is not None or (
            scope == PARAGRAPH and not masked[index].strip()
        )
        if boundary and block_start is not None:
            contexts.append((*_trim(masked, block_start, index), block_heading))
            block_start = None
        if heading is not None:
            heading_text = heading.text
            if scope == SECTION:
                block_start = index
                block_heading = heading_text
            continue
        if block_start is None and (scope == SECTION or masked[index].strip()):
            block_start = index
            block_heading = heading_text
    if block_start is not None:
        contexts.append((*_trim(masked, block_start, end), block_heading))
    return [context for context in contexts if context[0] < context[1]]


def deadline_matches(line: str) -> tuple[str, ...]:
    """締切の形に当たる文字列を、行の中の位置の順に返す。長い一致に含まれる短い一致は捨てる"""
    spans = sorted(
        {m.span() for pattern in DEADLINE_FORMS for m in pattern.finditer(line)},
        key=lambda span: (span[0], -span[1]),
    )
    kept: list[tuple[int, int]] = []
    for start, end in spans:
        if not any(s <= start and end <= e for s, e in kept):
            kept.append((start, end))
    return tuple(dict.fromkeys(line[start:end] for start, end in kept))


def sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_END.split(text) if part.strip()]


def judge(text: str) -> dict[str, tuple[Evidence, ...]]:
    """文から4つの情報の手がかりを集める。手がかりが1つでもあれば、その情報があると見る"""
    info: dict[str, list[Evidence]] = {kind: [] for kind in KINDS}
    for kind, rules in TEXT_RULES.items():
        for rule, pattern in rules:
            info[kind].extend(
                Evidence(rule, m.group(0)) for m in pattern.finditer(text)
            )
    for sentence in sentences(text):
        condition = _MISS_CONDITION.search(sentence)
        reporting = _REPORT_VERB.search(sentence)
        risk = _MISS_RISK.search(sentence)
        if condition and not reporting:
            info[IMPACT].append(Evidence(MISS_RESULT_RULE, condition.group(0)))
        if risk and reporting:
            match = f"{risk.group(0)} / {reporting.group(0)}"
            info[INTERIM].append(Evidence(MISS_REPORT_RULE, match))
    return {kind: tuple(dict.fromkeys(items)) for kind, items in info.items()}


def analyze(
    text: str, section: str | None = None, scope: str = SECTION
) -> list[Finding] | None:
    """締切の記述がある節か段落ごとに判定する。section の見出しが無ければ None を返す"""
    original = text.splitlines()
    masked = mask(original)
    if section is None:
        regions = [(0, len(masked))]
    else:
        regions = section_regions(masked, section)
        if not regions:
            return None
    findings: list[Finding] = []
    for region_start, region_end in regions:
        for start, end, heading in split_contexts(
            masked, region_start, region_end, scope
        ):
            mentions: list[Mention] = []
            for index in range(start, end):
                matches = deadline_matches(masked[index])
                if matches:
                    mentions.append(
                        Mention(index + 1, original[index].strip(), matches)
                    )
            if not mentions:
                continue
            body = "\n".join(masked[start:end])
            findings.append(
                Finding(start + 1, end, heading, tuple(mentions), judge(body))
            )
    return findings


def summarize(findings: list[Finding]) -> dict[str, int]:
    summary = {"contexts": len(findings)}
    summary["complete"] = sum(1 for finding in findings if not finding.missing())
    for kind in KINDS:
        summary[kind] = sum(1 for finding in findings if finding.info[kind])
    return summary


def to_json(findings: list[Finding], scope: str, section: str | None) -> dict:
    return {
        "scope": scope,
        "section": section,
        "summary": summarize(findings),
        "contexts": [
            {
                "start_line": finding.start,
                "end_line": finding.end,
                "heading": finding.heading,
                "mentions": [
                    {"line": m.line, "text": m.text, "matches": list(m.matches)}
                    for m in finding.mentions
                ],
                "info": {
                    kind: {
                        "present": bool(finding.info[kind]),
                        "evidence": [
                            {"rule": e.rule, "match": e.match}
                            for e in finding.info[kind]
                        ],
                    }
                    for kind in KINDS
                },
                "missing": finding.missing(),
            }
            for finding in findings
        ],
    }


def render_text(findings: list[Finding], scope: str) -> str:
    unit = UNIT_LABELS[scope]
    if not findings:
        return "締切の記述は見つからなかった\n"
    summary = summarize(findings)
    total = summary["contexts"]
    lines = [
        f"締切のある{unit} {total}件（4つがそろうのは{summary['complete']}件）",
        " / ".join(f"{LABELS[kind]} {summary[kind]}/{total}" for kind in KINDS),
    ]
    width = max(len(label) for label in LABELS.values())
    for number, finding in enumerate(findings, 1):
        where = f"{finding.start}〜{finding.end}行目"
        if finding.heading:
            where += f" 見出し「{finding.heading}」"
        lines += ["", f"{number}. {where}"]
        for mention in finding.mentions:
            lines.append(f"   締切 {mention.line}行目 {mention.text}")
        for kind in KINDS:
            evidence = finding.info[kind]
            label = LABELS[kind].ljust(width, "　")
            if evidence:
                found = " / ".join(dict.fromkeys(e.match for e in evidence))
                lines.append(f"   {label} あり「{found}」")
            else:
                lines.append(f"   {label} なし")
    return "\n".join(lines) + "\n"


def read_input(path: str | None) -> str:
    if path is None or path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("path", nargs="?", help="読むファイル（省略か - で標準入力）")
    parser.add_argument(
        "--section", help="この見出しの節だけを見る（例 Review Deadline）"
    )
    parser.add_argument(
        "--scope",
        choices=(SECTION, PARAGRAPH),
        default=SECTION,
        help="4つの情報を探す範囲（既定は節）",
    )
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    args = parser.parse_args(argv)
    try:
        text = read_input(args.path)
    except (OSError, UnicodeDecodeError) as error:
        print(f"deadline-brief-check: 入力を読めない: {error}", file=sys.stderr)
        return 2
    findings = analyze(text, args.section, args.scope)
    if findings is None:
        print(f"deadline-brief-check: 見出し「{args.section}」が無い", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                to_json(findings, args.scope, args.section),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_text(findings, args.scope), end="")
    return 1 if any(finding.missing() for finding in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
