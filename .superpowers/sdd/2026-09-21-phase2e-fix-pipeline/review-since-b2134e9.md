# Review since b2134e9, part 1 (brief 04)

Independent read-only review, 2026-09-24. Scope: `feat-dashboard` from `b2134e9` to `ce48932`,
excluding `feat/side-rebuild` (part 2). Commits read: the solidify fixes a528705, cccaa4c, b5e7f48,
f1b6aec, f32d035, 9c52695; fragments and the QA sheet 5169e68, ab2d2fc, 8046254, c0bbc98; the peer
merges 17939a4 (d505241), ee840e9 (dee358d), e57462d (a23b031, 5f2c7f1, 0c92b2d); 022a67b;
e97443e, d24da30, 8ffbda3; d6ef1a9, b3b9ad3, 1ee69e3, a03967d, e182922; bcccca2, 8ee9e4d; 28d63df,
03df53d. Round reports read in full: solidify-fix-fragments, border-shift, skp-export (K1, K2, S1),
merge-new-vertex, tjunction.

How it was checked:
- Code read at `ce48932` in a detached scratch worktree, never the shared working tree.
- Engine suite run there with `PYTHONPATH` pinned (`engine.__file__` confirmed inside the scratch
  worktree): **417 passed in 68.66 s, 0 skipped** (the SketchUp DLL is present), which is the
  count the T1 report gives.
- Six probe scripts, in this folder beside this file. Each one imports the committed engine,
  builds a small synthetic mesh, and prints what ships. To run one:
  `PYTHONPATH=<worktree at ce48932> .venv/Scripts/python.exe <probe>`.
- Not done, by rule: no real data was run, the SketchUp GUI was not opened, and the API tests
  were not run (they drop the shared test DB).

## Verdict: Changes required

Two guards tolerate changes they do not measure. On a fixture-sized input, each one ships real
visible damage with `passed = True`:
- the cap guard's back-side rule (C1);
- the fragment pass's excuse by name (C2).

Two more defects need fixing before the next owner check:
- solidify measures slab depth from the wrong faces (I1);
- a failed run overwrites the owner's `.skp` (I2).

Findings: **2 Critical, 2 Important, 9 Minor**.

---

## Critical

### C1. The cap guard lets an invented face cover any back-side hit, unmeasured, so S-C1's defect returns when the covered face is wound backwards

**Where:**
- `engine/guard/compare.py:1167-1172` is rule 2:
  `back_side = covered & (normal[safe_index] @ direction > 1e-9)` and
  `bad = covered & ~back_side & ~only_through_an_opening`. A back-side hit is never bad.
- The docstring states the rule at `compare.py:1081-1087`.
- `engine/fixes/solidify.py:570-571` runs `front, _back = compute_side_exposure(...)`. The back
  half is measured and then thrown away.

**Failure 1: the real underside is deleted, which is S-C1 again.** The input is
`slab_with_partial_underside` with its real underside's two triangles wound +z, into the slab.
Such faces are common:
- file A has 809 faces wound backwards (`solidify.py:30`);
- the orientation step that would flip them runs after solidify.

| | as committed (-z) | underside reversed (+z) |
|---|---|---|
| `cap_guard_removed` | 4 | **0** |
| underside exposure on the solidified mesh, front / back | 0.32, 0.30 / 0.03 | **0 / 0** |
| `removed_hidden[8, 9]` | False, False | **True, True** |
| `passed`; guard_final holes, moved | True; 0, 0 | **True; 0, 0** |
| z levels the shipped faces use | -9.8, -4.0, 0.0 | **-9.8, 0.0** |

The real underside at -4 in is gone, and the invented one at -9.8 in ships. Every guard passes:
- every later guard compares against the solidified reference;
- the cap guard let the cover through on rule 2;
- S-I2's invariant re-verifies the cap guard's own rules, rule 2 included, so it cannot catch
  this either.

