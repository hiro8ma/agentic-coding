"""revert された変更を正解にして、AI のコードレビューの検出率とノイズを測る。

Usage:
    python3 reviewer_eval.py --reviewer CMD [--repo PATH] [--rev REV] [--keywords PATH] [--json-out PATH]
    python3 reviewer_eval.py --claude [--repo PATH] ...
    python3 reviewer_eval.py --dry-run [--repo PATH] ...

revert のコミットごとに、元のコミットの差分をレビューの入力にし、revert が変えた行を不具合の位置とみなす。
revert されず、後のコミットが同じファイルを触っていないコミットを clean のケースにし、指摘の数をノイズとみなす。
レビューのコマンドは差分を標準入力で受け取り、1行に1件 {"file", "line", "summary"} の JSON を出す。

終了コード0で完了、1でレビューのコマンドが失敗したケースあり、2で引数か入力の誤り。
Python 3.10以降の標準ライブラリと git だけで動く。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

TRAILER_RE = re.compile(r"^This reverts commit ([0-9a-f]{7,64})\b", re.MULTILINE)
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
SHA_PREFIX_RE = re.compile(r"^[0-9a-f]{7,64}$")
REVERT_GREP = ('--grep=^Revert "', "--grep=^This reverts commit ")
# 利用者の diff.noprefix / diff.renames / color.ui の設定に出力の形を左右させない
DIFF_FLAGS = ("--no-color", "--no-ext-diff", "--no-renames", "--src-prefix=a/", "--dst-prefix=b/")

DEFAULT_TOLERANCE = 3
DEFAULT_MAX_CASES = 50
DEFAULT_CLEAN_CASES = 10
DEFAULT_CLEAN_WINDOW = 20
DEFAULT_MAX_DIFF_BYTES = 200_000
DEFAULT_TIMEOUT = 600.0

CLAUDE_PROMPT = (
    "You are reviewing a code change. The unified diff is on stdin. "
    "Report only problems likely to cause a bug or an incident, not style. "
    'Output one JSON object per line: {"file": "<path without a/ or b/>", '
    '"line": <line number in the new version of the file>, "summary": "<one sentence>"}. '
    "Output nothing else. If you find no problem, output nothing."
)

SUMMARY_LINES = (
    ("cases", "caught", "keyword_cases", "strict_caught", "clean_cases", "errors"),
    ("recall", "strict_recall", "findings_per_clean_case"),
    ("findings_per_case", "noise_share", "tolerance"),
)

Ranges = dict[str, list[tuple[int, int]]]


class GitError(RuntimeError):
    pass


@dataclass
class Case:
    kind: str  # "reverted" か "clean"
    target: str
    subject: str
    diff: str
    revert: str | None = None
    expected: Ranges = field(default_factory=dict)
    keywords: list[str] = field(default_factory=list)


@dataclass
class Finding:
    file: str
    line: int
    summary: str
    hit: bool = False
    strict: bool = False


@dataclass
class Result:
    case: Case
    findings: list[Finding] = field(default_factory=list)
    invalid_lines: int = 0
    error: str | None = None

    @property
    def hits(self) -> int:
        return sum(f.hit for f in self.findings)

    @property
    def strict_hits(self) -> int:
        return sum(f.strict for f in self.findings)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.case.kind == "clean":
            return "flagged" if self.findings else "quiet"
        return "caught" if self.hits else "missed"


def _run(command: list[str], stdin: str | None, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, input=stdin, capture_output=True, encoding="utf-8", errors="replace", check=False, **kwargs
    )


def git(repo: Path, *args: str, stdin: str | None = None) -> str:
    proc = _run(["git", "-C", str(repo), "-c", "core.quotePath=false", *args], stdin)
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {args[0]} が終了コード{proc.returncode}で失敗した")
    return proc.stdout


def commit_diff(repo: Path, sha: str, context: int) -> str:
    """最初の親との差分を返す。親がなければ空の tree との差分にする。"""
    parents = git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
    base = parents[0] if parents else git(repo, "hash-object", "-t", "tree", "--stdin", stdin="").strip()
    return git(repo, "diff", f"-U{context}", *DIFF_FLAGS, base, sha)


def reverted_lines(diff: str) -> Ranges:
    """revert の -U0 の差分から、revert が変えた行の範囲をファイルごとに返す。

    座標は revert の直前の版で、間に別の変更がなければ元のコミットの変更後の版と一致する。
    範囲が空のファイル（バイナリやモードだけの変更）は、ファイルのどの行も範囲に含める。
    """
    expected: Ranges = {}
    ranges: list[tuple[int, int]] = []
    created = in_header = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            # --no-renames なので `a/<path> b/<path>` の2つのパスは同じ長さになる
            ranges = expected.setdefault(line[len("diff --git a/") : (len(line) + 10) // 2], [])
            in_header, created = True, False
            continue
        if in_header and line.startswith("--- "):
            created = line[4:].rstrip("\t") == "/dev/null"
            continue
        match = HUNK_RE.match(line)
        if not match:
            continue
        in_header = False
        old_start, old_count = int(match[1]), int(match[2] or 1)
        new_start, new_count = int(match[3]), int(match[4] or 1)
        if created:
            # 元のコミットが消したファイルを revert が戻した。レビューは消えた側の行番号を指す
            ranges.append((new_start, new_start + new_count - 1))
        elif old_count == 0:
            ranges.append((max(old_start, 1), old_start + 1))
        else:
            ranges.append((old_start, old_start + old_count - 1))
    return expected


def _resolve(repo: Path, sha: str) -> str | None:
    try:
        return git(repo, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}").strip()
    except GitError:
        return None


def find_reverts(repo: Path, rev: str) -> dict[str, list[str]]:
    """revert らしいコミットの sha から、本文に書かれた対象の sha への辞書を新しい順に返す。"""
    out = git(repo, "log", "--no-show-signature", "--format=%H%x1f%B%x1e", *REVERT_GREP, rev, "--")
    reverts = {}
    for record in out.split("\x1e"):
        if record.strip():
            sha, body = record.strip("\n").split("\x1f", 1)
            reverts[sha] = TRAILER_RE.findall(body)
    return reverts


def extract_cases(
    repo: Path, rev: str, max_cases: int, max_diff_bytes: int
) -> tuple[list[Case], Counter[str], set[str]]:
    """revert のケースと除外の理由の件数、revert か revert の対象になったコミットの sha を返す。"""
    skipped: Counter[str] = Counter()
    reverts = find_reverts(repo, rev)
    targets: dict[str, str] = {}
    for sha, found in reverts.items():
        resolved = {_resolve(repo, s) for s in found}
        if not found:
            skipped["no_trailer"] += 1
        elif None in resolved:
            skipped["target_not_found"] += 1
        elif len(resolved) > 1:
            skipped["multiple_targets"] += 1
        else:
            targets[sha] = resolved.pop()

    reverted = set(targets.values())
    cases: list[Case] = []
    for sha, target in targets.items():
        if len(cases) >= max_cases:
            skipped["over_limit"] += 1
            continue
        # revert が後で取り消されたなら、元の変更は不具合ではなかったとみなす
        if sha in reverted:
            skipped["revert_reverted"] += 1
            continue
        message = git(repo, "show", "-s", "--no-show-signature", "--format=%B", target)
        if message.startswith('Revert "') or TRAILER_RE.search(message):
            skipped["target_is_revert"] += 1
            continue
        diff = commit_diff(repo, target, 3)
        expected = reverted_lines(commit_diff(repo, sha, 0))
        if not diff.strip() or not expected:
            skipped["empty_diff"] += 1
        elif len(diff.encode("utf-8")) > max_diff_bytes:
            skipped["diff_too_large"] += 1
        else:
            subject = message.split("\n", 1)[0]
            cases.append(Case("reverted", target, subject, diff, revert=sha, expected=expected))
    return cases, skipped, set(reverts) | reverted


def find_clean(repo: Path, rev: str, *, limit: int, window: int, excluded: set[str], max_diff_bytes: int) -> list[Case]:
    """excluded になく、後の window 件のコミットが同じファイルを触っていないコミットを新しい順に返す。"""
    if limit == 0:
        return []
    out = git(repo, "log", "--no-show-signature", "--no-renames", "--name-only", "--format=%x1e%H %P%x1f%s", rev, "--")
    commits = []
    for record in out.split("\x1e")[1:]:
        head, _, names = record.partition("\n")
        ids, _, subject = head.partition("\x1f")
        sha, *parents = ids.split()
        commits.append((sha, len(parents), subject, {n for n in names.splitlines() if n}))

    clean: list[Case] = []
    # 新しい側に window 件のコミットがないものは、まだ問題が出ていないだけかもしれないので除く
    for i in range(window, len(commits)):
        sha, parents, subject, files = commits[i]
        if parents != 1 or sha in excluded or not files:
            continue
        if any(files & later for *_, later in commits[i - window : i]):
            continue
        diff = commit_diff(repo, sha, 3)
        if diff.strip() and len(diff.encode("utf-8")) <= max_diff_bytes:
            clean.append(Case("clean", sha, subject, diff))
            if len(clean) >= limit:
                break
    return clean


def load_keywords(path: str) -> dict[str, list[str]]:
    """{"<revert か対象の sha の先頭7文字以上>": ["語", ...]} の JSON を読む。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("最上位が JSON のオブジェクトでない")
    keywords = {}
    for key, value in data.items():
        words = [value] if isinstance(value, str) else value
        if not SHA_PREFIX_RE.match(key) or not isinstance(words, list) or not all(isinstance(w, str) for w in words):
            raise ValueError(f"{key} は sha の先頭7文字以上と、語の配列にする")
        keywords[key] = [w for w in words if w.strip()]
    return keywords


