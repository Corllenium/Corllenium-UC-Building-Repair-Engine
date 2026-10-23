# UC MODEL FIXER — session record (2026-09-21 to 2026-09-24)

The durable record of what was built, why, what was measured, and what is still open. Written for
the owner and for any session that picks this up. Every number below was measured on the files, not
estimated. The working ledgers (every ruling, in order) are committed next to the reports under
`.superpowers/sdd/`; this page is the summary and the map.

## 1. The goal, in the owner's words (condensed)

- Clean the SketchUp OBJ exports of the CHTM sidewalk for Unity. Test files: `CHTM_SIDE_WALK_2nd_floor.obj`
  (file A) and `CHTM_2nd_to_3rd_building_sidewalk_outside.obj` (file B).
- **Remove, not hide**, everything that does not contribute to the outside: hidden inside faces,
  gridlines (triangle edges on flat surfaces), stacked duplicate layers ("texture hits texture"),
  stray fragments.
- **Do not delete the side meshes, only the inside. Build the side meshes where they are broken or
  missing.** The result is a clean solid slab.
- **Region outlines only on the edge line of the model**, never inside a slab. Toggling triangle
  edges or X-ray must show nothing extra.
- After every run, the latest `.skp` of each model in `OBJ FIXED RESULT/` to check in SketchUp 2026.
- Work visually: every round includes renders and a fix for what is seen, not only numbers.
- Dashboard on its own ports: web 5190, API 8190, PostgreSQL 5490.

## 2. Where everything is

| What | Where |
|---|---|
| Design spec (binding, with amendments) | `docs/superpowers/specs/2026-09-21-uc-model-fixer-design.md` |
| Plans | `docs/superpowers/plans/` |
| Ledgers (every ruling, measurement, dispatch, in order) | `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/progress.md`, `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/progress.md` |
| Round reports (with `## Public signatures`) | `.superpowers/sdd/2026-09-21-phase2e-fix-pipeline/*-report.md` |
| Engine | `engine/` (entry point `python -m engine.cli fix <snapshot> --out data/output`) |
| Frozen input copies | `data/snapshots/ce26e0392ab0` (A), `data/snapshots/0b290ec0bcb4` (B) |
| Run outputs | `data/output/<name>/`: `.fixed.obj` (Unity), `.fixed.ngon.obj`, `report.json`, `qa/` (21 renders), `.fixed.skp` |
| Owner's SketchUp files | `OBJ FIXED RESULT/<name>.fixed.skp` (overwritten by every run) |
| Preview page | `preview/index.html`, served at http://127.0.0.1:5180 |
| Dashboard | web http://localhost:5190, API http://127.0.0.1:8190, PostgreSQL 127.0.0.1:5490 |
| Diagnostic scripts used in this session | `docs/superpowers/records/scripts/` (see section 8) |

## 3. Which engine file handles which error

`engine/fixes/pipeline.py::fix_object` runs every step in this order: load and weld, **solidify**,
**exposure**, **hidden-face removal**, **fragments**, **orientation**, **duplicate layers**,
topology again, **merge**, **final guard** (rolled back if it fails), invariants, outputs.
`engine/cli.py` writes the files.

| What you see | Detected by | Fixed by | Safety check | Status |
|---|---|---|---|---|
| Hidden inside faces (only visible with X-ray) | `engine/vis/exposure.py`: `compute_exposure`, `compute_side_exposure`, `classify_exposure` (128 ray directions x 4 samples per face) | `engine/fixes/remove.py::remove_faces`, called from `fix_object` | `engine/guard/compare.py::guard_feedback` (strict: a face whose removal changes any pixel is restored) | Working. A: 1,985 removed; B: 2,584. **Limit:** a face visible through an opening or slit in a broken side is kept. |
| Missing or broken slab sides and bottoms | `engine/fixes/solidify.py::top_regions`, `_is_underside` (top or underside decided by looking below and above) | `engine/fixes/solidify.py::solidify`: walls along missing OR broken outline edges at each edge's own height (sloped tops follow the ground), broken side pieces inside a band replaced (a piece must belong to the slab; the wall keeps the side's material), one bottom per footprint at the slab's own depth, interior covered | `engine/guard/compare.py::solidify_feedback` (cap guard): a slab's new shell judged together; back-side covers measured by the covered side's original exposure; a new face never left on a piece given back or on an existing face; named allowed changes: replaced pieces, interior inside the volume, and rule 6 (a face outside every slab seen only through a slab now closed) | Working (brief 10, 01cc420..f7e27d1): A 917 / B 506 triangles, back faces from outside A 21,553 / B 2,787 px. Open: A's margin strip (thin sheet wound backwards), A's lower-landing stepped bottom border, B region 107 partly rebuilt, B4/B8; a general rebuild of broken undersides (brief 11). |
| Gridlines, triangle edges on flat surfaces | `engine/topo/planes.py`: `cluster_planes`, `build_regions`, `cluster_uv`; `engine/topo/edges.py::classify_edges` (class 1 = removable gridline) | `engine/fixes/merge.py::merge_regions` (per flat region: union, then constrained triangulation over existing vertices only; border vertices within 0.15 in of a straight line dropped) | Final guard in `fix_object` (`compare_views` against the solidified reference; border shifts up to 0.15 in are measured and tolerated) | Working. A: 177 regions merged; B: 90. One region per file skipped, being fixed now (section 6). |
| Texture on texture (z-fighting, stacked duplicate layers) | `engine/fixes/overlap.py`: `find_overlaps`, `covered_fractions` | `engine/fixes/overlap.py`: `plan_overlap_removal`, `remove_overlaps` | Strict guard | Same material: working (A 49, B 23 removed). Different materials: reported only (B had 39 such pairs at b2134e9); the owner's "which face wins" preference step is not built. |
| Reversed faces (purple back side in SketchUp) | `engine/fixes/orient.py::classify_orientation` (flip when the back is more exposed than the front; "thin sheet" when both sides are) | `engine/fixes/orient.py::flip_faces` | Guard | Working for clear cases (A 780 flipped). **Limit:** thin sheets (A 79, B 16) are not flipped, and faces on open or broken sides count as thin sheets. Closing the sides fixes this. |
| Stray fragments, slivers and folds | `engine/detectors/fragments.py::detect_fragments` (components joined through T-junctions; a sliver only on an open border), `engine/detectors/folds.py::detect_folds` | the fragment pass in `fix_object`; faces solidify invented, side-rebuild walls included, are protected | `engine/guard/piece_rays.py` (no line through a removed piece may reach a side never exposed), then `engine/guard/compare.py::fragment_feedback` (a candidate's pixels may show only the sky or an exposed side; per-view cap) | Working (briefs 07-09). At ca463c2: A 2 slivers + 26 fold members removed, B 1 sliver + 6 fold members; every one confirmed by the rays. |
| Zero-area faces | `engine/topo/adjacency.py::degenerate_mask` | removal in `fix_object` | Strict guard | Working. |
| T-junction lines (a line across a flat surface; cracks and sparkle in Unity) | `engine/topo/adjacency.py`: `find_t_vertices`, `t_junction_sub_edges` | `engine/fixes/merge.py` threads every existing vertex lying on an output edge into that edge (merged rings, or a fan split of a copied triangle); nothing moved or invented | Final guard (unchanged totals) | Working (28d63df): T-vertices A 353 -> 0, B 363 -> 0. Lines left are double layers, not T-junctions. |
| Lines inside flat surfaces in the `.skp` | measured on SketchUp's own model after writing | `engine/io/skp_writer.py::write_skp` (softens class 1 and 5 edges and, decided on SketchUp's own model, every edge between two coplanar same-material faces and every one-face edge lying wholly on one) | `read_skp` / `read_skp_summary` read-back | Working (bcccca2). Left: A 9, B 27 lines, of which B's 15 are material seams and the rest double layers. |
| "Did anything visible change?" (safety net for all of the above) | `engine/guard/views.py::ortho_first_hit` (26 views), `engine/rays/caster.py` | n/a | `engine/guard/compare.py`: `classify_pixels`, `compare_views`. Pixel classes: hole, material changed, moved, edge flicker, z-fight tie, crack closed, fragment removed, border shift | Working. |
| Visual check of every run | n/a | `engine/guard/qa_render.py::write_qa_sheet` (21 renders into `data/output/<name>/qa/`) | n/a | Working. |
| The SketchUp file | n/a | `engine/io/skp_writer.py::write_skp` (one face per merged region with inner loops for openings, materials with textures on both sides) | `read_skp_summary`, `check_skp_validity` | Working; files in `OBJ FIXED RESULT/`. |

## 4. History: rounds, commits, measured results

2026-10-17, Codex, STAGING-T123-V1: added exact copies of two staging tests missing from main; the requested five files match siege-jev-gate byte-for-byte. Requested pytest modules: main 81 passed, worktree 81 passed. Read-only receipt/Blender checks: all 12 floors/signatures match, buildings file self-contained with restored ARCHI ceiling present, current linked CHTM LOD0 99,310 triangles. Receipt and three `.blend` files unchanged. Both runners compile/import; third/fourth runner lacks `--stages` CLI and remains unedited under the foreign-untracked rule. [Full evidence and limitations](STAGING-T123-V1-report.md).

Triangles out of the fixed file (input: A 4,692, B 7,227). "Passed" = every invariant true and the
final guard passed.

