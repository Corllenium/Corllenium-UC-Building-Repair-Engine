# uc-guard — a Claude Code mod that enforces AGENTS.md

`uc-guard` is a `tool.call` hook. It **denies** the tool calls below, naming the rule they break, and
posts a toast. Every other call passes unchanged. It covers the main session and its sub-agents.

Queue job M1, plan `docs/superpowers/plans/2026-10-08-jev-and-claude-mods.md` (Task B1).

## The rules

| # | Denied | Tools | Rule |
|---|---|---|---|
| 1 | Writing or deleting under the CHECKPOINT-17 export `D:\PROJECTS\UC ENVIRONMENT BUILDING\`, the master `D:\PROJECTS\UC\02-SKETCHUP\current\`, or `...\CHECKPOINT-17-BACKUP\` (write verbs `rm`, `mv`, `Remove-Item`, `Set-Content`, ...; a copy or redirect that lands there). Reads and engine commands that read the export pass. | Bash, PowerShell, Write, Edit | AGENTS.md §3 "Never touch" and the §2 table |
| 2 | A bare `cd`, `pushd` or `popd` at the top level of a Bash command; `cd`/`Set-Location`/`Push-Location` anywhere in PowerShell, where parentheses don't scope it. `( cd "<dir>" && ... )` and `git -C` pass. | Bash, PowerShell | AGENTS.md §8 |
| 3 | `git add -A` / `.` / `--all` / `-u`, `git commit -a`, `git stash` without `push -m`, `git stash save` or `clear`, and `git push --force` / `-f` / `+ref`. Staging by name passes. | Bash, PowerShell | AGENTS.md §3 "Shared working tree" |
| 4 | `docker restart|stop|rm|kill|start|pause` on `fixer-api`, `fixer-web` or `fixer-db`; `docker compose up|down|restart|stop|rm|kill|start|pause`; `psql` on the live database `fixer`. `docker ps/logs` and `fixer_test_*` databases pass. | Bash, PowerShell | AGENTS.md §3 "Never touch" (HANDOFF §8) |
| 5 | Reading or writing `.env`, `.env.local`, `auth.json`, or anything under `Corllenium-Phone-session-Config`. `.env.example` passes. | Read, Write, Edit, Grep, Bash, PowerShell | Owner rule 2026-10-08 (Jev plan, "The secret"); code reads keys at run time |
| 6 | Writing into `OBJ FIXED RESULT\` or `MODEL FIXER ENGINE FILES\04-COLORING\` / `\05-FIXING\`, unless the command runs from `.claude/worktrees/verified`. Read-only commands (`ls`, `cat`, `Get-ChildItem`, ...) pass. | Bash, PowerShell, Write, Edit | AGENTS.md §3 (the owner's folders take only committed code) |

The shell checks are heuristics that catch the mistakes earlier sessions made. They don't fully parse the shell:
a script that writes a file from inside `python -c` is not seen. The guard is a backstop, and AGENTS.md is still the rule.

## Load it

- **In a Claude Code session:** start Claude with `claude --plugin-dir "D:/PROJECTS/UC MODEL FIXER/tools/claude-mods/uc-guard"`,
  or list that folder in `CLAUDE_CODE_PLUGIN_DIRS`.
- **Desktop app session:** a controller that builds a mod under the session's `dev-mods` folder hot-reloads it once the owner
  enables hot reloading.

## Check it

```bash
claude plugin validate "tools/claude-mods/uc-guard"
claude plugin test "tools/claude-mods/uc-guard"
```

Use Claude Code 2.1.293 or newer (the `plugin test` command). `tests/rules.test.ts` holds a denied and an allowed case
for every rule, plus two cases through the engine (a denied call never reaches the tool; an allowed one reaches it unchanged).
To type-check, use the tsconfig from the header of the engine's `claude-code.d.ts`, or the one the engine writes next to
the loaded mod in `.claude-plugin/types/`.