**Failure 2: solidify lays a skirt exactly over an existing side.** The input is a closed
40 x 40 x 8 in slab whose x = 0 side exists but is split at the midpoint of its top edge.
`_open_edges` (`solidify.py:121`) then sees the top's edge 0-3 with a table count of 1 and hangs a
skirt on it. This is N3's region-38 mechanism.
- **Side wound outward:** the cap guard refuses both skirt triangles, through rule 3.
- **Side wound inward:** nothing is refused, and the skirt ships exactly over the side:
  - 4 faces totalling 640 sq in lie on a 320 sq in side;
  - `removed_overlap` is 0 and `passed` is True.

  That is a z-fighting double layer ("texture on texture"), created by the fix itself.

**Evidence:** `probe_reversed_underside.py` and `probe_duplicate_skirt.py`. Rule 2's own
justification ("a one-sided renderer was dropping that pixel anyway") contradicts the project
decision that visibility is judged double-sided, since SketchUp and the Unity shader draw both
sides (session record section 7).

**Not measured:**
- how many cover decisions on A and B went through rule 2 (no real data was run);
- whether B's region 38 survived by this path (N3 does not say how its skirt got past the guard).

**Fix:**
- Judge a back-side hit by the original-mesh exposure of the side the ray met. The `_back` half
  is already computed.
- Exempt only the backs of the shell being closed: the region's own top faces, and the side faces
  its heights were measured from.
- Refuse any new face that coincides with an existing face. Use a coplanar-overlap test (e.g.
  `engine.fixes.overlap.find_overlaps`), not pixels: the renderer resolves a coincident pair as a
  tie, so pixels cannot be trusted to see it.
- Do not treat an outline edge as open when existing side faces cover it through T-junctions.
  This is N3's own recommendation for `_open_edges`.
- Keep both probes as regression tests.

### C2. Fragment removal is excused by name, and the detector can name a piece of the visible surface, so a hole ships with passed = True

**Where:**
- In `engine/detectors/fragments.py`:
  - `:77-101` builds components over shared welded edges only.
  - `:157-158` makes a component debris when its biggest face is at most 4 sq in and either its
    total area is under 4 sq in, it is a single face, or its extent is under 6 in.
  - `:170` is the sliver rule.
- In `engine/guard/compare.py`:
  - `:1035-1036` has `fail = fail & ~mine`, so a candidate's own pixels are never judged, whatever
    AFTER shows there.
  - `:505-507`: the final guard stamps `PX_FRAGMENT_REMOVED` before any other test.
  - `:700-705`: that class is never capped.

**Failure:** the input is a closed 40 x 40 x 8 in slab whose top holds a 3 x 1 in infill patch:
two triangles, 3 sq in. The patch meets the surrounding top only at T-junctions: the surround has a
vertex at the middle of each patch side, and the patch has none.
- The patch is its own component and is classed as a fragment.
- It is removed.
- `passed` is True and every invariant is True.
- guard_final shows holes 0, moved 0, material 0, flicker 0, and `fragment_removed` 321 px.
- A ray straight down through the patch centre now meets the inside of the bottom at z = -8.

A 3 sq in hole in the walking surface ships.

**The same rules also delete these:**
- **Small objects:** any separate component whose extent is under 6 in and whose faces are all
  4 sq in or less, whatever its total area. Examples: a finely triangulated 5 in drain cover, a
  bollard cap, a tactile-warning dome.
- **Thin plate sides:** an attached face with q < 0.02 and area of at most 4 sq in. That includes
  the side faces of a plate 0.25 in thick and 20 to 32 in long, or 0.1 in thick and 8 to 80 in
  long.

The module docstring says the "no face bigger than 4 sq in" rule "is what makes the other three
safe". That holds only for a component made of one big face.

**Evidence:** `probe_fragment_patch.py`. T-junctions are everywhere in these exports: T1 counted
A 353 and B 363 T-vertices at the merge input.

**Not verified:** whether any of the removed faces were real surface (3 fragments and 15 slivers on
A; 12 slivers on B). report.json lists only the smallest components that were kept, never the
removed ones, so nobody can check them.

