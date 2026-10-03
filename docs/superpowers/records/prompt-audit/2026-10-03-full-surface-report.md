# Prompt audit: full surface, 2026-10-03

Anthropic's Prompt Audit (`claude-api` skill, `shared/prompt-audit.md`, fetched 2026-10-03), Steps 0-6,
run non-interactively by the `prompt-auditor` role. The proposed diff is
`2026-10-03-full-surface.diff` beside this file: 15 hunks, nothing applied, nothing committed.

## Assumptions (Step 0)

**Scope**, as dispatched, in the main checkout `D:\PROJECTS\UC MODEL FIXER` (branch `feat-dashboard`, HEAD `0d2f15e`):
`AGENTS.md`, `CLAUDE.md`, `HERMES.md`; `.claude/agents/*.md` (6); `.claude/skills/*/SKILL.md` (4);
`docs/superpowers/records/briefs/TEMPLATE.md`; `docs/superpowers/records/hermes/README.md`;
`tools/auto_continue.py::build_prompt` (lines 349-408, with its caller `launch`);
`data/hermes_runs/1003-1923-next/prompt.md` (a git-ignored record of a past one-shot run, job P0-08).

**Skipped:**
- `~/.claude/CLAUDE.md` and the user's auto-memory: user-level, not named.
- `.claude/settings*.json`, `.mcp.json`, `.env*`: never read.
- `.claude/worktrees/`, `.hermes/worktrees/`: other checkouts.
- `.claude/launch.json`, `.claude/scheduled_tasks.lock`: not prompt text.
- `HANDOFF.md`, `WORK-CLAIMS.md`, `QUEUE.md`, the spec and the plans were read only to check facts.
- None of these exist: nested `CLAUDE.md` or `AGENTS.md`, `CLAUDE.local.md`, `.claude/commands`, rule files, output styles, skill reference files.

**Targets:**
- `CLAUDE.md`, `AGENTS.md` and the four skills, as read by Claude Code: **Claude Opus 5.5**.
- Agents with `model: opus` (`prompt-auditor`): Claude Opus 5.5.
- Agents with `model: sonnet` (`engine-builder`, `hermes-reviewer`, `rules-reviewer`): **Claude Sonnet 5**, as dispatched.
  The migration guide lists Claude Sonnet 5.5 as the current Sonnet, and the `sonnet` alias may resolve to it.
  No finding below depends on which.
- Agents with `model: haiku` (`census-analyst`, `unit-runner`): **Claude Haiku 4.5**.
- **Hermes (`gemini-3.8-flash`)** reads `HERMES.md`, `AGENTS.md`, `hermes/README.md`, the `build_prompt` text and the one-shot prompt.
  For that reader only the model-independent groups were applied: stale facts, conflicts between files, architecture.
- `TEMPLATE.md` is read by both: Group 1 for the Claude reader, the other groups for both.
- This is not a migration; no model ID changes. `shared/model-migration.md` was read for its per-target sections:
  Claude Opus 5.5, the Claude Opus 5 behavioral shifts, Claude Sonnet 5, Claude Sonnet 5.5.

**Protected text:** `AGENTS.md` §3-6 are the owner's rules. Anything that would weaken a prohibition or a
safety rule is a `flag`. Every `AGENTS.md` hunk (D10, D11) needs the owner's OK (`AGENTS.md:5`, and see F5).

## Summary

1. **The job-handoff skill's description does not load (F1).** The frontmatter of
   `.claude/skills/uc-handoff/SKILL.md` is not valid YAML: there is an unquoted `: ` after "alike".
   - Claude Code falls back to the H1 heading. This session lists the skill as "Taking and handing over queued jobs".
   - So "reviewing", "review, merge, records" and `tools/jobs.py` never reach routing.
   - Quoting the value fixes it (D8). The repo's own frontmatter test passes the broken file (F21).
2. **`AGENTS.md` tells every agent to edit `AGENTS.md` after every step (F2).** `AGENTS.md:63` says
   "update section 2 of this page". The line was copied from `HANDOFF.md:220`, where "this page" meant HANDOFF.
   - In `AGENTS.md` it names the owner-controlled §2 table.
   - That contradicts `AGENTS.md:5`, the file's own note at `:66`, §7.6 (`:137`) and `CLAUDE.md:20`, all of which say HANDOFF §2.
   - Fix: D10. It needs the owner's OK.
