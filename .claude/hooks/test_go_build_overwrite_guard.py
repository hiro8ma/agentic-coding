import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).with_name("go-build-overwrite-guard.py")
MAIN = "package main\n\nfunc main() {}\n"
SOURCES = {
    "cmd/foo/main.go": MAIN,
    "sub/main.go": MAIN,
    "pkg/lib/lib.go": "package lib\n",
}

CASES = {
    "追跡外の foo を go build ./cmd/foo/ が上書きするなら止める": {
        "outputs": ["foo"],
        "command": "go build ./cmd/foo/",
        "want": ["foo"],
    },
    "末尾の / が無くても止める": {
        "outputs": ["foo"],
        "command": "go build ./cmd/foo",
        "want": ["foo"],
    },
    "-o で書き出す先を変えれば止めない": {
        "outputs": ["foo"],
        "command": "go build -o /tmp/x ./cmd/foo",
    },
    "-o= の形も止めない": {
        "outputs": ["foo"],
        "command": "go build -o=bin/foo ./cmd/foo",
    },
    "./... は止めない": {"outputs": ["foo"], "command": "go build ./..."},
    "./cmd/foo/... は止めない": {
        "outputs": ["foo"],
        "command": "go build ./cmd/foo/...",
    },
    "パッケージが複数なら止めない": {
        "outputs": ["foo"],
        "command": "go build ./cmd/foo ./sub",
    },
    "go vet は止めない": {"outputs": ["foo"], "command": "go vet ./cmd/foo"},
    "go run は止めない": {"outputs": ["foo"], "command": "go run ./cmd/foo"},
    "go test は止めない": {"outputs": ["foo"], "command": "go test ./cmd/foo"},
    "foo が追跡されていれば止めない": {
        "outputs": ["foo"],
        "track_outputs": True,
        "command": "go build ./cmd/foo/",
    },
    "foo が無視の対象なら止めない": {
        "outputs": ["foo"],
        "files": {".gitignore": "/foo\n"},
        "command": "go build ./cmd/foo/",
    },
    "foo が無ければ止めない": {"command": "go build ./cmd/foo/"},
    "git の外では止めない": {
        "outputs": ["foo"],
        "git": False,
        "command": "go build ./cmd/foo/",
    },
    "cd sub && go build . は sub の名前のファイルが追跡外なら止める": {
        "outputs": ["sub/sub"],
        "command": "cd sub && go build .",
        "want": ["sub/sub"],
    },
    "引数の無い go build はカレントディレクトリのパッケージを見る": {
        "outputs": ["sub/sub"],
        "cwd": "sub",
        "command": "go build",
        "want": ["sub/sub"],
    },
    "入力に cwd が無ければ hook のカレントディレクトリを使う": {
        "outputs": ["foo"],
        "send_cwd": False,
        "command": "go build ./cmd/foo",
        "want": ["foo"],
    },
    "-C のディレクトリを基準にする": {
        "outputs": ["sub/sub"],
        "command": "go build -C sub .",
        "want": ["sub/sub"],
    },
    "&& の後ろの go build も見る": {
        "outputs": ["foo"],
        "command": "go vet ./... && go build ./cmd/foo",
        "want": ["foo"],
    },
    "2>&1 とパイプを付けても止める": {
        "outputs": ["foo"],
        "command": "go build ./cmd/foo 2>&1 | tail -5",
        "want": ["foo"],
    },
    "前に環境変数を付けても止める": {
        "outputs": ["foo"],
        "command": "CGO_ENABLED=0 go build ./cmd/foo",
        "want": ["foo"],
    },
    "値を取るフラグの値をパッケージと取り違えない": {
        "outputs": ["foo"],
        "command": "go build -tags integration -ldflags '-s -w' ./cmd/foo",
        "want": ["foo"],
    },
    "コメントの次の行の go build も見る": {
        "outputs": ["foo"],
        "command": "# (ビルドする)\ngo build ./cmd/foo",
        "want": ["foo"],
    },
    "go.mod があれば module の最後の要素を出力名にする": {
        "files": {"go.mod": "module example.com/bar\n", "main.go": MAIN},
        "outputs": ["bar", "repo"],
        "command": "go build .",
        "want": ["bar"],
    },
    "module の最後が版の要素なら1つ前の要素を使う": {
        "files": {"go.mod": "module example.com/bar/v2\n", "main.go": MAIN},
        "outputs": ["bar", "v2"],
        "command": "go build .",
        "want": ["bar"],
    },
    "main でないパッケージは止めない": {
        "outputs": ["lib"],
        "command": "go build ./pkg/lib",
    },
    "サブシェルは止めない": {
        "outputs": ["sub/sub"],
        "command": "(cd sub && go build .)",
    },
    "変数を展開する cd は止めない": {
        "files": {"$D/cmd/foo/main.go": MAIN},
        "outputs": ["$D/foo"],
        "command": "cd $D && go build ./cmd/foo",
    },
    "引用符が閉じないコマンドは通す": {
        "outputs": ["foo"],
        "command": 'go build ./cmd/foo "',
    },
}


def write(root, files):
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def isolated_env(tmp):
    # 利用者の全体の gitignore と、tmp より上のリポジトリを読ませない
    return dict(
        os.environ,
        HOME=str(tmp),
        XDG_CONFIG_HOME=str(tmp),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CEILING_DIRECTORIES=str(tmp),
    )


def make_tree(tmp, case, env):
    root = tmp / "repo"
    sources = dict(SOURCES, **case.get("files", {}))
    write(root, sources)
    outputs = case.get("outputs", [])
    write(root, {rel: "\x7fELF build output\n" for rel in outputs})
    if case.get("git", True):
        tracked = list(sources) + (outputs if case.get("track_outputs") else [])
        for args in (["init", "-q"], ["add", "--", *tracked]):
            subprocess.run(["git", *args], cwd=root, env=env, check=True)
    return root


def run_hook(stdin, cwd, env):
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def blocked_paths(stderr):
    return sorted(
        line[4:].split("（")[0]
        for line in stderr.splitlines()
        if line.startswith("  - ")
    )


class HookTest(unittest.TestCase):
    def test_cases(self):
        for name, case in CASES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                tmp = Path(os.path.realpath(d))
                env = isolated_env(tmp)
                root = make_tree(tmp, case, env)
                cwd = root / case.get("cwd", "")
                payload = {"tool_input": {"command": case["command"]}}
                if case.get("send_cwd", True):
                    payload["cwd"] = str(cwd)
                result = run_hook(json.dumps(payload), cwd, env)
                want = sorted(str(root / rel) for rel in case.get("want", []))
                self.assertEqual(result.returncode, 2 if want else 0, result.stderr)
                self.assertEqual(blocked_paths(result.stderr), want)
                if want:
                    self.assertIn("go build -o <別の場所>", result.stderr)

    def test_input_that_is_not_json_passes(self):
        with tempfile.TemporaryDirectory() as d:
            result = run_hook("go build ./cmd/foo", d, isolated_env(d))
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
