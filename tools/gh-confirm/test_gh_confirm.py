"""gh_confirm のテスト。

Usage:
    python3 -m unittest discover -s tools/gh-confirm
"""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gh_confirm as ghc

AUTO = f"（{ghc.AUTO_NOTE}）"
ADMIN = f"（{ghc.ADMIN_NOTE}）"

ASK_CASES: dict[str, tuple[str, list[str]]] = {
    "pr edit の番号と依頼先を読む": (
        "gh pr edit 12 --add-reviewer alice",
        ["レビュー依頼: #12 に alice"],
    ),
    "--add-reviewer= の形とカンマ区切りを読む": (
        "gh pr edit 12 --add-reviewer=alice,bob",
        ["レビュー依頼: #12 に alice, bob"],
    ),
    "--add-reviewer を重ね、番号がなければ現在のブランチ": (
        'gh pr edit --title "Fix" --add-reviewer alice --add-reviewer octo/core',
        ["レビュー依頼: 現在のブランチの PR に alice, octo/core"],
    ),
    "URL から repo と番号を読む": (
        "gh pr edit https://github.com/octo/app/pull/7 --add-reviewer @copilot",
        ["レビュー依頼: octo/app#7 に @copilot"],
    ),
    "subcommand の前の -R を repo にする": (
        "gh pr -R octo/app edit 7 --add-reviewer alice",
        ["レビュー依頼: octo/app#7 に alice"],
    ),
    "subcommand の前の --repo= を repo にする": (
        "gh pr --repo=octo/app merge 12",
        ["マージ: octo/app#12"],
    ),
    "後ろの --repo= を repo にする": (
        "gh pr edit 7 --add-reviewer alice --repo=octo/app",
        ["レビュー依頼: octo/app#7 に alice"],
    ),
    "ブランチ名で指定した PR": (
        "gh pr edit fix-login --add-reviewer alice",
        ["レビュー依頼: ブランチ fix-login の PR に alice"],
    ),
    "値を取るフラグの値を PR と取り違えない": (
        'gh pr edit -b "draft" -t 99 12 --add-reviewer alice',
        ["レビュー依頼: #12 に alice"],
    ),
    "pr create の --reviewer": (
        'gh pr create --title "Fix" --body "x" --reviewer alice',
        ["レビュー依頼: 新しく作る PR に alice"],
    ),
    "pr create の短いフラグの書き方を読む": (
        "gh pr create -dralice -r=bob -r carol",
        ["レビュー依頼: 新しく作る PR に alice, bob, carol"],
    ),
    "pr new は pr create の別名": (
        "gh pr new -f -r alice",
        ["レビュー依頼: 新しく作る PR に alice"],
    ),
    "REST の requested_reviewers に -f / -F を付けると POST": (
        (
            "gh api repos/octo/app/pulls/12/requested_reviewers"
            " -f 'reviewers[]=alice' -F 'team_reviewers[]=core'"
        ),
        ["レビュー依頼: octo/app#12 に alice, team:core"],
    ),
    "REST の requested_reviewers に -X POST と --input": (
        (
            "gh api -X POST /repos/{owner}/{repo}/pulls/12/requested_reviewers"
            " --input reviewers.json"
        ),
        ["レビュー依頼: #12（依頼先は読めない）"],
    ),
    "--input だけでも POST": (
        "gh api repos/octo/app/pulls/5/requested_reviewers --input body.json",
        ["レビュー依頼: octo/app#5（依頼先は読めない）"],
    ),
    "--method=post の小文字": (
        "gh api --method=post repos/octo/app/pulls/3/requested_reviewers",
        ["レビュー依頼: octo/app#3（依頼先は読めない）"],
    ),
    "GraphQL の requestReviews": (
        (
            "gh api graphql -f query='mutation { requestReviews(input: "
            '{pullRequestId: "PR_1", userIds: ["U_1"]}) { clientMutationId } }\''
        ),
        ["レビュー依頼: GraphQL の requestReviews で指定する PR（依頼先は読めない）"],
    ),
    "pr merge の番号を読む": (
        "gh pr merge 12 --squash --delete-branch",
        ["マージ: #12"],
    ),
    "--auto を理由に書く": (
        "gh pr merge --auto -s 12",
        [f"マージ: #12{AUTO}"],
    ),
    "--admin を理由に書き、merge の -r は値を取らない": (
        "gh pr merge -r 12 --admin",
        [f"マージ: #12{ADMIN}"],
    ),
    "番号のない pr merge は現在のブランチ": (
        "gh pr merge",
        ["マージ: 現在のブランチの PR"],
    ),
    "REST の merge に PUT": (
        "gh api -X PUT repos/octo/app/pulls/12/merge -f merge_method=squash",
        ["マージ: octo/app#12"],
    ),
    "GraphQL の enablePullRequestAutoMerge": (
        (
            "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: "
            '{pullRequestId: "PR_1"}) { clientMutationId } }\''
        ),
        [f"マージ: GraphQL の enablePullRequestAutoMerge で指定する PR{AUTO}"],
    ),
    "GraphQL の mergePullRequest": (
        (
            "gh api graphql -f query='mutation { mergePullRequest(input: "
            '{pullRequestId: "PR_1"}) { clientMutationId } }\''
        ),
        ["マージ: GraphQL の mergePullRequest で指定する PR"],
    ),
    "&& の後ろ": ("git push origin fix && gh pr merge 12", ["マージ: #12"]),
    "; と | と || の間": (
        "gh pr view 12; gh pr merge 12 | cat || true",
        ["マージ: #12"],
    ),
    "改行の後ろ": ("gh pr checks 12\ngh pr merge 12", ["マージ: #12"]),
    "二重引用符の中の $( )": ('echo "merged: $(gh pr merge 12)"', ["マージ: #12"]),
    "バッククォートの中": ("result=`gh pr merge 12`", ["マージ: #12"]),
    "入れ子のバッククォート": ("x=`echo \\`gh pr merge 12\\``", ["マージ: #12"]),
    "$( ) の中のサブシェルの後ろ": (
        'echo "$( (cd app); gh pr merge 12 )"',
        ["マージ: #12"],
    ),
    "<( ) の中": ("diff <(gh pr merge 12) /dev/null", ["マージ: #12"]),
    "bash -c の文字列": ('bash -c "gh pr merge 12"', ["マージ: #12"]),
    "bash -lc の中の &&": (
        "bash -lc 'cd app && gh pr edit 3 --add-reviewer alice'",
        ["レビュー依頼: #3 に alice"],
    ),
    "シェルの長いオプションと値を取るオプションの後の標準入力": (
        "bash --norc -o pipefail <<'EOF'\ngh pr merge 12\nEOF",
        ["マージ: #12"],
    ),
    "入れ子の sh -c": ("sh -c \"bash -c 'gh pr merge 12'\"", ["マージ: #12"]),
    "eval の文字列": ('eval "gh pr merge 12"', ["マージ: #12"]),
    "env と変数の代入": (
        "env GH_REPO=octo/app GH_PROMPT_DISABLED=1 gh pr merge 12",
        ["マージ: #12"],
    ),
    "前に置いた変数の代入": ("GH_TOKEN=x gh pr merge 12", ["マージ: #12"]),
    "前に付けて実行するコマンドを重ねる": (
        "sudo -u bot timeout 30 nice -n 5 command gh pr merge 12",
        ["マージ: #12"],
    ),
    "nohup / time -p / exec を前に付ける": (
        "nohup time -p exec gh pr merge 12",
        ["マージ: #12"],
    ),
    "エイリアスを避ける \\gh": ("\\gh pr merge 12", ["マージ: #12"]),
    "gh をパスで呼ぶ": ("/opt/homebrew/bin/gh pr merge 12", ["マージ: #12"]),
    "xargs で PR を渡す": (
        "gh pr list -q '.[].number' --json number | xargs -I{} gh pr merge {} -s",
        ["マージ: xargs で渡す PR"],
    ),
    "if の条件": ("if gh pr merge 12; then echo ok; fi", ["マージ: #12"]),
    "サブシェルと { } の中": (
        "(cd app && gh pr merge 12) && { gh pr merge 13; }",
        ["マージ: #12", "マージ: #13"],
    ),
    "シェルに流すヒアドキュメント": (
        "bash <<'EOF'\ngh pr merge 12\nEOF",
        ["マージ: #12"],
    ),
    "シェルに流すヒアストリング": ('bash <<< "gh pr merge 12"', ["マージ: #12"]),
    "区切りを引用符で囲まないヒアドキュメントの $( )": (
        "cat <<EOF\n$(gh pr merge 12)\nEOF",
        ["マージ: #12"],
    ),
    "&> の先を PR と取り違えない": ("gh pr merge &>merge.log 12", ["マージ: #12"]),
    "タブを除くヒアドキュメントの本文は見ず、後ろを見る": (
        "cat <<-EOF\n\tgh pr edit 1 --add-reviewer alice\n\tEOF\ngh pr merge 12",
        ["マージ: #12"],
    ),
    "行の継続": ("gh pr merge \\\n  12 --squash", ["マージ: #12"]),
    "リダイレクトの先と fd を PR と取り違えない": (
        "gh pr merge 2>&1 >merge.log 12",
        ["マージ: #12"],
    ),
    "本文のヒアドキュメントに ' と ) があっても後ろの --reviewer を読む": (
        (
            'gh pr create --title "Fix" --body "$(cat <<\'EOF\'\n'
            "Don't merge yet (see 1) below\n"
            'Then run "gh pr merge"\n'
            'EOF\n)" --reviewer alice'
        ),
        ["レビュー依頼: 新しく作る PR に alice"],
    ),
    "複数の操作を並べる": (
        "gh pr edit 12 --add-reviewer alice && gh pr merge 12 --auto",
        ["レビュー依頼: #12 に alice", f"マージ: #12{AUTO}"],
    ),
    "同じ操作は1つにまとめる": ("gh pr merge 12; gh pr merge 12", ["マージ: #12"]),
}