3. **Who may accept edits to `AGENTS.md` is ruled two ways (F5, flag).**
   - `AGENTS.md:5` requires the owner's OK for any change.
   - The later `AGENTS.md:140-141` and `uc-prompt-audit/SKILL.md:29-30` let the controller accept "clear" changes outside §3-6.
   - This decides how D10 and D11 of this very diff may be applied.

| Group | Findings | In the diff | Flags |
|---|---|---|---|
| 1 Dated prompt text | 1 | 1 | 0 |
| 2 Brittle skill and configuration files | 16 | 7 | 9 |
| 3 Tool descriptions (agent and skill descriptions) | 2 | 2 | 0 |
| 4 Request config and architecture | 0 | 0 | 0 |
| Outside the audit's scope | 2 | 0 | 2 |
| **Total** | **21** | **10 (15 hunks)** | **11** |

## Inventory (Step 1)

| File | Lines | Reader and target | Commits (`git blame`) |
|---|---|---|---|
| `AGENTS.md` | 154 | Claude Opus 5.5; Hermes | 3663629; `:138-141` 0d2f15e |
| `CLAUDE.md` | 22 | Claude Opus 5.5 | 3663629 |
| `HERMES.md` | 134 | Hermes | 4285034, 6b1d3dd, ce3a931 (§1-4); cdb0cfc, b41d7e7, 3663629 (§0, `:92-94`) |
| `.claude/agents/census-analyst.md` | 23 | Haiku 4.5 | a9785a2 |
| `.claude/agents/engine-builder.md` | 27 | Sonnet 5 | a9785a2 |
| `.claude/agents/hermes-reviewer.md` | 28 | Sonnet 5 | a9785a2 |
| `.claude/agents/prompt-auditor.md` | 39 | Opus 5.5 | 0d2f15e |
| `.claude/agents/rules-reviewer.md` | 31 | Sonnet 5 | a9785a2 |
| `.claude/agents/unit-runner.md` | 20 | Haiku 4.5 | a9785a2 |
| `.claude/skills/uc-handoff/SKILL.md` | 47 | Opus 5.5 | a9785a2 |
| `.claude/skills/uc-prompt-audit/SKILL.md` | 33 | Opus 5.5 | 0d2f15e |
| `.claude/skills/uc-repair-rules/SKILL.md` | 45 | Opus 5.5, and `engine-builder` | a9785a2 |
| `.claude/skills/uc-run-unit/SKILL.md` | 35 | Opus 5.5, and `unit-runner` | a9785a2 |
| `docs/superpowers/records/briefs/TEMPLATE.md` | 42 | Claude agents and Hermes | cdb0cfc |
| `docs/superpowers/records/hermes/README.md` | 34 | Hermes | cdb0cfc |
| `tools/auto_continue.py:349-408` (`build_prompt`) | 60 | Hermes, automatic runs (runner stopped until P5) | ce3a931 |
| `data/hermes_runs/1003-1923-next/prompt.md` | 10 | Hermes, one-shot run | git-ignored, no history |

## Provenance (Step 2)

| Commit | Date | Subject |
|---|---|---|
| 4285034 | 09-22 20:29 | docs: add dashboard build plan and HERMES project memory |
| 6b1d3dd | 09-24 18:37 | docs(record): handoff for Hermes and any agent that continues after a usage limit |
| ce3a931 | 09-25 21:13 | feat(tools): Hermes continues the running brief job while Claude is at its usage limit |
| 3663629 | 10-03 17:53 | docs(rules): AGENTS.md is the single rules source for Claude, Hermes and every agent |
| cdb0cfc | 10-03 17:54 | docs(hermes): the entry point for an owner-started Hermes session, the brief template and the report format |
| a9785a2 | 10-03 17:56 | docs(agents): project skills and sub-agent roles for the repair engine |
| b41d7e7 | 10-03 19:03 | docs(hermes): when the owner names a job, Hermes claims that one |
| 0d2f15e | 10-03 19:35 | docs(agents): prompt audit as a standing step |

No line traces to a retired Claude model, and no retired model name appears in the scope. The surface is
young (09-22 to 10-03), so almost every finding is a stale fact or a conflict between files, not dated
prompt style.

## Findings (Steps 3-5), highest confidence first

