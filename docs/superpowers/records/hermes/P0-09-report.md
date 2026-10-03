# P0-09 — Material look keys (Task 9)

- Branch: hermes/P0-09   Base: e7fac71031ca5160633acdbfffb6f41552ff566e (feat/repair-p0)
- Commits: e891d89 feat(campus): material look keys, so visual checks compare texture + colour, not material numbers
- Brief: docs/superpowers/plans/2026-10-03-repair-engine-p0.md#task-9

## Items
### Item 1 — Material look keys: DONE
- Tests added:
  - `test_parse_kd_d_defaults`
  - `test_parse_kd_d_parsed`
  - `test_look_key_format`
  - `test_build_materials_same_look_for_same_bytes_and_kd`
  - `test_build_materials_kd_differs_different_look`
  - `test_build_materials_missing_texture`
  - `test_build_materials_d_defaults_to_1`
  - `test_build_materials_stats_4_material_fixture`
  - `test_build_materials_untextured`
  - `test_cli_campus_materials`
- Red run (before the code):
```text
=================================== ERRORS ====================================
___________ ERROR collecting engine/tests/test_campus_materials.py ____________
ImportError while importing test module 'D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09\engine\tests\test_campus_materials.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
C:\Users\Future26\AppData\Local\Programs\Python\Python312\Lib\importlib\__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
engine\tests\test_campus_materials.py:5: in <module>
    from engine.campus.materials import parse_kd_d, look_key, build_materials
E   ModuleNotFoundError: No module named 'engine.campus.materials'
=========================== short test summary info ===========================
ERROR engine/tests/test_campus_materials.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.16s
```
- Green run (after):
```text
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py -q -p no:cacheprovider )
..........                                                               [100%]
10 passed in 1.49s
```
- Notes:
  - Implemented `parse_kd_d` to parse diffuse color (Kd) and opacity (d) with defaults `(1.0, 1.0, 1.0)` and `1.0`.
  - Implemented `look_key` taking `tex_sha256: str | None, kd, d` producing a deterministic 16-character hex digest of `f"{tex or 'none'}|{kd rounded 4}|{d rounded 4}"`.
  - Implemented `build_materials` locating textures relative to `tex_dir` or `mtl_path`, flagging missing textures with `missing_texture: True` and using `"missing:<map_kd>"` for their look key.
  - Implemented `campus-materials` CLI command in `engine/cli.py` accepting `--source`, `--out`, `--mtl`, and `--tex-dir`.

## Acceptance command outputs

### 1. Pytest suite for campus materials
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py -q -p no:cacheprovider )
..........                                                               [100%]
10 passed in 1.49s
```

### 2. Pytest suite for campus module
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_*.py -q -p no:cacheprovider )
..........................                                               [100%]
26 passed in 3.53s
```

