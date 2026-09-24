# Guard round — 2026-09-23 (R2d, M4, M5, R2b, R2c, M0 + extension, R1a)

Branch `feat-dashboard`. Seven items, one commit each, test-first throughout (failing test written
and run first, implementation second). Only files under `engine/` were edited, plus this report.
Untracked files were never touched; `git status` shows the same 13 untracked entries it did at the
start. The running servers (8190, 5190, 5180) were not stopped or restarted.

Baseline before any change: **172 passed**. After all seven: **190 passed**.

| # | commit | item |
|---|--------|------|
| 1 | `dd2b5ef` | R2d `fix(engine): only a failing base class is ever promoted` |
| 2 | `21a3434` | M4 `fix(engine): z-fight ties are not damage` |
| 3 | `675b83c` | M5 `fix(engine): a closed crack is an improvement, not damage` |
| 4 | `675235f` | R2b `fix(engine): the ring test cannot be skipped silently` |
| 5 | `53d5387` | R2c `test(engine): ring tests say what they test` |
| 6 | `93b1907` | M0 `fix(engine): a rolled-back merge keeps the guard report that failed` |
| 7 | `a29688e` | R1a `fix(engine): thin sheets are never flipped` |

---

## 1. R2d — only a failing base class is ever promoted (`dd2b5ef`)

`_classify` decided its promotion candidates with a fixed set — hole, material_changed,
moved_same_flat, moved_other — regardless of strictness. Under `strict=False` a `moved_same_flat`
pixel is *tolerated*, but promoting it to `edge_flicker` moved it into a class that **is** capped,
so a non-strict run could fail on pixels it had already decided not to mind. E4 measured it: 15 of
991 tolerated pixels re-classed as flicker, against a 1e-4 cap allowing 0.93 px in a 9,291 px view.

New `_failing_base(codes, strict)` is the single definition of "fails under the current
strictness" — deliberately the same rule `_fail_mask` applies to the final codes, minus the
promoted classes themselves. `classify_pixels` and `_classify` gained a keyword-only
`strict: bool = False`; `compare_views` forwards its own `strict`.

**Tests.** `test_a_tolerated_moved_same_flat_pixel_is_never_promoted_to_flicker` runs the same
sub-tolerance boundary shift at an internal silhouette both ways: `strict=True` gives 1
`edge_flicker` and fails at cap 0.0; `strict=False` gives 0 flicker, 1 `moved_same_flat`, and
passes at cap 0.0. `test_a_failing_base_class_is_still_promoted_when_not_strict` pins that the gate
is the base class's own verdict and not strictness itself — `material_changed` fails either way,
so a material boundary under tolerance is still rescued in a non-strict report.

First test failed at `assert tolerant.totals["edge_flicker"] == 0` → `assert 1 == 0`, then passed.
Suite after: 174.

---

## 2. M4 — z-fight ties are not damage (`21a3434`)

### The measurement that changed the implementation

The brief prescribes `EmbreeCaster.all_hits` via trimesh's
`intersects_location(multiple_hits=True)`. **That cannot work on the data it was written for**, and
I verified it before building on it:

* trimesh's multi-hit walks the ray forward, advancing the origin past each hit by
  `max(1e-8, mesh.scale * 1e-6)`. Two triangles at *identical* `t` can therefore never both be
  reported — the second is behind the advanced origin whatever the offset is.
* File B's pair is exactly that. Faces 2654 and 73 are both in the plane `y = 767.05`, share an
  edge, overlap, and carry materials 1 and 0:

  ```
  face 2654 (mat 1): (-408.58, 767.05, 156.96) (-369.21, 767.05, 147.64) (-408.58, 767.05, 147.64)
  face 73   (mat 0): (-408.58, 767.05, 147.64) (-369.21, 767.05, 151.78) (-408.58, 767.05, 156.96)
  distance of every vertex of each to the other's plane: 0.0
  ```
* Cast against exactly that geometry, `intersects_location(..., multiple_hits=True)` returns **one**
  triangle. BEFORE's tie set would have had a single member and the tie test could never have fired.