### F1. `uc-handoff` frontmatter is not valid YAML, so its description never loads
- **Location:** `.claude/skills/uc-handoff/SKILL.md:3`
- **Evidence:** `description: Use when taking, doing, handing in or reviewing a queued job in UC MODEL FIXER (tools/jobs.py) — for Claude and Hermes alike: claim, worktree, brief, report, done, review, merge, records.`
- **Pattern:** Group 3, "Vague one-liners … under-described" (routing text). The loaded description is the
  H1 heading, and a YAML syntax error is the cause.
- **Why obsolete:** `yaml.safe_load` fails with "mapping values are not allowed here" at frontmatter line 2,
  column 138 (the unquoted `: ` after "alike").
  - This session's skill list shows `uc-handoff: Taking and handing over queued jobs`, which is its H1 heading.
  - `uc-repair-rules` and `uc-run-unit` show their frontmatter descriptions.
  - Routing therefore loses "reviewing … review, merge, records" and `tools/jobs.py`.
- **Confidence:** High. The parse fails, and the fallback is visible in the session's skill list.
- **Action:** `rewrite`: put the value in double quotes; the text itself is unchanged.
  - Hunk **D8**.
  - Verified: the patched frontmatter parses, and the description loads as written.

### F2. "Update section 2 of this page" points at `AGENTS.md`, not HANDOFF
- **Location:** `AGENTS.md:63-64`
- **Evidence:** `- **Records**: after every step append to the ledger, update section 2 of this page and the session record's history, and commit them`
- **Pattern:** Group 2, "Volatile specifics": a reference the repository contradicts.
- **Why obsolete:** The line is copied verbatim from `HANDOFF.md:220`, where "this page" is HANDOFF.
  - In `AGENTS.md`, "this page" is `AGENTS.md`, whose §2 table may change only with the owner's OK (`AGENTS.md:5`).
  - The same file's note (`:66`: "section 2" in this list points to `HANDOFF.md`) and its §7.6 (`:137`: "the ledger, HANDOFF §2, …") disagree with it.
  - So do `CLAUDE.md:20` and `uc-handoff/SKILL.md:46`.
  - `engine-builder` reads "AGENTS.md (all sections)" (`engine-builder.md:10`) on a model that follows instructions literally.
- **Confidence:** High.
- **Action:** `rewrite` to "update HANDOFF §2 and the session record's history".
  - Hunk **D10**.
  - It is in §3: owner's OK.

### F3. The `CLAUDE.md` roster omits `prompt-auditor` and `uc-prompt-audit`
- **Location:** `CLAUDE.md:11`, `CLAUDE.md:14`
- **Evidence:** `` `engine-builder`, `unit-runner`, `rules-reviewer`, `hermes-reviewer`, `census-analyst`; `` and `` `uc-repair-rules`, `uc-handoff`, `uc-run-unit`, and later `uc-validate-floor` and `uc-comparison-skp`. ``
- **Pattern:** Group 2, "Volatile specifics".
- **Why obsolete:** `CLAUDE.md` (3663629, 17:53) predates 0d2f15e (19:35), which added
  `.claude/agents/prompt-auditor.md` and `.claude/skills/uc-prompt-audit/SKILL.md`.
  - The folders now hold 6 agents and 4 skills, and `tools/tests/test_claude_assets.py:6-8` lists the same.
  - The list is live routing help: the controller picks project skills from hundreds of installed ones.
- **Confidence:** High.
- **Action:** `rewrite`: add the two names. Hunk **D12**.

### F4. `HERMES.md` "Current Progress" is a 09-24 snapshot the records contradict
- **Location:** `HERMES.md:130-134`
- **Evidence:** `- In progress: T-junction repair (brief 01) and the side rebuild of broken slab sides (brief 02).` / `- Queued: reconcile + verify (03), review (04), dashboard fix wave (05), leftovers (06).` / `- Latest measured (2026-09-24 14:38): file A 4,692 -> 1,013 triangles, file B 7,227 -> 601, …`
- **Pattern:** Group 2, "Time-sensitive content" and "Volatile specifics" (model-independent; read by Hermes).
- **Why obsolete:** `HANDOFF.md` §3 records briefs 02, 03 and 10 as DONE (`:168-169`, `:176`).
  - Brief 03 reports 542 passed, A 1,044 / B 530.
  - New work runs from the job queue: `QUEUE.md` shows P0-01..P0-07 merged.
  - The section's own heading already defers to HANDOFF §2.
