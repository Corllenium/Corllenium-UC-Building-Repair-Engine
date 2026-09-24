### Task 6: Pipeline + invariants

**Files:** Create `engine\fixes\pipeline.py`, `engine\tests\test_pipeline.py`

**Interfaces — Produces:**
`@dataclass FixProfile(n_dirs=128, slit_threshold=0.05, accept_slit=False, flat_texture_std=8.0, guard_size=(900,600))`,
`@dataclass FixResult(mesh, source_faces, exposure_class, removed_hidden, removed_slit, restored_by_guard, merge_report, guard_after_removal: GuardReport, guard_final: GuardReport, invariants: dict, passed: bool)`,
`fix_object(mesh: MeshData, flatness: dict[str, float], profile=FixProfile()) -> FixResult`.

Order: `analyse_topology` -> `compute_exposure` -> candidates = hidden (+ slit when `accept_slit`) ->
`guard_feedback` against the original -> `remove_faces` (also drops degenerate faces) -> `analyse_topology` on the
result -> `merge_regions` -> final guard of merged mesh against the ORIGINAL -> invariants
(`material_count_same`, `bbox_same`, `area_not_grown`, `guard_passed`). If the final guard fails, the result falls
back to the un-merged mesh (removal only), `merge_report["rolled_back"] = True`, and `passed` reflects the fallback's guard.

- [ ] Tests on `box_with_partition()` (partition removed, 12 outer tris stay 12, passed), on a gridded closed box
  built from `grid_slab` faces (hidden none, merges to 12 tris), determinism (two runs -> identical arrays).
  Implement, pass, commit `feat(engine): fix pipeline with invariants and rollback`.

