# Fresh MAIN INFRA cleanup and visible progress

Status: design for owner review; no fresh floor is repaired or accepted by this document.

## Owner decisions

Source: `Z:\PC-4-STORAGE\UC MODELS\UPDATED MINECRAFT MODEL\MAIN INFRUSTRUCTURE`.
The owner identifies this as the fresh Minecraft export and has already cut all
seven floors. Clean with the repair engine without damaging facades or losing
visible triangles. Use this source in the Corllenium planning dashboard and show
specific progress. Delete obsolete MAIN INFRA plans/jobs and failed outputs.
Owner-confirmed October 23 scale: **1 Minecraft block = 1 metre**.

These decisions supersede old source/scale assumptions for this MAIN INFRA version
only. AGENTS.md sections 3-6 remain binding. Deletion is already authorized.
Deployment, restarts, live database writes and model acceptance retain their own gates.

## Measured starting point

- Source inventory this turn: 36 files, consisting of 7 OBJ, 7 MTL and 22 PNG.
  OBJ filenames are `1st` through `7th floor main infra.obj` with ordinary ordinals.
- Prior sandbox: `.worktrees/sandbox-20261023_111513_882c99`. It records zero
  candidates. Keep its frozen raw data, tests/code and diagnostics for review/reuse.
- Its importer refused 1F line 10224 and 4F line 36210. Saved nonplanarity distances
  are 4.98e-8 and 3.16e-7 source units against a 1.42e-14 arithmetic allowance.
  These numbers do not establish damage or justify loosening any repair guard.
- Reuse reviewed sandbox modules `engine/io/minecraft_floor.py`,
  `engine/fixes/precut_cleanup.py`, `tools/repair_fresh_main_infra.py` and tests.
- Three old reports explicitly have `guard.passed=false`: V2 1F, V2 6F and earlier
  6F. Their six OBJ variants qualify for deletion. Do not classify other outputs
  with `passed=true` as failed merely because they are old.
- Correct dashboard: repository 02 `D:/PROJECTS/02-Corllenium-Siege`, revision
  `8866be7` at inspection, Next.js/React/Three.js/Hono/Postgres. The fixer dashboard
  on port 5190 is separate. Old `building-repair-status.json` claims all 78 units
  complete, while `BuildingPipelineView.tsx` overlays legacy `completedUnits`.
- The same view has `handleRunSimulatedEngineFix` (line 416), which invents reduced
  triangle/error/validation results, and `handleApproveAndPush` (line 532), which
  assigns approval and a hardcoded commit. These must not act on fresh MAIN INFRA.

## Repair contract

1. Freeze the complete package through `engine.io.snapshot.copy_verified`.
   Never repair Z: originals. Reuse prior raw only after complete hash equality.
2. Preserve the owner's floor cuts, openings, stairs, facade outlines, actual
   corners, materials, normals, UVs and visible coverage. No recutting, custom
   7F/shared 6F hall replacement, SHIELD_FRONTAGE addition or guessed floor stacking.
3. Establish source-to-block mapping/up-axis, then record invertible engine frame,
   inverse and determinant. Physical scale is 1 metre/block = 1000/25.4 inches/block.
   Engine input uses inches; display output uses its explicit source frame. Verify
   round trip and prevent double scaling. Source-local floor origins stay intact.
4. Qualify tessellation against raw source rendered using the same recorded
   importer/version/settings. Keep actual 3D corners and polygon/corner provenance.
   No flattening, dropping polygons, welding or moving corners. Concave, nonplanar,
   bow-tie and degenerate polygons need tests. A materially ambiguous diagonal or
   unsupported polygon blocks its floor with the exact record and evidence.
5. Start with exact same-direction duplicates only if look/UV/normals/coverage
   are equivalent. Hidden-face and coplanar cleanup require separate tests and
   existing guards per pass. Excluded stages never execute; refusal restores the
   last passing state. Triangle reduction is not an acceptance target.
6. No fill, solidify, remesh, decimate, tolerance weld, guessed orientation change
   or material substitution in this first route. Opposite-facing sheets are not
   generic duplicates. Visible debris stays; missing source surfaces are review items.
7. Run 1F, independently qualify 4F, then 2F/3F/5F/6F/7F sequentially only after both
   pilots pass. One geometry worker avoids previous shared memory allocation failures.
8. A different agent runs the existing independent Validator with fresh-source
   look/UV samples and owner-signed error targets. Unsigned targets block acceptance.
   Keep existing 0.02 inch/pixel and more-than-4-pixel failure rule per viewpoint,
   guards and thresholds. Inspect external at/above-horizon, pedestrian and interior
   eye-height views from both sides, plus cut-floor, stair and facade crops.
9. Evidence: source/candidate hashes, stage audit, edit log, validation.json,
   before/after/diff images, reviewer identity and owner verdict. Read OBJ/MTL/assets
   back. A 26-view guard alone is insufficient. If SKP is produced, render/edge-audit
   it; otherwise explicitly report no SKP. Accepted deliverables use committed code
   and the existing verified publishing workflow.

## Planning dashboard contract

Reuse the existing MAIN INFRA floor view and comparison canvas with its current
visual identity. No new dashboard/service/database. Show seven rows with floor,
step, state, last actual work event/time, blocker/next action and evidence links.
States: queued, importing, cleaning, validating, blocked, needs_review, accepted,
failed, cancelled. Use text as well as colour, keyboard access and narrow layouts.

Show source revision and `Fresh Minecraft export`, 1 metre/block, heartbeat and
current task. Source preview says `Fresh source - not cleaned` and is enabled only
after import equivalence. Candidate is labelled candidate until independent
validation and owner acceptance. Missing assets/outputs show a specific error.

Version every event/preview/result by building/source revision/floor/run ID. Ignore
legacy MAIN INFRA completedUnits and cancelled-run late events without matching
provenance. A source change invalidates old acceptance. Other buildings keep their
state. Source/candidate/accepted references are separate; accepted adoption is
atomic with rollback. Package revisioned OBJ/MTL/textures using existing preview
publishing: browsers cannot read Z: paths. No invented percent, ETA or completion.

For fresh MAIN INFRA, replace the simulated engine and approve/push controls with
read-only evidence, current worker state and the persisted verified owner verdict.
No click or imported model can manufacture a Validator pass, published commit or
acceptance. If the existing review workflow cannot supply a persisted owner decision,
acceptance stays blocked; do not invent a new approval backend for this first slice.

Write progress atomically after real steps; heartbeat every 10 seconds while running;
poll every 5 seconds. After 90 seconds without heartbeat show `No recent worker update`
and the last work event. Heartbeat alone never proves work progressed.

## Ownership and order

Repository 05 owns geometry/validation/canonical progress; 04 receives accepted
packages; 02 owns preview/status integration. No Unity adoption or messaging implied.
Order: retire obsolete work; expose truthful progress; qualify import; run pilots
and remaining floors; prepare accepted package/display adoption and deploy candidate.

Status must show queued/importing/blocked even before import succeeds. Until the
package is frozen, source_revision is null with an explicit not-frozen state;
model preview and acceptance remain disabled. Assign a manifest revision after freeze.

Remaining technical gates: exporter axis/unit mapping, lossless tessellation,
fresh-source signed error targets and placement evidence for any assembled view.
Investigate files first. Source, cuts, deletion scope and block scale are settled.
