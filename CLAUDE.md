@AGENTS.md

# Claude-only notes for UC MODEL FIXER

The rules above (`AGENTS.md`) bind every agent. These notes add only what is specific to Claude Code sessions.

- **Controller workflow:** superpowers:subagent-driven-development.
  - The ledger is `.superpowers/sdd/<plan>/progress.md` (git-ignored, so `git add -f` it with the records).
  - The briefs come from the SDD `task-brief` script; reviews come from its `review-package` script. Pass absolute plan paths, and run the scripts from the main checkout.
- **Sub-agents** (`.claude/agents/`):
  - `engine-builder`, `unit-runner`, `rules-reviewer`, `hermes-reviewer`, `census-analyst`;
  - later: `floor-validator`, `skp-builder`.
  - A sub-agent never dispatches sub-agents and never merges.
- **Skills** (`.claude/skills/`): `uc-repair-rules`, `uc-handoff`, `uc-run-unit`, and later `uc-validate-floor` and `uc-comparison-skp`.
- **Hermes:** when the owner runs Hermes on the queue, its branches arrive as `awaiting-review` jobs.
  - Review each with `hermes-reviewer` and re-run its acceptance commands.
  - Then `tools/jobs.py review <id> --pass` and merge, or `--changes "<note>"` with a fix brief.
- **Records after every step:**
  - the ledger;
  - HANDOFF §2 and the session record (`docs/superpowers/records/`);
  - `tools/jobs.py render` for `QUEUE.md`;
  - then commit them by name.
