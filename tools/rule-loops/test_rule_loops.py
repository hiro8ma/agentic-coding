"""rule_loops のテスト。

Usage:
    python3 -m unittest discover -s tools/rule-loops
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rule_loops as rl

FIXTURES = HERE / "fixtures"


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = rl.main(list(args))
    return code, out.getvalue()


def by_title(text: str, tools: list[str] | None = None) -> dict[str, rl.Rule]:
    return {rule.title: rule for rule in rl.audit_text(text, "sample.md", tools)}


class WhyAttachmentTest(unittest.TestCase):
    def test_why_attaches_to_the_rule_it_follows(self) -> None:
        testCases = {
            "入れ子の Why は親の箇条書きに付く": {
                "text": "## A\n\n- rule one\n  - **Why:** 2025-01-02, reason\n- rule two\n",
                "want": {
                    "rule one": ("rule", ["2025-01-02"]),
                    "rule two": ("none", []),
                },
            },
            "2段下の Why は一番上の箇条書きに付く": {
                "text": "## A\n\n- rule one\n  - detail\n    - **Why:** 2025-01-02 reason\n",
                "want": {"rule one": ("rule", ["2025-01-02"])},
            },
            "入れ子でない Why の箇条書きは節に付く": {
                "text": "## A\n\n- rule one\n- **Why:** 2025-01-02、理由\n",
                "want": {"A": ("rule", ["2025-01-02"]), "rule one": ("section", [])},
            },
            "段落の Why は節に付く": {
                "text": "## A\n\nrule text\n\n- rule one\n\n**Why:** 2025-01-02、理由\n",
                "want": {"A": ("rule", ["2025-01-02"]), "rule one": ("section", [])},
            },
            "空行なしで続く Why の行は箇条書きに付く": {
                "text": "- rule one\n  **Why:** 2025-01-02 reason\n",
                "want": {"rule one": ("rule", ["2025-01-02"])},
            },
            "空行の後に下げた Why は箇条書きに付く": {
                "text": "- rule one\n\n  **Why:** 2025-01-02 reason\n",
                "want": {"rule one": ("rule", ["2025-01-02"])},
            },
            "英語の Why": {
                "text": "- Do not push on Fridays\n  - Why: On 2025-01-02 a push broke the build\n",
                "want": {"Do not push on Fridays": ("rule", ["2025-01-02"])},
            },
            "日本語の Why": {
                "text": "- 金曜に push しない\n  - **Why:** 2025-01-02、金曜の push でビルドが壊れた\n",
                "want": {"金曜に push しない": ("rule", ["2025-01-02"])},
            },
            "**Why**: と 理由: の形": {
                "text": "- one\n  - **Why**: 2025-01-02 x\n- two\n  - **理由:** 2025-01-03 y\n",
                "want": {
                    "one": ("rule", ["2025-01-02"]),
                    "two": ("rule", ["2025-01-03"]),
                },
            },
            "見出しの前の段落はファイルの説明を見出しにする": {
                "text": "---\ndescription: ノートの扱い\n---\n\n結論だけを書く\n\n**Why:** 2025-01-02 x\n",
                "want": {"ノートの扱い": ("rule", ["2025-01-02"])},
            },
            "コードブロックの中は読まない": {
                "text": "- rule one\n\n```\n- **Why:** 2025-01-02 x\n```\n",
                "want": {"rule one": ("none", [])},
            },
            "リンクだけの箇条書きは数えない": {
                "text": "- [notes](notes.md) — 索引\n- rule one\n",
                "want": {"rule one": ("none", [])},
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                rules = by_title(tc["text"])
                got = {
                    title: (rule.why_scope, rule.dates) for title, rule in rules.items()
                }
                self.assertEqual(got, tc["want"])

    def test_label_after_why_ends_the_why(self) -> None:
        rules = by_title(
            "## A\n\nrule text\n\n**Why:** 2025-01-02 x\n**How to apply:** run the hook\n"
        )
        section = rules["A"]
        self.assertEqual([why.text() for why in section.whys], ["2025-01-02 x"])
        self.assertEqual([e.name for e in section.structural], ["hook"])

    def test_why_lines_keep_their_line_numbers(self) -> None:
        rules = by_title(
            "## A\n\n- rule one\n  - **Why:** 2025-01-02 x\n  - **Why:** 2025-02-03 y\n"
        )
        self.assertEqual([why.line for why in rules["rule one"].whys], [4, 5])


class DateTest(unittest.TestCase):
    def test_extracts_three_forms(self) -> None:
        testCases = {
            "YYYY-MM-DD": {"text": "2025-03-04、x", "want": ["2025-03-04"]},
            "YYYY/M/D": {"text": "2025/7/8、x", "want": ["2025-07-08"]},
            "YYYY/MM/DD": {"text": "2025/07/08 x", "want": ["2025-07-08"]},
            "M/D は前の年付きの日付の年を使う": {
                "text": "2025/7/8、x。7/20、y",
                "want": ["2025-07-08", "2025-07-20"],
            },
            "M/D は後ろの年付きの日付の年も使う": {
                "text": "7/20 と 2025-08-01",
                "want": ["2025-07-20", "2025-08-01"],
            },
            "年付きの日付がなければ年なし": {
                "text": "3/4、x。4/5、y",
                "want": ["--03-04", "--04-05"],
            },
            "英語の文の頭の On M/D": {
                "text": "First on 3/4. On 4/5 again",
                "want": ["--04-05"],
            },
            "文中の M/D は数えない": {
                "text": "2025-10-25、x は10/13に外れていた（8/5 までは通った）",
                "want": ["2025-10-25"],
            },
            "年付きの日付の直後の M/D は文の頭でない": {
                "text": "2025-03-04 3/4",
                "want": ["2025-03-04"],
            },
            "同じ日付は1つに数える": {
                "text": "2025-03-04 と 2025/3/4",
                "want": ["2025-03-04"],
            },
            "ありえない日付は数えない": {
                "text": "2025-13-01 と 2/30 と 0/5",
                "want": [],
            },
            "日のない YYYY-MM は数えない": {"text": "2025-12 に移した", "want": []},
            "パスと版の番号は数えない": {
                "text": "v1/2 と src/3/4 と 1.2/3",
                "want": [],
            },
            "長い数字の一部は数えない": {"text": "RULE-20251029-2025", "want": []},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(rl.extract_dates(tc["text"]), tc["want"])


class RecurrenceTest(unittest.TestCase):
    def test_two_distinct_dates_are_a_recurrence(self) -> None:
        testCases = {
            "日付が1つ": {"why": "  - **Why:** 2025-01-02 x\n", "want": False},
            "同じ日付が2つの Why にある": {
                "why": "  - **Why:** 2025-01-02 x\n  - **Why:** 2025/1/2 y\n",
                "want": False,
            },
            "別の日付が2つの Why にある": {
                "why": "  - **Why:** 2025-01-02 x\n  - **Why:** 2025-02-03 y\n",
                "want": True,
            },
            "1つの Why に別の日付が2つ": {
                "why": "  - **Why:** 2025-01-02 x。2025-02-03 y\n",
                "want": True,
            },
            "Why がない": {"why": "", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                rule = by_title("- rule one\n" + tc["why"])["rule one"]
                self.assertEqual(rule.recurring, tc["want"])

    def test_dates_outside_why_are_not_incidents(self) -> None:
        rule = by_title("- 2025-03-04 から適用する\n  - **Why:** 2025-01-02 x\n")[
            "2025-03-04 から適用する"
        ]
        self.assertEqual(rule.dates, ["2025-01-02"])
        self.assertFalse(rule.recurring)


class StructuralTest(unittest.TestCase):
    def test_structural_keywords(self) -> None:
        testCases = {
            "hook": {"text": "- 本番のコマンドは hook で止める", "want": ["hook"]},
            "hook の event 名": {"text": "- PreToolUse で止める", "want": ["hook"]},
            "和文に続く CI": {"text": "- 全CIが緑になってから出す", "want": ["CI"]},
            "lint の道具": {
                "text": "- 変更したら golangci-lint を流す",
                "want": ["lint"],
            },
            "スクリプトのパス": {
                "text": "- `bin/check.sh` で確かめる",
                "want": ["script"],
            },
            "道具のパス": {"text": "- tools/guard を入れる", "want": ["tool"]},
            "語の一部は数えない": {
                "text": "- Use CIRCLE and webhooks wisely",
                "want": [],
            },
            "Why の中の語は数えない": {
                "text": "- 確認してから出す\n  - **Why:** 2025-01-02、hook が無かった",
                "want": [],
            },
            "入れ子の箇条書きの語も数える": {
                "text": "- 確認してから出す\n  - 止めるのは pre-commit",
                "want": ["hook"],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                (rule,) = rl.audit_text(tc["text"], "sample.md")
                self.assertEqual([e.name for e in rule.structural], tc["want"])

    def test_tool_option_adds_names(self) -> None:
        text = "- deploy-guard で止める\n"
        self.assertEqual(rl.audit_text(text, "sample.md")[0].structural, [])
        (rule,) = rl.audit_text(text, "sample.md", ["deploy-guard"])
        self.assertEqual(
            [(e.name, e.match, e.line) for e in rule.structural],
            [("tool", "deploy-guard", 1)],
        )


class FixKindTest(unittest.TestCase):
    def test_labels_follow_keyword_rules(self) -> None:
        testCases = {
            "毎回": {"text": "- 出す前に毎回確かめる", "want": rl.CRITERION},
            "直前に": {"text": "- 出す直前に聞く", "want": rl.CRITERION},
            "〜だけを〜と読む": {
                "text": "- 対象を書いた返事だけを合意と読む",
                "want": rl.CRITERION,
            },
            "〜と読まない": {
                "text": "- 短い返事を合意と読まない",
                "want": rl.CRITERION,
            },
            "英語の consent": {
                "text": "- Treat a reply as consent only when it names the target",
                "want": rl.CRITERION,
            },
            "禁止": {"text": "- 本番での手動の変更は禁止", "want": rl.ACTION},
            "文末の否定": {"text": "- 下書きを外部に貼らない", "want": rl.ACTION},
            "文末の動詞": {"text": "- タイトルは40字以内にする", "want": rl.ACTION},
            "英語の never": {"text": "- Never force push.", "want": rl.ACTION},
            "どちらの語もない": {
                "text": "- 出力は Markdown の表",
                "want": rl.UNLABELED,
            },
            "Why の中の語は見ない": {
                "text": "- 出力は Markdown の表\n  - **Why:** 2025-01-02、毎回聞かれた",
                "want": rl.UNLABELED,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                (rule,) = rl.audit_text(tc["text"], "sample.md")
                self.assertEqual(rule.fix_kind, tc["want"])


class FixtureReportTest(unittest.TestCase):
    def test_summary_counts(self) -> None:
        code, out = run("--json", str(FIXTURES / "rules.md"), str(FIXTURES / "memory"))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(
            report["summary"],
            {
                "files": 3,
                "rules": 10,
                "item_rules": 7,
                "section_rules": 3,
                "rules_with_why": 6,
                "rules_with_section_why_only": 3,
                "rules_without_why": 1,
                "recurring_rules": 4,
                "recurring_without_structural": 2,
                "sections_with_dates_across_rules": 1,
            },
        )

    def test_recurring_rules_and_evidence(self) -> None:
        _, out = run("--json", str(FIXTURES / "rules.md"))
        rules = json.loads(out)["rules"]
        recurring = {
            (r["line"], r["heading"]): (
                r["incident_dates"],
                [e["name"] for e in r["structural"]],
            )
            for r in rules
            if r["recurring"]
        }
        self.assertEqual(
            recurring,
            {
                (5, "Release"): (["2025-03-04", "2025-05-06"], ["script"]),
                (13, "下書きの扱い"): (["2025-07-08", "2025-07-20"], []),
                (24, "設定の変更"): (["2025-08-09", "2025-09-10"], ["hook"]),
                (36, "Notes"): (["--03-04", "--04-05"], []),
            },
        )

    def test_section_overlap_spans_rules(self) -> None:
        _, out = run("--json", str(FIXTURES / "rules.md"))
        overlaps = json.loads(out)["section_overlaps"]
        self.assertEqual(
            [
                (o["heading"], o["dates"], [r["line"] for r in o["rules"]])
                for o in overlaps
            ],
            [("Release", ["2025-03-04", "2025-05-06", "2025-06-01"], [5, 9])],
        )

    def test_markdown_lists_text_only_recurrences(self) -> None:
        _, out = run(str(FIXTURES / "rules.md"))
        text_only = out.split("## 再発していて、文章だけで守らせているルール")[1].split(
            "##"
        )[0]
        self.assertIn("rules.md:13 下書きの扱い", text_only)
        self.assertIn("rules.md:36 Notes", text_only)
        self.assertNotIn("rules.md:24", text_only)

    def test_directory_reads_matching_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "feedback_a.md").write_text(
                "- rule a\n  - **Why:** 2025-01-02 x\n", encoding="utf-8"
            )
            (root / "notes.txt").write_text("- not read\n", encoding="utf-8")
            (root / ".hidden").mkdir()
            (root / ".hidden" / "b.md").write_text("- hidden rule\n", encoding="utf-8")
            _, out = run("--json", str(root))
            self.assertEqual([r["title"] for r in json.loads(out)["rules"]], ["rule a"])
            _, out = run("--json", "--glob", "other_*.md", str(root))
            self.assertEqual(json.loads(out)["rules"], [])

    def test_missing_path_exits_2(self) -> None:
        code, out = run(str(FIXTURES / "missing.md"))
        self.assertEqual(code, 2)
        self.assertIn("入力を読めない", out)


if __name__ == "__main__":
    unittest.main()