PASS_CASES: dict[str, str] = {
    "PR を読むだけ": "gh pr view 12 --json title,body",
    "一覧と checks と diff": "gh pr list && gh pr checks 12 && gh pr diff 12",
    "タイトルと本文の編集": 'gh pr edit 12 --title "Fix" --body-file body.md',
    "レビュアーを外す": "gh pr edit 12 --remove-reviewer alice",
    "本文に --reviewer を含む PR の作成": (
        'gh pr create --draft --title "gh pr merge" --body "add --reviewer later"'
    ),
    "--reviewer のない PR の作成": "gh pr create --fill --draft",
    "echo の引数": "echo gh pr merge 12",
    "echo の二重引用符の中": 'echo "gh pr merge 12 --add-reviewer alice"',
    "単一引用符の中の $( )": "echo '$(gh pr merge 12)'",
    "エスケープした $( )": 'echo "\\$(gh pr merge 12)"',
    "$'...' の中の \\' と $( )": "echo $'it\\'s $(gh pr merge 12)'",
    "grep で探す": 'grep -rn -- --add-reviewer . | grep "gh pr merge"',
    "rg と sed で探す": "rg 'gh pr merge' docs && sed -n '/requestReviews/p' notes.md",
    "ヒアドキュメントの本文": (
        "cat <<'EOF' > notes.md\ngh pr merge 12\ngh pr edit 1 --add-reviewer alice\nEOF"
    ),
    "区切りを引用符で囲んだヒアドキュメントの $( )": "cat <<'EOF'\n$(gh pr merge 12)\nEOF",
    "引用符なしのヒアドキュメントでエスケープした $( )": (
        "cat <<EOF\n\\$(gh pr merge 12)\nEOF"
    ),
    "PR のコメントの本文": 'gh pr comment 12 --body "please gh pr merge 12"',
    "コメント": "# gh pr merge 12",
    "行末のコメントの中の ; の後ろ": "git status # then; gh pr merge 12",
    "コミットのメッセージ": 'git commit -m "gh pr merge 12 --auto をやめる"',
    "git の merge": "git merge --no-ff main",
    "requested_reviewers を読む": "gh api repos/octo/app/pulls/12/requested_reviewers",
    "requested_reviewers から外す": (
        "gh api -X DELETE repos/octo/app/pulls/12/requested_reviewers"
        " -f 'reviewers[]=alice'"
    ),
    "マージ済みかを確かめる": "gh api repos/octo/app/pulls/12/merge",
    "GraphQL で読む": "gh api graphql -f query='query { viewer { login } }'",
    "Issue の編集": "gh issue edit 3 --add-assignee alice",
    "名前が gh で始まる別のコマンド": "ghq get github.com/octo/app",
    "シェルでスクリプトのファイルを動かす": "bash scripts/release.sh",
    "python -c の文字列": "python3 -c \"print('gh pr merge 12')\"",
    "printf でファイルに書く": "printf '%s\\n' 'gh pr merge 12' > cmd.txt",
    "command -v で場所を調べる": "command -v gh",
    "算術展開と変数の展開": "echo $((1 + 2)) ${PWD}",
    "閉じていない引用符": 'gh pr view "12',
}


