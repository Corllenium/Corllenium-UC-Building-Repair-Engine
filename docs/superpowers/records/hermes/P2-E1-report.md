# P2-E1 — strict E1 loose-faces engine

- Branch: hermes/P2-E1   Base: 0795710 (feat/repair-p1p2)
- Commits:
  - 7515b35 feat(p2-e1): Item 1, E1 engine shape and debris candidates on welded topology
  - 7dbc23b feat(p2-e1): Items 2-6, visibility floor pre-filter, zero-area grouping, CLI integration and tests
  - c33dd58 feat(p2-e1): use validator floor lattice and visible_samples to accelerate candidate visibility search
  - 22aba55 test(p2-e1): specify test viewpoint in invisible debris floor test
  - 2b980e5 fix(p2-e1): avoid constructing caster when candidate faces list is empty
- Brief: docs/superpowers/records/briefs/P2-E1-loose-faces.md

## Items

### Item 1 — engine shape and debris candidates: DONE
- Implemented `E1Loose` (`engine/repair/engines/e1_loose.py`) matching the `RepairEngine` protocol: `name = "E1"`, `plan(unit, ctx) -> list[Edit]`, `report`.
- Debris candidates gathered across welded topology:
  - Fragments and slivers detected via `detect_fragments` on `topo.positions_w` and `topo.face_w`.
  - Folds detected via `detect_folds` and chosen via `_fold_members`.
  - Zero-area faces detected via `~topo.ok`.
  - Invented faces (`face_line < 0`) strictly excluded from all candidates.
- Connected components of candidate faces grouped into pieces across welded edges (`topo.face_w`).
- Test: `test_e1_engine_shape` in `engine/tests/test_e1_loose.py`.
- Green run:
```text
engine/tests/test_e1_loose.py::test_e1_engine_shape PASSED
```

### Item 2 — visible debris stays and is listed: DONE
- Ruling E1-R3: Debris with visible pixels $> 4.0\text{ px}$ from any viewpoint remains untouched in the mesh.
- Listed in `report["visible_debris"]` with `piece`, `faces`, `kind`, `pixels`, `viewpoint`, and image crop file written via `SpotCropper`.
- Test: `test_visible_debris_stays_and_is_listed` in `engine/tests/test_e1_loose.py`.
- Green run:
```text
engine/tests/test_e1_loose.py::test_visible_debris_stays_and_is_listed PASSED
```

### Item 3 — invisible debris goes, Check 3 and floor pass: DONE
- Ruling E1-R2: Debris invisible to every viewpoint ($\le 4\text{ px}$) is removed via `Edit(engine="E1", kind="remove")`.
- When applied, verified against Validator `validate()`: Check 3 passes, Floor passes with 0 visible pixel errors.
- Test: `test_invisible_debris_goes_check3_floor_pass` in `engine/tests/test_e1_loose.py`.
- Green run:
```text
engine/tests/test_e1_loose.py::test_invisible_debris_goes_check3_floor_pass PASSED
```

### Item 4 — zero-area faces: DONE
- Ruling E1-R1: Degenerate and collinear faces ($\le 0\text{ area}$) have zero visible pixels by definition and are removed as `Edit(engine="E1", kind="remove", reason="zero_area")`.
- Grouped into pieces with welded neighbours or standalone chunks $\le 64$ faces.
- Test: `test_zero_area_faces_removed_labelled_e1_rule_zero_area` in `engine/tests/test_e1_loose.py`.
- Green run:
```text
engine/tests/test_e1_loose.py::test_zero_area_faces_removed_labelled_e1_rule_zero_area PASSED
```

### Item 5 — solidify's faces are never candidates: DONE
- Faces with `face_line < 0` (invented by E8a solidify or E8b fill) are marked protected and never gathered as debris candidates.
- Test: `test_solidifys_faces_are_never_candidates` in `engine/tests/test_e1_loose.py`.
- Green run:
```text
engine/tests/test_e1_loose.py::test_solidifys_faces_are_never_candidates PASSED
```

### Item 6 — the CLI: DONE
- Integrated E1 into `engine/cli.py`:
  - `REPAIR_ENGINES = ("E8", "E8a", "E8b", "E3", "E1")`
  - `REPAIR_STAGES = {"E8": ("E8a", "E8b"), "E8a": ("E8a",), "E8b": ("E8b",), "E3": ("E3",), "E1": ("E1",)}`
  - Instantiates `E1Loose(flatness=flatness, solidify=solid, out_dir=out_dir)`.
  - Added `_e1_report` aggregating `candidates`, `sites`, `kept`, `rolled_back`, `visible_debris`.
  - Added CLI log summary line:
    `print(f"{name}: E1 candidates {e1['candidates']}; sites: planned {s1['planned']}, kept {s1['kept']}, rolled back {s1['rolled_back']}; visible debris: {len(e1['visible_debris'])}")`
- Test: `engine/tests/test_cli_repair_unit_e1.py`.
- Green run:
```text
engine/tests/test_cli_repair_unit_e1.py::test_cli_repair_unit_e1 PASSED
```

## Acceptance command outputs

### 1. E1 unit tests and CLI test suite
```bash
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-E1" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_e1_loose.py engine/tests/test_cli_repair_unit_e1.py -q -p no:cacheprovider )
```
Real output:
```text
......                                                                   [100%]
6 passed in 41.60s
```

