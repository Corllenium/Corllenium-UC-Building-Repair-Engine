# P0-09b — No silent texture fallback in campus-materials

- Branch: hermes/P0-09b   Base: 76d74bb17d84a75c1fc16d3f25d97f5fb243ba40 (feat/repair-p0)
- Commits:
  - 157435b fix(campus): remove silent basename texture fallback in materials resolution
- Brief: docs/superpowers/records/briefs/P0-09b-texture-fallback.md

## Items
### Item 1 — a missing exact path is a missing texture: DONE
- Tests added: `test_missing_exact_path_is_missing_texture`
- Red run (before the code):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_materials.py -k test_missing_exact_path_is_missing_texture -v -p no:cacheprovider )
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\PROJECTS\UC MODEL FIXER\.venv\Scripts\python.exe
rootdir: D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09b
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 20 items / 19 deselected / 1 selected

engine/tests/test_campus_materials.py::test_missing_exact_path_is_missing_texture FAILED [100%]

================================== FAILURES ===================================
_________________ test_missing_exact_path_is_missing_texture __________________

tmp_path = WindowsPath('C:/Users/Future26/AppData/Local/Temp/pytest-of-Future26/pytest-422/test_missing_exact_path_is_mis0')

    def test_missing_exact_path_is_missing_texture(tmp_path):
        # folder_b/tile.png is absent and folder_a/tile.png exists.
        # A material whose map_Kd is folder_b/tile.png gets missing_texture: true,
        # is not given folder_a's bytes, and does not share folder_a's look.
        dir_a = tmp_path / "folder_a"
        dir_a.mkdir()
        (dir_a / "tile.png").write_bytes(b"content_A")
        # folder_b/tile.png is absent
    
        mtl = tmp_path / "missing_exact.mtl"
        mtl.write_text(
            "newmtl mat_a\nKd 1 1 1\nmap_Kd folder_a/tile.png\n\nnewmtl mat_b\nKd 1 1 1\nmap_Kd folder_b/tile.png\n",
            encoding="utf-8",
        )
        res = build_materials(mtl, dir_a)
        mat_a = res["materials"]["mat_a"]
        mat_b = res["materials"]["mat_b"]
>       assert mat_b["missing_texture"] is True
E       assert False is True

engine\tests\test_campus_materials.py:214: AssertionError
=========================== short test summary info ===========================
FAILED engine/tests/test_campus_materials.py::test_missing_exact_path_is_missing_texture
====================== 1 failed, 19 deselected in 0.35s =======================
```
- Green run (after removing basename fallback from `_find_texture_file`):
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_materials.py -v -p no:cacheprovider )
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\PROJECTS\UC MODEL FIXER\.venv\Scripts\python.exe
rootdir: D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09b
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 20 items

engine/tests/test_campus_materials.py::test_parse_kd_d_defaults PASSED   [  5%]
engine/tests/test_campus_materials.py::test_parse_kd_d_parsed PASSED     [ 10%]
engine/tests/test_campus_materials.py::test_look_key_format PASSED       [ 15%]
engine/tests/test_campus_materials.py::test_build_materials_same_look_for_same_bytes_and_kd PASSED [ 20%]
engine/tests/test_campus_materials.py::test_build_materials_kd_differs_different_look PASSED [ 25%]
engine/tests/test_campus_materials.py::test_build_materials_missing_texture PASSED [ 30%]
engine/tests/test_campus_materials.py::test_build_materials_d_defaults_to_1 PASSED [ 35%]
engine/tests/test_campus_materials.py::test_build_materials_stats_4_material_fixture PASSED [ 40%]
engine/tests/test_campus_materials.py::test_build_materials_untextured PASSED [ 45%]
engine/tests/test_campus_materials.py::test_cli_campus_materials PASSED  [ 50%]
engine/tests/test_campus_materials.py::test_parse_kd_d_tr_support PASSED [ 55%]
engine/tests/test_campus_materials.py::test_kd_rounding_mutant PASSED    [ 60%]
engine/tests/test_campus_materials.py::test_d_opacity_mutant PASSED      [ 65%]
engine/tests/test_campus_materials.py::test_backslash_map_kd_equals_slash PASSED [ 70%]
engine/tests/test_campus_materials.py::test_same_name_textures_two_folders PASSED [ 75%]
engine/tests/test_campus_materials.py::test_missing_exact_path_is_missing_texture PASSED [ 80%]
engine/tests/test_campus_materials.py::test_reject_invalid_texture_paths PASSED [ 85%]
engine/tests/test_campus_materials.py::test_two_different_byte_textures_same_kd PASSED [ 90%]
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json PASSED [ 95%]
engine/tests/test_campus_materials.py::test_cli_largest_look_group_printed_first PASSED [100%]

============================= 20 passed in 2.36s ==============================
```
- Notes:
  Removed basename fallback from `_find_texture_file`. Paths resolve by exact MTL-relative path first, then relative to `tex_dir`. When a texture file is absent from both exact paths, it is not resolved by basename, preventing silent texture cross-contamination.

### Item 2 — test hygiene: DONE
- Tests updated:
  - `test_reject_invalid_texture_paths`: placed the MTL file inside `sub = tmp_path / "sub"`, so `map_Kd ../escape.png` resolves against `tmp_path / "escape.png"`, keeping the `..` test completely inside `tmp_path` without touching `tmp_path.parent`.
  - `test_cli_fabricated_source_json`: runs from a dedicated `work_dir` distinct from `source_dir` and `models_dir`, adds decoy `SRC-TEX` folders in `source_dir` and `work_dir`, and tests materials referencing both `tile.png` and `SRC-TEX/tile.png`, verifying that `--out relative_out.json` is resolved relative to cwd and that the sibling `SRC-TEX` of the MTL is used.
- Mutant demonstration:
  1. Reverting `--out` handling to resolve against `source_path.parent / args.out`:
```text
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json FAILED [100%]
...
    rel_out = work_dir / "relative_out.json"
>   assert rel_out.is_file()
E   AssertionError: assert False
E    +  where False = is_file()
E    +    where is_file = WindowsPath('.../work/relative_out.json').is_file
wrote materials to ...\source_dir\relative_out.json
```
  2. Reverting sibling `SRC-TEX` rule to look in `source_path.parent / "SRC-TEX"`:
```text
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json FAILED [100%]
...
    data = json.loads(rel_out.read_text(encoding="utf-8"))
    assert data["stats"]["materials"] == 2
>   assert data["stats"]["images"] == 1
E   assert 2 == 1
```

## Acceptance command outputs

### 1. Pytest suite
```text
$ PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_campus_materials.py engine/tests/test_campus_source.py -q -p no:cacheprovider )
....................................                                     [100%]
36 passed in 3.96s
```

### 2. Campus materials CLI real output check
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09b" && PYTHONPATH="$PWD" "$PY" -m engine.cli campus-materials --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" --out "D:/PROJECTS/UC MODEL FIXER/data/p009b_check/materials.json" )
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
wrote materials to D:\PROJECTS\UC MODEL FIXER\data\p009b_check\materials.json
```

Output sha256 check:
```text
$ "$PY" -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('D:/PROJECTS/UC MODEL FIXER/data/p009b_check/materials.json').read_bytes()).hexdigest())"
28a0e0d328e025246f4908cb5e5dcde61862daec5fca1ed051b58aaec38e06a5
```

## Unsure about
Nothing. All 36 targeted tests pass, output sha256 matches expected `28a0e0d3...` byte-for-byte, and mutant testing confirms the new assertions catch both mutant cases.
