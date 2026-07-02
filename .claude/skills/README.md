# Skills

[Skills](https://code.claude.com/docs/skills) are custom slash commands that accept arguments.

## Usage

Place `.md` files in `.claude/skills/` directory. Use `$ARGUMENTS` placeholder for user input.

```
.claude/skills/fix.md  →  /fix <issue>
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `/refactor <target>` | Refactor specified code |
| `/fix <issue>` | Fix a reported issue |
| `/doc <target>` | Generate documentation |
| `/add <feature>` | Add a new feature |
| `/search <term>` | Search codebase for term |
| `/rename <old> <new>` | Rename across codebase |
| `/debug <issue>` | Debug an issue |
| `/commit-message` | Generate commit message |
| `/diagram <target>` | Create ASCII diagram |
| `/migrate <target>` | Migrate code |
| `/security <target>` | Security audit |
| `/context-audit <target>` | Audit context design across rules, Skills, MCP, hooks, and subagents |
| `/spec-workflow <target>` | docs/ と .steering/ に仕様駆動開発ドキュメントを作成・更新する |

## Creating Skills

Skills support YAML frontmatter for metadata:

```markdown
---
name: fix
description: Fix a reported issue
---

Fix the issue: $ARGUMENTS

1. Understand the reported issue
2. Locate the relevant code
3. Implement a fix
4. Verify and run tests
```
