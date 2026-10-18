"""check_skill_parity のテスト。

Usage:
    python3 -m unittest discover -s tools/skill-parity
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_skill_parity as csp  # noqa: E402

FIXTURES = HERE / "fixtures"


def run(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = csp.main(list(args))
    return code, out.getvalue()


def by_name(skills: list[csp.Skill]) -> dict[str, csp.Skill]:
    return {s.entry_name: s for s in skills}


def messages(skill: csp.Skill, level: str) -> list[str]:
    return [f.message for f in skill.findings if f.level == level]


def write_skill(root: Path, rel: str, frontmatter: str, openai_yaml: str | None = None) -> Path:
    skill_dir = root / rel
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"{frontmatter}\n# body\n", encoding="utf-8")
    if openai_yaml is not None:
        (skill_dir / "agents").mkdir()
        (skill_dir / "agents" / "openai.yaml").write_text(openai_yaml, encoding="utf-8")
    return skill_dir


class TempRepo(unittest.TestCase):
    """.claude/skills を正本にし、.agents/skills からシンボリックリンクで共有するリポジトリを作る。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".claude" / "skills").mkdir(parents=True)
        (self.root / ".agents").mkdir()
        (self.root / ".agents" / "skills").symlink_to(Path("..") / ".claude" / "skills")

    def skill(self, name: str, frontmatter: str, openai_yaml: str | None = None) -> None:
        write_skill(self.root, f".claude/skills/{name}", frontmatter, openai_yaml)

    def check(self) -> dict[str, csp.Skill]:
        return by_name(csp.check(self.root, csp.DEFAULT_MAX_DESCRIPTION, csp.DEFAULT_CLAUDE_LISTING_LIMIT))


class FixtureTest(unittest.TestCase):
    def test_drift_fixture_reports_both_directions(self) -> None:
        code, out = run(str(FIXTURES / "drift"))
        self.assertEqual(code, 1, out)
        skills = by_name(csp.check(FIXTURES / "drift", 1024, 1536))
        self.assertEqual(sorted(skills), ["deploy-sample", "release-sample", "report-sample", "review-sample"])
        self.assertEqual(
            {name: (s.claude_auto, s.codex_auto, s.result) for name, s in skills.items()},
            {
                "deploy-sample": (False, True, "NG"),
                "release-sample": (False, False, "ok"),
                "report-sample": (True, True, "ok"),
                "review-sample": (True, False, "NG"),
            },
        )
        self.assertIn("agents/openai.yaml がない", messages(skills["deploy-sample"], "NG")[0])
        self.assertIn("disable-model-invocation: true がない", messages(skills["review-sample"], "NG")[0])

    def test_aligned_fixture_passes(self) -> None:
        code, out = run(str(FIXTURES / "aligned"))
        self.assertEqual(code, 0, out)
        self.assertIn("食い違いはない", out)

    def test_discovery_fixture_reports_unreachable_tools(self) -> None:
        code, out = run(str(FIXTURES / "discovery"))
        self.assertEqual(code, 1, out)
        skills = by_name(csp.check(FIXTURES / "discovery", 1024, 1536))
        self.assertEqual(
            {name: (s.claude_visible, s.codex_visible) for name, s in skills.items()},
            {
                "deploy-sample": (True, False),
                "report-sample": (False, True),
                "review-sample": (False, True),
            },
        )
        self.assertIn(".codex/skills からだけ見える", " ".join(messages(skills["review-sample"], "warn")))
        self.assertEqual(messages(skills["report-sample"], "warn"), [])

    def test_symlinked_roots_count_once(self) -> None:
        skills = csp.check(FIXTURES / "drift", 1024, 1536)
        report = by_name(skills)["report-sample"]
        self.assertEqual(report.via, {".claude/skills", ".agents/skills"})
        self.assertEqual(len(skills), 4)


class PolicyTest(TempRepo):
    def test_codex_reads_only_yaml12_booleans(self) -> None:
        cases = {
            "lowercase false hides": ("false", False),
            "capitalized False hides": ("False", False),
            "uppercase FALSE hides": ("FALSE", False),
            "flow mapping hides": (None, False),
            "yaml11 no is ignored": ("no", True),
            "quoted false is ignored": ('"false"', True),
            "zero is ignored": ("0", True),
        }
        for index, (tn, (value, want_auto)) in enumerate(cases.items()):
            with self.subTest(tn):
                name = f"policy{index}-sample"
                yaml = (
                    "policy: {allow_implicit_invocation: false}\n"
                    if value is None
                    else f"interface:\n  display_name: X\npolicy:\n  # hide\n  allow_implicit_invocation: {value} # c\n"
                )
                self.skill(name, f"---\nname: {name}\ndescription: d\ndisable-model-invocation: true\n---", yaml)
                skill = self.check()[name]
                self.assertEqual(skill.codex_auto, want_auto)
                self.assertEqual(skill.result, "NG" if want_auto else "ok")

    def test_claude_flag_accepts_documented_booleans(self) -> None:
        cases = {
            "true hides": ("true", False),
            "yes hides": ("yes", False),
            "quoted true hides": ('"true"', False),
            "ON hides": ("ON", False),
            "one hides": ("1", False),
            "false keeps auto": ("false", True),
        }
        for index, (tn, (value, want_auto)) in enumerate(cases.items()):
            with self.subTest(tn):
                name = f"flag{index}-sample"
                self.skill(name, f"---\nname: {name}\ndescription: d\ndisable-model-invocation: {value}\n---")
                self.assertEqual(self.check()[name].claude_auto, want_auto)

    def test_unrecognized_claude_flag_is_warned(self) -> None:
        self.skill("maybe-sample", "---\nname: maybe-sample\ndescription: d\ndisable-model-invocation: maybe\n---")
        skill = self.check()["maybe-sample"]
        self.assertTrue(skill.claude_auto)
        self.assertIn("maybe", messages(skill, "warn")[0])

    def test_broken_openai_yaml_is_warned_without_mismatch(self) -> None:
        self.skill(
            "broken-sample",
            "---\nname: broken-sample\ndescription: d\n---",
            "policy:\n  allow_implicit_invocation: no\n",
        )
        skill = self.check()["broken-sample"]
        self.assertEqual(skill.result, "warn")
        self.assertIn("`no`", messages(skill, "warn")[0])


