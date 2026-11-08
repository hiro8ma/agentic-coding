#!/usr/bin/env python3
"""PreToolUse hook: -o の無い go build が、git で追跡されていないファイルを上書きするのを止める。

go build は、パッケージが1つの main のとき、カレントディレクトリにパッケージの名前のファイルを書く。
書き出す先に追跡されていないファイルがあれば、exit 2 で止め、そのパスと代わりの書き方を stderr で返す。
追跡されているファイル、無視の対象のファイル、git のリポジトリの外、出力の名前を確かに決められない形は通す。
JSON でない入力、引用符が閉じないコマンド、git が動かない場合も通す。
"""

import json
import os
import re
import shlex
import subprocess
import sys

OPERATOR_CHARS = ";&|()<>\n"
PREFIX_WORDS = {"env", "time", "command"}
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
VALUE_FLAGS = {
    "C",
    "asmflags",
    "buildmode",
    "compiler",
    "covermode",
    "coverpkg",
    "debug-actiongraph",
    "debug-runtime-trace",
    "debug-trace",
    "gccgoflags",
    "gcflags",
    "installsuffix",
    "ldflags",
    "mod",
    "modfile",
    "overlay",
    "p",
    "pgo",
    "pkgdir",
    "tags",
    "toolexec",
}
MODULE_LINE = re.compile(r'^\s*module\s+"?([^"\s]+)"?', re.MULTILINE)
PACKAGE_MAIN = re.compile(r"^package\s+main\b", re.MULTILINE)
# go の isVersionElement と同じ。v2 以上の版の要素は出力の名前に使われない
VERSION_ELEMENT = re.compile(r"v(?:[2-9]|[1-9][0-9]+)")


class Unknown(Exception):
    """カレントディレクトリやコマンドの形を確かに読めない。"""


def segments(command):
    """演算子で区切ったコマンドの単語の列を返す。サブシェルとヒアドキュメントは Unknown にする。"""
    lex = shlex.shlex(
        command.replace("\\\n", ""), posix=True, punctuation_chars=OPERATOR_CHARS
    )
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    result, words = [], []
    skip_target = in_comment = False
    for token in lex:
        operator = bool(token) and all(c in OPERATOR_CHARS for c in token)
        if in_comment:
            if not (operator and "\n" in token):
                continue
            token = token[token.index("\n") :]
            in_comment = False
        if operator:
            if "(" in token or ")" in token or "<<" in token:
                raise Unknown
            if "<" in token or ">" in token:
                if words and words[-1].isdigit():
                    words.pop()
                skip_target = True
                continue
            result.append(words)
            words, skip_target, in_comment = [], False, False
        elif skip_target:
            skip_target = False
        elif token.startswith("#"):
            in_comment = True
        else:
            words.append(token)
    result.append(words)
    return result


def change_dir(base, words):
    args = words[1:]
    while args and args[0].startswith("-") and args[0] != "-":
        if args.pop(0) == "--":
            break
    if len(args) > 1:
        raise Unknown
    target = args[0] if args else "~"
    if target == "-" or "$" in target or "`" in target:
        raise Unknown
    target = os.path.expanduser(target)
    if target.startswith("~"):
        raise Unknown
    return os.path.normpath(os.path.join(base, target))


def is_main_package(directory):
    try:
        names = os.listdir(directory)
    except OSError:
        return False
    for name in names:
        if not name.endswith(".go") or name.endswith("_test.go"):
            continue
        if name.startswith(("_", ".")):
            continue
        try:
            with open(
                os.path.join(directory, name), encoding="utf-8", errors="replace"
            ) as f:
                if PACKAGE_MAIN.search(f.read()):
                    return True
        except OSError:
            continue
    return False


def exec_name(directory):
    """go が出力に付ける名前を返す。確かに決められなければ None。"""
    try:
        with open(os.path.join(directory, "go.mod"), encoding="utf-8") as f:
            match = MODULE_LINE.search(f.read())
    except FileNotFoundError:
        name = os.path.basename(directory)
        return None if not name or VERSION_ELEMENT.fullmatch(name) else name
    except OSError:
        return None
    if not match:
        return None
    elements = match.group(1).rstrip("/").split("/")
    if len(elements) > 1 and VERSION_ELEMENT.fullmatch(elements[-1]):
        return elements[-2]
    return elements[-1] or None


def build_output(base, words):
    """-o の無い go build が書き出すファイルの絶対パスとパッケージの引数を返す。推定できなければ None。"""
    i = 2
    packages = []
    while i < len(words):
        word = words[i]
        if word == "--":
            packages = words[i + 1 :]
            break
        if not word.startswith("-") or word == "-":
            packages = words[i:]
            break
        name, has_value, value = word.lstrip("-").partition("=")
        if name == "o":
            return None
        if name in VALUE_FLAGS and not has_value:
            i += 1
            value = words[i] if i < len(words) else ""
        if name == "C":
            if not value or "$" in value or "`" in value:
                return None
            base = os.path.normpath(os.path.join(base, os.path.expanduser(value)))
        i += 1
    if len(packages) > 1:
        return None
    package = packages[0] if packages else "."
    if "$" in package or "`" in package or "..." in package or package.endswith(".go"):
        return None
    if package not in (".", "..") and not package.startswith(("./", "../", "/")):
        return None
    directory = os.path.normpath(os.path.join(base, package))
    if not is_main_package(directory):
        return None
    name = exec_name(directory)
    if name is None:
        return None
    return os.path.join(base, name), package


def build_outputs(command, cwd):
    outputs = []
    base = cwd
    try:
        for words in segments(command):
            while words and (ASSIGNMENT.match(words[0]) or words[0] in PREFIX_WORDS):
                words = words[1:]
            if not words:
                continue
            if words[0] == "cd":
                base = change_dir(base, words)
            elif words[0] in ("pushd", "popd"):
                raise Unknown
            elif os.path.basename(words[0]) == "go" and words[1:2] == ["build"]:
                output = build_output(base, words)
                if output:
                    outputs.append(output)
    except Unknown:
        pass
    return outputs


def is_untracked_file(path):
    """git のリポジトリの中にあり、追跡も無視もされていない既存のファイルか。"""
    if not os.path.isfile(path):
        return False
    directory, name = os.path.split(path)

    def git(*args):
        return subprocess.run(
            ["git", "-C", directory, *args],
            capture_output=True,
            timeout=15,
            check=False,
        )

    try:
        # どちらも 0 は当てはまる、1 は当てはまらない、それ以外はリポジトリの外か git の失敗
        if git("ls-files", "--error-unmatch", "--", name).returncode != 1:
            return False
        return git("check-ignore", "-q", "--", name).returncode == 1
    except (OSError, subprocess.SubprocessError):
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)

    command = payload.get("tool_input", {}).get("command", "")
    if "go" not in command or "build" not in command:
        sys.exit(0)
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        cwd = os.getcwd()

    try:
        outputs = build_outputs(command, cwd)
    except ValueError:
        sys.exit(0)

    hits = [(path, package) for path, package in outputs if is_untracked_file(path)]
    if hits:
        package = shlex.quote(hits[0][1])
        print(
            "go build が、git で追跡されていない既存のファイルを上書きする。コマンドを止めた。\n"
            + "\n".join(f"  - {path}（go build {pkg} の出力）" for path, pkg in hits)
            + "\n追跡されていないファイルは、上書きすると git で戻せない。\n"
            + f"コンパイルを確かめるだけなら go vet {package} か"
            + f" go build -o /dev/null {package} を使う。\n"
            + f"バイナリが要るなら go build -o <別の場所> {package} で書き出す先を変える。",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