def attach_keywords(cases: list[Case], keywords: dict[str, list[str]]) -> list[str]:
    """ケースに語を付け、どのケースにも合わなかったキーを返す。"""
    unused = []
    for key, words in keywords.items():
        matched = [
            c for c in cases if c.kind == "reverted" and key in (c.target[: len(key)], (c.revert or "")[: len(key)])
        ]
        for case in matched:
            case.keywords.extend(w for w in words if w not in case.keywords)
        if not matched:
            unused.append(key)
    return unused


def parse_findings(output: str) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    invalid = 0
    for raw in output.splitlines():
        text = raw.strip()
        if not text or text.startswith("```"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            invalid += 1
            continue
        line = obj.get("line") if isinstance(obj, dict) else None
        if isinstance(line, str) and line.isdigit():
            line = int(line)
        if not isinstance(obj, dict) or not isinstance(obj.get("file"), str) or type(line) is not int:
            invalid += 1
            continue
        findings.append(Finding(file=obj["file"], line=line, summary=str(obj.get("summary", ""))))
    return findings, invalid


def is_hit(finding: Finding, expected: Ranges, tolerance: int) -> bool:
    path = finding.file
    for prefix in ("./", "a/", "b/"):
        if path not in expected and path.startswith(prefix):
            path = path[len(prefix) :]
    ranges = expected.get(path)
    if ranges is None:
        return False
    return not ranges or any(start - tolerance <= finding.line <= end + tolerance for start, end in ranges)


def is_strict_hit(finding: Finding, keywords: list[str]) -> bool:
    summary = finding.summary.casefold()
    return finding.hit and any(word.casefold() in summary for word in keywords)


def run_reviewer(command: list[str], diff: str, timeout: float, cwd: str | None) -> tuple[str, str | None]:
    try:
        proc = _run(command, diff, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        return "", f"{timeout:g}秒で終わらなかった"
    except OSError as exc:
        return "", f"起動できなかった（{exc}）"
    if proc.returncode != 0:
        last = proc.stderr.strip().splitlines()[-1:]
        return proc.stdout, f"終了コード{proc.returncode}" + (f"（{last[0]}）" if last else "")
    return proc.stdout, None


def evaluate(
    cases: list[Case], command: list[str], tolerance: int, timeout: float, cwd: str | None = None
) -> list[Result]:
    results = []
    for case in cases:
        stdout, error = run_reviewer(command, case.diff, timeout, cwd)
        if error:
            results.append(Result(case, error=error))
            continue
        findings, invalid = parse_findings(stdout)
        for finding in findings:
            finding.hit = is_hit(finding, case.expected, tolerance)
            finding.strict = is_strict_hit(finding, case.keywords)
        results.append(Result(case, findings, invalid))
    return results


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(results: list[Result], skipped: Counter[str], tolerance: int) -> dict:
    scored = [r for r in results if r.error is None]
    reverted = [r for r in scored if r.case.kind == "reverted"]
    keyed = [r for r in reverted if r.case.keywords]
    clean = [r for r in scored if r.case.kind == "clean"]
    findings = [f for r in reverted for f in r.findings]
    caught = sum(1 for r in reverted if r.hits)
    strict_caught = sum(1 for r in keyed if r.strict_hits)
    return {
        "cases": len(reverted),
        "caught": caught,
        "recall": _ratio(caught, len(reverted)),
        "keyword_cases": len(keyed),
        "strict_caught": strict_caught,
        "strict_recall": _ratio(strict_caught, len(keyed)),
        "clean_cases": len(clean),
        "findings_per_clean_case": _ratio(sum(len(r.findings) for r in clean), len(clean)),
        "findings_per_case": _ratio(len(findings), len(reverted)),
        "noise_share": _ratio(sum(1 for f in findings if not f.hit), len(findings)),
        "errors": len(results) - len(scored),
        "tolerance": tolerance,
        "skipped": dict(sorted(skipped.items())),
    }


def to_json(results: list[Result], summary: dict) -> dict:
    return {
        "summary": summary,
        "cases": [
            {
                "kind": r.case.kind,
                "revert": r.case.revert,
                "target": r.case.target,
                "subject": r.case.subject,
                "status": r.status,
                "expected": {path: [list(rng) for rng in ranges] for path, ranges in r.case.expected.items()},
                "keywords": r.case.keywords,
                "findings": [asdict(f) for f in r.findings],
                "invalid_lines": r.invalid_lines,
                "error": r.error,
            }
            for r in results
        ],
    }


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    widths = [max(len(row[col]) for row in [header, *rows]) for col in range(len(header))]
    return [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in [header, *rows]
    ]


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _skipped_line(skipped: Counter[str] | dict) -> str:
    return "skipped  " + ("  ".join(f"{k} {v}" for k, v in sorted(skipped.items())) or "-")


def render_results(results: list[Result], summary: dict) -> str:
    rows = []
    for r in results:
        reverted = r.case.kind == "reverted"
        rows.append(
            (
                r.case.kind,
                (r.case.revert or "-")[:8],
                r.case.target[:8],
                str(len(r.findings)),
                str(r.hits) if reverted else "-",
                str(r.strict_hits) if r.case.keywords else "-",
                str(len(r.findings) - r.hits),
                r.status,
                r.case.subject,
            )
        )
    header = ("kind", "revert", "target", "findings", "hits", "strict", "noise", "result", "subject")
    out = _table(header, rows)
    out.extend(f"error  {r.case.target[:8]}  {r.error}" for r in results if r.error)
    out.append("")
    out.extend("  ".join(f"{key} {_fmt(summary[key])}" for key in keys) for keys in SUMMARY_LINES)
    out.append(_skipped_line(summary["skipped"]))
    return "\n".join(out)


def render_cases(cases: list[Case], skipped: Counter[str]) -> str:
    def where(expected: Ranges) -> str:
        return " ".join(
            f"{path}:" + (",".join(f"{s}-{e}" if s != e else str(s) for s, e in ranges) or "*")
            for path, ranges in expected.items()
        )

    rows = [
        (c.kind, (c.revert or "-")[:8], c.target[:8], where(c.expected) or "-", ",".join(c.keywords) or "-", c.subject)
        for c in cases
    ]
    header = ("kind", "revert", "target", "expected", "keywords", "subject")
    return "\n".join([*_table(header, rows), "", _skipped_line(skipped)])


def reviewer_command(args: argparse.Namespace) -> list[str]:
    if args.claude:
        # --tools は値を複数取るので最後に置く。ツールを渡さず、差分の外（revert 後の版）を読ませない
        return ["claude", "-p", CLAUDE_PROMPT, "--no-session-persistence", "--output-format", "text", "--tools", ""]
    return shlex.split(args.reviewer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="revert された変更を正解にして、AI のコードレビューの検出率とノイズを測る"
    )
    parser.add_argument("--repo", default=".", help="対象の git リポジトリ（既定はカレントディレクトリ）")
    parser.add_argument(
        "--rev", default="HEAD", help="ケースを探す範囲。git log に渡す（例 main~500..main。既定は HEAD）"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--reviewer", help="レビューのコマンド。差分を標準入力で受け取り、指摘を JSON Lines で出す")
    mode.add_argument(
        "--claude", action="store_true", help="claude -p をツールなしで呼んでレビューさせる。利用料がかかる"
    )
    mode.add_argument("--dry-run", action="store_true", help="レビューを呼ばずに、抽出したケースと revert の範囲を出す")
    parser.add_argument("--keywords", help="revert のケースごとの語の JSON。strict の判定に使う")
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE, help="範囲の前後に許す行数")
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES, help="新しい順に評価する revert の件数")
    parser.add_argument(
        "--clean-cases", type=int, default=DEFAULT_CLEAN_CASES, help="clean のケースの件数。0で使わない"
    )
    parser.add_argument(
        "--clean-window", type=int, default=DEFAULT_CLEAN_WINDOW, help="clean とみなすまでに待つ後のコミットの件数"
    )
    parser.add_argument("--max-diff-bytes", type=int, default=DEFAULT_MAX_DIFF_BYTES, help="これより大きい差分は除く")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="1ケースの秒数の上限")
    parser.add_argument("--json-out", help="JSON をこのファイルに書き、標準出力には表だけを出す")
    args = parser.parse_args(argv)
    if min(args.tolerance, args.clean_cases) < 0 or min(args.max_cases, args.clean_window, args.max_diff_bytes) < 1:
        parser.error(
            "--tolerance / --clean-cases は0以上、--max-cases / --clean-window / --max-diff-bytes は1以上にする"
        )
    if args.timeout <= 0:
        parser.error("--timeout は正の値にする")

    command: list[str] = []
    if not args.dry_run:
        command = reviewer_command(args)
        if not command or shutil.which(command[0]) is None:
            print(f"レビューのコマンドが見つからない: {command[0] if command else '（空）'}", file=sys.stderr)
            return 2
    try:
        keywords = load_keywords(args.keywords) if args.keywords else {}
    except (OSError, ValueError, TypeError) as exc:
        print(f"--keywords を読めない: {exc}", file=sys.stderr)
        return 2

    repo = Path(args.repo)
    try:
        cases, skipped, excluded = extract_cases(repo, args.rev, args.max_cases, args.max_diff_bytes)
        cases += find_clean(
            repo,
            args.rev,
            limit=args.clean_cases,
            window=args.clean_window,
            excluded=excluded,
            max_diff_bytes=args.max_diff_bytes,
        )
    except (GitError, OSError) as exc:
        print(f"git の履歴を読めない: {exc}", file=sys.stderr)
        return 2
    for key in attach_keywords(cases, keywords):
        print(f"--keywords の {key} に合う revert のケースがない", file=sys.stderr)

    if args.dry_run:
        print(render_cases(cases, skipped))
        return 0
    if not cases:
        print("評価できるケースがない")
        print(_skipped_line(skipped))
        return 0

    with tempfile.TemporaryDirectory() as isolated:
        results = evaluate(cases, command, args.tolerance, args.timeout, isolated if args.claude else None)
    summary = summarize(results, skipped, args.tolerance)
    report = json.dumps(to_json(results, summary), ensure_ascii=False, indent=2)
    print(render_results(results, summary))
    if args.json_out:
        Path(args.json_out).write_text(report + "\n", encoding="utf-8")
    else:
        print()
        print(report)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
