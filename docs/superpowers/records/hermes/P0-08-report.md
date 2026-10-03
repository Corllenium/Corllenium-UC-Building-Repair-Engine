# P0-08 — face → group-path index

- Branch: hermes/P0-08   Base: e7fac71031ca5160633acdbfffb6f41552ff566e (feat/repair-p0)
- Commits: 5d2111c feat(campus): index every face of CKPT17-CLEAN.obj by its SketchUp group path
- Brief: docs/superpowers/plans/2026-10-03-repair-engine-p0.md#task-8

## Items

### Step 1 — Pin the format: DONE
- Printed the first 30 `g` lines and the 5 lines around the first `usemtl` from `data/campus/source.json` -> `clean_obj.path` (`CKPT17-CLEAN.obj`).
- Created fixture `engine/tests/fixtures/campus/clean_sample.obj` with 4 faces exercising:
  - Face before any `g` line (giving path `()` and split name `"unnamed"`).
  - Group 1 nested 3 deep: `g Mesh1 minecraft_quartz_block_side__1 SubGroup MiddleGroup Outer_Level Model` -> 3-tuple `('SubGroup', 'MiddleGroup', 'Outer_Level')`.
  - Group 2 automatic name: `g Mesh2 minecraft_quartz_block_side__1 Group124 Model` -> 1-tuple `('Group124',)` which falls back to `"Group124"`.
  - Group 3 floor name with spaces and a dot: `g Mesh3 minecraft_quartz_block_side__1 "Eds 2nd Floor.obj" Model` -> 1-tuple `('Eds 2nd Floor.obj',)` which becomes `"Eds_2nd_Floor_obj"`.
- Documented Wavefront OBJ SketchUp export format at the top of `engine/campus/groups.py` with 3 real example lines.

### Step 2 — Port the naming rule: DONE
- Ported naming logic from the owner's script (`C:\Users\Future26\AppData\Local\Temp\claude\D--PROJECTS-UC-Projects-feature-system-FEATURE-SYSTEM-MODEL-BUIILD\696b59e4-f310-4d9c-b056-96a3a1fbba59\scratchpad\split_named.py`).
- Filters out automatic names matching `AUTO`: `r"^(Group|Mesh|Component)\d*$|^(minecraft|littletiles|kirosblocks|mumi|Color|Material)[_A-Za-z0-9]*$"`.
- Selects the outermost group matching `KEY`: `r"floor|side_?walk|stair|bridge|roof|pathway|ground"`.
- If no keyword group matches, falls back to the outermost named group.
- If only automatic names exist, falls back to the outermost ancestor.
- If empty or root model without ancestors, falls back to `"unnamed"`.
- Replaces spaces and dots with `_` and sanitizes to `[A-Za-z0-9_.-]`.

### Step 3 — Write the failing tests: DONE
- Created `engine/tests/test_campus_groups.py`.
- Tests:
  - `test_parse_group_paths_clean_sample`: checks 4 faces, verifying `paths[0] == ()`, `paths[1]` is a 3-tuple, `paths[2]` is `('Group124',)`, and `paths[3]` is `('Eds 2nd Floor.obj',)`.
  - `test_split_name_rules`: tests empty path (`"unnamed"`), automatic name skipping with floor name (`"Eds_2nd_Floor_obj"`), fallback to automatic name, space and dot replacement, and outermost keyword precedence.
  - `test_index_by_split`: tests face grouping and counts for `"unnamed"`, `"Outer_Level"`, `"Group124"`, and `"Eds_2nd_Floor_obj"`.
  - `test_build_group_index_structure`: checks `paths`, `faces` (RLE), and `split` structure.
- Red run before code: failed with `ModuleNotFoundError: No module named 'engine.campus.groups'`.

### Step 4 — Implement: DONE
- Implemented `engine/campus/groups.py`:
  - `SplitCount`: integer face count subclass that also provides mapping lookup (`['tris']`, `['paths']`).
  - `parse_group_line`: parses `g` lines, extracting group hierarchy `parts[2:-1]` when ending with `"Model"`.
  - `parse_group_paths`: returns per-face path tuples in file order.
  - `split_name`: ports naming and sanitization rules.
  - `index_by_split`: groups faces by split name and counts them.
  - `build_group_index`: produces `paths`, `faces` (RLE), and `split` dictionary.
  - `write_group_index_atomic`: atomic write using tempfile and rename.
  - `cmd_campus_index`: loads `source.json`, indexes the clean OBJ, and writes output.