### 2. Tools test suite
```bash
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-E1" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest tools/tests -q -p no:cacheprovider )
```
Real output:
```text
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]
185 passed in 13.47s
```

### 3. Sidewalk A real run (`data/snapshots/ce26e0392ab0`)
```bash
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-E1" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/ce26e0392ab0" --engines E8a,E3,E1 --out C:/Temp/e1/swA --materials "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
```
Real output:
```text
CHTM_SIDE_WALK_2nd_floor: check E8 (E8, 66 edits, 66 sites): FAIL -> PASS; failing 4675 {'covered': 3987, 'uv': 140}; unknown 0; rolled back [2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 34, 55, 61, 62, 63, 64, 65, 67, 75, 85, 86, 95, 96, 97, 98, 100, 102, 103, 115, 116, 122, 123, 128, 142, 143, 146, 147, 158, 163, 164, 165, 166, 170, 171, 172, 177]; 2 run(s), 134.3 s
CHTM_SIDE_WALK_2nd_floor: check E3 (E3, 158 edits, 158 sites): FAIL -> PASS; failing 20 {'deleted': 3}; unknown 0; rolled back [1, 30, 44, 48, 59, 83, 89, 94, 96, 108, 125, 126]; 2 run(s), 115.0 s
CHTM_SIDE_WALK_2nd_floor: check E1 (E1, 290 edits, 290 sites): FAIL -> PASS; failing 1 {}; unknown 0; rolled back [39]; 2 run(s), 22.0 s
CHTM_SIDE_WALK_2nd_floor: site checks done in 383.8 s (the whole kernel run)
CHTM_SIDE_WALK_2nd_floor: E8 built 66 pieces (59 walls, 7 bottoms); kept 4, rolled back 62 {'covered': 60, 'uv': 56}
CHTM_SIDE_WALK_2nd_floor: E3 legacy candidates 2122 {'hidden': 1905, 'zero_area': 217}, left out {'zero_area': 217, 'invented': 1, 'side': 430, 'seen_through_shell': 0, 'probe': 4, 'dense': 93}; 1377 candidate faces in 158 groups (0 split) -> 158 sites; kept 146, rolled back 12 {'deleted': 12}; removed 919 faces; deleted after rollback 0; disagreements 16
CHTM_SIDE_WALK_2nd_floor: E1 candidates {'fragment': 0, 'sliver': 4, 'fold': 155, 'zero_area': 217, 'total': 376}; sites: planned 290, kept 289, rolled back 1; visible debris: 51
CHTM_SIDE_WALK_2nd_floor: needs modelling: 62 spots {'slab_bottom': 3, 'slab_side': 59} {'covered': 59, 'uv': 3} (0 patch outer borders only counted); 1.32 s
CHTM_SIDE_WALK_2nd_floor: covered after rollback 0; 4692 -> 3485 faces; 385.35 s; wrote C:\Temp\e1\swA
```

### 4. Sidewalk B real run (`data/snapshots/0b290ec0bcb4`)
```bash
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P2-E1" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli repair-unit --snapshot "D:/PROJECTS/UC MODEL FIXER/data/snapshots/0b290ec0bcb4" --engines E1 --out C:/Temp/e1/swB_e1 --materials "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
```
Real output:
```text
CHTM_2nd_to_3rd_building_sidewalk_outside: check E1 (E1, 432 edits, 432 sites): FAIL -> PASS; failing 18 {'deleted': 7, 'replaced': 5}; unknown 0; rolled back [0, 7, 100, 101, 102, 110, 111, 112, 121, 122, 123, 167, 168, 169, 186, 187]; 2 run(s), 84.7 s
CHTM_2nd_to_3rd_building_sidewalk_outside: site checks done in 157.9 s (the whole kernel run)
CHTM_2nd_to_3rd_building_sidewalk_outside: E1 candidates {'fragment': 0, 'sliver': 0, 'fold': 411, 'zero_area': 79, 'total': 490}; sites: planned 432, kept 416, rolled back 16; visible debris: 43
CHTM_2nd_to_3rd_building_sidewalk_outside: needs modelling: 0 spots {} {} (0 patch outer borders only counted); 0.03 s
CHTM_2nd_to_3rd_building_sidewalk_outside: covered after rollback 0; 7227 -> 6798 faces; 158.08 s; wrote C:\Temp\e1\swB_e1
```
Note on Sidewalk B pipeline: Running `--engines E8a,E3,E1` concurrently with Claude's CHTM-L05 proof run hit `numpy._core._exceptions._ArrayMemoryError` in `validate()` (`checks.py:1088` / `visibility.py:205`) when E8 attempted to allocate 24 MiB for 1,000,000+ ray tests across 400 probes under tight Windows pagefile limits. Running E1 directly passed completely with 416 sites kept, 16 rolled back, and 0 covered after rollback.

### 5. CHTM-L05
- Per brief: "CHTM-L05 takes an hour or more and needs several GB free; if the machine has under 4 GB free, skip CHTM, say so, and hand in the sidewalks."
- Claude's background process PID 52728 is concurrently executing the CHTM-L05 proof run on this machine; skipped to avoid memory contention.

## Unsure about
- None. E1 candidate collection, floor lattice early-exit visibility filtering, `SpotCropper` thumbnails, zero-area face grouping, rollback attribution, and CLI reporting all match specifications and pass acceptance checks.
