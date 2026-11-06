"""ref_link_check のテスト。

Usage:
    python3 -m unittest discover -s tools/ref-link-check
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ref_link_check as rlc

PR_URL = "https://github.com/octo/app/pull/12"
ISSUE_URL = "https://example.com/issues/IX-34"

BLOCK_CASES: dict[str, tuple[str, list[tuple[int, tuple[str, ...]]]]] = {
    "番号だけの #": ("#12 を直した", [(1, ("#12",))]),
    "接頭辞の番号だけ": ("IX-34 は保留にした", [(1, ("IX-34",))]),
    "既定の接頭辞を全部見る": (
        "PROJ-8 と E-501 と MPC-77",
        [(1, ("PROJ-8", "E-501", "MPC-77"))],
    ),
    "和文に続く番号": ("前回の#12と、IX-34の件", [(1, ("#12", "IX-34"))]),
    "括弧で添えた番号": ("ログインを直す（#4821）", [(1, ("#4821",))]),
    "見出しの中の番号": ("## #12 の状況", [(1, ("#12",))]),
    "表のセルの番号": ("| #12 | ログインを直す |", [(1, ("#12",))]),
    "英文の文末の番号": ("See #12.", [(1, ("#12",))]),
    "次の行が URL で始まらない": (
        f"#12 ログインを直す\nURL は {PR_URL}",
        [(1, ("#12",))],
    ),
    "次の行がフェンスで、その中の URL は数えない": (
        f"#12 ログインを直す\n```\n{PR_URL}\n```",
        [(1, ("#12",))],
    ),
    "インラインコードの URL は数えない": (
        f"#12 ログインを直す `{PR_URL}`",
        [(1, ("#12",))],
    ),
    "URL の行の次の行の番号": (
        f"#12 ログインを直す\n{PR_URL}\n#13 一覧を速くする",
        [(3, ("#13",))],
    ),
    "同じ行の同じ番号は1つにまとめる": ("#12 と #12", [(1, ("#12",))]),
    "閉じていないバッククォートの後ろ": ("`gh pr view #12", [(1, ("#12",))]),
    "フェンスの後ろ": ("```\n#1\n```\n#12 を直した", [(4, ("#12",))]),
}

PASS_CASES: dict[str, str] = {
    "タイトルの次の行に URL": f"#12 ログインを直す\n{PR_URL}",
    "空行をはさんで次の行に URL": f"#12 ログインを直す\n\n{PR_URL}",
    "箇条書きの下に下げた URL": f"- #12 ログインを直す\n  {PR_URL}",
    "引用の中の URL": f"> #12 ログインを直す\n> {PR_URL}",
    "山括弧で囲んだ URL": f"#12 ログインを直す\n<{PR_URL}>",
    "接頭辞の番号と次の行の URL": f"IX-34 シェルフの並びを直す\n{ISSUE_URL}",
    "同じ行に URL": f"ログインを直す #12 {PR_URL}",
    "Markdown のリンク": f"[#12 ログインを直す]({PR_URL})",
    "URL の中の番号": (
        f"{PR_URL}#issuecomment-34\n{ISSUE_URL}\nhttps://example.com/page#12"
    ),
    "バッククォートのフェンスの中": "```\ngh pr view 12 # #12\nIX-34\n```",
    "チルダのフェンスの中": "~~~text\n#12\n~~~",
    "下げたフェンスの中": "- 例\n  ```bash\n  gh pr merge #12\n  ```",
    "長いフェンスは短い閉じで終わらない": "````\n```\n#12\n```\n````",
    "閉じていないフェンスは最後までコード": "```\n#12",
    "インラインコード": "`#12` と ``IX-34`` は例として書いた",
    "1行に書いた3つのバッククォートはインラインコード": "```#12``` を例にした",
    "Slack のチャンネル名": "#team-news に投稿した",
    "数字で始まるチャンネル名": "#2026-offsite で話した",
    "16進の色": "#fff / #FF5733 / #1a2b3c / #123abc / #000000 / #0a0",
    "コミットのハッシュ": (
        "707f592 / 1e4d2ab / deadbeef / 9fceb02d0ae598e95dc970b74767f19372d61af8"
    ),
    "指数表記": "1E-10 と 3.2E-5",
    "見出しの記号": "# 概要\n## 2. 手順\n### 12月の予定",
    "HTML の数値参照": "&#12; と &#1234;",
    "語に続く #": "page#12 と v1#2",
    "パスとファイル名の中の番号": "docs/E-501/notes.md と items/#12",
    "語の中の接頭辞": "RULE-2026 / TYPE-12 / SIX-3 / PROJECT-1 / EX-9",
    "小文字の接頭辞": "ix-12 / e-773 / mpc-1",
    "長い識別子の一部": "IX-12-fix / #2026-01",
    "番号のない答え": "テストは通った",
}


class FindUnlinkedTest(unittest.TestCase):
    def test_finds_references_without_url(self) -> None:
        for name, (text, want) in BLOCK_CASES.items():
            with self.subTest(name):
                got = [(ref.line, ref.refs) for ref in rlc.find_unlinked(text)]
                self.assertEqual(got, want)

    def test_passes_linked_or_non_references(self) -> None:
        for name, text in PASS_CASES.items():
            with self.subTest(name):
                self.assertEqual(rlc.find_unlinked(text), [])

    def test_excerpt_is_cut_at_width(self) -> None:
        text = "#12 " + "あ" * 100
        (ref,) = rlc.find_unlinked(text)
        self.assertEqual(ref.excerpt, text[: rlc.EXCERPT_WIDTH] + "…")


class PrefixTest(unittest.TestCase):
    def test_parse_prefixes(self) -> None:
        testCases = {
            "カンマ区切りと空白": {"value": " ABC , DEF ", "want": ("ABC", "DEF")},
            "空は # だけ": {"value": "", "want": ()},
            "英字で始まらない名前と記号を含む名前は捨てる": {
                "value": "1X,A-B,OK,,A_B",
                "want": ("OK",),
            },
            "重なる名前は1つにする": {"value": "IX,IX", "want": ("IX",)},
        }
        for name, case in testCases.items():
            with self.subTest(name):
                self.assertEqual(rlc.parse_prefixes(case["value"]), case["want"])

    def test_prefixes_change_what_is_found(self) -> None:
        text = "ABC-1 と IX-2 と #3"
        testCases = {
            "既定": {"prefixes": rlc.DEFAULT_PREFIXES, "want": ("IX-2", "#3")},
            "差し替え": {"prefixes": ("ABC",), "want": ("ABC-1", "#3")},
            "空": {"prefixes": (), "want": ("#3",)},
        }
        for name, case in testCases.items():
            with self.subTest(name):
                (ref,) = rlc.find_unlinked(text, case["prefixes"])
                self.assertEqual(ref.refs, case["want"])

    def test_flag_overrides_env(self) -> None:
        testCases = {
            "どちらもなければ既定": {
                "env": None,
                "flag": None,
                "want": rlc.DEFAULT_PREFIXES,
            },
            "環境変数": {"env": "ABC,DEF", "flag": None, "want": ("ABC", "DEF")},
            "引数が環境変数より優先": {"env": "ABC", "flag": "IX", "want": ("IX",)},
            "空の環境変数は # だけ": {"env": "", "flag": None, "want": ()},
        }
        for name, case in testCases.items():
            with self.subTest(name):
                env = {k: v for k, v in os.environ.items() if k != rlc.PREFIXES_ENV}
                if case["env"] is not None:
                    env[rlc.PREFIXES_ENV] = case["env"]
                with mock.patch.dict(os.environ, env, clear=True):
                    self.assertEqual(rlc.resolve_prefixes(case["flag"]), case["want"])

    def test_hook_reads_prefixes_flag(self) -> None:
        _, out = run_hook(stop_payload(message="ABC-1 と IX-2"), "--prefixes", "ABC")
        self.assertEqual(
            json.loads(out)["reason"].splitlines()[1],
            "- 1行目「ABC-1 と IX-2」の ABC-1",
        )


def run_hook(stdin: str, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    stdin_patch = mock.patch.object(sys, "stdin", io.StringIO(stdin))
    quiet = contextlib.redirect_stderr(io.StringIO())
    with stdin_patch, contextlib.redirect_stdout(out), quiet:
        code = rlc.main(list(args))
    return code, out.getvalue()


def stop_payload(
    message: str | None = None,
    transcript: str | None = None,
    active: bool = False,
) -> str:
    payload: dict = {
        "session_id": "s1",
        "hook_event_name": "Stop",
        "stop_hook_active": active,
        "background_tasks": [],
        "session_crons": [],
    }
    if message is not None:
        payload["last_assistant_message"] = message
    if transcript is not None:
        payload["transcript_path"] = transcript
    return json.dumps(payload, ensure_ascii=False)


def prompt(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def say(text: str, sidechain: bool = False) -> dict:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def thinking() -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "thinking"}]},
    }


def tool_use() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
        },
    }


def tool_result() -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    }


def meta(kind: str) -> dict:
    return {"type": kind, "sessionId": "s1"}


class TranscriptTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, entries: list[object], name: str = "t.jsonl") -> str:
        path = self.dir / name
        lines = [
            e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)
            for e in entries
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path)

    def test_final_text(self) -> None:
        testCases = {
            "tool_use の後の文だけを読む": {
                "entries": [
                    prompt("直して"),
                    say("#12 を見る"),
                    tool_use(),
                    tool_result(),
                    thinking(),
                    say("直した"),
                    meta("last-prompt"),
                ],
                "want": "直した",
            },
            "最後の tool_use の後に続く文をまとめる": {
                "entries": [prompt("x"), tool_use(), tool_result(), say("a"), say("b")],
                "want": "a\n\nb",
            },
            "同じ entry の中で tool_use より前の文は読まない": {
                "entries": [
                    prompt("x"),
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {"type": "text", "text": "前"},
                                {"type": "tool_use", "id": "t1"},
                                {"type": "text", "text": "後"},
                            ]
                        },
                    },
                ],
                "want": "後",
            },
            "content が文字列の entry": {
                "entries": [
                    prompt("x"),
                    {"type": "assistant", "message": {"content": "文字列"}},
                ],
                "want": "文字列",
            },
            "サブエージェントの文は読まない": {
                "entries": [prompt("x"), say("本文"), say("下請け", sidechain=True)],
                "want": "本文",
            },
            "最後が tool_result なら文はない": {
                "entries": [prompt("x"), say("#12"), tool_use(), tool_result()],
                "want": None,
            },
            "前のターンの文は読まない": {
                "entries": [prompt("x"), say("#12"), prompt("次")],
                "want": None,
            },
        }
        for name, case in testCases.items():
            with self.subTest(name):
                path = self.write(case["entries"])
                self.assertEqual(rlc.final_text_from_transcript(path), case["want"])

    def test_only_final_text_blocks(self) -> None:
        testCases = {
            "前の文の番号では止めない": {
                "entries": [prompt("x"), say("#12 を見る"), tool_use(), tool_result()]
                + [say("直した")],
                "block": False,
            },
            "最後の文の番号で止める": {
                "entries": [prompt("x"), say(f"#12 を見る\n{PR_URL}"), tool_use()]
                + [tool_result(), say("#12 を直した")],
                "block": True,
            },
        }
        for name, case in testCases.items():
            with self.subTest(name):
                path = self.write(case["entries"])
                _, out = run_hook(stop_payload(transcript=path))
                self.assertEqual(bool(out), case["block"])

    def test_reads_large_transcript_from_the_end(self) -> None:
        filler = say("x" * 1000 + " #99")
        entries: list[object] = [prompt("x")] + [filler] * 5000
        entries += [tool_use(), tool_result(), say("#12 を直した")]
        path = self.write(entries)
        self.assertGreater(os.path.getsize(path), 5_000_000)
        # 先頭から読む実装なら、末尾に届く前に上限を使い切る
        text = rlc.final_text_from_transcript(path, max_bytes=64 * 1024)
        self.assertEqual(text, "#12 を直した")
        with mock.patch.object(rlc, "MAX_SCAN_BYTES", 64 * 1024):
            _, out = run_hook(stop_payload(transcript=path))
        self.assertIn("#12", json.loads(out)["reason"])

    def test_reverse_lines_joins_lines_across_chunks(self) -> None:
        lines = [b"a" * 10, b"", b"bb", b"c" * 25, b"d"]
        path = self.dir / "lines.txt"
        path.write_bytes(b"\n".join(lines) + b"\n")
        for chunk in (1, 3, 7, 64):
            with self.subTest(chunk=chunk):
                got = list(rlc.reverse_lines(str(path), chunk_bytes=chunk))
                self.assertEqual(got, [b"d", b"c" * 25, b"bb", b"a" * 10])

    def test_reverse_lines_drops_the_line_cut_by_the_limit(self) -> None:
        path = self.dir / "lines.txt"
        path.write_bytes(b"first-line\nsecond\nthird\n")
        got = list(rlc.reverse_lines(str(path), max_bytes=15, chunk_bytes=4))
        self.assertEqual(got, [b"third", b"second"])

    def test_expands_home_in_transcript_path(self) -> None:
        self.write([prompt("x"), say("#12 を直した")], "home.jsonl")
        with mock.patch.dict(os.environ, {"HOME": str(self.dir)}):
            _, out = run_hook(stop_payload(transcript="~/home.jsonl"))
        self.assertIn("#12", json.loads(out)["reason"])

    def test_fails_open_on_broken_transcript(self) -> None:
        complete = json.dumps(say("#12 を直した")).encode()
        testCases = {
            "書きかけの最後の行": complete + b'\n{"type": "assistant", ',
            "JSON でない行": b"#12 not json\n",
            "UTF-8 でない行": complete + b"\n\x80#12\n",
        }
        for name, content in testCases.items():
            with self.subTest(name):
                path = self.dir / "broken.jsonl"
                path.write_bytes(content)
                self.assertEqual(run_hook(stop_payload(transcript=str(path))), (0, ""))

    def test_fails_open_without_transcript(self) -> None:
        testCases = {
            "ファイルがない": stop_payload(transcript=str(self.dir / "missing.jsonl")),
            "ディレクトリ": stop_payload(transcript=str(self.dir)),
            "空のファイル": stop_payload(transcript=self.write([], "empty.jsonl")),
            "パスがない": stop_payload(),
        }
        for name, stdin in testCases.items():
            with self.subTest(name):
                self.assertEqual(run_hook(stdin), (0, ""))


class HookTest(unittest.TestCase):
    def test_blocks_with_references_in_reason(self) -> None:
        code, out = run_hook(stop_payload(message="完了\n#12 と IX-34 を直した"))
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(set(result), {"decision", "reason"})
        self.assertEqual(result["decision"], "block")
        self.assertEqual(
            result["reason"].splitlines()[:2],
            [
                "答えに、URL のない Issue / PR の番号がある",
                "- 2行目「#12 と IX-34 を直した」の #12 / IX-34",
            ],
        )
        self.assertNotIn("。", result["reason"])

    def test_last_assistant_message_wins_over_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(json.dumps(say("#99 を直した")) + "\n", encoding="utf-8")
            _, out = run_hook(stop_payload(message="直した", transcript=str(path)))
            self.assertEqual(out, "")
            _, out = run_hook(
                stop_payload(message="#12 を直した", transcript=str(path))
            )
            self.assertIn("#12", json.loads(out)["reason"])
            self.assertNotIn("#99", json.loads(out)["reason"])

    def test_stop_hook_active_never_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(json.dumps(say("#12 を直した")) + "\n", encoding="utf-8")
            testCases = {
                "last_assistant_message": stop_payload(message="#12", active=True),
                "transcript": stop_payload(transcript=str(path), active=True),
            }
            for name, stdin in testCases.items():
                with self.subTest(name):
                    self.assertEqual(run_hook(stdin), (0, ""))

    def test_passes_silently(self) -> None:
        cases = {
            "URL のある答え": stop_payload(message=f"#12 ログインを直す\n{PR_URL}"),
            "空の答え": stop_payload(message=""),
            "壊れた JSON": '{"stop_hook_active": false, ',
            "空の入力": "",
            "JSON の配列": "[]",
            "答えが文字列でない": json.dumps({"last_assistant_message": 12}),
        }
        for name, stdin in cases.items():
            with self.subTest(name):
                self.assertEqual(run_hook(stdin), (0, ""))

    def test_passes_on_bad_arguments(self) -> None:
        stdin = stop_payload(message="#12")
        self.assertEqual(run_hook(stdin, "--prefixes"), (0, ""))
        code, out = run_hook(stdin, "--unknown")
        self.assertEqual((code, json.loads(out)["decision"]), (0, "block"))

    def test_passes_when_the_check_fails(self) -> None:
        with mock.patch.object(rlc, "find_unlinked", side_effect=RecursionError):
            self.assertEqual(run_hook(stop_payload(message="#12")), (0, ""))

    def test_runs_as_a_hook_command(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "ref_link_check.py")],
            input=stop_payload(message="#12 を直した"),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(proc.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