So `EmbreeCaster.all_hits` is two passes: trimesh's multi-hit for the general several-surfaces case,
then an analytic **recovery** of the hits the walk skips. Each reported hit point is re-tested
against the other triangles that **share a vertex** with the triangle embree returned, and any that
contains it (within `_coincident_tol` of its plane and of its three edges) is reported at the same
`t`. A vertex→faces table is built lazily on the first `all_hits` call, so a plain render pays
nothing. `_COINCIDENT_REL_TOL = 1e-6` of the bounding-box diagonal is exactly the width of the band
embree steps over, and thousands of times smaller than `depth_tol`.

**Documented limit** (on the method): a coincident triangle sharing *no* vertex with the one embree
returned is still missed. Overlapping faces in a SketchUp export come from one face loop and do
share vertices, but a pair welded from two independently drawn loops need not. The tie test then
sees a one-member tie set and reports the pixel under its real class — the safe direction: a missed
tie is a reported failure, never a tolerated change.

`BruteCaster.all_hits` needs no recovery: the analytic test has no walk, so two triangles
overlapping in one plane both satisfy it at the same `t`. It is the oracle for the embree path.

### The pixel class

`PX_ZFIGHT_TIE = 6`. For a failing-base pixel, `_tie_probe` re-casts its own centre ray with
`all_hits` against both geometries; `_matches_tie_set` then asks, in both directions, whether the
other render's centre hit matches a member of this render's tie set (the surfaces within
`depth_tol` of its own first hit) — same material, hit point within `depth_tol` of that member's
plane. Both directions are required, so a *removed* member still fails. Evaluated before the ring
test. Never a failure at any cap; `totals` and `ViewVerdict` gain `zfight_tie`.

**Tests.** Two exactly coincident quads of different materials, AFTER = the same geometry with the
face order reversed so the winner flips (the test asserts the flip really happened, or the fixture
would be vacuous): every model pixel is `zfight_tie`, `material_changed` 0, passed at every cap.
AFTER with the winning quad removed: `zfight_tie` 0, `material_changed` on every model pixel,
failed. A same-material coincident pair losing a member: every total zero — the tie machinery is
not even needed. Plus four caster tests, including the file-B pair verbatim
(`test_all_hits_reports_both_faces_of_an_exactly_coincident_overlap`) and a brute-oracle agreement
test on 500 random rays.

Two caster-test assumptions of mine were wrong and I fixed the tests, not the code: a ray down the
exact centre of the cube's top quad grazes the shared diagonal and legitimately meets four
surfaces, and the random-ray fixture produces ~413 hits over 500 rays, not >500.

**Real data, measured immediately after this commit:** file B `guard_after_removal` went from 11
`material_changed` + 1 `edge_flicker` (failed) to **0 failures with 12 `zfight_tie`** — the exact
12 pixels of the diagnosis — and its merge stopped rolling back. Suite after: 181.

---

## 3. M5 — a closed crack is an improvement, not damage (`675b83c`)

`PX_CRACK_CLOSED = 7`, evaluated after the tie test and before the ring test, on the **same 16 ring
rays** — one ring cast now answers two questions, so this costs no extra rays. A failing pixel whose
BEFORE ring rays reproduce AFTER's *centre* verdict at least `_CRACK_RING_MIN = 12` times out of 16
is `PX_CRACK_CLOSED`: BEFORE's centre ray, and only it, went somewhere its whole neighbourhood did
not. Never a failure at any cap; `totals` and `ViewVerdict` gain `crack_closed`, a positive metric.

`_ring_reproduces` was split: `_ring_matches` returns the whole `(P, R)` boolean matrix, and
`_ring_reproduces` is now `.any(axis=1)` of it. The flicker test asks whether *any* ray reproduces;
the crack test asks *how many* do.

