# UC Repair Engine — design (spec)

**Status:** approved by the owner on 2026-10-03 (plan mode, after 11 decisions recorded below). **Supersedes nothing**: it is the phase after the 3D error filter (`2026-09-26-3d-error-filter-design.md`); the project design is `2026-09-21-uc-model-fixer-design.md`.

## Context

**Phase 1 (identification) is done and live.**
- `engine/detectors/errors.py::find_errors` finds 7 error kinds plus a facade layer.
- The dashboard draws them in 3D, and the Errors page documents each kind.
- Proven on CHTM 5th floor: 20,599 triangles; flicker 5,668 + 4,793; hidden 12,870; cracks 3,884; open
  edges 346; reversed 29; zero-area 1,055.

**The owner now wants a real repair engine:**
- one engine per error kind;
- run over every floor of every building of CHECKPOINT-17;
- hardened by agents, skills and workflows;
- an agent that validates each floor by the owner's rule;
- a comparison SketchUp file per building, with the floors side by side, like the owner's EDS file;
- Hermes (the owner's Gemini agent) able to take and execute jobs from the same foundation, with Claude
  reviewing everything.

## Decisions made with the owner (2026-10-03)

| Topic | Decision |
|---|---|
| Scope | **Every building**: BRS, CHTM, EDS, GYMNASIUM, MAIN, MAIN INFRASTRUCTURE, PE, SCIENCE A, ARCHITECTURE, plus the site pieces. Work runs **per floor or element**; the campus is never one job (blocked operation) |
| Source | The CHECKPOINT-17 model, which the owner has already checked. The **backup** in `MODEL FIXER ENGINE FILES\02-SKETCHUP-MODELS\CHECKPOINT-17-BACKUP\` is the source of truth (read only). The master in `D:\PROJECTS\UC\02-SKETCHUP\current\` is never touched |
| Reference for "visible" | CHECKPOINT-17 itself, before against after. The Minecraft export is old (owner): not a reference |
| **Owner's validation rule** | A floor passes only if: **(1)** every facade texture is still there; **(2)** the problems are solved; **(3)** nothing visible to the eye was deleted or covered. A Validator tool plus an independent agent checks this; then the owner confirms the floor |
| Visible rule | **Strict.** Nothing that can be seen is deleted or covered. Visible debris stays and is listed with a picture. A rebuilt side may cover only faces that are 0 % visible (today's cap is 10 %) |
| Viewpoints | **Outside, and inside: players walk the floors.** A face is removable only if no outside view and no eye-height view inside any floor can see it |
| Unity | Draws **both sides** of every face (`CampusDoubleSided.cs`, `_Cull = 0`), so back-to-back faces flicker |
| Back-to-back pairs | **Keep the side facing a viewer** (outside or walkable space) and remove the inward copy. Where both sides are seen with different looks, the owner decides |
| Flicker, different materials | Cutting the loser along the winner's border is **allowed**: a named exception to "only solidify adds points". Winner by rule; ties go to the owner |
| Holes | **Narrow flat fill allowed**: a planar border that matches the neighbouring plane, existing points only, shown in the review. Anything else goes to the "needs modelling" queue, with a SketchUp helper |
| Floors | Fixed **separately** (Unity shows them floor by floor). The floors above and below are loaded read-only as context |
| Comparison | Per building, one `.skp` with **2 rows**: CHECKPOINT-17, then engine-fixed. The floors sit side by side with labels |
| Outputs | `MODEL FIXER ENGINE FILES\05-FIXING\<BUILDING>\` (the comparison `.skp`) and `\<Lnn>\` per floor. Only results from committed code go there |
| Review | **Per floor**: accept or reject, plus "this spot is wrong" marks |
| ML | Rules first; learns from the owner's verdicts; never bypasses rules |
| Hermes | **Owner-started sessions**: "Read HERMES.md and do the next job". Claude lays the foundation and reviews; Hermes executes; only Claude merges. Automatic takeover comes later (P5) |
| External tools | **DREX and TypeSafe are not used.** Both are small decision and scoring models for finance and ops, with no geometry or code; our gates are deterministic and measured |

## Measured facts (2026-10-03, read only)

- **The CHECKPOINT-17 export** (`…\UC ENVIRONMENT BUILDING\…\CKPT17\`, made from this model on 09-26
  between two saves, read only through the snapshot importer):
  - 85 split OBJ files, **1,766,906 triangles**, in inches with Z up;
  - `CKPT17-CLEAN.obj` carries the **full group path on each `g` line** (up to 19 levels deep);
  - 391 materials, but only **86 distinct texture images** (351 of 379 textured materials share an image).
- **Floors:**
  - Names are unreliable: `BRS_9th_floor_obj1` is really L08; there are `_obj1` duplicates (Science A
    plan 2/3 are about 90 % shared, BRS 4th/5th are 27-40 % shared).
  - Some groups hold several floors: `MAIN_BUILDING` (2 floors), `Main_Infrustructure_Building` (7
    floors, 142 k triangles).
  - SCIENCE A has no L01.
  - Floor heights differ by building, and 28 of the 69 single-floor files are not 5 m tall.
- **Engine today:** proven on two 5-7 k-triangle sidewalk files plus one CHTM 5th floor test run (20,599 →
  7,428, passed). It fixes holes (slab sides and bottoms only), hidden faces, zero-area triangles, debris,
  reversed faces, same-material flicker, gridlines and cracks. **Different-material flicker and general
  holes are not built.**
- **Hotspots:**
  - `find_t_vertices` (`topo/adjacency.py:85`) compares every edge with every vertex;
  - `analyse_topology` runs 4-5 times per fix;
  - `double_layers` compares every pair of faces;
  - the guard is fixed at 900×600 (2.7-3.4 in per pixel on floors).
  - CHTM 5th `find_errors`: 40.8 s alone, 666 s under load.
- **SketchUp:** the SketchUp 2026 C SDK through ctypes works headless (`engine/io/skp_writer.py`;
  `build_eds.py`). Labels are pixel-font geometry (`pixfont.py`).
- **Hermes:**
  - Nous Research Hermes Agent (CLI and desktop), on `gemini-3.8-flash`;
  - `delegate_task` runs sub-agents (a one-shot run may have only 2);
  - `tools/auto_continue.py` exists (34 tests, never ran a real job, off).
  - Past lesson: Hermes's brief-07 work shipped a hole marked "passed", which review caught.

## Architecture

### 1. Source and inventory (P0a)
- **Source freeze:**
  - snapshot all 85 split OBJ files with `engine/io/snapshot.py::snapshot_object` (manifest check);
  - build a face → group-path index from `CKPT17-CLEAN.obj`;
  - write `source.json` with the sha256 of the export, MTL, textures, `.skp` and `.skb`.

  This keeps the export's print step, which every tolerance (`guard_depth_tol`, `sliver_width_bound`)
  depends on.
- **Export-vs-backup check:**
  - read-only, through the SDK, on sha256-verified copies of the backup;
  - per named group, compare the transform, bounding box and face area with the export;
  - a full SDK extraction happens only as the fallback for groups that don't match.
- **Inventory:**
  - a level table per building, from the heights with the most upward-facing slab area;
  - faces assigned by group path first, and split by level only where the paths can't separate floors
    (by face centre; triangles are never cut);
  - stairs, shells, roofs and bridges become separate **element** units;
  - duplicates are found by geometry.
- **`campus_map.json`**, which the owner confirms, holds per unit:
  - building, `Lnn`, type;
  - member group paths and their sha256, triangle count, base, top and slab heights;
  - read-only neighbour units;
  - the duplicate decision, misnamed and missing levels;
  - `confirmed_by_owner`.
- **`materials.json`:** a **look key** = texture sha256 + Kd + d. Every visual comparison uses it, never
  `usemtl` numbers.

### 2. Census (P0a)
- `engine.cli census` runs `find_errors` per unit and records:
  - the time and peak memory of each stage, plus the machine load;
  - flicker split by look and by winding.
- Output: `data/campus/census.json`, the baseline for "problems solved" and for the speed budget.

### 3. Validator, before any engine (P0b)
`engine/validate/` is its own module, float64, and not built on `compare_views`, so it is independent in
code as well as in agent. `engine.cli validate <unit>` writes `validation.json` and evidence crops.

| Check | How |
|---|---|
| **1. Textures there** | At least 4 area-weighted samples on every BEFORE face visible from a viewpoint. In AFTER, each must hit a surface within the depth tolerance with the **same look key and UV** (UV from barycentric weights at the hit; mod 1 only where the texture repeats) |
| **2. Problems solved** | `find_errors` BEFORE against AFTER, per kind, against numeric targets that the owner signs before P2. Every residual is listed with its location |
| **3. Nothing visible deleted or covered** | Same sampling, plus 1,024 or more ray directions on every removed or covered face, plus an object check (every visible group still present). The only allowed change is at E5 z-fight sites, where AFTER equals one of the BEFORE candidates (a named, measured guard class, test-first) |

- **Viewpoints:**
  - outside: 128 directions plus a ring of pedestrian-height perspective cameras;
  - **inside: eye-height probes** (1.6 m above every walkable upward surface with headroom, on a grid),
    with rays in all directions.
- **Building-level report:** coincident slabs between floors (for example EDS L01 top against L02 bottom).
- **`floor-validator` agent:** runs the tool, reads the evidence crops, writes PASS or FAIL with reasons.
  Never the builder; never edits.
- **Proof:** mutation tests (a deleted visible face, a dropped texture, a 0.5 UV shift, a flipped face, a
  covered visible face, a removed room wall) must each FAIL. It is then run on `data/out_chtm5` and on
  sidewalks A and B.

### 4. Repair kernel and engines (P1-P2)
- **Kernel v1 is observe-only.**
  - It wraps today's stages and keeps an **edit log**: one face fingerprint per face = its vertices snapped
    to the print step + its look key.
  - Accepted only when `report.json` is byte-identical to today's on A, B and CHTM 5th.
  - Then sites, apply, and rollback by bisection on a Validator failure.

| Engine | Fixes | Algorithm | Reuses | Limits (owner rules) |
|---|---|---|---|---|
| E1 loose | zero-area, debris | degenerate removal; components through T-junctions and contact; ray-confirmed | `fragments.py`, `folds.py`, `piece_rays` | **only invisible debris**; visible debris is listed |
| E2 reversed | inward-facing fronts | flip when back exposure > front; sheet consistency; ray-parity second opinion | `orient.py` | thin faces are never flipped alone |
| E3 hidden | inside solid parts | unseen from **outside and from interior probes**, floor alone; winding-number second opinion only where they disagree | `vis/exposure.py`, `remove.py`, `guard_feedback` | never side meshes; never room surfaces |
| E4 flicker, same look | duplicate layers | ≥ 99 % covered removal; coincident pairs (brief 13); one wall per side plane (brief 15) | `overlap.py`, `feat/coincident-pairs`, `wip/brief15-one-wall` (review and finish) | strict guard; tinted materials with the same look join only if the owner agrees |
| E5 flicker, different look | same-plane overlaps, **both windings** | **Opposite pairs:** keep the side facing a viewer and remove the inward copy. **Same-facing pairs:** (a) a patch inside a bigger face of the same source group wins; (b) else the look and UV that continue the plane's neighbours win; (c) else the owner decides. The loser is cut along the winner's border | `overlap.region_frame`, `overlapping_polygon_pairs`; shapely difference; `constrained_delaunay_triangles` (`merge.py:1061`); `_region_uvs`, `fit_uv` | new points only on the winner's border, snapped before E6 |
| E6 cracks | T-junctions | thread T-vertices into the long edges | `merge.py` (T1) | also fixes the `classify_edges` bug (`topo/edges.py:80-87`) with A/B proof |
| E7 gridlines | excess triangles | region merge to a fixed point | `merge.py` | area never grows |
| E8 holes | slab sides and bottoms; flat holes | solidify (cover only 0 %-visible faces); **narrow flat fill** | `solidify.py` | the flat fill is an owner exception to "hole fill blocked" and "area never grows"; complex holes go to the modelling queue |

- **Order:** E8 solidify → E3 → E1 → E2 → E4 → E5 → E6 + E7 (merge) → E8 flat fills → validate.
- **Invariant changes, each named, measured and test-first:**
  - `material_count_same` becomes "**no visible look lost**";
  - area growth is allowed only at E8 flat-fill sites;
  - the E5 z-fight class.
- **Hardening, the exit criteria per engine:**
  - fixtures and mutation tests;
  - deterministic reruns;
  - time and memory budgets;
  - kill-and-resume;
  - golden units (CHTM 5th plus 3 diverse ones);
  - **every spot the owner marks wrong becomes a test fixture.**

### 5. Speed (P1, measured first)
- Units after the split are at most 60-92 k triangles: set the budget on those, from the census timings.
- Planned fixes:
  - a spatial hash for T-junction search;
  - one `analyse_topology` per stage;
  - `double_layers` grouped by plane, with a chunked pixel stage.
- Keep 900×600 inside the engines. The Validator renders fine tiles only around edit sites.
- Parallel units:
  - OMP, MKL and OpenBLAS threads set to 1;
  - about 4 workers, the lower of 14 and 31 GB divided by the measured peak memory;
  - machine load recorded with every timing.

### 6. Runner, outputs, comparison (P3)
- `engine.cli repair-unit | repair-building`: a resumable queue of unit jobs. There is no campus command.
- Work in progress goes to `data/fixing_scratch/`.
- **The owner's `05-FIXING\` holds committed-code results only.** They are published from
  `.claude/worktrees/verified` (created then), with a per-floor `manifest.json` giving the commit and the
  hashes.
  - Per floor: fixed.obj/.mtl/tex (campus coordinates, inches, Z up, the Unity importer contract),
    fixed.skp, report.json, validation.json, evidence\.
- **Comparison** (`engine/campus/comparison.py`, with `pixfont.py` moved into the repo with tests):
  - row 1 is CHECKPOINT-17 with its raw exported edges; row 2 is engine-fixed; both are built from OBJ
    through the same writer;
  - column pitch = the widest floor + 8 m; colour plates; labels `L05 5TH FLOOR`; headers;
  - it never opens the master, and refuses outputs inside the backup or master folders;
  - checked by a top-down render (`records/scripts/render_skp.py`).

### 7. Review and learning (P4)
- **Campus page:** building × unit grid with census counts, fixed counts, the Validator verdict and the owner
  verdict.
- **Floor review:** BEFORE and AFTER 3D, evidence crops, residuals, the modelling queue; accept or reject;
  spot marks.
- Writing to the live database (fixed versions, review tables) needs the owner's OK at that time.
- **Risk score:** a transparent score first. A classifier (scikit-learn gradient boosting) comes only after
  200 or more labelled sites, at least 30 of them rejects. It orders the review and never applies anything.

### 8. Agents, skills, Hermes handover (P0c)
- **One rules source:** `AGENTS.md` at the repo root holds the HANDOFF §4 rules, the blocked operations and
  every owner decision above. `CLAUDE.md` imports it; HANDOFF and `HERMES.md` link to it.
- **Skills** (`.claude/skills/<name>/SKILL.md`, plain markdown that Hermes can read too):
  - `uc-repair-rules`, `uc-engine-contract`;
  - `uc-run-unit`;
  - `uc-validate-floor` (the workflow claim → snapshot → repair → validate → evidence → review → publish);
  - `uc-comparison-skp`, `uc-handoff`.
- **Sub-agents** (`.claude/agents/*.md`):

  | Agent | Model | Job |
  |---|---|---|
  | engine-builder | sonnet | TDD in its own worktree |
  | unit-runner | haiku | runs the CLI only |
  | floor-validator | sonnet | independent, read-only |
  | skp-builder | sonnet | the comparison file |
  | rules-reviewer | sonnet; opus for the final review | reviews |
  | hermes-reviewer | sonnet | every Hermes branch |
  | census-analyst | haiku | the census |

- **Owner-started Hermes session:** "Read HERMES.md and do the next job".
  - `HERMES.md` becomes the entry point:
    1. read `AGENTS.md`;
    2. `python tools/jobs.py next --for hermes` claims the first `ready` job marked `hermes-ok` whose
       dependencies are merged (file-locked, so no clash with Claude);
    3. work in `.hermes/worktrees/<job>` on `hermes/<job>`, item by item, each with a "done when" and
       named tests;
    4. paste the acceptance commands' output into `docs/superpowers/records/hermes/<job>-report.md`;
    5. `tools/jobs.py done <job>` sets it to "awaiting Claude review".
  - **The queue:** `data/jobs/queue.json`, with `QUEUE.md` generated from it: id, brief, type, who may
    take it, depends-on, status.
  - **Briefs** follow one template. For build jobs **Claude writes the failing tests first**.
  - **Hermes rules:**
    - write to scratch only;
    - `delegate_task` children are read-only;
    - a change to `engine/guard/**`, `FixProfile` thresholds or existing tests is rejected automatically;
    - never merge, never touch the live database or containers, never use a blocked operation.
  - **Claude reviews every Hermes branch:** `hermes-reviewer` plus a controller check, then merge or a fix
    brief back into the queue.
- **Automatic takeover at Claude's limit** (P5, with the owner's OK):
  - `tools/auto_continue.py` moves to the same queue, with heartbeats so a long run isn't mistaken for a
    stall;
  - one run at a time until P5 proves two are safe;
  - job templates for unit snapshots;
  - a Windows scheduled task.

## Phases
Each phase gets its own spec, its own plan, subagent-driven execution, reviews and records.

| Phase | Delivers | Proof |
|---|---|---|
| **P0a Source + inventory** | source freeze, the SDK cross-check, draft `campus_map.json`, `materials.json`, census with timings | every unit listed; triangle counts equal `_MANIFEST.txt`; census table; **owner decision sheet**: levels, duplicates, tint looks, check-2 targets |
| **P0b Validator v0** | checks 1-3 with interior probes, the agent | mutation tests all FAIL as they should; verdicts on CHTM 5th, A and B |
| **P0c Agents + Hermes handover** | `AGENTS.md`, `CLAUDE.md`, skills, agents, `HERMES.md`, `tools/jobs.py`, `QUEUE.md`, the brief template; worktree hygiene (prune, `verified`) | **an owner-started Hermes session takes a real `hermes-ok` P0 job, delivers a tested branch, and Claude reviews and merges it**; Hermes loads the skills |
| **P1 Kernel v1 + speed** | observe-only kernel with the edit log; the measured hotspots fixed | byte-identical reports on A, B and CHTM 5th; the largest units within budget |
| **P2 Engines** | E1-E8 under the strict rules (new: E5, interior-aware E3, flat fill) | per-engine exit criteria; the Validator passes on golden units |
| **P3 Run + outputs** | building by building (order from the census, the owner may reorder); `05-FIXING`; comparison `.skp` | Validator PASS per floor; comparison renders; the owner's confirmations |
| **P4 Review + ML** | Campus page, floor review, edit log, risk score, then the classifier | rejected sites ranked high on held-out floors |
| **P5 Hermes automatic** | queue-based takeover, scheduled task, heartbeats | one real takeover reviewed and merged |

## Verification
- **Every engine change:** the full engine suite stays green, the mutation tests FAIL as they should, and
  golden units pass the Validator.
- **Every floor:** all 3 Validator checks PASS with evidence crops, from outside and inside; the owner
  confirms.
- **Every building:** the comparison `.skp` opens; its render shows 2 rows × N units with labels, matching
  the inventory.
- **Hermes:** each branch is reviewed with its test output before merge.

## First steps after approval
1. Save this design as `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md` and commit it.
2. Use writing-plans to write the P0 plan (P0a, P0b, P0c), marking each task Claude-only, Hermes-ok or
   either.
3. Execute P0a subagent-driven. Prepare P0c early so the owner can start Hermes on the first `hermes-ok`
   jobs.
