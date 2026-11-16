#!/usr/bin/env python3
"""用語集の表に沿って、使わない語を出し先（コミット / PR / 文書）ごとに見つける。

Usage:
    python3 term_check.py lint --glossary glossary.md --target docs notes/ README.md
    python3 term_check.py lint --glossary glossary.md --target commit --json msg.txt
    git log -1 --format=%B | python3 term_check.py lint --glossary g.md --target commit -
    python3 term_check.py glossary --glossary glossary.md
    python3 term_check.py hook --glossary glossary.md          # Claude Code の PreToolUse(Bash)
    python3 term_check.py hook --glossary glossary.md --codex  # Codex の PreToolUse(Bash)

用語集は「使う語 / 使わない語 / 除く語 / 対象 / 使う場面 / 期待する判断」の列を持つ Markdown の表。
lint は、出し先に当てはまる行の使わない語を、フェンスとインラインコードと URL の外から探す。
glossary は、各行に使う場面と期待する判断が書いてあるかを確かめる。
hook は、git commit のメッセージと gh pr create / edit のタイトルと本文を取り出して lint と同じ規則で調べ、
当たれば deny を返す。用語集やコマンドを読めないときは、何も出さずに終了コード0で通す。
終了コードは、lint は当たりが無ければ0、あれば1（--report-only なら0）、
glossary は欠けが無ければ0、あれば1。どちらも入力か用語集を読めなければ2。hook は常に0。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

COMMIT = "commit"
PR = "pr"
DOCS = "docs"
ALL = "all"
TEXT_TARGETS = (COMMIT, PR, DOCS)
RULE_TARGETS = (*TEXT_TARGETS, ALL)

USE = "使う語"
AVOID = "使わない語"
EXCEPT = "除く語"
TARGETS = "対象"
SCENE = "使う場面"
JUDGMENT = "期待する判断"
COLUMNS = (USE, AVOID, EXCEPT, TARGETS, SCENE, JUDGMENT)
SEPARATOR = " / "
CONTEXT = 20

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_TABLE_ROW = re.compile(r"^\s*\|")
_DELIMITER_CELL = re.compile(r"^:?-+:?$")
_PIPE = re.compile(r"(?<!\\)\|")


class GlossaryError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    line: int
    use: tuple[str, ...]
    avoid: tuple[str, ...]
    excepts: tuple[str, ...]
    targets: tuple[str, ...]
    scene: str
    judgment: str

    def applies(self, target: str) -> bool:
        return target in self.targets or ALL in self.targets

    def missing(self) -> list[str]:
        return [
            name
            for name, value in ((SCENE, self.scene), (JUDGMENT, self.judgment))
            if not value
        ]

    def label(self) -> str:
        parts = []
        if self.use:
            parts.append(f"{USE}「{SEPARATOR.join(self.use)}」")
        if self.avoid:
            parts.append(f"{AVOID}「{SEPARATOR.join(self.avoid)}」")
        return " / ".join(parts)


@dataclass(frozen=True)
class Hit:
    line: int
    column: int
    word: str
    excerpt: str
    rule: Rule


@dataclass(frozen=True)
class Message:
    target: str
    source: str
    text: str


def _fenced(lines: list[str]) -> list[bool]:
    """行ごとに、フェンスのコードブロック（フェンスの行を含む）の中かを返す"""
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            flags.append(True)
            continue
        opening = _FENCE.match(line)
        if opening and not (
            opening.group(1)[0] == "`" and "`" in line[opening.end() :]
        ):
            fence = opening.group(1)
            flags.append(True)
            continue
        flags.append(False)
    return flags


def _cells(line: str) -> list[str]:
    text = line.strip()
    text = text.removeprefix("|")
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _PIPE.split(text)]


def _is_delimiter(line: str) -> bool:
    if not _TABLE_ROW.match(line):
        return False
    return all(_DELIMITER_CELL.match(cell) for cell in _cells(line))


def _terms(cell: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(t.strip() for t in cell.split(SEPARATOR) if t.strip()))


def _rule(line: int, cells: dict[str, str]) -> Rule:
    targets = tuple(t.strip() for t in cells[TARGETS].split("/") if t.strip())
    if not targets:
        raise GlossaryError(f"{line}行目: {TARGETS}が空")
    unknown = [t for t in targets if t not in RULE_TARGETS]
    if unknown:
        raise GlossaryError(
            f"{line}行目: {TARGETS}の「{' / '.join(unknown)}」は"
            f" {' / '.join(RULE_TARGETS)} のどれでもない"
        )
    use = _terms(cells[USE])
    avoid = _terms(cells[AVOID])
    if not use and not avoid:
        raise GlossaryError(f"{line}行目: {USE}も{AVOID}も無い")
    return Rule(
        line, use, avoid, _terms(cells[EXCEPT]), targets, cells[SCENE], cells[JUDGMENT]
    )


def parse_glossary(text: str) -> list[Rule]:
    """「使う語」か「使わない語」を見出しに持つ表の行を、規則として読む。フェンスの中の表は読まない"""
    lines = text.splitlines()
    fenced = _fenced(lines)
    rules: list[Rule] = []
    found = False
    i = 0
    while i < len(lines):
        if fenced[i] or not _TABLE_ROW.match(lines[i]):
            i += 1
            continue
        header = _cells(lines[i])
        if i + 1 >= len(lines) or not _is_delimiter(lines[i + 1]):
            i += 1
            continue
        if USE not in header and AVOID not in header:
            i += 2
            continue
        found = True
        absent = [name for name in COLUMNS if name not in header]
        if absent:
            raise GlossaryError(
                f"{i + 1}行目: 表の見出しに {' / '.join(absent)} が無い"
            )
        index = {name: header.index(name) for name in COLUMNS}
        i += 2
        while i < len(lines) and not fenced[i] and _TABLE_ROW.match(lines[i]):
            cells = _cells(lines[i])
            if len(cells) != len(header):
                raise GlossaryError(
                    f"{i + 1}行目: 列が{len(cells)}個ある（見出しは{len(header)}個）"
                )
            if any(cells):
                rules.append(
                    _rule(i + 1, {name: cells[index[name]] for name in COLUMNS})
                )
            i += 1
    if not found:
        raise GlossaryError(f"「{USE}」か「{AVOID}」の列を持つ表が無い")
    return rules


def load_glossary(path: str) -> list[Rule]:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        raise GlossaryError(f"読めない: {path}: {error}") from error
    return parse_glossary(text)


def _blank(found: re.Match[str]) -> str:
    return " " * len(found.group(0))


def mask(lines: list[str]) -> list[str]:
    """フェンス / インラインコード / URL を同じ長さの空白にする。行の数と字の位置は変えない"""
    return [
        " " * len(line) if inside else _URL.sub(_blank, _CODE_SPAN.sub(_blank, line))
        for line, inside in zip(lines, _fenced(lines))
    ]


def _excepted(line: str, start: int, word: str, compounds: tuple[str, ...]) -> bool:
    """start の位置の word が、その位置で compounds のどれかの一部になっているか"""
    for compound in compounds:
        offset = compound.find(word)
        while offset >= 0:
            if offset <= start and line.startswith(compound, start - offset):
                return True
            offset = compound.find(word, offset + 1)
    return False


def _excerpt(line: str, start: int, end: int) -> str:
    left = max(0, start - CONTEXT)
    right = min(len(line), end + CONTEXT)
    text = line[left:right].strip()
    return ("…" if left else "") + text + ("…" if right < len(line) else "")


def find_hits(text: str, rules: list[Rule], target: str) -> list[Hit]:
    original = text.splitlines()
    masked = mask(original)
    applicable = [rule for rule in rules if rule.applies(target)]
    hits: list[Hit] = []
    for number, line in enumerate(masked, 1):
        for rule in applicable:
            # 使う語が使わない語を含む（サーバー と サーバ）ときに、使う語を当たりにしない
            compounds = rule.excepts + rule.use
            taken: list[tuple[int, int]] = []
            for word in sorted(rule.avoid, key=len, reverse=True):
                start = line.find(word)
                while start >= 0:
                    end = start + len(word)
                    inside = any(s <= start and end <= e for s, e in taken)
                    if not inside and not _excepted(line, start, word, compounds):
                        taken.append((start, end))
                        hits.append(
                            Hit(
                                number,
                                start + 1,
                                word,
                                _excerpt(original[number - 1], start, end),
                                rule,
                            )
                        )
                    start = line.find(word, start + 1)
    return sorted(hits, key=lambda hit: (hit.line, hit.column, hit.rule.line))


# tools/gh-confirm の bash の解析を写したもの。$( ) の出力を語に入れるところだけが違う


class _Command:
    def __init__(self) -> None:
        self.words: list[str] = []
        self.stdin: list[str] = []


class _Parser:
    """bash の文法のうち、コマンドの区切り / 引用符 / 置換 / ヒアドキュメント / リダイレクトだけを読む"""

    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.commands: list[_Command] = []
        self.heredocs: list[tuple[str, bool, bool, _Command]] = []

    def parse(self, closer: str | None = None) -> None:
        s = self.s
        cmd = _Command()
        word: list[str] | None = None
        word_start = 0
        pending: str | None = None

        def finish_word() -> None:
            nonlocal word, pending
            if word is None:
                return
            text = "".join(word)
            word = None
            if pending is None:
                cmd.words.append(text)
            elif pending == "herestring":
                cmd.stdin.append(text)
            elif pending.startswith("heredoc"):
                quoted = any(q in s[word_start : self.i] for q in "'\"\\")
                self.heredocs.append((text, pending == "heredoc-", quoted, cmd))
            pending = None

        def finish_command() -> None:
            nonlocal cmd, pending
            finish_word()
            pending = None
            if cmd.words or cmd.stdin:
                self.commands.append(cmd)
            cmd = _Command()

        while self.i < len(s):
            c = s[self.i]
            if c in " \t":
                finish_word()
                self.i += 1
            elif c == "\n":
                finish_command()
                self.i += 1
                self._read_heredocs()
            elif c == "#" and word is None:
                end = s.find("\n", self.i)
                self.i = len(s) if end < 0 else end
            elif c in "<>" or s.startswith("&>", self.i):
                if word is not None and "".join(word).isdigit():
                    word = None
                finish_word()
                for op, kind in (
                    ("<<<", "herestring"),
                    ("<<-", "heredoc-"),
                    ("<<", "heredoc"),
                    ("&>>", "target"),
                    ("&>", "target"),
                    ("<>", "target"),
                    ("<&", "target"),
                    (">>", "target"),
                    (">|", "target"),
                    (">&", "target"),
                    ("<", "target"),
                    (">", "target"),
                ):
                    if s.startswith(op, self.i):
                        self.i += len(op)
                        pending = kind
                        break
            elif c in ";&|":
                finish_command()
                self.i += 1
            elif c == "(":
                finish_command()
                self.i += 1
                self.parse(")")
            elif c == ")":
                finish_command()
                self.i += 1
                if closer == ")":
                    return
            else:
                if word is None:
                    if c == "\\" and s.startswith("\\\n", self.i):
                        self.i += 2
                        continue
                    word = []
                    word_start = self.i
                self._read_word_part(word)
        finish_command()

    def _read_word_part(self, word: list[str]) -> None:
        s = self.s
        c = s[self.i]
        if c == "\\":
            word.append(s[self.i + 1 : self.i + 2])
            self.i += 2
        elif c == "'":
            end = s.find("'", self.i + 1)
            end = len(s) if end < 0 else end
            word.append(s[self.i + 1 : end])
            self.i = end + 1
        elif s.startswith("$'", self.i):
            self.i += 2
            while self.i < len(s) and s[self.i] != "'":
                if s[self.i] == "\\":
                    self.i += 1
                word.append(s[self.i : self.i + 1])
                self.i += 1
            self.i += 1
        elif c == '"':
            self.i += 1
            self._read_double_quoted(word)
        elif c in "`$":
            self._read_expansion(word)
        else:
            word.append(c)
            self.i += 1

    def _read_double_quoted(self, word: list[str]) -> None:
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\" and s[self.i + 1 : self.i + 2] in ('"', "\\", "$", "`"):
                word.append(s[self.i + 1])
                self.i += 2
            elif c in "`$":
                self._read_expansion(word)
            else:
                word.append(c)
                self.i += 1

    def _read_expansion(self, word: list[str]) -> None:
        s = self.s
        if s[self.i] == "`":
            end = self.i + 1
            inner: list[str] = []
            while end < len(s) and s[end] != "`":
                if s[end] == "\\" and s[end + 1 : end + 2] in ("`", "\\", "$"):
                    end += 1
                inner.append(s[end : end + 1])
                end += 1
            self.i = end + 1
            nested = _Parser("".join(inner))
            nested.parse()
            self.commands.extend(nested.commands)
            word.append(_output(nested.commands))
        elif s.startswith("$(", self.i):
            self.i += 2
            before = len(self.commands)
            self.parse(")")
            word.append(_output(self.commands[before:]))
        else:
            word.append("$")
            self.i += 1

    def _read_heredocs(self) -> None:
        s = self.s
        while self.heredocs:
            delimiter, strip_tabs, quoted, cmd = self.heredocs.pop(0)
            lines = []
            while self.i < len(s):
                end = s.find("\n", self.i)
                end = len(s) if end < 0 else end
                line = s[self.i : end]
                self.i = end + 1
                if strip_tabs:
                    line = line.lstrip("\t")
                if line == delimiter:
                    break
                lines.append(line)
            body = "\n".join(lines)
            cmd.stdin.append(body)
            if not quoted:
                self.commands.extend(_substitutions(body))


def _substitutions(text: str) -> list[_Command]:
    """引用符で囲まない区切りのヒアドキュメントでは、本文の $( ) と `...` が実行される"""
    parser = _Parser(text)
    while parser.i < len(text):
        if text[parser.i] == "\\":
            parser.i += 2
        elif text[parser.i] in "`$":
            parser._read_expansion([])
        else:
            parser.i += 1
    return parser.commands


def _output(commands: list[_Command]) -> str:
    """$( ) の中が cat のヒアドキュメント / ヒアストリングか echo なら、その出力を返す。読めなければ空白"""
    for cmd in commands:
        words = _unwrap(cmd.words)
        if (
            words
            and _name(words[0]) == "cat"
            and words[1:] in ([], ["-"])
            and cmd.stdin
        ):
            return "\n".join(cmd.stdin)
    if commands:
        words = _unwrap(commands[-1].words)
        if words and _name(words[0]) == "echo":
            args = words[1:]
            while args and args[0] in ("-n", "-e", "-E"):
                args = args[1:]
            return " ".join(args)
    return " "


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\+?=")
_KEYWORDS = {"!", "{", "if", "then", "elif", "else", "while", "until", "do"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# 前に付けても後ろのコマンドをそのまま実行するもの。値を取るオプションと、オプションの後の位置引数の数
_WRAPPERS: dict[str, tuple[frozenset[str], int]] = {
    "env": (frozenset({"-u", "-C", "--unset", "--chdir"}), 0),
    "command": (frozenset(), 0),
    "exec": (frozenset({"-a"}), 0),
    "nohup": (frozenset(), 0),
    "time": (frozenset({"-o", "-f"}), 0),
    "nice": (frozenset({"-n"}), 0),
    "sudo": (
        frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-T", "-U"}),
        0,
    ),
    "timeout": (frozenset({"-s", "-k", "--signal", "--kill-after"}), 1),
    "xargs": (frozenset({"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"}), 0),
}


def _name(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _unwrap(words: list[str]) -> list[str]:
    i = 0
    while i < len(words):
        if _ASSIGNMENT.match(words[i]) or words[i] in _KEYWORDS:
            i += 1
            continue
        name = _name(words[i])
        if name not in _WRAPPERS:
            break
        value_options, positionals = _WRAPPERS[name]
        i += 1
        while i < len(words) and words[i].startswith("-") and words[i] != "-":
            option = words[i]
            i += 1
            if option == "--":
                break
            if option in value_options:
                i += 1
        i += positionals
    return words[i:]


def _shell_script(args: list[str]) -> tuple[str, str]:
    """シェルの引数から、-c の文字列（"c"）/ 標準入力を読む（"stdin"）/ ファイルを読む（"file"）を見分ける"""
    has_c = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            break
        if arg in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
        elif arg.startswith("--"):
            i += 1
        elif len(arg) > 1 and arg[0] in "-+":
            has_c = has_c or (arg[0] == "-" and "c" in arg[1:])
            i += 1
        else:
            break
    rest = args[i:]
    if has_c:
        return "c", rest[0] if rest else ""
    return ("file", "") if rest else ("stdin", "")


@dataclass(frozen=True)
class _FlagSpec:
    values: dict[str, str]
    short_values: dict[str, str]


def _flags(values: str, short_values: str) -> _FlagSpec:
    """値を取るフラグを "名前" か "名前=まとめる先" で並べる"""

    def pairs(text: str) -> dict[str, str]:
        items = (item.partition("=") for item in text.split())
        return {name: key or name for name, _, key in items}

    return _FlagSpec(pairs(values), pairs(short_values))


# git commit の -t は --template で、gh pr の -t（--title）とは別物
_COMMIT = _flags(
    "message file reuse-message reedit-message fixup squash author date template"
    " cleanup trailer pathspec-from-file",
    "m=message F=file C=reuse-message c=reedit-message t=template",
)
_PR_CREATE = _flags(
    "assignee base body body-file head label milestone project recover reviewer"
    " template title repo",
    "a=assignee B=base b=body F=body-file H=head l=label m=milestone p=project"
    " r=reviewer T=template t=title R=repo",
)
_PR_EDIT = _flags(
    "add-assignee add-label add-project add-reviewer base body body-file milestone"
    " remove-assignee remove-label remove-project remove-reviewer title repo",
    "B=base b=body F=body-file m=milestone t=title R=repo",
)
_GIT_GLOBAL_VALUES = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
)


def _parse_flags(args: list[str], spec: _FlagSpec) -> dict[str, list[str]]:
    """値を取るフラグの値を集める。短いフラグはまとめて書いた形（-am msg）も読む"""
    values: dict[str, list[str]] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if name not in spec.values:
                continue
            if not eq:
                value = args[i] if i < len(args) else ""
                i += 1
            values.setdefault(spec.values[name], []).append(value)
        elif arg.startswith("-") and len(arg) > 1:
            for j, letter in enumerate(arg[1:], start=1):
                if letter in spec.short_values:
                    value = arg[j + 1 :]
                    if value.startswith("="):
                        value = value[1:]
                    elif not value:
                        value = args[i] if i < len(args) else ""
                        i += 1
                    values.setdefault(spec.short_values[letter], []).append(value)
                    break
    return values


def _next_word(args: list[str]) -> tuple[str | None, list[str]]:
    """前に置いたフラグを飛ばして最初の語を取る。飛ばしたフラグは残りの引数に戻す"""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-R", "--repo") else 1
    if i >= len(args):
        return None, []
    return args[i], args[:i] + args[i + 1 :]


def _chdir(base: Path, args: list[str]) -> Path:
    rest = [arg for arg in args if arg not in ("-L", "-P", "-e", "-@", "--")]
    if not rest:
        return Path.home()
    if rest[0] == "-":
        return base
    return base / os.path.expanduser(rest[0])


def _read_text(value: str, stdin: list[str], base: Path) -> tuple[str | None, str]:
    """-F / --body-file の値から文を読む。- は標準入力（ヒアドキュメント / ヒアストリング）"""
    if value == "-":
        return ("\n".join(stdin), "標準入力") if stdin else (None, "")
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = base / path
    try:
        return path.read_text(encoding="utf-8-sig"), f"ファイル {value}"
    except (OSError, UnicodeDecodeError):
        return None, ""


def _git_messages(args: list[str], stdin: list[str], base: Path) -> list[Message]:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        option = args[i]
        i += 1
        if option in _GIT_GLOBAL_VALUES and i < len(args):
            if option == "-C":
                base = base / os.path.expanduser(args[i])
            i += 1
    if i >= len(args) or args[i] != "commit":
        return []
    values = _parse_flags(args[i + 1 :], _COMMIT)
    found: list[Message] = []
    if "message" in values:
        text = "\n\n".join(values["message"])
        found.append(Message(COMMIT, "コミットメッセージ", text))
    for value in values.get("file", []):
        text, label = _read_text(value, stdin, base)
        if text is not None:
            found.append(Message(COMMIT, f"コミットメッセージ（{label}）", text))
    return found


def _gh_messages(args: list[str], stdin: list[str], base: Path) -> list[Message]:
    group, rest = _next_word(args)
    if group != "pr":
        return []
    sub, rest = _next_word(rest)
    spec = {"create": _PR_CREATE, "new": _PR_CREATE, "edit": _PR_EDIT}.get(sub or "")
    if spec is None:
        return []
    values = _parse_flags(rest, spec)
    found = [Message(PR, "PR のタイトル", value) for value in values.get("title", [])]
    found += [Message(PR, "PR の本文", value) for value in values.get("body", [])]
    for value in values.get("body-file", []):
        text, label = _read_text(value, stdin, base)
        if text is not None:
            found.append(Message(PR, f"PR の本文（{label}）", text))
    return found


def extract_messages(command: str, base: Path) -> list[Message]:
    """コマンドの文字列から、実際に実行される git commit と gh pr create / edit の文を集める"""
    parser = _Parser(command)
    parser.parse()
    found: list[Message] = []
    for cmd in parser.commands:
        words = _unwrap(cmd.words)
        if not words:
            continue
        name = _name(words[0])
        if name == "cd":
            base = _chdir(base, words[1:])
        elif name in _SHELLS:
            mode, script = _shell_script(words[1:])
            if mode == "c":
                found += extract_messages(script, base)
            elif mode == "stdin":
                for text in cmd.stdin:
                    found += extract_messages(text, base)
        elif name == "eval":
            found += extract_messages(" ".join(words[1:]), base)
        elif name == "git":
            found += _git_messages(words[1:], cmd.stdin, base)
        elif name == "gh":
            found += _gh_messages(words[1:], cmd.stdin, base)
    return found


def describe(hit: Hit, where: str) -> list[str]:
    use = f"{USE}「{SEPARATOR.join(hit.rule.use)}」" if hit.rule.use else f"{USE}なし"
    lines = [
        f"- {where}「{hit.word}」→ {use}（用語集の{hit.rule.line}行目）",
        f"  - 行「{hit.excerpt}」",
    ]
    if hit.rule.scene:
        lines.append(f"  - {SCENE} {hit.rule.scene}")
    if hit.rule.judgment:
        lines.append(f"  - {JUDGMENT} {hit.rule.judgment}")
    return lines


def rule_json(rule: Rule) -> dict:
    return {
        "line": rule.line,
        "use": list(rule.use),
        "avoid": list(rule.avoid),
        "except": list(rule.excepts),
        "targets": list(rule.targets),
        "scene": rule.scene,
        "judgment": rule.judgment,
    }


def lint_json(reports: list[tuple[str, list[Hit]]], glossary: str, target: str) -> dict:
    return {
        "summary": {
            "glossary": glossary,
            "target": target,
            "files": len(reports),
            "hits": sum(len(hits) for _, hits in reports),
        },
        "files": [
            {
                "path": path,
                "hits": [
                    {
                        "line": hit.line,
                        "column": hit.column,
                        "word": hit.word,
                        "excerpt": hit.excerpt,
                        "rule": rule_json(hit.rule),
                    }
                    for hit in hits
                ],
            }
            for path, hits in reports
        ],
    }


def render_lint(reports: list[tuple[str, list[Hit]]], target: str) -> str:
    total = sum(len(hits) for _, hits in reports)
    lines = [
        "# term-check",
        "",
        f"出し先 {target} / 読んだファイル{len(reports)}件 / 当たり{total}件",
    ]
    for path, hits in reports:
        if not hits:
            continue
        lines += ["", f"## {path}", ""]
        for hit in hits:
            lines += describe(hit, f"{hit.line}行目{hit.column}字目")
    return "\n".join(lines) + "\n"


def render_glossary(rules: list[Rule]) -> str:
    incomplete = [rule for rule in rules if rule.missing()]
    lines = [
        "# term-check glossary",
        "",
        (
            f"規則{len(rules)}件 / {SCENE}と{JUDGMENT}がそろう"
            f"{len(rules) - len(incomplete)}件 / 欠け{len(incomplete)}件"
        ),
    ]
    if incomplete:
        lines += ["", "## 欠けた規則", ""]
    for rule in incomplete:
        lines.append(f"- {rule.line}行目 {rule.label()}")
        lines.append("  - 欠け " + " / ".join(rule.missing()))
    return "\n".join(lines) + "\n"


def build_reason(found: list[tuple[Message, Hit]]) -> str:
    lines = ["用語集で使わない語を含む"]
    for message, hit in found:
        lines += describe(hit, f"{message.source}の{hit.line}行目")
    lines.append("用語集の期待する判断に沿って書き直してから、もう一度実行する")
    return "\n".join(lines)


def hook_output(found: list[tuple[Message, Hit]], codex: bool) -> dict:
    reason = build_reason(found)
    output: dict = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if codex:
        output["systemMessage"] = reason
    return output


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
                dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
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


def run_lint(args: argparse.Namespace) -> int:
    errors: list[str] = []
    rules: list[Rule] = []
    try:
        rules = load_glossary(args.glossary)
    except GlossaryError as error:
        errors.append(f"用語集: {error}")
    files, path_errors = expand(args.paths)
    errors += path_errors
    texts: list[tuple[str, str]] = []
    for name, path in files:
        try:
            texts.append((name, read_input(path)))
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"読めない: {name}: {error}")
    if errors:
        for error in errors:
            print(f"term-check: {error}", file=sys.stderr)
        return 2
    reports = [(name, find_hits(text, rules, args.target)) for name, text in texts]
    if args.json:
        output = lint_json(reports, args.glossary, args.target)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_lint(reports, args.target))
    if args.report_only:
        return 0
    return 1 if any(hits for _, hits in reports) else 0


def run_glossary(args: argparse.Namespace) -> int:
    try:
        rules = load_glossary(args.glossary)
    except GlossaryError as error:
        print(f"term-check: 用語集: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(render_glossary(rules))
    return 1 if any(rule.missing() for rule in rules) else 0


def run_hook(args: argparse.Namespace) -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name", "Bash") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, list) and all(isinstance(part, str) for part in command):
        command = shlex.join(command)
    if not isinstance(command, str):
        return 0
    cwd = payload.get("cwd")
    base = Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()
    # hook の不具合で Bash の全部を止めないよう、解析の失敗は通す
    try:
        messages = extract_messages(command, base)
        if not messages:
            return 0
        rules = load_glossary(args.glossary)
        found = [
            (m, hit) for m in messages for hit in find_hits(m.text, rules, m.target)
        ]
    except GlossaryError as error:
        print(
            f"term-check: 用語集を読めないので、確かめずに通す: {error}",
            file=sys.stderr,
        )
        return 0
    except Exception:  # noqa: BLE001
        return 0
    if found:
        print(json.dumps(hook_output(found, args.codex), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    lint = commands.add_parser("lint", help="ファイルの文から使わない語を探す")
    lint.add_argument("--glossary", required=True, help="用語集の Markdown のファイル")
    lint.add_argument(
        "--target", required=True, choices=TEXT_TARGETS, help="文の出し先"
    )
    lint.add_argument("--json", action="store_true", help="JSON で出す")
    lint.add_argument(
        "--report-only", action="store_true", help="当たりがあっても終了コード0を返す"
    )
    lint.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="読むファイルかディレクトリ（- で標準入力）",
    )
    lint.set_defaults(func=run_lint)

    glossary = commands.add_parser(
        "glossary", help="用語集の各行に使う場面と期待する判断があるかを確かめる"
    )
    glossary.add_argument(
        "--glossary", required=True, help="用語集の Markdown のファイル"
    )
    glossary.set_defaults(func=run_glossary)

    hook = commands.add_parser("hook", help="PreToolUse(Bash) の hook として動く")
    hook.add_argument("--glossary", required=True, help="用語集の Markdown のファイル")
    hook.add_argument(
        "--codex", action="store_true", help="理由の文を systemMessage でも返す"
    )
    hook.set_defaults(func=run_hook)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as error:
        # PreToolUse の hook が2で終わると Bash の呼び出しを止めるので、hook の引数の誤りは通す
        if argv[:1] == ["hook"] and error.code:
            return 0
        raise
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
