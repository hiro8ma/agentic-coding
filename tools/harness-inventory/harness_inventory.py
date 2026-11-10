#!/usr/bin/env python3
"""エージェントのハーネスの部品を、guide / sensor と computational / inferential に分けて数える。

Usage:
    python3 harness_inventory.py ROOT [ROOT ...]   # リポジトリのルートを読む
    python3 harness_inventory.py --user ROOT       # 利用者の設定（ホームの .claude / .codex）も合わせて読む
    python3 harness_inventory.py --user            # 利用者の設定だけを読む
    python3 harness_inventory.py --json ROOT       # JSON で出す

guide は行動の前に導く部品、sensor は行動とその結果を確かめる部品。
computational は決定的な検査、inferential は LLM の判断。
指示ファイルの規則は tools/rule-loops と同じ数え方で数え、
規則の本文か Why に、登録された決定的な sensor の名前が出るかを見る。

終了コードは0。読めないパスを渡したときだけ2。
Python 3.9以降の標準ライブラリだけで動く。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rule-loops"))

import rule_loops

GUIDE = "guide"
SENSOR = "sensor"
OUTSIDE = "outside"
COMPUTATIONAL = "computational"
INFERENTIAL = "inferential"
ROLE_LABELS = {
    GUIDE: "guide（行動の前に導く）",
    SENSOR: "sensor（行動と結果を確かめる）",
}
METHOD_LABELS = {
    COMPUTATIONAL: "computational（決定的な検査）",
    INFERENTIAL: "inferential（LLM の判断）",
}

CONTEXT = "文脈"
TOOLS = "道具"
WALLS = "壁と検査"
STATE = "状態"

MAX_DEPTH = 6
SKIP_DIRS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "venv",
    "coverage",
    "__pycache__",
    "fixtures",
    "testdata",
}
LIST_LIMIT = 3

TOOL_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "PermissionDenied",
}
SENSOR_EVENTS = TOOL_EVENTS | {
    "Stop",
    "SubagentStop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "PostToolBatch",
    "ConfigChange",
}
GUIDE_EVENTS = {
    "SessionStart",
    "Setup",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "SubagentStart",
    "InstructionsLoaded",
    "PreCompact",
    "PostCompact",
    "CwdChanged",
    "DirectoryAdded",
    "FileChanged",
    "PreModelSwitch",
    "PostModelSwitch",
}
NOTICE_EVENTS = {"Notification", "StopFailure", "SessionEnd", "MessageDisplay"}
NO_MATCHER_EVENTS = {
    "UserPromptSubmit",
    "PostToolBatch",
    "Stop",
    "TeammateIdle",
    "TaskCreated",
    "TaskCompleted",
    "WorktreeCreate",
    "WorktreeRemove",
    "MessageDisplay",
    "CwdChanged",
}
INFERENTIAL_HOOK_TYPES = {"prompt", "agent"}
EVENT_ROLE_LABELS = {
    GUIDE: "導く",
    SENSOR: "確かめる",
    "notice": "知らせる",
    "other": "その他",
}

INSTRUCTION_NAMES = {
    "AGENTS.md",
    "AGENTS.override.md",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "GEMINI.md",
}
USER_INSTRUCTIONS = (
    ".claude/CLAUDE.md",
    ".codex/AGENTS.md",
    ".codex/AGENTS.override.md",
    ".gemini/GEMINI.md",
)
PROJECT_SKILL_DIRS = (".claude/skills", ".agents/skills")
USER_SKILL_DIRS = (".claude/skills", ".agents/skills", ".codex/skills")
REVIEWER_TOKENS = {
    "review",
    "reviewer",
    "verify",
    "verifier",
    "check",
    "checker",
    "audit",
    "auditor",
    "critic",
    "judge",
    "eval",
    "evaluator",
    "qa",
}

LINTER_CONFIGS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("golangci-lint", re.compile(r"^\.golangci\.(?:ya?ml|toml|json)$")),
    ("ruff", re.compile(r"^\.?ruff\.toml$")),
    ("eslint", re.compile(r"^(?:\.eslintrc(?:\.[a-z]+)?|eslint\.config\.[cm]?[jt]s)$")),
    (
        "prettier",
        re.compile(r"^(?:\.prettierrc(?:\.[a-z]+)?|prettier\.config\.[cm]?[jt]s)$"),
    ),
    ("biome", re.compile(r"^biome\.jsonc?$")),
    ("clippy", re.compile(r"^\.?clippy\.toml$")),
    ("rustfmt", re.compile(r"^\.?rustfmt\.toml$")),
    ("markdownlint", re.compile(r"^\.markdownlint(?:-cli2)?(?:\.[a-z]+)?$")),
    ("textlint", re.compile(r"^\.textlintrc(?:\.[a-z]+)?$")),
    ("mypy", re.compile(r"^\.?mypy\.ini$")),
    ("shellcheck", re.compile(r"^\.shellcheckrc$")),
    ("staticcheck", re.compile(r"^staticcheck\.conf$")),
)
PYPROJECT_LINTERS = (("ruff", "[tool.ruff"), ("mypy", "[tool.mypy"))
GATE_RUNNERS = {
    ".pre-commit-config.yaml": "pre-commit",
    "lefthook.yml": "lefthook",
    "lefthook.yaml": "lefthook",
    ".lefthook.yml": "lefthook",
}
LINTER_CALLS = {
    "golangci-lint": r"golangci-lint|golangci/golangci-lint-action",
    "rustfmt": r"rustfmt|cargo\s+fmt",
}

_A = r"(?<![A-Za-z0-9_-])"
_Z = r"(?![A-Za-z0-9_-])"
_SCRIPT = re.compile(
    r"(?<![A-Za-z0-9_])((?:\$\{?[A-Za-z_][A-Za-z0-9_]*(?:[:-][^}]*)?\}?|~)?"
    r"[A-Za-z0-9_./@-]*\.(?:py|sh|bash|js|mjs|cjs|ts|rb|cmd|ps1))(?![A-Za-z0-9_])"
)
_VAR = re.compile(r"^(?:\$\{?([A-Za-z_][A-Za-z0-9_]*)(?:[:-][^}]*)?\}?|~)")
_NPX = re.compile(
    r"(?<![A-Za-z0-9_-])npx\s+(?:(?:-y|--yes)\s+)?(@?[A-Za-z0-9_./-]+(?:@[^\s]+)?)"
)
_EXACT_MATCHER = re.compile(r"^[A-Za-z0-9_\-, |]+$")
_NOT_IN_TOOL_NAME = re.compile(r"[\s\"'=&!<>]")
_PERMISSION = re.compile(r"^([A-Za-z0-9_]+)(?:\((.*)\))?$")
_TOML_TABLE = re.compile(r"^\s*\[\[?\s*(.+?)\s*\]\]?\s*(?:#.*)?$")
_TOML_KEYVAL = re.compile(r"""^\s*([A-Za-z0-9_-]+|"[^"]*")\s*=\s*(.*)$""")
_TOML_DOTTED = re.compile(r"\"[^\"]*\"|'[^']*'|[^.\"'\s]+")
_PREFIX_RULE = re.compile(r"\bprefix_rule\s*\(")
_DECISION = re.compile(r"""\bdecision\s*=\s*["']([A-Za-z_]+)["']""")
_PATTERN = re.compile(r"\bpattern\s*=\s*\[")
_STRING = re.compile(r"""\s*("(?:[^"\\]|\\.)*"|'[^']*')\s*,?""")
_WF_ON = re.compile(r"""^["']?on["']?\s*:\s*(.*)$""")
_WF_KEY = re.compile(r"^(\s+)-?\s*([A-Za-z_]+)\s*:?\s*(?:#.*)?$")
_AI_STEP = re.compile(
    r"anthropics/claude-code(?:-base)?-action|openai/codex-action"
    r"|google-github-actions/run-gemini-cli"
    rf"|{_A}claude\s+(?:-p|--print){_Z}|{_A}codex\s+exec{_Z}|{_A}gemini\s+(?:-p|--prompt){_Z}"
)
PR_TRIGGERS = {"pull_request", "pull_request_target", "merge_group"}
ON_PR = "PR のたび"
GENERIC_NAMES = {
    "hook",
    "hooks",
    "index",
    "main",
    "run",
    "check",
    "test",
    "tests",
    "lint",
    "script",
    "scripts",
    "default",
    "bash",
    "python",
    "python3",
    "node",
    "echo",
}
GENERIC_DIRS = {"hooks", "scripts", "bin", "tools", "src", "lib"}