- **Confidence:** High.
- **Action:** `rewrite`: keep the heading as a pointer to HANDOFF §2 and the queue, and drop the snapshot. Hunk **D14**.

### F5. Who may accept an `AGENTS.md` change is ruled two ways
- **Location:** `AGENTS.md:5`; `AGENTS.md:140-141`; `.claude/skills/uc-prompt-audit/SKILL.md:29-30`
- **Evidence:** `Change it only with the owner's OK.` vs `Its diff is only proposed; changes to §3-6 need the owner.` and `- accept the clear ones;` / `- send every change to \`AGENTS.md\` §3-6, and every \`flag\`, to the owner;`
- **Pattern:** Group 2, "Instruction files that contradict each other".
- **Why obsolete:** The newer passages (0d2f15e) let the controller accept clear `AGENTS.md` changes outside §3-6.
  The older rule (3663629) requires the owner for every change. The newer text loosens a prohibition.
- **Confidence:** High.
- **Action:** `flag`. The owner decides between two options:
  - (a) Every `AGENTS.md` change needs the owner; then `uc-prompt-audit:30` should say "every change to `AGENTS.md`".
  - (b) Only §3-6 needs the owner; then `AGENTS.md:5` should say so.
  - Until decided, D10 and D11 are owner items.

### F6. `HERMES.md` §2 restates `AGENTS.md`'s safety rules and has drifted
- **Location:** `HERMES.md:96`, `HERMES.md:97-101`, `HERMES.md:104`
- **Evidence:**
  - `:96`: `**Vertices are never moved or invented**, except by \`engine/fixes/solidify.py\` (walls and bottoms).`
  - `:97-101`: the blocked list (weld > 0.1 mm, `select_interior_faces`, hole-filling / Make Manifold / Decimation / remeshing, opposite-normal pairs).
  - `:104`: `Region surface area must never grow (cannot bridge openings).`
- **Pattern:** Group 2, "Instruction files that contradict each other". Keep-list item 8 protects only copies that agree.
- **Why obsolete:** These lines (4285034, 09-22; 6b1d3dd, 09-24) predate `AGENTS.md` §3-4 (3663629, 10-03), and they now differ from it:
  - The blocked list lacks "Dissolve above 5°" (`AGENTS.md:75`), "whole-campus jobs" (`:78`) and the brief-13 exception (`:76-77`).
  - `:96` lacks the E5 border points (`AGENTS.md:80-83`).
  - `:104` lacks the E8 narrow flat fill that "area never grows" allows (`AGENTS.md:84-86`).
  - `HERMES.md:92-94` already names `AGENTS.md` §3-6 as the source.
- **Confidence:** High.
- **Action:** `flag`, because the older passage is a prohibition list. The owner decides between two options:
  - Replace `:96-101` and `:104` with a pointer to `AGENTS.md` §3-4.
  - Or sync them line by line.

### F7. The automatic-continuation prompt diverges from `AGENTS.md` and `hermes-reviewer` (latent)
- **Location:** `tools/auto_continue.py:379`, `:380-381`, `:390-392`, `:404` (with `REPORTS` at `:37`); `HERMES.md:65-66`
- **Evidence:** `ends with the line\n  Hermes-Auto-Run: {run_id}`; `Write {REPORTS}/{run_id}-report.md` (`docs/superpowers/records/hermes-auto`); `weld above 0.1 mm, select_interior_faces, hole fill / Make Manifold / Decimate / remeshing, treating opposite-normal coincident faces as duplicates`; `Never run the api tests: they drop a database other sessions use.`; `that prompt's rules come first.`
- **Pattern:** Group 2, "Instruction files that contradict each other" and "Volatile specifics" (model-independent; read by Hermes).
- **Why obsolete:** The runner is stopped (`data/auto_continue/STOP`, `HANDOFF.md:106`). It covers only the old
  briefs 01-15 until it moves to the queue in P5 (`WORK-CLAIMS.md:3-5`, `HERMES.md:66`). When it moves:
  - (a) Its trailer would make `hermes-reviewer.md:20` mark every commit Critical, because that check requires `Hermes-Job: <id>`, as `AGENTS.md:154` does.
  - (b) Its report lands outside `hermes/<id>-report.md` (`AGENTS.md:130`).
  - (c) Its blocked list lacks "Dissolve above 5°" and "whole-campus jobs".
  - (d) `HERMES.md:65` ("that prompt's rules come first") and `AGENTS.md:5` ("this file wins") disagree on precedence.
  - (e) The reason at `:379` is stale since `cba42a5`, which gave each session its own `fixer_test_<pid>_*` database (`AGENTS.md:43-46`). The stricter rule still suits unattended runs on older commits.
