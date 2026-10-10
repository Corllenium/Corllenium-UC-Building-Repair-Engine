# Task P2-V2 brief: the Validator judges removed and covered faces to the owner's floor

**Owner decisions (2026-10-10, recorded in AGENTS.md §5, Visible rule):**
- no removed or covered face may show more than **4 pixels at 0.02 in per pixel** (about 0.0016 sq in) from any
  Validator viewpoint;
- this is judged on **every line of sight** and from **both sides** (Unity draws both sides, `_Cull = 0`).

The owner also chose to strengthen the Validator itself, so a floor cannot pass while a partly visible face was
removed or covered.

**Why (measured):**
- **P2-E3:** the Validator's 4-9 samples per face missed visible removed faces. CHTM 5th face 8480: 0 of 9 samples
  seen, 190 of 1,770 dense points seen. After E3's dense pre-filter, an independent check still finds patches of
  about 1.4 sq in on sidewalk A and about 1.37 sq in on sidewalk B (face 455).
- **P2-E8a concern 3:** `covered` tests only the chosen witness ray (`checks.py` about :395-478).
- **P2-E3 concern 3:** a ray-caster corner artefact. A line through the corner of CHTM 5th face 10553 misses in
  BEFORE and hits in AFTER, which holds a subset of BEFORE's faces. That gave 4 false `covered` samples and rolled
  back 21 sites.

**Base:** `feat/repair-p1p2` = 7258652 (E8a, E8b, E8c and E3 merged).

## Items (each test first; commit after each)

1. **The floor measure.** In `engine/validate`, add `face_visible_pixels(before_mesh, face, viewpoint)`. It renders an
   ID buffer of BEFORE along that viewpoint's line, centred on the face, at **0.02 in per pixel**, and returns the
   number of pixels where that face is the nearest surface.
   - Orthographic for direction viewpoints; perspective from the camera or probe position for ring cameras and
     eye-height probes, with the pixel size taken at the face.
   - Name the floor `VISIBLE_FLOOR_PX = 4` and `FLOOR_IN_PER_PX = 0.02` as constants. The owner may change them; no
     FixProfile field.
2. **Candidates for the measure.** A removed or covered face goes to item 1 when an **area-scaled lattice** (at
   least 36 points, plus one per sq in, capped at 4,096 per face) finds any point seen from any viewpoint, from either
   side. Report the lattice and the cap.
   - **Check 3 FAILs** when any such face has more than `VISIBLE_FLOOR_PX` pixels from any viewpoint that sees it.
   - The report lists each failing face: pixels, viewpoint, crop path.
   - A crop (BEFORE | AFTER at 0.02 in/px) is written for every face measured above 0 pixels.
3. **Every line of sight, both sides, for `covered`.** A BEFORE sample is covered when ANY viewpoint line that saw
   it in BEFORE, from either side, is blocked in AFTER by a face that was not the sample's own. It is no longer judged
   by one witness alone.
   - The covered amount is then measured per covering face with item 1's measure. Check 3 FAILs above the floor.
4. **The corner artefact.**
   - Make the ray-triangle test watertight, or make its edge and vertex tie rule consistent, so that a mesh which
     is a subset of BEFORE's faces can never newly block a line.
   - Measure on CHTM-L05 face 10553 with the line the P2-E3 report names (outputs in C:/Temp/e3/).
   - Test: a fixture whose AFTER is a face subset of BEFORE has 0 covered samples for every viewpoint, including
     lines through shared vertices and edges.
5. **The site judge follows.** `engine/site_judge.py` uses the same floor measure for its per-site focus runs, so the
   kernel's rollback and the floor verdict agree. Charging rules R8 (P2-E3) stay as they are.
6. **Mutations that must FAIL check 3:**
   - a removed face of which only a 0.5 × 0.5 in patch is visible (through a slot);
   - a covering face that blocks only the back side of a visible face;
   - a covering face that blocks a second line of a sample whose first witness line is still clear.

   **One that must PASS:** a removed face whose largest visible patch is 3 px at 0.02 in/px.
7. **Re-judge the merged engines' golden outputs** with the new Validator (BEFORE against final output, the three
   golden units):
   - E8a alone: `--engines E8a`;
   - E8a+E3: `--engines E8a,E3`.

   Report checks 1-3 per run, the failing faces with their pixels, the time against the old Validator, and the
   crops of the five worst faces, looked at and described.

## Exit (real output)

- The tests red, then green; the full engine and tools suites pass.
- **Changed existing tests:** list each one with a reason. Expect some, because covered and deleted are now judged
  more strictly. The controller rules on each before merge; none may be loosened.
- **Item 7's table.**
- **Time:** the new Validator's run time on CHTM 5th against today's (the old run takes about 14 minutes inside a
  repair-unit run).

## Rules

- AGENTS.md §3-§7. This job changes `engine/validate/**` and `engine/site_judge.py` on the owner's 2026-10-10
  decision.
  - Every change makes the judge **stricter or more exact**. None may excuse anything today's Validator fails,
    except the corner artefact (item 4), which is a false positive and must be shown to be one.
  - Nothing in `engine/guard/**`; no FixProfile change; no engine (`engine/repair/engines/**`) change.
- The builder of this job builds no repair engine in the same job (AGENTS §6: the judge is independent).
- Test first; commit after each item. Real runs write only to temp folders.
- Stop only your own processes, by PID.