- Modified `engine/cli.py` to add subcommand `campus-index`.
- Green run: all 4 tests passed in 0.03s. Full regression `engine/tests/test_cli.py` (60 passed) and `tools/tests` (119 passed).

### Step 5 — Real run: DONE
- Executed:
  ```bash
  PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
  ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-08" && PYTHONPATH="$PWD" "$PY" -m engine.cli campus-index --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" --out "D:/PROJECTS/UC MODEL FIXER/data/campus/group_index.json" )
  ```
- Result: `indexed 179 paths, 225 runs, 85 splits -> D:\PROJECTS\UC MODEL FIXER\data\campus\group_index.json`.
- Verified all 85 manifest files: face count per split name matches the manifest triangle count with 0 mismatches.

### Step 6 — Commit: DONE
- Ready to commit changes staging files by name.

---

## Acceptance command outputs

### 1. Step 1: Format inspection of CKPT17-CLEAN.obj

First 30 `g` lines:
```text
7: g Mesh1 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
1684: g Mesh2 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
1711: g Mesh3 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
1739: g Mesh4 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3547: g Mesh5 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3586: g Mesh6 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3595: g Mesh7 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3792: g Mesh8 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3818: g Mesh9 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3844: g Mesh10 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3870: g Mesh11 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3896: g Mesh12 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
3922: g Mesh13 minecraft_hardened_clay_stained_silver__1 BRS_3rd_floor_obj Model
4000: g Mesh14 minecraft_hardened_clay_stained_silver__1 BRS_3rd_floor_obj Model
4028: g Mesh15 minecraft_hardened_clay_stained_silver__1 BRS_3rd_floor_obj Model
4056: g Mesh16 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4064: g Mesh17 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4070: g Mesh18 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4076: g Mesh19 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4082: g Mesh20 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4480: g Mesh21 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4486: g Mesh22 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4492: g Mesh23 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4498: g Mesh24 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4508: g Mesh25 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4519: g Mesh26 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4525: g Mesh27 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4533: g Mesh28 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4539: g Mesh29 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
4545: g Mesh30 minecraft_quartz_block_top__1 BRS_3rd_floor_obj Model
```

5 lines around first `usemtl`:
```text
7: g Mesh1 minecraft_quartz_block_side__1 BRS_3rd_floor_obj Model
8: 
9: usemtl minecraft_quartz_block_side_-98
10: v -1987.03 23170.2 1759.84
11: vt 1.997 0.5
```

### 2. Step 3: Red test run (before implementation)

```text
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-08" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_groups.py -q -p no:cacheprovider )

=================================== ERRORS ====================================
_____________ ERROR collecting engine/tests/test_campus_groups.py _____________
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-08\engine\tests\test_campus_groups.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
C:\Users\Future26\AppData\Local\Programs\Python\Python312\Lib\importlib\__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\tests\test_campus_groups.py:6: in <module>
    from engine.campus.groups import (
E   ModuleNotFoundError: No module named 'engine.campus.groups'
=========================== short test summary info ===========================
ERROR engine/tests/test_campus_groups.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.19s
```

### 3. Step 4: Green test run (after implementation)

```text
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-08" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_groups.py -q -p no:cacheprovider )

....                                                                     [100%]
4 passed in 0.03s
```

Combined suite check (`test_campus_groups.py` and `test_campus_source.py`):
```text
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-08" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_groups.py engine/tests/test_campus_source.py -q -p no:cacheprovider )

....................                                                     [100%]
20 passed in 1.80s
```

### 4. Step 5: Real run CLI command output

```text
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-08" && PYTHONPATH="$PWD" "$PY" -m engine.cli campus-index --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" --out "D:/PROJECTS/UC MODEL FIXER/data/campus/group_index.json" )

indexed 179 paths, 225 runs, 85 splits -> D:\PROJECTS\UC MODEL FIXER\data\campus\group_index.json
```

### 5. Step 5: Real comparison table (85 / 85 Manifest Files)