class ScanTest(unittest.TestCase):
    def test_finds_actions_that_need_confirmation(self) -> None:
        for name, (command, want) in ASK_CASES.items():
            with self.subTest(name):
                got = [finding.describe() for finding in ghc.scan(command)]
                self.assertEqual(got, want)

    def test_passes_commands_that_do_not_run_those_actions(self) -> None:
        for name, command in PASS_CASES.items():
            with self.subTest(name):
                self.assertEqual(ghc.scan(command), [])


def run_hook(stdin: str, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    stdin_patch = mock.patch.object(sys, "stdin", io.StringIO(stdin))
    with stdin_patch, contextlib.redirect_stdout(out):
        code = ghc.main(list(args))
    return code, out.getvalue()


def bash_payload(command: object) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


class HookTest(unittest.TestCase):
    def test_claude_code_asks_with_targets_in_reason(self) -> None:
        code, out = run_hook(
            bash_payload("gh pr edit 12 --add-reviewer alice && gh pr merge 12 --auto")
        )
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(set(result), {"hookSpecificOutput"})
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], "ask")
        self.assertEqual(
            specific["permissionDecisionReason"].splitlines()[1:3],
            ["- レビュー依頼: #12 に alice", f"- マージ: #12{AUTO}"],
        )

    def test_codex_denies_and_shows_the_reason_to_the_user(self) -> None:
        code, out = run_hook(bash_payload("gh pr merge 12"), "--codex")
        self.assertEqual(code, 0)
        result = json.loads(out)
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("- マージ: #12", specific["permissionDecisionReason"])
        self.assertIn("利用者が自分で実行する", specific["permissionDecisionReason"])
        self.assertEqual(result["systemMessage"], specific["permissionDecisionReason"])

    def test_reads_command_given_as_argv(self) -> None:
        _, out = run_hook(bash_payload(["bash", "-lc", "gh pr merge 12"]))
        self.assertEqual(
            json.loads(out)["hookSpecificOutput"]["permissionDecision"], "ask"
        )

    def test_passes_silently(self) -> None:
        cases = {
            "確認の要らないコマンド": bash_payload("gh pr view 12"),
            "壊れた JSON": '{"tool_name": "Bash", ',
            "空の入力": "",
            "JSON の配列": "[]",
            "Bash 以外のツール": json.dumps(
                {"tool_name": "Write", "tool_input": {"command": "gh pr merge 12"}}
            ),
            "command がない": json.dumps({"tool_name": "Bash", "tool_input": {}}),
            "command が文字列でない": bash_payload(12),
        }
        for name, stdin in cases.items():
            with self.subTest(name):
                self.assertEqual(run_hook(stdin), (0, ""))

    def test_passes_when_the_parser_fails(self) -> None:
        with mock.patch.object(ghc, "scan", side_effect=RecursionError):
            self.assertEqual(run_hook(bash_payload("gh pr merge 12")), (0, ""))

    def test_runs_as_a_hook_command(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "gh_confirm.py")],
            input=bash_payload("gh pr merge 12"),
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(proc.stdout)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "ask")


CODEX_RULES_CASES: dict[str, dict[str, str | None]] = {
    "gh-merge.rules": {
        "gh pr merge 12 --squash": "prompt",
        "gh pr merge --auto 12": "prompt",
        "gh pr view 12": None,
        "gh pr edit 12 --add-reviewer alice": None,
    },
    "gh-pr-write.rules": {
        "gh pr edit 12 --add-reviewer alice": "prompt",
        "gh pr create -t fix -r alice": "prompt",
        "gh pr merge 12": None,
        "gh api graphql -f query=x": None,
    },
}


@unittest.skipUnless(shutil.which("codex"), "Codex CLI がない")
class CodexRulesTest(unittest.TestCase):
    def test_decisions(self) -> None:
        for rules, cases in CODEX_RULES_CASES.items():
            for command, want in cases.items():
                with self.subTest(rules=rules, command=command):
                    proc = subprocess.run(
                        ["codex", "execpolicy", "check", "--rules", str(HERE / rules)]
                        + ["--", *shlex.split(command)],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    self.assertEqual(json.loads(proc.stdout).get("decision"), want)


if __name__ == "__main__":
    unittest.main()
