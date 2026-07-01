---
name: context-audit
description: Audit project context files and suggest a cleaner split across rules, Skills, MCP, hooks, and subagents.
---

Run a context audit for: $ARGUMENTS

Use the portable skill at `skills/context-audit/SKILL.md`.

Follow this scope:

1. Inspect `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` if present
2. Inspect `.claude/commands/`, `.claude/skills/`, `skills/`, `.claude/agents/`, `.claude/mcp/`, `.claude/hooks/`
3. Classify findings as overloaded rules, skill candidates, weak triggers, missing reference split, tool context bloat, subagent mismatch, scriptable gates, or missing ignores
4. Return findings first, then proposed moves, then a minimal patch plan
5. If the user asked for implementation, apply the smallest scoped edits and verify the diff