- **Confidence:** High.
- **Action:** `flag`: a prohibition list and a precedence rule, behind a paused runner. Resolve it in the P5 move.
  `tools/tests/test_auto_continue.py:295-298` pins these strings, so any rewrite moves with its test:
  "api tests", "WORK-CLAIMS", "Hermes-Auto-Run: …", "hermes-auto/…-report.md".

### F8. The base-branch rule for records-only jobs exists only in `HERMES.md:23-24`
- **Location:** `AGENTS.md:127`; `HERMES.md:27-29`; `.claude/skills/uc-handoff/SKILL.md:18-19`; `docs/superpowers/records/hermes/README.md:12`
- **Evidence:**
  - `AGENTS.md:127`: `Branches are made from the phase's integration branch (P0: \`feat/repair-p0\`).`
  - `HERMES.md:27-29`: the same, with `feat/repair-p0` hard-coded in the command.
  - `uc-handoff:18-19`: `<integration branch>`.
  - `README.md:12`: `Base: <sha of feat/repair-p0 when the worktree was made>`.
  - The newest passage, `HERMES.md:23-24`, differs: `if it names none, use \`feat-dashboard\` for a records-only job and \`feat/repair-p0\` for code.`
- **Pattern:** Group 2, "Instruction files that contradict each other": rewrite the older passages to match the newer.
- **Why obsolete:** `HERMES.md:23-24` (b41d7e7, 19:03) is newer than every other location (17:53-17:56), and the repository follows it:
  - `docs/superpowers/records/hermes/H1-report.md:3` records `Base: b41d7e7… (feat-dashboard)`; the H1 brief names no branch.
  - `QUEUE.md` puts the records job P0-06 on `feat-dashboard`.
  - Under the older text, a records-only job claimed with `next` would branch from the code branch.
- **Confidence:** Medium.
  - Assumption: the newer rule, written for owner-named jobs, holds for every job, because the base depends on the job's kind, not on how it was claimed.
  - If the owner wants it for named jobs only, drop these four hunks.