@dataclass
class Root:
    label: str
    path: Path
    user: bool


@dataclass
class Part:
    root: str
    layer: str
    role: str
    method: str
    kind: str
    where: str
    count: int
    unit: str = "件"
    note: str = ""


@dataclass
class Hook:
    source: str
    event: str
    matcher: str | None
    type: str
    label: str
    script: str | None = None
    script_found: bool | None = None
    has_if: bool = False
    keys: list[str] = field(default_factory=list)

    @property
    def role(self) -> str:
        if self.event in SENSOR_EVENTS:
            return SENSOR
        if self.event in GUIDE_EVENTS:
            return GUIDE
        if self.event in NOTICE_EVENTS:
            return "notice"
        return "other"

    @property
    def method(self) -> str:
        return INFERENTIAL if self.type in INFERENTIAL_HOOK_TYPES else COMPUTATIONAL


@dataclass
class Sensor:
    kind: str
    name: str
    where: str
    keys: list[str]


@dataclass
class Permissions:
    source: str
    allow: int = 0
    ask: int = 0
    deny: int = 0
    mode: str = ""
    sandbox: str = ""


@dataclass
class Finding:
    where: str
    message: str


@dataclass
class Inventory:
    root: Root
    parts: list[Part] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    sensors: list[Sensor] = field(default_factory=list)
    permissions: list[Permissions] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    instructions: list[tuple[str, Path]] = field(default_factory=list)

    def add(
        self,
        layer: str,
        role: str,
        method: str,
        kind: str,
        where: str,
        count: int,
        **kw: str,
    ) -> None:
        if count:
            self.parts.append(
                Part(self.root.label, layer, role, method, kind, where, count, **kw)
            )


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("_", "-"))


def name_keys(*names: str) -> list[str]:
    keys: list[str] = []
    for name in names:
        key = normalize(name).strip()
        if len(key) >= 4 and key not in GENERIC_NAMES and key not in keys:
            keys.append(key)
    return keys


def key_pattern(key: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9-]){re.escape(key)}(?![a-z0-9-])")