class MetadataTest(TempRepo):
    def test_name_and_description_rules(self) -> None:
        cases = {
            "name differs from directory": (
                "rename-sample",
                "---\nname: other-name\ndescription: d\n---",
                "warn",
                "ディレクトリ名と違い",
            ),
            "name over 64 characters": (
                "long-name-sample",
                f"---\nname: {'n' * 65}\ndescription: d\n---",
                "NG",
                "64文字を超え",
            ),
            "missing description": (
                "nodesc-sample",
                "---\nname: nodesc-sample\n---",
                "NG",
                "description がなく",
            ),
            "empty quoted description": (
                "emptydesc-sample",
                '---\nname: emptydesc-sample\ndescription: ""\n---',
                "NG",
                "description がなく",
            ),
            "description over 1024 characters": (
                "longdesc-sample",
                f"---\nname: longdesc-sample\ndescription: {'x' * 1025}\n---",
                "warn",
                "1025文字で、Codex は1024文字で切る",
            ),
            "description and when_to_use over 1536 characters": (
                "listing-sample",
                f"---\nname: listing-sample\ndescription: {'x' * 1000}\nwhen_to_use: {'y' * 600}\n---",
                "warn",
                "Claude Code は一覧で1536文字で切る",
            ),
            "no frontmatter": ("nofm-sample", "# no frontmatter", "NG", "frontmatter がなく"),
            "unclosed frontmatter": (
                "open-sample",
                "---\nname: open-sample\ndescription: d",
                "NG",
                "閉じる --- がない",
            ),
        }
        for tn, (name, frontmatter, level, needle) in cases.items():
            with self.subTest(tn):
                self.skill(name, frontmatter)
                skill = self.check()[name]
                self.assertTrue(
                    any(needle in m for m in messages(skill, level)),
                    f"{level} に「{needle}」がない: {skill.findings}",
                )

    def test_japanese_description_is_counted_in_characters(self) -> None:
        self.skill("jp-sample", f"---\nname: jp-sample\ndescription: {'あ' * 600}\n---")
        skill = self.check()["jp-sample"]
        self.assertEqual(len(skill.description), 600)
        self.assertEqual(skill.result, "ok")

    def test_limits_can_be_changed(self) -> None:
        self.skill("short-sample", "---\nname: short-sample\ndescription: twelve chars\n---")
        code, out = run(str(self.root), "--max-description", "5")
        self.assertEqual(code, 0, out)
        self.assertIn("Codex は5文字で切る", out)

    def test_multiline_description_forms(self) -> None:
        cases = {
            "folded": ("description: >-\n  first line\n  second line", "first line second line"),
            "literal": ("description: |\n  first line\n  second line", "first line\nsecond line"),
            "plain continuation": ("description: first line\n  second line", "first line second line"),
            "single quoted": ("description: 'it''s quoted: yes'", "it's quoted: yes"),
            "double quoted with comment": ('description: "a: b" # note', "a: b"),
        }
        for index, (tn, (line, want)) in enumerate(cases.items()):
            with self.subTest(tn):
                name = f"multi{index}-sample"
                self.skill(name, f"---\nname: {name}\n{line}\nmetadata:\n  owner: team\n---")
                self.assertEqual(self.check()[name].description, want)


class FixOptionTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "drift"
        shutil.copytree(FIXTURES / "drift", self.root, symlinks=True)

    def test_fix_writes_missing_openai_yaml_only_for_claude_flagged_skills(self) -> None:
        code, out = run(str(self.root), "--fix")
        target = self.root / ".claude" / "skills" / "deploy-sample" / "agents" / "openai.yaml"
        self.assertIn("作成: .claude/skills/deploy-sample/agents/openai.yaml", out)
        self.assertEqual(target.read_text(encoding="utf-8"), csp.OPENAI_YAML_POLICY)
        self.assertFalse((self.root / ".claude" / "skills" / "report-sample" / "agents").exists())
        skills = by_name(csp.check(self.root, 1024, 1536))
        self.assertEqual(skills["deploy-sample"].result, "ok")
        # review-sample は SKILL.md の変更が要るので --fix では直さず、食い違いとして残る
        self.assertEqual(skills["review-sample"].result, "NG")
        self.assertEqual(code, 1, out)

    def test_fix_leaves_repository_fixture_untouched(self) -> None:
        run(str(self.root), "--fix")
        self.assertFalse((FIXTURES / "drift" / ".claude" / "skills" / "deploy-sample" / "agents").exists())


class ArgumentTest(unittest.TestCase):
    def test_missing_root_is_usage_error(self) -> None:
        code, out = run(str(FIXTURES / "does-not-exist"))
        self.assertEqual(code, 2, out)

    def test_root_without_skill_dirs_is_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(tmp)
        self.assertEqual(code, 2, out)


if __name__ == "__main__":
    unittest.main()
