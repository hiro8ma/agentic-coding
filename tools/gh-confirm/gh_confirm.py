#!/usr/bin/env python3
"""シェルのコマンドから、利用者の確認が要る GitHub の操作（レビュー依頼とマージ）を見つける。

Usage:
    python3 gh_confirm.py          # Claude Code の PreToolUse(Bash) の hook。見つけたら ask を返す
    python3 gh_confirm.py --codex  # Codex の PreToolUse(Bash) の hook。見つけたら deny を返す

標準入力の hook の JSON から tool_input.command を読む。
見つからないとき、JSON が読めないとき、解析に失敗したときは、何も出さずに終了コード0で通す。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    action: str
    target: str
    reviewers: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def describe(self) -> str:
        if self.action == "review":
            if self.reviewers:
                return f"レビュー依頼: {self.target} に {', '.join(self.reviewers)}"
            return f"レビュー依頼: {self.target}（依頼先は読めない）"
        text = f"マージ: {self.target}"
        if self.notes:
            text += "（" + " / ".join(self.notes) + "）"
        return text


AUTO_NOTE = "--auto 付き。必要な条件が揃った時点で、確認なしにマージされる"
ADMIN_NOTE = "--admin 付き。ブランチの保護の条件を満たさなくてもマージする"


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
            word.append("`...`")
        elif s.startswith("$(", self.i):
            self.i += 2
            self.parse(")")
            word.append("$(...)")
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


def _unwrap(words: list[str]) -> tuple[list[str], bool]:
    via_xargs = False
    i = 0
    while i < len(words):
        if _ASSIGNMENT.match(words[i]) or words[i] in _KEYWORDS:
            i += 1
            continue
        name = words[i].rsplit("/", 1)[-1]
        if name not in _WRAPPERS:
            break
        value_options, positionals = _WRAPPERS[name]
        via_xargs = via_xargs or name == "xargs"
        i += 1
        while i < len(words) and words[i].startswith("-") and words[i] != "-":
            option = words[i]
            i += 1
            if option == "--":
                break
            if option in value_options:
                i += 1
        i += positionals
    return words[i:], via_xargs


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


_PR_EDIT = _flags(
    "add-assignee add-label add-project add-reviewer base body body-file milestone"
    " remove-assignee remove-label remove-project remove-reviewer title repo",
    "B=base b=body F=body-file m=milestone t=title R=repo",
)
_PR_CREATE = _flags(
    "assignee base body body-file head label milestone project recover reviewer"
    " template title repo",
    "a=assignee B=base b=body F=body-file H=head l=label m=milestone p=project"
    " r=reviewer T=template t=title R=repo",
)
_PR_MERGE = _flags(
    "author-email body body-file match-head-commit subject repo",
    "A=author-email b=body F=body-file t=subject R=repo",
)
_API = _flags(
    "cache field header hostname input jq method preview raw-field=field template",
    "F=field H=header q=jq X=method p=preview f=field t=template",
)


def _parse_flags(
    args: list[str], spec: _FlagSpec
) -> tuple[list[str], dict[str, list[str]], set[str]]:
    """gh（cobra / pflag）の書き方で、位置引数 / 値を取るフラグ / 値を取らないフラグに分ける"""
    positionals: list[str] = []
    values: dict[str, list[str]] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            if name not in spec.values:
                flags.add(name)
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
                flags.add(letter)
        else:
            positionals.append(arg)
    return positionals, values, flags


def _split_logins(values: list[str]) -> tuple[str, ...]:
    return tuple(
        login.strip() for value in values for login in value.split(",") if login.strip()
    )


def _next_word(args: list[str]) -> tuple[str | None, list[str]]:
    """前に置いたフラグを飛ばして最初の語を取る。飛ばしたフラグは残りの引数に戻す"""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-R", "--repo") else 1
    if i >= len(args):
        return None, []
    return args[i], args[:i] + args[i + 1 :]


def _pr_label(
    positionals: list[str], values: dict[str, list[str]], via_xargs: bool
) -> str:
    if via_xargs:
        return "xargs で渡す PR"
    if not positionals:
        return "現在のブランチの PR"
    ref = positionals[0]
    url = re.fullmatch(r"https?://[^/]+/([^/]+/[^/]+)/pull/(\d+)\S*", ref)
    if url:
        return f"{url[1]}#{url[2]}"
    repo = values["repo"][-1] if "repo" in values else ""
    if ref.isdigit():
        return f"{repo}#{ref}"
    return f"{repo + ' の' if repo else ''}ブランチ {ref} の PR"


def _gh(args: list[str], via_xargs: bool) -> Finding | None:
    group, rest = _next_word(args)
    if group == "api":
        return _gh_api(rest)
    if group != "pr":
        return None
    sub, rest = _next_word(rest)
    if sub == "merge":
        positionals, values, flags = _parse_flags(rest, _PR_MERGE)
        notes = tuple(
            note
            for flag, note in (("auto", AUTO_NOTE), ("admin", ADMIN_NOTE))
            if flag in flags
        )
        return Finding("merge", _pr_label(positionals, values, via_xargs), notes=notes)
    if sub == "edit":
        positionals, values, _ = _parse_flags(rest, _PR_EDIT)
        if "add-reviewer" not in values:
            return None
        target = _pr_label(positionals, values, via_xargs)
        return Finding("review", target, _split_logins(values["add-reviewer"]))
    if sub in ("create", "new"):
        _, values, _ = _parse_flags(rest, _PR_CREATE)
        if "reviewer" not in values:
            return None
        return Finding("review", "新しく作る PR", _split_logins(values["reviewer"]))
    return None


def _gh_api(args: list[str]) -> Finding | None:
    positionals, values, _ = _parse_flags(args, _API)
    if not positionals:
        return None
    endpoint = positionals[0]
    if endpoint == "graphql":
        text = " ".join(args)
        if "requestReviews" in text:
            return Finding("review", "GraphQL の requestReviews で指定する PR")
        if "enablePullRequestAutoMerge" in text:
            return Finding(
                "merge",
                "GraphQL の enablePullRequestAutoMerge で指定する PR",
                notes=(AUTO_NOTE,),
            )
        if "mergePullRequest" in text:
            return Finding("merge", "GraphQL の mergePullRequest で指定する PR")
        return None
    if "method" in values:
        method = values["method"][-1].upper()
    elif "field" in values or "input" in values:
        method = "POST"
    else:
        method = "GET"
    repo = re.search(r"repos/([^/{}]+/[^/{}]+)/pulls/", endpoint)
    reviewers = re.search(r"(?:^|/)pulls/(\d+)/requested_reviewers/?$", endpoint)
    if reviewers and method == "POST":
        logins = []
        for field in values.get("field", []):
            key, _, value = field.partition("=")
            if key == "reviewers[]":
                logins.append(value)
            elif key == "team_reviewers[]":
                logins.append(f"team:{value}")
        target = f"{repo[1] if repo else ''}#{reviewers[1]}"
        return Finding("review", target, reviewers=tuple(logins))
    merge = re.search(r"(?:^|/)pulls/(\d+)/merge/?$", endpoint)
    if merge and method == "PUT":
        return Finding("merge", f"{repo[1] if repo else ''}#{merge[1]}")
    return None


def _analyze(words: list[str], stdin: list[str]) -> list[Finding]:
    words, via_xargs = _unwrap(words)
    if not words:
        return []
    name = words[0].rsplit("/", 1)[-1]
    if name in _SHELLS:
        mode, script = _shell_script(words[1:])
        if mode == "c":
            return scan(script)
        if mode == "stdin":
            return [finding for text in stdin for finding in scan(text)]
        return []
    if name == "eval":
        return scan(" ".join(words[1:]))
    if name == "gh":
        finding = _gh(words[1:], via_xargs)
        return [finding] if finding else []
    return []


def scan(command: str) -> list[Finding]:
    """コマンドの文字列のうち、実際に実行される gh の呼び出しから、確認が要る操作を集める"""
    parser = _Parser(command)
    parser.parse()
    found: list[Finding] = []
    for cmd in parser.commands:
        for finding in _analyze(cmd.words, cmd.stdin):
            if finding not in found:
                found.append(finding)
    return found


def build_reason(findings: list[Finding], codex: bool) -> str:
    lines = ["利用者の確認が要る GitHub の操作を含む"]
    lines += [f"- {finding.describe()}" for finding in findings]
    if codex:
        lines.append(
            "Codex の hook は確認の画面を出せないので止めた。"
            "利用者に上の対象を示して承認を得てから、利用者が自分で実行する"
        )
    else:
        lines.append("上の対象が意図どおりかを確かめてから承認する")
    return "\n".join(lines)


def hook_output(findings: list[Finding], codex: bool) -> dict:
    reason = build_reason(findings, codex)
    output: dict = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny" if codex else "ask",
            "permissionDecisionReason": reason,
        }
    }
    if codex:
        output["systemMessage"] = reason
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--codex",
        action="store_true",
        help="Codex 向けに deny を返す（Codex の PreToolUse は ask を扱わない）",
    )
    args = parser.parse_args(argv)
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
    try:
        findings = scan(command)
    # ガードの不具合で Bash の全部を止めないよう、解析の失敗は通す
    except Exception:  # noqa: BLE001
        return 0
    if findings:
        print(json.dumps(hook_output(findings, args.codex), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
