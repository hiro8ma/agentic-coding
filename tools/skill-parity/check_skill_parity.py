#!/usr/bin/env python3
"""Claude Code と Codex で共有する Skill の呼び出し方針と検出の食い違いを調べる。

Usage:
    python3 check_skill_parity.py [--fix] [--max-description N] [--claude-listing-limit N] [root]

root の .claude/skills / .agents/skills / .codex/skills を走査する。
シンボリックリンクはたどり、実体のパスが同じ Skill は1つにまとめる。

終了コード0で食い違いなし、1で食い違いあり、2で引数か入力の誤り。
Python 3.10以降の標準ライブラリだけで動く。YAML は Skill の frontmatter と agents/openai.yaml に出る範囲だけを読む。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# (置き場所, 読むツール)。ツールの対応は Claude Code 2.1.302とCodex CLI 0.162.0で確かめた
SKILL_ROOTS = (
    (".claude/skills", "claude"),
    (".agents/skills", "codex"),
    (".codex/skills", "codex"),
)
# Codex の公式文書に載っていないが、0.162.0では読まれた置き場所
UNDOCUMENTED_CODEX_ROOT = ".codex/skills"

# Agent Skills の仕様の上限。Codex 0.162.0は name が超えると読み込まず、description は超えた分を切った
MAX_NAME = 64
DEFAULT_MAX_DESCRIPTION = 1024
# Claude Code は一覧で description と when_to_use を合わせて切る。skillListingMaxDescChars で変えられる
DEFAULT_CLAUDE_LISTING_LIMIT = 1536

OPENAI_YAML_POLICY = "policy:\n  allow_implicit_invocation: false\n"

CLAUDE_TRUE = {"true", "yes", "on", "1"}
CLAUDE_FALSE = {"false", "no", "off", "0"}
# Codex は YAML 1.2の真偽値だけを読む。no / 0 / "false" は false にならなかった
CODEX_TRUE = {"true", "True", "TRUE"}
CODEX_FALSE = {"false", "False", "FALSE"}


class YamlError(ValueError):
    pass


class Scalar(str):
    """引用符で囲まれていたかを覚えている文字列。"""

    quoted: bool

    def __new__(cls, value: str, quoted: bool = False) -> Scalar:
        obj = super().__new__(cls, value)
        obj.quoted = quoted
        return obj


KEY_RE = re.compile(r"""^(?P<key>"[^"]*"|'[^']*'|[^\s#'"][^:#]*?)\s*:(?:\s+(?P<rest>.*))?$""")
BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?[1-9]?[+-]?(?:\s+#.*)?$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skippable(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _strip_comment(text: str) -> str:
    return re.split(r"\s+#", text, maxsplit=1)[0].rstrip()


def _unquote_key(key: str) -> str:
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        return key[1:-1]
    return key


def _parse_quoted(text: str, lines: list[str], i: int) -> tuple[Scalar, int]:
    quote = text[0]
    buf = text[1:]
    pieces = []
    while True:
        if quote == '"':
            end = _find_double_quote_end(buf)
        else:
            end = _find_single_quote_end(buf)
        if end >= 0:
            pieces.append(buf[:end])
            break
        pieces.append(buf.strip())
        if i >= len(lines):
            raise YamlError("引用符が閉じていない")
        buf = lines[i].strip()
        i += 1
    raw = " ".join(p for p in pieces if p != "") if len(pieces) > 1 else pieces[0]
    if quote == '"':
        value = re.sub(r'\\(["\\/nt])', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), raw)
    else:
        value = raw.replace("''", "'")
    return Scalar(value, quoted=True), i


def _find_double_quote_end(buf: str) -> int:
    escaped = False
    for pos, ch in enumerate(buf):
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return pos
    return -1


def _find_single_quote_end(buf: str) -> int:
    pos = 0
    while pos < len(buf):
        if buf[pos] == "'":
            if pos + 1 < len(buf) and buf[pos + 1] == "'":
                pos += 2
                continue
            return pos
        pos += 1
    return -1


def _parse_flow_mapping(text: str) -> dict:
    inner = _strip_comment(text)
    if not inner.endswith("}"):
        raise YamlError("{ } の形を読めない")
    inner = inner[1:-1].strip()
    result: dict = {}
    if not inner:
        return result
    for part in inner.split(","):
        if "{" in part or "[" in part:
            raise YamlError("入れ子の { } は読めない")
        key, sep, value = part.partition(":")
        if not sep:
            raise YamlError("{ } の中に key: value でない要素がある")
        value = value.strip()
        if value[:1] in "\"'":
            result[_unquote_key(key.strip())] = Scalar(value[1:-1], quoted=True)
        else:
            result[_unquote_key(key.strip())] = Scalar(value)
    return result


def _collect_block(lines: list[str], i: int, parent_indent: int) -> tuple[list[str], int]:
    block = []
    while i < len(lines):
        line = lines[i]
        if line.strip() and _indent(line) <= parent_indent:
            break
        block.append(line)
        i += 1
    while block and not block[-1].strip():
        block.pop()
    return block, i


def _block_scalar(indicator: str, block: list[str]) -> Scalar:
    body = [line for line in block if line.strip()]
    if not body:
        return Scalar("")
    base = min(_indent(line) for line in body)
    texts = [line[base:] if line.strip() else "" for line in block]
    if indicator.startswith("|"):
        return Scalar("\n".join(texts))
    paragraphs, current = [], []
    for text in texts:
        if text:
            current.append(text.strip())
        else:
            paragraphs.append(" ".join(current))
            current = []
    paragraphs.append(" ".join(current))
    return Scalar("\n".join(paragraphs))


def _parse_mapping(lines: list[str], i: int, indent: int) -> tuple[dict, int]:
    result: dict = {}
    while i < len(lines):
        line = lines[i]
        if _skippable(line):
            i += 1
            continue
        current = _indent(line)
        if current < indent:
            break
        if current > indent:
            raise YamlError(f"{i + 1}行目のインデントが合わない")
        content = line.strip()
        match = KEY_RE.match(content)
        if not match or content.startswith("- "):
            raise YamlError(f"{i + 1}行目を key: value として読めない")
        key = _unquote_key(match.group("key").strip())
        rest = (match.group("rest") or "").strip()
        i += 1
        if not rest or rest.startswith("#"):
            j = i
            while j < len(lines) and _skippable(lines[j]):
                j += 1
            if j >= len(lines):
                result[key] = None
            elif (
                _indent(lines[j]) > current and not lines[j].strip().startswith("- ") and KEY_RE.match(lines[j].strip())
            ):
                result[key], i = _parse_mapping(lines, j, _indent(lines[j]))
            elif lines[j].strip().startswith("- ") and _indent(lines[j]) >= current:
                # 配列の中身は使わないので読み飛ばす
                k = j
                while k < len(lines) and (
                    _skippable(lines[k])
                    or _indent(lines[k]) > current
                    or (_indent(lines[k]) == current and lines[k].strip().startswith("- "))
                ):
                    k += 1
                result[key], i = [], k
            elif _indent(lines[j]) > current:
                block, i = _collect_block(lines, i, current)
                result[key] = Scalar(" ".join(line.strip() for line in block if line.strip()))
            else:
                result[key] = None
        elif BLOCK_SCALAR_RE.match(rest):
            block, i = _collect_block(lines, i, current)
            result[key] = _block_scalar(rest, block)
        elif rest[0] in "\"'":
            result[key], i = _parse_quoted(rest, lines, i)
        elif rest.startswith("{"):
            result[key] = _parse_flow_mapping(rest)
        elif rest.startswith("["):
            result[key] = []
        else:
            parts = [_strip_comment(rest)]
            block, i = _collect_block(lines, i, current)
            parts.extend(line.strip() for line in block if line.strip() and not line.strip().startswith("#"))
            result[key] = Scalar(" ".join(parts))
    return result, i


def parse_yaml_mapping(text: str) -> dict:
    """frontmatter と agents/openai.yaml に出る範囲の YAML を辞書にする。"""
    lines = text.replace("\t", "    ").splitlines()
    result, i = _parse_mapping(lines, 0, 0)
    for rest in lines[i:]:
        if not _skippable(rest):
            raise YamlError("最上位の key: value のあとに読めない行がある")
    return result


def split_frontmatter(text: str) -> str | None:
    """SKILL.md の先頭の --- から次の --- までを返す。frontmatter がなければ None。"""
    text = text.lstrip("﻿")
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        return None
    for pos in range(1, len(lines)):
        if lines[pos].rstrip() == "---":
            return "\n".join(lines[1:pos])
    raise YamlError("frontmatter を閉じる --- がない")


@dataclass
class Finding:
    level: str  # "NG" か "warn"
    message: str


@dataclass
class Skill:
    path: Path
    entry_name: str
    via: set = field(default_factory=set)
    name: str | None = None
    description: str | None = None
    when_to_use: str | None = None
    claude_auto: bool = True
    codex_auto: bool = True
    has_openai_yaml: bool = False
    findings: list = field(default_factory=list)

    @property
    def claude_visible(self) -> bool:
        return any(SKILL_ROOT_TOOL[root] == "claude" for root in self.via)

    @property
    def codex_visible(self) -> bool:
        return any(SKILL_ROOT_TOOL[root] == "codex" for root in self.via)

    def add(self, level: str, message: str) -> None:
        self.findings.append(Finding(level, message))

    @property
    def result(self) -> str:
        levels = {f.level for f in self.findings}
        if "NG" in levels:
            return "NG"
        if "warn" in levels:
            return "warn"
        return "ok"


SKILL_ROOT_TOOL = dict(SKILL_ROOTS)


def discover(root: Path) -> list[Skill]:
    skills: dict[Path, Skill] = {}
    for rel, _tool in SKILL_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if not entry.is_dir() or not (entry / "SKILL.md").is_file():
                continue
            real = entry.resolve()
            skill = skills.get(real)
            if skill is None:
                skill = skills[real] = Skill(path=real, entry_name=entry.name)
            skill.via.add(rel)
    return sorted(skills.values(), key=lambda s: (s.entry_name, str(s.path)))


def _read_claude_flag(skill: Skill, frontmatter: dict) -> None:
    raw = frontmatter.get("disable-model-invocation")
    if raw is None:
        return
    value = str(raw).strip().lower()
    if value in CLAUDE_TRUE:
        skill.claude_auto = False
    elif value not in CLAUDE_FALSE:
        skill.add("warn", f"disable-model-invocation の値 `{raw}` を真偽値として読めず、Claude Code は自動で呼ぶ")


def _read_codex_policy(skill: Skill) -> tuple[str | None, bool]:
    """Codex の自動呼び出しの方針を読み、自動で呼ばれる理由と、値が壊れているかを返す。"""
    path = skill.path / "agents" / "openai.yaml"
    if not path.is_file():
        return "agents/openai.yaml がない", False
    skill.has_openai_yaml = True
    try:
        data = parse_yaml_mapping(path.read_text(encoding="utf-8"))
    except (YamlError, UnicodeDecodeError) as exc:
        return f"agents/openai.yaml を読めない（{exc}）", True
    policy = data.get("policy")
    if not isinstance(policy, dict) or "allow_implicit_invocation" not in policy:
        return "agents/openai.yaml に policy.allow_implicit_invocation がない", False
    raw = policy["allow_implicit_invocation"]
    if not isinstance(raw, Scalar):
        return "allow_implicit_invocation に真偽値がない", True
    if not raw.quoted and raw in CODEX_FALSE:
        skill.codex_auto = False
        return None, False
    if not raw.quoted and raw in CODEX_TRUE:
        return "allow_implicit_invocation が true", False
    shown = f'"{raw}"' if raw.quoted else str(raw)
    return f"allow_implicit_invocation の値 `{shown}` を Codex は false と読まない", True


def inspect(skill: Skill, max_description: int, claude_listing_limit: int) -> None:
    frontmatter: dict = {}
    readable = False
    try:
        block = split_frontmatter((skill.path / "SKILL.md").read_text(encoding="utf-8"))
        if block is None:
            skill.add("NG", "SKILL.md に frontmatter がなく、Codex が読み込まない")
        else:
            frontmatter = parse_yaml_mapping(block)
            readable = True
    except (YamlError, UnicodeDecodeError) as exc:
        skill.add("NG", f"SKILL.md の frontmatter を読めない（{exc}）")

    name = frontmatter.get("name")
    skill.name = str(name).strip() if name is not None else None
    description = frontmatter.get("description")
    skill.description = str(description).strip() if description is not None else None
    when_to_use = frontmatter.get("when_to_use")
    skill.when_to_use = str(when_to_use).strip() if when_to_use is not None else None

    dirname = skill.entry_name
    if skill.name and len(skill.name) > MAX_NAME:
        skill.add("NG", f"name が{len(skill.name)}文字で{MAX_NAME}文字を超え、Codex が読み込まない")
    elif skill.name and skill.name != dirname:
        skill.add(
            "warn",
            f"name `{skill.name}` がディレクトリ名と違い、呼び出す名前がずれる"
            f"（Claude Code は /{dirname} と /{skill.name}、Codex は ${skill.name}）",
        )
    if not skill.description:
        if readable:
            skill.add("NG", "description がなく、Codex が読み込まない。Claude Code は本文の最初の行を説明に使う")
    else:
        if len(skill.description) > max_description:
            skill.add(
                "warn",
                f"description が{len(skill.description)}文字で、Codex は{max_description}文字で切る",
            )
        listing = len(skill.description) + (len(skill.when_to_use) + 1 if skill.when_to_use else 0)
        if listing > claude_listing_limit:
            skill.add(
                "warn",
                f"description と when_to_use が計{listing}文字で、Claude Code は一覧で{claude_listing_limit}文字で切る",
            )

    _read_claude_flag(skill, frontmatter)
    codex_reason, broken = _read_codex_policy(skill)

    if not skill.claude_auto and skill.codex_auto:
        hint = "。--fix で作れる" if not skill.has_openai_yaml else ""
        skill.add("NG", f"Claude Code は自動で呼ばないが、Codex は自動で呼ぶ（{codex_reason}{hint}）")
    elif skill.claude_auto and not skill.codex_auto:
        skill.add(
            "NG",
            "Codex は自動で呼ばないが、Claude Code は自動で呼ぶ（SKILL.md に disable-model-invocation: true がない）",
        )
    elif broken:
        skill.add("warn", codex_reason)

    if not skill.claude_visible:
        skill.add("NG", "Claude Code から見えない（.claude/skills から届かない）")
    if not skill.codex_visible:
        skill.add("NG", "Codex から見えない（.agents/skills から届かない）")
    elif skill.via & {rel for rel, tool in SKILL_ROOTS if tool == "codex"} == {UNDOCUMENTED_CODEX_ROOT}:
        skill.add("warn", "Codex には .codex/skills からだけ見える。公式文書の置き場所は .agents/skills")


def fix(skills: list[Skill], root: Path) -> list[str]:
    """Claude Code で自動呼び出しを止めた Skill に、足りない agents/openai.yaml を作る。"""
    written = []
    for skill in skills:
        if skill.claude_auto or not skill.codex_auto or skill.has_openai_yaml:
            continue
        target = skill.path / "agents" / "openai.yaml"
        target.parent.mkdir(exist_ok=True)
        target.write_text(OPENAI_YAML_POLICY, encoding="utf-8")
        written.append(_display(target, root))
    return written


def _display(path: Path, root: Path) -> str:
    return os.path.relpath(path, root)


def _labels(skills: list[Skill], root: Path) -> list[str]:
    names = [s.entry_name for s in skills]
    return [s.entry_name if names.count(s.entry_name) == 1 else _display(s.path, root) for s in skills]


def render(skills: list[Skill], root: Path) -> str:
    labels = _labels(skills, root)
    header = ("skill", "claude", "codex", "claude-auto", "codex-auto", "result")
    rows = [
        (
            label,
            "yes" if s.claude_visible else "no",
            "yes" if s.codex_visible else "no",
            "on" if s.claude_auto else "off",
            "on" if s.codex_auto else "off",
            s.result,
        )
        for label, s in zip(labels, skills, strict=True)
    ]
    widths = [max(len(row[col]) for row in [header, *rows]) for col in range(len(header))]
    out = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [header, *rows]
    ]
    details = [
        f"{f.level:<4}  {label}  {f.message}"
        for label, s in zip(labels, skills, strict=True)
        for f in sorted(s.findings, key=lambda f: f.level != "NG")
    ]
    if details:
        out.append("")
        out.extend(details)
    return "\n".join(out)


