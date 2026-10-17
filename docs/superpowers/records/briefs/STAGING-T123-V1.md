# STAGING-T123-V1: synchronize and verify Blender staging Tasks 1-3

Owner request, 2026-10-17: verify the main checkout and `.hermes/worktrees/siege-jev-gate`.

- Compare `engine/fixes/building_repair.py`, `engine/campus/blender_staging.py`, `engine/campus/bpy_apply_repaired_floors_to_staging.py`, `engine/tests/test_building_repair.py`, and `engine/tests/test_blender_staging.py`; copy missing test files to main, preserving existing source files.
- Run the five requested test modules with the main checkout's `.venv/Scripts/python.exe`, explicit checkout `PYTHONPATH`, and no pytest cache, in both checkouts.
- Compile and safely import the two CHTM runners, and check their `--stages` support without triggering repairs.
- Verify the staging receipt against all three saved Blender files in separate background read-only processes. Confirm 12 CHTM floors, self-contained buildings staging, restored ARCHI ceiling, and 99,310 combined CHTM LOD0 triangles.
- Record actual output and limitations. Do not alter Blender files, foreign untracked files, running services, databases, or live exports.

The owner explicitly named both checkouts; verification stays in those checkouts. This task introduces no geometry or guard changes.