**The limit is documented on `classify_pixels`**: damage narrower than the ring radius (`depth_tol`)
is indistinguishable from a closed crack. A genuinely lost sliver thinner than that, with intact
surface on both sides of it, reads as a crack the fix closed. The ring radius is the merge's own
working tolerance, so this is the same bound everything else here is judged at.

**Tests.** A slab of two big triangles split by a 0.02 in crack over a lower surface 10 in behind,
with the crack aimed through a chosen pixel's own ray. AFTER = the slab re-triangulated as one quad
with no crack: `crack_closed` on every gap pixel, `moved_other` 0, passed at every cap. AFTER = one
whole upper triangle gone from the same scene: `crack_closed` 0, `moved_other` on >1000 pixels,
failed at every cap — not one BEFORE ring ray reproduces AFTER's centre there, because they all
still meet the slab 10 in in front of it.

The crack runs at slope 2/5 so it is not parallel to any of the ring's eight angles (all 16 rays
clear a 0.02 in gap). That same slope is commensurate with the square pixel lattice, so the crack
passes exactly through a pixel centre every 5th row: **25** gap pixels, not the 1 I first asserted.
I measured which pixels fell through and why before changing the assertion.

**Real data, measured immediately after this commit:** file A's merge passed at **1,894 triangles
with `crack_closed = 1`** — the single pixel of the diagnosis — instead of rolling back to 2,656.
Suite after: 183.

---

## 4. R2b — the ring test cannot be skipped silently (`675235f`)

`compare_views` only ever checked that a nonzero `edge_flicker_cap` came with geometry, while
`_classify` also requires the planes before it will run the ring (now also the tie and crack tests).
Geometry without planes therefore cast nothing, tolerated nothing, and looked as though it tolerated
something. The planes are a pure function of the geometry, so they are now derived from it when not
supplied. A cap above zero with neither, **or with planes alone**, still raises — planes say what a
ring ray hit, not where to cast it.

**Tests.** `test_a_cap_above_zero_builds_the_planes_the_ring_needs_from_the_geometry` asserts the
derived-planes report is identical to the supplied-planes one and that `edge_flicker == 1`, i.e.
the ring really was cast. `test_a_cap_above_zero_with_planes_but_no_geometry_is_still_an_error`
pins the remaining error. The first failed on the pre-existing `allow_depth_fallback` ValueError
before the fix, then passed.

**A test was only green because the ring was being skipped.** `test_interior_hole_fails_at_any_cap`
fed a placeholder geometry (one unit triangle at the origin) unrelated to its synthetic buffers. The
moment the ring genuinely ran, the placeholder's ring rays all missed and the interior hole was
classified `crack_closed`. That is the correct verdict *for the placeholder* and nonsense for the
picture. I did not weaken the test: its cap>0 cases were replaced by
`test_an_interior_hole_flanked_by_coplanar_survivors_fails_at_any_cap` on a real slab with a real
rectangular hole — the very scene R2c asks for, landed here because R2b's fix required it. The
hole's left edge sits 0.05 in from a pixel centre, inside the inner ring radius, so **ring condition
1 genuinely holds at the rim** (the surviving slab beside the hole is the same material in the same
plane) while condition 2 cannot (BEFORE has no miss within the ring). Result at caps 0.0, 1e-4 and
1.0: 49 holes, 0 flicker, 0 `crack_closed`, 0 `zfight_tie`, not passed.

Suite after: 186.

---

## 5. R2c — ring tests say what they test (`53d5387`)

Every comment still describing the deleted 3x3-neighbourhood / 5x5-coverage rule is gone — eight
places in `test_guard.py` and one in `classify_pixels`' own docstring — replaced by what the ring
rule actually does. `grep -n "3x3\|5x5\|coverage prob\|sub-ray"` over `engine/` now returns nothing.

`_DUMMY_GEOMETRY`, the placeholder that lied, is replaced by `_BLOCK_GEOMETRY`: the **real** quad the
synthetic block picture comes from. `_buffers` puts every hit one unit along +z from an origin at
`(col, row, 0)`, so its hit points all lie on the plane `z = 1`, and the quad is that plane over the
block's own extent. A flicker test with a cap above zero now derives real planes from it and really
casts the ring. `_flicker_report` only falls back to `allow_depth_fallback=True` in the deliberate
no-geometry case, which is what two of its callers are actually testing.

