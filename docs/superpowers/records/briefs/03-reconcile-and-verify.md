# Brief 03 — reconcile the branches, rerun, verify, deliver the SketchUp files

Do this after briefs 01 and 02 are finished (their claims released). Main checkout, branch
`feat-dashboard`. Nothing else may be committing in the main checkout while you do it.

1. **Merge** `feat/side-rebuild` into `feat-dashboard` with `git merge --no-ff --no-commit
   feat/side-rebuild`. Expected conflicts: `engine/tests/fixtures/build.py` and
   `engine/tests/test_cli.py` (both sides append at the end: keep both blocks, ours first), possibly
   `engine/cli.py` (the side rebuild adds a back-face print line; the writer softening changed the
   `.skp` print line: keep both). Check `python -c "import ast; ast.parse(open(f).read())"` on every
   resolved file and that no top-level name is defined twice. Run the engine suite before committing
   the merge; commit with a message that lists the conflicts and how they were resolved.
2. **Rerun** both files and `preview-data` (commands in HANDOFF.md section 5). They write the
   owner's `.skp` files into `OBJ FIXED RESULT/`.
3. **Verify** (evidence, not claims): both `report.json` files `passed: true`, all invariants true,
   `merge_report.rolled_back` false, the final guard's holes / material_changed / moved counts 0;
   `backface_px` final much lower than input; the `.skp` audit (`skp_edge_audit.py`) with lines
   inside flat surfaces and T-junction lines near 0. Render both `.skp` files with `render_skp.py`
   into `data/skp_render/A` and `data/skp_render/B` and READ at least `obl_top_a.png`,
   `obl_bot_a.png` and `side_low_a.png` of each; check the sawtooth spot on file B (under the slope
   between the upper landing and the lower slab) is a clean wall now. Describe what you see.
4. **Records**: ledger entry with every number above; session record sections 4 to 6 updated;
   HANDOFF.md section 2 updated; claims released; commit those files.
5. **Tell the owner**: the two `.skp` paths, the table of numbers, two renders, and what is still
   visibly wrong.

If a verification fails (rollback, guard failure, lines still there), do not paper over it: find the
cause with the diagnostic scripts in `docs/superpowers/records/scripts/` (`diag_flicker.py` for guard
pixels, `diag_new_vertex.py` for skipped merge regions, `skp_edge_audit.py` for drawn lines), record
it, and put a new numbered brief in this folder.