- **Action:** `rewrite` four places to the same rule (the brief's branch; else the integration branch for code, `feat-dashboard` for records-only):
  - Hunks **D9**, **D11** (owner's OK), **D13**, **D15**.

### F9. `prompt-auditor` is told to fetch and index, with neither tool granted
- **Location:** `.claude/agents/prompt-auditor.md:4`, `:12`
- **Evidence:** `tools: Read, Grep, Glob, Bash, Write` and `(fetch and index it; read \`shared/model-migration.md\` …)`
- **Pattern:** Group 2, "Volatile specifics": the file names a capability that its own tool list does not provide.
- **Why obsolete:** The `tools:` list grants no web-fetch and no index tool, so as a sub-agent only Bash can reach the URL.
  - "Index" cannot be done at all.
  - Adding WebFetch is not the fix: in this environment it returns a small-model answer about the page, not the raw procedure that must be followed exactly.
- **Confidence:** Medium.
- **Action:** `rewrite`: say the raw file is fetched through Bash (`curl -sL <url>`). Hunk **D5**.

### F10. Pointers to other prompt files that the sub-agent cannot follow without a path
- **Location:** `.claude/agents/engine-builder.md:15`; `.claude/agents/unit-runner.md:10-11`; `.claude/agents/hermes-reviewer.md:21`
- **Evidence:** `follow the skill \`uc-repair-rules\`.`; `then the skill \`uc-run-unit\`, then the brief.`; `and the rules as the \`rules-reviewer\` role does.`
- **Pattern:** Group 2, "Wrong degrees of freedom": a fragile step left to inference.
- **Why obsolete:** None of these agents' `tools:` lists grants a Skill tool, so a skill is reachable only by reading its `SKILL.md`, and no path is given.
  - `hermes-reviewer` cannot see `rules-reviewer`'s checklist without reading that file.
  - The steps involved are the pre-flight rules check before engine code, and the rules review.
  - Claude Sonnet 5 follows instructions literally and does not infer requests that were not made (`model-migration.md` → Migrating to Claude Sonnet 5 → Behavioral shifts).
  - Unverified alternative: Claude Code sub-agent frontmatter may accept a `skills:` field to preload a skill. Check its docs before using it.
- **Confidence:** Medium.
- **Action:** `rewrite`: name the file, and for `hermes-reviewer` the step. Hunks **D2**, **D7**, **D4**.

### F11. `hermes-reviewer`'s description names a `jobs.py` subcommand that does not exist
- **Location:** `.claude/agents/hermes-reviewer.md:3`
- **Evidence:** `Reviews a branch Hermes handed in (tools/jobs.py status awaiting-review) …`
- **Pattern:** Group 2, "Volatile specifics": a command that is not defined.
- **Why obsolete:** `tools/jobs.py:539-580` defines `list`, `next`, `claim`, `done`, `release`, `review`, `block`, `unblock`, `add` and `render`. There is no `status` subcommand.
  The listing command is `list --status awaiting-review` (`uc-handoff/SKILL.md:37`). The phrase may mean the job's status; the rewrite removes the ambiguity.
- **Confidence:** Medium.
- **Action:** `rewrite` to "(a tools/jobs.py job in status awaiting-review)". Hunk **D3**.

### F12. `rules-reviewer`'s description has no boundary with `hermes-reviewer`
- **Location:** `.claude/agents/rules-reviewer.md:3`
- **Evidence:** `Reviews a UC repair-engine diff against its brief and against AGENTS.md's binding rules, … Read-only; returns findings with severity and file:line.`
- **Pattern:** Group 3, "Near-duplicate overlapping tools": explicit boundaries in both descriptions.
- **Why obsolete:** Both agents review a job's diff against its brief and `AGENTS.md`.
  - `hermes-reviewer` says it is for Hermes branches; `rules-reviewer` does not exclude them.
  - `AGENTS.md:133-134` and `uc-handoff/SKILL.md:39-40` route Hermes branches to `hermes-reviewer`, which also re-runs every acceptance command.
- **Confidence:** Medium.
- **Action:** `add` one sentence: "For a branch Hermes handed in, use hermes-reviewer instead." Hunk **D6**.

### F13. `census-analyst` has a numeric output ceiling
- **Location:** `.claude/agents/census-analyst.md:23`
- **Evidence:** `a markdown summary under about 500 words, with exact numbers taken from the file.`
- **Pattern:** Group 1f, "Output-shaping choreography": numeric output ceilings. Group 1b covers the same thing as hard word caps.
- **Why obsolete:** A word cap tuned for padding models starves required content. The same file requires:
  - totals per error kind for each of 9+ buildings (`AGENTS.md:92`);
  - every timeout or failed unit;
  - the 5 slowest and 5 largest units with machine load;
  - the flicker split campus-wide and per building.

  A 500-word ceiling forces cuts there. Target: Haiku 4.5.
- **Confidence:** Medium.
- **Action:** `rewrite` as audience framing without the number: tables the owner can scan, exact numbers, a few sentences for the proposal. Hunk **D1**.

### F14. The §3 vertex rule does not name the E5 exception that §4 grants
- **Location:** `AGENTS.md:56-59`; `AGENTS.md:80-83`
- **Evidence:** `Only \`engine/fixes/solidify.py\` may invent vertices; the merge never moves or invents one.` vs `The losing face of a different-look overlap may be cut along the winning face's border. The new points lie only on that border.`
- **Pattern:** Group 2, "Instruction files that contradict each other". Both lines are from one commit, so history cannot order them.
- **Why obsolete:** The spec calls the E5 cut "a named exception to 'only solidify adds points'" (`docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md:34`).
  - `rules-reviewer.md:17` and `uc-repair-rules/SKILL.md:27-29` already carry the exception.
  - `AGENTS.md` §3 does not point to it.
- **Confidence:** Medium.
- **Action:** `flag` (safety rule).
  - If the owner wants §3 to name it, append the exception after the phrase that `tools/tests/test_agents_md.py:8` pins.
  - For example: "Only `engine/fixes/solidify.py` may invent vertices (the E5 cut's border points, §4, are the one exception); …".

### F15. A dated one-time approval sits inside a standing prohibition
- **Location:** `AGENTS.md:41-42`
- **Evidence:** `Rebuilding or restarting them, and any write to the live database \`fixer\`, is the owner's decision. The owner approved the 2026-09-25 rebuild (section 8).`
- **Pattern:** Group 2, "History narratives".
- **Why obsolete:** A past approval inside a standing rule can be read as a standing permission. The rebuild is documented in HANDOFF §8.
- **Confidence:** Low.
- **Action:** `flag` (safety rule): the owner decides whether the sentence moves to HANDOFF §8.

### F16. "Never touch" the export folder, while §2 allows reads through `snapshot.py`
- **Location:** `AGENTS.md:37-38`; `AGENTS.md:24`
- **Evidence:** `**Never touch**: …, the live export folder \`D:\PROJECTS\UC ENVIRONMENT BUILDING\...\`` vs `read only, and only through \`engine/io/snapshot.py\``
- **Pattern:** Group 2, "Instruction files that contradict each other": one rule in two wordings.
- **Why obsolete:** The exception sits in another section. `engine-builder.md:22` and `HERMES.md:53-54` state it next to the rule; `AGENTS.md` §3 does not.
- **Confidence:** Low.
- **Action:** `flag` (safety rule): the owner decides whether §3 names the `snapshot.py` exception.

### F17. `HERMES.md` §3 (project structure) is a 09-24 snapshot
- **Location:** `HERMES.md:112-126`
- **Evidence:** `Tests: pytest engine/tests -q (406+ passing).` and the engine tree.
- **Pattern:** Group 2, "Volatile specifics".
- **Why obsolete:** Nothing in it is contradicted outright, because these are omissions and a lower bound:
  - `engine/tests` now has 605 test functions.
  - The tree omits `engine/campus`, `engine/topo`, `engine/transport`, `detectors/errors.py` and `detectors/folds.py`.
  - It also omits the CLI's `errors`, `preview-data` and `campus-freeze`.
- **Confidence:** Low.
- **Action:** `flag`: a pointer to HANDOFF would stop the drift.

### F18. "Golden unit" in `uc-repair-rules` means a different set than in the spec
- **Location:** `.claude/skills/uc-repair-rules/SKILL.md:43-44`
- **Evidence:** `run the Validator on a golden unit (CHTM 5th floor and the sidewalks) and paste its verdict.`
- **Pattern:** Group 2, "Volatile specifics".
- **Why obsolete:** The spec (`:160`) and the P1-P2 plan (`:47`, `:247`) define the golden units as CHTM 5th plus 3 diverse units from the census.
  - CHTM 5th plus sidewalks A and B is P0 task 16's v0-verdict set (P0 plan `:754-756`).
  - The Validator itself lands with P0-15 and P0-16, both still `ready`.
- **Confidence:** Low.
- **Action:** `flag`: align the term when the census picks the 3 units (P2-R1).

### F19. The one-shot Hermes prompt hard-codes the base branch
- **Location:** `data/hermes_runs/1003-1923-next/prompt.md:6`
- **Evidence:** `3. Work in your own worktree from \`feat/repair-p0\`, test first.`
- **Pattern:** Group 2, "Instruction files that contradict each other". The file is git-ignored, so history cannot order it.
- **Why obsolete:** The run claimed P0-08, a code job (`hermes.out`: `jobs.py done P0-08 --branch hermes/P0-08`), so the line was right for that run.
  The prompt restates `HERMES.md` §0, so it would be wrong for a records-only job (see F8).
- **Confidence:** Low.
- **Action:** `flag`: the record needs no edit. If the next one-shot prompt reuses this text, drop step 3's base and let `HERMES.md` step 3 choose it (D13).

## Outside the audit's scope

### F20. The containers `AGENTS.md` names are defined only in uncommitted files
- **Location:** `AGENTS.md:20`, `AGENTS.md:39-40`; `docker-compose.yml`
- **Evidence:** `containers \`fixer-api\`, \`fixer-web\`, \`fixer-db\`` and `\`fixer-web\` (5190 and 5180, nginx)`. The committed `docker-compose.yml` (HEAD) defines only `db` (`fixer-db`, `127.0.0.1:5490:5432`).
- **Why:** The `api` and `web` services exist only as uncommitted working-tree changes, with untracked `Dockerfile.api`, `Dockerfile.web` and `nginx.conf`.
  The prompt text matches the running system; the gap is that the live container config is not committed.
- **Confidence:** High (fact). **Action:** `flag`, with no edit proposed. The files are uncommitted work that this audit did not create (`AGENTS.md` §3).

### F21. The frontmatter test cannot catch F1
- **Location:** `tools/tests/test_claude_assets.py:16-19`
- **Evidence:** `if ":" in line and not line.startswith(" "):` / `key, value = line.split(":", 1)`
- **Why:** Splitting each line on its first colon accepts frontmatter that YAML rejects, and the test passed `uc-handoff` (16 passed on HEAD).
  A `yaml.safe_load` assertion would catch this class. Whether PyYAML is in the project's venv is unverified.
- **Confidence:** High (fact). **Action:** `flag` (test code, outside the prompt surface).

## Group 4: request config and architecture

- **Claude surface: not applicable.** There is no request-building code: no Anthropic SDK import and no model ID in code. Only the sub-agent roster check applies.
  - There are six agents.
  - `rules-reviewer` and `hermes-reviewer` overlap, but they differ by more than a filter or a payload field.
    `hermes-reviewer` re-runs every acceptance command in a scratch worktree and checks Hermes-only items;
    `rules-reviewer` runs at most one focused test.
  - No merge is proposed; their boundary is F12.
- **Hermes runner (`tools/auto_continue.py`): no finding.**
  - There is one model call per run, and its work is adaptive (finishing a brief).
  - Claims, the worktree, work-in-progress carry-over, the time limit and spend accounting are already code (`usage.json`, daily cap).
  - No token countdown reaches the prompt.

## Checked and kept

- The `AGENTS.md` §3-6 rules and the reasons stated beside them: context, and prohibitions against demonstrated failures (keep-list items 1, 3, 5).
- "Never dispatch sub-agents" in all six agents.
  - Each `tools:` list already lacks the Agent tool, and `test_claude_assets.py:35` pins the phrase.
- `hermes-reviewer.md:8-9`, the history of a defect marked "passed": it is the reason for "Trust only output you produce yourself".
- A review and an acceptance re-run before every merge (`AGENTS.md:133-134`, `uc-handoff:39-41`).
  - This resembles the Claude Opus 5 over-verification pattern.
  - It is in fact the owner's separation of duties (`AGENTS.md:108`), with a demonstrated failure behind it.
- Capitals in routing text (`uc-repair-rules:3` "ANY", `engine-builder:3` "ONE"): allowed by the Group 3 trigger split.
- Rules repeated for Claude and for Hermes that agree: the interpreter, the report path, merge rights, the never-touch lists. This is working redundancy (keep-list item 8).
- Planned paths, not contradictions: `engine/validate/` and `engine/decide/` (`AGENTS.md:19`, `:108`; `uc-prompt-audit:19`).
  - They exist on neither `feat-dashboard` nor `feat/repair-p0`; P0-14..17 are `ready`.
  - `uc-run-unit`'s "Available after" column is accurate today: `campus-freeze` exists, and the other commands are not in `engine/cli.py` yet.
- Facts confirmed against the repository:
  - Commit `cba42a5` exists, and so do the per-session `fixer_test_<pid>_*` databases (`api/tests/db_helper.py:39`).
  - The branches `feat/repair-p0` and `corllenium/p1-ingest` exist.
  - `jobs.py next` exits 3 when nothing is eligible, and prints id, brief, branch (`tools/jobs.py:543`, `:585`).
  - `default_skp_dir()` is `OBJ FIXED RESULT` (`engine/cli.py:366-369`), as `HERMES.md:74-75` says.
  - Ports 5190 / 8190 / 5490 / 5180 match, and so does Vite's `strictPort`.
  - Every other named in-repo path exists.

## Verification

- `yaml.safe_load` over all 10 agent and skill frontmatters: HEAD has 1 error (`uc-handoff`), and the patched copies have 0.
- `git apply --check` on the diff passes against the CRLF working tree, and `git apply --cached --check` passes against the LF index (both exit 0).
  The repository's files were unchanged afterwards.
- `tools/tests/test_agents_md.py`, `test_claude_assets.py` and `test_handover_docs.py` pin prompt text.
  - On copies of HEAD: 16 passed. On the patched copies: 16 passed.
  - No hunk touches `build_prompt`, so the pins in `test_auto_continue.py` are unaffected.
- Grep for every replaced phrase: it appears only at the hunk sites, and at `HANDOFF.md:220`, where "this page" is correct.
- Not run: Step 7 behavioral probes. The hunks are wording and config fixes; the controller re-tests them as `uc-prompt-audit` step 3 says.