What that geometry deliberately does *not* contain is `drop`: an individually deleted pixel is a
synthetic edit no real surface can express, which is precisely why no ring ray reproduces it and a
dropped pixel is never rescued. `test_interior_hole_fails_at_any_cap` gets its cap loop back on that
honest footing (holes 1, flicker 0, crack_closed 0, zfight_tie 0, at every cap), and the error test
now asserts what the lifted error produces rather than only that nothing was raised.

Suite after: 186 (no net count change — comments, helper and assertions).

---

## 6. M0 — a rolled-back merge keeps the guard report that failed (`93b1907`)

`FixResult.guard_merge_attempt: GuardReport | None` is the merged mesh's guard against the
reference — the report that decided whether the merge was kept. It survives the rollback, where
`guard_final` describes the fallback that shipped instead. `None` only when the merge never
converged and there was no merged mesh to guard; the *same* report as `guard_final` when nothing was
rolled back. `report.json` carries it with its per-view verdicts.

**M0 extension.** `engine/cli.py` gains `_failing_view_indices(result)` and writes
`guard_fail_<index>.png` for every view any of the three guards counted a failure or flicker pixel
in, besides the six axis views (an axis view that also fails gets both names). `<index>` is the
view's index in `VIEWS_26`. "Failure or flicker" is `holes`, `material_changed`, `moved_other`,
`moved_same_flat` or `edge_flicker`: `moved_same_flat` because whether it fails depends on the run's
strictness, `edge_flicker` because whether it fails depends on that view's cap. `zfight_tie` and
`crack_closed` are never failures under any setting, so a view holding only those is not listed.

Documented on `_write_guard_images`: AFTER is always the mesh that **shipped**, so a view listed
because `guard_merge_attempt` failed shows the rolled-back result, not the discarded candidate. The
picture says which view to look at; `report.json`'s `guard_merge_attempt` says what that view
counted. Carrying the discarded candidate mesh out of `fix_object` was not in scope.

**Tests.** The existing rollback test asserts `guard_merge_attempt.passed is False`, that it is not
the same object as `guard_final`, and that it names more than one bad view. The non-convergence test
asserts it is `None`. A new pipeline test asserts it equals `guard_final` when the merge is kept. A
new CLI test asserts a failing run writes `guard_fail_<index>.png` for **exactly** the views
`report.json` itself calls bad, and a second asserts a clean run writes none.

One assertion of mine was wrong and I corrected the test: I asserted the discarded candidate's guard
would show `holes > 0`, but the fixture is a *closed* box, so a lost outer face reveals the far
inner wall — the damage is 9,612 `moved_same_flat` pixels over 26 views, failing because that run's
final guard is strict. Suite after: 188.

---

## 7. R1a — thin sheets are never flipped (`a29688e`)

`classify_orientation` now decides THIN_SHEET **first** — both sides exposed and
`min/max >= sheet_ratio` — and FLIP applies only to what is left, where `back > front`.

The reasoning, recorded in the docstring: a sheet really seen from both sides has no outward side to
be wound towards, so "which side sees more sky" is not evidence about its winding. Anything standing
near one of its faces tips `back > front` by a few per cent, and flipping it does not correct
anything — it moves the one-sided hole to the equally visible other side, which is strictly worse.

**Tests.** `test_a_thin_sheet_is_never_flipped_even_when_its_back_sees_more` uses the measured
numbers of the fixture below plus a genuinely reversed face (front 0.10 / back 0.90, and front 0.0 /
back 0.5) that must still FLIP. End to end,
`test_a_free_standing_quad_seen_from_both_sides_is_a_sheet_not_a_flip` builds a 10x10 quad with a
6x6 awning floating 3 in over it — measured front 0.391 / back 0.500, ratio 0.78 — and asserts the
old rule's whole test (`back > front`) holds while nothing is flipped and both faces report as thin
sheets. Both failed before the change (`assert not r.flipped.any()` → `[True, True, False, False]`),
then passed.

