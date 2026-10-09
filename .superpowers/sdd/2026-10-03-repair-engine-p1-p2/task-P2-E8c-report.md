# P2-E8c report: the needs-modelling queue and its SketchUp helper

The implementer could not write report files: the Write tool refused report `.md` files from subagents. The controller
filed this from the implementer's hand-back message, condensed, with its numbers and outputs kept verbatim.

**Status: DONE_WITH_CONCERNS.**
- Worktree `.claude/worktrees/P2-E8c`, branch `claude/P2-E8c`, base `ed278b7`, HEAD `a9cf234`, clean.

## Commits

| commit | what |
|---|---|
| 954acbf | item 1: `engine/campus/needs_modelling.py` `build_needs_modelling`; `engine/tests/test_needs_modelling.py` (12 tests) |
| c5d78c9 | item 2: `repair-unit` writes `needs_modelling.json` and crops; item 4a (exit-1 cleanup); `fill_review.SpotCropper`; `engine/tests/test_cli_needs_modelling.py` |
| d41da51 | item 4b: the help test asserts the full exit-code phrases. This is the only existing-test edit: `test_cli_repair_unit.py::test_the_help_documents_the_exit_codes` |
| d9e6405 | item 3: `tools/sketchup/needs_modelling_views.rb`; `tools/tests/test_needs_modelling_views.py` (28 tests) |
| 0c7aa1e | item 4c: `fills_from_edit_log(path, after, before_faces=None)`; `engine/tests/test_validate_edit_log_new_faces.py` (5 tests) |
| 1b9e07b | the spot-crop window grows to 1200 in (the 400 in cap cut a 40 ft slab bottom) |
| a9cf234 | test: pieces dropped with their whole stage (exit 3) are counted, not listed |

## Test summary

```
tools:  151 passed in 16.98s
engine: 1830 passed, 1 xfailed in 759.23s (0:12:39)
```

Every new test was red first, then green:
- item 1: ImportError, then 12 passed;
- item 2: 7 failed (FileNotFoundError), then 10 passed;
- 4b: proved by changing the help text temporarily (1 failed), then restored;
- 4c: 4 failed, then 10 passed;
- item 3: 17 failed with the script moved away, and a `; model.save` mutation turns 3 tests red; then 28 passed.

## The implementer's readings of the brief (for the controller to confirm)

1. **Geometry.**
   - `report.json` `pieces[*]` now carries `border`, `border_ordered`, `border_rings`, `area_in2` and `normal` for
     pieces that were not kept.
   - A hole's normal is fitted from its points, with the sign up.
2. **The edit log is a cross-check.** A listed piece must have its `rolled_back` line, otherwise ValueError.
3. **"Own charge".** A piece dropped with its whole stage (exit 3) is counted in
   `counts.stage_rolled_back_not_listed`, not listed.
4. **Slab entry reason.** It is the Validator reason charged on the most samples; all reasons go in `detail`.
5. **Merged spots.** Identical borders become one entry, the other named in `also`, counted in `counts.merged`.
6. **4c: the exact bound, not the brief's literal one.** A kept cut that removes k faces lowers the first new face
   id to `before_faces - k`. With no kept cut, this is the brief's rule.
7. **4a.** Exit 1 also removes `edit_log.jsonl` and the `fills/` and `needs_modelling/` folders (this tool's own
   files only). A foreign file stays (tested).
8. **The outline is a Tool (`view.draw`), not an Overlay.** One extra menu item: "Show outline again".
9. **`suggested_view.source`** is `direction`, `camera`, `probe` or `normal`.

## Acceptance: `repair-unit --engines E8` (outputs in C:/Temp/e8c/{swA,swB,chtm5}, exit 0 on all)

| unit | entries | by kind | kind/reason | outer borders | view source | time (s) |
|---|---|---|---|---|---|---|
| sidewalk A | 143 (1 merged) | hole 82, slab_side 54, slab_bottom 7 | hole/not_a_simple_loop 82; slab_side/covered 49, /uv 5; slab_bottom/covered 7 | 2 | direction 65, normal 58, probe 13, camera 7 | 59.6 |
| sidewalk B | 142 | hole 98, slab_side 33, slab_bottom 11 | hole/not_a_simple_loop 93, /self_crossing 5; slab_side/covered 32, /uv 1; slab_bottom/covered 11 | 2 | normal 86, camera 30, direction 20, probe 6 | 155.1 |
| CHTM-L05 | 395 | hole 194, slab_bottom 109, slab_side 92 | hole/not_a_simple_loop 193, /neighbour_not_coplanar 1; slab_bottom/covered 102, /uv 7; slab_side/covered 75, /overlaid 1, /uv 16 | 4 | normal 173, direction 84, probe 127, camera 11 | 1266.8 (shared load) |

The script checked that every crop exists: 143, 142 and 395 crops.

```
CHTM_SIDE_WALK_2nd_floor: needs modelling: 143 spots {'hole': 82, 'slab_bottom': 7, 'slab_side': 54} {'covered': 56, 'not_a_simple_loop': 82, 'uv': 5} (2 patch outer borders only counted); 3.81 s
CHTM_2nd_to_3rd_building_sidewalk_outside: needs modelling: 142 spots {'hole': 98, 'slab_bottom': 11, 'slab_side': 33} {'covered': 43, 'not_a_simple_loop': 93, 'self_crossing': 5, 'uv': 1} (2 patch outer borders only counted); 4.61 s
CHTM-L05: needs modelling: 395 spots {'hole': 194, 'slab_bottom': 109, 'slab_side': 92} {'covered': 177, 'neighbour_not_coplanar': 1, 'not_a_simple_loop': 193, 'overlaid': 1, 'uv': 23} (4 patch outer borders only counted); 19.77 s
```

## Visual pass (the implementer looked at the top 5 by area per unit; contact sheets in C:/Temp/e8c/*_top5.png)

The 15 largest entries are all slab bottoms and sides that E8a rolled back as covered or uv, 823 to 189,883 in².
- Ordered borders draw as yellow outlines.
- Branching bottom outlines are unordered and draw as crosses.
- The CHTM ones follow room and wing outlines in plan view.

## SketchUp helper

- `tools/sketchup/needs_modelling_views.rb`, about 215 lines.
- Menu `Extensions > UC Needs Modelling`: Next spot, Previous spot, Show outline again, List (an HtmlDialog with Go
  links) and Done (restores the camera).
- It refuses a target more than 600 in outside the model's bounds.
- **Not run in SketchUp, and no Ruby on this PC to syntax-check it.**

## Concerns

1. The Ruby script is unrun (`view.draw_points`, `UI::HtmlDialog#set_on_closed` written from memory). It needs a
   smoke run before the owner relies on it.
2. Coordinates assume the `.skp` matches the OBJ (inches, Z up). Only an offset over 600 in is caught.
3. 193 of 395 CHTM-L05 entries are `not_a_simple_loop`, often 2-6 open-edge points with no area, and 173 have
   `source: normal`. No filter was applied.
4. A hole and the slab piece E8a failed to close can describe one place; only identical borders merge.
5. Unordered borders. A piece's `area_in2` is the area of its faces, not of the border polygon.
6. 4c deviates from the brief's wording on purpose (reading 6 above).
7. New `report.json` keys: `needs_modelling`, `seconds.needs_modelling`, piece `border*` / `area_in2` / `normal`.
   `seconds.total` includes the queue.

Not touched: `engine/guard/**`, `engine/validate/**`, `FixProfile`. No mesh changes; writes go only under `--out`.