class Scanner:
    def __init__(self, root: Root, home: Path) -> None:
        self.root = root
        self.home = home
        self.inv = Inventory(root)

    def show(self, path: Path) -> str:
        label = self.root.label.rstrip("/") or "/"
        try:
            return f"{label}/{path.relative_to(self.root.path).as_posix()}"
        except ValueError:
            pass
        try:
            return f"~/{path.relative_to(self.home).as_posix()}"
        except ValueError:
            return path.as_posix()

    def show_many(self, paths: list[Path]) -> str:
        shown = [self.show(p) for p in paths[:LIST_LIMIT]]
        if len(paths) > LIST_LIMIT:
            shown.append(f"ほか{len(paths) - LIST_LIMIT}件")
        return " / ".join(shown)

    def finding(self, path: Path, message: str) -> None:
        self.inv.findings.append(Finding(self.show(path), message))

    def read_json(self, path: Path) -> object | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.finding(path, "JSON として読めない")
            return None

    def scan(self) -> Inventory:
        base = self.root.path
        files = [] if self.root.user else walk_files(base)
        self.scan_instructions(files)
        self.scan_skills()
        self.scan_agents()
        for name in (
            ("settings.json",)
            if self.root.user
            else ("settings.json", "settings.local.json")
        ):
            self.scan_claude_settings(base / ".claude" / name)
        self.scan_codex()
        self.scan_mcp()
        if not self.root.user:
            self.scan_workflows()
            self.scan_linters(files)
        return self.inv

    def scan_instructions(self, files: list[Path]) -> None:
        base = self.root.path
        if self.root.user:
            found = [base / rel for rel in USER_INSTRUCTIONS if (base / rel).is_file()]
        else:
            found = [p for p in files if p.name in INSTRUCTION_NAMES]
            if (base / ".claude" / "CLAUDE.md").is_file():
                found.append(base / ".claude" / "CLAUDE.md")
        rules_dir = base / ".claude" / "rules"
        rule_files = sorted(rules_dir.rglob("*.md")) if rules_dir.is_dir() else []
        for path in sorted(found) + rule_files:
            self.inv.instructions.append((self.show(path), path))
        distinct = len({p.resolve() for p in found})
        note = f"中身の違うもの{distinct}件" if distinct != len(found) else ""
        self.inv.add(
            CONTEXT,
            GUIDE,
            INFERENTIAL,
            "指示ファイル",
            self.show_many(sorted(found)),
            len(found),
            note=note,
        )
        self.inv.add(
            CONTEXT, GUIDE, INFERENTIAL, "rules", self.show(rules_dir), len(rule_files)
        )

    def scan_skills(self) -> None:
        dirs = USER_SKILL_DIRS if self.root.user else PROJECT_SKILL_DIRS
        for rel in dirs:
            path = self.root.path / rel
            if not path.is_dir():
                continue
            entries = [d for d in sorted(path.iterdir()) if not d.name.startswith(".")]
            skills = [d for d in entries if (d / "SKILL.md").is_file()]
            self.inv.add(
                CONTEXT, GUIDE, INFERENTIAL, "skill", self.show(path), len(skills)
            )
            loose = [d.name for d in entries if d not in skills]
            if loose:
                self.finding(
                    path,
                    f"SKILL.md の無い項目{len(loose)}件は skill として読まれない"
                    f"（{' / '.join(loose[:LIST_LIMIT])}{' ほか' if len(loose) > LIST_LIMIT else ''}）",
                )
        commands = self.root.path / ".claude" / "commands"
        if commands.is_dir():
            self.inv.add(
                CONTEXT,
                GUIDE,
                INFERENTIAL,
                "コマンド",
                self.show(commands),
                len(list(commands.rglob("*.md"))),
            )
        prompts = self.root.path / ".codex" / "prompts"
        if self.root.user and prompts.is_dir():
            self.inv.add(
                CONTEXT,
                GUIDE,
                INFERENTIAL,
                "コマンド",
                self.show(prompts),
                len(list(prompts.glob("*.md"))),
            )

    def scan_agents(self) -> None:
        for rel, pattern in ((".claude/agents", "*.md"), (".codex/agents", "*.toml")):
            path = self.root.path / rel
            if not path.is_dir():
                continue
            reviewers, others = [], []
            for agent in sorted(path.glob(pattern)):
                tokens = set(re.split(r"[-_.\s]+", agent.stem.lower()))
                (reviewers if tokens & REVIEWER_TOKENS else others).append(agent.stem)
            self.inv.add(
                CONTEXT,
                GUIDE,
                INFERENTIAL,
                "サブエージェント",
                self.show(path),
                len(others),
            )
            self.inv.add(
                WALLS,
                SENSOR,
                INFERENTIAL,
                "レビュー役のサブエージェント",
                self.show(path),
                len(reviewers),
                note=" / ".join(reviewers),
            )

    def scan_claude_settings(self, path: Path) -> None:
        data = self.read_json(path)
        if not isinstance(data, dict):
            return
        self.scan_hooks(path, data.get("hooks"))
        if data.get("disableAllHooks") is True:
            self.finding(path, "disableAllHooks が true で、hook がすべて止まる")
        perms = (
            data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        )
        record = Permissions(self.show(path))
        lists = {}
        for key in ("allow", "ask", "deny"):
            value = perms.get(key)
            lists[key] = (
                [v for v in value if isinstance(v, str)]
                if isinstance(value, list)
                else []
            )
            setattr(record, key, len(lists[key]))
        mode = perms.get("defaultMode")
        record.mode = mode if isinstance(mode, str) else ""
        sandbox = data.get("sandbox")
        if isinstance(sandbox, dict) and "enabled" in sandbox:
            record.sandbox = "有効" if sandbox.get("enabled") is True else "無効"
        self.inv.permissions.append(record)
        where = self.show(path)
        self.inv.add(
            WALLS,
            SENSOR,
            COMPUTATIONAL,
            "permissions の ask と deny",
            where,
            record.ask + record.deny,
        )
        self.inv.add(
            WALLS, OUTSIDE, "", "検査を飛ばす許可（allow）", where, record.allow
        )
        for key in ("ask", "deny"):
            for entry in lists[key]:
                keys = permission_keys(entry)
                if keys:
                    self.inv.sensors.append(
                        Sensor(f"permissions の {key}", entry, where, keys)
                    )
        if record.mode == "auto":
            self.inv.add(WALLS, SENSOR, INFERENTIAL, "auto モードの分類器", where, 1)
        if record.mode in ("auto", "bypassPermissions") and not self.root.user:
            self.finding(
                path,
                f"defaultMode の {record.mode} は、プロジェクトと local の設定では効かない",
            )
        if record.mode == "bypassPermissions":
            self.inv.add(
                WALLS,
                OUTSIDE,
                "",
                "許可の確認を飛ばす既定（bypassPermissions）",
                where,
                1,
            )
        if record.sandbox:
            self.inv.add(WALLS, OUTSIDE, "", "sandbox", where, 1, note=record.sandbox)
        plugins = data.get("enabledPlugins")
        if isinstance(plugins, dict):
            enabled = sum(1 for v in plugins.values() if v is True)
            self.inv.add(
                TOOLS,
                OUTSIDE,
                "",
                "plugin",
                where,
                enabled,
                note="中の hook と skill は読まない",
            )

    def scan_hooks(self, path: Path, hooks: object) -> None:
        if not isinstance(hooks, dict):
            return
        where = self.show(path)
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                matcher = group.get("matcher")
                matcher = matcher if isinstance(matcher, str) else None
                for entry in group.get("hooks") or []:
                    if isinstance(entry, dict):
                        self.add_hook(path, where, event, matcher, entry)

    def add_hook(
        self, path: Path, where: str, event: str, matcher: str | None, entry: dict
    ) -> None:
        kind = entry.get("type") if isinstance(entry.get("type"), str) else "command"
        command = entry.get("command") if isinstance(entry.get("command"), str) else ""
        hook = Hook(where, event, matcher, kind, "", has_if="if" in entry)
        if kind in INFERENTIAL_HOOK_TYPES:
            prompt = entry.get("prompt") if isinstance(entry.get("prompt"), str) else ""
            hook.label = f"{kind}: {shorten(prompt, 30)}"
        elif kind == "http":
            hook.label = f"http: {shorten(str(entry.get('url', '')), 40)}"
        elif kind == "mcp_tool":
            hook.label = f"mcp_tool: {entry.get('server', '')}/{entry.get('tool', '')}"
        else:
            self.label_command(hook, command)
        self.inv.hooks.append(hook)
        problem = matcher_problem(event, matcher)
        if problem:
            self.finding(
                path,
                f"{event} の hook「{hook.label}」の matcher「{matcher}」は{problem}",
            )
        if hook.has_if and event not in TOOL_EVENTS:
            self.finding(
                path,
                f"{event} の hook「{hook.label}」の if は道具のイベントでしか読まれず、この hook は動かない",
            )
        if hook.script_found is False:
            self.finding(
                path,
                f"{event} の hook「{hook.label}」のスクリプト {hook.script} が見つからない",
            )

    def label_command(self, hook: Hook, command: str) -> None:
        candidates = []
        for match in _SCRIPT.finditer(command):
            resolved = self.resolve(match.group(1))
            candidates.append((match.group(1), resolved))
        if candidates:
            token, resolved = next(
                ((t, r) for t, r in candidates if r is not None and r.is_file()),
                candidates[0],
            )
            script = Path(token)
            hook.label = script.stem
            hook.script = self.show(resolved) if resolved is not None else token
            hook.script_found = resolved.is_file() if resolved is not None else None
            parent = script.parent.name
            extra = (
                [parent]
                if parent and not parent.startswith(".") and parent not in GENERIC_DIRS
                else []
            )
            hook.keys = name_keys(script.stem, *extra)
            return
        if "\n" in command.strip():
            hook.label = "（インラインのスクリプト）"
            return
        npx = _NPX.search(command)
        if npx:
            package = npx.group(1)
            if "@" in package[1:]:
                package = package[: package.index("@", 1)]
            hook.label = package
        else:
            words = command.split()
            hook.label = Path(words[0]).name if words else "（空）"
        hook.keys = name_keys(hook.label)

    def resolve(self, token: str) -> Path | None:
        match = _VAR.match(token)
        if match:
            name = match.group(1) or "HOME"
            rest = token[match.end() :].lstrip("/")
            if name == "HOME":
                return self.home / rest
            if name == "CLAUDE_PROJECT_DIR" and not self.root.user:
                return self.root.path / rest
            return None
        if token.startswith("/"):
            return Path(token)
        if self.root.user:
            return None
        return self.root.path / token

    def scan_codex(self) -> None:
        codex = self.root.path / ".codex"
        config = codex / "config.toml"
        if config.is_file():
            top, tables = read_toml(
                config.read_text(encoding="utf-8", errors="replace")
            )
            where = self.show(config)
            record = Permissions(
                where,
                mode=top.get("approval_policy", ""),
                sandbox=top.get("sandbox_mode", ""),
            )
            self.inv.permissions.append(record)
            if record.sandbox:
                self.inv.add(
                    WALLS, OUTSIDE, "", "sandbox", where, 1, note=record.sandbox
                )
            reviewer = top.get("approvals_reviewer", "")
            if reviewer and reviewer != "user":
                self.inv.add(
                    WALLS,
                    SENSOR,
                    INFERENTIAL,
                    "承認をモデルに任せる設定",
                    where,
                    1,
                    note=f"approvals_reviewer = {reviewer}",
                )
            servers = sorted(
                {t[1] for t in tables if len(t) >= 2 and t[0] == "mcp_servers"}
            )
            self.inv.add(
                TOOLS,
                OUTSIDE,
                "",
                "MCP サーバー",
                where,
                len(servers),
                note=" / ".join(servers),
            )
        hooks = codex / "hooks.json"
        data = self.read_json(hooks)
        if isinstance(data, dict):
            self.scan_hooks(hooks, data.get("hooks"))
        rules_dir = codex / "rules"
        if not rules_dir.is_dir():
            return
        for path in sorted(rules_dir.glob("*.rules")):
            where = self.show(path)
            counts = {"allow": 0, "prompt": 0, "forbidden": 0}
            for decision, tokens in parse_exec_rules(
                path.read_text(encoding="utf-8", errors="replace")
            ):
                counts[decision] = counts.get(decision, 0) + 1
                keys = name_keys(" ".join(tokens)) if len(tokens) >= 2 else []
                if decision != "allow" and keys:
                    self.inv.sensors.append(
                        Sensor(
                            f"execpolicy の {decision}", " ".join(tokens), where, keys
                        )
                    )
            self.inv.permissions.append(
                Permissions(
                    where,
                    allow=counts["allow"],
                    ask=counts["prompt"],
                    deny=counts["forbidden"],
                )
            )
            self.inv.add(
                WALLS,
                SENSOR,
                COMPUTATIONAL,
                "execpolicy の prompt と forbidden",
                where,
                counts["prompt"] + counts["forbidden"],
            )
            self.inv.add(
                WALLS, OUTSIDE, "", "検査を飛ばす許可（allow）", where, counts["allow"]
            )

    def scan_mcp(self) -> None:
        path = self.root.path / (".claude.json" if self.root.user else ".mcp.json")
        data = self.read_json(path)
        if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
            names = sorted(data["mcpServers"])
            self.inv.add(
                TOOLS,
                OUTSIDE,
                "",
                "MCP サーバー",
                self.show(path),
                len(names),
                note=" / ".join(names),
            )

    def scan_workflows(self) -> None:
        wf_dir = self.root.path / ".github" / "workflows"
        if not wf_dir.is_dir():
            return
        paths = sorted(p for p in wf_dir.iterdir() if p.suffix in (".yml", ".yaml"))
        groups: dict[tuple[str, str], list[Path]] = {}
        for path in paths:
            text = path.read_text(encoding="utf-8", errors="replace")
            triggers = parse_workflow(text)
            method = INFERENTIAL if _AI_STEP.search(text) else COMPUTATIONAL
            when = trigger_class(triggers)
            groups.setdefault((method, when), []).append(path)
            if method == COMPUTATIONAL and when == ON_PR:
                self.inv.sensors.append(
                    Sensor("CI", path.name, self.show(path), name_keys(path.name))
                )
        for (method, when), members in sorted(groups.items()):
            where, count = self.show_many(members), len(members)
            if when == ON_PR:
                self.inv.add(WALLS, SENSOR, method, "CI", where, count, unit="本")
                continue
            note = when + ("、LLM を使う" if method == INFERENTIAL else "")
            self.inv.add(
                WALLS,
                OUTSIDE,
                "",
                "PR で動かない CI",
                where,
                count,
                unit="本",
                note=note,
            )

    def scan_linters(self, files: list[Path]) -> None:
        found: dict[str, list[Path]] = {}
        gates: dict[str, list[Path]] = {}
        for path in files:
            for linter, pattern in LINTER_CONFIGS:
                if pattern.match(path.name):
                    found.setdefault(linter, []).append(path)
            if path.name == "pyproject.toml":
                text = path.read_text(encoding="utf-8", errors="replace")
                for linter, marker in PYPROJECT_LINTERS:
                    if marker in text:
                        found.setdefault(linter, []).append(path)
            if path.name in GATE_RUNNERS:
                gates.setdefault(GATE_RUNNERS[path.name], []).append(path)
        husky = self.root.path / ".husky"
        if husky.is_dir():
            gates["husky"] = sorted(
                p for p in husky.iterdir() if p.is_file() and not p.name.startswith("_")
            )
        callers = self.caller_texts(gates)
        for linter, paths in sorted(found.items()):
            call = re.compile(
                rf"{_A}(?:{LINTER_CALLS.get(linter, re.escape(linter))}){_Z}",
                re.IGNORECASE,
            )
            wired = [name for name, text in callers if call.search(text)]
            note = (
                "呼ぶ場所 " + " / ".join(wired)
                if wired
                else "CI / hook / pre-commit に名前が出ない"
            )
            self.inv.add(
                WALLS,
                SENSOR,
                COMPUTATIONAL,
                f"linter（{linter}）",
                self.show_many(paths),
                len(paths),
                note=note,
            )
            if wired:
                self.inv.sensors.append(
                    Sensor("linter", linter, self.show(paths[0]), name_keys(linter))
                )
        for runner, paths in sorted(gates.items()):
            self.inv.add(
                WALLS, SENSOR, COMPUTATIONAL, runner, self.show_many(paths), len(paths)
            )
            self.inv.sensors.append(
                Sensor(
                    "pre-commit",
                    runner,
                    self.show(paths[0]) if paths else "",
                    name_keys(runner),
                )
            )

    def caller_texts(self, gates: dict[str, list[Path]]) -> list[tuple[str, str]]:
        texts = []
        wf_dir = self.root.path / ".github" / "workflows"
        if wf_dir.is_dir():
            texts.append(
                (
                    "CI",
                    "\n".join(
                        p.read_text(encoding="utf-8", errors="replace")
                        for p in sorted(wf_dir.glob("*.y*ml"))
                    ),
                )
            )
        hook_text = []
        for rel in (
            ".claude/settings.json",
            ".claude/settings.local.json",
            ".codex/hooks.json",
        ):
            path = self.root.path / rel
            if path.is_file():
                hook_text.append(path.read_text(encoding="utf-8", errors="replace"))
        texts.append(("hook", "\n".join(hook_text)))
        gate_text = [
            p.read_text(encoding="utf-8", errors="replace")
            for paths in gates.values()
            for p in paths
        ]
        texts.append(("pre-commit", "\n".join(gate_text)))
        return texts


