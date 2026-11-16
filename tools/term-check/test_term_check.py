"""term_check のテスト。

Usage:
    python3 -m unittest discover -s tools/term-check
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import term_check as tc

FIXTURES = HERE / "fixtures"
GLOSSARY = FIXTURES / "glossary.md"
INCOMPLETE = FIXTURES / "incomplete_glossary.md"
TEXTS = FIXTURES / "texts"
COMMIT_MESSAGE = TEXTS / "commit_message.txt"
NOTES = TEXTS / "notes.md"

RULES = tc.load_glossary(str(GLOSSARY))
COMPOUNDS = (
    "仕様",
    "模様",
    "同様",
    "多様",
    "様子",
    "様式",
    "様々",
    "一様",
    "様相",
    "異様",
)
HEADER = "| 使う語 | 使わない語 | 除く語 | 対象 | 使う場面 | 期待する判断 |\n|---|---|---|---|---|---|\n"


def run(*args: str, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = tc.main(list(args))
    return code, out.getvalue(), err.getvalue()


def hits(text: str, target: str, rules: list[tc.Rule] | None = None) -> list[tuple]:
    found = tc.find_hits(text, RULES if rules is None else rules, target)
    return [(hit.line, hit.column, hit.word) for hit in found]


def messages(command: str, base: Path = HERE) -> list[tuple[str, str, str]]:
    return [(m.target, m.source, m.text) for m in tc.extract_messages(command, base)]


def payload(command: object, cwd: str | None = None) -> str:
    data: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        data["cwd"] = cwd
    return json.dumps(data)


def hook(stdin: str, *args: str) -> tuple[int, str, str]:
    return run("hook", "--glossary", str(GLOSSARY), *args, stdin=stdin)


def parsed(test: unittest.TestCase, text: str) -> list[tc.Rule]:
    try:
        return tc.parse_glossary(text)
    except tc.GlossaryError as error:
        test.fail(f"読めるはずの用語集を読めなかった: {error}")


def decided(test: unittest.TestCase, out: str) -> dict:
    test.assertNotEqual(out, "", "hook が何も出さなかった")
    return json.loads(out)


class MatchTest(unittest.TestCase):
    def test_except_compounds_of_the_example_glossary(self) -> None:
        for compound in COMPOUNDS:
            with self.subTest(f"{compound}は当たらず、同じ行の社名の後ろの様は当たる"):
                self.assertEqual(hits(f"{compound}を直す", tc.COMMIT), [])
                self.assertEqual(
                    hits(f"架空商事様の{compound}", tc.COMMIT), [(1, 5, "様")]
                )

    def test_hits(self) -> None:
        testCases = {
            "社名の後ろの様は commit で当たる": {
                "text": "架空商事様に送る",
                "target": tc.COMMIT,
                "want": [(1, 5, "様")],
            },
            "社名の後ろの様は pr で当たる": {
                "text": "架空商事様に送る",
                "target": tc.PR,
                "want": [(1, 5, "様")],
            },
            "社名の後ろの様は docs では当たらない": {
                "text": "架空商事様に送る",
                "target": tc.DOCS,
                "want": [],
            },
            "対象が all の規則は docs でも当たる": {
                "text": "オーダーを受ける",
                "target": tc.DOCS,
                "want": [(1, 1, "オーダー")],
            },
            "対象が docs / pr の規則は commit では当たらない": {
                "text": "見積もり書を送る",
                "target": tc.COMMIT,
                "want": [],
            },
            "対象が docs / pr の規則は docs で当たる": {
                "text": "見積もり書を送る",
                "target": tc.DOCS,
                "want": [(1, 1, "見積もり書")],
            },
            "除く語のオーダーメイドは当たらない": {
                "text": "オーダーメイドの封筒",
                "target": tc.DOCS,
                "want": [],
            },
            "除く語の後ろの単独のオーダーは当たる": {
                "text": "オーダーメイドとオーダー",
                "target": tc.DOCS,
                "want": [(1, 9, "オーダー")],
            },
            "使う語の中の使わない語は当たらない": {
                "text": "サーバーとサーバ",
                "target": tc.DOCS,
                "want": [(1, 6, "サーバ")],
            },
            "仕様の直後の様は仕様の一部でないので当たる": {
                "text": "仕様様",
                "target": tc.COMMIT,
                "want": [(1, 3, "様")],
            },
            "同じ行の2つの様は2つ当たる": {
                "text": "架空商事様と架空商事様",
                "target": tc.COMMIT,
                "want": [(1, 5, "様"), (1, 11, "様")],
            },
            "見出しの行も当たる": {
                "text": "# 架空商事様",
                "target": tc.PR,
                "want": [(1, 7, "様")],
            },
            "行の番号を数える": {
                "text": "直す\n\n架空商事様",
                "target": tc.COMMIT,
                "want": [(3, 5, "様")],
            },
            "同じ行の当たりを字の順に並べる": {
                "text": "オーダーは架空商事様から",
                "target": tc.COMMIT,
                "want": [(1, 1, "オーダー"), (1, 10, "様")],
            },
            "英字の語は大文字と小文字を区別する": {
                "text": "Master と master",
                "target": tc.DOCS,
                "want": [(1, 10, "master")],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hits(tcase["text"], tcase["target"]), tcase["want"])

    def test_skips_code_and_urls(self) -> None:
        testCases = {
            "バッククォートのフェンスの中は見ない": {
                "text": "```\n架空商事様\n```\n架空商事様",
                "want": [(4, 5, "様")],
            },
            "チルダのフェンスの中は見ない": {
                "text": "~~~text\n架空商事様\n~~~\n架空商事様",
                "want": [(4, 5, "様")],
            },
            "閉じないフェンスは最後まで見ない": {
                "text": "```\n架空商事様\n\n架空商事様",
                "want": [],
            },
            "短いフェンスでは長いフェンスを閉じない": {
                "text": "````\n```\n架空商事様\n````\n架空商事様",
                "want": [(5, 5, "様")],
            },
            "インラインコードの中は見ず、その後ろは見る": {
                "text": "`master` と master",
                "want": [(1, 12, "master")],
            },
            "2つのバッククォートのインラインコードの中は見ない": {
                "text": "``a ` master`` と master",
                "want": [(1, 18, "master")],
            },
            "URL の中は見ず、その後ろは見る": {
                "text": "https://example.com/master/docs と master",
                "want": [(1, 35, "master")],
            },
            "http の URL の中も見ない": {
                "text": "http://example.com/?b=master",
                "want": [],
            },
            "リンクの文は見て、リンクの先は見ない": {
                "text": "[master](https://example.com/master)",
                "want": [(1, 2, "master")],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hits(tcase["text"], tc.COMMIT), tcase["want"])

    def test_longer_word_of_one_row_covers_the_shorter(self) -> None:
        rules = tc.parse_glossary(
            HEADER + "| 発注書 | オーダー / オーダー書 | | all | 場面 | 判断 |\n"
        )
        testCases = {
            "長い語に当たれば、中の短い語は数えない": {
                "text": "オーダー書を送る",
                "want": [(1, 1, "オーダー書")],
            },
            "短い語だけなら短い語が当たる": {
                "text": "オーダーを送る",
                "want": [(1, 1, "オーダー")],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hits(tcase["text"], tc.DOCS, rules), tcase["want"])

    def test_rows_that_ban_the_same_word_report_separately(self) -> None:
        rules = tc.parse_glossary(
            HEADER
            + "| 発注 | オーダー | | all | 場面 | 判断 |\n"
            + "| 依頼 | オーダー | | docs | 場面 | 判断 |\n"
        )
        found = tc.find_hits("オーダー", rules, tc.DOCS)
        self.assertEqual(
            [(hit.column, hit.rule.line) for hit in found], [(1, 3), (1, 4)]
        )

    def test_compound_with_the_word_twice(self) -> None:
        rules = tc.parse_glossary(
            HEADER + "| さん | ちゃん | ちゃんちゃんこ | all | 場面 | 判断 |\n"
        )
        testCases = {
            "除く語の中の1つ目の語は当たらない": {"text": "ちゃんちゃんこ", "want": []},
            "除く語の中の2つ目の語も当たらない": {
                "text": "赤いちゃんちゃんこ",
                "want": [],
            },
            "除く語の外の語は当たる": {
                "text": "ちゃんちゃんこを着た猫田ちゃん",
                "want": [(1, 13, "ちゃん")],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hits(tcase["text"], tc.DOCS, rules), tcase["want"])

    def test_excerpt(self) -> None:
        testCases = {
            "短い行はそのまま出す": {
                "text": "架空商事様に送る",
                "want": "架空商事様に送る",
            },
            "長い行は当たりの前後20字で切る": {
                "text": "あ" * 30 + "架空商事様" + "い" * 30,
                "want": "…" + "あ" * 16 + "架空商事様" + "い" * 20 + "…",
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                found = tc.find_hits(tcase["text"], RULES, tc.COMMIT)
                self.assertEqual([hit.excerpt for hit in found], [tcase["want"]])


class GlossaryTest(unittest.TestCase):
    def test_example_glossary(self) -> None:
        first = RULES[0]
        self.assertEqual(
            (first.line, first.use, first.avoid, first.excepts, first.targets),
            (8, (), ("様",), COMPOUNDS, (tc.COMMIT, tc.PR)),
        )
        self.assertTrue(first.scene and first.judgment)
        self.assertEqual(
            [(rule.line, rule.use, rule.avoid, rule.targets) for rule in RULES[1:]],
            [
                (9, ("発注",), ("オーダー",), (tc.ALL,)),
                (10, ("見積書",), ("見積もり書", "御見積書"), (tc.DOCS, tc.PR)),
                (11, ("サーバー",), ("サーバ",), (tc.ALL,)),
                (12, ("main",), ("master",), (tc.ALL,)),
            ],
        )

    def test_reading_rows(self) -> None:
        testCases = {
            "見出しの名前で列を読み、列の順は問わない": {
                "text": "| 対象 | 使わない語 | 使う語 | 期待する判断 | 除く語 | 使う場面 |\n"
                "|:--|:-:|--:|---|---|---|\n"
                "| docs | オーダー | 発注 | 判断 | オーダーメイド | 場面 |\n",
                "want": [(3, ("発注",), ("オーダー",), ("オーダーメイド",), ("docs",))],
            },
            "フェンスの中の表は読まない": {
                "text": "```\n"
                + HEADER
                + "| 例 | 例え | | all | 場面 | 判断 |\n```\n\n"
                + HEADER
                + "| 発注 | オーダー | | all | 場面 | 判断 |\n",
                "want": [(9, ("発注",), ("オーダー",), (), ("all",))],
            },
            "使う語と使わない語の列が無い表は読まない": {
                "text": "| 名前 | 中身 |\n|---|---|\n| a | b |\n\n"
                + HEADER
                + "| 発注 | オーダー | | all | 場面 | 判断 |\n",
                "want": [(7, ("発注",), ("オーダー",), (), ("all",))],
            },
            "表の後ろの段落で表を閉じる": {
                "text": HEADER
                + "| 発注 | オーダー | | all | 場面 | 判断 |\n段落\n| a |\n",
                "want": [(3, ("発注",), ("オーダー",), (), ("all",))],
            },
            "全部のセルが空の行は飛ばす": {
                "text": HEADER + "| | | | | | |\n| 発注 | | | all | 場面 | 判断 |\n",
                "want": [(4, ("発注",), (), (), ("all",))],
            },
            "セルの中の \\| を縦棒として読む": {
                "text": HEADER + "| 発注 | a\\|b | | all | 場面 | 判断 |\n",
                "want": [(3, ("発注",), ("a|b",), (), ("all",))],
            },
            "語は前後に空白のある斜線だけで分ける": {
                "text": HEADER + "| 該当なし | N/A / n/a | | docs | 場面 | 判断 |\n",
                "want": [(3, ("該当なし",), ("N/A", "n/a"), (), ("docs",))],
            },
            "対象は空白の無い斜線でも分ける": {
                "text": HEADER + "| 発注 | オーダー | | commit/pr | 場面 | 判断 |\n",
                "want": [(3, ("発注",), ("オーダー",), (), ("commit", "pr"))],
            },
            "同じ語を2回書いても1回にする": {
                "text": HEADER
                + "| 発注 | オーダー / オーダー | | all | 場面 | 判断 |\n",
                "want": [(3, ("発注",), ("オーダー",), (), ("all",))],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                rules = parsed(self, tcase["text"])
                got = [(r.line, r.use, r.avoid, r.excepts, r.targets) for r in rules]
                self.assertEqual(got, tcase["want"])

    def test_malformed_glossary(self) -> None:
        testCases = {
            "表が無い": {
                "text": "# 用語集\n\n本文だけ\n",
                "want": "「使う語」か「使わない語」の列を持つ表が無い",
            },
            "区切りの行の無い表は表に数えない": {
                "text": "| 使う語 | 使わない語 |\n| 発注 | オーダー |\n",
                "want": "「使う語」か「使わない語」の列を持つ表が無い",
            },
            "見出しに期待する判断の列が無い": {
                "text": "| 使う語 | 使わない語 | 除く語 | 対象 | 使う場面 |\n|---|---|---|---|---|\n",
                "want": "1行目: 表の見出しに 期待する判断 が無い",
            },
            "列の数が見出しと違う": {
                "text": HEADER + "| 発注 | オーダー | all | 場面 | 判断 |\n",
                "want": "3行目: 列が5個ある（見出しは6個）",
            },
            "対象が空": {
                "text": HEADER + "| 発注 | オーダー | | | 場面 | 判断 |\n",
                "want": "3行目: 対象が空",
            },
            "対象が決まった値のどれでもない": {
                "text": HEADER
                + "| 発注 | オーダー | | commit / slack | 場面 | 判断 |\n",
                "want": "3行目: 対象の「slack」は commit / pr / docs / all のどれでもない",
            },
            "使う語も使わない語も無い": {
                "text": HEADER + "| | | | all | 場面 | 判断 |\n",
                "want": "3行目: 使う語も使わない語も無い",
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                try:
                    tc.parse_glossary(tcase["text"])
                except Exception as error:  # noqa: BLE001
                    got = (type(error).__name__, str(error))
                else:
                    got = None
                self.assertEqual(got, ("GlossaryError", tcase["want"]))

    def test_completeness(self) -> None:
        testCases = {
            "使う場面と期待する判断がそろえば0": {
                "path": GLOSSARY,
                "code": 0,
                "out": "# term-check glossary\n\n"
                "規則5件 / 使う場面と期待する判断がそろう5件 / 欠け0件\n",
            },
            "欠けた行を並べて1": {
                "path": INCOMPLETE,
                "code": 1,
                "out": "# term-check glossary\n\n"
                "規則4件 / 使う場面と期待する判断がそろう1件 / 欠け3件\n\n"
                "## 欠けた規則\n\n"
                "- 6行目 使う語「受注」\n"
                "  - 欠け 使う場面\n"
                "- 7行目 使う語「納品書」 / 使わない語「納品伝票」\n"
                "  - 欠け 期待する判断\n"
                "- 8行目 使う語「検収」 / 使わない語「受け入れ確認」\n"
                "  - 欠け 使う場面 / 期待する判断\n",
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                code, out, err = run("glossary", "--glossary", str(tcase["path"]))
                self.assertEqual((code, out, err), (tcase["code"], tcase["out"], ""))

    def test_lint_runs_on_an_incomplete_glossary(self) -> None:
        code, out, _ = run(
            "lint",
            "--glossary",
            str(INCOMPLETE),
            "--target",
            "docs",
            "-",
            stdin="オーダーと納品伝票",
        )
        self.assertEqual(code, 1)
        self.assertIn("当たり2件", out)

    def test_glossary_with_bom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "bom.md")
            path.write_text(
                "\ufeff" + HEADER + "| 発注 | オーダー | | all | 場面 | 判断 |\n",
                encoding="utf-8",
            )
            text = path.read_text(encoding="utf-8")
            try:
                rules = tc.load_glossary(str(path))
            except tc.GlossaryError as error:
                self.fail(f"BOM の付いた用語集を読めなかった: {error}")
        self.assertEqual(text[0], "\ufeff")
        self.assertEqual([(r.line, r.avoid) for r in rules], [(3, ("オーダー",))])


class ExtractTest(unittest.TestCase):
    def test_messages(self) -> None:
        C = tc.COMMIT
        P = tc.PR
        M = "コミットメッセージ"
        testCases = {
            "-m の値を読む": {
                "command": 'git commit -m "架空商事様"',
                "want": [(C, M, "架空商事様")],
            },
            '-m に続けた値を読む（-m"..."）': {
                "command": 'git commit -m"架空商事様"',
                "want": [(C, M, "架空商事様")],
            },
            "--message= の値を読む": {
                "command": "git commit --message=架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "--message の次の値を読む": {
                "command": "git commit --message 架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "まとめた短いフラグの -am を読む": {
                "command": "git commit -am 架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "複数の -m は空行でつなぐ": {
                "command": "git commit -m 件名 -m 本文",
                "want": [(C, M, "件名\n\n本文")],
            },
            "$(cat <<'EOF') のヒアドキュメントを読む": {
                "command": "git commit -m \"$(cat <<'EOF'\n件名\n\n架空商事様\nEOF\n)\"",
                "want": [(C, M, "件名\n\n架空商事様")],
            },
            "区切りを引用符で囲まないヒアドキュメントも読む": {
                "command": 'git commit -m "$(cat <<EOF\n架空商事様\nEOF\n)"',
                "want": [(C, M, "架空商事様")],
            },
            "$(echo) の出力を読む": {
                "command": 'git commit -m "$(echo 架空商事様)"',
                "want": [(C, M, "架空商事様")],
            },
            "読めない $( ) は空白にして前後を読む": {
                "command": 'git commit -m "架空商事$(date)様"',
                "want": [(C, M, "架空商事 様")],
            },
            "-F - はヒアドキュメントを読む": {
                "command": "git commit -F - <<'EOF'\n架空商事様\nEOF",
                "want": [(C, "コミットメッセージ（標準入力）", "架空商事様")],
            },
            "--file=- はヒアストリングを読む": {
                "command": 'git commit --file=- <<< "架空商事様"',
                "want": [(C, "コミットメッセージ（標準入力）", "架空商事様")],
            },
            "git -C と -c の後ろの commit を読む": {
                "command": "git -C . -c user.name=x commit -m 架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "--author の値はメッセージに数えない": {
                "command": 'git commit --author "架空商事様 <a@example.com>" -m ok',
                "want": [(C, M, "ok")],
            },
            "commit の -t は --template で、メッセージに数えない": {
                "command": "git commit -t 架空商事様.txt -m ok",
                "want": [(C, M, "ok")],
            },
            "&& と ; でつないだコマンドも読む": {
                "command": "git add . && git commit -m 架空商事様; gh pr create --title t --body b",
                "want": [
                    (C, M, "架空商事様"),
                    (P, "PR のタイトル", "t"),
                    (P, "PR の本文", "b"),
                ],
            },
            "改行と || でつないだコマンドも読む": {
                "command": "git status\ngit commit -m a || gh pr edit 12 --body b",
                "want": [(C, M, "a"), (P, "PR の本文", "b")],
            },
            "gh pr create の短いフラグを読む": {
                "command": "gh pr create -t 件名 -b 本文 -d",
                "want": [(P, "PR のタイトル", "件名"), (P, "PR の本文", "本文")],
            },
            "gh pr new は gh pr create の別名": {
                "command": "gh pr new --title=件名",
                "want": [(P, "PR のタイトル", "件名")],
            },
            "gh pr edit のタイトルを読む": {
                "command": "gh pr edit 12 --title 件名",
                "want": [(P, "PR のタイトル", "件名")],
            },
            "gh pr の前の -R を飛ばす": {
                "command": "gh pr -R octo/app create --body 本文",
                "want": [(P, "PR の本文", "本文")],
            },
            "gh pr の本文の $(cat <<'EOF') を読む": {
                "command": "gh pr create --title t --body \"$(cat <<'EOF'\n## TL;DR\n架空商事様\nEOF\n)\"",
                "want": [
                    (P, "PR のタイトル", "t"),
                    (P, "PR の本文", "## TL;DR\n架空商事様"),
                ],
            },
            "--body-file - はヒアドキュメントを読む": {
                "command": "gh pr create -t t --body-file - <<'EOF'\n架空商事様\nEOF",
                "want": [
                    (P, "PR のタイトル", "t"),
                    (P, "PR の本文（標準入力）", "架空商事様"),
                ],
            },
            "bash -c の文字列の中も読む": {
                "command": "bash -c 'git commit -m 架空商事様'",
                "want": [(C, M, "架空商事様")],
            },
            "eval の文字列の中も読む": {
                "command": "eval git commit -m 架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "env や変数の代入を前に付けても読む": {
                "command": "GIT_AUTHOR_NAME=x env git commit -m 架空商事様",
                "want": [(C, M, "架空商事様")],
            },
            "サブシェルと $( ) の中の git commit も読む": {
                "command": "(git commit -m a) && echo $(git commit -m b)",
                "want": [(C, M, "a"), (C, M, "b")],
            },
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                self.assertEqual(messages(tcase["command"]), tcase["want"])

    def test_commands_without_messages(self) -> None:
        testCases = {
            "echo の引数の git commit": ('echo "git commit -m 架空商事様"', []),
            "コメントの git commit": ("git status # git commit -m 架空商事様", []),
            "メッセージを付けない git commit": ("git commit", []),
            "--amend --no-edit": ("git commit --amend --no-edit", []),
            "-C で前のコミットのメッセージを使う": ("git commit -C HEAD", []),
            "-C に続けた前のコミットの名前をメッセージに数えない": (
                "git commit -Cmain",
                [],
            ),
            "-t に続けたテンプレートの名前をメッセージに数えない": (
                "git commit -tmy.txt",
                [],
            ),
            "git commit 以外の -m": ("git merge -m 架空商事様 topic", []),
            "git log の -m": ("git log -m", []),
            "gh pr view": ("gh pr view 12", []),
            "gh pr comment の本文": ("gh pr comment 12 --body 架空商事様", []),
            "gh issue create の本文": ("gh issue create --title 架空商事様", []),
            "引用符で囲んだヒアドキュメントの中の git commit": (
                "cat <<'EOF'\ngit commit -m 架空商事様\nEOF",
                [],
            ),
            "文書に書くヒアドキュメントは、つないだ git commit の文に数えない": (
                "cat > note.md <<'EOF' && git commit -m docs\n架空商事様\nEOF",
                [(tc.COMMIT, "コミットメッセージ", "docs")],
            ),
        }
        for tn, (command, want) in testCases.items():
            with self.subTest(tn):
                self.assertEqual(messages(command), want)

    def test_message_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sub").mkdir()
            (root / "msg.txt").write_text("架空商事様\n", encoding="utf-8")
            (root / "sub" / "msg.txt").write_text(
                "サブの架空商事様\n", encoding="utf-8"
            )
            (root / "bom.txt").write_text("﻿先頭の架空商事様", encoding="utf-8")
            (root / "latin.txt").write_bytes(b"\xff\xfe\x00broken")
            absolute = root / "msg.txt"
            file_label = "コミットメッセージ（ファイル msg.txt）"
            testCases = {
                "-F の相対パスは cwd から読む": {
                    "command": "git commit -F msg.txt",
                    "want": [(tc.COMMIT, file_label, "架空商事様\n")],
                },
                "--file= の絶対パスを読む": {
                    "command": f"git commit --file={absolute}",
                    "want": [
                        (
                            tc.COMMIT,
                            f"コミットメッセージ（ファイル {absolute}）",
                            "架空商事様\n",
                        )
                    ],
                },
                "git -C の後ろの -F は -C の場所から読む": {
                    "command": "git -C sub commit -F msg.txt",
                    "want": [(tc.COMMIT, file_label, "サブの架空商事様\n")],
                },
                "cd の後ろの -F は cd の先から読む": {
                    "command": "cd sub && git commit -F msg.txt",
                    "want": [(tc.COMMIT, file_label, "サブの架空商事様\n")],
                },
                "先頭の BOM を外す": {
                    "command": "git commit -F bom.txt",
                    "want": [
                        (
                            tc.COMMIT,
                            "コミットメッセージ（ファイル bom.txt）",
                            "先頭の架空商事様",
                        )
                    ],
                },
                "gh pr create の --body-file を読む": {
                    "command": "gh pr create --body-file msg.txt",
                    "want": [(tc.PR, "PR の本文（ファイル msg.txt）", "架空商事様\n")],
                },
                "gh pr edit の -F を読む": {
                    "command": "gh pr edit 12 -F msg.txt",
                    "want": [(tc.PR, "PR の本文（ファイル msg.txt）", "架空商事様\n")],
                },
                "無いファイルは読まない": {
                    "command": "git commit -F missing.txt",
                    "want": [],
                },
                "UTF-8 で読めないファイルは読まない": {
                    "command": "git commit -F latin.txt",
                    "want": [],
                },
                "標準入力の無い -F - は読まない": {
                    "command": "git commit -F -",
                    "want": [],
                },
            }
            for tn, tcase in testCases.items():
                with self.subTest(tn):
                    self.assertEqual(messages(tcase["command"], root), tcase["want"])


class HookTest(unittest.TestCase):
    def test_denies_with_hits_in_the_reason(self) -> None:
        command = (
            "git commit -m \"$(cat <<'EOF'\nfeat: 架空商事様の仕様を直す\nEOF\n)\""
        )
        code, out, err = hook(payload(command))
        self.assertEqual((code, err), (0, ""))
        result = decided(self, out)
        self.assertEqual(set(result), {"hookSpecificOutput"})
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], "deny")
        rule = RULES[0]
        self.assertEqual(
            specific["permissionDecisionReason"].splitlines(),
            [
                "用語集で使わない語を含む",
                "- コミットメッセージの1行目「様」→ 使う語なし（用語集の8行目）",
                "  - 行「feat: 架空商事様の仕様を直す」",
                f"  - 使う場面 {rule.scene}",
                f"  - 期待する判断 {rule.judgment}",
                "用語集の期待する判断に沿って書き直してから、もう一度実行する",
            ],
        )

    def test_codex_also_shows_the_reason_to_the_user(self) -> None:
        code, out, _ = hook(
            payload("gh pr create --title 架空商事様のオーダー"), "--codex"
        )
        self.assertEqual(code, 0)
        result = decided(self, out)
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("systemMessage", result)
        self.assertEqual(result["systemMessage"], specific["permissionDecisionReason"])
        self.assertIn("- PR のタイトルの1行目「様」", result["systemMessage"])
        self.assertIn(
            "- PR のタイトルの1行目「オーダー」→ 使う語「発注」",
            result["systemMessage"],
        )

    def test_reads_message_files_from_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "msg.txt").write_text("架空商事様\n", encoding="utf-8")
            _, out, _ = hook(payload("git commit -F msg.txt", cwd=directory))
        reason = decided(self, out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("- コミットメッセージ（ファイル msg.txt）の1行目「様」", reason)

    def test_reads_command_given_as_argv(self) -> None:
        _, out, _ = hook(payload(["bash", "-lc", "git commit -m 架空商事様"]))
        self.assertEqual(
            decided(self, out)["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_passes_silently(self) -> None:
        testCases = {
            "使わない語の無いコミット": payload(
                "git commit -m 'feat: 架空商事の仕様を直す'"
            ),
            "docs に書くヒアドキュメントとつないだコミット": payload(
                "cat > note.md <<'EOF' && git commit -m docs\n架空商事様\nEOF"
            ),
            "メッセージを付けないコミット": payload("git commit --amend --no-edit"),
            "echo の引数": payload("echo \"git commit -m '架空商事様'\""),
            "無いファイルの -F": payload("git commit -F missing.txt", cwd=str(HERE)),
            "壊れた JSON": '{"tool_name": "Bash", ',
            "空の入力": "",
            "JSON の配列": "[]",
            "Bash 以外のツール": json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"command": "git commit -m 架空商事様"},
                }
            ),
            "command が無い": json.dumps({"tool_name": "Bash", "tool_input": {}}),
            "command が文字列でない": payload(12),
        }
        for tn, stdin in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hook(stdin), (0, "", ""))

    def test_glossary_errors_pass_with_a_note(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory, "broken.md")
            broken.write_text("# 表の無い用語集\n", encoding="utf-8")
            testCases = {
                "無い用語集": str(Path(directory, "missing.md")),
                "表の無い用語集": str(broken),
            }
            for tn, glossary in testCases.items():
                with self.subTest(tn):
                    code, out, err = run(
                        "hook",
                        "--glossary",
                        glossary,
                        stdin=payload("git commit -m 架空商事様"),
                    )
                    self.assertEqual((code, out), (0, ""))
                    self.assertIn("用語集を読めないので、確かめずに通す", err)

    def test_glossary_is_not_read_without_messages(self) -> None:
        code, out, err = run(
            "hook", "--glossary", "missing.md", stdin=payload("git status")
        )
        self.assertEqual((code, out, err), (0, "", ""))

    def test_argument_errors_pass(self) -> None:
        testCases = {
            "--glossary が無い": ["hook"],
            "知らない引数": ["hook", "--glossary", str(GLOSSARY), "--unknown"],
        }
        for tn, args in testCases.items():
            with self.subTest(tn):
                try:
                    code, out, _ = run(*args, stdin=payload("git commit -m 架空商事様"))
                except SystemExit as error:
                    self.fail(f"hook が終了コード{error.code}で終わった")
                self.assertEqual((code, out), (0, ""))

    def test_passes_when_the_parser_fails(self) -> None:
        with mock.patch.object(tc, "extract_messages", side_effect=RecursionError):
            try:
                got = hook(payload("git commit -m 架空商事様"))
            except RecursionError:
                self.fail("解析の失敗が hook の外に出た")
        self.assertEqual(got, (0, "", ""))

    def test_runs_as_a_hook_command(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(HERE / "term_check.py"),
                "hook",
                "--glossary",
                str(GLOSSARY),
            ],
            input=payload("git commit -m 架空商事様"),
            capture_output=True,
            text=True,
            check=True,
        )
        result = decided(self, proc.stdout)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")


class CliTest(unittest.TestCase):
    def lint(self, *args: str, stdin: str = "") -> tuple[int, str, str]:
        return run("lint", "--glossary", str(GLOSSARY), *args, stdin=stdin)

    def test_exit_codes(self) -> None:
        testCases = {
            "当たりがあれば1": {"args": ["--target", "commit", "-"], "code": 1},
            "--report-only なら当たりがあっても0": {
                "args": ["--target", "commit", "--report-only", "-"],
                "code": 0,
            },
            "当たりが無ければ0": {"args": ["--target", "docs", "-"], "code": 0},
        }
        for tn, tcase in testCases.items():
            with self.subTest(tn):
                code, _, err = self.lint(*tcase["args"], stdin="架空商事様に送る")
                self.assertEqual((code, err), (tcase["code"], ""))

    def test_input_with_bom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "bom.md")
            path.write_text("\ufeff架空商事様に送る\n", encoding="utf-8")
            code, out, _ = self.lint("--target", "commit", "--json", str(path))
        hit = json.loads(out)["files"][0]["hits"][0]
        self.assertEqual((code, hit["line"], hit["column"]), (1, 1, 5))

    def test_input_errors_exit_2_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            latin = Path(directory, "latin.md")
            latin.write_bytes(b"\xff\xfe\x00broken")
            broken = Path(directory, "broken.md")
            broken.write_text(
                HEADER + "| 発注 | オーダー | | slack | 場面 | 判断 |\n",
                encoding="utf-8",
            )
            testCases = {
                "無いパス": {
                    "args": [
                        "lint",
                        "--glossary",
                        str(GLOSSARY),
                        "--target",
                        "docs",
                        str(Path(directory, "none.md")),
                    ],
                    "err": "パスが無い",
                },
                "UTF-8 で読めないファイル": {
                    "args": [
                        "lint",
                        "--glossary",
                        str(GLOSSARY),
                        "--target",
                        "docs",
                        str(latin),
                    ],
                    "err": "読めない",
                },
                "--report-only でも2": {
                    "args": [
                        "lint",
                        "--glossary",
                        str(GLOSSARY),
                        "--target",
                        "docs",
                        "--report-only",
                        str(latin),
                    ],
                    "err": "読めない",
                },
                "lint で壊れた用語集": {
                    "args": [
                        "lint",
                        "--glossary",
                        str(broken),
                        "--target",
                        "docs",
                        str(NOTES),
                    ],
                    "err": "用語集: 3行目: 対象の「slack」",
                },
                "lint で無い用語集": {
                    "args": [
                        "lint",
                        "--glossary",
                        str(Path(directory, "none.md")),
                        "--target",
                        "docs",
                        str(NOTES),
                    ],
                    "err": "用語集: 読めない",
                },
                "glossary で壊れた用語集": {
                    "args": ["glossary", "--glossary", str(broken)],
                    "err": "用語集: 3行目: 対象の「slack」",
                },
            }
            for tn, tcase in testCases.items():
                with self.subTest(tn):
                    code, out, err = run(*tcase["args"])
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn(tcase["err"], err)

    def test_argument_errors_exit_2(self) -> None:
        testCases = {
            "パスが無い": ["lint", "--glossary", str(GLOSSARY), "--target", "docs"],
            "出し先が無い": ["lint", "--glossary", str(GLOSSARY), str(NOTES)],
            "知らない出し先": [
                "lint",
                "--glossary",
                str(GLOSSARY),
                "--target",
                "all",
                str(NOTES),
            ],
            "コマンドが無い": [],
        }
        for tn, args in testCases.items():
            with self.subTest(tn):
                with self.assertRaises(SystemExit) as raised:
                    run(*args)
                self.assertEqual(raised.exception.code, 2)

    def test_files_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sub").mkdir()
            (root / ".hidden").mkdir()
            (root / "a.md").write_text("架空商事様\n", encoding="utf-8")
            (root / "b.txt").write_text("架空商事様\n", encoding="utf-8")
            (root / "sub" / "c.md").write_text("ok\n架空商事様\n", encoding="utf-8")
            (root / ".hidden" / "d.md").write_text("架空商事様\n", encoding="utf-8")
            a = str(root / "a.md")
            testCases = {
                "ディレクトリは下の階層の *.md を名前の順に読み、隠しディレクトリは読まない": {
                    "args": [str(root)],
                    "want": [(a, [1]), (str(root / "sub" / "c.md"), [2])],
                },
                "直に渡したファイルは拡張子を問わず読む": {
                    "args": [str(root / "b.txt")],
                    "want": [(str(root / "b.txt"), [1])],
                },
                "同じファイルを2回渡しても1回だけ読む": {
                    "args": [a, a, str(root / "sub" / ".." / "a.md")],
                    "want": [(a, [1])],
                },
            }
            for tn, tcase in testCases.items():
                with self.subTest(tn):
                    code, out, _ = self.lint(
                        "--target", "commit", "--json", *tcase["args"]
                    )
                    data = json.loads(out)
                    got = [
                        (f["path"], [hit["line"] for hit in f["hits"]])
                        for f in data["files"]
                    ]
                    self.assertEqual((code, got), (1, tcase["want"]))

    def test_markdown_output(self) -> None:
        code, out, _ = self.lint("--target", "commit", str(COMMIT_MESSAGE), str(NOTES))
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(
            lines[:3],
            ["# term-check", "", "出し先 commit / 読んだファイル2件 / 当たり6件"],
        )
        self.assertEqual(
            [line for line in lines if line.startswith(("## ", "- "))],
            [
                f"## {COMMIT_MESSAGE}",
                "- 1行目11字目「様」→ 使う語なし（用語集の8行目）",
                "- 1行目13字目「オーダー」→ 使う語「発注」（用語集の9行目）",
                "- 4行目1字目「サーバ」→ 使う語「サーバー」（用語集の11行目）",
                "- 4行目9字目「master」→ 使う語「main」（用語集の12行目）",
                f"## {NOTES}",
                "- 1行目7字目「様」→ 使う語なし（用語集の8行目）",
                "- 3行目7字目「様」→ 使う語なし（用語集の8行目）",
            ],
        )
        self.assertIn("  - 行「サーバの設定は master に入れてから直す」", lines)
        self.assertIn("  - 期待する判断 長音の付いたサーバーに揃える", lines)

    def test_markdown_output_without_hits(self) -> None:
        code, out, _ = self.lint("--target", "docs", str(NOTES), "-", stdin="ok")
        self.assertEqual(code, 1)
        self.assertNotIn("## -", out)
        code, out, _ = self.lint("--target", "docs", "-", stdin="ok")
        self.assertEqual(
            (code, out),
            (0, "# term-check\n\n出し先 docs / 読んだファイル1件 / 当たり0件\n"),
        )

    def test_json_shape(self) -> None:
        code, out, _ = self.lint("--target", "docs", "--json", str(NOTES))
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(
            data["summary"],
            {"glossary": str(GLOSSARY), "target": "docs", "files": 1, "hits": 1},
        )
        self.assertEqual(
            data["files"],
            [
                {
                    "path": str(NOTES),
                    "hits": [
                        {
                            "line": 3,
                            "column": 22,
                            "word": "見積もり書",
                            "excerpt": "…架空商事様から、オーダーメイドの封筒の見積もり書を頼まれた",
                            "rule": {
                                "line": 10,
                                "use": ["見積書"],
                                "avoid": ["見積もり書", "御見積書"],
                                "except": [],
                                "targets": ["docs", "pr"],
                                "scene": "架空商事に出す金額の書類を指すとき",
                                "judgment": "書類の名前は見積書に揃え、金額を見積もる作業は見積もりと書く",
                            },
                        }
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