**Fix:**
- Connect components across T-junctions: an edge lying on another face's edge within the 0.15 in
  tolerance `analyse_topology` already uses. Also connect them across coplanar contact.
- In fragment mode, permit a candidate's own pixel only when AFTER shows background, or a face
  side whose exposure on the reference is above 0. Never permit the inside of a closed shell.
- Write each removed component's face ids, area and bbox to report.json.
- Cap `fragment_removed` per view, the way `crack_closed` is capped.
- Consider reporting components that touch other geometry instead of deleting them.

---

## Important

### I1. Solidify boxes a thin slab to the depth of any side face touching a corner of its open edge, and the cap guard allows all of it

**Where:**
- `solidify.py:153-163`: `rows` is every side face at either endpoint, and the thickness is top z
  minus the lowest of them, so the deepest wins.
- `solidify.py:327-336`: `own` and `bottom_h = min(own)` come from the open edges only. The
  region's existing closed sides are ignored.
- `compare.py:1160-1172`: rules 1 (background) and 2 (back sides) are never measured.

**Failure:** the input is a 40 x 40 in top with three outward 2 in skirts and the x = 0 edge open.
Its corner (0, 0, 0) is also the top of a 30 in retaining wall running outward in -x.
- `thickness_per_region` is {0: 30.0} and `bottom_depth_per_region` is {0: 30.0}.
- Solidify adds 1 skirt and 1 bottom, and `cap_guard_removed` is 0.
- `passed` is True, and the shipped faces reach z = -30 over the slab's footprint.

A 2 in slab becomes a 30 in box, with 28 in gaps under its three real sides. Everything the new
faces cover is background (rule 1) or a back side (rule 2).

**Evidence:** `probe_deep_corner.py`. The solidify report's closing hypothesis names the
deepest-side rule, but as a refusal count; this consequence is not refused at all. Real skirts on
A run from 1.3 to 49 in, and A has stepped platforms.

**Scope notes:**
- It is not a regression of S-I4 or S-I5 for a region with one open edge: the median of one value
  is that value.
- It was not measured on real data. Comparing `bottom_depth_per_region` with each region's
  existing sides would show whether it happens there.

**Fix:**
- Take an open edge's height only from side faces that hang from this region's outline: they
  share an edge with a region face, or start at the region's top along the outline. Use the
  shallowest of those, not the deepest.
- Place the bottom no deeper than the shallowest existing side of the region, closed sides
  included.
- Report every region whose skirt or bottom is deeper than its own existing sides.

### I2. A failed run overwrites the owner's SketchUp file

**Where:**
- `engine/cli.py:397` calls `_write_skp` whatever `result.passed` is.
- `cli.py:346-352` copies the file with `shutil.copyfile` into the skp folder, replacing what is
  there.
- `cli.py:689-694`: `main` passes `default_skp_dir()`, which is `OBJ FIXED RESULT/`.

**Failure:** `probe_failed_run_skp.py` forces the same wrong removal as
`test_cmd_fix_exits_two_when_a_visible_face_is_wrongly_removed`. The skp folder already holds the
last passing run's file.
- The exit code is 2 and `passed` is False.
- `skp.written` is True.
- The folder's `box_with_partition.fixed.skp` is replaced (5,899 bytes).

The owner's routine is to open the latest `.skp` after every run (session record section 1), and
nothing in the file says the engine rejected it. No test covers a failing run with a skp folder:
`test_cmd_fix_replaces_the_previous_skp_in_the_skp_folder` uses a passing run.

**Fix:**
- Copy only when `result.passed` is True.
- On a failed run, keep the previous copy, or write `<name>.fixed.FAILED.skp` beside it.
- Say what happened on the CLI line and in `report.json` `skp.copied_to`.

---

## Minor

**M1. The S-I2 test reaches the cut-off path with 0 rounds, on a premise the code contradicts.**
- **Where:** `engine/tests/test_solidify.py:487-506`. The report says "`max_rounds = 1` would
  converge and prove nothing".