def walk_files(root: Path) -> list[Path]:
    found: list[Path] = []
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        else:
            dirnames[:] = sorted(
                d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
            )
        found.extend(Path(dirpath) / name for name in sorted(filenames))
    return found


def shorten(text: str, width: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def matcher_problem(event: str, matcher: str | None) -> str:
    if matcher in (None, "", "*"):
        return ""
    if event in NO_MATCHER_EVENTS:
        return "、matcher を読まないイベントなので無視される"
    if (
        event in TOOL_EVENTS
        and not _EXACT_MATCHER.match(matcher)
        and _NOT_IN_TOOL_NAME.search(matcher)
    ):
        return "、正規表現として読まれ、道具の名前に入らない文字（空白 / 引用符 / = など）を含むので、どの道具にも一致しない"
    return ""


def permission_keys(entry: str) -> list[str]:
    match = _PERMISSION.match(entry.strip())
    if not match:
        return []
    tool, spec = match.group(1), match.group(2)
    if spec is None:
        return name_keys(tool)
    spec = re.sub(r"(?::\*|\s*\*+)$", "", spec.strip()).strip()
    spec = re.sub(r"^(?:\./|\*\*/)+", "", spec)
    if not spec or set(spec) <= set("*/."):
        return []
    return name_keys(spec)


def read_toml(text: str) -> tuple[dict[str, str], list[list[str]]]:
    """config.toml の、最上位の1行の値と、表の見出しだけを読む"""
    top: dict[str, str] = {}
    tables: list[list[str]] = []
    current: list[str] | None = None
    depth = 0
    triple = ""
    for line in text.splitlines():
        if triple:
            if triple in line:
                triple = ""
            continue
        if depth > 0:
            depth += line.count("[") - line.count("]")
            continue
        keyval = _TOML_KEYVAL.match(line)
        table = None if keyval else _TOML_TABLE.match(line)
        if table:
            current = [
                part.strip("\"'") for part in _TOML_DOTTED.findall(table.group(1))
            ]
            tables.append(current)
            continue
        if not keyval:
            continue
        value = keyval.group(2).strip()
        for quote in ('"""', "'''"):
            if value.startswith(quote) and value.count(quote) == 1:
                triple = quote
        if value.startswith("["):
            depth = value.count("[") - value.count("]")
        if current is None:
            top[keyval.group(1).strip('"')] = toml_scalar(value)
    return top, tables


def toml_scalar(value: str) -> str:
    quoted = re.match(r"\"((?:[^\"\\]|\\.)*)\"|'([^']*)'", value)
    if quoted:
        return quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
    return value.split("#", 1)[0].strip()


def parse_exec_rules(text: str) -> list[tuple[str, list[str]]]:
    """Codex の .rules から、prefix_rule ごとの decision と、pattern の先頭の文字列を取る"""
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    starts = [m.end() for m in _PREFIX_RULE.finditer(body)]
    rules = []
    for index, start in enumerate(starts):
        chunk = body[
            start : starts[index + 1] if index + 1 < len(starts) else len(body)
        ]
        decision = _DECISION.search(chunk)
        tokens: list[str] = []
        pattern = _PATTERN.search(chunk)
        if pattern:
            pos = pattern.end()
            while True:
                match = _STRING.match(chunk, pos)
                if not match:
                    break
                raw = match.group(1)
                tokens.append(json.loads(raw) if raw.startswith('"') else raw[1:-1])
                pos = match.end()
        rules.append((decision.group(1) if decision else "allow", tokens))
    return rules


def parse_workflow(text: str) -> list[str]:
    triggers: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        on = _WF_ON.match(line)
        if not on or triggers:
            continue
        rest = on.group(1).split("#", 1)[0].strip()
        if rest:
            triggers = [
                t.strip(" '\"") for t in rest.strip("[]").split(",") if t.strip(" '\"")
            ]
            continue
        indent = None
        for following in lines[index + 1 :]:
            if not following.strip() or following.lstrip().startswith("#"):
                continue
            if not following[0].isspace():
                break
            key = _WF_KEY.match(following)
            if not key:
                continue
            if indent is None:
                indent = len(key.group(1))
            if len(key.group(1)) == indent:
                triggers.append(key.group(2))
    return triggers


def trigger_class(triggers: list[str]) -> str:
    names = set(triggers)
    if names & PR_TRIGGERS:
        return ON_PR
    if "push" in names:
        return "push のたび"
    if "schedule" in names:
        return "定期"
    if names == {"workflow_dispatch"}:
        return "手動"
    if "workflow_call" in names:
        return "ほかの workflow から呼ばれる"
    return "そのほかのイベント" if names else "起動の条件が読めない"


def rule_text(rule: rule_loops.Rule, owned: set[tuple[str, int]]) -> str:
    lines = [text for no, text in rule.body if (rule.file, no) not in owned]
    lines.extend(why.text() for why in rule.whys)
    return normalize("\n".join(lines))


def match_rules(
    rules: list[rule_loops.Rule], sensors: list[Sensor]
) -> list[list[Sensor]]:
    item_lines: dict[tuple[str, int], set[tuple[str, int]]] = {}
    for rule in rules:
        if rule.kind == "item":
            item_lines.setdefault(rule.section_key, set()).update(
                (rule.file, no) for no, _ in rule.body
            )
    patterns = [(sensor, [key_pattern(k) for k in sensor.keys]) for sensor in sensors]
    hits = []
    for rule in rules:
        owned = (
            item_lines.get(rule.section_key, set()) if rule.kind == "section" else set()
        )
        text = rule_text(rule, owned)
        hits.append(
            [sensor for sensor, pats in patterns if any(p.search(text) for p in pats)]
        )
    return hits


def hook_sensors(hooks: list[Hook]) -> list[Sensor]:
    sensors: list[Sensor] = []
    seen: set[tuple[str, str]] = set()
    for hook in hooks:
        if hook.role != SENSOR or hook.method != COMPUTATIONAL or not hook.keys:
            continue
        if (hook.source, hook.label) in seen:
            continue
        seen.add((hook.source, hook.label))
        sensors.append(
            Sensor(f"hook（{hook.event}）", hook.label, hook.source, hook.keys)
        )
    return sensors


def build_report(roots: list[Root], home: Path) -> dict[str, object]:
    inventories = [Scanner(root, home).scan() for root in roots]
    parts = [part for inv in inventories for part in inv.parts]
    hooks = [hook for inv in inventories for hook in inv.hooks]
    parts.extend(hook_parts(inventories))
    sensors = hook_sensors(hooks) + [s for inv in inventories for s in inv.sensors]

    seen: dict[Path, str] = {}
    files: list[dict[str, str]] = []
    rules: list[rule_loops.Rule] = []
    for inv in inventories:
        for shown, path in inv.instructions:
            real = path.resolve()
            if real in seen:
                files.append({"file": shown, "same_as": seen[real]})
                continue
            seen[real] = shown
            files.append({"file": shown, "same_as": ""})
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rules.extend(rule_loops.audit_text(text, shown))
    hits = match_rules(rules, sensors)
    backed = [(rule, found) for rule, found in zip(rules, hits) if found]
    named = {(s.kind, s.name, s.where) for _, found in backed for s in found}
    mentioned = [r for r, found in zip(rules, hits) if r.structural and not found]
    recurring = [(r, found) for r, found in zip(rules, hits) if r.recurring]

    return {
        "roots": [{"label": r.label, "user": r.user} for r in roots],
        "quadrants": quadrants(parts),
        "outside": cell([p for p in parts if p.role == OUTSIDE]),
        "parts": [asdict(p) for p in sorted(parts, key=part_order)],
        "hooks": [hook_json(h) for h in hooks],
        "permissions": [asdict(p) for inv in inventories for p in inv.permissions],
        "instruction_files": files,
        "rules": {
            "total": len(rules),
            "backed": len(backed),
            "backed_ratio": round(len(backed) / len(rules), 4) if rules else 0.0,
            "mentioned_without_sensor": len(mentioned),
            "recurring": len(recurring),
            "recurring_backed": sum(1 for _, found in recurring if found),
            "backed_rules": [rule_json(rule, found) for rule, found in backed],
            "recurring_without_sensor": [
                rule_json(rule, []) for rule, found in recurring if not found
            ],
        },
        "sensors": [asdict(s) for s in sensors],
        "unnamed_sensors": [
            asdict(s) for s in sensors if (s.kind, s.name, s.where) not in named
        ],
        "findings": [asdict(f) for inv in inventories for f in inv.findings],
    }


def hook_parts(inventories: list[Inventory]) -> list[Part]:
    totals: dict[tuple[str, str, str, str, str, str], int] = {}
    for inv in inventories:
        for hook in inv.hooks:
            role, method = (
                (hook.role, hook.method)
                if hook.role in (GUIDE, SENSOR)
                else (OUTSIDE, "")
            )
            layer = {GUIDE: CONTEXT, SENSOR: WALLS}.get(hook.role, STATE)
            kind = {
                "notice": "知らせる hook",
                "other": "そのほかのイベントの hook",
            }.get(hook.role, "hook")
            key = (inv.root.label, layer, role, method, kind, hook.source)
            totals[key] = totals.get(key, 0) + 1
    return [Part(*key, count, unit="本") for key, count in totals.items()]


def part_order(part: Part) -> tuple[int, int, str, str]:
    roles = {GUIDE: 0, SENSOR: 1, OUTSIDE: 2}
    methods = {COMPUTATIONAL: 0, INFERENTIAL: 1, "": 2}
    return roles[part.role], methods[part.method], part.kind, part.where


def cell(parts: list[Part]) -> list[dict[str, object]]:
    totals: dict[tuple[str, str], int] = {}
    for part in parts:
        totals[(part.kind, part.unit)] = (
            totals.get((part.kind, part.unit), 0) + part.count
        )
    return [
        {"kind": kind, "count": count, "unit": unit}
        for (kind, unit), count in totals.items()
    ]


def quadrants(parts: list[Part]) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {
        role: {
            method: cell([p for p in parts if p.role == role and p.method == method])
            for method in METHOD_LABELS
        }
        for role in ROLE_LABELS
    }


def hook_json(hook: Hook) -> dict[str, object]:
    data = asdict(hook)
    data["role"] = hook.role
    data["method"] = hook.method
    return data


def rule_json(rule: rule_loops.Rule, found: list[Sensor]) -> dict[str, object]:
    return {
        "file": rule.file,
        "line": rule.line,
        "title": rule.title,
        "recurring": rule.recurring,
        "sensors": [f"{s.kind}「{s.name}」" for s in found],
    }


def count_text(kind: str, count: object, unit: object) -> str:
    gap = " " if re.search(r"[A-Za-z]$", kind) else ""
    return f"{kind}{gap}{count}{unit}"


def cell_text(items: list[dict[str, object]]) -> str:
    return (
        " / ".join(count_text(str(i["kind"]), i["count"], i["unit"]) for i in items)
        or "なし"
    )


def md(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def percent(ratio: float) -> str:
    return f"{ratio * 100:.1f}%"


def render_markdown(report: dict[str, object]) -> str:
    roots = report["roots"]
    rules = report["rules"]
    out = ["# harness-inventory", ""]
    out.append(f"読んだルート{len(roots)}件（{' / '.join(r['label'] for r in roots)}）")
    out += ["", "## guide / sensor と computational / inferential", ""]
    out.append(f"| | {METHOD_LABELS[COMPUTATIONAL]} | {METHOD_LABELS[INFERENTIAL]} |")
    out.append("|---|---|---|")
    for role, label in ROLE_LABELS.items():
        row = report["quadrants"][role]
        out.append(
            f"| {label} | {cell_text(row[COMPUTATIONAL])} | {cell_text(row[INFERENTIAL])} |"
        )
    out += ["", f"2x2 の外の部品は {cell_text(report['outside'])}"]

    out += ["", "## 規則と決定的な sensor", ""]
    distinct = sum(1 for f in report["instruction_files"] if not f["same_as"])
    out.append(
        f"規則{rules['total']}件（指示ファイル{distinct}件。数え方は tools/rule-loops と同じ）"
    )
    out.append(
        f"登録された決定的な sensor の名前が、本文か Why に出る規則{rules['backed']}件（{percent(rules['backed_ratio'])}）"
    )
    out.append(
        f"文章では hook / CI / lint などに触れるが、登録された sensor の名前が出ない規則{rules['mentioned_without_sensor']}件"
    )
    out.append(
        f"再発した規則（Why の日付が2つ以上）{rules['recurring']}件のうち、sensor の名前が出るもの{rules['recurring_backed']}件"
    )
    if rules["backed_rules"]:
        out += ["", "| 場所 | 規則 | sensor |", "|---|---|---|"]
        for rule in rules["backed_rules"]:
            out.append(
                f"| {md(rule['file'])}:{rule['line']} | {md(rule['title'])} | {md(' / '.join(rule['sensors']))} |"
            )
    if rules["recurring_without_sensor"]:
        out += ["", "### 再発していて、sensor の名前が出ない規則", ""]
        out += [
            f"- {r['file']}:{r['line']}「{r['title']}」"
            for r in rules["recurring_without_sensor"]
        ]
    if report["unnamed_sensors"]:
        out += ["", "### どの規則にも名前が出ない決定的な sensor", ""]
        out += [
            f"- {s['kind']}「{s['name']}」（{s['where']}）"
            for s in report["unnamed_sensors"]
        ]

    if report["findings"]:
        out += ["", "## 確かめること", ""]
        out += [f"- {f['where']} {f['message']}" for f in report["findings"]]

    out += [
        "",
        "## 部品",
        "",
        "| 層 | 区分 | 部品 | 場所 | 件数 | 補足 |",
        "|---|---|---|---|---|---|",
    ]
    for part in report["parts"]:
        out.append(part_row(part))

    hooks = report["hooks"]
    if hooks:
        out += [
            "",
            "## hook",
            "",
            "| イベント | 役割 | 本数 | コマンド |",
            "|---|---|---|---|",
        ]
        events: dict[str, list[dict[str, object]]] = {}
        for hook in hooks:
            events.setdefault(hook["event"], []).append(hook)
        for event, members in events.items():
            labels = sorted({str(h["label"]) for h in members})
            out.append(
                f"| {event} | {EVENT_ROLE_LABELS[members[0]['role']]} | {len(members)} | {md(' / '.join(labels))} |"
            )
        out += [
            "",
            "| コマンド | 型 | イベント | 設定 | スクリプト |",
            "|---|---|---|---|---|",
        ]
        commands: dict[tuple[str, str, str], list[dict[str, object]]] = {}
        for hook in hooks:
            commands.setdefault(
                (str(hook["label"]), str(hook["type"]), str(hook["source"])), []
            ).append(hook)
        for (label, kind, source), members in commands.items():
            found = members[0]["script_found"]
            script = (
                {True: "あり", False: "見つからない", None: "確かめられない"}[found]
                if members[0]["script"]
                else "—"
            )
            names = " / ".join(dict.fromkeys(str(h["event"]) for h in members))
            out.append(
                f"| {md(label)} | {kind} | {md(names)} | {md(source)} | {script} |"
            )

    if report["permissions"]:
        out += [
            "",
            "## 許可と sandbox",
            "",
            "| 設定 | allow | ask / prompt | deny / forbidden | 既定 | sandbox |",
            "|---|---|---|---|---|---|",
        ]
        for p in report["permissions"]:
            out.append(
                f"| {md(p['source'])} | {p['allow']} | {p['ask']} | {p['deny']} | {p['mode'] or '—'} | {p['sandbox'] or '—'} |"
            )
    return "\n".join(out) + "\n"


def part_row(part: dict[str, object]) -> str:
    quadrant = (
        "2x2 の外" if part["role"] == OUTSIDE else f"{part['role']} / {part['method']}"
    )
    count = f"{part['count']}{part['unit']}"
    return f"| {part['layer']} | {quadrant} | {md(part['kind'])} | {md(part['where'])} | {count} | {md(part['note'])} |"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("roots", nargs="*", help="リポジトリのルート")
    parser.add_argument(
        "--user",
        action="store_true",
        help="利用者の設定（ホームの .claude / .codex）も読む",
    )
    parser.add_argument(
        "--home", default=None, help="ホームディレクトリ（既定は利用者のホーム）"
    )
    parser.add_argument("--json", action="store_true", help="JSON で出す")
    args = parser.parse_args(argv)
    home = (
        Path(args.home).expanduser().resolve() if args.home else Path.home().resolve()
    )
    roots: list[Root] = []
    if args.user:
        roots.append(Root("~", home, True))
    for raw in args.roots:
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            print(f"harness-inventory: ディレクトリを読めない: {raw}", file=sys.stderr)
            return 2
        roots.append(Root(raw.rstrip("/") or "/", path, path == home))
    if not roots:
        print("harness-inventory: ROOT か --user を渡す", file=sys.stderr)
        return 2
    if not home.is_dir():
        print(f"harness-inventory: ホームを読めない: {home}", file=sys.stderr)
        return 2
    report = build_report(roots, home)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
