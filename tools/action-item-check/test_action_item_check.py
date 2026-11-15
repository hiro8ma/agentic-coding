"""action_item_check のテスト。

Usage:
    python3 -m unittest discover -s tools/action-item-check
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import action_item_check as aic

dbc = aic.dbc

FIXTURES = HERE / "fixtures"
MINUTES = FIXTURES / "minutes"
WEEKLY = MINUTES / "weekly.md"
NOTION = MINUTES / "notion_export.md"
COLUMNS = FIXTURES / "columns.md"


def run(*args: str, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("sys.stdin", io.StringIO(stdin)))
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        code = aic.main(list(args))
    return code, out.getvalue(), err.getvalue()


def spans(text: str) -> list[tuple[int, int, str]]:
    return [(item.start, item.end, item.source) for item in aic.analyze(text)]


def present(item_text: str) -> dict[str, bool]:
    items = aic.analyze("## Next Action\n\n- " + item_text + "\n")
    if len(items) != 1:
        raise AssertionError(f"項目が1件でない: {len(items)}")
    return {kind: bool(evidence) for kind, evidence in items[0].info.items()}


def judged(text: str) -> aic.Item:
    items = aic.analyze("## Next Action\n\n" + text + "\n")
    if len(items) != 1:
        raise AssertionError(f"項目が1件でない: {len(items)}")
    return items[0]


S = aic.SECTION
C = aic.CHECKBOX


class ItemTest(unittest.TestCase):
    def test_items_found(self) -> None:
        testCases = {
            "見出しの Next Action の節の箇条書きを項目にする": {
                "text": "# 定例\n\n## Next Action\n\n- 資料を作る\n- 連絡する\n",
                "want": [(5, 5, S), (6, 6, S)],
            },
            "太字の行の宿題の節は次の太字の行で閉じる": {
                "text": "**宿題**\n- 資料を作る\n\n**メモ**\n- 雑談\n",
                "want": [(2, 2, S)],
            },
            "太字の行の節は見出しでも閉じる": {
                "text": "**NA**\n- 資料を作る\n## メモ\n- 雑談\n",
                "want": [(2, 2, S)],
            },
            "太字の箇条書きの NA は子だけを項目にする": {
                "text": "- **NA**\n  - 資料を作る\n  - 連絡する\n- 次の議題\n",
                "want": [(2, 2, S), (3, 3, S)],
            },
            "見出しの節の中の太字の箇条書きの宿題は子だけを項目にする": {
                "text": "## Next Action\n- **宿題**\n  - 資料を作る\n",
                "want": [(3, 3, S)],
            },
            "節の外のチェックボックスを項目にする": {
                "text": "## メモ\n\n- [ ] 資料を作る\n- [x] 連絡した\n- 雑談\n",
                "want": [(3, 3, C), (4, 4, C)],
            },
            "節の外のチェックボックスでない箇条書きは数えない": {
                "text": "## 決定事項\n\n- 12/1に始める\n",
                "want": [],
            },
            "節の中のチェックボックスは節の項目として1回だけ数える": {
                "text": "## TODO\n\n- [ ] 資料を作る\n",
                "want": [(3, 3, S)],
            },
            "入れ子の箇条書きは親の項目に含める": {
                "text": "## NA\n- 資料を作る\n  - 子\n    - 孫\n- 連絡する\n",
                "want": [(2, 4, S), (5, 5, S)],
            },
            "入れ子のチェックボックスは親の一部にする": {
                "text": "## メモ\n- [ ] 親の作業\n  - [ ] 子の作業\n",
                "want": [(2, 3, C)],
            },
            "同じ階層の見出しで節を閉じる": {
                "text": "## Next Action\n- 資料を作る\n## メモ\n- 雑談\n",
                "want": [(2, 2, S)],
            },
            "下の階層の見出しは節に含め、上の階層の見出しで閉じる": {
                "text": "## NA\n### 店舗\n- 資料を作る\n### 本部\n- 連絡する\n# 次\n- 雑談\n",
                "want": [(3, 3, S), (5, 5, S)],
            },
            "見出しの節の中の太字の行は項目を閉じ、節は続ける": {
                "text": "## NA\n- 資料を作る\n**メモ**\n- 連絡する\n",
                "want": [(2, 2, S), (4, 4, S)],
            },
            "NAME や N/A の見出しは節にしない": {
                "text": "## NAME\n- 雑談\n## N/A\n- 雑談\n",
                "want": [],
            },
            "リアクションの見出しは節にしない": {
                "text": "## リアクション\n- 雑談\n",
                "want": [],
            },
            "フェンスの中のチェックボックスは数えない": {
                "text": "```\n- [ ] 例\n```\n",
                "want": [],
            },
            "HTML のコメントの中のチェックボックスは数えない": {
                "text": "<!--\n- [ ] 例\n-->\n",
                "want": [],
            },
            "タブで字下げした子も親に含める": {
                "text": "## NA\n- 資料を作る\n\t- 子\n",
                "want": [(2, 3, S)],
            },
            "Notion の見出しの属性を外して読む": {
                "text": '## 宿題 {toggle="true"}\n\t- 資料を作る\n',
                "want": [(2, 2, S)],
            },
            "空行の後の字下げの無い段落で項目を閉じる": {
                "text": "## NA\n- 資料を作る\n\n段落\n",
                "want": [(2, 2, S)],
            },
            "空行の後でも字下げした行は項目に含める": {
                "text": "## NA\n- 資料を作る\n\n  続きの段落\n",
                "want": [(2, 4, S)],
            },
            "空行の無い字下げの無い行は項目の続きにする": {
                "text": "## NA\n- 資料を作る\n続きの行\n",
                "want": [(2, 3, S)],
            },
            "節の最初の箇条書きの字下げを項目の階層にする": {
                "text": "## NA\n  - 資料を作る\n    - 子\n  - 連絡する\n",
                "want": [(2, 3, S), (4, 4, S)],
            },
            "番号付きの箇条書きも項目にする": {
                "text": "## NA\n1. 資料を作る\n2) 連絡する\n",
                "want": [(2, 2, S), (3, 3, S)],
            },
            "中黒で始まる行も箇条書きに数える": {
                "text": "## 宿題\n・資料を作る\n・ 連絡する\n",
                "want": [(2, 2, S), (3, 3, S)],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(spans(tc["text"]), tc["want"])

    def test_action_labels(self) -> None:
        testCases = {
            "Next Action": True,
            "next actions": True,
            "NA": True,
            "na": True,
            "アクション": True,
            "次のアクション": True,
            "宿題": True,
            "TODO": True,
            "ToDo": True,
            "To-Do": True,
            "やること": True,
            "Action Items": True,
            "action item": True,
            "NA（11/13）": True,
            "決定事項": False,
            "NAME": False,
            "N/A": False,
            "ANALYSIS": False,
            "DNA の検査": False,
            "リアクション": False,
        }
        for label, want in testCases.items():
            for form in ("## {}", "**{}**", "**{}:**"):
                text = form.format(label) + "\n- 資料を作る\n"
                with self.subTest(
                    f"{form.format(label)} は節に{'する' if want else 'しない'}"
                ):
                    self.assertEqual(bool(aic.analyze(text)), want)

    def test_section_name(self) -> None:
        testCases = {
            "Notion の見出しの属性を外した文を節の名前にする": {
                "text": '## 宿題 {toggle="true"}\n- 資料を作る\n',
                "want": "宿題",
            },
            "太字の行の末尾のコロンを外した文を節の名前にする": {
                "text": "**NA:**\n- 資料を作る\n",
                "want": "NA",
            },
            "太字の箇条書きの文を節の名前にする": {
                "text": "- **Next Action**\n  - 資料を作る\n",
                "want": "Next Action",
            },
            "節の外のチェックボックスは節の名前を持たない": {
                "text": "- [ ] 資料を作る\n",
                "want": None,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(
                    [item.section for item in aic.analyze(tc["text"])], [tc["want"]]
                )


class OwnerTest(unittest.TestCase):
    def test_owner(self) -> None:
        testCases = {
            "Notion のユーザーのメンションを担当に数える": {
                "text": '<mention-user url="user://00000000-0000-0000-0000-000000000001"/> 資料を作る',
                "want": True,
            },
            "名前つきの Notion のユーザーのメンションを担当に数える": {
                "text": '<mention-user url="user://0001">犬山</mention-user> 資料を作る',
                "want": True,
            },
            "@名前を担当に数える": {"text": "@inuyama 資料を作る", "want": True},
            "全角の＠も担当に数える": {"text": "＠犬山 資料を作る", "want": True},
            "メールアドレスの @ は担当に数えない": {
                "text": "info@example.com に資料を送る",
                "want": False,
            },
            "@channel は担当に数えない": {"text": "@channel 資料を見る", "want": False},
            "コードの中の @ は担当に数えない": {
                "text": "`@inuyama` の設定を直す",
                "want": False,
            },
            "担当の語を担当に数える": {"text": "資料を作る 担当 犬山", "want": True},
            "英語の owner を担当に数える": {"text": "owner: inu", "want": True},
            "漢字の名前にさんを担当に数える": {
                "text": "犬山さんが資料を作る",
                "want": True,
            },
            "カタカナの名前にさんを担当に数える": {
                "text": "ミケさんが資料を作る",
                "want": True,
            },
            "英字の名前にさんを担当に数える": {
                "text": "Inuさんが資料を作る",
                "want": True,
            },
            "たくさんは担当に数えない": {"text": "資料をたくさん作る", "want": False},
            "皆さんは担当に数えない": {"text": "皆さんで資料を見る", "want": False},
            "お客さんは担当に数えない": {"text": "お客さんに資料を送る", "want": False},
            "行頭の丸括弧の名前を担当に数える": {
                "text": "(犬山) 資料を作る",
                "want": True,
            },
            "行頭の隅付き括弧の名前を担当に数える": {
                "text": "【猫田】資料を作る",
                "want": True,
            },
            "行末の全角括弧の名前を担当に数える": {
                "text": "資料を作る（鳥井）",
                "want": True,
            },
            "行末の角括弧の英字の名前を担当に数える": {
                "text": "資料を作る [inu]",
                "want": True,
            },
            "括弧に担当と期限があれば担当に数える": {
                "text": "資料を作る（猫田、11/20）",
                "want": True,
            },
            "括弧に二人の名前を斜線で並べても担当に数える": {
                "text": "資料を作る（猫田/鳥井）",
                "want": True,
            },
            "行末の括弧が相対の期限なら担当に数えない": {
                "text": "資料を作る（来週）",
                "want": False,
            },
            "行末の括弧が中の付かない年内なら担当に数えない": {
                "text": "資料を作る（年内）",
                "want": False,
            },
            "行末の括弧が日付なら担当に数えない": {
                "text": "資料を作る（11/20）",
                "want": False,
            },
            "行末の括弧が曜日なら担当に数えない": {
                "text": "資料を作る（金）",
                "want": False,
            },
            "行末の括弧が状態の語なら担当に数えない": {
                "text": "資料を作る（済）",
                "want": False,
            },
            "行末の括弧が理由の語なら担当に数えない": {
                "text": "資料を作る（目的）",
                "want": False,
            },
            "行末の括弧が大文字の略語なら担当に数えない": {
                "text": "資料を作る (API)",
                "want": False,
            },
            "行末の括弧が4字の漢字なら担当に数えない": {
                "text": "資料を作る（資料作成）",
                "want": False,
            },
            "行末の括弧の開きと閉じが合わなければ担当に数えない": {
                "text": "資料を作る（犬山]",
                "want": False,
            },
            "行の途中の括弧は担当に数えない": {
                "text": "資料（犬山）を作る",
                "want": False,
            },
            "行頭のリンクの文は担当に数えない": {
                "text": "[資料](https://example.com/doc)を作る",
                "want": False,
            },
            "括弧の組織の語はひらがなでも担当に数える": {
                "text": "資料を作る（お客さま）",
                "want": True,
            },
            "Notion のページのメンションは担当に数えない": {
                "text": '資料を作る（<mention-page url="https://example.com/p">議事録</mention-page>）',
                "want": False,
            },
            "子の行の担当も親の項目で読む": {
                "text": "資料を作る\n  - 犬山さんが持つ",
                "want": True,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(present(tc["text"])[aic.OWNER], tc["want"])


class ColumnTest(unittest.TestCase):
    def test_columns(self) -> None:
        cols, text = aic.COLUMN_FORM, aic.TEXT_FORM
        testCases = {
            "3つの欄のローマ字の名前を担当にする": {
                "text": "- [ ] Taro Inuyama / 資料を作る / 11/20",
                "want": (cols, True, True, False),
            },
            "3つの欄の名字だけを担当にする": {
                "text": "- [ ] 犬山 / 資料を作る / 未定",
                "want": (cols, True, False, False),
            },
            "1つ目の欄が未定なら担当なし": {
                "text": "- [ ] 未定 / 資料を作る / 11/20",
                "want": (cols, False, True, False),
            },
            "1つ目の欄が TBD なら担当なし": {
                "text": "- [ ] TBD / 資料を作る / 11/20",
                "want": (cols, False, True, False),
            },
            "1つ目の欄が小文字の tbd でも担当なし": {
                "text": "- [ ] tbd / 資料を作る / 11/20",
                "want": (cols, False, True, False),
            },
            "1つ目の欄がハイフンなら担当なし": {
                "text": "- [ ] - / 資料を作る / 11/20",
                "want": (cols, False, True, False),
            },
            "1つ目の欄が空なら担当なし": {
                "text": "- [ ] / 資料を作る / 11/20",
                "want": (cols, False, True, False),
            },
            "3つ目の欄が未定なら、2つ目の欄の次回を期限に数えない": {
                "text": "- [ ] 犬山 / 次回の資料を来週作る / 未定",
                "want": (cols, True, False, False),
            },
            "3つ目の欄の文を期限にする": {
                "text": "- [ ] 犬山 / 余白を直す / 金曜日配信前まで",
                "want": (cols, True, True, False),
            },
            "3つ目の欄が空なら期限なし": {
                "text": "- [ ] 犬山 / 資料を作る /",
                "want": (cols, True, False, False),
            },
            "3つ目の欄が TBD なら期限なし": {
                "text": "- [ ] 犬山 / 資料を作る / TBD",
                "want": (cols, True, False, False),
            },
            "3つ目の欄がハイフンなら期限なし": {
                "text": "- [ ] 犬山 / 資料を作る / -",
                "want": (cols, True, False, False),
            },
            "2つ目の欄の理由を読む": {
                "text": "- [ ] 犬山 / 入稿が近いので資料を作る / 11/20",
                "want": (cols, True, True, True),
            },
            "入れ子の行の理由を読む": {
                "text": "- [ ] 犬山 / 資料を作る / 11/20\n  - 入稿が近いので",
                "want": (cols, True, True, True),
            },
            "3つ目の欄の理由の語は読まない": {
                "text": "- [ ] 犬山 / 資料を作る / 入稿に合わせるため11/20",
                "want": (cols, True, True, False),
            },
            "入れ子の行の担当は欄の形では読まない": {
                "text": "- [ ] 未定 / 資料を作る / 11/20\n  - 犬山さんが持つ",
                "want": (cols, False, True, False),
            },
            "入れ子の行の期限は欄の形では読まない": {
                "text": "- [ ] 犬山 / 資料を作る / 未定\n  - 11/20まで",
                "want": (cols, True, False, False),
            },
            "Notion のメンションの欄を担当と期限にする": {
                "text": '- [ ] <mention-user url="user://0001"/> / 資料を作る / <mention-date start="2026-11-20"/>',
                "want": (cols, True, True, False),
            },
            "全角の斜線も欄に分ける": {
                "text": "- [ ] 犬山 ／ 資料を作る ／ 未定",
                "want": (cols, True, False, False),
            },
            "4つの欄なら語の規則で読む": {
                "text": "- [ ] 猫田 / 費用 / 日程を比べる / 11/27",
                "want": (text, False, True, False),
            },
            "2つの欄なら語の規則で読む": {
                "text": "- [ ] 犬山さん / 資料を作る 11/20",
                "want": (text, True, True, False),
            },
            "チェックボックスでない行は3つの欄でも語の規則で読む": {
                "text": "- 犬山 / 資料を作る / 未定",
                "want": (text, False, False, False),
            },
            "斜線の前後に空白が無ければ欄に分けない": {
                "text": "- [ ] 犬山/資料を作る/未定 11/20",
                "want": (text, False, True, False),
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                item = judged(tc["text"])
                got = (item.form, *(bool(item.info[kind]) for kind in aic.KINDS))
                self.assertEqual(got, tc["want"])

    def test_column_evidence_rules(self) -> None:
        testCases = {
            "欄の形の担当と期限は欄の文を手がかりにする": {
                "text": "- [ ] Taro Inuyama / 資料を作る / 金曜日配信前まで",
                "owner": [(aic.COLUMN_OWNER_RULE, "Taro Inuyama")],
                "due": [(aic.COLUMN_DUE_RULE, "金曜日配信前まで")],
            },
            "Notion のメンションの欄は読める形にして手がかりにする": {
                "text": '- [ ] <mention-user url="user://0001"/> / 資料を作る / <mention-date start="2026-11-20"/>',
                "owner": [(aic.COLUMN_OWNER_RULE, "@user")],
                "due": [(aic.COLUMN_DUE_RULE, "2026-11-20")],
            },
            "語の規則の担当と期限は語の規則の名前を手がかりにする": {
                "text": "- [ ] 犬山さんが資料を作る 11/20",
                "owner": [("〇〇さん", "犬山さん")],
                "due": [(aic.DUE_FORM_RULE, "11/20")],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                item = judged(tc["text"])
                got = {
                    key: [(e.rule, e.match) for e in item.info[kind]]
                    for key, kind in (("owner", aic.OWNER), ("due", aic.DUE))
                }
                self.assertEqual(got, {"owner": tc["owner"], "due": tc["due"]})


class OwnerKindTest(unittest.TestCase):
    def test_owner_kind(self) -> None:
        p, g = aic.PERSON, aic.GROUP
        testCases = {
            "欄のローマ字の名前は person": {
                "text": "- [ ] Taro Inuyama / 資料 / 未定",
                "want": p,
            },
            "欄の名字は person": {"text": "- [ ] 犬山 / 資料 / 未定", "want": p},
            "欄の先方は group": {"text": "- [ ] 先方 / 資料 / 未定", "want": g},
            "欄の側は group": {"text": "- [ ] 弊社 側 / 資料 / 未定", "want": g},
            "欄の中黒でつないだ当事者は group": {
                "text": "- [ ] 弊社 側・先方 / 資料 / 未定",
                "want": g,
            },
            "欄の中黒でつないだ二人の名前は group": {
                "text": "- [ ] 犬山・猫田 / 資料 / 未定",
                "want": g,
            },
            "欄の読点でつないだ二人の名前は group": {
                "text": "- [ ] 犬山、猫田 / 資料 / 未定",
                "want": g,
            },
            "欄のお客さまは group": {"text": "- [ ] お客さま / 資料 / 未定", "want": g},
            "欄の弊社は group": {"text": "- [ ] 弊社 / 資料 / 未定", "want": g},
            "欄の全員は group": {"text": "- [ ] 全員 / 資料 / 未定", "want": g},
            "欄の両者は group": {"text": "- [ ] 両者 / 資料 / 未定", "want": g},
            "欄の Notion のユーザーは person": {
                "text": '- [ ] <mention-user url="user://0001"/> / 資料 / 未定',
                "want": p,
            },
            "欄の担当が未定なら担当の種類も無い": {
                "text": "- [ ] 未定 / 資料 / 未定",
                "want": None,
            },
            "名前にさんは person": {"text": "- 犬山さんが資料を作る", "want": p},
            "@名前は person": {"text": "- @inu 資料を作る", "want": p},
            "括弧の先方は group": {"text": "- 資料を作る（先方）", "want": g},
            "括弧のお客さまは group": {"text": "- 資料を作る（お客さま）", "want": g},
            "括弧の中黒でつないだ二人の名前は group": {
                "text": "- 資料を作る（猫田・鳥井）",
                "want": g,
            },
            "括弧の全員は group": {"text": "- 資料を作る（全員）", "want": g},
            "担当の語だけなら person": {"text": "- 担当を決めて資料を作る", "want": p},
            "担当の無い項目は担当の種類も無い": {"text": "- 資料を作る", "want": None},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(judged(tc["text"]).owner_kind(), tc["want"])


class DueTest(unittest.TestCase):
    def test_due(self) -> None:
        testCases = {
            "月と日を斜線で書いた日付を期限に数える": {
                "text": "資料を作る 11/20",
                "want": True,
            },
            "月と日を漢字で書いた日付を期限に数える": {
                "text": "11月20日に資料を作る",
                "want": True,
            },
            "年月日をハイフンで書いた日付を期限に数える": {
                "text": "2026-11-20 資料を作る",
                "want": True,
            },
            "曜日つきの日付を期限に数える": {
                "text": "11/20（金）に資料を作る",
                "want": True,
            },
            "括弧の曜日だけでも期限に数える": {
                "text": "資料を作る（金）",
                "want": True,
            },
            "曜日の語を期限に数える": {"text": "金曜に資料を作る", "want": True},
            "Notion の日付のメンションを期限に数える": {
                "text": '資料を作る <mention-date start="2026-11-20"/>',
                "want": True,
            },
            "Notion の日時のメンションを期限に数える": {
                "text": '資料を作る <mention-date start="2026-11-20T10:00:00.000+09:00"/>',
                "want": True,
            },
            "今週中を期限に数える": {"text": "今週中に資料を作る", "want": True},
            "来週を期限に数える": {"text": "来週、資料を作る", "want": True},
            "次回までを期限に数える": {"text": "資料を作る（次回まで）", "want": True},
            "明日を期限に数える": {"text": "明日、資料を送る", "want": True},
            "中の付かない月内を期限に数える": {
                "text": "月内に資料を作る",
                "want": True,
            },
            "EOD を期限に数える": {"text": "EODで資料を送る", "want": True},
            "英語の tomorrow を期限に数える": {
                "text": "send it tomorrow",
                "want": True,
            },
            "子の行の期限も親の項目で読む": {
                "text": "資料を作る\n  - 11/20まで",
                "want": True,
            },
            "日付の無い項目は期限なし": {"text": "資料を作る", "want": False},
            "URL の中の日付は期限に数えない": {
                "text": "https://example.com/2026/11/20 を読む",
                "want": False,
            },
            "コードの中の日付は期限に数えない": {
                "text": "`2026-11-20` の形に直す",
                "want": False,
            },
            "Notion のユーザーのメンションの URL の数字は期限に数えない": {
                "text": '<mention-user url="user://2026-11-20"/> 資料を作る',
                "want": False,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(present(tc["text"])[aic.DUE], tc["want"])


class ReasonTest(unittest.TestCase):
    def test_reason(self) -> None:
        testCases = {
            "ためを理由に数える": {
                "text": "印刷に入れるため、資料を作る",
                "want": True,
            },
            "のでを理由に数える": {"text": "入稿が近いので資料を作る", "want": True},
            "動詞に続くからを理由に数える": {
                "text": "先方が使うから、資料を作る",
                "want": True,
            },
            "目的を理由に数える": {"text": "資料を作る。目的は告知", "want": True},
            "背景を理由に数える": {
                "text": "資料を作る。背景は在庫の不足",
                "want": True,
            },
            "なぜを理由に数える": {
                "text": "資料を作る。なぜ要るかは下に書く",
                "want": True,
            },
            "英語の why を理由に数える": {
                "text": "make the doc. Why: low stock",
                "want": True,
            },
            "に向けてを理由に数える": {
                "text": "セールに向けて資料を作る",
                "want": True,
            },
            "子の行の理由も親の項目で読む": {
                "text": "資料を作る\n  - 入稿が近いので",
                "want": True,
            },
            "の前に、は時機なので理由に数えない": {
                "text": "定例の前に資料を送る",
                "want": False,
            },
            "てから、は順番なので理由に数えない": {
                "text": "確認してから資料を送る",
                "want": False,
            },
            "名詞に続くからは理由に数えない": {
                "text": "来週から資料を作る",
                "want": False,
            },
            "あらためては理由に数えない": {
                "text": "あらためて資料を送る",
                "want": False,
            },
            "理由の語が無い項目は理由なし": {"text": "資料を作る", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(present(tc["text"])[aic.REASON], tc["want"])

    def test_reason_rules_reuse_the_existing_tool(self) -> None:
        existing = dbc.TEXT_RULES[dbc.REASON]
        self.assertIn(aic.TIMING_RULE, [rule for rule, _ in existing])
        reused = [
            pattern for rule, pattern in aic.REASON_RULES if rule != aic.PURPOSE_RULE
        ]
        kept = [pattern for rule, pattern in existing if rule != aic.TIMING_RULE]
        self.assertEqual(len(reused), len(existing) - 1)
        for got, want in zip(reused, kept):
            self.assertIs(got, want)


class FixtureTest(unittest.TestCase):
    def test_fixture_items(self) -> None:
        o, d, r = aic.OWNER, aic.DUE, aic.REASON
        testCases = {
            "週次の定例は入れ子の理由を読み、節の外のチェックボックスも数える": {
                "path": WEEKLY,
                "want": [
                    (10, 11, []),
                    (12, 12, [r]),
                    (13, 13, [o, d, r]),
                    (14, 15, []),
                    (19, 19, [r]),
                ],
            },
            "Notion の書き出しはメンションを担当と期限に読む": {
                "path": NOTION,
                "want": [
                    (7, 8, []),
                    (9, 9, [d, r]),
                    (10, 10, [o, d, r]),
                    (13, 13, [r]),
                ],
            },
            "担当 / 内容 / 期限の欄の形は欄で担当と期限を読む": {
                "path": COLUMNS,
                "want": [
                    (3, 3, [d, r]),
                    (4, 5, []),
                    (6, 6, [d, r]),
                    (7, 7, [d, r]),
                    (8, 9, []),
                    (10, 10, [o, d, r]),
                    (11, 11, [o, d, r]),
                    (12, 12, [o, r]),
                ],
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                items = aic.analyze(tc["path"].read_text(encoding="utf-8"))
                got = [(item.start, item.end, item.missing()) for item in items]
                self.assertEqual(got, tc["want"])


class CliTest(unittest.TestCase):
    def test_exit_codes(self) -> None:
        complete = "## NA\n- 犬山さんが11/20までに資料を作る。入稿が近いため\n"
        testCases = {
            "欠けがあれば1": {"args": (str(MINUTES),), "stdin": "", "code": 1},
            "--report-only は欠けがあっても0": {
                "args": ("--report-only", str(MINUTES)),
                "stdin": "",
                "code": 0,
            },
            "欠けが無ければ0": {"args": ("-",), "stdin": complete, "code": 0},
            "項目が無ければ0": {
                "args": ("-",),
                "stdin": "## メモ\n- 雑談\n",
                "code": 0,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                code, out, err = run(*tc["args"], stdin=tc["stdin"])
                self.assertEqual(code, tc["code"])
                self.assertIn("# action-item-check", out)
                self.assertEqual(err, "")

    def test_input_errors_exit_2_without_output(self) -> None:
        missing = str(FIXTURES / "missing.md")
        testCases = {
            "無いパスは2": {"args": (missing,)},
            "--report-only でも無いパスは2": {"args": ("--report-only", missing)},
            "読めるパスと無いパスを混ぜても2": {"args": (str(MINUTES), missing)},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                code, out, err = run(*tc["args"])
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("パスが無い", err)

    def test_no_paths_exit_2(self) -> None:
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            raised = stack.enter_context(self.assertRaises(SystemExit))
            aic.main([])
        self.assertEqual(raised.exception.code, 2)

    def test_files_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / ".hidden").mkdir()
            (root / "a.md").write_text("- [ ] 資料を作る\n", encoding="utf-8")
            (root / "sub" / "b.md").write_text("- [ ] 連絡する\n", encoding="utf-8")
            (root / ".hidden" / "c.md").write_text("- [ ] 隠す\n", encoding="utf-8")
            (root / "d.txt").write_text("- [ ] 読まない\n", encoding="utf-8")
            bom = root / "bom.txt"
            bom.write_text("﻿## NA\n- 資料を作る\n", encoding="utf-8")
            broken = root / "broken.txt"
            broken.write_bytes(b"\xff\xfe- [ ] \xe3\n")
            testCases = {
                "ディレクトリは下の階層の md を読み、隠しディレクトリは読まない": {
                    "args": (str(root),),
                    "code": 1,
                    "paths": [str(root / "a.md"), str(root / "sub" / "b.md")],
                    "items": [1, 1],
                },
                "同じファイルを2回渡しても1回だけ読む": {
                    "args": (str(root / "a.md"), str(root)),
                    "code": 1,
                    "paths": [str(root / "a.md"), str(root / "sub" / "b.md")],
                    "items": [1, 1],
                },
                "BOM の付いたファイルも先頭の見出しを読む": {
                    "args": (str(bom),),
                    "code": 1,
                    "paths": [str(bom)],
                    "items": [1],
                },
                "UTF-8 で読めないファイルは2": {
                    "args": (str(broken),),
                    "code": 2,
                    "paths": None,
                    "items": None,
                },
            }
            for tn, tc in testCases.items():
                with self.subTest(tn):
                    code, out, err = run("--json", *tc["args"])
                    self.assertEqual(code, tc["code"])
                    if tc["paths"] is None:
                        self.assertEqual(out, "")
                        self.assertIn("読めない", err)
                        continue
                    report = json.loads(out)
                    self.assertEqual([f["path"] for f in report["files"]], tc["paths"])
                    self.assertEqual(
                        [f["summary"]["items"] for f in report["files"]], tc["items"]
                    )

    def test_markdown_output(self) -> None:
        code, out, _ = run(str(MINUTES))
        self.assertEqual(code, 1)
        lines = out.splitlines()
        testCases = {
            "全体の件数を出す": "項目9件 / 3つがそろう3件 / 担当の欠け2件 / 期限の欠け3件 / 理由の欠け6件 / 組織か複数の担当0件",
            "ファイルごとの件数を出す": "項目5件 / 3つがそろう2件 / 担当の欠け1件 / 期限の欠け1件 / 理由の欠け3件 / 組織か複数の担当0件",
            "ファイルの見出しを出す": f"## {WEEKLY}",
            "欠けた項目の行と文を出す": "- 13行目「- 告知の文面を確かめる」",
            "欠けた情報を出す": "  - 欠け 担当 / 期限 / 理由",
            "ある情報の手がかりを出す": "  - あり 担当「猫田」 / 期限「来週」",
            "Notion のメンションは中の文と日付にして出す": "- 13行目「- [ ] @user 撮影の日程を決める 2026-11-25」",
        }
        for tn, want in testCases.items():
            with self.subTest(tn):
                self.assertIn(want, lines)
        self.assertFalse([line for line in lines if "10〜11行目" in line])
        _, nested, _ = run("-", stdin="## NA\n- 資料を作る\n  - 子\n")
        self.assertIn("- 2〜3行目「- 資料を作る」", nested.splitlines())

    def test_markdown_output_for_columns(self) -> None:
        code, out, _ = run(str(COLUMNS))
        self.assertEqual(code, 1)
        lines = out.splitlines()
        testCases = {
            "組織か複数の担当の件数を出す": "項目8件 / 3つがそろう2件 / 担当の欠け3件 / 期限の欠け5件 / 理由の欠け6件 / 組織か複数の担当3件",
            "組織か複数の担当に印を付ける": "  - あり 担当「先方」（組織か複数）",
            "人の担当には印を付けない": "  - あり 担当「Taro Inuyama」",
        }
        for tn, want in testCases.items():
            with self.subTest(tn):
                self.assertIn(want, lines)

    def test_json_shape(self) -> None:
        code, out, _ = run("--json", str(WEEKLY))
        report = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(
            report["summary"],
            {
                "files": 1,
                "items": 5,
                "complete": 2,
                "missing": {aic.OWNER: 1, aic.DUE: 1, aic.REASON: 3},
                "owner_kind": {aic.PERSON: 4, aic.GROUP: 0},
            },
        )
        item = report["files"][0]["items"][0]
        keys = ("start_line", "end_line", "source", "section", "form", "owner_kind")
        self.assertEqual(
            {key: item[key] for key in keys},
            {
                "start_line": 10,
                "end_line": 11,
                "source": aic.SECTION,
                "section": "Next Action",
                "form": aic.TEXT_FORM,
                "owner_kind": aic.PERSON,
            },
        )
        self.assertEqual(item["missing"], [])
        self.assertEqual(
            item["info"][aic.OWNER],
            {"present": True, "evidence": [{"rule": "〇〇さん", "match": "犬山さん"}]},
        )
        self.assertEqual(report["files"][0]["items"][4]["source"], aic.CHECKBOX)

    def test_json_for_columns(self) -> None:
        _, out, _ = run("--json", str(COLUMNS))
        report = json.loads(out)
        self.assertEqual(report["summary"]["owner_kind"], {aic.PERSON: 2, aic.GROUP: 3})
        items = report["files"][0]["items"]
        self.assertEqual(
            [(i["form"], i["owner_kind"]) for i in items],
            [
                (aic.COLUMN_FORM, aic.PERSON),
                (aic.COLUMN_FORM, aic.PERSON),
                (aic.COLUMN_FORM, aic.GROUP),
                (aic.COLUMN_FORM, aic.GROUP),
                (aic.COLUMN_FORM, aic.GROUP),
                (aic.COLUMN_FORM, None),
                (aic.COLUMN_FORM, None),
                (aic.TEXT_FORM, None),
            ],
        )
        self.assertEqual(
            items[3]["info"][aic.OWNER]["evidence"],
            [{"rule": aic.COLUMN_OWNER_RULE, "match": "弊社 側・先方"}],
        )


if __name__ == "__main__":
    unittest.main()