- **Measured** (`probe_cap_rounds.py`): at `max_rounds=1`, round 0 removes 4 faces and the loop
  ends by running out of rounds. The appended verification (round 1, 0 failing, 0 removed) is what
  makes `cap_guard_passed` True. Code without that verification would end on round 0's 8,498
  failing pixels.
- **Gap:** at 0 rounds, the returned mesh and the pre-removal mesh are the same mesh. A
  verification rendered on a stale `keep` would therefore still pass the test, even though the
  test's docstring says it proves the verdict comes "from a real final render".
- **Fix:** add a `max_rounds=1` case asserting that `history[-1]` is round 1 with 0 failing and 0
  removed, and that `cap_guard_passed` is True.

**M2. The `bbox_same` invariant cannot fail.**
- **Where:** `engine/fixes/pipeline.py:524-525` compares every row of `positions`. Merge, removal
  and flip never touch that array: the shipped mesh shares the reference's `positions` object
  (checked: `r.mesh.positions is r.reference_mesh.positions` is True).
- **Checked:** a shipped mesh reduced to 1 face still passes, with a used bbox of z 0..0 against
  the reference's -8..0.
- **Relevance:** the invariant is older than this scope (c19a1ea), but the T1 report and the
  session record cite it as evidence that the surface is unchanged.
- **Fix:** compare the bbox of the vertices that faces use, or drop the invariant.

**M3. Growth over background is still unmeasured, and d505241 now lets a region grow.**
- **Where:**
  - `compare.py:481-500`: a pixel where BEFORE missed and AFTER hit stays `PX_OK`. The border
    probe's "appeared" branch (`:571-576`) can never reach it.
  - `merge.py:1002-1017`: per region, growth up to `collinear_tol x perimeter` is now accepted
    when the pass nets to 0 or less.
- **Correction to border-shift concern 2:** that concern gives the bound as rule 9 plus
  `area_not_grown`, but both are net area checks. The only real bound is the RDP construction
  (0.15 in), and no guard sees a merge bug that grows a silhouette.
- **Fix:** class BEFORE-miss / AFTER-hit pixels as a failing base (e.g. `PX_GROWN`), and let the
  ring and border-shift measurement excuse them exactly like losses.

**M4. The border-shift "displacement" is really the clearance to the nearest triangle of any surface.**
- **Where:** `compare.py:571-576` and `281-299`; the docstrings at `396-408` and `707-719` call it
  "the real displacement".
- **Effect:** where a lost strip lies between the retreating border and another surface at the old
  border (a skirt, which solidify now hangs on every open top edge), the value measured is the distance
  to the nearer of the two. At grazing views, a strip up to 2 x tol wide can then read as within
  tol.
- **Status:** verified by reading the code, not reproduced. Head-on views would still fail such a
  strip, so the practical loss is small.
- **Fix:** measure first against triangles of the same material near the BEFORE hit's plane, or
  change the docstrings to say "clearance".

**M5. F5: every snapshot version imported before e57462d has `asset_sha256` NULL, so the first re-import of each model duplicates it.**
- **Why:** b2134e9's `SnapshotResult` had no such field, and the importer stored
  `getattr(..., None)`. The new lookup (`api/services/importer.py:113-119`) never matches NULL.
- **Effect:** the first re-import of each unchanged model after F5 creates a duplicate version
  plus a second snapshot folder `<sha12>-<asset8>`. There is no migration or backfill. The
  duplicate fails nothing (no unique constraint on versions); it is clutter.
- **Fix:** backfill `asset_sha256` from each existing snapshot folder, or match NULL on sha256
  alone and backfill it then.

**M6. `ON_FACE_TOL` is justified by a sweep on a mesh that no longer ships.**
- **Where:** `engine/io/skp_writer.py:121-126`.
- **Why stale:** the sweep (A 69 / 72 / 73 / 77, B 9) ran on `feat/skp-soften` from 8ffbda3, before
  d6ef1a9, b3b9ad3 and 28d63df changed the merge output. T1 later measured the writer's
  `tjunction_lines_softened` falling from A 42 to 16 and B 9 to 3.
