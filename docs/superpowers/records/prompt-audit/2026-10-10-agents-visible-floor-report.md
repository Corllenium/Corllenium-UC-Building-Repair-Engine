# Prompt audit: AGENTS.md §5 "Visible rule" row (commit 8e40db5)

Date 2026-10-10. Proposed diff: `2026-10-10-agents-visible-floor.diff` (same folder). Nothing is applied.
(The dispatch named one file, `2026-10-10-agents-visible-floor.md`; the standing audit rule asks for a report and a
diff, so there are two files with that stem.)

## Step 0: scope and target assumptions

- **Scope.** `AGENTS.md` line 101 (the row changed in 8e40db5), read against `AGENTS.md` §1, §3, §4, §5, §6,
  `.claude/agents/floor-validator.md`, `.claude/skills/uc-validate-floor/SKILL.md`, and (to find files needing a
  pointer) `CLAUDE.md`, `HERMES.md`, the other `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`,
  `docs/superpowers/records/briefs/TEMPLATE.md`, `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md`,
  `engine/validate/` (read for facts only) and the queued brief `task-P2-V2-brief.md`.
  Not read: `.claude/settings*.json`, `.mcp.json`, `.env*`, credentials. `tools/auto_continue.py` and
  `data/hermes_runs/*` are outside this request.
- **Targets.**
  - `AGENTS.md` is read by Claude Code (the model running this audit, Claude Sonnet 5.5) and, completely, by Hermes
    (HERMES.md step 1) on Gemini (`gemini-3.8-flash`). For the Hermes reader only the model-independent groups
    (stale facts, conflicts, architecture) apply.
  - `floor-validator.md` pins `model: sonnet`: audited against Sonnet 5.5. `uc-validate-floor` has no pin: Sonnet 5.5.
- **Owner approval.** The row is the owner's decision of 2026-10-10 (stated in the dispatch). Every proposal below
  keeps its content (4 px, 0.02 in per pixel, every line of sight, both sides) and changes wording, structure or
  pointers only. Hunks that touch §6 or add a reading of the rule are marked and need the owner (AGENTS.md
  intro, §7 item 7).

## Summary

The row's numbers are right (4 × 0.02 × 0.02 = 0.0016 sq in) and it agrees with §1 (both sides drawn), §3 (guards
are not loosened: the floor is a Validator tolerance, and HANDOFF ruling E8-R1 keeps the guard's
`cover_max_exposure` at 0.10) and the Viewpoints row. It has three problems and leaves two decisions open:

1. **The judge never reads it.** `floor-validator` step 1 sends the agent to §6, §2 and §3, and `uc-validate-floor`
   says "The rule is `AGENTS.md` §6". The measure lives in §5. The agent that applies the floor is not pointed at it.
2. **The Validator does not measure it yet.** `engine/validate` has no floor measure (grep for
   `VISIBLE_FLOOR_PX`, `FLOOR_IN_PER_PX`, `face_visible_pixels` finds only the P2-V2 brief and the ledger); P2-V2 is
   claimed and unmerged. Check 3 today is sample-based (`min_per_face` 4, `area_per_sample` 36). A `floor-validator`
   PASS today does not show the floor, and nothing in its prompt says so.
3. **The row is hard to read as written:** two thresholds in one cell ("0 % visible" and "4 pixels"), "show" for a
   covered face, "any Validator viewpoint" with the Viewpoints row two lines below, and "about" for an exact figure.

Counts: Group 1 (dated text) 0. Group 2 (brittle configuration files, stale facts, conflicts) 7 findings (F1-F7, all with
proposed hunks) plus 3 flag items (FL1-FL3). Group 3 not applicable (no tool descriptions in scope). Group 4
not applicable (no request-building or prompt-assembly code in scope; the sub-agent roster is unaffected: no
redundant agents introduced).

## Findings (highest confidence first)

### F1. The judge is not pointed at the measure (High)

- **Location.** `.claude/agents/floor-validator.md:10`, `.claude/skills/uc-validate-floor/SKILL.md:8`; the measure is
  `AGENTS.md:101`.
- **Evidence.** floor-validator: "Read the rules first: `AGENTS.md` §6 (the owner's validation rule) and §2 and §3
  (what is read-only)". Skill: "The rule is `AGENTS.md` §6".
