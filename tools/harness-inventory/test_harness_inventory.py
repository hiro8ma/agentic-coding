"""harness_inventory のテスト。

Usage:
    python3 -m unittest discover -s tools/harness-inventory
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

import harness_inventory as hi

FIXTURES = HERE / "fixtures"
REPO = FIXTURES / "repo"
HOME = FIXTURES / "home"


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = hi.main(list(args))
    return code, out.getvalue()


def fixture_report() -> dict:
    roots = [hi.Root("~", HOME, True), hi.Root("repo", REPO, False)]
    return hi.build_report(roots, HOME)


def cell_kinds(items: list[dict]) -> dict[str, int]:
    return {item["kind"]: item["count"] for item in items}


def write(base: Path, rel: str, text: str) -> Path:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def scan(base: Path, user: bool = False, home: Path | None = None) -> hi.Inventory:
    root = hi.Root("r", base, user)
    return hi.Scanner(root, home or base).scan()


def settings(hooks: dict) -> str:
    return json.dumps({"hooks": hooks})


class QuadrantTest(unittest.TestCase):
    def test_fixture_parts_land_in_their_quadrant(self) -> None:
        quadrants = fixture_report()["quadrants"]
        testCases = {
            "guide / computational は文脈を足すイベントの hook": {
                "role": hi.GUIDE,
                "method": hi.COMPUTATIONAL,
                "want": {"hook": 1},
            },
            "guide / inferential は指示ファイル / skill / コマンド / サブエージェント": {
                "role": hi.GUIDE,
                "method": hi.INFERENTIAL,
                "want": {
                    "指示ファイル": 2,
                    "skill": 2,
                    "コマンド": 1,
                    "サブエージェント": 1,
                },
            },
            "sensor / computational は hook / 許可の確認 / PR の CI / 呼ばれる linter": {
                "role": hi.SENSOR,
                "method": hi.COMPUTATIONAL,
                "want": {
                    "hook": 3,
                    "permissions の ask と deny": 2,
                    "execpolicy の prompt と forbidden": 1,
                    "CI": 1,
                    "linter（ruff）": 1,
                },
            },
            "sensor / inferential は prompt の hook / AI の CI / auto モード / レビュー役": {
                "role": hi.SENSOR,
                "method": hi.INFERENTIAL,
                "want": {
                    "hook": 1,
                    "CI": 1,
                    "auto モードの分類器": 1,
                    "承認をモデルに任せる設定": 1,
                    "レビュー役のサブエージェント": 1,
                },
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                got = cell_kinds(quadrants[tc["role"]][tc["method"]])
                self.assertEqual(got, tc["want"])

    def test_fixture_outside_parts(self) -> None:
        got = cell_kinds(fixture_report()["outside"])
        self.assertEqual(
            got,
            {
                "検査を飛ばす許可（allow）": 5,
                "plugin": 1,
                "MCP サーバー": 2,
                "sandbox": 1,
                "PR で動かない CI": 1,
                "知らせる hook": 1,
            },
        )


class HookTest(unittest.TestCase):
    def test_event_and_type_decide_the_quadrant(self) -> None:
        testCases = {
            "PreToolUse の command は sensor / computational": {
                "event": "PreToolUse",
                "type": "command",
                "want": (hi.SENSOR, hi.COMPUTATIONAL),
            },
            "Stop の prompt は sensor / inferential": {
                "event": "Stop",
                "type": "prompt",
                "want": (hi.SENSOR, hi.INFERENTIAL),
            },
            "SubagentStop の agent は sensor / inferential": {
                "event": "SubagentStop",
                "type": "agent",
                "want": (hi.SENSOR, hi.INFERENTIAL),
            },
            "SessionStart の command は guide / computational": {
                "event": "SessionStart",
                "type": "command",
                "want": (hi.GUIDE, hi.COMPUTATIONAL),
            },
            "UserPromptSubmit の http は guide / computational": {
                "event": "UserPromptSubmit",
                "type": "http",
                "want": (hi.GUIDE, hi.COMPUTATIONAL),
            },
            "Notification は知らせる": {
                "event": "Notification",
                "type": "command",
                "want": ("notice", hi.COMPUTATIONAL),
            },
            "知らないイベントはその他": {
                "event": "SomethingNew",
                "type": "command",
                "want": ("other", hi.COMPUTATIONAL),
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                hook = hi.Hook("s", tc["event"], None, tc["type"], "x")
                self.assertEqual((hook.role, hook.method), tc["want"])

    def test_matcher_problems(self) -> None:
        testCases = {
            "空は全件": {"event": "PreToolUse", "matcher": "", "want": False},
            "* は全件": {"event": "PreToolUse", "matcher": "*", "want": False},
            "道具の名前": {"event": "PreToolUse", "matcher": "Bash", "want": False},
            "| で並べた名前": {
                "event": "PostToolUse",
                "matcher": "Edit|Write",
                "want": False,
            },
            "空白と , で並べた名前": {
                "event": "PostToolUse",
                "matcher": "Edit, Write",
                "want": False,
            },
            "正規表現": {"event": "PreToolUse", "matcher": "mcp__.*", "want": False},
            "式の形は一致しない": {
                "event": "PostToolUse",
                "matcher": 'tool == "Bash"',
                "want": True,
            },
            "|| の式も一致しない": {
                "event": "PostToolUse",
                "matcher": 'tool == "Write" || tool == "Edit"',
                "want": True,
            },
            "matcher を読まないイベントは無視される": {
                "event": "Stop",
                "matcher": "Bash",
                "want": True,
            },
            "SessionStart の matcher は読まれる": {
                "event": "SessionStart",
                "matcher": "startup|resume",
                "want": False,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(
                    bool(hi.matcher_problem(tc["event"], tc["matcher"])), tc["want"]
                )

    def test_labels_and_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "repo"
            home = Path(tmp) / "home"
            write(base, ".claude/hooks/guard.py", "")
            write(base, "tools/push-guard/push_guard.py", "")
            write(home, ".claude/hooks/notify.sh", "")
            testCases = {
                "CLAUDE_PROJECT_DIR のスクリプト": {
                    "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"',
                    "user": False,
                    "want": ("guard", True, ["guard"]),
                },
                "相対のパスはルートから": {
                    "command": "bash -c 'cd \"${CLAUDE_PROJECT_DIR:-.}\" && .claude/hooks/guard.py'",
                    "user": False,
                    "want": ("guard", True, ["guard"]),
                },
                "tools の下はディレクトリ名も名前にする": {
                    "command": 'python3 "$CLAUDE_PROJECT_DIR/tools/push-guard/push_guard.py"',
                    "user": False,
                    "want": ("push_guard", True, ["push-guard"]),
                },
                "HOME のスクリプト": {
                    "command": 'f="${HOME-}/.claude/hooks/notify.sh"; [ -f "$f" ] && sh "$f"',
                    "user": True,
                    "want": ("notify", True, ["notify"]),
                },
                "見つからないスクリプト": {
                    "command": "python3 ~/.claude/hooks/gone.py",
                    "user": True,
                    "want": ("gone", False, ["gone"]),
                },
                "利用者の設定の相対のパスは確かめられない": {
                    "command": "python3 hooks/guard.py",
                    "user": True,
                    "want": ("guard", None, ["guard"]),
                },
                "存在するほうのスクリプトを名前にする": {
                    "command": "if win; then ~/.claude/hooks/notify.cmd; else ~/.claude/hooks/notify.sh; fi",
                    "user": True,
                    "want": ("notify", True, ["notify"]),
                },
                "npx は版を除いたパッケージの名前": {
                    "command": "npx -y sample-formatter@1.2.0 --hook",
                    "user": False,
                    "want": ("sample-formatter", None, ["sample-formatter"]),
                },
                "スクリプトがなければ最初の語": {
                    "command": "afplay /System/Library/Sounds/Ping.aiff",
                    "user": True,
                    "want": ("afplay", None, ["afplay"]),
                },
                "複数行はインラインのスクリプト": {
                    "command": '#!/bin/bash\ninput=$(cat)\necho "$input"',
                    "user": False,
                    "want": ("（インラインのスクリプト）", None, []),
                },
            }
            for tn, tc in testCases.items():
                with self.subTest(tn):
                    root = hi.Root("r", home if tc["user"] else base, tc["user"])
                    scanner = hi.Scanner(root, home)
                    hook = hi.Hook("s", "PreToolUse", None, "command", "")
                    scanner.label_command(hook, tc["command"])
                    self.assertEqual(
                        (hook.label, hook.script_found, hook.keys), tc["want"]
                    )

    def test_if_on_non_tool_event_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            hook = {"type": "command", "command": "echo x", "if": "Bash(git *)"}
            write(
                base, ".claude/settings.json", settings({"Stop": [{"hooks": [hook]}]})
            )
            findings = [f.message for f in scan(base).findings]
            self.assertTrue(any("if は道具のイベント" in m for m in findings), findings)


class PermissionTest(unittest.TestCase):
    def test_permission_keys(self) -> None:
        testCases = {
            "Bash の :* を外す": {
                "entry": "Bash(gh pr merge:*)",
                "want": ["gh pr merge"],
            },
            "Bash の * を外す": {
                "entry": "Bash(git push --force *)",
                "want": ["git push --force"],
            },
            "パスの ./ を外す": {"entry": "Read(./.env.local)", "want": [".env.local"]},
            "括弧のない道具は道具の名前": {"entry": "WebFetch", "want": ["webfetch"]},
            "* だけは名前にしない": {"entry": "Bash(*)", "want": []},
            "短すぎる名前は使わない": {"entry": "Bash(ls:*)", "want": []},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(hi.permission_keys(tc["entry"]), tc["want"])

    def test_auto_mode_by_scope(self) -> None:
        testCases = {
            "利用者の設定の auto は分類器の sensor": {
                "user": True,
                "want_sensor": True,
                "want_finding": False,
            },
            "プロジェクトの auto は効かないと出す": {
                "user": False,
                "want_sensor": True,
                "want_finding": True,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                write(
                    base,
                    ".claude/settings.json",
                    json.dumps({"permissions": {"defaultMode": "auto"}}),
                )
                inv = scan(base, user=tc["user"])
                kinds = [p.kind for p in inv.parts]
                self.assertEqual("auto モードの分類器" in kinds, tc["want_sensor"])
                self.assertEqual(
                    any("効かない" in f.message for f in inv.findings),
                    tc["want_finding"],
                )


class ParserTest(unittest.TestCase):
    def test_read_toml(self) -> None:
        text = (
            'model = "m"  # comment\n'
            "approval_policy = 'never'\n"
            "notify = [\n"
            '  "a",\n'
            '  ["nested", "array"]\n'
            "]\n"
            'note = """\n'
            "[not_a_table]\n"
            '"""\n'
            'sandbox_mode = "read-only"\n'
            "[mcp_servers.docs]\n"
            'sandbox_mode = "inside-a-table"\n'
            "[mcp_servers.docs.tools.search]\n"
            '[projects."/srv/a.b"]\n'
        )
        top, tables = hi.read_toml(text)
        self.assertEqual(
            {k: top[k] for k in ("model", "approval_policy", "sandbox_mode")},
            {"model": "m", "approval_policy": "never", "sandbox_mode": "read-only"},
        )
        self.assertEqual(
            tables,
            [
                ["mcp_servers", "docs"],
                ["mcp_servers", "docs", "tools", "search"],
                ["projects", "/srv/a.b"],
            ],
        )

    def test_parse_exec_rules(self) -> None:
        text = (
            'prefix_rule(pattern=["git", "status"], decision="allow")\n'
            'prefix_rule(pattern=["git", "log"])\n'
            '# prefix_rule(pattern=["rm"], decision="forbidden")\n'
            "prefix_rule(\n"
            '    pattern = ["gh", "pr", ["merge", "close"]],\n'
            '    decision = "prompt",\n'
            ")\n"
            "prefix_rule(pattern=['rm', '-rf'], decision='forbidden')\n"
        )
        self.assertEqual(
            hi.parse_exec_rules(text),
            [
                ("allow", ["git", "status"]),
                ("allow", ["git", "log"]),
                ("prompt", ["gh", "pr"]),
                ("forbidden", ["rm", "-rf"]),
            ],
        )

    def test_workflow_triggers(self) -> None:
        testCases = {
            "1行の on": {"text": "on: push\n", "want": "push のたび"},
            "配列の on": {"text": "on: [push, pull_request]\n", "want": hi.ON_PR},
            "ブロックの on": {
                "text": "on:\n  schedule:\n    - cron: '0 0 * * 1'\n  workflow_dispatch:\njobs:\n  a:\n",
                "want": "定期",
            },
            "引用符の on と merge_group": {
                "text": '"on":\n  merge_group:\n  push:\n    branches: [main]\n',
                "want": hi.ON_PR,
            },
            "手動だけ": {"text": "on:\n  workflow_dispatch:\n", "want": "手動"},
            "ほかの workflow から呼ばれる": {
                "text": "on:\n  workflow_call:\n    inputs:\n      a:\n",
                "want": "ほかの workflow から呼ばれる",
            },
            "on がない": {"text": "name: x\n", "want": "起動の条件が読めない"},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                triggers = hi.parse_workflow(tc["text"])
                self.assertEqual(hi.trigger_class(triggers), tc["want"])

    def test_ai_steps(self) -> None:
        testCases = {
            "claude-code-action": {
                "text": "- uses: anthropics/claude-code-action@v1",
                "want": True,
            },
            "codex exec": {"text": "- run: codex exec 'review'", "want": True},
            "claude -p": {"text": "- run: claude -p 'review'", "want": True},
            "名前の一部は数えない": {
                "text": "- run: ./claude-pipeline.sh",
                "want": False,
            },
            "LLM を使わない手順": {"text": "- run: ruff check .", "want": False},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                self.assertEqual(bool(hi._AI_STEP.search(tc["text"])), tc["want"])


class RuleBackingTest(unittest.TestCase):
    def test_fixture_rule_summary(self) -> None:
        rules = fixture_report()["rules"]
        self.assertEqual(
            {
                k: rules[k]
                for k in (
                    "total",
                    "backed",
                    "mentioned_without_sensor",
                    "recurring",
                    "recurring_backed",
                )
            },
            {
                "total": 7,
                "backed": 4,
                "mentioned_without_sensor": 1,
                "recurring": 3,
                "recurring_backed": 1,
            },
        )
        backed = {r["title"].split()[0]: r["sensors"] for r in rules["backed_rules"]}
        self.assertEqual(backed["Do"], ["hook（PreToolUse）「secret_guard」"])
        self.assertEqual(backed["Lint"], ["linter「ruff」"])
        self.assertEqual(backed["Ask"], backed["gh"])
        self.assertEqual(
            backed["gh"],
            [
                "execpolicy の prompt「gh pr merge」",
                "permissions の ask「Bash(gh pr merge:*)」",
            ],
        )

    def test_names_match_rules(self) -> None:
        sensor = hi.Sensor(
            "hook（PreToolUse）", "push_guard", "s", hi.name_keys("push_guard")
        )
        testCases = {
            "名前がそのまま出る": {
                "text": "- Stop pushes with push_guard\n",
                "want": True,
            },
            "_ と - を同じに読む": {"text": "- `push-guard` が止める\n", "want": True},
            "大文字と小文字を問わない": {
                "text": "- Push-Guard stops it\n",
                "want": True,
            },
            "和文に続く名前": {"text": "- push-guardで止める\n", "want": True},
            "Why の中の名前も数える": {
                "text": "- push しない\n  - **Why:** 2025-01-02 push-guard を入れた\n",
                "want": True,
            },
            "長い語の一部は数えない": {
                "text": "- push-guardian に任せる\n",
                "want": False,
            },
            "hook と書くだけでは数えない": {
                "text": "- push は hook で止める\n",
                "want": False,
            },
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                rules = hi.rule_loops.audit_text(tc["text"], "a.md")
                hits = hi.match_rules(rules, [sensor])
                self.assertEqual(bool(hits[0]), tc["want"])

    def test_section_rule_does_not_count_its_items(self) -> None:
        text = "## A\n\nSection prose\n\n- use push-guard\n- other rule\n"
        rules = hi.rule_loops.audit_text(text, "a.md")
        sensor = hi.Sensor("hook", "push-guard", "s", ["push-guard"])
        hits = dict(zip((r.title for r in rules), hi.match_rules(rules, [sensor])))
        self.assertEqual(
            {title: bool(found) for title, found in hits.items()},
            {"A": False, "use push-guard": True, "other rule": False},
        )

    def test_only_sensor_hooks_back_rules(self) -> None:
        hooks = [
            hi.Hook(
                "s",
                "SessionStart",
                None,
                "command",
                "load-context",
                keys=["load-context"],
            ),
            hi.Hook("s", "Stop", None, "prompt", "prompt: x", keys=["prompt-x"]),
            hi.Hook(
                "s", "Stop", None, "command", "answer-check", keys=["answer-check"]
            ),
            hi.Hook(
                "s",
                "SubagentStop",
                None,
                "command",
                "answer-check",
                keys=["answer-check"],
            ),
        ]
        self.assertEqual([s.name for s in hi.hook_sensors(hooks)], ["answer-check"])

    def test_linter_needs_a_caller_to_be_a_sensor(self) -> None:
        testCases = {
            "CI が呼ぶ linter は sensor": {
                "files": {
                    ".github/workflows/ci.yml": "on: pull_request\njobs:\n  a:\n    steps:\n      - run: ruff check .\n"
                },
                "want": ["ruff"],
            },
            "pre-commit が呼ぶ linter は sensor": {
                "files": {
                    ".pre-commit-config.yaml": (
                        "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
                        "    hooks:\n      - id: ruff\n"
                    )
                },
                "want": ["ruff"],
            },
            "どこからも呼ばれない linter は sensor にしない": {"files": {}, "want": []},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                write(base, "ruff.toml", "line-length = 100\n")
                for rel, text in tc["files"].items():
                    write(base, rel, text)
                inv = scan(base)
                self.assertEqual(
                    [s.name for s in inv.sensors if s.kind == "linter"], tc["want"]
                )

    def test_only_pr_workflows_are_ci_sensors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, ".github/workflows/test.yml", "on: [pull_request]\n")
            write(base, ".github/workflows/deploy.yml", "on:\n  push:\n")
            write(
                base,
                ".github/workflows/review.yml",
                "on: pull_request\nsteps:\n  - uses: openai/codex-action@v1\n",
            )
            inv = scan(base)
            self.assertEqual(
                [s.name for s in inv.sensors if s.kind == "CI"], ["test.yml"]
            )
            got = {(p.role, p.method, p.note) for p in inv.parts if "CI" in p.kind}
            self.assertEqual(
                got,
                {
                    (hi.SENSOR, hi.COMPUTATIONAL, ""),
                    (hi.SENSOR, hi.INFERENTIAL, ""),
                    (hi.OUTSIDE, "", "push のたび"),
                },
            )


class DiscoveryTest(unittest.TestCase):
    def test_project_walk_skips_noise_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for rel in (
                "AGENTS.md",
                "pkg/AGENTS.md",
                "pkg/CLAUDE.md",
                ".claude/CLAUDE.md",
                ".claude/rules/go.md",
                "node_modules/x/AGENTS.md",
                "tools/fixtures/AGENTS.md",
                ".hidden/AGENTS.md",
            ):
                write(base, rel, "- rule\n")
            shown = sorted(name for name, _ in scan(base).instructions)
            self.assertEqual(
                shown,
                [
                    "r/.claude/CLAUDE.md",
                    "r/.claude/rules/go.md",
                    "r/AGENTS.md",
                    "r/pkg/AGENTS.md",
                    "r/pkg/CLAUDE.md",
                ],
            )

    def test_linked_instruction_file_is_read_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            write(home, ".claude/CLAUDE.md", "- one\n- two\n")
            (home / ".codex").mkdir()
            (home / ".codex" / "AGENTS.md").symlink_to(home / ".claude" / "CLAUDE.md")
            report = hi.build_report([hi.Root("~", home, True)], home)
            self.assertEqual(report["rules"]["total"], 2)
            self.assertEqual(
                report["instruction_files"],
                [
                    {"file": "~/.claude/CLAUDE.md", "same_as": ""},
                    {"file": "~/.codex/AGENTS.md", "same_as": "~/.claude/CLAUDE.md"},
                ],
            )

    def test_skills_without_skill_md_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, ".claude/skills/good/SKILL.md", "x")
            write(base, ".claude/skills/loose.md", "x")
            write(base, ".claude/skills/empty/README.md", "x")
            write(base, ".claude/skills/.system/SKILL.md", "x")
            inv = scan(base)
            self.assertEqual(
                [(p.kind, p.count) for p in inv.parts if p.kind == "skill"],
                [("skill", 1)],
            )
            self.assertEqual(
                [f.message for f in inv.findings],
                ["SKILL.md の無い項目2件は skill として読まれない（empty / loose.md）"],
            )

    def test_broken_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write(base, ".claude/settings.json", "{not json")
            self.assertEqual(
                [f.message for f in scan(base).findings], ["JSON として読めない"]
            )


class MainTest(unittest.TestCase):
    def test_exit_codes(self) -> None:
        testCases = {
            "fixture は0": {
                "args": ["--home", str(HOME), "--user", str(REPO)],
                "want": 0,
            },
            "ないディレクトリは2": {"args": [str(HERE / "no-such-dir")], "want": 2},
            "ルートも --user もなければ2": {"args": [], "want": 2},
        }
        for tn, tc in testCases.items():
            with self.subTest(tn):
                code, _ = run(*tc["args"])
                self.assertEqual(code, tc["want"])

    def test_json_and_markdown(self) -> None:
        code, out = run("--json", "--home", str(HOME), "--user", str(REPO))
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["rules"]["backed_ratio"], round(4 / 7, 4))
        code, out = run("--home", str(HOME), "--user", str(REPO))
        self.assertEqual(code, 0)
        self.assertIn("本文か Why に出る規則4件（57.1%）", out)
        self.assertIn("## 確かめること", out)


if __name__ == "__main__":
    unittest.main()
