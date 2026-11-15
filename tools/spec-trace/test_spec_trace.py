"""spec_trace のテスト。

Usage:
    python3 -m unittest discover -s tools/spec-trace
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import itertools
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import spec_trace as st

FIXTURES = HERE / "fixtures"
SHOP = FIXTURES / "shop"
DRIFT = FIXTURES / "drift"
TEMPLATE = (
    HERE.parent.parent
    / "skills"
    / "spec-workflow"
    / "assets"
    / "steering-requirements-template.md"
)
DISCRIMINATING = "test_free_from_tax_included_5000"
NON_DISCRIMINATING = "test_free_for_large_order"
_MODULE_IDS = itertools.count()


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = st.main(list(args))
    return code, out.getvalue()


def ids(text: str, bare: tuple[str, ...] = st.DEFAULT_BARE_PREFIXES) -> list[str]:
    return [rule.id for rule in st.parse_spec(text, "spec.md", bare)]


def refs(text: str, prefixes: set[str]) -> list[tuple[str, int]]:
    pattern = st.reference_pattern(prefixes)
    return [(rid, loc.line) for rid, loc in st.find_references(text, "t", pattern)]


def write_tree(root: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def run_shop_tests(impl: str, test_file: Path = SHOP / "test_shipping.py") -> dict:
    name = f"spec_trace_shop_tests_{next(_MODULE_IDS)}"
    spec = importlib.util.spec_from_file_location(name, test_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TestResult()
    sys.path.insert(0, str(SHOP))
    try:
        with mock.patch.dict(os.environ, {"SHIPPING_IMPL": impl}):
            suite.run(result)
    finally:
        sys.path.remove(str(SHOP))
    return {
        "run": result.testsRun,
        "failures": {test._testMethodName for test, _ in result.failures},
        "errors": {test._testMethodName for test, _ in result.errors},
    }


def load_impl(name: str):
    spec = importlib.util.spec_from_file_location(
        f"spec_trace_{name}", SHOP / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DefinitionTest(unittest.TestCase):
    def test_reads_ids_at_the_start_of_items_and_headings(self) -> None:
        testCases = {
            "角括弧の ID は接頭辞を問わない": {
                "text": "- [SHIP-1] 送料無料\n",
                "want": ["SHIP-1"],
            },
            "AC-1 と区切りのコロン": {"text": "- AC-1: WHEN x\n", "want": ["AC-1"]},
            "AC1 は AC-1 に揃える": {"text": "- AC1 WHEN x\n", "want": ["AC-1"]},
            "AC-01 は AC-1 に揃える": {"text": "- AC-01 WHEN x\n", "want": ["AC-1"]},
            "太字の ID": {"text": "- **AC-2**: WHEN x\n", "want": ["AC-2"]},
            "インラインコードの ID": {"text": "- `AC-3` WHEN x\n", "want": ["AC-3"]},
            "見出しの ID": {"text": "### AC-4 クーポン\n", "want": ["AC-4"]},
            "番号付きの箇条書き": {"text": "1. [RET-2] 返品\n", "want": ["RET-2"]},
            "チェックボックスの後": {"text": "- [ ] AC-5 WHEN x\n", "want": ["AC-5"]},
            "段落の中の ID は読まない": {
                "text": "各条件に`AC-1`などの識別子を付ける\n[SHIP-1] は段落\n",
                "want": [],
            },
            "箇条書きの途中の ID は読まない": {
                "text": "- 送料は SHIP-1 と [SHIP-2] に従う\n",
                "want": [],
            },
            "フェンスの中は読まない": {
                "text": "```text\n- [SHIP-1] x\n```\n- [SHIP-2] y\n",
                "want": ["SHIP-2"],
            },
            "箇条書きの下げたフェンスも読まない": {
                "text": "- a\n  ```\n  - [SHIP-1] x\n  ```\n",
                "want": [],
            },
            "角括弧のない別の接頭辞は読まない": {
                "text": "- UTF-8 で保存する\n- SHIP-1 送料\n- GPT-4 を使う\n",
                "want": [],
            },
            "リンクの文の ID は読まない": {
                "text": "- [RFC-2119](https://example.com/rfc) x\n- [AC-1](requirements.md) y\n",
                "want": [],
            },
            "AC で始まる別の語は読まない": {
                "text": "- ACCESS-1 x\n- AC-1a x\n",
                "want": [],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(ids(tc["text"]), tc["want"])

    def test_prefix_option_reads_bare_ids(self) -> None:
        text = "- **FR-001**: System MUST x\n- SC-001: y\n"
        self.assertEqual(ids(text), [])
        self.assertEqual(ids(text, ("AC", "FR")), ["FR-1"])

    def test_rule_text(self) -> None:
        testCases = {
            "同じ行の文": {
                "text": "- [SHIP-1] 注文の合計が5,000円以上なら送料無料\n",
                "want": "注文の合計が5,000円以上なら送料無料",
            },
            "区切りの記号を除く": {
                "text": "- AC-1： WHEN x\n",
                "want": "WHEN x",
            },
            "見出しの閉じる記号を除く": {
                "text": "## [SHIP-1] 送料 ##\n",
                "want": "送料",
            },
            "見出しだけなら次のフェンスの中を読む": {
                "text": "### AC-1\n\n```text\nWHEN a\nTHE SYSTEM SHALL b\n```\n",
                "want": "WHEN a THE SYSTEM SHALL b",
            },
            "箇条書きだけなら下げた行を読み、次の項目で止める": {
                "text": "- AC-1\n  WHEN a\n  THE SYSTEM SHALL b\n- AC-2 c\n",
                "want": "WHEN a THE SYSTEM SHALL b",
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                rules = st.parse_spec(tc["text"], "spec.md", ("AC",))
                self.assertEqual(rules[0].text, tc["want"])

    def test_unfilled_requirements_template_has_no_rules(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("AC-1", text)
        self.assertEqual(ids(text), [])
        filled = text.replace(
            "## 制約", "- AC-1: WHEN a THE SYSTEM SHALL b\n\n## 制約", 1
        )
        self.assertEqual(ids(filled), ["AC-1"])


class ReferenceTest(unittest.TestCase):
    def test_reference_forms(self) -> None:
        testCases = {
            "コメントの ID": {"text": "# SHIP-1 の境界", "want": [("SHIP-1", 1)]},
            "文字列のテスト名": {
                "text": 'it("SHIP-1 送料無料", () => {})',
                "want": [("SHIP-1", 1)],
            },
            "Python の関数名の ship_1": {
                "text": "def test_ship_1_free():",
                "want": [("SHIP-1", 1)],
            },
            "Go の TestSHIP_1": {
                "text": "func TestSHIP_1(t *testing.T) {",
                "want": [("SHIP-1", 1)],
            },
            "Go の TestAC1": {
                "text": "func TestAC1AddsFee(t *testing.T) {",
                "want": [("AC-1", 1)],
            },
            "Go の t.Run の文字列": {
                "text": 't.Run("AC-2 外す", func(t *testing.T) {',
                "want": [("AC-2", 1)],
            },
            "和文に続く ID": {"text": "# 規則SHIP-1の確認", "want": [("SHIP-1", 1)]},
            "SHIP-10 は SHIP-1 に数えない": {
                "text": "# SHIP-10",
                "want": [("SHIP-10", 1)],
            },
            "前に英字がある ID は数えない": {"text": "XSHIP-1 LatestAC1", "want": []},
            "同じ行の同じ ID は1回": {
                "text": "# SHIP-1 と ship_1",
                "want": [("SHIP-1", 1)],
            },
            "行ごとに数える": {
                "text": "# SHIP-1\n# AC-2\n",
                "want": [("SHIP-1", 1), ("AC-2", 2)],
            },
            "区切りのない小文字は数えない": {
                "text": 'sha = "ac12ef" ship1 = 3',
                "want": [],
            },
            "区切りのない大文字": {
                "text": "def test_SHIP1():",
                "want": [("SHIP-1", 1)],
            },
            "定義されていない接頭辞は探さない": {
                "text": "UTF-8 SHA-256 ISO-8601 IX-34",
                "want": [],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(refs(tc["text"], {"SHIP", "AC"}), tc["want"])

    def test_no_prefixes_means_no_references(self) -> None:
        self.assertIsNone(st.reference_pattern(set()))
        self.assertEqual(st.find_references("SHIP-1", "t", None), [])


class FixtureReportTest(unittest.TestCase):
    def test_shop_counts_ship_1_as_tested(self) -> None:
        code, out = run("--json", str(SHOP))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["summary"]["coverage"], 1.0)
        self.assertEqual(report["summary"]["untested"], 0)
        self.assertEqual(report["summary"]["stale"], 0)
        [rule] = report["rules"]
        self.assertEqual(
            (rule["id"], rule["file"], rule["line"]), ("SHIP-1", "specs/shipping.md", 5)
        )
        self.assertEqual(
            rule["tests"],
            [
                {"file": "test_shipping.py", "line": 20},
                {"file": "test_shipping.py", "line": 25},
            ],
        )

    def test_drift_reports_untested_stale_and_duplicates(self) -> None:
        code, out = run("--json", str(DRIFT))
        self.assertEqual(code, 1)
        report = json.loads(out)
        self.assertEqual(
            report["spec_files"],
            [
                ".steering/20261101-gift-wrap/requirements.md",
                ".steering/20261105-coupon/requirements.md",
                "specs/returns.md",
            ],
        )
        self.assertEqual(report["test_files"], ["gift_wrap_test.go", "returns.test.ts"])
        self.assertEqual(
            report["summary"],
            {
                "rules": 4,
                "tested": 2,
                "coverage": 0.5,
                "untested": 2,
                "stale": 1,
                "duplicated": 1,
            },
        )
        self.assertEqual([r["id"] for r in report["untested"]], ["AC-2", "RET-2"])
        self.assertEqual(
            [(s["id"], s["file"], s["line"]) for s in report["stale"]],
            [("RET-3", "returns.test.ts", 9)],
        )
        [duplicate] = report["duplicates"]
        self.assertEqual(duplicate["id"], "AC-1")
        self.assertEqual(
            [d["file"] for d in duplicate["definitions"]],
            [
                ".steering/20261101-gift-wrap/requirements.md",
                ".steering/20261105-coupon/requirements.md",
            ],
        )
        [coupon] = [r for r in report["rules"] if "coupon" in r["file"]]
        self.assertEqual(
            coupon["text"],
            "WHEN 利用者が期限の切れたクーポンを使う THE SYSTEM SHALL クーポンを使えないと表示する",
        )
        self.assertEqual(coupon["tests"], [{"file": "gift_wrap_test.go", "line": 5}])

    def test_markdown(self) -> None:
        code, out = run(str(DRIFT))
        self.assertEqual(code, 1)
        self.assertIn("規則4件のうち、テストが ID で参照する規則2件（50.0%）", out)
        self.assertIn(
            "| RET-2 | specs/returns.md:7 | セールの商品は返品できない | なし |", out
        )
        self.assertIn("- RET-3 returns.test.ts:9「", out)
        self.assertIn(
            "- AC-1 .steering/20261101-gift-wrap/requirements.md:9"
            " / .steering/20261105-coupon/requirements.md:9",
            out,
        )

    def test_report_only_exits_zero(self) -> None:
        code, _ = run("--report-only", str(DRIFT))
        self.assertEqual(code, 0)


class MutantTest(unittest.TestCase):
    def test_arithmetic_of_the_fixture(self) -> None:
        correct = load_impl("shipping")
        mutant = load_impl("shipping_mutant")
        testCases = {
            "税抜4,545円は税込4,999円": {
                "total": 4545,
                "tax_included": 4999,
                "correct": False,
                "mutant": False,
            },
            "税抜4,546円は税込5,000円": {
                "total": 4546,
                "tax_included": 5000,
                "correct": True,
                "mutant": False,
            },
            "税抜10,000円は税込11,000円": {
                "total": 10000,
                "tax_included": 11000,
                "correct": True,
                "mutant": True,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(correct.tax_included(tc["total"]), tc["tax_included"])
                self.assertEqual(correct.is_free_shipping(tc["total"]), tc["correct"])
                self.assertEqual(mutant.is_free_shipping(tc["total"]), tc["mutant"])

    def test_only_the_discriminating_test_catches_the_mutant(self) -> None:
        self.assertEqual(
            run_shop_tests("shipping"), {"run": 2, "failures": set(), "errors": set()}
        )
        self.assertEqual(
            run_shop_tests("shipping_mutant"),
            {"run": 2, "failures": {DISCRIMINATING}, "errors": set()},
        )

    def test_spec_trace_cannot_tell_a_non_discriminating_test(self) -> None:
        source = (SHOP / "test_shipping.py").read_text(encoding="utf-8")
        start = source.index(f"    def {DISCRIMINATING}")
        end = source.index(f"    def {NON_DISCRIMINATING}")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                {
                    "specs/shipping.md": (SHOP / "specs/shipping.md").read_text(
                        encoding="utf-8"
                    ),
                    "test_shipping.py": source[:start] + source[end:],
                },
            )
            code, out = run("--json", str(root))
            weak = run_shop_tests("shipping_mutant", root / "test_shipping.py")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["coverage"], 1.0)
        self.assertEqual(weak, {"run": 1, "failures": set(), "errors": set()})


class DiscoveryTest(unittest.TestCase):
    def test_default_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                {
                    "specs/a/deep.md": "- [A-1] x\n",
                    ".steering/20261101-x/requirements.md": "- AC-1 x\n",
                    ".steering/20261101-x/design.md": "- AC-9 x\n",
                    "docs/other.md": "- [B-1] x\n",
                    "src/test_a.py": "# A-1 AC-1\n",
                    "src/a_test.go": "// B-1\n",
                    "web/a.spec.ts": "// A-1\n",
                    "node_modules/x/test_x.py": "# A-2\n",
                    ".venv/test_v.py": "# A-3\n",
                    "fixtures/test_f.py": "# A-4\n",
                    "src/helper.py": "# A-5\n",
                },
            )
            report = st.build_report(root, ".", [], [], [])
        self.assertEqual(
            report["spec_files"],
            [".steering/20261101-x/requirements.md", "specs/a/deep.md"],
        )
        self.assertEqual(
            report["test_files"], ["src/a_test.go", "src/test_a.py", "web/a.spec.ts"]
        )
        self.assertEqual(report["stale"], [])
        self.assertEqual(report["summary"]["coverage"], 1.0)

    def test_spec_and_tests_options_replace_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                {
                    "specs/a.md": "- [A-1] x\n",
                    "docs/rules.md": "- [B-1] x\n- [B-2] y\n",
                    "test_a.py": "# A-1 B-1\n",
                    "checks/rules_check.py": "# B-2 B-3\n",
                },
            )
            code, out = run(
                "--json", "--spec", "docs/rules.md", "--tests", "checks/*.py", str(root)
            )
        report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(report["spec_files"], ["docs/rules.md"])
        self.assertEqual(report["test_files"], ["checks/rules_check.py"])
        self.assertEqual([r["id"] for r in report["untested"]], ["B-1"])
        self.assertEqual([s["id"] for s in report["stale"]], ["B-3"])

    def test_prefix_option_finds_references_without_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, {"test_a.py": "# OLD-1\n"})
            self.assertEqual(run(str(root))[0], 0)
            code, out = run("--json", "--prefix", "OLD", str(root))
        self.assertEqual(code, 1)
        self.assertEqual([s["id"] for s in json.loads(out)["stale"]], ["OLD-1"])

    def test_no_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(tmp)
        self.assertEqual(code, 0)
        self.assertIn("仕様のファイルが見つからない", out)
        self.assertIn("規則0件", out)

    def test_input_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            testCases = {
                "ROOT がない": [str(Path(tmp) / "missing")],
                "--spec のパスがない": ["--spec", "missing.md", tmp],
                "--tests が絶対のパス": ["--tests", str(Path(tmp) / "*.py"), tmp],
                "--prefix が小文字": ["--prefix", "ac", tmp],
            }
            for tn, tc in testCases.items():
                with self.subTest(tn):
                    self.assertEqual(run(*tc)[0], 2)
                    self.assertEqual(run("--report-only", *tc)[0], 2)


if __name__ == "__main__":
    unittest.main()
