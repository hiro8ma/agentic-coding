"""deadline_brief_check のテスト。

Usage:
    python3 -m unittest discover -s tools/deadline-brief-check
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import deadline_brief_check as dbc

FIXTURES = HERE / "fixtures"
PR_BODY = FIXTURES / "pr_body.md"
REQUEST_DRAFT = FIXTURES / "request_draft.md"


def run(*args: str, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = dbc.main(list(args))
    return code, out.getvalue(), err.getvalue()


def present(text: str) -> dict[str, bool]:
    return {kind: bool(evidence) for kind, evidence in dbc.judge(text).items()}


def only(kind: str, text: str) -> bool:
    return present(text)[kind]


class DeadlineMentionTest(unittest.TestCase):
    def test_forms_that_mark_a_deadline(self) -> None:
        testCases = {
            "年月日をスラッシュで書いた日付と時刻": {
                "line": "2026/11/11 17:00 までに見てほしい",
                "want": ("2026/11/11", "17:00", "までに"),
            },
            "年月日をハイフンで書いた日付": {
                "line": "2026-12-05 に出す",
                "want": ("2026-12-05",),
            },
            "月と日だけの日付": {"line": "12/5の展示", "want": ("12/5",)},
            "年月日を漢字で書いた日付": {
                "line": "2026年12月5日に出す",
                "want": ("2026年12月5日",),
            },
            "月末と上旬": {"line": "12月末か1月上旬", "want": ("12月末", "1月上旬")},
            "時の形の時刻": {"line": "17時に見る", "want": ("17時",)},
            "曜日": {"line": "金曜の朝に見る", "want": ("金曜",)},
            "今週中": {"line": "今週中に見る", "want": ("今週中",)},
            "和文に続く EOD": {"line": "EODまでに見る", "want": ("EOD", "までに")},
            "締切の語の揺れ": {
                "line": "締め切りと〆切と締切りと期日と納期",
                "want": ("締め切り", "〆切", "締切り", "期日", "納期"),
            },
            "見出しの Deadline": {"line": "## Review Deadline", "want": ("Deadline",)},
            "期限を表す due": {"line": "due Friday", "want": ("due",)},
            "英語の月の名前": {"line": "by Dec 5", "want": ("Dec 5",)},
            "全角の数字と斜線は半角に直して見る": {
                "line": "１２／５の展示",
                "want": ("12/5",),
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                masked = dbc.mask([tc["line"]])[0]
                self.assertEqual(dbc.deadline_matches(masked), tc["want"])

    def test_forms_that_are_not_a_deadline(self) -> None:
        testCases = {
            "理由を表す due to": "due to the outage",
            "長さを表す1時間": "1時間かかる",
            "画像の比の16:9": "16:9 の画像",
            "パスの中の数字": "data/1/2 を読む",
            "見出しに日付の無い節": "## 手順",
            "コードの中の日付": "`2026/11/11` は例",
            "URL の中の日付": "https://example.com/2026/11/11/post を見る",
            "HTML のタグの中の日付": '<a href="x?d=12/5">開く</a>',
            "HTML のコメントの中の締切": "<!-- 締切 12/5 -->",
        }
        for tn, line in testCases.items():
            with self.subTest(tn):
                masked = dbc.mask([line])[0]
                self.assertEqual(dbc.deadline_matches(masked), ())


class MaskTest(unittest.TestCase):
    def test_masked_parts(self) -> None:
        testCases = {
            "フェンスの中の行は空にする": {
                "lines": ["```", "締切 12/5", "```", "後ろ"],
                "want": ["", "", "", "後ろ"],
            },
            "チルダのフェンスも閉じるまで空にする": {
                "lines": ["~~~", "締切", "```", "~~~", "後ろ"],
                "want": ["", "", "", "", "後ろ"],
            },
            "複数行の HTML のコメントは閉じるまで消す": {
                "lines": ["前<!-- 締切", "12/5", "-->後ろ"],
                "want": ["前", "", " 後ろ"],
            },
            "URL の後ろの和文は残す": {
                "lines": ["https://example.com/a）の前に入れる"],
                "want": [" ）の前に入れる"],
            },
            "行の中で閉じるバッククォートの並びはフェンスにしない": {
                "lines": ["```a``` の後に12/5"],
                "want": ["  の後に12/5"],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(dbc.mask(tc["lines"]), tc["want"])


class FirmnessTest(unittest.TestCase):
    def test_firmness(self) -> None:
        testCases = {
            "動かせない期限": {"text": "動かせない期限です", "want": True},
            "遅くとも": {"text": "遅くとも12/5には", "want": True},
            "最終の締切": {"text": "最終締切は12/5", "want": True},
            "目安": {"text": "12/5は目安です", "want": True},
            "仮の期限": {"text": "仮の期限として12/5", "want": True},
            "できれば": {"text": "できれば12/5までに", "want": True},
            "急ぎではない": {"text": "急ぎではない", "want": True},
            "至急": {"text": "至急お願いします", "want": True},
            "早いほどよい": {"text": "早いほどよい", "want": True},
            "未定": {"text": "未定", "want": True},
            "英語の no rush": {"text": "no rush, Friday is fine", "want": True},
            "英語の hard deadline": {"text": "this is a hard deadline", "want": True},
            "英語の ASAP は和文に続いても見る": {"text": "ASAPで", "want": True},
            "仮説は仮に数えない": {"text": "仮説を確かめる", "want": False},
            "助かるは固さに数えない": {"text": "見てもらえると助かる", "want": False},
            "日付だけ": {"text": "2026/11/11 17:00", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(only(dbc.FIRMNESS, tc["text"]), tc["want"])


class ImpactTest(unittest.TestCase):
    def test_impact(self) -> None:
        testCases = {
            "間に合わないときの結果": {
                "text": "間に合わないと展示に出せない",
                "want": True,
            },
            "遅れたときの結果": {
                "text": "遅れると公開が後ろ倒しになる",
                "want": True,
            },
            "待っている間に止まっていること": {
                "text": "ローカルの起動がブロックされている",
                "want": True,
            },
            "影響が無いと書く": {"text": "遅れても影響はない", "want": True},
            "ほかの作業がこれを待つ": {"text": "CI もこれ待ち", "want": True},
            "英語の otherwise": {
                "text": "otherwise the demo shows old data",
                "want": True,
            },
            "間に合わないときの連絡は影響に数えない": {
                "text": "間に合わない場合は連絡してください",
                "want": False,
            },
            "理由だけ": {
                "text": "2026/11/11 17:00（公開の前に入れるため）",
                "want": False,
            },
            "固さだけ": {"text": "急ぎではない", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(only(dbc.IMPACT, tc["text"]), tc["want"])


class InterimReportTest(unittest.TestCase):
    def test_interim_report(self) -> None:
        testCases = {
            "間に合わなさそうなら連絡": {
                "text": "間に合わなさそうなら前日までに連絡してください",
                "want": True,
            },
            "延長は相談": {
                "text": "延長が要るときは相談してください",
                "want": True,
            },
            "遅れそうなら一声": {
                "text": "遅れそうなら Slack で一声かけてほしい",
                "want": True,
            },
            "途中経過の共有": {"text": "水曜に途中経過を共有してほしい", "want": True},
            "英語の let me know": {
                "text": "let me know if you can't make it",
                "want": True,
            },
            "知らせる語が無い": {
                "text": "間に合わないと展示に出せない",
                "want": False,
            },
            "間に合わない見込みが無い": {
                "text": "URL を共有する前に入れたい",
                "want": False,
            },
            "見込みと知らせる語が別の文": {
                "text": "遅れそうです。結果は共有します。",
                "want": False,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(only(dbc.INTERIM, tc["text"]), tc["want"])


class ReasonTest(unittest.TestCase):
    def test_reason(self) -> None:
        testCases = {
            "ため": {"text": "公開に入れるため", "want": True},
            "ので": {"text": "CI が落ちているので急ぎ", "want": True},
            "動詞に続くから": {"text": "翌日に使うから。", "want": True},
            "より前": {"text": "公開より前に入れたい", "want": True},
            "より先": {"text": "別の PR より先に入れたい", "want": True},
            "その先": {"text": "その先は未確認", "want": False},
            "動詞に続く前に": {"text": "A/B を始める前に入れたい", "want": True},
            "の前": {"text": "定例の前", "want": True},
            "の後に": {"text": "確認の後に入れる", "want": True},
            "てから": {"text": "判断が出てからでよい", "want": True},
            "に間に合わせる": {"text": "展示に間に合わせたい", "want": True},
            "英語の before": {"text": "before the demo", "want": True},
            "名前に": {"text": "名前に日付を入れる", "want": False},
            "午前中": {"text": "午前中に見る", "want": False},
            "最後に": {"text": "最後に確認する", "want": False},
            "文の頭の後で": {"text": "後で見てほしい", "want": False},
            "あらためて": {"text": "あらためて見てほしい", "want": False},
            "名詞に続くから": {"text": "ここから、順に見る", "want": False},
            "のでは": {"text": "間に合うのではないか", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(only(dbc.REASON, tc["text"]), tc["want"])


class ContextTest(unittest.TestCase):
    def test_scope_decides_where_to_look(self) -> None:
        text = REQUEST_DRAFT.read_text(encoding="utf-8")
        testCases = {
            "節の範囲は見出しの無い文面の全体を1つに見る": {
                "scope": dbc.SECTION,
                "want": [((1, 7), {dbc.FIRMNESS: True, dbc.REASON: True})],
            },
            "段落の範囲は空行で分け、締切のある段落だけを返す": {
                "scope": dbc.PARAGRAPH,
                "want": [
                    ((3, 4), {dbc.FIRMNESS: False, dbc.REASON: False}),
                    ((6, 7), {dbc.FIRMNESS: True, dbc.REASON: True}),
                ],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings = dbc.analyze(text, scope=tc["scope"])
                got = [
                    (
                        (f.start, f.end),
                        {kind: bool(f.info[kind]) for kind in tc["want"][0][1]},
                    )
                    for f in findings or []
                ]
                self.assertEqual(got, tc["want"])

    def test_section_option(self) -> None:
        testCases = {
            "見出しの大文字と空白の違いは同じに見る": {
                "text": "# 前\n\n##  review   deadline  \n\n12/5\n\n## 次\n\n12/6",
                "want": [(3, 5)],
            },
            "下の階層の見出しは節に含め、節の範囲では分ける": {
                "text": "## Review Deadline\n12/5\n### 補足\n12/6のため\n## 次\n12/7",
                "want": [(1, 2), (3, 4)],
            },
            "同じ名前の節が2つあれば両方を見る": {
                "text": "## Review Deadline\n12/5\n## 次\n12/6\n## Review Deadline\n12/7",
                "want": [(1, 2), (5, 6)],
            },
            "見出しの末尾のコロンと閉じる記号は外す": {
                "text": "## Review Deadline: ##\n12/5",
                "want": [(1, 2)],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings = dbc.analyze(tc["text"], section="Review Deadline")
                self.assertEqual([(f.start, f.end) for f in findings or []], tc["want"])

    def test_missing_section_returns_none(self) -> None:
        self.assertIsNone(dbc.analyze("## 概要\n12/5", section="Review Deadline"))

    def test_heading_is_a_mention_only_in_section_scope(self) -> None:
        text = "## Review Deadline\n\n急ぎではない\n"
        testCases = {
            "節の範囲では見出しの Deadline を締切に数える": {
                "scope": dbc.SECTION,
                "want": [[1]],
            },
            "段落の範囲では見出しを読まない": {"scope": dbc.PARAGRAPH, "want": []},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings = dbc.analyze(text, "Review Deadline", tc["scope"]) or []
                got = [[m.line for m in f.mentions] for f in findings]
                self.assertEqual(got, tc["want"])

    def test_paragraph_scope_misses_a_reason_in_the_next_paragraph(self) -> None:
        text = "## Review Deadline\n\n2026/10/30 17:00\n\n- 11/6の更新の前に入れたい\n"
        testCases = {
            "節の範囲では次の段落の理由も見る": {"scope": dbc.SECTION, "want": [True]},
            "段落の範囲では段落ごとに見る": {
                "scope": dbc.PARAGRAPH,
                "want": [False, True],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings = dbc.analyze(text, "Review Deadline", tc["scope"]) or []
                got = [bool(f.info[dbc.REASON]) for f in findings]
                self.assertEqual(got, tc["want"])

    def test_pr_body_sections(self) -> None:
        text = PR_BODY.read_text(encoding="utf-8")
        testCases = {
            "全文では日付のある節を全部返し、コードの中の日付は数えない": {
                "section": None,
                "want": [
                    ("Debug List", [15]),
                    ("Review Deadline", [17, 19, 22]),
                ],
            },
            "節を指すとその節だけを返す": {
                "section": "Review Deadline",
                "want": [("Review Deadline", [17, 19, 22])],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                findings = dbc.analyze(text, tc["section"]) or []
                got = [(f.heading, [m.line for m in f.mentions]) for f in findings]
                self.assertEqual(got, tc["want"])

    def test_pr_body_review_deadline_has_all_four(self) -> None:
        text = PR_BODY.read_text(encoding="utf-8")
        findings = dbc.analyze(text, "Review Deadline") or []
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].missing(), [])


class CliTest(unittest.TestCase):
    def test_exit_code_and_output(self) -> None:
        testCases = {
            "4つがそろうと0": {
                "args": (str(PR_BODY), "--section", "Review Deadline"),
                "stdin": "",
                "code": 0,
                "out": "締切のある節 1件（4つがそろうのは1件）",
            },
            "欠けがあれば1": {
                "args": (str(REQUEST_DRAFT), "--scope", "paragraph"),
                "stdin": "",
                "code": 1,
                "out": "締切のある段落 2件（4つがそろうのは0件）",
            },
            "標準入力を読む": {
                "args": ("--section", "Review Deadline"),
                "stdin": "## Review Deadline\n\n2026/11/11 17:00\n",
                "code": 1,
                "out": "固さ 0/1 / 影響 0/1 / 途中の報告 0/1 / 理由 0/1",
            },
            "締切が無ければ0": {
                "args": ("-",),
                "stdin": "手順を直した\n",
                "code": 0,
                "out": "締切の記述は見つからなかった",
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                code, out, _ = run(*tc["args"], stdin=tc["stdin"])
                self.assertEqual(code, tc["code"])
                self.assertIn(tc["out"], out)

    def test_input_errors_exit_2(self) -> None:
        testCases = {
            "節が無い": {
                "args": ("--section", "Review Deadline"),
                "err": "見出し「Review Deadline」が無い",
            },
            "ファイルが無い": {
                "args": (str(FIXTURES / "missing.md"),),
                "err": "入力を読めない",
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                code, out, err = run(*tc["args"], stdin="## 概要\n12/5\n")
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(tc["err"], err)

    def test_json_shape(self) -> None:
        code, out, _ = run(
            "--json",
            "--section",
            "Review Deadline",
            stdin="## Review Deadline\n\n2026/11/11 17:00（公開の前に入れるため、急ぎ）\n",
        )
        report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(
            report["summary"],
            {
                "contexts": 1,
                "complete": 0,
                dbc.FIRMNESS: 1,
                dbc.IMPACT: 0,
                dbc.INTERIM: 0,
                dbc.REASON: 1,
            },
        )
        context = report["contexts"][0]
        self.assertEqual(
            [m["line"] for m in context["mentions"]],
            [1, 3],
        )
        self.assertEqual(context["missing"], [dbc.IMPACT, dbc.INTERIM])
        self.assertEqual(
            context["info"][dbc.FIRMNESS]["evidence"],
            [{"rule": "急ぎ", "match": "急ぎ"}],
        )


if __name__ == "__main__":
    unittest.main()