- **Pattern.** Group 2, rule ruled on in one file and not reachable from the file that applies it (a conflict by
  omission: two files load separately, so behaviour depends on which was read).
- **Why.** §6 check 3 says only "nothing visible to the eye was deleted or covered". The number that decides it is in
  §5 and neither the agent nor the skill sends the reader there. Repository-grounded: the three files above.
- **Action.** `rewrite` (hunks 1 and 3 of the diff). The pointer names the §5 row and carries no number, so the
  figure lives in one place (AGENTS.md wins on any disagreement, per its intro).

### F2. Two thresholds in one cell (Medium)

- **Location.** `AGENTS.md:101`.
- **Evidence.** "a rebuilt side may cover only faces that are 0 % visible. **How it is measured (owner, 2026-10-10):**
  no removed or covered face may show more than **4 pixels** ..."
- **Pattern.** Group 2, internal conflict (a reader can take "0 %" and "4 pixels" as two different tests; a 3-pixel
  cover is 0 % visible by neither reading but passes the second).
- **Why.** The owner's words are "the strict visible rule is measured as" the floor, so the floor is the meaning of
  "0 % visible" and "can be seen". The row does not say that.
- **Action.** `rewrite` (hunk 5): split into the original row and a "Visible rule, measured (owner, 2026-10-10)" row
  that ends "\"Cannot be seen\" and \"0 % visible\" in the row above mean at or below this floor". Assumed reading,
  for the owner to confirm. Splitting also gives §6 a row to point at (F3 hunk).

### F3. Counting basis is implicit (Medium)

- **Location.** `AGENTS.md:101`.
- **Evidence.** "no removed or covered face may show more than 4 pixels at 0.02 in per pixel (about 0.0016 sq in) from
  any Validator viewpoint".
- **Pattern.** Group 2 (request criterion: clear and unambiguous for every reader).
- **Why, point by point (each tied to the P2-V2 brief, items 1, 2 and 3):**
  - "show" is wrong for a covered face, which shows nothing afterwards. The count is taken in CHECKPOINT-17 (before),
    where the face is the nearest surface.
  - "from any Validator viewpoint": a Hermes or engine-builder reader does not know the Validator's viewpoints. The
    Viewpoints row is two lines below; name it.
  - Per viewpoint, largest count decides, counts are not added across viewpoints (brief item 2: "more than
    VISIBLE_FLOOR_PX pixels from any viewpoint that sees it"). The row is silent.
  - "0.02 in per pixel" is taken at the face (brief item 1: "pixel size taken at the face" for perspective
    viewpoints); "about 0.0016 sq in" is exact, and is the area across the line of sight, not the face's area.
  - The floor is easy to misread as a builder's budget; builders aim for zero (`uc-repair-rules` item 4 and
    `rules-reviewer` already say "anything visible ... deleted or covered" with no tolerance, which is the right
    direction, so no change to them).
- **Action.** `rewrite` (hunk 5, same row as F2). Includes "it loosens no guard (§3)".

### F4. A PASS today cannot show the floor, and the judge is not told (Medium)

- **Location.** `.claude/agents/floor-validator.md:54-63` (output step); `engine/validate/checks.py:30-60`
  (docstring: check 3 is a sample test); `AGENTS.md:101`.
- **Evidence.** `grep VISIBLE_FLOOR_PX|FLOOR_IN_PER_PX|face_visible_pixels` over `*.py` finds no code; QUEUE.md line 61
  shows P2-V2 claimed. floor-validator's PASS rule is "`validation.json` says `verdict` PASS".
- **Pattern.** Group 2, volatile specifics (a rule stated in the present tense whose enforcement is queued). The
  row says "how it is measured"; until P2-V2 merges, it is how it will be measured.
- **Why.** The Validator's PASS is the owner's gate (§6). A PASS whose check 3 is sample-based would be read as a floor
  pass.
- **Action.** `add` (hunk 2): floor-validator reports whether `validation.json` carries the floor measure, else says
  check 3 was sample-based and the floor was not measured. Land with P2-V2, and name the `validation.json` key P2-V2
  writes in place of the prose. Do not apply earlier than the Validator can say.

### F5. Pixel floor next to two other "4"s (Medium)

