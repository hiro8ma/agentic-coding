#!/usr/bin/env python3
"""エージェントの報告（Markdown）から、使う前に確かめる主張を拾う。

Usage:
    python3 claim_check.py [FILE ...]               # FILE がなければ標準入力を読む
    python3 claim_check.py --repo OWNER/NAME FILE   # path@sha:line の引用を gh api で照合する
    python3 claim_check.py --strict FILE            # 拾った主張があれば終了コード1
    python3 claim_check.py --hook                   # Claude Code の hook。標準入力の JSON から報告を読む

拾うもの
- 探した範囲を書いていない不在の主張
- 出典を書いていない数値
- path@sha:line の引用の形の誤り（--repo を付けたときは、ファイルと行も照合する）
- 証拠を書いていない完了と保存の主張

終了コードは0。--strict を付けたときだけ、拾った主張があれば1。入力を読めないときは2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

ABSENCE = "absence"
NUMBER = "number"
COMPLETION = "completion"
CITATION = "citation"
KINDS = (ABSENCE, NUMBER, COMPLETION, CITATION)

KIND_LABELS = {
    ABSENCE: "不在の主張",
    NUMBER: "出典のない数値",
    COMPLETION: "証拠のない完了",
    CITATION: "引用の誤り",
}

# Claude Code は additionalContext を10,000字で切る
HOOK_CONTEXT_LIMIT = 9000
MAX_CITED_LINES = 20


@dataclass(eq=False)
class Unit:
    """箇条書きの1項目 / 表の1行 / 段落。探した範囲と出典はこの単位の中で探す"""

    kind: str
    section: str
    indent: int = 0
    parts: list[tuple[int, str]] = field(default_factory=list)
    parent: Unit | None = None
    children: list[Unit] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    row_source: str = ""
    table: int = -1
    skip: bool = False

    def text(self) -> str:
        return "\n".join(text for _, text in self.parts)

    def descendants(self) -> list[Unit]:
        found: list[Unit] = []
        for child in self.children:
            found.append(child)
            found.extend(child.descendants())
        return found

    def ancestors(self) -> list[Unit]:
        found: list[Unit] = []
        node = self.parent
        while node is not None:
            found.append(node)
            node = node.parent
        return found


@dataclass(frozen=True)
class Claim:
    line: int
    text: str
    unit: Unit
    previous: str = ""


@dataclass(frozen=True)
class Document:
    claims: list[Claim]
    citations: list[tuple[int, str]]
    footnotes: frozenset[str]


_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d{1,3}[.)])\s+(.*)$")
_TASK = re.compile(r"^\[([ xX])\]\s*")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_FOOTNOTE_DEF = re.compile(r"^\s*\[\^([^\]\s]+)\]:\s*(.*)$")
_HR = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_YAML_LINE = re.compile(r"^(?:[\w-]+\s*:|\s+\S|\s*-\s)")
_SOURCE_HEADER = re.compile(
    r"出典|根拠|ソース|引用|参照|確認方法|証拠|source|evidence|reference|citation|link|url",
    re.IGNORECASE,
)
_EMPTY_CELL = {"", "-", "—", "なし", "n/a", "N/A", "未確認"}


def _cells(line: str) -> list[str]:
    body = line.strip()
    body = body.removeprefix("|")
    body = body.removesuffix("|")
    return [cell.strip() for cell in body.split("|")]


def _strip_comments(lines: list[str]) -> list[str]:
    text = _HTML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), "\n".join(lines))
    return text.split("\n")


def parse(text: str) -> Document:
    lines = _strip_comments(text.splitlines())
    units: list[Unit] = []
    citations: list[tuple[int, str]] = []
    footnotes: set[str] = set()
    section = ""
    stack: list[Unit] = []
    last: Unit | None = None
    para: Unit | None = None
    table_header: list[str] | None = None
    source_col = -1
    table_id = 0
    fence: str | None = None
    fence_body: list[str] = []
    i = 0

    if lines and lines[0].strip() == "---":
        end = next((j for j in range(1, len(lines)) if lines[j].strip() == "---"), -1)
        if end > 0 and all(
            _YAML_LINE.match(line) for line in lines[1:end] if line.strip()
        ):
            i = end + 1

    def new_unit(kind: str, indent: int, lineno: int, body: str) -> Unit:
        nonlocal last
        unit = Unit(kind=kind, section=section, indent=indent, parts=[(lineno, body)])
        units.append(unit)
        last = unit
        return unit

    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        i += 1
        if fence is not None:
            if raw.strip().startswith(fence):
                if last is not None:
                    last.blocks.append("\n".join(fence_body))
                fence = None
                fence_body = []
            else:
                fence_body.append(raw)
            continue
        opened = _FENCE.match(raw)
        if opened:
            fence = opened.group(1)[0] * 3
            para = None
            continue
        if not raw.strip():
            para = None
            table_header = None
            continue
        for match in _CITATION.finditer(raw):
            citations.append((lineno, match.group(0)))
        heading = _HEADING.match(raw)
        if heading:
            section = heading.group(2)
            stack.clear()
            last = para = None
            table_header = None
            continue
        if _HR.match(raw):
            para = None
            continue
        footnote = _FOOTNOTE_DEF.match(raw)
        if footnote:
            footnotes.add(footnote.group(1))
            para = None
            continue
        if raw.lstrip().startswith(">"):
            if last is not None:
                last.blocks.append(raw.lstrip()[1:].strip())
            continue
        if raw.lstrip().startswith("|"):
            para = None
            stack.clear()
            next_line = lines[i] if i < len(lines) else ""
            if table_header is None and _TABLE_SEP.match(next_line):
                table_header = _cells(raw)
                table_id += 1
                source_col = next(
                    (n for n, h in enumerate(table_header) if _SOURCE_HEADER.search(h)),
                    -1,
                )
                i += 1
                continue
            if _TABLE_SEP.match(raw):
                continue
            cells = _cells(raw)
            unit = new_unit("row", 0, lineno, " | ".join(cells))
            unit.table = table_id if table_header is not None else -1
            if 0 <= source_col < len(cells) and cells[source_col] not in _EMPTY_CELL:
                unit.row_source = cells[source_col]
            continue
        table_header = None
        bullet = _BULLET.match(raw)
        if bullet:
            para = None
            indent = len(bullet.group(1).expandtabs(4))
            body = bullet.group(2)
            task = _TASK.match(body)
            while stack and stack[-1].indent >= indent:
                stack.pop()
            unit = new_unit("bullet", indent, lineno, _TASK.sub("", body, count=1))
            unit.skip = bool(task and task.group(1) == " ")
            if stack:
                unit.parent = stack[-1]
                stack[-1].children.append(unit)
            stack.append(unit)
            continue
        indent = len(raw) - len(raw.lstrip())
        if stack and indent > stack[-1].indent and para is None:
            stack[-1].parts.append((lineno, raw.strip()))
            last = stack[-1]
            continue
        if para is not None:
            para.parts.append((lineno, raw.strip()))
            continue
        stack.clear()
        para = new_unit("para", indent, lineno, raw.strip())

    claims: list[Claim] = []
    for unit in units:
        if unit.skip:
            continue
        previous = ""
        for line, sentence in _sentences(unit):
            claims.append(Claim(line, sentence, unit, previous))
            previous = sentence
    return Document(claims, citations, frozenset(footnotes))


_SENTENCE_END = re.compile(r"(?<=[。！？!?])|(?<=\.)(?=\s+[A-Z「\"`*])")
_ABBREVIATION = re.compile(
    r"(?:\bet al|\be\.g|\bi\.e|\bcf|\bvs|\bFig|\bTab|\bSec|\bEq|\bNo|\bpp?|\bapprox|\bSt|\bDr|\bMr|\bMs)\.$"
)
_TERMINAL = tuple("。！？!?.:：")


def _sentences(unit: Unit) -> list[tuple[int, str]]:
    """単位を文に分ける。行の区切りは文の区切りとし、折り返した英文だけを1行につなぐ"""
    logical: list[tuple[list[tuple[int, int]], str]] = []
    for lineno, text in unit.parts:
        text = text.strip()
        if not text:
            continue
        if (
            logical
            and unit.kind != "row"
            and not logical[-1][1].endswith(_TERMINAL)
            and text[0].islower()
            and text[0].isascii()
        ):
            offsets, joined = logical[-1]
            offsets.append((len(joined) + 1, lineno))
            logical[-1] = (offsets, joined + " " + text)
        else:
            logical.append(([(0, lineno)], text))
    result: list[tuple[int, str]] = []
    for offsets, text in logical:
        starts = [offset for offset, _ in offsets]
        pos = 0
        for piece in _split_keep_offsets(text):
            stripped = piece.strip()
            if stripped:
                start = pos + piece.index(stripped[0])
                result.append((offsets[bisect_right(starts, start) - 1][1], stripped))
            pos += len(piece)
    return result


def _split_keep_offsets(text: str) -> list[str]:
    masked = _URL.sub(lambda m: "x" * len(m.group(0)), text)
    masked = _INLINE_CODE.sub(lambda m: "x" * len(m.group(0)), masked)
    pieces: list[str] = []
    last = 0
    for match in _SENTENCE_END.finditer(masked):
        if _ABBREVIATION.search(masked[: match.start()]):
            continue
        if match.start() > last:
            pieces.append(text[last : match.start()])
            last = match.start()
    pieces.append(text[last:])
    return pieces


_URL = re.compile(r"https?://[^\s)>\]」』]+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\((?:https?://)?[^)\s]+\)")
_INLINE_CODE = re.compile(r"(`+)(.+?)\1")
_CITATION = re.compile(
    r"(?<![\w/.@-])(?P<path>[A-Za-z0-9_./-]*[A-Za-z0-9_-][./][A-Za-z0-9_./-]*)"
    r"@(?P<ref>[A-Za-z0-9_.-]+):(?P<lines>\d+(?:-\d+)?)\b"
)
_PATH_LINE = re.compile(
    r"(?<![\w/])[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z]{1,6}:\d+"
)
_FOOTNOTE_REF = re.compile(r"\[\^([^\]\s]+)\]")
_BRACKET_REF = re.compile(r"\[[Ss]?\d{1,3}(?:[,\s]+[Ss]?\d{1,3})*\](?![(:])")
_SHA = re.compile(
    r"(?<![A-Za-z0-9])(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![A-Za-z0-9])"
)
_ARXIV = re.compile(
    r"(?:arXiv:\s*)?(?<!\d)\d{4}\.\d{4,5}(?:v\d+)?(?!\d)", re.IGNORECASE
)
_LOCATOR = re.compile(
    r"(?:\b(?:Table|Tab\.|Fig\.|Figure|Section|Sec\.|Appendix|Eq\.)\s*[A-Z]?\d+"
    r"|(?:表|図|式|付録)\s*[A-Z]?\d+|§\s*\d+|\bpp?\.\s*\d+|\bL\d+(?:-L?\d+)?\b|\d+\s*ページ)"
)
_SOURCE_LABEL = re.compile(
    r"出典\s*[:：]|引用元\s*[:：]|ソース\s*[:：]|\bsources?\s*:", re.IGNORECASE
)
_ACADEMIC = re.compile(
    r"\b[A-Z][A-Za-z-]+(?: et al\.?| and [A-Z][A-Za-z-]+)?,? \(?\d{4}[a-z]?\)?"
)
_FILE_EXT = (
    r"py|go|ts|tsx|js|jsx|mjs|md|yaml|yml|json|jsonl|toml|sql|sh|rs|txt|csv|tsv|"
    r"ipynb|html|css|rb|java|kt|swift|c|h|cc|cpp|proto|tf|ini|cfg|lock|xml|log"
)
_PATH = re.compile(
    rf"^(?:\.{{0,2}}/)?[\w.@-]+(?:/[\w.@-]+)*(?:/|\.(?:{_FILE_EXT}))(?::\d+(?:-\d+)?)?$"
    rf"|^[\w.-]+/[\w./-]+$"
)
_BARE_PATH = re.compile(
    rf"(?<![\w/.])(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.(?:{_FILE_EXT}))?(?![\w/])"
    rf"|(?<![\w/.])[A-Za-z0-9_-]+\.(?:{_FILE_EXT})(?![\w.])"
)
_CLI = frozenset(
    [
        "git",
        "gh",
        "grep",
        "egrep",
        "rg",
        "ag",
        "ack",
        "find",
        "fd",
        "ls",
        "cat",
        "head",
        "tail",
        "sed",
        "awk",
        "jq",
        "yq",
        "wc",
        "sort",
        "uniq",
        "diff",
        "curl",
        "wget",
        "python",
        "python3",
        "pip",
        "pip3",
        "uv",
        "uvx",
        "pytest",
        "ruff",
        "mypy",
        "pyright",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "bun",
        "node",
        "deno",
        "tsc",
        "go",
        "gofmt",
        "golangci-lint",
        "staticcheck",
        "cargo",
        "rustc",
        "make",
        "docker",
        "kubectl",
        "helm",
        "terraform",
        "gcloud",
        "gsutil",
        "bq",
        "aws",
        "az",
        "psql",
        "mysql",
        "sqlite3",
        "duckdb",
        "sh",
        "bash",
        "zsh",
        "codex",
        "claude",
        "ssh",
        "rsync",
        "tree",
        "du",
        "stat",
        "file",
        "xargs",
        "env",
        "time",
        "timeout",
    ]
)
_OUTPUT = re.compile(
    r"\b(?:passed|failed|OK|errors?|warnings?|Ran \d+|exit(?: code| status)?\s*[:=]?\s*\d+"
    r"|All checks passed|\d+ (?:tests?|passed|failed|files?|rows?|lines?|matches|errors?)"
    r"|HTTP/\d|\d+ files? (?:changed|reformatted|left unchanged))\b"
)


def _code_spans(text: str) -> list[str]:
    return [match.group(2).strip() for match in _INLINE_CODE.finditer(text)]


def is_command(code: str) -> bool:
    body = code.strip()
    if body.startswith("$ "):
        return True
    words = body.split()
    if not words:
        return False
    first = words[0].rsplit("/", 1)[-1]
    if first in _CLI or words[0].startswith("./"):
        return True
    if first.upper() in ("SELECT", "WITH") and len(words) >= 3:
        return True
    return len(words) >= 2 and any(re.match(r"--?[A-Za-z]", word) for word in words[1:])


def is_output(code: str) -> bool:
    return bool(_OUTPUT.search(code))


def is_path(code: str) -> bool:
    return " " not in code.strip() and bool(_PATH.match(code.strip()))


@dataclass(frozen=True)
class Evidence:
    url: bool = False
    command: bool = False
    output: bool = False
    path: bool = False
    citation: bool = False
    sha: bool = False
    footnote: bool = False
    locator: bool = False
    label: bool = False
    scope: bool = False

    def __or__(self, other: Evidence) -> Evidence:
        return Evidence(
            **{name: getattr(self, name) or getattr(other, name) for name in _FIELDS}
        )


_FIELDS = tuple(Evidence.__dataclass_fields__)

_SCOPE = re.compile(
    r"(?:を|で)検索|検索し(?:た|て|ても)|検索の結果|検索をかけ|探し(?:た|て)|探索し"
    r"|読んだ|を読んで|読み通し|調べ(?:た|て)|確かめ(?:た|て)|洗い出し|走査し|照合し|突き合わせ"
    r"|の範囲で|の範囲では|範囲を|を対象に|を対象とし|全体を|全文を|全件を|数え(?:た|て)|集計し(?:た|て)"
    r"|\bgrep|\brg\b|ripgrep|gh search|git grep|git log -S"
    r"|\bsearch(?:ed|ing)?\s+(?:for|in|through|across|the)\b|\bsearched\b|\bscanned\b"
    r"|\blooked\s+(?:in|at|through|for)\b|\bchecked\s+(?:all|every|each|in|the|across)\b"
    r"|\bread\s+(?:all|every|through|the\s+(?:whole|entire))\b|\bafter\s+reading\b"
    r"|\bacross\s+(?:all|the|every)\b|\bin\s+the\s+(?:whole|entire)\b",
    re.IGNORECASE,
)


def evidence_of(text: str, footnotes: frozenset[str] = frozenset()) -> Evidence:
    codes = _code_spans(text)
    plain = _INLINE_CODE.sub(" ", text)
    return Evidence(
        url=bool(_URL.search(text)),
        command=any(is_command(code) for code in codes),
        output=any(is_output(code) for code in codes),
        path=any(is_path(code) for code in codes) or bool(_BARE_PATH.search(plain)),
        citation=bool(_CITATION.search(text) or _PATH_LINE.search(text)),
        sha=bool(_SHA.search(text)),
        footnote=any(ref in footnotes for ref in _FOOTNOTE_REF.findall(text))
        or bool(_BRACKET_REF.search(plain)),
        locator=bool(_LOCATOR.search(plain)) or bool(_ARXIV.search(plain)),
        label=bool(_SOURCE_LABEL.search(plain)) or bool(_ACADEMIC.search(plain)),
        scope=bool(_SCOPE.search(plain)),
    )


def block_evidence(blocks: list[str]) -> Evidence:
    if not any(block.strip() for block in blocks):
        return Evidence()
    joined = "\n".join(blocks)
    lines = [line.strip() for line in joined.splitlines() if line.strip()]
    command = any(is_command(line) for line in lines)
    return Evidence(output=True, command=command, scope=command)


_QUOTED = re.compile(r"「[^「」]*」|『[^『』]*』|“[^”]*”|\"[^\"\n]{1,200}\"")

_HONEST = re.compile(
    r"未確認|未検証|未計測|未測定|未実施|不明|推測|推定|"
    r"(?:確認|検証|計測|測定|再現|調査|実行|照合)(?:して|できて|でき|しきれて)?い?(?:ない|ません|おらず)|"
    r"確かめ(?:て|られて|きれて)?い?(?:ない|ません)|(?:分か|わか|決ま|測)ってい(?:ない|ません)|"
    r"(?:見|試し|調べ|比べ)てい(?:ない|ません)|読(?:んでい|めてい|めなかっ)(?:ない|ません|た)|"
    r"\b(?:unverified|unconfirmed|unknown|TBD|not\s+(?:yet\s+)?(?:verified|checked|tested|confirmed|measured))\b|"
    r"\b(?:did|have|has|could)\s*(?:not|n't)\s+(?:yet\s+)?(?:verif|check|confirm|test|measur|run)\w*",
    re.IGNORECASE,
)

_JA_ABSENCE = re.compile(
    r"(?:見つから|見当たら)(?:ない|なかった|ず|ません)"
    r"|存在(?:しない|しなかった|せず|しません|しておらず|していない)"
    r"|(?:てい?(?:ない|なかった|ません)|でい(?:ない|なかった|ません)|[てで]おらず)"
    r"|(?:さ|わ|ば|ま|か)れ(?:ない|なかった|ず|ません)"
    r"|(?<!で)(?<!じゃ)[がはもに](?:一切|どこにも|特に|全く|まったく|何も|ほとんど|まだ)?"
    r"(?:無い|ない|無く|なく|無かった|なかった|ありません|ございません|無し|なし)"
    r"|未(?:実装|対応|定義|設定|使用|導入|接続|登録|反映|適用)"
    r"|欠落|欠如|不在|(?:欠け|抜け|抜け落ち)てい"
    r"|(?:^|(?<=[\s|:]))(?:該当)?(?:なし|無し)(?=\s*(?:$|[|。)、,/]))"
)
_JA_IDIOM_BEFORE = (
    "必要",
    "意味",
    "余地",
    "仕方",
    "しょう",
    "間違い",
    "変わり",
    "心配",
    "疑い",
    "他",
    "ほか",
    "しか",
    "間",
    "程",
    "ほど",
    "何で",
    "とんで",
    "遠慮",
    "申し分",
    "文句",
    "抜かり",
    "限り",
)
# 自分の作業をまだしていないという報告は、外の状態についての不在の主張として扱わない
_JA_SELF_UNDONE = re.compile(
    r"(?:保存|プッシュ|push|コミット|commit|マージ|merge|デプロイ|deploy|反映|適用|apply|登録|送信|投稿|"
    r"公開|記録|アップロード|upload|着手)\s*し$|書き込ん$",
    re.IGNORECASE,
)
_JA_CONDITIONAL_AFTER = re.compile(
    r"^(?:場合|とき|時|なら|ように|よう|限り|か(?!ら)|でしょう|だろう|かも|はず|と|で(?![すし])|くても|くて(?:よい|いい|良い|も)|ければ"
    r"|ことを(?:指摘|言|聞|伝))"
)
_NOUN_START = re.compile(r"^[\u4e00-\u9fff\u30a0-\u30ffA-Za-z]")
_JA_ABSENCE_IDIOM_WHOLE = re.compile(
    r"かもしれない|に違いない|に過ぎない|にすぎない|とは限らない"
)

_EN_ABSENCE = re.compile(
    r"\bno\s+(?!(?:longer|need|more|matter|doubt|later|earlier|less|fewer|sooner|worse|better|"
    r"idea|way|particular|sense)\b)(?=\w)"
    r"|\bnot\s+found\b|\bnothing\s+(?:was|is|were|has\s+been|had\s+been)?\s*\w+ed\b|\bnothing\s+(?:was\s+)?(?:found|written|sent|set)\b|\bfound\s+no(?:thing)?\b"
    r"|\b(?:could|can|did)\s*(?:not|n't|\s+not)\s+(?:find|locate|see)\b|\bcannot\s+(?:find|locate)\b"
    r"|\bunable\s+to\s+(?:find|locate)\b|\b(?:does|do|did)\s*(?:not|n't)\s+exist\b"
    r"|\bnon-?existent\b|\bunimplemented\b|\bnone\b"
    r"|\b(?:is|are|was|were)\s*(?:not|n't)\s+(?:yet\s+)?(?:any|implemented|present|used|called|"
    r"set|run|written|read|available|supported|handled|defined|configured|imported|referenced|"
    r"included|stored|saved|filtered|excluded|covered|wired|enabled|registered|applied)\b"
    r"|\b(?:is|are|was|were)\s+missing\b|\bmissing\s+from\b|\blacks?\b|\black\s+of\b"
    r"|\bnever\s+(?:\w+ed|set|read|written|run|sent|built|hit)\b|\bthere\s+(?:is|are|was|were)\s*(?:not|n't)\b"
    r"|\b(?:does|did|do)\s*(?:not|n't)\s+(?!(?:matter|mean|seem|appear|need|want|know|think|make|"
    r"care|guarantee|verify|check|confirm|test|measure|run|exist|find|have\s+to)\b)[a-z]+",
    re.IGNORECASE,
)
_EN_NONE_CASE = re.compile(r"\bnone\b|(?:^|[.;:]\s+)None\s+(?:of|were|was|found|exist)")
_EN_NO_ACTION = re.compile(
    r"\bno\s+(?:further\s+)?(?:action|changes?)\s+(?:is\s+|are\s+)?(?:needed|required)\b",
    re.IGNORECASE,
)

_JA_COMPLETION = re.compile(
    r"(?:保存|プッシュ|push|コミット|commit|マージ|merge|デプロイ|deploy|反映|適用|apply|登録|"
    r"書き込|書き出|アップロード|upload|送信|投稿|公開|記録)\s*"
    r"(?:しました|した|済み|済|されました|された|できました|できた|んだ|みました|みした)"
    r"|(?:通った|通りました|通過した|通過しました|パスした|パスしました|成功した|成功しました|"
    r"緑になった|グリーンになった|オールグリーン|全件通|全件成功)"
    r"|確認済み|動作確認(?:した|しました|済み)",
    re.IGNORECASE,
)
_JA_COMPLETION_AFTER = re.compile(
    r"^(?:ら|い|か|方|がる|場合|とき|時|つもり|はず|ことにする)"
)

_EN_COMPLETION = re.compile(
    r"\b(?:saved|pushed|committed|merged|deployed|uploaded|published|persisted|stored|posted|"
    r"written\s+to|applied)\b",
    re.IGNORECASE,
)
_EN_COMPLETION_BEFORE = re.compile(
    r"\b(?:will|would|should|must|can|could|may|might|to|be|not|n't|never|if|when|unless|"
    r"the|a|an|this|that|its|their|any|once|whether)\s+(?:\w+\s+)?$",
    re.IGNORECASE,
)
_EN_PASSED = re.compile(
    r"\b(?:tests?|checks?|CI|build|lint(?:ers?)?|suite|ruff|pytest|unittest|type\s*checks?)\b"
    r"[^.;]{0,40}?\b(?:pass(?:ed|es|ing)?|succeeded|green)\b"
    r"|\ball\s+(?:\w+\s+){0,3}pass(?:ed)?\b",
    re.IGNORECASE,
)
_EN_NEGATION = re.compile(r"\b(?:not|n't|never|fail(?:ed|s|ing)?)\b", re.IGNORECASE)

_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_UNIT_NUMBER = re.compile(
    rf"(?<![A-Za-z0-9_.@/#-]){_NUM}\s*(?:%|件|人|倍|割|pt\b|ポイント|pp\b|percent\b|points?\b|x(?![\w.])|×)"
)
_DECIMAL = re.compile(r"(?<![A-Za-z0-9_.@/:#-])\d+\.\d+(?!\.?\d)")
_VERSION_WORDS = (
    r"python|go|node(?:\.?js)?|java|ruby|rust|php|bun|deno|version|ver\.?|バージョン|release|"
    r"リリース|opus|sonnet|haiku|claude(?:\s+code)?|gpt|gemini|gemma|llama|qwen|mistral|ios|"
    r"android|macos|ubuntu|debian|windows|chrome|safari|firefox|typescript|react|next(?:\.js)?|"
    r"django|rails|kubernetes|terraform|codex(?:\s+cli)?|cli|api|http|tls|oauth|utf|unicode|step|"
    r"ステップ|section|sec\.?|§|table|tab\.?|fig\.?|figure|表|図|式|章|節|eq\.?|chapter|phase|"
    r"フェーズ|v"
)
# 「Python 3.9 と 3.15」のように並べた版も版として扱う
_VERSION_BEFORE = re.compile(
    rf"(?:{_VERSION_WORDS})\s*(?:\d+(?:\.\d+)*\s*(?:と|、|,|/|and|or|から|to|〜|-)\s*)*$",
    re.IGNORECASE,
)
_HONEST_SECTION = re.compile(
    r"限界|制約|未解決|limitations?|caveats?|known\s+issues|open\s+questions",
    re.IGNORECASE,
)
_CONCLUSION = re.compile(
    r"結論|まとめ|要約|要点|サマリ|tl;?dr|summary|conclusion|key\s+findings|bottom\s+line|所見",
    re.IGNORECASE,
)


def _scrub(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INLINE_CODE.sub(" ⟨code⟩ ", text)
    text = _MD_LINK.sub(lambda m: m.group(1), text)
    text = _URL.sub(" ⟨url⟩ ", text)
    text = _CITATION.sub(" ⟨cite⟩ ", text)
    text = _PATH_LINE.sub(" ⟨cite⟩ ", text)
    text = _FOOTNOTE_REF.sub(" ", text)
    text = _BRACKET_REF.sub(" ", text)
    text = _ARXIV.sub(" ⟨id⟩ ", text)
    return text


def _unquote(text: str) -> str:
    return _QUOTED.sub(" ⟨quote⟩ ", text)


def is_question(scrubbed: str) -> bool:
    return scrubbed.rstrip().endswith(("?", "？"))


def find_absence(scrubbed: str) -> str | None:
    text = _unquote(scrubbed)
    for match in _JA_ABSENCE.finditer(text):
        before = text[: match.start()]
        after = text[match.end() :]
        if before.endswith(_JA_IDIOM_BEFORE):
            continue
        if match.group(0).startswith(("て", "で")) and (
            _JA_SELF_UNDONE.search(before)
            or "今回" in before
            or re.search(r"[はも]し$", before)
        ):
            continue
        # 「評価していない作品は」のように名詞にかかる形は、主張の述語でない
        if _NOUN_START.match(after):
            continue
        if _JA_CONDITIONAL_AFTER.match(after):
            continue
        window = text[max(0, match.start() - 4) : match.end() + 4]
        if _JA_ABSENCE_IDIOM_WHOLE.search(window):
            continue
        return match.group(0)
    for match in _EN_ABSENCE.finditer(text):
        word = match.group(0)
        if word.lower() == "none" and not _EN_NONE_CASE.search(
            text[max(0, match.start() - 3) : match.end() + 8]
        ):
            continue
        if _EN_NO_ACTION.match(text, match.start()):
            continue
        lowered = word.lower()
        if (
            lowered.startswith(("do not", "don't", "do n't"))
            and not text[: match.start()].strip()
        ):
            continue
        # 「I did not 〜」は自分の作業の報告として扱う。探す動詞のときだけ不在の主張にする
        if (
            lowered.startswith(("did not", "didn't", "do not", "don't", "do n't"))
            and re.search(r"\b(?:I|we)\s*$", text[: match.start()], re.IGNORECASE)
            and not re.search(r"\b(?:find|locate|see|exist)\b", lowered)
        ):
            continue
        return word
    return None


def find_numbers(scrubbed: str) -> list[str]:
    found: list[str] = []
    for match in _UNIT_NUMBER.finditer(scrubbed):
        found.append(match.group(0).strip())
    for match in _DECIMAL.finditer(scrubbed):
        if any(match.group(0) in item for item in found):
            continue
        if _VERSION_BEFORE.search(scrubbed[: match.start()]):
            continue
        found.append(match.group(0))
    return found


def find_completion(scrubbed: str) -> str | None:
    for match in _JA_COMPLETION.finditer(scrubbed):
        if _JA_COMPLETION_AFTER.match(scrubbed[match.end() :]):
            continue
        return match.group(0)
    for match in _EN_COMPLETION.finditer(scrubbed):
        before = scrubbed[: match.start()]
        if _EN_COMPLETION_BEFORE.search(before):
            continue
        if re.search(r"\b(?:is|are)\s+$", before):
            continue
        if re.search(r"\b(?:nothing|none|no|never|not)\b", before, re.IGNORECASE):
            continue
        return match.group(0)
    for match in _EN_PASSED.finditer(scrubbed):
        if _EN_NEGATION.search(match.group(0)):
            continue
        return match.group(0)
    return None


@dataclass(frozen=True)
class Flag:
    kind: str
    priority: int
    line: int
    text: str
    reason: str
    hint: str
    section: str = ""
    table: int = -1


@dataclass(frozen=True)
class CitationResult:
    line: int
    citation: str
    status: str
    detail: str = ""
    lines: tuple[tuple[int, str], ...] = ()


@dataclass
class Report:
    claims: int
    flags: list[Flag]
    citations: list[CitationResult]
    repo: str | None = None

    def flagged(self) -> bool:
        return bool(self.flags)


def _context_evidence(claim: Claim, doc: Document, *, scope: bool) -> Evidence:
    unit = claim.unit
    footnotes = doc.footnotes
    evidence = evidence_of(claim.text, footnotes) | block_evidence(unit.blocks)
    for child in unit.descendants():
        evidence = (
            evidence
            | evidence_of(child.text(), footnotes)
            | block_evidence(child.blocks)
        )
    if unit.row_source:
        evidence = (
            evidence | Evidence(label=True) | evidence_of(unit.row_source, footnotes)
        )
    if scope:
        # 「〜を検索した。見つからなかった」のように、範囲は直前の文に書かれることが多い
        evidence = evidence | evidence_of(claim.previous, footnotes)
        for ancestor in unit.ancestors():
            evidence = evidence | evidence_of(ancestor.text(), footnotes)
    return evidence


def _source_evidence(claim: Claim, doc: Document) -> Evidence:
    evidence = _context_evidence(claim, doc, scope=False)
    for ancestor in claim.unit.ancestors():
        evidence = evidence | evidence_of(ancestor.text(), doc.footnotes)
    if claim.unit.section:
        evidence = evidence | evidence_of(claim.unit.section, doc.footnotes)
    return evidence


def _clip(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def check_claim(claim: Claim, doc: Document) -> list[Flag]:
    scrubbed = _scrub(claim.text)
    if is_question(scrubbed) or _HONEST.search(scrubbed):
        return []
    section = claim.unit.section
    if section and (_HONEST.search(section) or _HONEST_SECTION.search(section)):
        return []
    flags: list[Flag] = []
    absence = find_absence(scrubbed)
    if absence:
        ev = _context_evidence(claim, doc, scope=True)
        # URL を添えた「この資料は〜を書いていない」は、読んだ資料が範囲になる
        if not (
            ev.scope or ev.command or ev.path or ev.citation or ev.url or ev.footnote
        ):
            flags.append(
                Flag(
                    ABSENCE,
                    1,
                    claim.line,
                    _clip(claim.text),
                    f"「{absence}」と書いたが、探した範囲と方法がない",
                    "どこを、どの方法で探したかを確かめる。import 先 / 設定 / 呼び出し元も含める",
                    section,
                )
            )
    numbers = find_numbers(scrubbed)
    if numbers:
        ev = _source_evidence(claim, doc)
        if not (
            ev.url
            or ev.citation
            or ev.command
            or ev.footnote
            or ev.locator
            or ev.label
            or ev.path
        ):
            conclusion = bool(_CONCLUSION.search(section))
            where = f"（{section}）" if conclusion else ""
            flags.append(
                Flag(
                    NUMBER,
                    1 if conclusion else 3,
                    claim.line,
                    _clip(claim.text),
                    f"{', '.join(numbers[:3])} に出典がない{where}",
                    "原典の該当箇所を開き、値と、何と比べた値かを確かめる",
                    section,
                    claim.unit.table,
                )
            )
    completion = find_completion(scrubbed)
    if completion:
        ev = _context_evidence(claim, doc, scope=False)
        if not (ev.command or ev.output or ev.url or ev.sha or ev.citation):
            flags.append(
                Flag(
                    COMPLETION,
                    2,
                    claim.line,
                    _clip(claim.text),
                    f"「{completion}」と書いたが、コマンド / 出力 / URL がない",
                    "実行したコマンドと出力、または保存先の URL を開いて確かめる",
                    section,
                )
            )
    return flags


@dataclass(frozen=True)
class FetchResult:
    """content が None なら取れなかった。missing は、ファイルか commit が無いと確かめられたこと"""

    content: str | None
    error: str = ""
    missing: bool = False


Fetcher = Callable[[str, str, str], FetchResult]


@dataclass(frozen=True)
class _Cited:
    path: str
    ref: str
    first: int
    last: int


def parse_citation(citation: str) -> tuple[_Cited | None, str]:
    """(引用, 形の誤り)。形が正しければ誤りは空文字"""
    match = _CITATION.fullmatch(citation)
    if not match:
        return None, "path@sha:行 の形で読めない"
    path, ref, lines = match.group("path"), match.group("ref"), match.group("lines")
    if path.startswith("/") or ".." in path.split("/"):
        return None, "リポジトリの中のパスでない"
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        return None, f"{ref} は commit の sha でない。ブランチなら後で中身が変わる"
    start, _, end = lines.partition("-")
    first, last = int(start), int(end or start)
    if first < 1 or last < first:
        return None, f"行の範囲 {lines} が正しくない"
    return _Cited(path, ref, first, last), ""


def gh_fetch(repo: str, path: str, ref: str) -> FetchResult:
    endpoint = f"repos/{repo}/contents/{quote(path)}?ref={quote(ref)}"
    try:
        proc = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw+json", endpoint],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return FetchResult(None, "gh が見つからない")
    except subprocess.TimeoutExpired:
        return FetchResult(None, "gh api が30秒で終わらなかった")
    if proc.returncode != 0:
        message = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        text = (
            message[-1]
            if message
            else f"gh api が終了コード{proc.returncode}で失敗した"
        )
        if "No commit found" in text:
            return FetchResult(None, f"commit {ref} がない", missing=True)
        if "Not Found" in text:
            return FetchResult(None, "ファイルがない", missing=True)
        return FetchResult(None, f"照合できなかった（{text}）")
    body = proc.stdout.decode("utf-8", "replace")
    # ディレクトリを指すと、raw を求めても中身の一覧の JSON が返る
    if body.startswith("[{") and '"path"' in body[:500]:
        try:
            listing = json.loads(body)
        except ValueError:
            listing = None
        if isinstance(listing, list) and all(
            isinstance(e, dict) and "type" in e for e in listing
        ):
            return FetchResult(None, "ディレクトリでファイルでない", missing=True)
    return FetchResult(body)


def verify_citations(
    citations: list[tuple[int, str]], repo: str | None, fetch: Fetcher | None = None
) -> list[CitationResult]:
    fetch = fetch or gh_fetch
    results: list[CitationResult] = []
    cache: dict[tuple[str, str], FetchResult] = {}
    for line, citation in citations:
        cited, problem = parse_citation(citation)
        if cited is None:
            results.append(CitationResult(line, citation, "error", problem))
            continue
        if repo is None:
            results.append(CitationResult(line, citation, "unchecked"))
            continue
        key = (cited.path, cited.ref)
        if key not in cache:
            cache[key] = fetch(repo, cited.path, cited.ref)
        fetched = cache[key]
        if fetched.content is None:
            status = "error" if fetched.missing else "unavailable"
            results.append(CitationResult(line, citation, status, fetched.error))
            continue
        file_lines = fetched.content.splitlines()
        first, last = cited.first, cited.last
        if last > len(file_lines):
            results.append(
                CitationResult(
                    line,
                    citation,
                    "error",
                    f"ファイルは{len(file_lines)}行で、{last}行目がない",
                )
            )
            continue
        shown = tuple(
            (n, file_lines[n - 1])
            for n in range(first, min(last, first + MAX_CITED_LINES - 1) + 1)
        )
        detail = (
            ""
            if last - first + 1 <= MAX_CITED_LINES
            else f"先頭{MAX_CITED_LINES}行だけ示す"
        )
        results.append(CitationResult(line, citation, "ok", detail, shown))
    return results


def _group_table_numbers(flags: list[Flag]) -> list[Flag]:
    """同じ表の行の「出典のない数値」は1件にまとめる。結果の表で行の数だけ並ぶのを防ぐ"""
    rows: dict[int, list[Flag]] = {}
    for flag in flags:
        if flag.kind == NUMBER and flag.table >= 0:
            rows.setdefault(flag.table, []).append(flag)
    grouped: list[Flag] = []
    for flag in flags:
        members = (
            rows.get(flag.table) if flag.kind == NUMBER and flag.table >= 0 else None
        )
        if not members or len(members) == 1:
            grouped.append(flag)
            continue
        if flag is not members[0]:
            continue
        where = f"（{flag.section}）" if flag.priority == 1 else ""
        grouped.append(
            Flag(
                NUMBER,
                min(member.priority for member in members),
                flag.line,
                flag.text,
                f"表の{len(members)}行（L{flag.line}-L{members[-1].line}）の数値に出典がない{where}",
                "表の値をどのコマンドか原典から取ったかを確かめ、数行を突き合わせる",
                flag.section,
                flag.table,
            )
        )
    return grouped


def check_text(
    text: str, repo: str | None = None, fetch: Fetcher | None = None
) -> Report:
    doc = parse(text)
    flags: list[Flag] = []
    for claim in doc.claims:
        flags.extend(check_claim(claim, doc))
    flags = _group_table_numbers(flags)
    citations = verify_citations(doc.citations, repo, fetch)
    for result in citations:
        if result.status == "error":
            flags.append(
                Flag(
                    CITATION,
                    1,
                    result.line,
                    result.citation,
                    result.detail,
                    "引用元のファイルと行を開き、主張の根拠になっているかを確かめる",
                )
            )
    flags.sort(key=lambda flag: (flag.priority, flag.line, KINDS.index(flag.kind)))
    return Report(len(doc.claims), flags, citations, repo)


PRIORITY_TITLES = {
    1: "優先度1（不在の主張 / 結論の数値 / 引用の誤り）",
    2: "優先度2（証拠のない完了と保存）",
    3: "優先度3（結論の外の数値）",
}


def summary_line(report: Report) -> str:
    counts = {kind: 0 for kind in KINDS}
    for flag in report.flags:
        counts[flag.kind] += 1
    parts = " / ".join(f"{KIND_LABELS[kind]}{counts[kind]}" for kind in KINDS)
    return f"確かめる主張{len(report.flags)}件（{parts}）、読んだ主張{report.claims}件"


def format_report(report: Report, name: str = "", for_hook: bool = False) -> str:
    out: list[str] = []
    title = f"claim-check: {name}" if name else "claim-check"
    out.append(title)
    out.append(summary_line(report))
    if not report.flags:
        out.append(
            "拾った主張はない。この検査は範囲 / 出典 / 証拠の書き忘れだけを見る。主張が正しいことは示さない"
        )
    for priority in (1, 2, 3):
        items = [flag for flag in report.flags if flag.priority == priority]
        if not items:
            continue
        out.append("")
        out.append(f"## {PRIORITY_TITLES[priority]}")
        for flag in items:
            out.append(f"- [ ] L{flag.line} {KIND_LABELS[flag.kind]}: {flag.reason}")
            out.append(f"  「{flag.text}」")
            if not for_hook:
                out.append(f"  → {flag.hint}")
    shown = [c for c in report.citations if c.status == "ok"]
    unchecked = [c for c in report.citations if c.status == "unchecked"]
    unavailable = [c for c in report.citations if c.status == "unavailable"]
    if shown and not for_hook:
        out.append("")
        out.append(f"## 引用の中身（{report.repo} で照合した）")
        for result in shown:
            note = f"（{result.detail}）" if result.detail else ""
            out.append(f"- L{result.line} {result.citation}{note}")
            for number, text in result.lines:
                out.append(f"    {number:>5} | {text}")
    if unchecked:
        out.append("")
        out.append(
            f"引用{len(unchecked)}件は形だけを確かめた。--repo OWNER/NAME を付けると中身を照合する"
        )
    if unavailable:
        out.append("")
        out.append(f"引用{len(unavailable)}件は照合できなかった")
        for result in unavailable:
            out.append(f"- L{result.line} {result.citation}: {result.detail}")
    return "\n".join(out)


_TASK_NOTIFICATION = re.compile(
    r"<task-notification>(.*?)</task-notification>", re.DOTALL
)
_TAG = r"<{0}>(.*?)</{0}>"
_AGENT_MESSAGE = re.compile(
    r"<agent-message from=\"([^\"]*)\">\n(.*?)^</agent-message>",
    re.DOTALL | re.MULTILINE,
)


def _tag(name: str, text: str) -> str | None:
    match = re.search(_TAG.format(name), text, re.DOTALL)
    return match.group(1) if match else None


def reports_from_prompt(prompt: str) -> list[tuple[str, str]]:
    """UserPromptSubmit の prompt から、バックグラウンドのサブエージェントの報告を取り出す"""
    found: list[tuple[str, str]] = []
    for match in _AGENT_MESSAGE.finditer(prompt):
        lines = match.group(2).split("\n")
        frame = next(
            (n for n, line in enumerate(lines) if "[Subagent hand-back]" in line), -1
        )
        if frame < 0:
            continue
        start = next(
            (n for n in range(frame, len(lines)) if "The report follows:" in lines[n]),
            frame,
        )
        # 報告の行は、枠の偽装を防ぐために2文字下げて渡される
        body = [
            line[2:] for line in lines[start + 1 :] if line.startswith("  ") or not line
        ]
        found.append((f"サブエージェント {match.group(1)} の報告", "\n".join(body)))
    for match in _TASK_NOTIFICATION.finditer(prompt):
        block = match.group(1)
        result = _tag("result", block)
        if result is None or (_tag("status", block) or "").strip() != "completed":
            continue
        if "SubagentHandback" in result[:300]:
            continue
        summary = (_tag("summary", block) or "サブエージェントの報告").strip()
        found.append((summary, result))
    return found


def reports_from_payload(payload: dict) -> tuple[str, list[tuple[str, str]]]:
    event = payload.get("hook_event_name", "")
    if event == "PostToolUse" and payload.get("tool_name") in ("Agent", "Task"):
        response = payload.get("tool_response")
        if isinstance(response, str):
            return event, [("サブエージェントの報告", response)]
        if (
            not isinstance(response, dict)
            or response.get("status", "completed") != "completed"
        ):
            return event, []
        content = response.get("content")
        if isinstance(content, str):
            return event, [("サブエージェントの報告", content)]
        if isinstance(content, list):
            texts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            text = "\n".join(t for t in texts if isinstance(t, str))
            return event, [("サブエージェントの報告", text)] if text.strip() else []
        return event, []
    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        return event, reports_from_prompt(prompt) if isinstance(prompt, str) else []
    return event, []


def hook_context(reports: list[tuple[str, Report]]) -> str:
    lines = [
        "claim-check: サブエージェントの報告の次の主張は、要約を使う前に原典かコマンドの出力で確かめる",
        "この検査は書き方だけを見る。印のない主張が正しいとは限らない",
    ]
    for name, report in reports:
        lines.append("")
        lines.append(format_report(report, name, for_hook=True))
    text = "\n".join(lines)
    if len(text) > HOOK_CONTEXT_LIMIT:
        text = (
            text[: HOOK_CONTEXT_LIMIT - 40] + "\n…（長いので切った。CLI で全体を見る）"
        )
    return text


def run_hook(stdin_text: str) -> str:
    """hook の JSON を受け、出す JSON の文字列を返す。出すものがなければ空文字"""
    try:
        payload = json.loads(stdin_text)
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    event, reports = reports_from_payload(payload)
    checked = [(name, check_text(text)) for name, text in reports]
    flagged = [(name, report) for name, report in checked if report.flagged()]
    if not flagged:
        return ""
    output = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": hook_context(flagged),
        }
    }
    return json.dumps(output, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("files", nargs="*", help="報告の Markdown。なければ標準入力")
    parser.add_argument(
        "--repo",
        help="path@sha:line の引用を照合する GitHub のリポジトリ（OWNER/NAME）",
    )
    parser.add_argument(
        "--strict", action="store_true", help="拾った主張があれば終了コード1"
    )
    parser.add_argument(
        "--hook", action="store_true", help="Claude Code の hook として動く"
    )
    args = parser.parse_args(argv)
    if args.hook:
        try:
            output = run_hook(sys.stdin.read())
        # hook の不具合でセッションを止めないよう、失敗は黙って通す
        except Exception:  # noqa: BLE001
            return 0
        if output:
            print(output)
        return 0
    if args.repo and not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        parser.error("--repo は OWNER/NAME の形で渡す")
    sources: list[tuple[str, str]] = []
    try:
        if args.files:
            for path in args.files:
                with open(path, encoding="utf-8") as handle:
                    sources.append((path, handle.read()))
        else:
            sources.append(("標準入力", sys.stdin.read()))
    except (OSError, UnicodeDecodeError) as error:
        print(f"claim-check: 入力を読めない: {error}", file=sys.stderr)
        return 2
    any_flag = False
    for index, (name, text) in enumerate(sources):
        report = check_text(text, args.repo)
        any_flag = any_flag or report.flagged()
        if index:
            print()
        print(format_report(report, name))
    return 1 if args.strict and any_flag else 0


if __name__ == "__main__":
    sys.exit(main())
