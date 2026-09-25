"""Brief 13's "undo the fix once and see it fail": apply one mutation to the worktree's engine
source, run the tests that should catch it, restore the file byte for byte, and say whether the
tests failed. Usage: mutate_conditions.py <worktree root> (uses the main checkout's .venv).
Run it on a clean tree: each file is restored byte for byte, whatever the test does."""
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
python = r"D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"

MUTATIONS = [
    ("undo the fix: the pipeline no longer hands remove_overlaps the side exposure",
     "engine/fixes/pipeline.py",
     "        side_exposure=(front_now, back_now))",
     "        side_exposure=None)",
     "engine/tests/test_pipeline.py::test_an_exactly_stacked_opposite_wound_copy_loses_the_face_turned_away"),
    ("condition 3a gone: materials are not compared",
     "engine/fixes/overlap.py",
     "        if mesh.face_material[i] != mesh.face_material[j]:",
     "        if False:",
     "engine/tests/test_pipeline.py::test_a_stacked_copy_in_another_material_keeps_both_faces"),
    ("condition 1 loosened: the engine's 0.15 in plane tolerance instead of 0.001 in",
     "engine/fixes/overlap.py",
     "COINCIDENT_PLANE_TOL = 1e-3",
     "COINCIDENT_PLANE_TOL = 0.15",
     "engine/tests/test_pipeline.py::test_an_offset_or_partial_copy_is_not_a_pair_and_keeps_both_faces"),
    ("condition 1 loosened: any overlap instead of 0.99 both ways",
     "engine/fixes/overlap.py",
     "COINCIDENT_COVER = 0.99",
     "COINCIDENT_COVER = 0.0",
     "engine/tests/test_pipeline.py::test_an_offset_or_partial_copy_is_not_a_pair_and_keeps_both_faces"),
    ("condition 3b gone: UV mappings are not compared",
     "engine/fixes/overlap.py",
     "        if not entry[\"uv_residual\"] <= COINCIDENT_UV_TOL:",
     "        if False:",
     "engine/tests/test_pipeline.py::test_a_stacked_copy_whose_uvs_are_shifted_half_a_tile_keeps_both_faces"),
    ("condition 3b as numbers: UVs compared without the whole-tile shift",
     "engine/fixes/overlap.py",
     "    return float(np.abs(diff - np.round(diff[0])).max())",
     "    return float(np.abs(diff).max())",
     "engine/tests/test_pipeline.py::test_a_stacked_copy_whose_uvs_are_shifted_whole_tiles_is_the_same_surface"),
    ("condition 4: a tie falls to one face",
     "engine/fixes/overlap.py",
     "        if side_i == side_j:",
     "        if False:",
     "engine/tests/test_overlap.py::test_an_exposure_tie_keeps_both_faces"),
    ("condition 4: exposure alone decides, the guard views are not asked",
     "engine/fixes/overlap.py",
     "        if mine < theirs:",
     "        if False:",
     "engine/tests/test_overlap.py::test_the_side_the_guard_views_see_less_is_never_the_one_kept"),
    ("pairs may contradict each other",
     "engine/fixes/overlap.py",
     "        if keep in dropped or drop in kept:",
     "        if False:",
     "engine/tests/test_overlap.py::test_two_pairs_that_disagree_about_one_face_never_remove_the_face_one_of_them_keeps"),
    ("the guard's put-backs are not written into the pairs",
     "engine/fixes/overlap.py",
     "        if entry[\"verdict\"] == \"removed\" and not removed[entry[\"removed\"]]:",
     "        if False:",
     "engine/tests/test_overlap.py::test_a_pair_the_guard_puts_back_is_reported_as_kept"),
]

for label, rel, old, new, test in MUTATIONS:
    path = root / rel
    original = path.read_bytes()
    text = original.decode("utf-8")
    assert text.count(old) == 1, (label, text.count(old))
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    try:
        run = subprocess.run([python, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
                             cwd=root, capture_output=True, text=True,
                             env={**__import__("os").environ, "PYTHONPATH": str(root)})
    finally:
        path.write_bytes(original)
    tail = [line for line in run.stdout.splitlines() if " passed" in line or " failed" in line]
    verdict = "CAUGHT" if run.returncode != 0 else "NOT CAUGHT"
    print(f"{verdict:10s} {label}\n           -> {tail[-1] if tail else run.stdout[-300:]}")