def check(root: Path, max_description: int, claude_listing_limit: int) -> list[Skill]:
    skills = discover(root)
    for skill in skills:
        inspect(skill, max_description, claude_listing_limit)
    return skills


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Claude Code と Codex で共有する Skill の呼び出し方針と検出の食い違いを調べる",
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリのルート（既定はカレントディレクトリ）")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="disable-model-invocation: true の Skill に、ない agents/openai.yaml を作る",
    )
    parser.add_argument(
        "--max-description",
        type=int,
        default=DEFAULT_MAX_DESCRIPTION,
        help=f"description の上限の文字数（既定は{DEFAULT_MAX_DESCRIPTION}。Agent Skills の仕様と Codex 0.162.0の挙動）",
    )
    parser.add_argument(
        "--claude-listing-limit",
        type=int,
        default=DEFAULT_CLAUDE_LISTING_LIMIT,
        help=f"Claude Code の一覧で description と when_to_use を合わせた上限（既定は{DEFAULT_CLAUDE_LISTING_LIMIT}）",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ディレクトリではない: {args.root}", file=sys.stderr)
        return 2
    if not any((root / rel).is_dir() for rel, _tool in SKILL_ROOTS):
        print(f"{args.root} に .claude/skills / .agents/skills / .codex/skills がない", file=sys.stderr)
        return 2

    skills = check(root, args.max_description, args.claude_listing_limit)
    if args.fix:
        for path in fix(skills, root):
            print(f"作成: {path}")
        skills = check(root, args.max_description, args.claude_listing_limit)

    if not skills:
        print("SKILL.md を持つディレクトリがない")
        return 0
    print(render(skills, root))
    failures = sum(1 for s in skills if s.result == "NG")
    print()
    if failures:
        print(f"食い違いのある Skill が{failures}件ある")
        return 1
    print("食い違いはない")
    return 0


if __name__ == "__main__":
    sys.exit(main())
