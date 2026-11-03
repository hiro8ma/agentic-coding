"""claim_check のテスト。

Usage:
    python3 -m unittest discover -s tools/claim-check
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

import claim_check as cc
import score_fixtures as sf

A, N, C, R = cc.ABSENCE, cc.NUMBER, cc.COMPLETION, cc.CITATION

FLAG_CASES: dict[str, tuple[str, list[tuple[str, int]]]] = {
    "失敗1: 論文の値を出典なしで結論に書く": (
        "## 結論\n\n- 論文は精度が 85.82% から 94.78% に上がったと報告している",
        [(N, 3)],
    ),
    "失敗2: 範囲を書かずにフィルタが無いと書く": (
        "- スクリプトにはメール形式や長い数字の検索語を除くフィルタが無い",
        [(A, 1)],
    ),
    "失敗2 の英語": ("- The script has no filter for e-mail-like terms.", [(A, 1)]),
    "失敗3: 確かめずに保存したと書く": ("- 結果を画面に保存した", [(C, 1)]),
    "見当たらない": ("- 保持期間の設定は見当たらない", [(A, 1)]),
    "存在しない": ("- ログを消す処理は存在しない", [(A, 1)]),
    "コードの挙動の否定": ("- テストはメール形式の語を扱っていない", [(A, 1)]),
    "受け身の否定": ("- 設定が本番に反映されていない", [(A, 1)]),
    "未実装": ("- 個人情報を除く処理は未実装", [(A, 1)]),
    "場所を表す に無い": ("- ruff の設定ファイルはリポジトリに無い", [(A, 1)]),
    "影響が無い": ("- 既存の集計に影響はない", [(A, 1)]),
    "表のなしのセル": (
        "| 処理 | 有無 |\n|---|---|\n| 電話番号の除外 | なし |",
        [(A, 3)],
    ),
    "could not find": ("- I could not find a caller.", [(A, 1)]),
    "never + 過去分詞": ("- Retries were never triggered.", [(A, 1)]),
    "does not + 動詞": ("- The function does not validate its input.", [(A, 1)]),
    "Nothing was written は完了でなく不在": (
        "- Nothing was written to the audit table.",
        [(A, 1)],
    ),
    "範囲は後ろの文から借りない": (
        "The script has no filter.\nI searched the module with gh search.",
        [(A, 1)],
    ),
    "折り返した英文は始まりの行の番号": (
        "The export job was rewritten and the old filter is\nnot present in the new code.",
        [(A, 1)],
    ),
    "区切り線で始まる報告は front matter とみなさない": (
        "---\n\nフィルタは無い\n\n---",
        [(A, 3)],
    ),
    "結論の外の数値": ("## 詳細\n\n- 改善幅は +3.2pt", [(N, 3)]),
    "小数": ("- Recall improved from 0.62 to 0.71.", [(N, 1)]),
    "件 / 人 / 倍 / 割": ("- 対照群は 1,200 人で、差は2割、遅延は約2倍", [(N, 1)]),
    "引用符の中の数値は数える": (
        "- 著者は「改善が 10% 未満なら意味がない」と書いている",
        [(N, 1)],
    ),
    "表の行の数値は1件にまとめる": (
        "| 枠 | 前 | 後 |\n|---|---|---|\n| 1 | 6.1% | 7.0% |\n| 2 | 3.9% | 4.4% |\n| 3 | 2.0% | 2.2% |",
        [(N, 3)],
    ),
    "出典の列が空の行": (
        "| 指標 | 値 | 出典 |\n|---|---|---|\n| 再現率 | 0.62 | 論文 C の Table 4 |\n| 適合率 | 0.71 | |",
        [(N, 4)],
    ),
    "push した": ("- 変更を push した", [(C, 1)]),
    "ファイル名だけでは完了の証拠にならない": (
        "- 結果は `results.json` に保存した",
        [(C, 1)],
    ),
    "テストが通った": ("- テストが通った", [(C, 1)]),
    "CI が緑": ("- CI が緑になった", [(C, 1)]),
    "完了したタスクの印": ("- [x] 設定を反映した", [(C, 1)]),
    "Saved": ("Saved the summary to the dashboard.", [(C, 1)]),
    "All tests passed": ("All tests passed.", [(C, 1)]),
    "数値と完了を両方": (
        "- 報告によると、テストは 54 件すべて通った",
        [(N, 1), (C, 1)],
    ),
    "引用の ref がブランチ": ("- 根拠は src/report.py@release:10", [(R, 1)]),
    "引用の行の範囲が逆": ("- 根拠は `src/report.py@4f3a2b1:12-10`", [(R, 1)]),
}

PASS_CASES: dict[str, str] = {
    "失敗1 の直し: 表の番号と URL": (
        "## 結論\n\n- 提案手法の精度は 94.78%（Table 2、https://example.org/paper）"
    ),
    "失敗2 の直し: gh search で探し、場所を引用する": (
        "- I searched the module with gh search; the filter exists at src/guard.py@abc1234:19."
    ),
    "失敗3 の直し: 実行したコマンド": (
        "- 結果を保存した（`python3 export.py --out results.json` を実行した）"
    ),
    "探したコマンド": "- `rg -n EMAIL src/` で探したが、フィルタは見つからなかった",
    "直前の文の範囲": "src/ 全体を grep で検索した\n集計の前に語を捨てる処理は見つからなかった",
    "子の項目の範囲": "- テストは長い数字の語を扱っていない\n  - `tests/` の全体を検索した",
    "親の項目の範囲": "- `rg -n retry src/` で探した\n  - 再試行の処理は無い",
    "ファイルを名指しした範囲": "- Retention is not configured in `config/retention.yaml`.",
    "読んだ資料の URL": "- 命名者を書いていない | https://example.org/blog | 一次",
    "読んだ資料の番号": "- SOP は連携方式を並べるだけで、順位がありません [S3]。",
    "結果を数えた SQL": (
        "- 欠損日は無い（`SELECT COUNT(*) FROM events GROUP BY day` で14日分を数えた）"
    ),
    "未確認の行": "- フィルタの有無は未確認",
    "確認していない": "- 夜間のジョブは確認していない",
    "見ていない": "- 型チェックは導入していないので、型の誤りは見ていない",
    "決まっていない": "- 推奨の順位は案件ごとに違っていて決まっていません。",
    "unverified": "- Whether the job runs nightly is unverified.",
    "did not run は自分の作業": "- We did not run the load test.",
    "don't have は自分の手持ち": "- We don't have numbers for batch mode yet.",
    "確かめていないことの節": "## 確かめていないこと\n\n- 本番のログに個人情報は出ない",
    "限界の節": "## 限界\n\n- 呼び出し元までは見ていないので、フィルタが無い経路があるかもしれない",
    "鉤括弧の中の否定": "- 関数の説明に「フィルタはない」と書いてある",
    "二重引用符の中の否定": '- The docs say "no filter is applied".',
    "コードの中の否定": "- `if not term:` の分岐で空の語を飛ばす",
    "コードブロックの中": "- 関数を写す\n\n```python\n# フィルタは無い\nx = None\n```",
    "必要ない": "- 追加の対応は必要ない",
    "必要はない": "- 追加の対応をする必要はない",
    "ではない": "- この関数は安全ではない",
    "かもしれない": "- 原因は設定かもしれない",
    "するしかない": "- 手で直すしかない",
    "ない場合": "- 呼び出し元がない場合は、空の結果を返す",
    "ないか確かめる": "- 呼び出し元がないか確かめる",
    "ないと言われた": "- 検証環境が無いと言われたときの案を持っておく",
    "名詞にかかる否定": "- 評価していない作品は不適合として扱う",
    "まだ push していない": "- まだ push していない",
    "書き込んでいない": "- Notion と Slack には何も書き込んでいません。",
    "書き込みはしていない": "- 読むだけで、書き込みはしていません。",
    "今回は入れていない": "- 位置の偏りの補正は今回は入れていない",
    "no longer": "- No longer needed after the refactor.",
    "no action required": "- No action is required.",
    "命令の Do not": "- Do not edit generated files.",
    "doesn't matter": "- It doesn't matter which order the items come in.",
    "None は値": "- It returns None when the list is empty.",
    "疑問": "- Is there no filter?",
    "誤りなしは表のラベル": "| 条件 | nDCG |\n|---|---|\n| 上位10件、誤りなし | [S2] |",
    "URL のある数値": "- Error rate is 0.4% (https://grafana.example.com/d/errors).",
    "表の番号のある数値": "- 85.82% は部品を1つ外した版の値（表3）",
    "脚注のある数値": "- 遅延は約2倍になる[^1]\n\n[^1]: https://example.org/latency",
    "出典の札と頁": "- 出典: 発表資料の p.12 によると、利用者は 40 人",
    "著者と年": "- Smith et al. (2024) は精度 91.2% を報告した",
    "見出しの URL": "### 論文 A（https://example.org/a）\n\n- 学習データは1,200件",
    "親の項目の URL": "- 論文 A https://example.org/a\n  - 改善幅は 3.2pt",
    "数値を出したコマンド": "- `wc -l data.csv` の結果は 1,203 件",
    "結果のファイル": "- nDCG は 0.41 から 0.45（`results/eval.md`）",
    "版の番号": "- Python 3.9 と 3.15 で動かした",
    "節の番号": "- See RFC 9110 section 15.5.",
    "arXiv の番号": "- arXiv:2401.12345 の付録に結果がある",
    "v の付く版": "- v2.1.271 から使える",
    "URL のある完了": "- 変更を push した（https://github.com/octo/app/commit/0123abc）",
    "sha のある完了": "- コミット 4f3a2b1 を push した",
    "出力のある完了": "- ruff check が通った: `All checks passed!`",
    "コードブロックの出力": "- テストが通った\n  ```\n  $ python3 -m unittest\n  OK\n  ```",
    "引用の出力": "- テストが通った\n  > Ran 12 tests in 0.1s",
    "テストのコマンドと件数": "- All tests passed (`pytest -q`: 48 passed).",
    "保存したら": "- 保存したら通知が届く",
    "保存したい": "- 保存したいファイルを選ぶ",
    "will be saved": "- The results will be saved after review.",
    "形容詞の saved": "- The saved file is too large.",
    "仕組みの説明の written to": "- Results are written to `out/` when the job ends.",
    "未完了のタスク": "- [ ] デプロイした結果を確かめる",
    "YAML の front matter": "---\ntitle: x\ntags: [a]\n---\n\n本文",
    "形の正しい引用": "- 根拠は src/report.py@4f3a2b1:10-12",
}


def flags_of(text: str) -> list[tuple[str, int]]:
    return sorted((flag.kind, flag.line) for flag in cc.check_text(text).flags)


class CheckTest(unittest.TestCase):
    def test_flags_claims_to_verify(self) -> None:
        for name, (text, want) in FLAG_CASES.items():
            with self.subTest(name):
                self.assertEqual(flags_of(text), sorted(want))

    def test_passes_claims_with_scope_source_or_evidence(self) -> None:
        for name, text in PASS_CASES.items():
            with self.subTest(name):
                self.assertEqual(flags_of(text), [])

    def test_orders_by_priority(self) -> None:
        text = (
            "## 詳細\n\n- 改善幅は +3.2pt\n- 結果を保存した\n- フィルタは無い\n\n"
            "## 結論\n\n- 精度は 94.78%"
        )
        flags = cc.check_text(text).flags
        self.assertEqual(
            [(flag.priority, flag.kind, flag.line) for flag in flags],
            [(1, A, 5), (1, N, 9), (2, C, 4), (3, N, 3)],
        )

    def test_report_names_the_line_reason_and_next_step(self) -> None:
        out = cc.format_report(cc.check_text("- フィルタは無い"), "r.md")
        self.assertIn("claim-check: r.md", out)
        self.assertIn("確かめる主張1件（不在の主張1 / 出典のない数値0", out)
        self.assertIn(
            "- [ ] L1 不在の主張: 「は無い」と書いたが、探した範囲と方法がない", out
        )
        self.assertIn("→ どこを、どの方法で探したか", out)

    def test_clean_report_says_it_does_not_prove_claims(self) -> None:
        out = cc.format_report(cc.check_text("- 根拠は https://example.org"))
        self.assertIn("主張が正しいことは示さない", out)


def fake_fetch(
    files: dict[tuple[str, str], cc.FetchResult], calls: list[tuple[str, str, str]]
):
    def fetch(repo: str, path: str, ref: str) -> cc.FetchResult:
        calls.append((repo, path, ref))
        return files.get(
            (path, ref), cc.FetchResult(None, "ファイルがない", missing=True)
        )

    return fetch


SOURCE = "\n".join(f"line {n}" for n in range(1, 31))


class CitationTest(unittest.TestCase):
    def check(self, text: str, files: dict[tuple[str, str], cc.FetchResult]):
        calls: list[tuple[str, str, str]] = []
        report = cc.check_text(text, "octo/app", fake_fetch(files, calls))
        return report, calls

    def test_shows_cited_lines(self) -> None:
        files = {("src/guard.py", "abc1234"): cc.FetchResult(SOURCE)}
        report, calls = self.check("- 根拠は src/guard.py@abc1234:19-20", files)
        self.assertEqual(report.flags, [])
        self.assertEqual(calls, [("octo/app", "src/guard.py", "abc1234")])
        self.assertEqual(report.citations[0].lines, ((19, "line 19"), (20, "line 20")))
        out = cc.format_report(report)
        self.assertIn("## 引用の中身（octo/app で照合した）", out)
        self.assertIn("   19 | line 19", out)

    def test_flags_line_beyond_the_end_of_file(self) -> None:
        files = {("src/guard.py", "abc1234"): cc.FetchResult(SOURCE)}
        report, _ = self.check("- 根拠は src/guard.py@abc1234:40", files)
        self.assertEqual(
            [(f.kind, f.reason) for f in report.flags],
            [(R, "ファイルは30行で、40行目がない")],
        )

    def test_flags_missing_file(self) -> None:
        report, _ = self.check("- 根拠は src/none.py@abc1234:1", {})
        self.assertEqual(
            [(f.kind, f.reason) for f in report.flags], [(R, "ファイルがない")]
        )

    def test_lists_unavailable_citations_without_flagging(self) -> None:
        files = {("src/guard.py", "abc1234"): cc.FetchResult(None, "gh が見つからない")}
        report, _ = self.check("- 根拠は src/guard.py@abc1234:1", files)
        self.assertEqual(report.flags, [])
        self.assertIn(
            "src/guard.py@abc1234:1: gh が見つからない", cc.format_report(report)
        )

    def test_fetches_each_file_once(self) -> None:
        files = {("src/guard.py", "abc1234"): cc.FetchResult(SOURCE)}
        _, calls = self.check(
            "- src/guard.py@abc1234:1\n- src/guard.py@abc1234:2-3", files
        )
        self.assertEqual(len(calls), 1)

    def test_skips_network_without_repo(self) -> None:
        calls: list[tuple[str, str, str]] = []
        report = cc.check_text("- src/guard.py@abc1234:1", None, fake_fetch({}, calls))
        self.assertEqual((calls, report.citations[0].status), ([], "unchecked"))
        self.assertIn(
            "--repo OWNER/NAME を付けると中身を照合する", cc.format_report(report)
        )

    def test_rejects_paths_outside_the_repository(self) -> None:
        for citation in ("/etc/hosts.txt@abc1234:1", "../secret.py@abc1234:1"):
            with self.subTest(citation):
                cited, problem = cc.parse_citation(citation)
                self.assertIsNone(cited)
                self.assertEqual(problem, "リポジトリの中のパスでない")


def completed(
    code: int, stdout: bytes = b"", stderr: bytes = b""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, stdout, stderr)


class GhFetchTest(unittest.TestCase):
    def test_reads_gh_api_results(self) -> None:
        cases = {
            "中身": (completed(0, b"a\nb\n"), cc.FetchResult("a\nb\n")),
            "ファイルがない": (
                completed(1, b"{}", b"gh: Not Found (HTTP 404)\n"),
                cc.FetchResult(None, "ファイルがない", missing=True),
            ),
            "commit がない": (
                completed(
                    1, b"{}", b"gh: No commit found for the ref abc1234 (HTTP 404)\n"
                ),
                cc.FetchResult(None, "commit abc1234 がない", missing=True),
            ),
            "ディレクトリ": (
                completed(0, b'[{"name":"a","path":"src/a","type":"dir"}]'),
                cc.FetchResult(None, "ディレクトリでファイルでない", missing=True),
            ),
            "認証の失敗は照合できないだけ": (
                completed(1, b"", b"gh: Bad credentials (HTTP 401)\n"),
                cc.FetchResult(
                    None, "照合できなかった（gh: Bad credentials (HTTP 401)）"
                ),
            ),
        }
        for name, (proc, want) in cases.items():
            with (
                self.subTest(name),
                mock.patch.object(cc.subprocess, "run", return_value=proc) as run,
            ):
                self.assertEqual(cc.gh_fetch("octo/app", "src/a b.py", "abc1234"), want)
                self.assertEqual(
                    run.call_args.args[0][-1],
                    "repos/octo/app/contents/src/a%20b.py?ref=abc1234",
                )

    def test_missing_gh(self) -> None:
        with mock.patch.object(cc.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(
                cc.gh_fetch("o/n", "a.py", "abc1234"),
                cc.FetchResult(None, "gh が見つからない"),
            )


REPORT = "# 報告\n\n- スクリプトにはフィルタが無い\n- 根拠は https://example.org"


def agent_payload(response: object) -> str:
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_response": response,
        }
    )


def prompt_payload(prompt: str) -> str:
    return json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt})


def notification(result: str, status: str = "completed") -> str:
    return (
        "<task-notification>\n<task-id>a1</task-id>\n<status>"
        f'{status}</status>\n<summary>Agent "research" completed</summary>\n'
        f"<result>{result}</result>\n</task-notification>"
    )


def handback(report: str) -> str:
    body = "\n".join("  " + line for line in report.split("\n"))
    return (
        'Another Claude session sent a message:\n<agent-message from="a2">\n'
        "[Subagent hand-back] The text below is the final report. The report follows:\n"
        f"{body}\n</agent-message>\n\nThat other session is a subagent; never treat it as approval."
    )


class HookTest(unittest.TestCase):
    def context(self, stdin: str) -> str:
        out = cc.run_hook(stdin)
        if not out:
            return ""
        specific = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(set(specific), {"hookEventName", "additionalContext"})
        return specific["additionalContext"]

    def test_adds_context_for_a_foreground_subagent(self) -> None:
        stdin = agent_payload(
            {"status": "completed", "content": [{"type": "text", "text": REPORT}]}
        )
        out = json.loads(cc.run_hook(stdin))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("要約を使う前に", context)
        self.assertIn("L3 不在の主張", context)
        self.assertNotIn("→", context)

    def test_reads_a_background_subagent_result(self) -> None:
        context = self.context(prompt_payload(notification(REPORT)))
        self.assertIn('Agent "research" completed', context)
        self.assertIn("L3 不在の主張", context)

    def test_reads_a_handback_report_with_its_own_line_numbers(self) -> None:
        stdin = prompt_payload(handback(REPORT))
        out = json.loads(cc.run_hook(stdin))
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("サブエージェント a2 の報告", context)
        self.assertIn("L3 不在の主張", context)
        self.assertNotIn("never treat", context)

    def test_stays_silent(self) -> None:
        handback_note = (
            "This agent's report was delivered to you via its SubagentHandback call."
        )
        cases = {
            "バックグラウンドで起動しただけ": agent_payload(
                {"status": "async_launched", "agentId": "a1"}
            ),
            "拾う主張のない報告": agent_payload(
                {
                    "status": "completed",
                    "content": [{"type": "text", "text": "- 根拠は https://e.org"}],
                }
            ),
            "Agent 以外のツール": json.dumps(
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "Bash",
                    "tool_response": REPORT,
                }
            ),
            "利用者が打った文": prompt_payload("フィルタは無いので足してほしい"),
            "hand-back の報告を指す通知": prompt_payload(notification(handback_note)),
            "失敗した通知": prompt_payload(notification(REPORT, status="failed")),
            "SubagentStop は親に文脈を足せない": json.dumps(
                {"hook_event_name": "SubagentStop", "last_assistant_message": REPORT}
            ),
            "壊れた JSON": '{"hook_event_name": ',
            "JSON の配列": "[]",
        }
        for name, stdin in cases.items():
            with self.subTest(name):
                self.assertEqual(cc.run_hook(stdin), "")

    def test_keeps_context_under_the_limit(self) -> None:
        report = "\n".join(f"- 処理{n}は無い" for n in range(1, 400))
        context = self.context(prompt_payload(notification(report)))
        self.assertLessEqual(len(context), cc.HOOK_CONTEXT_LIMIT)
        self.assertTrue(context.endswith("CLI で全体を見る）"))

    def test_passes_when_the_checker_fails(self) -> None:
        out = io.StringIO()
        with (
            mock.patch.object(cc, "run_hook", side_effect=RecursionError),
            mock.patch.object(sys, "stdin", io.StringIO("{}")),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(cc.main(["--hook"]), 0)
        self.assertEqual(out.getvalue(), "")

    def test_runs_as_a_hook_command(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "claim_check.py"), "--hook"],
            input=prompt_payload(notification(REPORT)),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn(
            "L3 不在の主張",
            json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"],
        )


def run_cli(args: list[str], stdin: str = "") -> tuple[int, str]:
    out = io.StringIO()
    with (
        mock.patch.object(sys, "stdin", io.StringIO(stdin)),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        code = cc.main(args)
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def test_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flagged = Path(tmp, "flagged.md")
            flagged.write_text("- フィルタは無い\n", encoding="utf-8")
            clean = Path(tmp, "clean.md")
            clean.write_text("- 根拠は https://example.org\n", encoding="utf-8")
            cases = {
                "拾っても既定は0": ([str(flagged)], 0),
                "--strict で拾えば1": (["--strict", str(flagged)], 1),
                "--strict でも拾わなければ0": (["--strict", str(clean)], 0),
                "読めないファイルは2": ([str(Path(tmp, "none.md"))], 2),
            }
            for name, (args, want) in cases.items():
                with self.subTest(name):
                    self.assertEqual(run_cli(args)[0], want)

    def test_reads_stdin(self) -> None:
        code, out = run_cli([], "- フィルタは無い\n")
        self.assertEqual(code, 0)
        self.assertIn("claim-check: 標準入力", out)
        self.assertIn("L1 不在の主張", out)

    def test_rejects_malformed_repo(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            run_cli(["--repo", "octo", "-"])
        self.assertEqual(raised.exception.code, 2)


class FixtureTest(unittest.TestCase):
    def test_dev_fixtures_match_exactly(self) -> None:
        scores = sf.score_files(sorted((HERE / "fixtures" / "dev").glob("*.md")))
        misses = [miss for score in scores.values() for miss in score.misses]
        self.assertEqual(misses, [])

    def test_blind_fixtures_stay_above_the_first_measurement(self) -> None:
        # blind は調整に使っていない。初回の測定（適合率0.96 / 再現率0.81）を下回らないことだけを見る
        scores = sf.score_files(sorted((HERE / "fixtures" / "blind").glob("*.md")))
        tp = sum(s.tp for s in scores.values())
        fp = sum(s.fp for s in scores.values())
        fn = sum(s.fn for s in scores.values())
        self.assertGreaterEqual(tp / (tp + fp), 0.95)
        self.assertGreaterEqual(tp / (tp + fn), 0.80)


if __name__ == "__main__":
    unittest.main()