### 3. Real run of `campus-materials`
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli campus-materials --source data/campus/source.json --out data/campus/materials.json )
materials: 391, textured: 379, images: 86, looks: 97
looks (97):
  99f0140b5c745271 (21 materials): ['minecraft_concrete_white_-1', 'minecraft_concrete_white_-118', 'minecraft_concrete_white_-131', 'minecraft_concrete_white_-146', 'minecraft_concrete_white_-177', 'minecraft_concrete_white_-38', 'minecraft_concrete_white_-66', 'minecraft_concrete_white_-86', 'mumi_minecraft_concrete_white_-13', 'mumi_minecraft_concrete_white_-15', 'mumi_minecraft_concrete_white_-2', 'mumi_minecraft_concrete_white_-21', 'mumi_minecraft_concrete_white_-32', 'mumi_minecraft_concrete_white_-38', 'mumi_minecraft_concrete_white_-4', 'mumi_minecraft_concrete_white_-41', 'mumi_minecraft_concrete_white_-43', 'mumi_minecraft_concrete_white_-44', 'mumi_minecraft_concrete_white_-55', 'mumi_minecraft_concrete_white_-7', 'mumi_minecraft_concrete_white_-8']
  20e507257694096a (21 materials): ['minecraft_quartz_block_top_-1', 'minecraft_quartz_block_top_-25', 'minecraft_quartz_block_top_-47', 'minecraft_quartz_block_top_-61', 'minecraft_quartz_block_top_-77', 'minecraft_quartz_block_top_-81', 'minecraft_quartz_block_top_-86', 'minecraft_quartz_block_top_-98', 'mumi_minecraft_quartz_block_top_-10', 'mumi_minecraft_quartz_block_top_-15', 'mumi_minecraft_quartz_block_top_-18', 'mumi_minecraft_quartz_block_top_-2', 'mumi_minecraft_quartz_block_top_-20', 'mumi_minecraft_quartz_block_top_-22', 'mumi_minecraft_quartz_block_top_-23', 'mumi_minecraft_quartz_block_top_-28', 'mumi_minecraft_quartz_block_top_-3', 'mumi_minecraft_quartz_block_top_-4', 'mumi_minecraft_quartz_block_top_-5', 'mumi_minecraft_quartz_block_top_-6', 'mumi_minecraft_quartz_block_top_-8']
  47bc867f76a6a583 (19 materials): ['minecraft_concrete_white_-119', 'minecraft_concrete_white_-132', 'minecraft_concrete_white_-147', 'minecraft_concrete_white_-15579874', 'minecraft_concrete_white_-178', 'minecraft_concrete_white_-39', 'minecraft_concrete_white_-68', 'minecraft_concrete_white_-85', 'mumi_minecraft_concrete_white_-14', 'mumi_minecraft_concrete_white_-15579874', 'mumi_minecraft_concrete_white_-16', 'mumi_minecraft_concrete_white_-33', 'mumi_minecraft_concrete_white_-37', 'mumi_minecraft_concrete_white_-40', 'mumi_minecraft_concrete_white_-42', 'mumi_minecraft_concrete_white_-45', 'mumi_minecraft_concrete_white_-5', 'mumi_minecraft_concrete_white_-6', 'mumi_minecraft_concrete_white_-9']
  e7267bea01030a72 (19 materials): ['minecraft_quartz_block_bottom_-1', 'minecraft_quartz_block_bottom_-24', 'minecraft_quartz_block_bottom_-46', 'minecraft_quartz_block_bottom_-59', 'minecraft_quartz_block_bottom_-78', 'minecraft_quartz_block_bottom_-81', 'minecraft_quartz_block_bottom_-85', 'minecraft_quartz_block_bottom_-97', 'mumi_minecraft_quartz_block_bottom_-18', 'mumi_minecraft_quartz_block_bottom_-2', 'mumi_minecraft_quartz_block_bottom_-20', 'mumi_minecraft_quartz_block_bottom_-22', 'mumi_minecraft_quartz_block_bottom_-23', 'mumi_minecraft_quartz_block_bottom_-28', 'mumi_minecraft_quartz_block_bottom_-3', 'mumi_minecraft_quartz_block_bottom_-4', 'mumi_minecraft_quartz_block_bottom_-5', 'mumi_minecraft_quartz_block_bottom_-6', 'mumi_minecraft_quartz_block_bottom_-8']
  bd6c058c4cb48b94 (19 materials): ['minecraft_quartz_block_side_-1', 'minecraft_quartz_block_side_-25', 'minecraft_quartz_block_side_-47', 'minecraft_quartz_block_side_-60', 'minecraft_quartz_block_side_-78', 'minecraft_quartz_block_side_-82', 'minecraft_quartz_block_side_-86', 'minecraft_quartz_block_side_-98', 'mumi_minecraft_quartz_block_side_-18', 'mumi_minecraft_quartz_block_side_-2', 'mumi_minecraft_quartz_block_side_-20', 'mumi_minecraft_quartz_block_side_-22', 'mumi_minecraft_quartz_block_side_-23', 'mumi_minecraft_quartz_block_side_-28', 'mumi_minecraft_quartz_block_side_-3', 'mumi_minecraft_quartz_block_side_-4', 'mumi_minecraft_quartz_block_side_-5', 'mumi_minecraft_quartz_block_side_-6', 'mumi_minecraft_quartz_block_side_-8']
  ac7e8d57ecc8baba (17 materials): ['littletiles_ltcolored0_-1', 'littletiles_ltcolored0_-11', 'littletiles_ltcolored0_-22', 'littletiles_ltcolored0_-30', 'littletiles_ltcolored0_-46', 'littletiles_ltcolored0_-50', 'littletiles_ltcolored0_-54', 'littletiles_ltcolored0_-62', 'littletiles_ltcolored0_-87', 'littletiles_ltcolored0_-88', 'mumi_littletiles_ltcolored0_-10', 'mumi_littletiles_ltcolored0_-12', 'mumi_littletiles_ltcolored0_-13', 'mumi_littletiles_ltcolored0_-14', 'mumi_littletiles_ltcolored0_-2', 'mumi_littletiles_ltcolored0_-4', 'mumi_littletiles_ltcolored0_-6']
  4ac116f3fb1aef2a (13 materials): ['minecraft_hardened_clay_stained_silver_-1', 'minecraft_hardened_clay_stained_silver_-14', 'minecraft_hardened_clay_stained_silver_-21', 'minecraft_hardened_clay_stained_silver_-23', 'minecraft_hardened_clay_top_silver_-1', 'minecraft_hardened_clay_top_silver_-14', 'minecraft_hardened_clay_top_silver_-23', 'mumi_minecraft_hardened_clay_stained_silver_-3', 'mumi_minecraft_hardened_clay_stained_silver_-4', 'mumi_minecraft_hardened_clay_stained_silver_-6', 'mumi_minecraft_hardened_clay_top_silver_-3', 'mumi_minecraft_hardened_clay_top_silver_-4', 'mumi_minecraft_hardened_clay_top_silver_-6']
  3f67c2be6ecf2e1b (12 materials): ['littletiles_ltstone_-29', 'littletiles_ltstone_-31', 'littletiles_ltstone_-34', 'littletiles_ltstone_-5', 'mumi_littletiles_ltstone_-11', 'mumi_littletiles_ltstone_-14', 'mumi_littletiles_ltstone_-15', 'mumi_littletiles_ltstone_-18', 'mumi_littletiles_ltstone_-19', 'mumi_littletiles_ltstone_-3', 'mumi_littletiles_ltstone_-4', 'mumi_littletiles_ltstone_-8']
  ee52601ae648a8c3 (11 materials): ['minecraft_sandstone_top_-1', 'minecraft_sandstone_top_-10', 'minecraft_sandstone_top_-17', 'minecraft_sandstone_top_-3', 'mumi_minecraft_sandstone_top_-1', 'mumi_minecraft_sandstone_top_-10', 'mumi_minecraft_sandstone_top_-11', 'mumi_minecraft_sandstone_top_-12', 'mumi_minecraft_sandstone_top_-4', 'mumi_minecraft_sandstone_top_-6', 'mumi_minecraft_sandstone_top_-9']
  df9bea6ab2aa4b5e (10 materials): ['minecraft_glass_white_-1', 'minecraft_glass_white_-18', 'minecraft_glass_white_-23', 'minecraft_glass_white_-25', 'minecraft_glass_white_-26', 'minecraft_glass_white_-28', 'minecraft_glass_white_-31', 'minecraft_glass_white_-8', 'mumi_minecraft_glass_white_-5', 'mumi_minecraft_glass_white_-6']
wrote materials to D:\PROJECTS\UC MODEL FIXER\data\campus\materials.json
```

### 4. Verification of output JSON
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -c "import json; d=json.load(open('D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json')); print('stats:', d['stats']); print('mats:', len(d['materials']), 'looks:', len(d['looks']))" )
stats: {'materials': 391, 'textured': 379, 'images': 86, 'looks': 97}
mats: 391 looks: 97
```

## Unsure about
Nothing. All 10 tests pass, the real run exactly meets the brief criteria (391 materials, 86 images, 97 looks, and prints the top 10 look groups with names).
