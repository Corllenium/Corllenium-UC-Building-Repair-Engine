# STAGING-ENGINE-2-3

- 2026-10-19: claimed job; inspected runner; requested `--stage-failed` is obsolete and rejected. Retried with equivalent default staging behavior, guards enabled. Export completed: floor 2 has 53,605 triangles; floor 3 has 58,216. Floor 2 repair running. See `docs/superpowers/records/STAGING-ENGINE-2-3-report.md`.
- 2026-10-19: runner regression suite: 26 passed in 6.58s. Prepared read-only checks for OBJ references, materials/textures, variant bounds, hashes, staging receipt counts, and fresh Blender readback of target/non-target meshes. Floor 2 still computing; no verdict claimed.
- 2026-10-19 20:05 +08:00: floor 2 fragment ray verification reached round 52 (755 initial units); process remains CPU-active. Launched automatic read-only artifact/Blender verifier waiting for summary.json. Recovery PIDs and filenames recorded in report. No engine edits, guard changes, or floor pass claimed.
- 2026-10-19 21:24 +08:00: first floor 2 attempt failed after at least round 240 with an Embree/trimesh 2.14 MiB allocation failure under low shared commit headroom. Preserved engine-attempt1.log; orchestrator automatically began retry 1/3. No output or guard pass claimed.