**Measured on the real files**, applying the old and new rules to the same `compute_side_exposure`
output:

| | old flip | old sheet | new flip | new sheet | sheets no longer flipped |
|---|---|---|---|---|---|
| file A | 844 | 47 | **809** | **82** | **35** |
| file B | 842 | 103 | 838 | 107 | 4 |

Exactly the "about 35 genuine thin sheets flipped on file A (47 reported where 82 were measured)"
the review predicted. Suite after: 190.

---

## Engine suite

```
.venv/Scripts/python.exe -m pytest engine/tests -q
190 passed in 28.95s
```

(172 at the start of the round; +18.)

---

## Real-data runs

Six CLI invocations, all on the committed code. Every run **passed** (exit 0).

### Default — `python -m engine.cli fix <snapshot> --out data/output`

| | file A `ce26e0392ab0` | file B `0b290ec0bcb4` |
|---|---|---|
| name | CHTM_SIDE_WALK_2nd_floor | CHTM_2nd_to_3rd_building_sidewalk_outside |
| triangles before → after | 4,692 → **1,891** | 7,227 → **1,278** |
| hidden candidates / restored / removed | 1,853 / 34 / 1,819 | 2,411 / 30 / 2,381 |
| slit removed | 0 | 0 |
| degenerate removed / restored | 217 / 0 | 79 / 0 |
| flipped | 809 | 838 |
| thin sheets | 82 | 107 |
| one-sided holes before → after | 570,046 → 120,073 | 465,146 → 90,572 |
| merge | converged, **not rolled back**, 176 regions merged, 1,072 faces copied, skipped {overlap 9, invalid_polygon 5} | converged, **not rolled back**, 95 regions merged, 355 faces copied, skipped {overlap 3, new_vertex 1, invalid_polygon 1} |
| runtime | 35 s | 39 s |

Guard totals (`model_px` 2,059,414 for A, 2,425,186 for B; all three guards passed):

| guard | file | holes | material_changed | moved_same_flat | moved_other | **zfight_tie** | **crack_closed** | edge_flicker (hole/moved/material) |
|---|---|---|---|---|---|---|---|---|
| after_removal | A | 0 | 0 | 0 | 0 | **0** | **0** | 0 (0/0/0) |
| merge_attempt | A | 0 | 0 | 0 | 0 | **0** | **1** | 1 (1/0/0) |
| final | A | 0 | 0 | 0 | 0 | **0** | **1** | 1 (1/0/0) |
| after_removal | B | 0 | 0 | 0 | 0 | **12** | **0** | 0 (0/0/0) |
| merge_attempt | B | 0 | 0 | 0 | 0 | **14** | **0** | 1 (0/1/0) |
| final | B | 0 | 0 | 0 | 0 | **14** | **0** | 1 (0/1/0) |

Invariants, both files: `material_count_same` ✔ `bbox_same` ✔ `area_not_grown` ✔ `guard_passed` ✔
→ `passed = True`.

Failing-view images: `guard_fail_16.png` (file A), `guard_fail_17.png` (file B) — one each, for the
single `edge_flicker` pixel.

### `--accept-slit` — `--out data/output_accept_slit`

| | file A | file B |
|---|---|---|
| triangles before → after | 4,692 → **1,727** | 7,227 → **1,135** |
| hidden candidates / restored / removed | 1,853 / 34 / 1,819 | 2,411 / 30 / 2,381 |
| slit removed | **163** | **181** |
| degenerate removed / restored | 217 / 0 | 79 / 0 |
| flipped | 728 | 754 |
| thin sheets | 82 | 107 |
| one-sided holes before → after | 570,046 → 120,910 | 465,146 → 91,003 |
| merge | converged, not rolled back, 145 regions, 1,005 copied, skipped {overlap 4, invalid_polygon 5} | converged, not rolled back, 73 regions, 299 copied, skipped {overlap 1, new_vertex 1, invalid_polygon 1} |
| runtime | 58 s | 66 s |