| # | Split Name | Index Tris | Manifest Tris | Match |
|---|---|---:|---:|:---:|
| 01 | `Main_Infrustructure_Building` | 142,234 | 142,234 | PASS |
| 02 | `Gymnasium_5th_floor_and_roof` | 91,714 | 91,714 | PASS |
| 03 | `MAIN_BUILDING` | 80,078 | 80,078 | PASS |
| 04 | `Main_6ft_Floor_obj` | 67,113 | 67,113 | PASS |
| 05 | `Architecture_1st_floor` | 60,388 | 60,388 | PASS |
| 06 | `Architecture_dep_2nd_Floor_obj` | 54,343 | 54,343 | PASS |
| 07 | `EDS_3rd_Floor` | 47,710 | 47,710 | PASS |
| 08 | `EDS_4th_Floor` | 40,921 | 40,921 | PASS |
| 09 | `Architecture_emergency_stairs` | 39,527 | 39,527 | PASS |
| 10 | `Main_7th_Floor_obj` | 39,167 | 39,167 | PASS |
| 11 | `BRS_2nd_floor_obj` | 36,867 | 36,867 | PASS |
| 12 | `Eds_9th_Floor_obj` | 34,979 | 34,979 | PASS |
| 13 | `Main_3RD_Floor_obj1` | 31,979 | 31,979 | PASS |
| 14 | `Eds_8th_Floor_obj` | 30,798 | 30,798 | PASS |
| 15 | `Eds_6th_Floor_obj` | 29,524 | 29,524 | PASS |
| 16 | `Eds_7th_Floor_obj` | 29,050 | 29,050 | PASS |
| 17 | `Architecture_dep_7th_Floor_obj` | 28,280 | 28,280 | PASS |
| 18 | `BRS_5th_floor_obj` | 28,234 | 28,234 | PASS |
| 19 | `BRS_4th_floor_obj` | 27,850 | 27,850 | PASS |
| 20 | `Eds_5ft_Floor_obj` | 27,401 | 27,401 | PASS |
| 21 | `Gymnasium_3rd_floor_obj` | 26,092 | 26,092 | PASS |
| 22 | `Main_8th_Floor_obj` | 25,710 | 25,710 | PASS |
| 23 | `Eds_10th_Floor_obj` | 23,822 | 23,822 | PASS |
| 24 | `Gymnasium_4th_floor_obj` | 23,436 | 23,436 | PASS |
| 25 | `CHTM_3rd_floor` | 22,793 | 22,793 | PASS |
| 26 | `Gymnasium_1st_Floor` | 22,666 | 22,666 | PASS |
| 27 | `BRS_3rd_floor_obj` | 22,017 | 22,017 | PASS |
| 28 | `Sciene_A_Floor_plan_4_obj` | 21,318 | 21,318 | PASS |
| 29 | `BRS_5th_floor_obj1` | 20,683 | 20,683 | PASS |
| 30 | `chtm_5ft_floor` | 20,599 | 20,599 | PASS |
| 31 | `BRS_10th_floor_obj` | 18,828 | 18,828 | PASS |
| 32 | `BRS_7th_floor_obj` | 18,192 | 18,192 | PASS |
| 33 | `CHTM_4th_floor` | 18,188 | 18,188 | PASS |
| 34 | `Chtm_2nd_floor` | 18,074 | 18,074 | PASS |
| 35 | `Eds_2nd_Floor_obj` | 17,700 | 17,700 | PASS |
| 36 | `Gymnasium_2nd_floor_obj` | 17,410 | 17,410 | PASS |
| 37 | `BRS_9th_floor_obj` | 17,217 | 17,217 | PASS |
| 38 | `BRS_9th_floor_obj1` | 17,109 | 17,109 | PASS |
| 39 | `CHTM_7th_floor_obj` | 17,039 | 17,039 | PASS |
| 40 | `CHTM_8th_floor_obj` | 16,762 | 16,762 | PASS |
| 41 | `Architecture_dep_3rd_Floor_obj` | 16,755 | 16,755 | PASS |
| 42 | `BRS_6th_floor_obj` | 16,683 | 16,683 | PASS |
| 43 | `BRIDGE_ZONE` | 16,663 | 16,663 | PASS |
| 44 | `Main_2nd_Floor_obj` | 16,530 | 16,530 | PASS |
| 45 | `BRS_4th_floor_obj1` | 16,329 | 16,329 | PASS |
| 46 | `CHTM_9th_floor_obj` | 15,957 | 15,957 | PASS |
| 47 | `Architecture_dep_4th_Floor_obj` | 15,897 | 15,897 | PASS |
| 48 | `CHTM_6ft_floor_obj` | 15,698 | 15,698 | PASS |
| 49 | `Sciene_A_Floor_plan_6_obj` | 15,447 | 15,447 | PASS |
| 50 | `CHTM_10th_floor_obj` | 14,934 | 14,934 | PASS |
| 51 | `Architecture_dep_6th_Floor_obj` | 14,782 | 14,782 | PASS |
| 52 | `Sciene_A_Floor_plan_5_obj` | 14,683 | 14,683 | PASS |
| 53 | `Architecture_dep_5th_Floor_obj` | 14,531 | 14,531 | PASS |
| 54 | `CHTM_11th_floor_obj` | 13,925 | 13,925 | PASS |
| 55 | `PE_5ft_Floor_obj` | 13,638 | 13,638 | PASS |
| 56 | `EDS_1st_Floor` | 12,764 | 12,764 | PASS |
| 57 | `PE_4th_Floor_obj` | 12,004 | 12,004 | PASS |
| 58 | `Sciene_A_Floor_plan_3_obj` | 11,394 | 11,394 | PASS |
| 59 | `PE_3rd_Floor_obj` | 11,341 | 11,341 | PASS |
| 60 | `PE_6th_Floor_obj` | 10,963 | 10,963 | PASS |
| 61 | `BRS_11th_floor_obj` | 10,502 | 10,502 | PASS |
| 62 | `PE_2nd_Floor` | 9,980 | 9,980 | PASS |
| 63 | `Sciene_A_Floor_plan_3_obj1` | 9,084 | 9,084 | PASS |
| 64 | `Eds_11th_Floor_obj` | 9,004 | 9,004 | PASS |
| 65 | `CHTM_sidewalk_zone` | 8,593 | 8,593 | PASS |
| 66 | `CHTM_1st_floor_zone` | 7,856 | 7,856 | PASS |
| 67 | `CHTM_12th_floor_obj` | 6,664 | 6,664 | PASS |
| 68 | `Main_Infrustructure_1st_floor` | 5,792 | 5,792 | PASS |
| 69 | `Sciene_A_Floor_plan_2_obj` | 5,264 | 5,264 | PASS |
| 70 | `PE_1st_Floor` | 5,255 | 5,255 | PASS |
| 71 | `Sciene_A_Floor_plan_2_obj1` | 4,682 | 4,682 | PASS |
| 72 | `BRS_12th_floor_obj` | 3,357 | 3,357 | PASS |
| 73 | `Group137` | 2,898 | 2,898 | PASS |
| 74 | `BRS_1st_floor_obj` | 2,400 | 2,400 | PASS |
| 75 | `BRS_ZONE` | 2,358 | 2,358 | PASS |
| 76 | `ROAD_harrison_front` | 2,334 | 2,334 | PASS |
| 77 | `unnamed` | 2,178 | 2,178 | PASS |
| 78 | `Main_1st_Floor_obj` | 1,395 | 1,395 | PASS |
| 79 | `PE_GROUND_landscaping` | 955 | 955 | PASS |
| 80 | `Main_3RD_Floor_obj` | 627 | 627 | PASS |
| 81 | `Side_walk_harrision_Main_building_2` | 405 | 405 | PASS |
| 82 | `BRS_GROUND_FLOOR_PATHWAY_obj` | 233 | 233 | PASS |
| 83 | `Group220` | 199 | 199 | PASS |
| 84 | `ARCHITECTURE_BUILDING` | 131 | 131 | PASS |
| 85 | `Group124` | 30 | 30 | PASS |

Total triangles across all 85 splits: 1,766,906 (exact match to `totals.tris` in `source.json`).

## Unsure about
Nothing. The naming rule reproduces 85/85 manifest files and triangle counts exactly with 0 differences. Group index file `data/campus/group_index.json` is generated and verified.