| When | Round | Commits | A | B |
|---|---|---|---|---|
| 09-21 | Phase 0 spike, Phase 1A foundations, Phase 2E tasks 1-9 (rays, exposure, guard, removal, merge kernel, pipeline, CLI, preview) | 819bb32 ... | | |
| 09-23 | Engine round, guard round (ties, cracks, flicker ring, reports) | ... a29688e | 1,891 | 1,278 |
| 09-23 | Merge quality (one slab one face) | 0eec601 ... 0d464e0 | 1,674 | 1,173 |
| 09-23 | Overlap removal + solidify | f0bea77 ... b2134e9 | 1,600 | 1,113 |
| 09-23/24 | Solidify fixes (original-exposure cover rule, local wall heights, shallowest bottoms, refused partial bottoms, cap guard invariant) + fragments + QA sheet | a528705 ... c0bbc98 | 1,590 | 1,128 |
| 09-24 03:30 | Peer fixes merged: rule 9 per pass (d505241), union slivers close (dee358d), asset-aware snapshot identity (F5) | 17939a4, ee840e9, e57462d | 2,579 (merge rolled back) | 602 |
| 09-24 04:10 | The merge guard measures border shifts instead of counting pixels | 022a67b | **1,117** | **602** |
| 09-24 08:50 | SketchUp export: `.skp` per run into `OBJ FIXED RESULT/` | e97443e, d24da30, merge 8ffbda3 | .skp 731 faces | .skp 248 faces |
| 09-24 09:25 | Merge: T-junction sliver rings closed at the source, a union corner no vertex explains sets aside only its triangles (N1, N2) | d6ef1a9, b3b9ad3 | **902** (0 regions skipped, 87 copied) | **555** |
| 09-24 14:15 | SketchUp writer hides every line inside a flat same-material surface (S1) | bcccca2, merge 8ee9e4d | .skp lines inside surfaces 14 | 32 |
| 09-24 18:50 | Merge threads T-junction vertices into the edges they lie on (T1): T-vertices A 353 -> 0, B 363 -> 0 | 28d63df, 03df53d | **1,013** | **601** |
| 09-24 22:09 | Review part 1 fixes (brief 07): fragments joined through T-junctions and their own pixels judged, failed run writes `.FAILED.skp`, growth over background fails (PX_GROWN), bbox invariant on used vertices | merge 19f97cc | 1,019 | 593 |
| 09-25 05:50 | Review 2a fixes (brief 08): a sliver only on an open border, invented faces never debris, bbox within the border tolerance, guard images know the new classes, fragment cap from the real files | 536fca7 ... d570927 | 1,033 | 596 |
| 09-25 07:30 | Side rebuild SR0-SR6, on its own branch: walls along missing or broken sides, broken pieces replaced; back faces A 20,793, B 6,006; owner's ramp close-up 948 back px (input 43,696) | ff4a0ec ... 8d238c4 (feat/side-rebuild) | 876 | 486 |
| 09-25 08:00 | Debris confirmed by rays through each piece; folds resolved (brief 09) | 3386c4f, 62bee9d | 1,031 | 600 |
| 09-25 08:52 | Side rebuild merged into feat-dashboard (brief 03): back faces A 20,945, B 5,993; ramp close-up in the written `.skp` 948 back px; no rollback | 68f6d15, a89f771, 82adc60, ca463c2 | **1,044** | **530** |
| 09-25 17:12 | Side rebuild follow-ups + review part 2 (brief 10): joint shell judgement, thickness from the files, top/underside by looking below and above (it was deleting 19,777 sq in of A's region 33), no new face on a given-back piece, pieces belong to the slab, lower surface only where own sides end | 9f64ae9..f7e27d1 | **917** | **506** |
| 09-25 21:10 | Automatic continuation: `tools/auto_continue.py` hands the running brief job to Hermes on its own branch when a transcript shows Claude's usage limit (34 tests, fake Hermes; one real Hermes smoke call). The owner ran `stop` at 21:18 | ce3a931, 06efe3c | — | — |
| 09-25 21:20 | Dashboard fix wave merged (Hermes passes 1-4, three read-only reviews; round 3 approved with 6 minor follow-ups, now brief 12); API 39, web 46; engine unchanged | cba42a5 | — | — |
| 09-25 21:50 | Brief 11 items 2 and R10-C1: a bottom covers the whole footprint; a real underside is the bottom of the body above it, fascia or no sky (agent's real runs, before review) | 0a81860, 281a569 | 884 | 510 |
| 09-25 21:55 | Owner's decisions carried out: live DB backed up, 6 backslash rows rewritten, dashboard rebuilt from 281a569 (nginx timeout 600 s, live DB migrated to 0002), live model loads in the container; brief 13 (one copy of stacked opposite-wound same-material surfaces) started | — | — | — |
| 09-25 23:45 | Brief 11 finished (DONE_WITH_CONCERNS, 15 commits): margin-strip winding, one bottom per footprint, the review-of-brief-10 findings C1, I1-I3, M1, M3-M6 (M2 pinned xfail); items 3-4 traced, every change measured worse; A1 purple strips and A2 stepped lines gone; 607 passed + 1 xfailed | 4019987 .. ab22ff3 | **881** | **513** |
| 09-26 00:10 | Session closed by the owner. Brief 15 item 1 committed (`double_layers` in every report); item 2 (one wall per side plane) parked unverified on `wip/brief15-one-wall`; runner and auto-resume stopped; owner files from ab22ff3 | 3c54e77 (1795d38 on its branch) | 881 | 513 |
| 09-26 11:40 | 3D error filter (spec 7f4cb1a, plan f4fac78 + 1d945d2), subagent-driven on `feat/error-filter` in `.claude/worktrees/error-filter`. Tasks 1-5 complete and reviewed: `pair_list`; `find_errors` (7 kinds); flicker search 17.6x faster (slice 342.4 s to 19.5 s, same 6,376 pairs); `engine.cli errors` (CHTM 5th floor raw: hidden 12,870, flicker 5,668 + 4,793 faces, cracks 3,884, 40.8 s); `POST`/`GET /api/versions/{id}/errors`. Owner added real textures (Task 13) and a facade layer (Task 14). Task 6 running | 0fde3ca .. 4a998da on its branch | — | — |
| 09-26 12:55 | Errors page live at /errors (owner: "where is the documentation page"): a planning catalogue of 10 error kinds and 10 engine mistakes, each in a floating window with the Little Tiles cause, the exact test, measured counts per model, the solution and what remains; the owner's verdict per kind and model saved to data/errors_doc/validation.json; all 32 owner screenshots placed. 3D error filter paused after its Task 6 (approved) | 013aa91 .. 2b63a26 on feat/errors-page (deployed, not merged) | — | — |
| 09-26 13:55 | Errors page merged into feat-dashboard after its final review | dee9801 | — | — |
| 09-26 14:54 | Layer (i) windows: an (i) beside each error layer in the workspace opens that error's window, with a verdict for the open model (owner: "if I click gridlines ... a window where I can see the details") | 63ce3c5, 4776e3d, merge 277a722 | — | — |
| 09-26 16:35 | 3D error filter deployed without textures (Tasks 1-10, 12, 14, 15): Errors column, flicker first, isolate, blink, fly-to, click shows the faces a face fights, facade layer, open edges = truly open, meshbuf cache (CHTM opens in ~4 s) | 997e71d on feat/error-filter | — | — |
| 09-26 20:55 | Real textures in the 3D viewer (Task 13, toggle U), deployed; feat-dashboard (217 commits) and feat/error-filter pushed to GitHub (private) | ae905ac | — | — |
| 09-26 22:31 | Machine rebooted: the dashboard containers (restart policy "no") stopped until `docker start` at ~23:00; the fix-round agent was stopped mid-work and resumed by message | — | — | — |
| 09-26 23:27 | Final whole-branch review (0 Critical, 4 Important, 11 Minor) fixed in one round: toggles no longer walk both errors files, crack dots and open edges no longer show through walls (49,157 -> 12,724 px at the overview), Isolate/X-ray clicks pick the error face, stray fragments and slivers in "Zero-area and stray bits" (CHTM: 0), versioned errors files; merged and deployed; engine 633 + 1 xfailed, API 61, web 107 | 6eba359 .. 6015f26, merge 0bfd433 | — | — |
| 10-02 | `MODEL FIXER ENGINE FILES` organised into 01-05 (437 files moved, size + MD5 checked) | — (git-ignored) | — | — |
| 10-03 | **UC Repair Engine** program: the spec (owner decisions, validation rule, decision hooks + Jev) and the P0 and P1-P2 plans; `AGENTS.md` as the one rules source; the job queue `tools/jobs.py`; `HERMES.md` entry; skills and sub-agents; the CHECKPOINT-17 source freeze (P0-07: 85 splits, 1,766,906 tris); Hermes's first job H1 (VPS inventory) reviewed and merged; prompt audit #1 (21 findings) applied with the owner's OK | 2a748d4 .. 40a69ae | — | — |
| 10-03 late | Owner order: every floor's error map first (kept as the engines' record, a fix plan per unit), one engine flow per floor run as an n8n workflow | f53f3e9 | — | — |
| 10-04 | P0-08 (face group-path index, Hermes, 2 reviews) and P0-09 (material look keys, Hermes, 2 reviews; follow-up P0-09b queued) merged into feat/repair-p0; P0-11 (SDK cross-check: 63 match, 18 area-only mismatches, export lacks 90,391 tris vs the backup) in fix round 1; speed jobs S1 (T-junction search) and S3 (double_layers) queued for Hermes with Claude's committed tests (21 and 19) and running; P0-10 inventory dispatched | 5674331, 478326b, 7ff3a4c, 2b9b0a4 | — | — |

Every commit since b2134e9, oldest last: `git log --first-parent b2134e9..HEAD`.

Why file A rolled back at 03:30 and how it was fixed: the merge made 1,117 triangles, but the final
guard failed on 14 "edge flicker" pixels in one of 26 views against a cap of 11. Every one of the
59 flagged pixels was measured: surface borders moved by at most 0.062 in (the merge may move a
border by 0.15 in), no surface missing. A pixel count cannot tell a 0.013 in shift along an edge that
lies on pixel centres from real damage, so the guard now measures the displacement instead
(022a67b); anything farther than 0.15 in still fails.

### 2026-10-08: owner decisions, Validator proof, colour-coded error export
- **P0-13 merged:** the owner's answers; the signed check-2 targets; campus map of 80 units, 78 confirmed.
- **P0-16 merged:** 7 mutation rows, each caught; real verdicts all FAIL; the floor-validator agent.
- **P0-18 merged and published:** `04-COLORING`, 10 files built from 83b89a8.
  - Each face is drawn once, in the first kind that lists it.
  - Read-back equals written minus the exact duplicate triangles, with residuals of at most 23 faces per file
    (unexplained, listed in each report).
- **Full suite on the merged branch:** 1273 passed, 1 xfailed.
- **The Jev + mods plan** was handed to a second controller session.

### 2026-10-08: Jev + Claude Code mods (second controller session)
- **M1 `uc-guard` merged** (c22c952): it denies tool calls that break AGENTS.md. rules-reviewer needed 3 fix rounds;
  the first review found a `docker compose -p ... up` bypass (HANDOFF.md:351). 27 tests.
- **P0-17:** the Jev wrapper is approved and in a minor-fix round. The real pilot waits for the key.
- **M2 `uc-status`:** built and tested; the screenshot check is next.

### 2026-10-08 night: Jev on the VPS (second controller session)
- **Merged:** `feat/jev-vps` → `feat-dashboard` (e2a37ee). Eight tasks went through 13 fix rounds in all.
- **Defects the reviews caught:**
  - Choice option order lost, both in the cache key and in jsonb storage;
  - owner answers shadowed by cached Jev answers;
  - loose answer types;
  - nginx crashing when the decide container is absent;
  - a root container;
  - the `uc-engine` login reaching the whole dashboard;
  - a phone layout with the row buttons off-screen (found in the browser check).
- **Jev stays off** until the repair engine is ready. The deploy waits for the owner's OK.

### 2026-10-08 evening: P0 closed
- **Final review and fixes:** the end-of-P0 review found the branch ready to merge. The fix round covered the
  flicker labels (MATERIAL, not LOOK), refused unknown target kinds, removed the machine path, and guarded the
  double_layers chunk sizes.
- **Prompt audit** of the briefs applied.
- **Phase merge** 8163bb0. Suites 1320 passed, 1 xfailed.
- **Colour export** republished from 8163bb0.
- **Follow-ups** are queued as P1-H1.

### 2026-10-09: P1 closed
- **The kernel:** K1, K1b, K2, K3, K3b.
- **The Decider:** D1, plus D2 from the Jev session.
- **Hardening and speed:** H1, H1b, S2.
- **Final review:** READY TO MERGE. Phase merge c88ac1c; suites 1811 passed.
- **First per-stage Validator verdicts** on CHTM 5th recorded.
- **A process-kill incident** recorded.

### 2026-10-09: uc-guard rule 7 (M1c) merged
- **Owner OK** after the 10:21 `taskkill /IM python.exe` incident. Merge ba11fb5 into feat-dashboard.
- **Rule 7:** kill only by PID. Killing by name or by filter is denied, in Bash, PowerShell, and when nested.
- **Review:** rules-reviewer, 2 fix rounds, then APPROVED; plugin test 37/37.
- **Parked Minor:** `foreach ($p in Get-Process name) { ... }` is not seen.

### 2026-10-09: P2-K0 merged, E8a started
- **P2-K0** (kernel prep): review Spec PASS; one fix round (the legacy marker could be bypassed) re-reviewed APPROVED.
- **Byte-identical** on sidewalks A and B; merged into `feat/repair-p1p2` as b43d27f.
- **E8a brief** (strict solidify engine) with ruling E8-R1; implementer dispatched.

### 2026-10-09: P2-E8a merged, E8b started
- **E8a** (strict solidify engine): review APPROVED, one fix round re-reviewed APPROVED; merged as 76ca35a.
- **Real runs:** covered after rollback 0 on sidewalks A, B and CHTM 5th.
- **Controller correction:** the flagged swB site 90 view change was not a Validator miss; the camera stood inside a
  closed pocket.
- **E8b brief** (narrow flat fill, Validator class `fill_site`); implementer dispatched.

### 2026-10-09: P2-E8b merged, E8c started
- **E8b** (narrow flat fill): the measurement found 0 closed loops before E6 (271 of 393 chain ends on CHTM 5th
  are T-junctions); ruling R9 kept the rule.
- **Review:** APPROVED, with one fix round: rulings R10 and R11, and the Validator's independent re-measurement.
- **Merged** as ed278b7.
- **E8c brief and dispatch.**

### 2026-10-09: P2-E8c merged; E8 complete
- **The needs-modelling queue and its read-only SketchUp helper.**
- **Review:** CHANGES (the HtmlDialog links; a bypassable static scan). Fix round re-reviewed APPROVED.
- **Merged** as 9cae2d2.

### 2026-10-10 / 11: E3 merged; the Validator to the owner's floor; the Unity pipeline started
- **E3** merged (7258652). **P2-V2** (the Validator's floor measure, horizon rule, corner fix) merged (0795710) after
  one fix round; the owner set the floor (4 px at 0.02 in/px) and the horizon rule in chat.
- **Unity floor pipeline:** spec and Part 1 plan approved; U1-B merged; U1-A with Hermes.
- **Hermes started** on the queue (U1-A, P2-H2).

## 5. Measured state of the SketchUp files

Audit of every edge SketchUp draws, read back through the C API (`scripts/skp_edge_audit.py`).
First at 8ffbda3 (08:53), then after the merge fix (b3b9ad3, files written 09:29):

| | A at 8ffbda3 | A at b3b9ad3 | B at 8ffbda3 | B at b3b9ad3 |
|---|---|---|---|---|
| Faces / edges | 731 / 1,618 | 517 / 1,248 | 248 / 734 | 220 / 680 |
| Hidden (soft) edges | 560 | 268 | 143 | 102 |
| Visible lines inside a flat same-material surface | 21 | 21 | 5 | 5 |
| Visible T-junction lines lying on a flat surface | 100 (longest 551 in) | 50 | 36 | 36 |
| Real outer borders | 214 | 220 | 200 | 203 |
| Lines where a wall meets a surface | 328 | 339 | 150 | 151 |
| Shape edges above 5 degrees | 330 | 301 | 158 | 143 |
| Material borders | 0 | 0 | 12 | 12 |

At ca463c2, after the side rebuild was merged (brief 03; files written 08:50 B, 08:52 A), the same
audit. The before columns are feat-dashboard's owner files of 08:00/08:01, audited the same way.

| | A before (3d30327) | A at ca463c2 | B before (3d30327) | B at ca463c2 |
|---|---|---|---|---|
| Faces / edges | 588 / 1,321 | 622 / 1,397 | 254 / 690 | 211 / 571 |
| Hidden (soft) edges | 397 | 426 | 149 | 146 |
| Visible lines inside a flat same-material surface | 8 (48.8 ft) | 17 (20.3 ft) | 2 (1.6 ft) | 0 |
| Visible T-junction lines lying on a flat surface | 3 (54.9 ft) | 3 (12.3 ft) | 20 (47.2 ft) | 20 (42.3 ft) |
| Real outer borders | 232 | 380 | 200 | 126 |
| Lines where a wall meets a surface | 251 | 181 | 91 | 63 |
| Shape edges above 5 degrees | 354 | 311 | 165 | 171 |
| Material borders | 0 | 0 | 12 | 14 |
| Non-manifold edges (3+ faces) | 76 | 79 | 51 | 31 |

## 6. Open problems (owner screenshots, 2026-09-24)

1. ~~Broken sides are kept, not rebuilt.~~ **Rebuilt: the side rebuild is merged** (68f6d15,
   brief 03; built on feat/side-rebuild, SR0-SR6). Walls go along missing OR broken outline edges,
   and the broken pieces are replaced (A 105, B 45). The inside seen through them is covered and
   then removed by the hidden pass.
   - Back faces seen from outside: A 119,504 -> 20,945, B 21,948 -> 5,993.
   - The owner's sawtooth (B region 309, the ramp) is one clean wall in the written `.skp`: its
     close-up has 948 back pixels (input 43,696).
   - Left (brief 10): the cap guard judges a wall and its bottom separately; `max_thickness`
     (36 in) is below the 39.37 in blocks; the underside test misses some undersides; B's middle
     slabs read as trays from below; a thin purple plate stays at the ramp's landing end.
2. ~~Lines inside flat surfaces in the `.skp`~~ **mostly fixed** (writer softening bcccca2, T-junction
   threading 28d63df): A 121 -> 9, B 41 -> 27. What is left: B's 15 material seams (real edges) and
   double layers (one surface's edge lying over a second copy of it: A's 551 in line at x = 2515.77
   and 9 on B), expected to go with the side rebuild; see briefs/06-leftovers.md item 15.
   **At ca463c2** (side rebuild merged), by the audit:
   - A has 17 lines inside flat surfaces (20.3 ft) and 3 T-junction lines (12.3 ft). A's 551 in
     double-layer line at x = 2515.77 is gone. Three of the six longest lines left lie along
     x = 2673.2 at z 1778.1, not traced.
   - B has 0 lines inside flat surfaces and 20 T-junction lines (42.3 ft).
3. ~~File A's sloped underside is a triangle lattice~~ **fixed (b3b9ad3)**: the region's own
   T-junctions made a 71 in x 0.00006 in sliver in its union, whose corner sat 7.87 in from any
   vertex; such slivers are now closed at the source. In the `.skp` that underside is 111 soft-edged
   triangles, because it is 0.005 in off flat and SketchUp splits any face more than about 0.001 in
   off its plane (19 such regions on A, 9 on B); the edges are hidden. Leftovers found on the way:
   file B region 74 draws as 17 triangles (4 overlapping triangles cut an island off it); region 38 is
   a side face with a solidify wall laid over it (solidify took an existing side's top edge for an
   open edge); region 79 is two original triangles folded over their shared edge.
4. **Interior visible from inside the model** (owner's X-ray/inside screenshot): faces kept because
   they are visible through openings or slits in broken sides; follows item 1. With the side
   rebuild merged, the hidden pass removes A 2,063 and B 2,734 faces (was 1,985 and 2,566). Not
   re-checked from inside.
5. **Review**: part 1 and 2a done, and their fixes landed (briefs 07, 08, 09). Part 2, the side
   rebuild, is queued.
6. **Dashboard fix wave** (brief `.superpowers/sdd/2026-09-22-dashboard-and-engine-continuation/fix-wave-1-brief.md`,
   D1-D12) not started; D0 superseded by the F5 merge.
7. Different-material overlaps: the owner's preference step ("which face wins") not built.
8. **File A ships a coincident double layer with opposite windings** on its lower landing at
   z 1612.2 (x 1384-1443, y 22591-22630). Both layers come from the export, and they z-fight.
   Neither the fold pass nor the duplicate-layer pass removed either one (not traced). Found in
   brief 03, while tracing why the T-junction threading moves A's back-face count by 161 pixels:
   it is only which of the two layers a ray meets first.

## 7. Decisions that shape the engine (details in the ledger)

- Visibility is judged double-sided (SketchUp and the Unity shader draw both sides); a one-sided
  render is a diagnostic only. A culled render once faked holes in an intact sidewalk.
- Nothing visible may change unless a rule names the change and measures it: z-fight ties, closed
  cracks (capped), removed debris (by name), border shifts up to the merge's own 0.15 in tolerance.
- Only solidify may invent vertices; the merge never moves or invents one.
- Merge area rule amended (d505241): per region a bounded border movement, per pass no net growth.
- Peer-session work is accepted only after measurement in an isolated worktree and merged by the
  controller; foreign uncommitted edits are parked on `wip/` branches, never discarded
  (`wip/snapshot-alias-copy-master-plan`, `wip/footprint-heuristic`).

## 8. Diagnostic scripts (copied here from the session scratchpad)

Run from the repo root with `PYTHONPATH` set to the repo root and the project interpreter
`.venv/Scripts/python.exe`.

| Script | Answers |
|---|---|
| `scripts/diag_flicker.py <snapshot> <out>` | Where are the pixels that fail the merge guard, per view, with the faces under them |
| `scripts/diag_flicker_dist.py <out>` | How far did the surface really move at each of those pixels |
| `scripts/diag_new_vertex.py <snapshot>` | Which merge region is skipped for a new vertex, by which path, and how far off |
| `scripts/skp_edge_audit.py <file.skp>` | Every edge SketchUp draws, classed; lines inside flat surfaces and T-junction lines |
| `scripts/edge_audit.py <file.ngon.obj>` | The same for the polygon OBJ (overstates: holed regions are triangles there) |
| `scripts/render_skp.py <file.skp> <out dir>` | 21 renders of a `.skp` with only the edges SketchUp draws |
| `scripts/sketchup_views.rb` (through the SketchUp bridge) | Real SketchUp views of the open model: shaded with back faces purple, X-ray, textured |
| `tools/auto_continue.py status` (repo root) | Is Claude at its usage limit, which job Hermes would take over, what Hermes spent today (HANDOFF.md section 7) |

## 9. How to resume

```bash
.venv/Scripts/python.exe -m pytest engine/tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/ce26e0392ab0 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli fix data/snapshots/0b290ec0bcb4 --out data/output --skp-dir "D:/PROJECTS/UC MODEL FIXER/data/skp_scratch"
.venv/Scripts/python.exe -m engine.cli preview-data data/snapshots/ce26e0392ab0 --out preview/data
```

Then read `data/output/<name>/report.json`, look at `data/output/<name>/qa/*.png`, audit
`data/skp_scratch/<name>.fixed.skp` with `scripts/skp_edge_audit.py`, and read the tail of the
ledger for the current queue. The owner's `OBJ FIXED RESULT/` is refreshed only from committed code
(HANDOFF.md section 2). If Claude was cut by its usage limit, first run `tools/auto_continue.py status`
and read `AUTO-CONTINUE-LOG.md`: Hermes may hold a job (HANDOFF.md section 7).

Lessons that cost time: agents are cut by the account session limit (resume them by message after
the reset, never re-dispatch blindly); on Windows a running agent's output file reads as empty, which
is not a hang; other sessions edit this same working tree, so workers use their own worktree or
branch and the controller merges; describe the work inline in agent prompts; run API tests only when
no other session is (they drop the shared test database).

### 2026-10-19 � STAGING-ENGINE-2-3 (codex-sol)

Claimed owner-requested MAIN INFRA floors 2�3 engine run. Export complete: 53,605 and 58,216 triangles. Repair pending. See STAGING-ENGINE-2-3-report.md; obsolete --stage-failed replaced by equivalent default staging.

STAGING-ENGINE-2-3 progress, 2026-10-19 20:05 +08:00: runner tests 26 passed; floor 2 fragment ray verification reached round 52, 755 initial units. Automatic artifact and headless Blender readback verifier queued. Recovery details in STAGING-ENGINE-2-3-report.md; no floor pass claimed.

### 2026-10-19 - STAGING-ENGINE-1-6-7-V2 (claude-vertex-opus)

Claimed owner-requested MAIN INFRA floors 6, 7 and 1 engine run into MAIN-INFRA-ALL-FLOORS-ENGINE-STAGED.blend (work dir engine-7floors-v2). Input V2 is re-saved by a live Blender session, so the run reads the sha256-checked copy MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-210156.blend. Runner tests 26 passed. Launched 21:08, waiting for memory headroom. See STAGING-ENGINE-1-6-7-V2-report.md; no floor pass claimed.

STAGING-ENGINE-2-3, 2026-10-19 21:24 +08:00: first floor 2 attempt failed after at least fragment round 240 on a 2.14 MiB trimesh allocation. Full failure preserved in engine-7floors-2-3/2F/engine-attempt1.log. Runner automatically began retry 1/3. No fixed OBJ or staged Blender output yet; verification pending.

### 2026-10-19 - STAGING-ENGINE-4-5-V2 (claude-argon)

Claimed owner-requested MAIN INFRA floors 4 and 5 engine run into MAIN-INFRA-FLOORS-4-5-ENGINE.blend (work dir engine-7floors-4-5-v2). Input V2 is re-saved by a live Blender session (21:50:57 and 21:56:50), so the run reads the sha256-checked copy MAIN-INFRA-ALL-FLOORS-FIXED-CUTS-V2.frozen-215650.blend (0d3ffedb...d8a8). Runner tests 26 passed. Launched 21:59 (PID 47836); export complete: 4F 45,004 tris, 5F 34,464 tris; 4F engine running. See STAGING-ENGINE-4-5-V2-report.md; no floor pass claimed.

STAGING-ENGINE-4-5-V2, 2026-10-19 22:45 +08:00: first floor 4 attempt hit a 1.76 MiB trimesh allocation failure in piece_ray_check during a machine commit spike (436 MB free); preserved as engine-7floors-4-5-v2/4F/engine-attempt1.log. Runner automatically started retry 1/3 at 22:44:13 with 5,629 MB commit free (PID 41872).

STAGING-ENGINE-2-3 recovery: second floor 2 attempt failed at 22:42 on a 1.42 MiB allocation. Source changed externally; preserved new 18949D... snapshot and archived initial exports/logs. Restart shim 57684/interpreter 6316 is waiting for 10 GB commit headroom. Auto-verifier shim 6300 watches engine liveness and will check both OBJ variants and fresh Blender readback. No fixed output or validation pass claimed; job remains active and resource-blocked.

### 2026-10-23 - MAIN-INFRA-RESET-20261023 (Codex)

Owner reset to the fresh seven-floor Z: Minecraft export, confirmed 1 block = 1 metre, and authorized deletion of both old plans/jobs and failed outputs. Retired five old job entries, deleted six explicit failed-guard OBJ variants and four obsolete plan/brief files with SHA-256 receipts and absence readback. Source/raw data and diagnostic evidence remain. Replacement design/plan reviewed independently; progress precedes import and simulated dashboard completion/approval is disallowed for fresh MAIN INFRA. Queue tests: 9 passed in 1.22s. See MAIN-INFRA-RESET-20261023.md. Actual state: plan awaiting owner review; no fresh geometry repair, model acceptance or dashboard code/deployment this turn.

2026-10-23 MAIN-INFRA-CLEAN-20261023: owner approved execution. Dashboard a1e234f has 20 passing UI tests, clean typecheck/lint/build and actual disk-backed browser polling/mobile proof. Engine 25cd6e5 has 59 passing focused import/freeze/cleanup/progress tests. Fresh source qualification next; no repaired/accepted floor or deployment. See MAIN-INFRA-CLEAN-20261023.md.

2026-10-23 Codex MAIN-INFRA-CLEAN: fresh seven-card Before/After dashboard committed2800a66/de060b9, compiledbrowser8.9s/build26pages/UI28/publisher17 pass. Engine98a1580/fa5db8a. Independent1F preservationPASS but overallFAIL;4Fstrictguardnext with reviewed originalmesh oracle. Noacceptedfloor/SKP/deployment. Mainownedrecords synchronized; taskworktree carries committed record.

2026-10-23 Codex MAIN-INFRA-CLEAN: 4F strict guard passed 4853024pixels, failure classes0, all78160triangles and19assets retained. Native QA30pairs identical; independent readback passes. Original336Validator full signed checks running worker49304 with PID-bound heartbeat. Noacceptedfloor/deployment. Engine9306483/dashboard9386a4d records.

2026-10-23 owner split recorded: Codex1F–3F, Claude Code4F–7F; both use UC MODEL FIXER engine. Disjoint/allseven checks passed in data/main-infra-fresh/floor-ownership.json. Claude queuejob MAIN-INFRA-CLAUDE-4F-7F-20261023 ready, not falsely claimed. Separate output roots; single shared dashboard publisher Codex. Claude actual process/output not yet confirmed. Mandatory actualengineoutput AGENTS9 committed4c2329c after independent audit.

2026-10-23: Actual fresh1F E3 complete15856->10136/5720removed. Full signed textures+visible coveragePASS;16qualifiednativepairs0RGBA. Initialeye0camera wasinvalid(.6002mabovefloor/1mcavity), correctedno pedestrianfacadedamage. OveralltargetsFAIL1626differentlook/1014same/2372cracks;unaccepted. UserexplicitlyrequiresLIVEjev-repairpage. Atomicstatus+24model/evidencefilesinstalledbothhostingroots; HTTPstatus8c00b09c...verifiednext. App/APIstillbb71d31; noDB/restart. LiveUIbranch44da3d8b basedbb71, not197commitsbehindpreviewbranch. OwnershipCodex1-3/Claude4-7 remains.

2026-10-23 19:12 +08: Liveabd68ceUI95hashesverified2roots/public,realbrowser7cards/textured1F15856->10136explicitcandidate,26statuspolls200. Fixedpublisherpermissions600->644. Actual2F53936/56832(3F) checkedE3runningfec7b3e;56828/53602inputs;independentproofpending. PID/startboundpublisher47902. Claude4-7claim/worktreeconfirmed;noengineoutputclaim. Noacceptedfloor/DBchange/apprestart.

2026-10-23 20:00 +08: Real1FE7PID56540/tree396061b1;original15856/E3stage10136;independentE7/serializer/finiteindexreviewsPASS,actualpreservationpending.2F53936/3F56832originalimportsunchanged.Livepublisher47760/session68861all3actualworkers;2F/3FBeforemodels9/7texturespublic/browsed. Claude7FseparateE3saved26152->20625pendingvalidation.DraftPR39unmerged;GitHubCIneverstartedduebilling/spendinglimitnotification.Noacceptedfloor/DBwrite/apprestart.

2026-10-23: Supersedes lower-floor running report: all1F/2F/3F workers failed12:20:17UTC; independent Windows Event1003 confirms99.63% systemcommit. No new candidates. Failed attempts preserved; owned bulk test stopped; sequential fresh retries prepared, not started. See MAIN-INFRA-MEMORY-RECOVERY-20261023.md. UI58a0f34 built33routes,35focusedtests passed, compiled/live proof pending.

2026-10-23 21:05 +08: Fresh mesh inspection is LIVE from Siege 58a0f34, evidence cd148fd. Authenticated live check: 65/65 status polls200, zero exceptions, 390px no overflow; all95 static files verified, API/models/status preserved. Root reopened live1F proof. Serial1F E7 attempt2 started PID43456, creation13:00:59.5817497Z, exec85048 after three >=8GiB headroom samples; observerexec51889. Sole publisherexec1032 follows the new actual worker. Older E3candidate10136 remains explicit inspection only; no new candidate or accepted floor.2F/3F wait sequentially. See MAIN-INFRA-MEMORY-RECOVERY-20261023.md.

## 21:50 +08 — actual retry terminal and source-boundary diagnosis

1F E7 attempt2 PID43456 ended13:36:26.253134UTC, wall2121.56s. Default
kernel final PASS followed three rollback rounds:628planned,273kept,355rolled.
Serializer then failed source-frame `_source_weights` boundary equality; final
1F and staged candidate are both absent. 10,578 is UNSAVED, never a new After.
Independent receipt b0a5f202d6b37628d8e5cc351bf9d221eb005ba3db24ecf833ff3f26fb1389f8
binds failed artifacts and explicitly records independent checks NOT STARTED.
1023 resource samples: observed worker peakcommit2,311,098,368B, minimum global
headroom3,774,504,960B. This attempt passed the previous memory failure point.

Bounded deterministic planner reconstruction matches all628 actual K1 records.
263/273 kept source float proofs pass; ten fail only Shapely barycentric union
by2.7755575615628914e-17 normalized area. Exact Fraction(original binary64)
plane, nonnegative barycentrics, positive winding, exact area and oriented edge
boundary cancellation pass all ten. Literal site2479 fixture SHA
0ffab4d4c34b446a799ea0edc2af25e03dec4d89341161261b6689b0b3dee702;
parent area3/32m². Source positions remain unchanged. A separate TDD serializer
fix is in progress; no epsilon/snap/buffer/guard loosening is authorized.
K1 logs omit exact UV/normal/output bytes: they cannot certify a recovered
original candidate or justify attaching the old PASS to reconstructed geometry.

Status runtime isolated RED reproduced retry reading obsolete worker path;
GREEN1test passed after actual path binding, loading-state support, pending
triangle counts and truthful per-floor failure summary. Owned publisher16316
was creation-time verified then replaced by exec42942. Public13:47:02 readback
reports actual1F source boundary and old2F/3F allocation failures, unchanged
E3candidate URL; both remote roots hash b18c3d8f at13:46:24. Source/model/DB/server
state untouched. Runtime and its bounded fixture are preserved beside this
record under scripts/main-infra/live-worker-status-runtime.ps1 and
scripts/main-infra/test_live_worker_runtime.py.

2F retry wrapper a4898bdd / frozen component531769c / exact floor material maps
remain prepared, not started. Launch gate13:43/13:47 had4.173/4.493GiB commit
headroom; no new heavy job was started into that margin. No foreign app killed.
Codex1F-3F and Claude4F-7F remain separate. UI filter LIVE; no floor accepted.

## 22:15 +08 — source fix committed and actual 2F retry launched

Source-saving fix94dc8a4b54da572c703f35678bc1165bbbda91a9 is committed in the
separate main-infra-e7-source-proof worktree. Only production file changed is
serializer tools/main_infra_e7_serialization.py, SHA6456ac625441ce9c2649e088247ba73e094995858b074a127d7a54292365a44a.
49focused tests pass locally7.09s and independently5.77s. All273 source cuts
accepted, zero rejected, all628 donor K1 records matched. Actual all273 receipt
5ef4f7d5a395f26ba1284819a35223e0c83a45e2a2dd02f0e88637d4c21f9e3b;
independent linkageb651f602beeee46ed55f4ddeb42804a7a50dc35b7cf954c9f517390ce0b53219.
All11 committed evidence files read/hashchecked. Jobawaitingreview, no core,
weights, guard, signedValidator or threshold change and no saved new1Fmodel.
New attempt3 checked-subset/checkpoint implementation is in a separate claimed
job/worktree; no old PASS may be attached to reconstructed geometry.

Owner replied that they would free memory. Root measured recovery, initially
7.607/7.736GiB; strict8 and7.5GiB trial gates returned NOTSTARTED and wrote no
worker/candidate. After assessment the operational one-worker gate is7GiB,
with three fresh samples; this is not a model guard tolerance. Actual successful
launch samples at14:13:09/10/11 UTC were8.056/7.919/8.187GiB, physical available
4926/4763/5031MiB. Frozen code531769cad83dd6d03214a94cbd21e0209f8f2f33,
runtimea4898bdd79b192b20bb1c40afd31d1623dd3c3d28f06e8fd33c4c7a35ef9190f,
2Fmaterialsf06c1c87d9ceee46e3a5d1c4241059d86dc2bf7e5bf06d09c9f3a95433024df8
were checked before launch. No overwrite or prior failure deletion.

ACTUAL2F E3 attempt2 PID41648, creation14:13:11.8254166Z, exec73109, input56828,
state running_checked_E3. New private run is E3worktree/data/main-infra-e3/
run-20261023-attempt2, console main/data/tmp/main-infra-2F-attempt2-console.txt.
Observerexec37006 records resources-2F.jsonl. At14:15:10 workerprivate596MiB,
peak1341MiB, systemheadroom6.555GiB. Bounded150-250MiB fixture window granted
to attempt3builder; no second heavy geometry/guard/native/Validator/browser.

Rootsolepublisher60916/start13:46:23.0224340Z/exec42942 reads new atomic
extra-e3-workers.json PID/start/path. Actual public14:13:57 reports2Fcleaning,
PID41648/alive/CPU41.75, overallrunning. 1Ffailure remains sourceboundary;
prior preservedE3inspectionasset remains unchanged. 3F remains its old failed
attempt until its actual serial retry. Separate independent2F caller is being
prepared, not run. Codex1F-3F / Claude4F-7F; no accepted floor.

## 23:12 +08 — truthful queued retries, reviewed callers and exporter

Actual 2F E3 attempt2 remains running PID41648/start14:13:11.8254166Z,
component531769c, qualified56828 triangles. At15:06:20 workerprivate1291MiB,
peak1967MiB, systemcommit57,436,819,456/67,303,272,448bytes; no saved candidate
or new failure. A single heavy geometry process remains the operational rule.

The reviewed 1F attempt3 component is18c8ae993cfed71ad7e978d7b253cecb8a1ec5c5:
new checked subset, typed checkpoint captured BEFORE saving, exact source-proof
serializer6456ac62. Independent36fixtures passed15.28s; final reviewf6372781.
Real prepare/run has not started; no old kernel PASS is reusable. 2F independent
caller committed1ac1de3 with53 pinned inputs/0mismatches,30tinytests passed2.53s;
actual guard/native/full Validator waits for saved output and serial memory GO.

The E7 preview exporter now has local52PASS20.14s and independent52PASS23.08s,
reviewb9000bb9; fixtures use real tiny geometry but synthetic external evidence.
Initial independent path-limit-only test failure is retained. No actual E7floor
was packaged or accepted. Root delegated only named reviewed-file commit/records.

Retired failed1Fworker config; all prior attempts/records preserved. New deferred
3F observation regression RED then GREEN1test/0PowerShellparsererrors. Replaced
only owned status publisher60916 while idle; replacement47864 creation
15:08:03.691458Z exec79843. Public HTTP readback15:08:05 reports 1Fqueued,
2Fcleaning/PID41648/alive,3Fqueued. Existing1F E3inspectionpreview10136 remains;
2F/3FAfter stay empty. Full same-turn public artifact is queued-retry-live-
readback-20261023.json beside the tested status runtime. Claude4F-7F unchanged.

### Reviewed exporter committed; checkpoint status regression

E7 preview exporter commit2197243f0bfd4187dba41b3728c1193bb6702168 now contains
exact independently reviewed bytes (reviewb9000bb9) and durable successful52PASS
log plus the prior path-limit-only failed log. No real E7model was packaged.
Sourcefix/attempt3/exporter jobs remain separate, with no engine/guard changes.

A new actual attempt3 state checked_checkpoint_saved exposed another truthful-
status regression: RED reportedfailed, GREEN1test0.135s/0PowerShellparsererrors
now reports cleaning and verified checkpoint saving. Next-action text derives
from observed active floors. Runtime file updated on disk; running publisher
47864 retains its loaded212cd30 version until the next owned restart before1F.
Actual2F remains the only heavy worker; saved independent output still pending.

## 23:38 +08 — actual 1F preparation saved; guarded execution gate

Actual1F prepare-only CLI completed EXIT0/wall36.726s, frozen18c8ae9, planSHA
e5af36dde9a242388985200cd6502b370dba87aba92ef152bec9e91b0f681e2a. All628donor
K1records match;273selected/355excluded;273exact-source+273engine proofsPASS,
rejects0. Original15856/stage10136 remain distinct.14inputs/201components/3donors
rehashed; executiontreeHEADunchanged. Durable readback57b3b69f copied verbatim.
35globalsamples minheadroom7.23GiB. Private/peakINVALID: initial observer tracked
venvlauncher64416, not actual interpreter; never use847872B as worker budget.
No1Fkernel or candidate exists yet. Public15:32:07 shows queued273proofmilestone.

Operational rootreview permits a guarded second1Fworker only after3fresh>=8GiB
headroomsamples, actualchild identity fromlaunch,3GiB private/OSpeakcap and abort
onlynewowned1Ftree ifglobalheadroom<3.5GiB/counteroridentityfailure. Independent
review found reasonable best-effort, not a guarantee. This changes no geometry
threshold or signed guard. Recent600samples min5.880/median8.297/latest8.372GiB;
2Factualpeak1.921GiB, prior1F2.152GiB. Launch still requiresactualgates; at15:37
headroom7.426GiB/no1Fexecuteprocess. No other new heavy process is authorized.

Loaded tested checkpoint-aware3438f3e status runtime by replacing only owned
publisher47864 with4996/start15:35:22.463240Z/exec46920. Newdynamicnextaction uses
observed active floors. Publictwo-rootreadback15:35:24 identical; 2Factual41648
stillrunning,3Fqueued; Claude4F-7F remains separate. Independent1Fattempt3caller
job claimed in separate tree; only bounded TDD permitted. Noacceptedfloor.

## 23:55 +08 — preserve Claude blockers; optional 1F launcher held

Read-only ownership audit: actualClaude5F PID52020/start13:51:56.4222323Z was
alive/private1.20GB;4Fownerstep says checkedE3queued after exactduplicateguard
(noE3workerwitness).6F/7F immutableworkerrecords candidate_saved27108/20625,
ownerreportsblocked due signedremainingtargets. No foreignworker/outputchanged.

Found and corrected a statusmirrorbug: candidate_saved overwrote ownerblocked
withvalidating. GenuinefixtureRED ('validating'!='blocked'), GREEN1test0.200s,
PowerShellparser0errors. Savedcountretained; blocked/failed/cancelled ownerverdict
preserved. Replacedonlyownedpublisher4996 with57300/start15:52:56.585440Z/exec10075.
Public15:53:37 confirms6F/7Fblockedwithactualownerreportedtargetcounts/evidence
summary, 2Fcleaning,1F/3Fqueued. Publicreadbackartifactcommittedbesideruntime.
RootdoesnotclaimindependentgeometryapprovalofClaudeoutputs or adoptassetURLs.

Optional1Fconditionalgate samples15:38were7.8276/7.6605/7.6815GiB (<8), later
7.6..6.8GiB. Noexecuteeverstarted. Independentexternalobserverreviewfoundearly
unboundchildcleanup, unverifiedkill andblockingCIMgaps. RootrevokedGO; agent
stoppedonlyownedobserver63804/start15:45:31.7673815Z andverifiedexit15:49:21.
RootindependentCIM15:49:42foundnoexecute/noobserver. No1Fexecutionnamespaceor
candidateexists; frozen18c8ae9/P e5af unchanged. Observer-only lifecyclecorrection
andnonmodelregressions requireindependentreview+freshrootGO. Actual2F41648
continuescheckedkernel; nooutput/newfailure. Noacceptedfloor.


## 2026-10-24 00:35 +08 - actual 1F saved, independent proof started

ACTUAL1FE7 attempt3 saved10578 source/engine triangles fromstage10136/original15856.
DefaultfreshkernelPASS;273kept/0rollback; verifiedtypedcheckpoint BEFORE saving;
all7newMTL/PNGassets exactqualifiedhashes. ActualPython60308/start16:22:46.8585703Z,
launcher51068/monitor60396/exec21420 exited0 at16:31:19.243954Z. Kernelwall482.12s,
launchwall512.467s; peakcommit1.55GiB/minheadroom5.87GiB; noresourceabort.
Frozen18c8ae9/P e5af unchanged. Newfinalcutb587c3b9/runadb653f7/asset019d965f/
checkpointf6a25830; fullfinalreadbacka73a7462 copied verbatim beside these records.

Earlier v3 startup rejected ownedconhost and stoppedbeforemodelwork;all3owned
handlesexitverified/noWdir. V4narrowclassificationfix9cce3684 independentlyclear;
real_components SAMEHiddenstartupRED->GREEN3.719s/49samples/all10handlesexited.
Actualv4passinggates8.603/8.675/8.712GiB, fullownedtreebudget3GiB/<3.5GiBglobalabort.
ExactreviewedPSbytes preserved withoutGitnewlinefilters. No geometryrulechanged.

Public feed boundactual1F60308+2F41648; now1Fvalidating/pending10578, displayed
E3candidate10136 retained untilnewindependentpreservation/nativeproof. 2Fstill
checkedkernel/nooutput,3Fqueued; Claude4F-7F separate. Publisher57300/exec10075.
Independent1Fcallerdaa5d94/source2ad92656 has36PASS/help0/reviewclear; formaljob
handofftoCodex-Independent-Validator. Its2checkoutCRLFfiles restoredonlyfrom
verifiedcommittedLFblobs; all201components/14inputs/3donors/7assets match, treeclean.
RootGO actual1Fbind/prepare thenfresh>=8GiBgated strict26 -> native33qualified+
13diagnostic -> fullsignedValidator/defaultSettings/targets against ORIGINAL15856.
Singleextraheavybesideexisting2F; owneroperatorindependent. No modelpublication or
acceptedfloor yet. Signedtargets may FAIL; do not weaken or reuse oldPASS.


2026-10-24 00:54 +08: actual independent 1F preparation exited 1 after
75.618 s on caller metadata, before strict guard/native/full signed validation.
The retained original qualified 1F receipt d2ab32f2 has no historical job_id;
its qualified/floor/revision and all four source/engine/reference anchors match.
The failed actual PID15192/result15167ca3/stderrdd981abb remain immutable.
This is not a geometry failure. A narrow caller compatibility fix is committed
3796a0c2: missing historical job_id is allowed, a present wrong/null/blank value
is rejected, and all existing source anchors stay required. The actual retained
schema regression failed before the fix; 44 targeted tests pass afterward.
Independent diff review and a fresh actual preparation retry are pending.
No new 1F E7 model is published or accepted: live shows pending10578 and keeps
the existing independently preserved E3 preview10136 until the new proof exists.
Actual 2F PID41648 remains in the FIRST combined SiteJudge preservation check
(kernel first call, not repeated per-site checks). CPU rose22381.69 to22681.34 s
in118.87 s; one no-locals, nonblocking MainThread dump confirms active ray-lattice
work. No output/ETA/percentage is claimed. 3F readiness55e33ccf and measured glass
factsd78b3dda are copied into this record folder; no 3F engine launch occurred.
The live public status returned200 at16:49:56Z: 1Fvalidating,2Fcleaning,3Fqueued;
all accepted_preview fields remain null. Codex1F-3F/Claude4F-7F split unchanged.


2026-10-24 01:17 +08: actual independent 1F preparation is retrying under committed
callera77aa44f3366820c7fd7aef94d82e7ab403ba20d, PID34652/start17:15:36.6328407Z.
The prior metadata correction3796 passed independent review, then actualretry37540
stopped on an additional stored/physical fingerprint equality prerequisite.
Measured469a0df8/ada1e27d prove physicalmissing5990/added712 are strictsubsets
ofstored5993/715; both depthfloors0.05in; zero physical-only or unchanged-lineage
mismatches. Three tiny existing-vertex cut aliases explain the difference.
The corrected caller requires this explicit conservative superset (all physical
suspects still checked), records both masks, and rejects physical-only suspects,
shape/type/depth changes. Actual retained fixture RED then55PASS13.87s; delivery
independently verified actualmaskbytes,17inventory+201component/14input/3donorpins
and all default signed sampling branches. No geometry/engine/guard/defaults changed.
Completed1F engine feed config was retired after candidate_saved witness95e9c175;
actual precision blocker was publicly readbackHTTP200, then canonical1F was moved
tovalidating with actualretry34652. Pending10578/priorE3preview10136/acceptednull
remain. New model publication waits for independent guard/native/fullsigned proof.
Reviewed3Fwrapperbd6862b2/config7f7b2698 refuse preexisting output/W/snapshot and
E3subdirectorycwd beforegate/launch; actualrootpositive/toolsnegative passed.
All219pins match, V4unchanged;3F model HOLD behind1F proof and8GiB launchgate.


2026-10-24 01:21 +08: preparation34652 exited1 at17:16:50.617Z after74.079s,
after passing source qualification and measured conservative precision proof.
The next failure is a receipt key collision: builder target path is already
bound as targets; validator default target lives in a different worktree.
All owned handles exited; no resource abort or guard/native/full model verdict.
Both agents now audit all phase pin namespaces against the real multi-worktree
receipt before a narrow distinct validator-target label fix/retry. Original
builder target entry, signed target bytes and model/P remain untouched.
Canonical/live1F now reports the actual checker handoff blocker, workerfalse;
new10578 candidate remains pending while prior10136 preview stays inspectable.


2026-10-24 01:36 +08: ACTUAL independent1F preparation and strict26 GUARD PASS.
Complete cross-worktree audit of committedcallera0a8dbda70544d9e1dee90f0d52271a7321324dd
verified293phase labels/files0collisions/mismatch;58targetedtestsPASS14.12s.
Actualprepare64336 exited0 at17:29:21.404Z; savedprepared6254dd54 binds294paths,
original15856/stage10136/final10578 and exacttypedcheckpoint/cut/assets.
Actualguard26816 exited0 at17:32:28.822Z; saved489f5c23 covers26views900x600,
3,924,929modelpixels; holes/material_changed/moved_other/grown all0; existing
zfight_tie1 retains passed=true. Physicalguarddepth5.9055118110236214e-5in,
nooverride. Originalbed4/candidatecc8e hashes stillmatch; all295guardpathsrehash.
Actualnative60972/start17:34:32.2104441Z nowrunning withBlender5.1.2 source-source
andPILsavedPNGreadback;33qualified+13diagnostic pairs, no nativeverdict yet.
Userfreedmorememory: root17:25 headroom9.546GiB, guard3freshsamples~12.7GiB.
Everyheavy retains8GiB admission/3GiBown/global3.5GiB abort. Root/peer approved
an additional3F admission check of3fresh>=12GiB before unchangedreviewed3Fwrapper,
reservingfull3GiB3F plusfull3GiBremaining1Fproof;3F actual launchstillpending
freshpreflight/admission. Source/modelthresholds unchanged;1F proofpriority.
Live1F updated toactualnativePID60972, strictguardPASS26/26; pending10578 and
priorE3preview10136 remain. No newE7preview/acceptedflooruntilnative+signedproof.


### 2026-10-24 02:14 SGT - actual 3F run and conservative 1F retry

- Actual 3F E3 worker22268 started2026-10-23T17:36:13.820579Z after three measured12GiB admission samples; original53602triangles, isolated from actual2F41648. Code531769c, worker a4898bdd, qualified3Fmapada00c4d; both still running on fresh source. No candidate/acceptance invented.
- Actual1F independent strict26-view guard PASS:3924929modelpixels, zero holes/material/moved/growth; existingzfighttie1. Prepared6254dd54, guard489f5c23. Native e80bf884 FAIL:335RGB-only changedpixels in17/33qualifiedviews, alpha/silhouette changes0 across46pairs. E7 candidate10578 remains blocked; old preserved E3candidate10136 stays inspectable and acceptance remainsnull.
- Independent pixel-center diagnostic associates335changed samples with92E7sites, matching originalparent/material/depth and no nearest-hit ties. This approximates camera/rays and does not identify actualGPU primitives or prove native preservation. Exact Fraction source audit8d1d7862 measures all715cutchildren/2145corners: maximum1.5762807725749894e-12texels;9863unchangedfaces and fullpositiontable exact, no material/plane/membership/winding failure. Raster/texture interpolation sensitivity remains a hypothesis.
- Separate unchanged signed Validator diagnostic actually runningPID29576/start17:52:10.6357055Z, nativeFAIL retained, diagnostic-only/notpublishable. Base231919casts completed; dense removed-face visibility underway. No guard, target33606ce9, Settings/FixProfile or quality threshold changed.
- Created independent attempt4WT at18c8ae9, branchcodex/main-infra-e7-native-safe-attempt4-20261024. JobMAIN-INFRA-E7-NATIVE-SAFE-ATTEMPT4-20261024 claimedCodex-1F-Native-Safe. Narrow TDD policy will exclude all92native-mapped whole repair proposals after unchanged628donor verification(273kept/355rollback), retaining181 original edits/order with new hash-boundidentity/namespace/checkpoint. Code and tiny tests only are authorized now; real prepare/kernel waits for independent review and free guarded1Fslot.
- ClaudeCode owns4F-7F; no foreign model/process/server/liveDB touched. Root continues scoped live worker/status publication.


### Actual 1F signed diagnostic terminal - 2026-10-24

Actual29576 completed18:17:41.9728646Z/1531.49s, exit2 with full signedFAIL report967e49df and receipt2cd78fea, noabort/allownedexited. TexturesFAIL108392samples/10covered/4faces, no look/UV/side mismatch. Per-facecoverageFAIL9809=11.5px and10366=6.2px (>4), contributor site6680/edit211/original9807; this site is outside92native-linked. Textureclusteroriginal8563/8564/8633/8634 retains exact source faces but covering contributors are not persisted; bounded unchanged-function replay authorized to map them, not an acceptance shortcut. Both failure groups remain blockers, no proof/publish promotion. Rootopened both actualfloorPNGcropped evidence: thin highlighted seams.

Both attempt4briefs amended: exclusion count is measured union of native and all signed-failure contributors, not fixed92/181; policyseal waits for complete mapping. Independentattempt4job/WT froma0a8 claimedCodex-Independent-Validator, separate from frozen completeddiagnostic. Rootcanonical1Fblocked/workerfalse; existingE3preview10136 retained;2F41648/3F22268 running. Conservative builder TDD RED16failed16.87s/104.6MB after unrelated pytestplugin isolation; no newactualmodelrunyet.


### Complete measured attempt4 exclusion union

Unchanged-function four-face diagnostic replay reproduced100samples/10covered/232.5in² and27blockedvisiblelines in4.72s, tree252366848B, allownedexited/noabort. Contributor-map432e513ea14cac9f0604464c4bf249ffcd908b3a0c6f475994270dc24fd4a082 maps12aftertriangles to10texture-contributor sites2478,2479,2599,2902,2903,5185,8451,9039,9040,9503; floor adds6680. These11signed contributors overlap native92 at2902/8451. Final measured union101exclusions leaves172 of273donor-kept proposals; original628/273/355 classification remains unchanged. This supersedes earlier pending92/181 and93/180 arithmetic. Bind actual signed report967e49df, receipt2cd78fea and replay432e513e into new policy/preparation/checkpoint/cut/independent proof. Every excluded original face stays. No fullproof rerun or changed gate; attempt3remainsFAIL. Rootlive readback confirms1Fblocked/29576false,2F41648true,3F22268true;acceptednullall.


### 2026-10-24 03:00 SGT - conservative 1F engine retry actually running

The attempt4 code is frozen at 95dad1de1be241e613cb0763447b662b918f7eca in its separate worktree. Independent review cleared the policy, saved preparation and execution configuration. The original 628 donor checks and 273-kept/355-rollback partition are unchanged; the measured union excludes 101 proposals and keeps their original faces, retaining 172 original typed edits in order. Focused evidence: 26 policy/schema, 38 donor/checkpoint/runner and 1 component/CLI check passed. All 203 component, 238 preparation and 239 execution pins matched. Nine inherited files reproduce exact retained CRLF bytes after normalized committed-blob equality proofs; named index refresh yielded zero staged engine delta. No verifier, guard, target or algorithm change was used to resolve the byte mismatch.

Actual preparation PID59404 started 2026-10-23T18:54:20.7833793Z and exited0 at18:55:04.8597636Z after44.2429502s, no resource abort, all owned handles exited. Saved preparation SHA1e42d67a3419b9a3cc7388c8714837b7e06b358350450b5d11479b94353bf14d passed 172 exact-source and 172 engine proofs, with unchanged source positions and zero rejected proposals. Independent readback d5511909 verified selection order, typed digest/seal, all 14 inputs/3 donor inputs/203 components and the evidence-bound policy ff44af74. Measured preparation OS peak289861632B; minimum commit headroom9943691264B.

After separate operational clearance and fresh unchanged 8GiB/3GiB/3.5GiB admission/limits, the actual checked repair PID14236 started 2026-10-23T19:00:14.1430901Z (launcher53488, monitor10952). Phase config27e6ae73 pins the actual preparation; wrapper42e5/V4 observer9cce are unchanged. Actual execution-1F/worker.json reports checking/planned_cuts172. The existing live publisher now follows this exact PID/lifetime/path alongside actual2F41648 and3F22268. No engine candidate, new native/signed pass or acceptance is claimed yet. Attempt3 failures remain archived, and the existing inspectable E3 model stays displayed while the new output awaits independent proof. Claude Code owns4F-7F.

The separate attempt4 validator checkout now matches all203 builder components and is finishing its new cohort/identity caller tests. Its actual candidate hashes stay unset until this engine run saves. No active/frozen historical tree, owner source, server, database or foreign worker was changed.

### 2026-10-24 03:55 SGT - saved 1F repair; one-pixel native failure retained

Actual attempt4 engine PID 14236 exited 0 at 19:14:29.1437485Z after 855.1558136 seconds, no resource abort, all owned processes exited. The saved candidate has 10,393 triangles: 159 cuts kept and 13 fresh kernel rollbacks from 172 selected proposals. These 13 rollbacks are separate from the original 355 donor rollbacks and 101 policy exclusions. Final readback e339fcf5 confirms exact source position tables, unchanged surviving ancestry/UV/normal prefixes and all seven copied asset hashes. The default kernel confirmation passed after its own charged rollback round; no guard was loosened.

The independent validator is frozen at a50226737ac155f4f7a303e3c2afe48abd45c29d. Actual preparation 4e80ed64 passed. Strict guard 53f54fc4 passed all 26 views and 3,924,929 model pixels with zero holes, material changes, movement, growth or violations. Actual native readback eed21d64 FAILED: 32 of 33 qualified views are identical; one RGB pixel at (221,172) in outside ORTHO view_-1_-1_1 changed [176,176,176,255] to [206,206,206,255]. Alpha and silhouette occupancy changes are zero. Original/candidate/difference PNGs were opened and read back. The cause is not waived. All 144 native artifact hashes matched and all proof workers exited. No canonical signed report, independent acceptance, new candidate publication or floor acceptance exists.

Source-only footprint report 04f6947f checked all 416 kept child projections using F64 and imported F32 coordinates, whole-pixel area plus up to two pixels padding, exact rational intersection and no depth/backface filter. Only site 5120 intersects at padding 0, 1 and 2. This is not an actual GPU primitive claim. Its measured process exited 0 below 63 MB including observer. Actual 13 fresh rollback sites are 2028, 4414, 5676, 5688, 7485, 7491, 7787, 7913, 8126, 8232, 8289, 8835 and 8889. Attempt5 has a separate claimed job, branch and worktree; retain the previous 101 exclusions plus these contributors. Final union remains unsealed pending signed diagnostic; only bounded code/tests and draft policy are released, no new heavy engine phase.

Separate full signed diagnostic PID 57652 actually started 2026-10-23T19:50:43.2943031Z (launcher 21404, monitor 25236), after the footprint slot ended and fresh unchanged resource admission passed. Script 63b18bdf/config 9221c689 passed independent review with all 17 pins matching. It compares original 15,856 against candidate 10,393 using unchanged default Settings and signed targets; actual nativeFAIL is required. Output is exclusively native-failure-diagnostic, with acceptance/publication false. It cannot create canonical acceptance. Its terminal result is pending.

Latest actual process readback: 2F PID 41648/start 14:13:11.8254166Z and 3F PID 22268/start 17:36:13.8205790Z remain alive with measured CPU 48,877.1 and 17,144.1 seconds. Both worker files remain running_checked_E3 and neither candidate directory exists. Live publisher PID 57300 is alive. Live 1F retains the blocker, pending 10,393 triangles, displayed previous E3 candidate 10,136 and accepted_preview null. Claude Code owns 4F-7F. No foreign worker, owner source, server, database or API changed.

The owner clarified the new key is Claude Mem only. That exact configured key received HTTP 200 on a read-only provider authentication check; local memory worker health/readiness were HTTP 200. No key value was exposed or copied to Siege; actual compression is not claimed.

### 2026-10-24 04:03 SGT - actual 3F engine output saved; independent proof queued

Actual 3F worker 22268/start2026-10-23T17:36:13.8205790Z saved the fresh original 53,602 -> 38,691 triangles. Its monitor terminal exited0 at19:50:28.0941785Z after8054.5408417s, no abort, all owned processes exited. Of1820 proposed E3 edits,1675 were kept and145 rolled back; the default kernel confirmation passed with zero failing/unknown sites. Candidate source SHA a9108644, engine c3664f9e, audit56ab090d, lineage c16be706, edit-log22fd8da0. Root readback14e052ac independently parsed both saved OBJ spaces: full position/UV/normal tables are exactly unchanged, all38691 surviving faces/materials exactly match unique ordered original lineage, and all8 copied candidate asset hashes match original input pins. This is structural evidence, not visibility acceptance.

New job MAIN-INFRA-3F-VALIDATE-ATTEMPT2-20261024 is claimed Codex-3F-Independent on codex/main-infra-3f-validation-20261024, in a separate new checkout from frozen independent2F code1ac1de3. Delivery did not build3F and owns its independent proof. Only minimal shared2F/3F profile code/TDD/plans are released initially. Strict26 guard, native33 qualified+13 separate diagnostic views, and unchanged full default owner-signed original-to-candidate validation require independent review/root phaseGO. No engine/guard/profile/target/render-policy change or old pass reuse is allowed. Current2F frozen caller behavior stays unchanged. No3F acceptance or publication is claimed.

Public live JSON HTTP200 readback at19:55:56Z showed1F actual diagnostic57652/nativeFAIL retained,2F actual41648alive, and3F candidate saved38691/worker22268false/validation pending/accepted_preview null. The actual3F model remains undisplayed pending independent preservation evidence; root alone changes live assets. Claude owns4F-7F. The separate1F signed diagnostic continues with no verdict yet.

### 2026-10-24 04:18 SGT - measured 1F signed diagnostic failure; 2F confirmation observed

Separate attempt4 signed diagnostic PID57652 exited2 at2026-10-23T20:09:17.6134655Z after1114.429s, no resource abort, all owned processes exited. Actual report b1865442 and diagnostic receipt8622d58f retain nativeFAIL/nonpublishable. Textures PASS:108392 visible samples, zero failed/deleted/covered/look/UV/side samples. The dense visible-surface floor FAILS for original9809 at10.5pixels and10366 at4.1pixels, both probe422. Their reason is DELETED and covering_faces is empty; it is invalid to infer no contributors or reuse the old covered-face mapping. Both actual evidence PNGs were opened: gray/taupe surface panels with tiny magenta seam marks. The cause remains unproved; a separate bounded exact-default two-face attribution replay is being prepared. No full validator/native rerun or gate change is released. The final attempt5 policy stays unsealed and must reject unmapped DELETED failures.

The owner-signed problem census also remains FAIL: different-look flicker1626, same-look1014 and cracks2344 exceed zero targets; reversed0 passes. Report-only counts are hidden2945, loose1 and open edges2295. No canonical signed validation/review/acceptance exists. The live1F record was updated to blocked, actual57652false, native failure plus both coverage failures retained, texturePASS true, acceptance/publication false; previous E3 display remains.

A new read-only nonblocking/no-locals snapshot of exact actual2F PID41648/start14:13:11.8254166Z gives stack SHAe1a12432. It is inside visibility lattice from kernel.py run304, called by kernel.py353 run(kept,"confirm"). This proves the current stage is confirmation after charged rollback; no rollback count, final verdict or ETA is inferred. The worker remains running_checked_E3 with no saved output at this observation. No process was paused, injected into, restarted or changed.3F remains saved38691 with its separate independent caller/manifest review underway.

### 2026-10-24 04:37 SGT - 3F strict guard passed; inherited1F site5 loss bound to repair jobs

Actual3F strictguard60004/start20:23:41.9680715Z exited0 at20:24:01.3682605Z after19.4703363s, no abort, all owned exited. Guard01dc21dc passed26views at900x600/4,717,188modelpixels with all failure totals0; existing tiecounter5 remains nonfailure. OSpeak867954688B/tree845041664B/minheadroom15.576GB. Frozenindependentcallera4c78e33, manifest00b13d36/all277pins, phase4bac0ccc/all295pins and independentreviewbda56864 matched. Nativeplan6ae017fd uses originalsourcef9f2 againstactuala910/c366, exact46cameras16walking+17outsidequalified plus13diagnostic. Root read complete69-line nativeadapter31227f3b and all304phasepins b8f36297 match. Metadata TDD8cases passed. Nativeadapter/test/config bytes are committed here before release; actualnativephase notstarted at this record. No3F publication or acceptance.

Focused1F attribution38372/start20:23:54.3841257Z exited0 at20:24:28.1019171Z after33.79s, noabort/allownedexited. Attributiona84b7a53 exactly reproduced10.52650491669533 and4.0685108629886715lostpixels; all14same lines already failagainsttheearlierE3baseline withidenticallostweights. No extraE7contributor is demonstrated. Provenance773272ec binds E3log0455/survivors4651: both original9809 and10366 were removedbykeptE3site5, a274-face removal. The old3d10 preservationPASS measured14othercandidatefaces and omittedthese2; later E7coverage candidates exposedthem. Source/settings/precision/targets match, so the earlier partialPASS did not clear these2faces. The live1F record explicitly retains this corrected baseline finding and remainsblocked; no newcandidate publication/acceptance.

New claimed enginejob MAIN-INFRA-E3-1F-RETAIN-VISIBLE-20261024 runs in isolatedcodex/main-infra-e3-1f-retain-visible-20261024 from95dad. Reuse existing committed load_replay_plan/run_checked_replay with EXPLICITrestore_sites=(5,), all283originalrecord/K1 checks, original3rolledsites preserved and freshdefaultSiteJudge/FixProfile/kernel validate_sites=True. Retaining site5 plans279selected/5446removals/10410survivors before freshdecisions only; this is not an actualoutput. No posthocOBJpatch/newvertices/guardchange. Minimal code/TDD/checkpoint/preparation only released; actualheavyphase needsreview/GO. FrozenE7attempt5draft14ada remainsheld; nooldstageindexedE7edits may be appliedtochangedbaseline.

Separate claimed independentjob MAIN-INFRA-1F-VALIDATE-RETAIN-VISIBLE-20261024 has its ownnewcheckout froma4c78e33. Reuse explicit1FE3profile, keep2F/3Fdefaults, futureactualhashesnull. Besides original-to-new strict26/native33+13/fullsigneddefaultproof, it must force default floorchecksfor9809/10366/probe422 andall14lostlines, even if candidatepreselectionomitsthem. All274site5faces mustsurviveexactly. No owneracceptance untilactualevidence andownerreview. Actual2F41648continuesitsconfirmation; ClaudeCodeowns4F-7F. Servers/database/API/foreignworkers/owneroriginals untouched.

### 2026-10-24 05:18 SGT - actual 1F corrective engine running; 2F and 3F candidates withheld

1F: code 17247d295d809a6405fae8271a4d3d290e04bb59 is frozen. Actual preparation 54296 exited zero at 21:13:06.8573867Z after 9.9265725 seconds; no resource abort, all owned processes exited. Actual preparation SHA 41fcb9a8146891da633289c57c097baba419a59fbafd068ce54951be6fdc583b verifies all 283 original E3 records, selects 279 proposals, retains all 274 faces of original site 5 and preserves the three original rollback sites. 10410 is planning arithmetic only. Root and independent reviewer rehashed all 233 execution pins. Execution config 4e2091563e767fb8b92420927d2d79921cbe4e3f33f5ccd1a603343f50d7dc28 uses unchanged 42e5/V4 admission (three fresh 8 GiB samples, own 3 GiB cap, global 3.5 GiB headroom). Actual engine replay 40476/start 21:15:39.9150019Z is running in its separate retained-visible namespace. No saved corrective output or new preservation verdict yet. Old E3 candidate link is withdrawn; original 9809/10366 visible loss remains recorded. E7 attempt 5 stays held on the changed baseline. Separate independent 1F caller now verifies the actual E3 checkpoint directly without importing the unrelated E7 engine dependency chain; its missing-import integration failure was measured before the narrower read-only implementation.

2F: actual original E3 engine 41648 saved 56828 -> 38134 triangles with 1065 kept/95 rolled-back sites, then exited zero. Controller terminal readback 1b96c772 is explicitly tool-session evidence, not a fabricated V4 terminal assertion. Exact saved source/engine tables, face material tuples and ordered lineage match. Independent strict26 worker 51584/start 21:00:34.6242438Z exited 2 at 21:03:53.765Z after 199.258 seconds, no resource abort, all owned exited. Guard 1d95e1c4 FAILED: 1,683,106 moved_other samples across 6,270,353 model pixels; holes/material/growth and other failure totals zero. No native or full signed acceptance run was started. The retained strict guard saved no images/buffers, so there is no failed QA image to claim inspected. A separate one-view diagnostic is being prepared to save the actual buffers and compare a literal identical BEFORE/BEFORE control plus bounded double-precision witness rays. Embree float32 reconstruction against original float64 planes is a hypothesis, not a cause or a waived failure. Original physical tolerance and all guard thresholds stay unchanged. Candidate is withheld.

3F: saved 53602 -> 38691. Strict26 passed, but actual native worker 23216 exited 2 after 22.821 seconds, no abort/all owned exited. Native 33d60ae7 has 119 changed qualified RGB pixels across eight views including 42 in walking view eye_3_qualified_1_probe_295. Alpha/silhouette changes are zero across all 46 views. Root and Delivery inspected the actual walking pair/diff: narrow wall-column and isolated floor differences; no unproved hole claim. All 467 native inputs rehashed. Conservative footprint worker 50760 exited zero after 11.818 seconds; footprint 63eb9d4b binds 258 currently kept whole E3 sites/6268 removed source faces, with separate 145 original rolled-back sites retained. It tests all 14911 removed faces in float64 and import float32, full pixels plus two-pixel pad, no occlusion/depth/backface pruning. It does not claim GPU primitive certainty. Full original signed diagnostic 17092/start 20:44:32.3337348Z remains alive at 21:15:17Z; base 563821 casts finished but no terminal signed verdict yet. Its failure/result will be united with native contributors before any corrective 3F policy. No 3F repair publication or acceptance.

Live status: the prior owned publisher 57300 had stopped on SSH timeout at 20:01Z, leaving a stale public feed. Manual scoped publication recovered HTTP200/current floor data at 20:50:53Z. Recovery code f3243fb retained terminal identity/schema checks and retried network failures, but its actual first launch 58240 published once then exposed a second-health-write File.Replace null conversion failure. The real D-drive RED fixture reproduced that error; narrow dcbf433 fixes it with [NullString]::Value and GREEN verifies two readable writes, original open-handle content and no temporary remainder. That helper is not yet redeployed in this record. Null output_triangles in the earlier manually withdrawn 1F status also failed the existing schema; root removed the unknown measured field and revalidated the complete document. Neither schema nor guard was loosened. Both old 2F/3F engine tracker entries are now explicitly deferred so old worker witnesses cannot overwrite independent proof states. Root remains sole canonical/live publisher. Claude Code owns 4F-7F. No server/container/database/API restart or write, original model mutation, guard/profile/target relaxation, or accepted floor.

Raw proof, terminal, preparation, execution identity and publisher failure copies are under docs/superpowers/records/MAIN-INFRA-REPAIR-PROGRESS-20261024-root, with a SHA256 manifest. No floor is accepted.

### 2026-10-24 06:30 SGT - live logs and inspection delivered; corrected1F signed validation active

Actual live delivery: source6d016409/inspection-assets01dc98c0, evidence19e4f10+f7ecd54 on owned Siege branch. Both public roots and HTTP readback matched95 static files and14 model/evidence files. API stayedbb71d3144c32e237133b4c7d995c39900508f9ab; no application/server/container restart or database mutation. Original native-failed3F output38691 and four evidence JSONs are available by explicit inspection; accepted_preview remains null, validator_passed=false, native119RGB/8viewsFAIL and all remaining problem counts retained. Real configured login200/logout204,52successful status polls, no page errors/authenticated HTTP failures; before/after material-colour edge toggles changed both actual canvases;7material groups;390px no overflow. Saved PNGs opened by root. Original prelogin401 and two operational verification-script failures are recorded honestly; final UTF8 v3 passed. Only our publisher was paused/resumed, actual44780/start22:15:19.9127718Z using unchanged1aaaf83c runtime. Public timestamps advanced after deployment.

1F: actual40476 engine exited0 at21:28:49.1646881Z (789.35s), saved15856->10410;279selected sites retained, original3rollbacks retained, all274site5faces preserved. Exact saved worker134a0dd9/sourcefef98d78/engineb7e67b8c/audit5b9d16fa/typedcheckpoint83ec67d3/retentiona1420b50. Independent frozen c2d48db caller actual13184 strict26PASS ec36e05bc42a1c446958cf054536ffac94f9222ba5118bf18e0699d62c92bca5,3924929modelpixels/allviolationtotals0. Actual23392 forcedfloorPASS b35c6c6cf4a9db281544a34ed137c9430cac0d1b051b3e6b8376e95a05ef09cb: original9809/10366 retained/all14formerlylost sightlines nowlostfalse. Native renderer64232 completed46pairs but operational adapter used3F class labels and exited1; preserved. Tested savedPNG-only finalizer27424/48ea1d40 emitted768e54ab59716ef718481eef1cca44ec61854f7286c498f14515f46cf7bbbd2a:33qualified (16walking+17outside)0changedpixels;13diagnostics separately129712changed. Root openedpaired-detailPNG: textured whitewalls/greenbands/openings/floors match; qualifieddiff panelsblack. All676receipt labels rehashed0mismatch. Full original signed/defaultValidator actual25704/start22:19:08.3391513Z is RUNNING under unchanged42e5/V4 own3GiB/global3.5GiB/fresh3x8GiB gates;632pins,afbca682 config. No signed verdict/acceptance claimed. Actual live worker/CPU observed; new preview still gated.

2F: original saved38134 retained; original26-viewFAIL1d95e1c4c03b7bd0209308690b06acfe01d95128564fdfdfaa4ca0fa652c96dc/1683106moved_other not overwritten. Bounded tiled diagnostic actual64136 completed58.609s,4d75824a receipt: view4 actual and unchanged BEFORE/BEFORE both118869moved_other, all452739 hitpairs sameoriginalfaces/equaldeptharrays; F64 geometric residual exposed float32hit quantization. Actual/control savedtriptychPNGs opened by independent agent. Completion86b95df0 rehashes147inputs/5artifacts0mismatch. Guard-specific job735d762b changes only supporting-plane distance calculation, unchanged tolerances/caps/targets; exact-rational distinctplane branch addresses independently found huge-origin cancellation. Independent builder review CLEAR;29new+68existing small testsPASS, two unchanged large fixtures remain250MiB resource-aborted. Concrete larger bounded fixture/golden configs pendingreview; no actual corrected26-view2F retry/native/signed verdict yet.

3F correction:47f58caca98a2813fedfda8dd1206defd7b2b19d restores263 whole implicated/subthresholdsites (6281originalfaces), preserves145oldrollbacks; planned1412checked proposals/44972survivors are not actual output.55focused tests/CLI/committedsmokesPASS; independent staticpreparation reviewCLEAR260pins. Actualprepare26800/start22:19:47.1557329Z exit1/noabort/allownedgone17.62s; original2F/3F producer receipt has engine_obj_sha256 but no before_sha256. Common1F loader compared correct frozen snapshot against missingfieldNone. Original input/audit untouched; narrow explicit absent-key2F/3F receipt adapter being tested, no blindretry or actualnew3F model. Old3Fnative119FAIL/fullsignedtargetsFAIL remain visible in live inspection.

Configuration measured and documented: active01 project-map; oldPhone-session-Config/workspaces.json absent; map'sSiege repo NAME stale but actual02 origin/commonGitdir is Corllenium-Siege-Planning-Dashboard.04 modelarchive has existing broadLFS/core.longpaths configuration; verified-only output policy retained.05 engineorigin correct. ExistingLFS3.7.1/globalfilters used;02 scopedpreviewOBJ/MTL/PNG attributes and checkoutlfs:true,9objects2.1MB uploaded/fsckPASS; core.longpaths enabled afteractual291charpath. Canonical02 with-env wrapper supplied configuredGitHubworkflow scope without secretcopy/print. Source/asset/evidence/publisher commits pushed on ownbranches; no merge/historyrewrite. DraftPR39 remains reviewable. Codex1F-3F/ClaudeCode4F-7F ownership unchanged.

Raw live receipts and SHA inventory: MAIN-INFRA-REPAIR-PROGRESS-20261024-root/delivery-live-20261024/. Siege render evidence and executed deployment/verification tooling: docs/handoff/main-infra-live-logs-20261024/ in the Siege worktree. No fully repaired floor or acceptance is claimed by this record.

### 2026-10-24 06:52 SGT - actual1F signed verdict and corrective3F launch

1F actual25704 terminatedexit2/noabort/allownedgone22:33:10.1508821Z/841.91s. Root re-read validation70299e1f00f324168a0488ab401f1ea167307f9754366f8d271a918c78a74829:108392texture samplesPASS, visiblecoverage/defaultfloorPASS, different-look5684->1798/same-look3347->1153/cracks2819->2378 remainFAIL(target0). Actual signedPNG count0; native140PNGinventory/33qualified0delta remainsbound768e54. Live1Fstateblocked/workerexited; independentinspect-only review4f32d479 preservesFAIL/acceptancefalse. Private10410candidate inspection53784 running under219/ca14/f2171GiB; no publicnew1Fpointeryet.

3F correctedpreparation2 actual52512 exited0/13.5s/noabort/allownedgone; Pb62f399728cd09e08cfbecc8306d61628d62d8f6aa972c8ecf26b008a4cd1f62. Independent261phase/205component/57consumedinput pins rehashed0bad. Readinessconcatenated-pathmetadata corrected innewd97a5e artifact; oldfailurepreserved. Root/IVreviewGO0d174e config. ActualcheckedE3execute60376/start22:43:56.2456960Z isrunning innewattempt2 namespace;1412proposals/6281originalfacesretained/145oldrollbacks;44972stillarithmetic. RootlivePID/CPUobserved348.34sat22:46:17; displayed38691candidate clearlylabelledpriorfailedinspection. Newpublisher job will supportcurrentcommonstate/path/run/kernel-start bindings; old1aa runtime remains untiltested/reviewedreplacement.

Guard-F64:29new+70existingguardcasesPASS aftertwoexplicit1GiBfixture runs(actual57948/34556, noabort). All3privategoldenconfigs/rootinputpins reviewed; actualgolden1CHTM5 completedexit2/noabort withold/new26-viewreports EXACTLYIDENTICAL(allfail, material5467/moved13200/edge130/grown89/holes0); this is regressionevidence, notowneracceptance. Golden2actual35048 running; golden3queuedsequential. Actual2Fretryheldpendingthesechecks. Frozen3Fcorrectionc125,1Fcallerc2 andguardc243 branches werepushed toengineorigin. Siege receiptsf7ecd54 andmainrecords7db4c44 pushed; draftPR39 updated withactualdelivery/limits; hostedCI40033695570 explicitlybilling-blockedbeforechecksstart.

Queueclaims recorded for independent2FF64validation and actualliveobservations; branchlabels corrected underexistingqueue lock. No geometry/source/guardthreshold/ownerdecision changed.

### 2026-10-24 07:36 SGT - live 1F delivered, exact LFS reproduction, 2F17 and new3F44972

1F real Before/After inspection is live: fresh15,856 versus preserved10,410, six original materials and eight actual proof links. All17 published files passed HTTP SHA readback; real configured-login browser QA measured both models/triangle-edge changes, nine worker events,29successful polls/no authenticated HTTP or page errors/no390pxoverflow. Native qualified views zero changed pixels; signed preservation passes, but problem targets1798different/1153same/2378cracks stillFAIL, acceptancefalse. Existing E7 cleanup is being adapted to this preserved base in a separate claimed job; no E7 model phase has run.

2F numerical retry actually exited37932/exit2/noabort at23:07:16.9397982Z:17moved_other pixels in four views(9/6/1/1), allhole/material/growth zero, defaulttol unchanged. Exact reporta7097da888c70c072332e83cc4ce56be4ee454036e339984f4b33c6e1aea2462. Native/fullsigned stopped. A separate claimed bounded diagnostic is being built; no waiver or floor acceptance.

Corrective3F E3 actually exited60376/exit0/noabort at23:06:54.7080520Z, saved44,972source+engine triangles/1412kept/0freshrollback. All6281protected original faces and old145rollbackcohort survive exact typed lineage; root separately counted both savedOBJf-records. Independentc553 profile129testsPASS, root+Delivery rehashed388strict26pins0mismatch, actualoutputabsent. RootGO issued onlyfor fresh strict26/default900x600 under existing8GiB/3GiB/3.5GiB gates. Native/fullsigned require separate actualreadback/GO; existing3Fpublic38,691failedinspection is not evidence for44972.

Live observere1e9575/actual53812 is installed; twice-read public statuses show1F10410inspection/2F17FAIL/new3F44972saved/exitedworkers. Completed60376registration retired after two receipts; no server/API/container restart or liveDBwrite; API remainsbb71d3144c32e237133b4c7d995c39900508f9ab. Floors4-7remainClaudeCode-owned and mirrored only.

ConfiguredGit/LFS used: actualfilteredHEAD3739d11 reproduces all31public payload hashes,19LFSpaths/13uniqueobjects/zero mismatches. Scoped JSON -text preserves signed exactbytes; freshZ/master/04verified-output folders untouched. New1Fliveproofs/screenshots/receipts pushed toSiege2e2fb05 onexistingconfiguredbranch, PR39draftunmerged. HostedCIneverstarted due accountpayment/spendinglimit; noCIpass claimed. Priorguardpush auto-reviewblock was resolved after newexactpublicorigin/admin/credentialfreepayloadtrust evidence, actualb56d9ea pushsucceeded.

Evidence: delivery-update-20261024-0736/SHA256.json pins nine actual receipts/reports; 1Flive screenshots live in Siege docs/handoff/main-infra-live-logs-20261024/evidence-1f-retained/. Three newclaimedjobs are recorded with actualcodexbranchlabels. No model acceptance.


### 2026-10-24 07:38 SGT - corrected3F actual strict26 PASS

Actual55272/creation23:31:55.8455340Z terminatedexit0/noabort/allgone23:32:19.5522209Z/23.78s. New44972guard7f987622766e2c3402d2c03e68468137ed137fc3614cdc5a6d61129a6125ac2c measures26x900x600/4717188modelpixels/allhole,movement,material,growthviolations0/existingtie3. Fullactual1412kept/0freshrollback,263retainedsites6281faces and145oldrollbacksites7818faces survived exact original lineage;500receiptlabels0mismatch. This is newc553/e92/Pb62 candidateproof, not old38691. Native46plan metadata preparing; no actualnative/fullsigned/package hasrun. Livecanonical updated with actualguardPASS and explicitpendingnewnative/signednull; old38691validation moved to previous_inspection_validation, currentinspectionstilllabelledolderfailed38691. Acceptance remainsfalse.
