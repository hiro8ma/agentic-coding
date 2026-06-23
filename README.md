# agentic-coding

Knowledge, skills, and configuration templates for developing with coding agents — Claude Code, OpenAI Codex, Google Gemini CLI / Antigravity, and Cursor.

## Overview

This repository accumulates reusable knowledge for agent-driven development across vendors: rule files ([CLAUDE.md](https://code.claude.com/docs/memory) / [AGENTS.md](https://agents.md/) / GEMINI.md), [Agent Skills](https://agentskills.io) (`SKILL.md`), [commands](https://code.claude.com/docs/commands), [hooks](https://code.claude.com/docs/hooks), [MCP servers](https://code.claude.com/docs/mcp), and [settings](https://code.claude.com/docs/settings). Skills are portable Markdown + directories, so the same skill runs across Claude Code, Codex, Cursor, VS Code / GitHub Copilot, and Gemini CLI.

## Structure

- **CLAUDE.md** - Main rule file (per-repo instructions)
- **docs/** - Cross-agent knowledge
  - `agent-skills.md` - Agent Skills spec, progressive disclosure, cross-vendor adoption
  - `subagents.md` - Subagent patterns
  - `coding-agent-github-actions.md` - Running coding agents in CI
  - `pr-review-bot-workflow.md` - PR review bot
  - `security.md` - Security guidelines
- **skills/** - Portable Agent Skills (`SKILL.md` + scripts/references/assets)
  - `knowledge-note/` - Author a knowledge note
  - `weekly-report/` - Generate a weekly progress report
- **.claude/** - Claude Code configuration and language guidelines
  - `commands/` - Custom slash commands
  - `skills/` - Claude Code skills
  - `hooks/` `mcp/` `settings/` - Configuration templates
  - `architecture/` - Common architecture patterns
  - `go/` `rust/` `typescript/` - Per-language style, guidelines, and patterns

## Skill portability across agents

| Agent | Skill location | Invocation |
|-------|----------------|------------|
| Claude Code | `.claude/skills/` | auto / slash command |
| OpenAI Codex | `.agents/skills/` | auto / `/skills` / `$cmd` |
| VS Code / GitHub Copilot | `.github/skills/` | auto-detect |
| Google Antigravity | `.agents/skills/` | auto-detect |
| Cursor | `SKILL.md` detection | auto / slash command |

A `SKILL.md` body is identical across tools; only the detection directory differs. See `docs/agent-skills.md` for details.

## Commands

| Command | Description |
|---------|-------------|
| `/review` | Review code changes in current branch |
| `/explain` | Explain code in a file |
| `/test` | Run tests for the project |
| `/lint` | Run linter for the project |
| `/format` | Format code in the project |
| `/build` | Build the project |
| `/status` | Show git status |

## Skills

| Skill | Description |
|-------|-------------|
| `/refactor <target>` | Refactor specified code |
| `/fix <issue>` | Fix a reported issue |
| `/doc <target>` | Generate documentation |
| `/add <feature>` | Add a new feature |
| `/search <term>` | Search codebase for term |
| `/rename <old> <new>` | Rename across codebase |
| `/debug <issue>` | Debug an issue |
| `/commit-message` | Generate commit message from staged changes |
| `/diagram <target>` | Create ASCII diagram |
| `/migrate <target>` | Migrate code to new version/framework |
| `/security <target>` | Security audit |

## Usage

Apply the contents of this repository to your project so coding agents generate and review code following consistent conventions, and reuse the portable skills across any supported agent.