| guard | file | holes | material_changed | moved_same_flat | moved_other | zfight_tie | crack_closed | edge_flicker (hole/moved/material) |
|---|---|---|---|---|---|---|---|---|
| after_removal | A | 0 | 0 | **1,006** | 0 | 0 | 0 | **0** (0/0/0) |
| merge_attempt | A | 0 | 0 | **1,008** | 0 | 0 | 0 | 1 (1/0/0) |
| final | A | 0 | 0 | **1,008** | 0 | 0 | 0 | 1 (1/0/0) |
| after_removal | B | 0 | 0 | 426 | 0 | **12** | 0 | 0 (0/0/0) |
| merge_attempt | B | 0 | 0 | 427 | 0 | **14** | 0 | 0 (0/0/0) |
| final | B | 0 | 0 | 427 | 0 | **14** | 0 | 0 (0/0/0) |

Invariants ✔ on both; `passed = True` on both. This is R2d directly: **1,008 tolerated
`moved_same_flat` pixels on file A and not one of them promoted to `edge_flicker`.** Under the old
rule 15 of 991 were promoted and capped, which is what failed the previous `--accept-slit` run.

### `preview-data` — `--out preview/data`

Both wrote successfully (41 s file A, 34 s file B): `guard_damaged_px` 1 on each,
`guard_passed: True`, `after_merged` 1,891 / 1,278, `regions` 176 / 95, `flipped` 809 / 838,
`thin_sheets` 82 / 107, `one_sided_holes_after` 120,073 / 90,572, `gridline_edges` 561 / 571,
`outline_edges_after` 3,148 / 2,138.

### Determinism

Two full runs of each file, into different output directories:

```
CHTM_SIDE_WALK_2nd_floor:                  IDENTICAL (36,229 bytes, sha256 2ea497cc71fed279…)
CHTM_2nd_to_3rd_building_sidewalk_outside: IDENTICAL (36,282 bytes, sha256 bcff148375c5f443…)
```

Byte-identical `report.json`, as required. No random numbers were added to production code.

### The `guard_fail_*.png` I opened

`data/output/CHTM_SIDE_WALK_2nd_floor/guard_fail_16.png`: the BEFORE panel shows the ramp-and-walkway
silhouette broken into a patchwork of dozens of separately shaded coplanar fragments, the AFTER
panel shows the identical outline with those fragments merged into clean flat panels, and the DIFF
panel is an unmarked light-grey silhouette — no red and no amber anywhere — so the merge changed the
triangulation and not one visible pixel of the facade.

---

## Differences from the expected outcomes, with their cause

* **File A default is 1,891 triangles, not the 1,894 the brief expected.** I measured 1,894
  immediately after M5 (`675b83c`), exactly as predicted. R1a then landed and stopped 35 thin sheets
  from being flipped; a face that is no longer reversed clusters into a different plane region, so
  the merge produces a slightly different (and slightly better) triangulation. Same cause for file
  B: 1,282 after M4, 1,278 after R1a. Nothing was tuned.
