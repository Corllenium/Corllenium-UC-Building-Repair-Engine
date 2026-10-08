# Jev pilot + Claude Code mods — plan for a new controller session

> **For the new session:** read this file, then `AGENTS.md`, then `CLAUDE.md`. You are the **controller**:
> claim jobs with `tools/jobs.py`, dispatch sub-agents (`engine-builder`, `rules-reviewer`), review, merge.
> REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Mods are built with the `plugin-authoring` skill.

**Goal:** (A) land Jev, TypeSafe's confidence-scored decision model, as a *suggest-only* helper in the engine;
(B) build Claude Code mods that enforce this repo's rules and show its state, so agents stop breaking rules by
accident.

**Written:** 2026-10-08, by the session that ran P0-13/P0-16/P0-18. **Owner:** Gabriel.

**Spec:** `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md` §9 (Decision hooks and Jev, approved by the
owner 2026-10-03). Plan text for the pilot: `docs/superpowers/plans/2026-10-03-repair-engine-p0.md` **Task 17**.
Follow-ups: `docs/superpowers/plans/2026-10-03-repair-engine-p1-p2.md` rows **P1-D1** and **P1-D2**.

## Global constraints (binding, from AGENTS.md and spec §9)

- **Jev never decides** whether to delete or keep geometry, a guard tolerance, or a Validator verdict. It only
  suggests: answers are pre-filled, and the owner or the deterministic rules confirm them.
- **Only text leaves the machine:** group names, material names and categories, small numbers. Never meshes,
  textures or the model.
- **The secret:** the engine reads `TYPESAFE_API_KEY` at run time, from the process environment first, else only
  that one line of the git-ignored repo-root `.env` (owner decision 2026-10-08; `engine/decide/jev.py::read_env_key`,
  `engine.cli decide-pilot --env-file <path>`). Agents never open, print, grep, write or commit `.env*`, and never
  ask for the key in chat. A test asserts that the key appears in no `repr`, log or exception text.
- **No key or no SDK** means `source = "none"`, and the pipeline never waits on Jev.
- **Worktrees:** one job = one brief, one branch, one worktree. Use `claude/<id>` in `.claude/worktrees/<id>`,
  from `feat/repair-p0` for engine code. Never a bare `cd`: use subshells or `git -C`. Stage files by name.
- **Python:** `"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"` with `PYTHONPATH` set to the worktree root.
- **Test first**, commit after every item, a review before every merge, and the records after every step
  (ledger, HANDOFF §2, session record, `tools/jobs.py render`).
- **Prompt audit:** a mod that injects text into the system prompt (`prompt.compose`) counts as an agent prompt.
  Run `prompt-auditor` on it (AGENTS.md §7).

## State (re-measure at the start; last updated 2026-10-08)

`tools/jobs.py list` and the ledger `.superpowers/sdd/2026-10-08-jev-and-claude-mods/progress.md` are the truth; this
table only says where the plan stood.

| Fact | Value |
|---|---|
| Part A | merged: `P0-17` and `P0-17b` (`engine/decide/`, the `decide-pilot` command). Pilot run 2 is in the ledger |
| Part B | `M1` `uc-guard` and `M1b` merged; `M2` `uc-status` approved, waits for the owner's on-screen check; `M3` waits for owner decision 4 |
| `typesafe-sdk` and the key | installed, and the pilot ran against the real API (ledger). How the key is read: "The secret" above |
| `feat/repair-p0` | holds P0-13 (signed `engine/validate/targets.json`), P0-16, P0-17, P0-17b and P0-18; checked out in `.claude/worktrees/repair-p0` by the P0 session |

## Owner actions (only the owner can do these; the session asks and waits)

1. **Put the key in the repo-root `.env` himself** as the line `TYPESAFE_API_KEY=...` (done 2026-10-08). Claude never
   handles the value.
2. **OK the install** of `typesafe-sdk` into `.venv` (already approved 2026-10-03; confirm once in chat).
3. **Approve hot reloading** when Claude Code asks "Enable hot reloading for this session?" (needed for part B).
4. **After the pilot:** decide where Jev stays: inventory pre-fill, material categories for E5, tie-break
   suggestions in the floor review, or review triage (Task 17 "Done when").

---

## Part A — Jev

### Task A1 = queue jobs P0-17 and P0-17b: the pilot (done; owner decision 4 is open)

Merged into `feat/repair-p0`. The code is the interface: read `engine/decide/jev.py` (`Decision`, `JevDecider`,
`NoulQ`/`ChoiceQ`/`ScoreQ`, `classify_group_names`, `classify_materials`) and `engine/decide/pilot.py`, not the P0 plan's
Task 17 text. That text differed from the live API in four places, so a later Jev job checks its interface against the
SDK's documentation or a measured call before it is dispatched:
- a `Noul` answer carries no confidence: the wrapper maps the probability p to `confidence = max(p, 1 - p)`;
- the state sent with the questions is a dict, not a string;
- a `Score` takes at most 10 levels and a `Choice` at most 255 options; `JevDecider.ask` checks both before any call. A
  16-level floor `Score` made 17 of the first 57 pilot calls fail with HTTP 400, so the floor is a 16-option `Choice`;
