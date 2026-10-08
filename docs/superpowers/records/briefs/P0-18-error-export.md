# Brief P0-18: per-building colour-coded error export (.skp)

**Job:** P0-18 (claude, build). **Branch:** `claude/P0-18` from `feat/repair-p0`.
**Owner request (2026-10-08):** "highlight all floors that have specific error export", "even errors with groupings".
**Owner answers:** one `.skp` per building, floors side by side; light grey geometry, errors in bright colours.

Read-only export. Nothing here changes the model or any repair rule: it draws the census error maps.

## What it builds
`MODEL FIXER ENGINE FILES\04-COLORING\<BUILDING>\<BUILDING>-errors.skp`, one per building plus `SITE`
(10 files), from:
- `data/campus/campus_map.json` (owner-confirmed units, members, flags, excluded groups);
- `data/campus/errors/<group>.json` (census error maps; face indices into the snapshot mesh);
- `data/campus/source.json` (snapshot folders, sha256);
- `data/campus/skp_check.json` (export-vs-backup mismatches).

## Layout
- One column per unit, in level order (floors L01.., then elements), 8 m (315 in) apart; each unit is moved so its
  bbox min x/y sits at the column origin and its base at z = 0.
- Excluded duplicate groups (owner, 2026-10-08) get their own columns at the end, labelled `EXCLUDED`.
- Under each column: label lines in pixel-font geometry (`engine/campus/pixfont.py`): level and unit name, then one
  short line per grouping problem in that problem's colour.
- A legend at the start of the row: one swatch and name per error kind and grouping kind, with the building's counts.

## Groups and tags
- Unit group `UNIT | <unit>` > member group `MEMBER | <group>` (faces "all" or its band by face-centre z, as the
  inventory split them) > one group per kind.
- Each face goes to exactly one group, first match in this order: flicker_diff, flicker_same, reversed, loose,
  hidden; otherwise `base` (light grey). A face listed under two kinds is drawn in the first; the counts in the legend
  and the report still count every listing.
- Open edges: a thin triangular tube per segment (`open_edges`). Cracks: a small octahedron per crack point,
  one per 6 in cell (`cracks`). Degenerate (zero-area) triangles of an error kind: an octahedron at the centre, one per
  6 in cell, in that kind's group; degenerate base triangles are not drawn and are counted.
- Grouping problems (`grouping_<kind>`): split, misnamed, missing, duplicate, shared, footprint, skp_mismatch, excluded.
  Each is a coloured plate under the unit (z = -2 in) whose group name carries the full text, plus its label line.
- Every kind group sits on a tag of the same name (`base`, `error_<kind>`, `grouping_<kind>`, `labels`), so the owner
  can switch each kind on and off.

## Items (test first, each committed)
1. `engine/campus/pixfont.py`: moved from the owner's scripts folder, with `% + _ / : ( )` added. Tests: every glyph
   7 rows of 5; `text_rects` of "L05" covers the expected cells; unknown characters are spaces.
2. `engine/campus/error_export.py` planning (no SDK): `face_kinds`, `member_mask`, `grid_dedup`, `flag_label`,
   `plan_building`. Tests on a synthetic two-unit building: priority, split bands, dedup, column offsets, flags and
   excluded columns, counts.
3. SDK writer `write_building_skp(plan, out)`: groups, tags, materials, faces, tubes, markers, plates, labels. Test
   (skipped without the SDK): a tiny plan round-trips; read back, the face count per tag matches the plan.
4. CLI `campus-errors-skp [--buildings ...] --out <dir>`; writes `<BUILDING>/<BUILDING>-errors.skp` and
   `<BUILDING>-errors.json` (counts, skipped degenerate faces, sha256 of the inputs, engine commit).

## Done when
- Engine tests green; the 10 files written to scratch (`data/coloring_scratch/`), each read back with
  `read_skp_summary`; one render per building read and described.
- Published to `04-COLORING` only from the committed code, from `.claude/worktrees/verified`.
