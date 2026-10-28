"""reviewer_eval のテスト。

Usage:
    python3 -m unittest discover -s tools/reviewer-eval
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shlex
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fake_reviewer
import fixture_repo
import reviewer_eval as rev

FAKE_REVIEWER = shlex.join([sys.executable, str(HERE / "fake_reviewer.py")])


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = rev.main(list(args))
    return code, out.getvalue()


class FixtureRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "repo"
        cls.shas = fixture_repo.build(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_extracts_reverted_changes_newest_first(self) -> None:
        cases, skipped, excluded = rev.extract_cases(self.root, "HEAD", 50, 200_000)
        s = self.shas
        self.assertEqual(
            [(c.revert, c.target, c.subject, c.expected) for c in cases],
            [
                (s["revert_truncate"], s["truncate"], "Truncate tax to whole units", {"app/pricing.py": [(6, 6)]}),
                (s["revert_backoff"], s["backoff"], "Lengthen retry backoff", {"app/client.py": [(9, 9)]}),
                (s["revert_discount"], s["discount"], "Add member discount", {"app/pricing.py": [(12, 16)]}),
            ],
        )
        self.assertEqual(skipped, Counter(no_trailer=1, revert_reverted=1, target_is_revert=1))
        self.assertTrue({s["rename"], s["revert_rename"], s["reland_rename"], s["no_trailer"]} <= excluded)
        self.assertNotIn(s["add_report"], excluded)

    def test_review_input_is_the_original_diff(self) -> None:
        cases, _, _ = rev.extract_cases(self.root, "HEAD", 50, 200_000)
        backoff = next(c for c in cases if c.target == self.shas["backoff"])
        self.assertIn("+        time.sleep(30)", backoff.diff)
        self.assertIn("+Retries back off for 30 seconds.", backoff.diff)
        self.assertNotIn("This reverts commit", backoff.diff)

    def test_limits_drop_cases(self) -> None:
        testCases = {
            "max cases keeps the newest": {
                "max_cases": 1,
                "max_diff_bytes": 200_000,
                "want_targets": ["truncate"],
                "want_skipped": {"over_limit": 2},
            },
            "large diffs are skipped": {
                "max_cases": 50,
                "max_diff_bytes": 1,
                "want_targets": [],
                "want_skipped": {"diff_too_large": 3},
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                cases, skipped, _ = rev.extract_cases(self.root, "HEAD", tc["max_cases"], tc["max_diff_bytes"])
                self.assertEqual([c.target for c in cases], [self.shas[t] for t in tc["want_targets"]])
                for reason, count in tc["want_skipped"].items():
                    self.assertEqual(skipped[reason], count)

    def test_rev_range_limits_the_search(self) -> None:
        cases, _, _ = rev.extract_cases(self.root, f"{self.shas['backoff']}..HEAD", 50, 200_000)
        self.assertEqual([c.target for c in cases], [self.shas["truncate"], self.shas["backoff"]])

    def test_clean_cases_skip_reverted_recent_and_retouched(self) -> None:
        testCases = {
            "window of three keeps commits nobody touched afterwards": {
                "limit": 10,
                "window": 3,
                "want": ["add_usage", "add_report"],
            },
            "limit keeps the newest": {"limit": 1, "window": 3, "want": ["add_usage"]},
            "short window lets recent and retouched commits in": {
                "limit": 2,
                "window": 1,
                "want": ["tune_config", "add_config"],
            },
            "window longer than the history finds nothing": {"limit": 10, "window": 20, "want": []},
            "zero disables clean cases": {"limit": 0, "window": 3, "want": []},
        }
        _, _, excluded = rev.extract_cases(self.root, "HEAD", 50, 200_000)
        for tn, tc in testCases.items():
            with self.subTest(tn):
                clean = rev.find_clean(
                    self.root,
                    "HEAD",
                    limit=tc["limit"],
                    window=tc["window"],
                    excluded=excluded,
                    max_diff_bytes=200_000,
                )
                self.assertEqual([c.target for c in clean], [self.shas[label] for label in tc["want"]])
                self.assertTrue(all(c.kind == "clean" and not c.expected for c in clean))

    def test_scores_fake_reviewer_on_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            keywords = Path(tmp) / "keywords.json"
            keywords.write_text(
                json.dumps({self.shas[label]: words for label, words in fixture_repo.KEYWORDS.items()}),
                encoding="utf-8",
            )
            json_path = Path(tmp) / "report.json"
            code, out = run(
                "--repo",
                str(self.root),
                "--reviewer",
                FAKE_REVIEWER,
                "--clean-window",
                "3",
                "--keywords",
                str(keywords),
                "--json-out",
                str(json_path),
            )
            report = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0, out)
        summary = report["summary"]
        del summary["skipped"]
        self.assertEqual(
            summary,
            {
                "cases": 3,
                "caught": 2,
                "recall": 0.6667,
                "keyword_cases": 3,
                "strict_caught": 1,
                "strict_recall": 0.3333,
                "clean_cases": 2,
                "findings_per_clean_case": 0.5,
                "findings_per_case": 1.0,
                "noise_share": 0.3333,
                "errors": 0,
                "tolerance": 3,
            },
        )
        status = {c["target"]: c["status"] for c in report["cases"]}
        self.assertEqual(
            status,
            {
                self.shas["truncate"]: "missed",
                self.shas["backoff"]: "caught",
                self.shas["discount"]: "caught",
                self.shas["add_usage"]: "flagged",
                self.shas["add_report"]: "quiet",
            },
        )
        backoff = next(c for c in report["cases"] if c["target"] == self.shas["backoff"])
        self.assertEqual(
            [(f["file"], f["hit"], f["strict"]) for f in backoff["findings"]],
            [("README.md", False, False), ("app/client.py", True, True)],
        )
        self.assertIn("recall 0.67  strict_recall 0.33  findings_per_clean_case 0.50", out)
        self.assertNotIn('"summary"', out)

    def test_unknown_keyword_key_is_warned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            keywords = Path(tmp) / "keywords.json"
            keywords.write_text(json.dumps({"0000000": ["x"]}), encoding="utf-8")
            code, out = run("--repo", str(self.root), "--dry-run", "--keywords", str(keywords))
        self.assertEqual(code, 0, out)
        self.assertIn("--keywords の 0000000 に合う revert のケースがない", out)

    def test_reviewer_failure_is_an_error_not_a_miss(self) -> None:
        failing = shlex.join([sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(3)"])
        code, out = run("--repo", str(self.root), "--reviewer", failing, "--clean-cases", "0")
        self.assertEqual(code, 1, out)
        self.assertIn("終了コード3（boom）", out)
        self.assertIn("cases 0  caught 0  keyword_cases 0  strict_caught 0  clean_cases 0  errors 3", out)
        self.assertIn('"recall": null', out)

    def test_dry_run_does_not_need_a_reviewer(self) -> None:
        code, out = run("--repo", str(self.root), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("app/client.py:9", out)
        self.assertIn("app/pricing.py:12-16", out)


class ArgumentTest(unittest.TestCase):
    def test_reviewer_or_mode_is_required(self) -> None:
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stderr(io.StringIO()):
            rev.main(["--repo", "."])
        self.assertEqual(ctx.exception.code, 2)

    def test_not_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run("--repo", tmp, "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("git の履歴を読めない", out)

    def test_claude_command_is_built_only_from_the_flag(self) -> None:
        claude = rev.reviewer_command(argparse.Namespace(claude=True, reviewer=None))
        self.assertEqual(claude[:2], ["claude", "-p"])
        self.assertEqual(claude[-2:], ["--tools", ""])
        custom = rev.reviewer_command(argparse.Namespace(claude=False, reviewer=FAKE_REVIEWER))
        self.assertEqual(custom, [sys.executable, str(HERE / "fake_reviewer.py")])


class ParseTest(unittest.TestCase):
    def test_reverted_lines(self) -> None:
        header = "diff --git a/app/x.py b/app/x.py\nindex 1..2 100644\n--- a/app/x.py\n+++ b/app/x.py\n"
        testCases = {
            "changed lines use the old side": {
                "diff": header + "@@ -10,2 +10,2 @@\n-a\n-b\n+c\n+d\n",
                "want": {"app/x.py": [(10, 11)]},
            },
            "missing count means one line": {
                "diff": header + "@@ -7 +7 @@\n-a\n+b\n",
                "want": {"app/x.py": [(7, 7)]},
            },
            "pure insertion anchors on the neighbours": {
                "diff": header + "@@ -4,0 +5,2 @@\n+a\n+b\n",
                "want": {"app/x.py": [(4, 5)]},
            },
            "insertion at the top starts at line one": {
                "diff": header + "@@ -0,0 +1 @@\n+a\n",
                "want": {"app/x.py": [(1, 1)]},
            },
            "several hunks in one file": {
                "diff": header + "@@ -3 +3 @@\n-a\n+b\n@@ -20,3 +20,0 @@\n-c\n-d\n-e\n",
                "want": {"app/x.py": [(3, 3), (20, 22)]},
            },
            "file restored by the revert uses the restored lines": {
                "diff": "diff --git a/old.py b/old.py\nnew file mode 100644\n--- /dev/null\n+++ b/old.py\n"
                "@@ -0,0 +1,3 @@\n+a\n+b\n+c\n",
                "want": {"old.py": [(1, 3)]},
            },
            "file removed by the revert": {
                "diff": "diff --git a/new.py b/new.py\ndeleted file mode 100644\n--- a/new.py\n+++ /dev/null\n"
                "@@ -1,2 +0,0 @@\n-a\n-b\n",
                "want": {"new.py": [(1, 2)]},
            },
            "binary file has no ranges": {
                "diff": "diff --git a/logo.png b/logo.png\nindex 1..2 100644\n"
                "Binary files a/logo.png and b/logo.png differ\n",
                "want": {"logo.png": []},
            },
            "path with spaces": {
                "diff": "diff --git a/my dir/x.py b/my dir/x.py\n--- a/my dir/x.py\n+++ b/my dir/x.py\n"
                "@@ -2 +2 @@\n-a\n+b\n",
                "want": {"my dir/x.py": [(2, 2)]},
            },
            "removed line that looks like a header stays content": {
                "diff": header + "@@ -5,2 +5,0 @@\n--- a/other.py\n-x\n",
                "want": {"app/x.py": [(5, 6)]},
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(rev.reverted_lines(tc["diff"]), tc["want"])

    def test_parse_findings(self) -> None:
        testCases = {
            "json lines": {
                "output": '{"file": "a.py", "line": 3, "summary": "x"}\n{"file": "b.py", "line": "7"}\n',
                "want": [("a.py", 3, "x"), ("b.py", 7, "")],
                "want_invalid": 0,
            },
            "prose and fences around findings": {
                "output": 'Here are the findings:\n```json\n{"file": "a.py", "line": 3, "summary": "x"}\n```\n',
                "want": [("a.py", 3, "x")],
                "want_invalid": 1,
            },
            "objects without a usable line": {
                "output": '{"file": "a.py"}\n{"file": "a.py", "line": true}\n[1, 2]\n{"line": 3}\n',
                "want": [],
                "want_invalid": 4,
            },
            "no output": {"output": "", "want": [], "want_invalid": 0},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings, invalid = rev.parse_findings(tc["output"])
                self.assertEqual([(f.file, f.line, f.summary) for f in findings], tc["want"])
                self.assertEqual(invalid, tc["want_invalid"])

    def test_is_hit(self) -> None:
        expected = {"app/x.py": [(10, 12)], "logo.png": []}
        testCases = {
            "inside the range": {"file": "app/x.py", "line": 11, "want": True},
            "at the lower tolerance edge": {"file": "app/x.py", "line": 7, "want": True},
            "just below the tolerance": {"file": "app/x.py", "line": 6, "want": False},
            "at the upper tolerance edge": {"file": "app/x.py", "line": 15, "want": True},
            "just above the tolerance": {"file": "app/x.py", "line": 16, "want": False},
            "other file": {"file": "app/y.py", "line": 11, "want": False},
            "diff prefix is ignored": {"file": "b/app/x.py", "line": 11, "want": True},
            "relative prefix is ignored": {"file": "./app/x.py", "line": 11, "want": True},
            "file without ranges matches any line": {"file": "logo.png", "line": 999, "want": True},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                finding = rev.Finding(file=tc["file"], line=tc["line"], summary="")
                self.assertEqual(rev.is_hit(finding, expected, 3), tc["want"])

    def test_is_strict_hit(self) -> None:
        testCases = {
            "hit with a keyword in the summary": {"hit": True, "summary": "Sleep blocks the worker", "want": True},
            "hit about a different issue": {"hit": True, "summary": "TODO is left", "want": False},
            "keyword outside the reverted lines": {"hit": False, "summary": "sleep is long", "want": False},
            "case without keywords": {"hit": True, "summary": "sleep is long", "keywords": [], "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                finding = rev.Finding(file="a.py", line=1, summary=tc["summary"], hit=tc["hit"])
                self.assertEqual(rev.is_strict_hit(finding, tc.get("keywords", ["sleep", "backoff"])), tc["want"])

    def test_load_keywords(self) -> None:
        testCases = {
            "list of words": {"data": {"abcdef1": ["rate", " "]}, "want": {"abcdef1": ["rate"]}},
            "single word": {"data": {"abcdef1": "rate"}, "want": {"abcdef1": ["rate"]}},
            "short key": {"data": {"abc": ["rate"]}, "want": None},
            "non hex key": {"data": {"discount": ["rate"]}, "want": None},
            "non string word": {"data": {"abcdef1": [1]}, "want": None},
            "not an object": {"data": [["abcdef1", "rate"]], "want": None},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "keywords.json"
                path.write_text(json.dumps(tc["data"]), encoding="utf-8")
                if tc["want"] is None:
                    with self.assertRaises((ValueError, TypeError)):
                        rev.load_keywords(str(path))
                else:
                    self.assertEqual(rev.load_keywords(str(path)), tc["want"])


class FakeReviewerTest(unittest.TestCase):
    def test_reports_new_side_line_numbers(self) -> None:
        diff = (
            "diff --git a/app/x.py b/app/x.py\n--- a/app/x.py\n+++ b/app/x.py\n"
            "@@ -3,4 +3,4 @@\n keep\n-old()\n+time.sleep(5)\n keep\n+# TODO later\n"
            "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-eval(x)\n"
        )
        self.assertEqual(
            [(f["file"], f["line"]) for f in fake_reviewer.review(diff)],
            [("app/x.py", 4), ("app/x.py", 6)],
        )


if __name__ == "__main__":
    unittest.main()