- the pilot's truth is the confirmed `data/campus/campus_map.json`, not the Task 10 inventory.

Pilot command: `decide-pilot` with `--source`, `--materials`, `--map` and `--out` (`engine/cli.py`). `data/` is
git-ignored and absent from worktrees, so a run from a worktree names the main checkout's `data/campus/` files.

**Open:** owner decision 4 (where Jev stays: inventory pre-fill, material categories for E5, tie-break suggestions in the
floor review, or review triage). The numbers are in the ledger.

### Task A2 = P1-D1 then P1-D2 (later; not in this session unless P1-K1 has landed)

`engine/decide/decider.py`:
- question types, with the chain rules → Jev (SUGGEST) → owner queue;
- a `data/decide/log.jsonl` log and a cache by state hash;
- modes OFF/SUGGEST/AUTO, with promotion at ≥ 95 % agreement over ≥ 50 decisions.

D1 depends on the kernel job P1-K1. Do not start it before P1-K1 is merged. Spec §9 has the question table
per engine (`e5.winner`, `e4.same_look`, `e8.opening_kind`, …).

---

## Part B — Claude Code mods (`plugin-authoring` skill)

**What a mod is here:**
- a plugin of function hooks that the Claude Code engine hot-reloads in the session;
- it can block or rewrite tool calls (`tool.call`), add a status line, a band above the prompt, a pane, a toast
  or a slash command, and run on a timer;
- its files are `.claude-plugin/plugin.json`, `hooks/hooks.json` and `hooks/register.tsx`, written under the
  session's `dev-mods` folder (the skill gives the path);
- each one is checked with `claude plugin validate`, `tsc -p` and `claude plugin test`.

**When one is finished,** copy it into the repo under `tools/claude-mods/<name>/` so every session (and the
owner's terminal, `claude --plugin-dir`) can load it.

**Rule:** a new mod must replace something or fill a real gap (global rule 6). The three below each fill a gap
measured in past sessions. Nothing else gets built without the owner asking.

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

### Task B2 = queue job M2: `uc-status` (status line plus a band)

**Gap:** the controller loses track of which job and worktree it is in, and of what is running. That cost a
compaction recovery today.

**What it does:**
- **Status line:** current branch, worktree name, and the claimed job from `data/jobs/queue.json`
  (`P0-17 claimed`).
- **Band above the prompt:**
  - counts of queue jobs by status;
  - a warning when the main checkout has uncommitted files in paths this session staged before;
  - a reminder when commits were made but the ledger (`.superpowers/sdd/*/progress.md`) was not touched since.
- **Data access:** read-only, through `$.fs` and `$.process` (`git`).

**Done when:** it is green, it shows correct values in a screenshot, and it is copied to `tools/claude-mods/uc-status/`.

### Task B3 = queue job M3: `jev-suggest` pane (only after A1's pilot and owner decision 4)

**Gap:** Jev's SUGGEST mode needs the owner to confirm answers. The dashboard floor review (P4) does not exist yet.

**What it does:** a pane opened by `/jev-review` that lists pending suggestions from `data/decide/log.jsonl`, with
the question, the answer and the confidence, and **Accept** or **Change** buttons that write the owner's
decision back.

**Limit:** it is an interim tool. Once the dashboard floor review exists (P4), retire it or keep it only if the
owner wants both. That decision is the owner's, so ask him before building B3.

---

## Order and orchestration

1. **Start:** run `tools/jobs.py list` and read the ledger; re-measure the "State" table.
2. **B1 `uc-guard`:** done (M1, M1b merged). The controller builds a mod with `plugin-authoring`, then `rules-reviewer`
   reviews it.
3. **A1 (P0-17, P0-17b):** done. For a later engine job:
   - claim it, then create the worktree `claude/<id>` from `feat/repair-p0`;
   - dispatch `engine-builder` (sonnet) with the brief's text inline and the constraints above;
   - review it with `rules-reviewer`.
4. **B2 `uc-status`:** approved by review; after the owner's on-screen check, merge it.
5. **Stop and report to the owner:**
   - the pilot numbers;
   - mods B1 and B2 live;
   - ask decision 4 (where Jev stays) and whether to build B3.

**Merging into `feat/repair-p0`:** that branch is checked out in `.claude/worktrees/repair-p0` by the P0 session, so
git refuses a merge from anywhere else. Ask that session for the `--no-ff` merge and for its engine and tools suites;
every merge so far waited for its "go".

**Agents:** at most two concurrent (rate limit). Describe the work inline in each dispatch, not only by pointing at
a file.

## Acceptance (paste real output into the ledger)

- `( cd "<wt>" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_decide_jev.py -q -p no:cacheprovider )`
- The full engine suite is green on the merged `feat/repair-p0`.
- `claude plugin validate`, `tsc -p` and `claude plugin test` pass for each mod.
- `data/campus/jev_pilot.json` exists, and the ledger quotes its accuracy, coverage, latency and tokens.
