import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).with_name("leak-scan.py")
spec = importlib.util.spec_from_file_location("leak_scan", HOOK)
leak_scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(leak_scan)

# 実在の鍵やパスを置かないよう、形だけを実行時に組み立てる
GEMINI_KEY = "AQ" + "." + "A" * 50
LOCAL_PATH = "/" + "Users" + "/someone"


def write_patterns(directory, body):
    path = Path(directory) / "patterns.tsv"
    path.write_text(body, encoding="utf-8")
    return str(path)


class ScanTest(unittest.TestCase):
    def test_public_patterns(self):
        public = [(label, re.compile(rx)) for label, rx in leak_scan.PATTERNS.items()]
        cases = {
            "Gemini の鍵の形は止める": (f"key = {GEMINI_KEY}", True),
            "形の名前だけを書いた文は止めない": ("`AQ.` の形式も検査する", False),
            "ローカルパスは止める": (f"cd {LOCAL_PATH}/repo", True),
            "関係の無い文は止めない": ("hello world", False),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(bool(leak_scan.scan(text, public)), want)

    def test_private_patterns_are_read_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_patterns(
                d,
                "# コメント\n"
                "顧客\t(?<![A-Za-z])ACME(?![A-Za-z])\n"
                "大文字小文字を区別しない\t(?i)\\bexamplecorp\\b\n",
            )
            patterns = leak_scan.load_private_patterns(path)
        cases = {
            "語として出たら止める": ("ACME の記事", True),
            "語の一部なら止めない": ("ACMEX の記事", False),
            "(?i) を付けた形は大文字でも止める": ("EXAMPLECORP", True),
            "どれにも当たらない": ("other", False),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(bool(leak_scan.scan(text, patterns)), want)

    def test_missing_or_broken_file_is_ignored(self):
        self.assertEqual(
            leak_scan.load_private_patterns("/nonexistent/patterns.tsv"), []
        )
        with tempfile.TemporaryDirectory() as d:
            path = write_patterns(d, "タブの無い行\n壊れた形\t(\n正しい形\tOK\n")
            patterns = leak_scan.load_private_patterns(path)
        self.assertEqual([label for label, _ in patterns], ["正しい形"])

    def test_env_selects_private_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_patterns(d, "テスト専用のラベル\tACME\n")
            old = os.environ.get(leak_scan.PRIVATE_PATTERNS_ENV)
            os.environ[leak_scan.PRIVATE_PATTERNS_ENV] = path
            try:
                labels = [label for label, _ in leak_scan.all_patterns()]
            finally:
                if old is None:
                    del os.environ[leak_scan.PRIVATE_PATTERNS_ENV]
                else:
                    os.environ[leak_scan.PRIVATE_PATTERNS_ENV] = old
        self.assertIn("テスト専用のラベル", labels)
        self.assertIn("API キー (Gemini)", labels)


class HookTest(unittest.TestCase):
    def run_hook(self, repo, patterns_path):
        payload = json.dumps({"tool_input": {"command": "git commit -m test"}})
        env = dict(os.environ, **{leak_scan.PRIVATE_PATTERNS_ENV: patterns_path})
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=payload,
            capture_output=True,
            text=True,
            cwd=repo,
            env=env,
            check=False,
        )

    def test_commit_with_private_word_is_blocked_and_clean_commit_passes(self):
        with tempfile.TemporaryDirectory() as d:
            patterns = write_patterns(d, "顧客\tACME\n")
            repo = Path(d) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            (repo / "a.md").write_text("ACME の話\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.md"], cwd=repo, check=True)
            blocked = self.run_hook(repo, patterns)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("顧客", blocked.stderr)

            (repo / "a.md").write_text("ふつうの話\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.md"], cwd=repo, check=True)
            self.assertEqual(self.run_hook(repo, patterns).returncode, 0)

    def test_removed_lines_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            patterns = write_patterns(d, "顧客\tACME\n")
            repo = Path(d) / "repo"
            repo.mkdir()
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
            subprocess.run([*git, "init", "-q"], cwd=repo, check=True)
            (repo / "a.md").write_text("ACME の話\n", encoding="utf-8")
            subprocess.run([*git, "add", "a.md"], cwd=repo, check=True)
            subprocess.run([*git, "commit", "-q", "-m", "init"], cwd=repo, check=True)
            (repo / "a.md").write_text("ふつうの話\n", encoding="utf-8")
            subprocess.run([*git, "add", "a.md"], cwd=repo, check=True)
            self.assertEqual(self.run_hook(repo, patterns).returncode, 0)


if __name__ == "__main__":
    unittest.main()
