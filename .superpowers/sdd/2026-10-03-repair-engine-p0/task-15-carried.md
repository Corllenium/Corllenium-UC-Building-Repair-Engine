# Carried into P0-15 from P0-14 (implementer concerns 3-12 and the task review, 2026-10-04)

## Required in P0-15 (each test first)
1. **Probes on reversed walkable floors.** `interior_probes` takes only faces with winding normal `n_z > 0.9`, so a
   downward-wound walkable floor gets no probes. Example: `closed_room` with its floor reversed gives 0 of 20;
   on CHTM 5th, 6 lattice cells have none. Reversed faces are an error kind, and the engine will flip exactly
   these, so the Validator must see them from inside.
   - Take faces with `|n_z| > 0.9` and place candidates on the +z side. The headroom ray from 0.5 in above and the
     majority back-face vote stay as they are; the vote rejects solid interiors.
   - Tests: `closed_room` with a reversed floor keeps its interior probes; a downward-wound true ceiling adds no
     probe inside a solid.
   - Measure CHTM 5th's probe count before and after, and paste it.
2. **`check_caster`** (`visibility.py:55-60`) also requires `np.array_equal(caster.faces, mesh.face_v)`. Test it with
   a caster built from a different mesh with the same face count.
3. **`_rows`** (`visibility.py:113-117`) requires shape (k, 3). It must not reshape a (3, 2) array.
4. **Face ids in `face_samples`** (`sampling.py:104`): refuse float, negative or out-of-range ids.
5. **Two surviving mutants get tests:**
   - a blocker 0.5 in before a camera or probe must block the segment;
   - a candidate probe with 14-20 back votes must be dropped.
6. **Wording:** `LEVEL` (`viewpoints.py:22-24`) is a fixed bin, not a band. Name, in the `interior_probes` docstring,
   the two limits the review measured: reversed floors (fixed by item 1); reversed ceiling plus reversed walls
   can drop open-air probes (18 of 20 kept with one such wall, 13 of 20 with two).

## Design notes for the checks
- **Check 3's "covered" test** uses its own depth comparison with the tolerance `max(2 × print step, 0.05 in)`. Never
  rely on visibility's 0.02 in step-off, which jumps any layer closer than that: a face 0.015 in in front does not
  count as covering.
- **Allowed-change classes.** Back-to-back pairs: both faces read as "seen", from `_Cull = 0`. v0 has no
  allowed-change classes (the brief), so removing an inward copy FAILS v0 check 3. That is expected; the named
  E4/E5 class comes with those engines.
- **Check 1:** cast from the best-conditioned viewpoint per sample (largest |cos| between the viewing ray and the
  normal). Edge-on views are ill-conditioned.
- **Memory.** Cast in chunks of samples. The dense seen/front matrices are 1.6 GB at 500 k samples × 1,600
  viewpoints. CHTM 5th at the default density is 441 k samples, 1,549 viewpoints and about 8 min per mesh.
  Report the validate command's time and peak memory on CHTM 5th. If it is too slow, propose a measured
  density setting; do not silently lower the brief's.
- **Viewpoints.** Compute the probes once from BEFORE and reuse them for AFTER (the lattice is anchored to the
  mesh's bbox). Recentre AFTER with BEFORE's centre: `recentred(after, centre)`.
- trimesh 5.1.0 drops a first hit within 1e-5 of parallel (`engine/rays/caster.py:70`), so a near-parallel plate may not
  block a segment. This is rare in axis-aligned geometry; note it and do not fix it here, because the caster is
  shared code.
- The `closed_room` face order is relied on by the P0-14 tests; append new fixtures, never reorder.