- **Fix:** re-run the sweep on the current output and restate the numbers.

**M7. `polygon_edges` says it returns "the edges SketchUp will draw", but the writer hides edges the sheet still draws.**
- **Where:** `engine/guard/qa_render.py:74-76`.
- **Why wrong:** the writer hides every class 1 and class 5 edge of copied rows, plus the S1
  lines, so the QA sheet draws fans that SketchUp hides (T1 concern 4, still true).
- **Fix:** correct the docstring, or feed the sheet the writer's soft set.

**M8. An unexpected exception in the QA or `.skp` step leaves the previous run's report.json beside the new OBJs.**
- **Where:** `cli.py:378-401` writes the OBJs first and report.json last. `_write_skp` catches
  only `SketchUpError` (`cli.py:341`).
- **Trigger:** any other exception from the QA or `.skp` step, e.g. a ctypes access violation,
  which surfaces as `OSError`.
- **Fix:** write or delete report.json before the optional exports, or catch `Exception` in
  `_write_skp`.

**M9. The session record's error map (section 3) describes both guards more safely than the code behaves.**
- **Cap guard:** it says "a new face may only cover faces seen through openings, original exposure
  under 0.10". It does not mention that background and back sides are covered without any
  measurement (C1, I1).
- **Fragments:** it lists `fragment_feedback` as the safety check. It does not say that a
  candidate's own pixels are never judged (C2).
- **Fix:** update the map when C1, C2 and I1 are fixed.

---

## Checked and found sound