* **File B's merge passes**, so the brief's alternative ("or `guard_merge_attempt` shows exactly
  which pixels fail") did not arise. `guard_merge_attempt` is recorded anyway, passing, with 14
  `zfight_tie`.
* **`zfight_tie` is 12 after removal and 14 after the merge on file B.** The extra two appear only
  once the merge re-triangulates: the same overlapping-face defect, seen in two more pixels because
  the merged region presents a slightly different first-hit face there. Both are ties in both
  directions, so both are correctly not damage.
* **File A shows `crack_closed = 1` and `edge_flicker = 1`,** not one pixel doing both — they are
  different pixels, in the same view (index 16).

## Deviations from the brief, and why

1. **`ReusableCaster` has no `all_hits`.** The brief lists it alongside `EmbreeCaster` and
   `BruteCaster`, but `ReusableCaster` is a *factory*, not a caster: it has no `first_hit` or
   `any_hit` either, and no bound geometry to cast against — `__call__(positions, faces)` returns
   the caster. Giving it `all_hits` alone would half-implement the protocol against an undefined
   geometry. Every caller already gets `all_hits` through the caster it builds, which
   `test_reusable_caster_*` continues to cover.
2. **`EmbreeCaster.all_hits` is not only `intersects_location(multiple_hits=True)`.** It cannot be:
   see §2, where the prescribed call is shown returning one of the two coincident faces on file B's
   own geometry. The recovery pass and its limit are documented on the method.
3. **The R2c interior-hole test landed in the R2b commit**, because R2b's fix is what made the old
   placeholder-geometry version produce a wrong answer, and leaving the suite red between commits
   was worse. R2c carries the comment cleanup, the `_BLOCK_GEOMETRY` replacement and the restored
   cap loop.

## Concerns

* **`guard_fail_*.png` is noisy on a non-strict run.** `_failing_view_indices` counts
  `moved_same_flat` because whether it fails depends on strictness — correct for a strict run, but
  an `--accept-slit` run that *passes* still wrote 18 images (file A) and 13 (file B) for pixels it
  deliberately tolerated. Narrowing it to the run's own strictness would need `fix_object` to record
  `strict_final`, which was not in scope. The default runs write exactly one image each.
* **The coincident-hit recovery assumes overlapping faces share a vertex.** True of the measured
  file-B pair and of SketchUp face loops generally, not true in principle. The failure mode is safe
  (a missed tie is reported as damage), but a z-fight between two independently drawn loops would
  still fail the guard.
* **`preview-data`'s `stats` does not yet expose `crack_closed`, `zfight_tie` or the rollback
  flag**, so the preview page cannot show them. That is R1c, which was explicitly not in this
  round's list.
* **`engine/guard/render.py` gives `PX_ZFIGHT_TIE` and `PX_CRACK_CLOSED` no colour** in the DIFF
  panel — they render as plain model grey. Neither is a failure, so nothing is mis-signalled, but a
  crack the fix closed is arguably worth showing in green. Not requested; not changed.
* **The three guard reports are computed independently**, so a run now casts the tie probe as well
  as the ring on every failing-base pixel. Runtimes are unchanged in practice (27–39 s default,
  58–66 s with `--accept-slit`, against ~30 s before) because the candidate sets are tiny, but a
  catastrophically failing merge would pay `all_hits` on every failing pixel.

---

## Public signatures

Only what changed this round; everything else is unchanged from the last `## Public signatures`
section of `engine-round-2026-09-23-report.md`.

```
engine/rays/caster.py

_COINCIDENT_REL_TOL = 1e-6      # NEW: relative slack for the coincident-hit recovery, as a
                                # fraction of the mesh's bounding-box diagonal

class RayCaster(Protocol):
    any_hit(origins, directions) -> np.ndarray                      # unchanged
    first_hit(origins, directions) -> (tri, t)                      # unchanged
    all_hits(origins, directions) -> (ray_index, tri, t)            # NEW
        # three parallel arrays, one entry per HIT (int64, int64, float64); a ray that hits
        # nothing contributes no entry, so H is unrelated to len(origins); order within one ray
        # is unspecified. Two triangles overlapping in the SAME plane are both reported, at the
        # same t.

class EmbreeCaster:
    all_hits(origins, directions) -> (ray_index, tri, t)            # NEW
        # trimesh multiple_hits=True, PLUS an analytic recovery of hits its ray-stepping skips
        # (coincident faces): each reported hit point is re-tested against the triangles sharing
        # a vertex with the triangle it hit. LIMIT documented on the method.
    # new private state: _positions, _coincident_tol, _vertex_faces (lazy)
    # new private methods: _vertex_face_table(), _coincident_with(itri, points), _contains(...)

class BruteCaster:
    all_hits(origins, directions) -> (ray_index, tri, t)            # NEW (no recovery needed)

class ReusableCaster                                                # UNCHANGED (see Deviations)
```

```
engine/guard/compare.py

PX_ZFIGHT_TIE = 6       # NEW
PX_CRACK_CLOSED = 7     # NEW
_CRACK_RING_MIN = 12    # NEW: of the 2 * _RING_ANGLES = 16 ring rays

classify_pixels(before_depth, before_tri, after_depth, after_tri, material_before, material_after,
                flat_materials, depth_tol, *, origins=None, direction=None, plane_before=None,
                plane_after=None, ring=None, tie=None, allow_depth_fallback=False,
                strict=False) -> np.ndarray
    # NEW keyword-only `tie`: tie(mask) -> ((ray, tri, t) before, (ray, tri, t) after)
    # NEW keyword-only `strict`: which base classes may be promoted at all
    # promotion order: tie -> crack -> ring; no tie/ring => those classes never appear

_failing_base(codes, strict) -> np.ndarray                          # NEW (module-private)
_tie_probe(buffers, caster_before, caster_after) -> callable        # NEW (module-private)
_matches_tie_set(hit_ray, hit_tri, hit_t, t_first, member_material, member_plane,
                 other_point, other_material, other_hit, depth_tol, n_pixels) -> np.ndarray   # NEW
_ring_matches(centre_tri, centre_material, centre_plane, ring_tri, ring_point, ring_material,
              depth_tol) -> np.ndarray                              # NEW: the (P, R) matrix
_ring_reproduces(...) -> np.ndarray                                 # now _ring_matches(...).any(1)

@dataclass
class ViewVerdict:
    view; model_px; holes; moved_same_flat; moved_other; material_changed
    zfight_tie: int      # NEW  (inserted after material_changed)
    crack_closed: int    # NEW  (inserted after zfight_tie, before edge_flicker)
    edge_flicker; edge_flicker_hole; edge_flicker_moved; edge_flicker_material

compare_views(...) -> GuardReport
    # signature unchanged; `totals` gains "zfight_tie" and "crack_closed"
    # BEHAVIOUR: plane_before/plane_after are now DERIVED from geometry_before/geometry_after when
    # not supplied; edge_flicker_cap > 0 without geometry still raises (planes alone do not help)
    # `strict` is now also forwarded to classify_pixels as the promotion gate

guard_feedback(...) -> (mask, history)   # signature and results unchanged (casts no ring, no tie)
face_planes(...)                         # unchanged
```

```
engine/fixes/orient.py

classify_orientation(front, back, ok, sheet_ratio=0.5) -> np.ndarray
    # signature unchanged. PRECEDENCE CHANGED: THIN_SHEET is decided first (both sides exposed and
    # min/max >= sheet_ratio); FLIP only applies to what is left, where back > front.
```

```
engine/fixes/pipeline.py

@dataclass
class FixResult:
    # ... unchanged fields ...
    guard_after_removal: GuardReport
    guard_merge_attempt: GuardReport | None   # NEW: the MERGED mesh's guard against the reference,
                                              # kept on rollback; None only when the merge did not
                                              # converge; the same report as guard_final when the
                                              # merge was kept. (inserted between
                                              # guard_after_removal and guard_final)
    guard_final: GuardReport

fix_object(mesh, flatness, profile=FixProfile()) -> FixResult   # signature unchanged
FixProfile                                                       # unchanged
```

```
engine/cli.py

_failing_view_indices(result: FixResult) -> list[int]           # NEW
    # indices into VIEWS_26 of every view any of the three guards counted a failure or flicker
    # pixel in (holes / material_changed / moved_other / moved_same_flat / edge_flicker)

_view_verdict_dict(v)   # now also emits "zfight_tie" and "crack_closed"
_build_report(...)      # report.json gains "guard_merge_attempt" (a guard-report dict, or null)
_write_guard_images(...)  # signature unchanged; now also writes guard_fail_<index>.png for every
                          # index in _failing_view_indices(result), besides the six axis views
```
