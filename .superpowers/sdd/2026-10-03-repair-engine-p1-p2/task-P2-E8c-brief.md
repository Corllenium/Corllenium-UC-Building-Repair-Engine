# Task P2-E8c brief: the needs-modelling queue and its SketchUp helper

**Owner decision (AGENTS.md §5, Holes):** the narrow flat fill (E8), and anything else goes to the per-floor "needs
modelling" queue. **Plan** (E8): everything else goes to `needs_modelling.json`, with a SketchUp helper script that
opens a view at each spot.

**Base:** `feat/repair-p1p2` after the P2-E8b merge. Interfaces from there:
- `engine.cli repair-unit (--unit | --snapshot) --engines E8|E8a|E8b --out <dir>`, exit codes 0/1/2/3;
- `report.json` has:
  - `sites` (E8a pieces kept and rolled back, by reason);
  - `fills`;
  - `not_filled` (one row per refused hole: rule, reason, loop, centroid, normal);
  - `fill_stats`.
- `edit_log.jsonl`.

## Items (each test first; commit after each)

1. **`engine/campus/needs_modelling.py`: `build_needs_modelling(report, edit_log, before_mesh) -> dict`.** One entry
   per spot the engines left open:
   - every `not_filled` row, except patch outer borders, which are counted only;
   - every E8a piece rolled back on its own charge. Its hole is still open: give the piece's border edge run and
     the reason it was refused.

   Each entry has:
   - `id` (stable: sha256 of the sorted, print-step-snapped border points, first 12 hex);
   - `unit`, `kind` (`hole`, `slab_side` or `slab_bottom`), `reason`;
   - `centroid`, `normal`, `bbox` (model inches, Z up);
   - `border` (point list), `length_in`, `area_in2` where planar;
   - `suggested_view`: eye, target and up, placed 1.6 m from the centroid along the side a viewer reaches. Use the
     Validator's viewpoints that saw the spot in BEFORE; if none, use the normal.

   Entries are sorted by area, then length, descending.

   **Tests:**
   - a fixture with one refused hole and one rolled-back slab side gives two entries, with their kinds, reasons
     and stable ids;
   - the ids are the same when the face order is shuffled.
2. **`repair-unit` writes `<out>/needs_modelling.json`** (schema version 1, the unit, the counts by kind and reason,
   and the entries). Each entry also gets `crop`: a BEFORE image from `suggested_view`, written under
   `<out>/needs_modelling/`.

   **Test:** the CLI on the fixture writes the file, it validates against the schema, and every crop exists.
3. **The SketchUp helper `tools/sketchup/needs_modelling_views.rb`.** It is plain Ruby for SketchUp 2026, run from
   the Ruby Console or the MCP bridge, with the needs_modelling.json path set at the top.
   - It reads the JSON and adds a menu `Extensions > UC Needs Modelling` with `Next spot`, `Previous spot` and
     `List`.
   - `Next` and `Previous` set the camera to the entry's `suggested_view` and draw a temporary outline of its
     `border` with a view overlay or `view.draw` (a Tool). **No geometry is added to the model.**
   - `List` shows the entries in a UI.messagebox or an HtmlDialog: id, kind, reason, area.
   - It never saves the model, never adds geometry, scenes or layers, and restores the camera when the menu's
     `Done` is chosen.
   - The header says it is for the owner's own working copy and must never be run on the CHECKPOINT-17 master.
   - **Test** (Python): a test reads the script and asserts it contains no `save`, `add_face`, `add_line`,
     `entities.add`, `pages.add` or `layers.add`. A smoke run through the SketchUp MCP bridge happens only if the
     controller asks.
4. **Two small parked items from P2-E8a.**
   - (a) `repair-unit`'s exit-1 path (BEFORE differs from the campus map) first removes any `report.json`,
     `<unit>.fixed.obj` and `needs_modelling.json` left in `--out` by an earlier run.
   - (b) The help test asserts the full phrase `3: the stage was rolled back whole`, not loose digits. These are
     the only existing-test edits allowed; name them.
   - (c) From the P2-E8b re-review: `engine/cli.py` `fills_from_edit_log` refuses (exit 2) any `after_faces` id that
     is not a new face. A new face's id is at least the BEFORE face count; an id below it names an existing BEFORE
     face. Test it.

## Exit (real output)

- The tests red, then green; the full engine and tools suites pass.
- **`repair-unit --engines E8` on sidewalk A, sidewalk B and CHTM-L05:**
  - entries by kind and reason;
  - the top 5 by area, with their crops looked at and described;
  - time.
- **SketchUp helper:** pasted source plus the static test; no live SketchUp run unless the controller asks.

## Rules

- AGENTS.md §3-§7.
- Read-only on BEFORE meshes; writes only under `--out`.
- The helper never modifies or saves a model.
- No change to `engine/guard/**`, `engine/validate/**` or `FixProfile`.
- Stop only your own processes, by PID.
- **Job type:** `either`. Hermes may take it; the report goes to `docs/superpowers/records/hermes/P2-E8c-report.md`
  if Hermes does.
