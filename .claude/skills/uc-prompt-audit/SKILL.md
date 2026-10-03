---
name: uc-prompt-audit
description: Use whenever an agent prompt file in UC MODEL FIXER is added or changed (AGENTS.md, CLAUDE.md, HERMES.md, .claude/agents, .claude/skills, brief templates, Hermes or Jev prompt text) — dispatch the prompt-auditor subagent on the changed files, then review its proposed diff before anything is applied.
---

# Prompt audit as a standing step

The owner asked (2026-10-03) for Anthropic's Prompt Audit (`claude-api` skill, `shared/prompt-audit.md`)
to run with a subagent as the work goes forward. The rules it must respect are `AGENTS.md` §3-6.

## When

- After any commit that adds or changes:
  - `AGENTS.md`, `CLAUDE.md`, `HERMES.md`;
  - `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`;
  - `docs/superpowers/records/briefs/TEMPLATE.md`;
  - prompt-assembly code (`tools/auto_continue.py::build_prompt`);
  - the Hermes one-shot prompts;
  - Jev question schemas (`engine/decide/`).
- Before a phase merges into `feat-dashboard`: a full-surface audit.

## How

1. Dispatch the `prompt-auditor` agent (model opus), naming the changed files as its scope, or "full
   surface".
2. It writes `docs/superpowers/records/prompt-audit/<date>-<scope>-report.md` and a proposed `.diff`, and
   applies nothing.
3. **The controller reviews each proposed change:**
   - accept the clear ones;
   - send every change to `AGENTS.md` §3-6, and every `flag`, to the owner;
   - re-test behaviour where the procedure says so (probe behaviour, not self-report).
4. Apply the accepted hunks in a normal commit that names the report.
5. Add a line to the ledger: the counts per group and what was applied.
