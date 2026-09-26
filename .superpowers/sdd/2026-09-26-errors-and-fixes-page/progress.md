# SDD ledger — plan: docs/superpowers/plans/2026-09-26-errors-and-fixes-page.md

Spec: docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md (read; binding, with the owner's 11:55 direction below).
Worktree: D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/errors-page, branch feat/errors-page, from 03074c6.

## Pre-flight scan (2026-09-26 11:55)

| Tasks | Shared file / interface | Produces vs consumes | Found |
|---|---|---|---|
| 1 ↔ 3/4 | `/api/docs/images/{name}` | 1 serves it; 3's `imageUrl` builds `/api/docs/images/<encoded>`; 4 renders it | consistent |
| 2 ↔ 5 | `data/errors_doc/img/you-*.{png,webp}`, `owner_images.json`; `check.py` default `web/public/docs/errors.json` | 3's seed path = check's default | consistent |
| 3 ↔ 4 | errorsDoc exports (filterChoices, filterErrors, filterFromQuery, filterToQuery, groupBySection, imageUrl, kindLabel, types) | all defined in 3 | consistent |
| 1 ↔ 3D filter | `api/main.py` include_router | feat/error-filter adds errors_router, this adds docs_router | merge conflict expected (two added lines), resolved at the merge |

| Task | Self-consistency |
|---|---|
| 1 | "names outside the pattern" may pass before the route exists (unknown route = 404) — the plan says so; `x.png%0A` needs `fullmatch` (used) |
| 2 | expected names/words recomputed by hand from the sample log (lines 1, 3, 4; line 6 is a repeat; line 7 not JSON) |
| 3 | validateDoc problem order recomputed against the code's check order — matches the test |
| 4 | template `@click` closures pass `image?: string` — openBox must accept undefined (plan code passes `s2.image` inside v-if; TS does not narrow into closures) — fix in the brief |

## Rulings
- Ruling: content file at web/public/docs/errors.json (nginx try_files would 301/403 a dist/errors/ folder) — see plan.
- Ruling: no mounted view test (no test-utils/DOM env in the project) — pure functions + vue-tsc + build + browser check.
- Ruling (owner 11:55, "every error has its own document description ... why ... Minecraft Little Tiles ... floating window ... hidden faces ... what is the solution ... more detailed ... planning, not fixing"): Tasks 1-2 stand (image route, screenshot extraction); Tasks 3-5 are re-planned around a catalogue of error kinds, each with a detailed floating-window description (what, why from the Little Tiles export, what it does in Unity, where and how many, the solution plan, what was tried, why some remain); nothing is fixed in any model — costs a re-plan of Tasks 3-5.

## Progress
- Tasks 1+2: dispatched together (implementer haiku, BASE 03074c6)
- Tasks 1+2: implementer DONE 013aa91 (Task 1), c10721f (Task 2); 12 passed per report; review dispatched (sonnet)
- Owner answers 12:10: depth of the "Hidden inside faces" draft approved for every kind; the floating window opens from the Errors page cards (not the 3D legend); kinds = the 10 listed + engine mistakes.
- Tasks 1+2: review — spec ✅, Approved (path safety, extraction rules, dedupe checked; tools 39 passed, docs+health 7 passed).
- Tasks 1+2: Important (brief-inherited): the tool_result skip in extract_owner_images is unreachable in the tests (the fixture's tool_result line has no origin, so the origin check rejects it first) — fix round adds a human-origin + tool_result fixture.
- Tasks 1+2: minor (deferred): a valid-JSON non-dict line is guarded but untested.
- Ruling: check.py must read the catalogue schema (kinds[].examples, engine_mistakes[].examples, other_screenshots) — the re-plan changed the schema and did not carry check.py along (controller's miss, found by running it: 29 of 32 screenshots reported unused although all 32 are placed) — one fix round with the finding above — costs a small commit.
- Task 8: implementer DONE_WITH_CONCERNS eadef68 (10/10; resolveJsonModule already on); concern: vue-tsc -b fails on 3 PRE-EXISTING errors in web/src/three/Viewport.ts (lines 332, 333, 360; present at c10721f = feat-dashboard 03074c6).
- Ruling: the type-check gate for this plan is "no new vue-tsc errors beyond those 3" — they are on feat-dashboard already, `vite build` does not type-check so the live image builds, and the 3D filter's Task 9 edits Viewport.ts where they belong — costs nothing if wrong beyond a later cleanup.
- Task 11 (content): full catalogue committed (10 kinds, 10 engine mistakes, all 32 owner screenshots placed; content test 10/10). Screenshots extracted to data/errors_doc (32; zip data/backups/errors_doc-2026-09-26.zip).
- Tasks 1+2: fix round 1/5 (2 addressed: check.py reads kinds/engine_mistakes/other_screenshots; human-origin tool_result fixture proven to fail without the skip; commit 7783e61; tools 40 passed; real check 0 missing, 0 unused); re-review dispatched (haiku)
- Task 9: dispatched (implementer haiku, BASE 7783e61)
- Tasks 1+2: re-review — all findings addressed (40 passed; check 0 missing, 0 unused); complete (commits 03074c6..013aa91..c10721f + fix 7783e61, review clean)
- Task 9: implementer DONE bc8fa17 (docs+health 11 passed); review dispatched (sonnet)
- Task 8: review — spec ✅, Approved (test file and seed byte-identical to the brief; validateCatalogue order hand-traced; content test passes on the full catalogue; vue-tsc: only the 3 pre-existing Viewport.ts errors).
- Task 8: minor (deferred): engineStem's `?? file` fallback is unreachable; filterFromQuery recomputes filterChoices per call (tens of items; harmless).
- Task 8: complete (commits c10721f..eadef68, review clean)
- Task 10: dispatched (implementer sonnet, BASE bc8fa17)
- Task 9: review — spec ✅, Approved (verbatim to the brief; ids never reach the filesystem; tempfile + os.replace under the lock; missing verdict key → 422; tests independent).
- Task 9: minor (deferred): a hand-corrupted validation.json gives GET/PUT 500 (invalid JSON) or GET 200 with a wrong shape; the only writer is the app's atomic path.
- Task 9: minor (deferred): the lock is process-local; correct for the single-process uvicorn in Dockerfile.api, undocumented.
- Task 9: complete (commits 7783e61..bc8fa17, review clean)
- Task 10: implementer stalled (stream watchdog, 600 s, while reading; nothing written); resumed by message to write each file in parts, commands in the foreground
- Task 10: implementer DONE 2b63a26 (resumed after the stall; ErrorsView 734 lines, ErrorWindow 480; vue-tsc only the 3 known Viewport.ts errors; vitest 57/57; build OK). Concerns: defineExpose(setSaveError) bridges the save-error row; mistakes use a neutral swatch; engine select shows full paths; lightbox Esc precedence via stopImmediatePropagation; ModelsView header buttons may need a gap.
- Ruling: deploy 2b63a26 before its review finishes — the owner asked to see the page; the old images are tagged :pre-20260926 and the DB backed up (data/backups/fixer-20260926-1246.dump), so a rollback is one command; a review fix means one more web-only rebuild — costs a rebuild if the review finds something.
- Deployed 12:48 (HANDOFF section 8 from dk at 2b63a26): alembic ran no migration; /errors 200 (and with ?open=), /docs/errors.json 60,648 B (10 kinds, 10 mistakes), /api/docs/validation 200 empty, images 200 (png, webp), traversal 404, /api/health and /api/models 200.
- Task 10: review dispatched (sonnet)
- Browser check (12:50, live 5190): page renders (Validated 0 of 30; 3 model cards; 10 of 10 kinds); the Hidden inside faces window has all 13 headings in order and 8/8 screenshots loaded; verdict set then cleared through the UI round-trips to data/errors_doc/validation.json (back to empty); lightbox opens; one Esc closes only the lightbox, a second closes the window; filters: engine=solidify 2 of 10 kinds + 6 mistakes, +model A still 2, Clear 10 of 10; URL follows every change. Screenshots (headless Edge) sent to the owner.
- Finding (browser check): horizontal page overflow below ~1100 px: long unbreakable names/paths in the model cards (.model-card h3, .model-source) overflow their card (scrollWidth 1109 vs 1009). Fix in Task 10's fix round: overflow-wrap: anywhere on the card texts.
- Task 10: review — spec ✅, Needs fixes. Important: the setSaveError bridge is instance-keyed; a late failure after a window switch shows "Not saved" in the wrong window (state itself never corrupted). Minors: ready guard is a no-op (one extra router.replace); no pointercancel; .header-actions has no CSS (gap from a whitespace node); verdictOf x3 per row; status-badge CSS duplicated in two files. All 5 implementer concerns agreed. Gates re-run: vue-tsc only the 3 known Viewport.ts errors; vitest 57/57.
- Task 10: fix round 1/5 dispatched (resumed implementer): the Important + pointercancel + .header-actions gap + card overflow-wrap (browser finding); the ready guard, triple verdictOf and duplicated CSS left as minors (deferred).
- Task 10: fix round 1 done 3ac8331 (setSaveError guarded by openId; pointercancel; .header-actions gap; min-width:0 + overflow-wrap:anywhere; gates: vue-tsc 3 known only, vitest 57/57, build OK); re-review dispatched (haiku)
- Redeployed web 13:10 from 3ac8331 (API unchanged since 2b63a26). Live check: at a 1024-px window scrollWidth 1009 = clientWidth 1009 (overflow gone; long names wrap in their cards); Models header .header-actions display flex, gap 8px, 'Errors & fixes' links to /errors.
- Task 10: re-review — all 4 findings addressed (vue-tsc 3 known only; vitest 57/57); complete (commits bc8fa17..2b63a26 + fix 3ac8331, review clean)
- Final review (opus): Ready after fixes. Important 1: ✕ does not close the window (pointer capture on the title bar steals the click; reproduced in Chrome). Important 2: notes can be lost (textarea bound to the saved note; failed save wipes it; blur-save + verdict-click race sends note ""; verdicts that failed to load look empty). Minors: validator gaps (title, sources, numbers, API id rules); missing/invalid errors.json message; image placeholder; check.py traceback when inputs missing; save failure after the window closed is dropped; raw 422 JSON; validation.json not in any backup; hidden-faces status inconsistent (Fixed with 66/27 left) and 1,853 vs 2,065 unexplained; empty engine-mistakes heading; UTC times; docstrings; HANDOFF names 2b63a26 though web runs 3ac8331. Merge into feat-dashboard is clean; feat/error-filter will conflict in api/main.py (keep both routers).
- Content fix (controller) b7f843d: one status rule (leftovers in a shipped file = Partly fixed: hidden A/B, double layers B) and the 1,853 vs 2,065 gap explained (rebuild encloses 239 more on A, 232 on B).
- Final fix dispatch (ONE, sonnet, fresh): items 1-12 of final-fix-brief.md (A web window/notes, B API keeps the note, C validator + load checks, D placeholders/check.py/empty filter/local times). Records items (validation.json backup, HANDOFF image commit) done by the controller.