- **Location.** `.claude/skills/uc-validate-floor/SKILL.md:54-55` (and `engine/validate/checks.py:288-289`).
- **Evidence.** "the defaults are the owner's values (the signed targets file, 36, 4)".
- **Pattern.** Group 2, ambiguity between two values that share a number (4 samples per face, 36 sq in per sample, and
  the 4-pixel floor).
- **Action.** `rewrite` (hunk 4): name the units and say neither is the pixel floor.

### F6. §6 check 3 does not point at the measure (Medium, owner needed)

- **Location.** `AGENTS.md:119-120`.
- **Action.** `rewrite` (hunk 6): "measured as §5 \"Visible rule, measured\" says". Section 6 changes only with
  the owner's OK; the row itself is approved, this hunk is a pointer and is the owner's to take or leave. Without it,
  F1's pointer is still enough for the judge.

### F7. The design spec restates the rule without the measure (Medium)

- **Location.** `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md:30` (the same "Visible rule" row, "today's cap
  is 10 %"); line 126 describes check 3 as "1,024 or more ray directions".
- **Pattern.** Group 2, duplicate that will drift. The spec is "the authority" (AGENTS.md §2) and was written first.
- **Action.** `rewrite` (hunk 7): add a pointer to the §5 row. Line 126 and the `checks.py` docstring (lines 26-30)
  describe the old check 3; P2-V2 should rewrite them when it lands (not proposed here, the code is its job).

## Agreement with the rest of AGENTS.md and the two files (checked)

- **§1** (Unity draws both sides, `_Cull = 0`): the "both sides" clause is the reason, consistent.
- **§3 guards:** consistent. The floor judges; it changes no guard threshold or invariant. HANDOFF E8-R1 keeps the
  guard at 0.10 and puts "0 % visible" in the Validator.
- **§5 Viewpoints / Back-to-back / Flicker rows:** consistent; "both sides" fits "Where both sides are seen with
  different looks, the owner decides".
- **§6:** consistent in content, no pointer (F6).
- **`uc-repair-rules` item 4, `rules-reviewer`:** zero tolerance wording; stricter than the floor, so no conflict.
- **`HERMES.md`:** copies nothing (line 96 points to AGENTS.md §3-6 "and only there"); no change.
- **`CLAUDE.md`, `briefs/TEMPLATE.md`, `engine-builder`, `unit-runner`, `hermes-reviewer`:** no restatement of the rule.

## Flag items (no edit proposed)

- **FL1. E5, E8 and same-look coplanar copies (owner decision).** The floor counts a removed or covered face's
  pixels in BEFORE. §4's E5 cut removes part of a visible loser, E8 covers whatever shows through a filled hole, and
  removing the inward copy of a back-to-back pair (§5) removes a face a viewer on the other side may see. The row does
  not say whether these are judged by the floor, exempt, or judged by "a surface of the same look is still at that
  place" (what check 3 does today, `checks.py:30-60`; the spec line 126 names E5 sites as the one allowed change). The
  owner should state which, in one sentence, before P2-V2 is judged: otherwise the Validator's first FAIL on a
  back-to-back removal will be read either way.
- **FL2. The P2-V2 brief disagrees with itself.** Item 1 counts pixels where the face is the nearest surface (a total),
  item 6 passes "a removed face whose largest visible patch is 3 px" (a patch). Two 3-px patches total 6.
  Item 3 "measured per covering face with item 1's measure" does not say whether the pixels counted are the face's
  pixels the cover hides or the cover's. Brief-level; for the controller. Not a prompt file.
- **FL3. Heading date (low).** §5 is headed "Owner decisions (2026-10-03)" and now holds a 2026-10-10 row. The row carries
  its date, so nothing misleads; left alone.

## Verification (Step 7, repository checks)

- Row text and commit: `git show 8e40db5 -- AGENTS.md`; arithmetic 4 × 0.02² = 0.0016.
- Paths named in the proposed hunks exist: `.claude/agents/floor-validator.md`,
  `.claude/skills/uc-validate-floor/SKILL.md`, the spec file.
- The proposed diff passes `git apply --check` against the main checkout (it was not applied).
- No behavioural probe applies: these are rule texts, not prompts that steer generated output.
