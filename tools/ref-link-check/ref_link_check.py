#!/usr/bin/env python3
"""エージェントの最後の答えに URL のない Issue / PR の番号があれば、Stop の hook で答え直させる。

Usage:
    python3 ref_link_check.py                      # Claude Code の Stop の hook
    python3 ref_link_check.py --prefixes IX,PROJ   # 番号の接頭辞を変える

標準入力の hook の JSON から last_assistant_message を読む。
無ければ transcript_path の JSONL を末尾から読み、最後の答えの文を取り出す。
`#123` と `<接頭辞>-123` のうち、同じ行に URL がなく、次の空でない行も URL で始まらないものがあれば、
decision に block を返して答え直させる。
stop_hook_active が true のとき、JSON や transcript が読めないとき、解析に失敗したときは、
何も出さずに終了コード0で通す。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

DEFAULT_PREFIXES = ("IX", "PROJ", "E", "MPC")
PREFIXES_ENV = "REF_LINK_CHECK_PREFIXES"
MAX_SCAN_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
EXCERPT_WIDTH = 60
CODE_MARK = "`"

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_URL_LINE = re.compile(r"^[\s>]*<?https?://")
_PREFIX_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
# 和文の文字も \w に入るので、境界は ASCII の英数字だけで判定する
_ISSUE = r"(?<![A-Za-z0-9_/&])#[1-9][0-9]*(?![A-Za-z0-9_-])"


@dataclass(frozen=True)
class Reference:
    line: int
    refs: tuple[str, ...]
    excerpt: str


def parse_prefixes(value: str) -> tuple[str, ...]:
    names = (part.strip() for part in value.split(","))
    return tuple(dict.fromkeys(name for name in names if _PREFIX_NAME.match(name)))


def reference_pattern(prefixes: Sequence[str]) -> re.Pattern[str]:
    alternatives = [_ISSUE]
    if prefixes:
        names = "|".join(
            re.escape(name) for name in sorted(set(prefixes), key=len, reverse=True)
        )
        alternatives.append(rf"(?<![A-Za-z0-9_/-])(?:{names})-[0-9]+(?![A-Za-z0-9_-])")
    return re.compile("|".join(alternatives))


def mask_code(lines: list[str]) -> list[str]:
    """フェンスの中の行とインラインコードを CODE_MARK に置き換える。行の数は変えない"""
    masked: list[str] = []
    fence: str | None = None
    for line in lines:
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            masked.append(CODE_MARK)
            continue
        opening = _FENCE.match(line)
        # 「```a```」のように後ろにバッククォートがある行はフェンスでなくインラインコード
        if opening and not (
            opening.group(1)[0] == "`" and "`" in line[opening.end() :]
        ):
            fence = opening.group(1)
            masked.append(CODE_MARK)
            continue
        masked.append(_CODE_SPAN.sub(CODE_MARK, line))
    return masked


def _next_line_is_url(lines: list[str], index: int) -> bool:
    for line in lines[index + 1 :]:
        if line.strip():
            return bool(_URL_LINE.match(line))
    return False


def find_unlinked(
    text: str, prefixes: Sequence[str] = DEFAULT_PREFIXES
) -> list[Reference]:
    pattern = reference_pattern(prefixes)
    original = text.splitlines()
    lines = mask_code(original)
    found: list[Reference] = []
    for index, line in enumerate(lines):
        if _URL.search(line):
            continue
        refs = tuple(dict.fromkeys(pattern.findall(line)))
        if not refs or _next_line_is_url(lines, index):
            continue
        excerpt = original[index].strip()
        if len(excerpt) > EXCERPT_WIDTH:
            excerpt = excerpt[:EXCERPT_WIDTH] + "…"
        found.append(Reference(index + 1, refs, excerpt))
    return found


def block_reason(references: list[Reference]) -> str:
    lines = ["答えに、URL のない Issue / PR の番号がある"]
    for ref in references:
        lines.append(f"- {ref.line}行目「{ref.excerpt}」の {' / '.join(ref.refs)}")
    lines.append(
        "番号で触れる項目ごとに、タイトルを書き、次の行に URL をそのまま書く"
        "（Markdown のリンク記法は使わない）"
    )
    lines.append("タイトルと URL を確かめてから、答えを書き直す")
    lines.append("URL を確かめられない項目は、確かめられないと書く")
    return "\n".join(lines)


def reverse_lines(
    path: str, max_bytes: int = MAX_SCAN_BYTES, chunk_bytes: int = CHUNK_BYTES
) -> Iterator[bytes]:
    """ファイルの末尾から max_bytes までを、後ろの行から順に返す。途中で切れた先頭の行は返さない"""
    with open(path, "rb") as file:
        file.seek(0, os.SEEK_END)
        pos = file.tell()
        limit = max(0, pos - max_bytes)
        pieces: list[bytes] = []
        while pos > limit:
            size = min(chunk_bytes, pos - limit)
            pos -= size
            file.seek(pos)
            parts = file.read(size).split(b"\n")
            pieces.append(parts[-1])
            if len(parts) == 1:
                continue
            line = b"".join(reversed(pieces))
            if line.strip():
                yield line
            for part in reversed(parts[1:-1]):
                if part.strip():
                    yield part
            pieces = [parts[0]]
        if pos == 0:
            line = b"".join(reversed(pieces))
            if line.strip():
                yield line


def final_text_from_transcript(
    path: str, max_bytes: int = MAX_SCAN_BYTES
) -> str | None:
    """最後の利用者の入力か tool_use より後にある、メインのエージェントの文を返す"""
    texts: list[str] = []
    for raw in reverse_lines(path, max_bytes):
        try:
            entry = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(entry, dict) or entry.get("isSidechain") is True:
            continue
        kind = entry.get("type")
        if kind == "user":
            break
        if kind != "assistant":
            continue
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            continue
        reached_tool_use = False
        for block in reversed(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                texts.append(block["text"])
            elif block.get("type") in ("tool_use", "server_tool_use"):
                reached_tool_use = True
                break
        if reached_tool_use:
            break
    return "\n\n".join(reversed(texts)) or None


def final_text(payload: dict) -> str | None:
    message = payload.get("last_assistant_message")
    if isinstance(message, str):
        return message
    path = payload.get("transcript_path")
    if not isinstance(path, str) or not path:
        return None
    try:
        return final_text_from_transcript(os.path.expanduser(path))
    except OSError:
        return None


def resolve_prefixes(flag: str | None) -> tuple[str, ...]:
    value = flag if flag is not None else os.environ.get(PREFIXES_ENV)
    return DEFAULT_PREFIXES if value is None else parse_prefixes(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--prefixes",
        help=(
            f"番号の接頭辞をカンマ区切りで渡す（既定は {','.join(DEFAULT_PREFIXES)}。"
            f"環境変数 {PREFIXES_ENV} より優先する。空にすると # だけを見る）"
        ),
    )
    try:
        args, _ = parser.parse_known_args(argv)
    # Stop の hook が exit 2 を返すと答えを止めてしまうので、引数の誤りも通す
    except SystemExit:
        return 0
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict) or payload.get("stop_hook_active"):
            return 0
        text = final_text(payload)
        references = (
            find_unlinked(text, resolve_prefixes(args.prefixes)) if text else []
        )
    except Exception:  # noqa: BLE001
        return 0
    if references:
        output = {"decision": "block", "reason": block_reason(references)}
        print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
