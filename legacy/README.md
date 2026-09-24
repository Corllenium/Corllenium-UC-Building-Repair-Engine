# legacy — unguarded scripts, do not run

These root scripts predate the guarded pipeline (`engine.cli fix`). They delete faces without the
26-view guard (`build_solid_outer_shell.py`), loop over `rings` as a vertex list (it has been a
dict since 629d428), or overwrite `preview/data` in place. Keep for reference only.

Owner of the main working tree: move them here with `Move-Item` (they are untracked, so `git mv`
refuses them) and then `git add legacy/` when convenient —
build_solid_outer_shell.py, build_clean_skp.py, create_skp.py, execute_full_internal_clean.py,
export_fixed_result.py, inspect_guard.py, test_edge_rebuild.py, test_startup.rb,
update_preview_and_models.py, fixed_mesh_data.json.

The SketchUp SDK ctypes writer inside `update_preview_and_models.py` is the one part worth keeping;
it is extracted into `engine/io/skp_writer.py` in P7 (Corllenium spec section 7).