- **Only solidify invents or moves a vertex.**
  - The merge emits only `welded_to_original` rows (`merge.py:1252, 1274`).
  - The rows it appends are `vt` and `vn` only (`merge.py:1242, 1249`).
  - The writer passes each welded vertex's lowest row through unchanged (`skp_writer.py:418-420,
    626`).
  - SketchUp's own `weld_vertices=true` fill is outside the engine's control.
- **T1 threading keeps the surface to within tolerance, stays deterministic, and cannot loop.**
  - "On" is a 3-D distance to the segment interior at `thread_tolerance`, 1e-6 in on both files
    (`merge.py:760-775`).
  - `find_t_vertices` only considers vertices of faces in the table (`adjacency.py:82`), so a
    removed face's vertex is never threaded back in.
  - `_split` fans one triangle into pieces of exactly its area, keeping the winding. It ends
    because every cut turns a listed vertex into a corner of strictly smaller pieces, and the
    opposite corner is excluded.
  - Rounds are capped at `MAX_THREAD_ROUNDS`, and every dict is built in sorted order.
  - Growth is bounded by (vertex, edge) incidences per round; T1 measured +12 % on A and +8 % on B.
  - Weakness: its "bbox unchanged" evidence is M2.
- **The writer never softens a material border, and hides a real outline only across a gap of
  0.02 in or less.**
  - Class 1 needs one region, and regions are split by material (`planes.py:68`).
  - Class 5 needs the same material (`edges.py:54-67`).
  - S1 compares materials (`_same_look`) and checks for angled faces before hiding anything
    (`skp_writer.py:1079-1095`).
  - Rule (b) hides an edge only when coplanar faces of the same look cover its far side along its
    whole length, to within 0.02 in. So a real outline is hidden only across a crack or step of
    0.02 in or less, which is documented.
- **The merge cannot close a real opening or bridge a region.**
  - The sliver test (`4 x area / perimeter <= 2e-4 in`, i.e. a strip at most 1e-4 in wide) sits
    two orders of magnitude below the 0.01 in print step.
  - The snap maps a union coordinate to its nearest vertex, within at most 0.01 in, so it cannot
    fuse two printed vertices.
  - Set-aside triangles are copied through whole, and the rest is unioned again, so nothing is
    bridged.
  - Rule 9 per pass keeps `area_not_grown`.
  - One silent loss, noted but not raised as a finding: a sliver island, or an outer ring that
    collapses onto fewer than 3 vertices, is dropped without being copied or counted
    (`merge.py:589-590, 602-603`). It is at most `snap_tol` wide.
- **Z-fight ties, crack caps and flicker caps behave as documented.**
  - A tie needs both directions to match by material and plane (`compare.py:530-545`), so a
    removed member of a pair in different materials still fails.
  - A coplanar layer in the same material never reaches the tie test, because its base class is
    OK.
  - Crack promotion is refused wherever BEFORE's first hit was deleted (`compare.py:915-919,
    1025-1030`).
- **The measured numbers in the docstrings match the reports.**
  - `snap_tolerance`: 3,441 = 3,415 + 24 + 1 + 1; 0.0016 / 0.0085 = 0.19; tips up to 0.0053 in;
    0.3 to 4.7 degrees.
  - `_pieces`: 13 of 33 holes; 2e-4 against 8.9e-5 and 0.25 in.
  - `thread_tolerance`: 1,000x and 610x; the 3 and 11 near pairs.
  - `PLANE_TOL`: 1.2e-3; 5.0e-3 / 1.25e-3; 1.6e-3.
  - The border-shift docstring: 14 pixels against a cap of 11.4; 0.062 in.
  - The fragments module: 285 faces, 391 to 793 sq in.
  - VIEWS_26's near-horizontal views (measured |z| 0.0077 to 0.011 normalised).
  - The exceptions are M1, M6, M7 and M9.
- **The tests that reach their paths artificially, or were written after the code:**
  - S-I3's two shapely patches really do test solidify's all-or-nothing verdict. The non-polygon
    branch is unreachable under GEOS's contract, but the test is a fair defensive one.
  - F1's regression test reproduces the defect through the old calling convention, so it is
    meaningful.
  - F2's pixel bands come from the geometry (an 80 in perimeter at 0.88 in per pixel), so they are
    meaningful.
  - S-I2 is M1.

## The authors' own concerns, re-checked

| concern | result |
|---|---|
| solidify 1 (68 hidden, not 96), 2 (`open_box_with_cells` open) | design outcomes; C1 shows that some rule-2 covers can be wrong |
| solidify 4, 5 (tests artificial or written after the code) | see above; S-I2 is M1 |
| border-shift 2 (growth over sky) | still open; its stated bound is wrong (M3) |
| border-shift 3 (per-view `border_shift` missing from report.json) | still open at ce48932 (`cli.py:124-131`) |
| border-shift 6 (documented limit) | holds; M4 adds the measure-to-any-plane caveat |
| skp 2 / merge-new-vertex 3 (nonplanar regions written as soft triangles) | hidden correctly; the class 1/5 softening and S1 rule (a) both cover their diagonals |
| merge-new-vertex 5 (region 38, solidify) | reproduced in miniature; it ships only when the existing side is reversed (C1, failure 2) |
| T1 1 (near T-junctions left at 6.1e-4 to 4.6e-3 in) | a ruling for the controller; leaving them is consistent with "never move a vertex" |
| T1 4 (QA sheet draws fans SketchUp hides) | still open; the docstring is still wrong (M7) |
| T1 5 (coincident faces in the `.skp`) | SketchUp merges them; the OBJ keeps both layers, so Unity still z-fights there |

## Probe scripts in this folder

| script | shows |
|---|---|
| `probe_reversed_underside.py` | C1 failure 1 (the real underside deleted, passed True) |
| `probe_duplicate_skirt.py` | C1 failure 2 (a coincident skirt over a reversed side, passed True) |
| `probe_fragment_patch.py` | C2 (a 3 x 1 in hole in the top, passed True) |
| `probe_deep_corner.py` | I1 (a 2 in slab boxed to 30 in, passed True) |
| `probe_failed_run_skp.py <tmp parent>` | I2 (exit 2, the skp folder's file replaced) |
| `probe_cap_rounds.py` | M1 (the one-round cut-off path, and its verification round) |
