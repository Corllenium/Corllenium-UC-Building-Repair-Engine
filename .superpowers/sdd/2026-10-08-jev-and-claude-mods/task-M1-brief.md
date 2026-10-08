### Task B1 = queue job M1: `uc-guard` (the highest value)

**Gap:** the rules exist only as text, and agents still break them. On 2026-10-08 a bare `cd` moved this session
into the main checkout. Earlier sessions also overlapped API test databases and staged with `git add -A`.

**What it does:** a `tool.call` hook on Bash, PowerShell, Write and Edit that **denies**, naming the AGENTS.md
rule:
- a write or delete under `D:\PROJECTS\UC ENVIRONMENT BUILDING\` (the live export folder), the master
  `D:\PROJECTS\UC\02-SKETCHUP\current\`, or `...\CHECKPOINT-17-BACKUP\`;
- a bare `cd <dir>` at the start of a Bash command, outside a `( ... )` subshell;
- `git add -A`, `git add .`, `git commit -a`, `git stash` without `push -m`, `git push --force`;
- `docker restart|stop|rm|compose up` on `fixer-api`, `fixer-web` or `fixer-db`, and `psql ... fixer`
  (the live database);
- reading `.env`, `.env.local`, `auth.json`, or anything under `Corllenium-Phone-session-Config`;
- writes into `OBJ FIXED RESULT\` or `MODEL FIXER ENGINE FILES\04-COLORING|05-FIXING` from any place other than
  `.claude/worktrees/verified`.

It **allows** everything else unchanged. Every denial also posts a toast.

**Tests (`*.test.ts`):** one denied and one allowed case per rule, with the allowed cases including
`( cd "<wt>" && ... )` and `git -C`.

**Done when:**
- validate, tsc and test are green;
- the owner has seen one live denial in the session;
- the mod is copied to `tools/claude-mods/uc-guard/` with a README naming each rule and its AGENTS.md section;
- a rules-reviewer has passed it.

