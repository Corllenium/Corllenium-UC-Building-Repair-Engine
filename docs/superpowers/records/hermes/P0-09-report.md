# P0-09 — Material look keys (Task 9)

- Branch: hermes/P0-09   Base: e7fac71031ca5160633acdbfffb6f41552ff566e (feat/repair-p0)
- Commits:
  - dc54986 feat(campus): material look keys, so visual checks compare texture + colour, not material numbers
  - 0e0054f fix(campus): address review notes for campus-materials
- Brief: docs/superpowers/plans/2026-10-03-repair-engine-p0.md#task-9

## Items
### Item 1 — Material look keys: DONE
- Initial tests added:
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
- Additional tests added for review notes 1-5:
  - `test_parse_kd_d_tr_support` (Note 5: Tr support when d absent, d wins when present)
  - `test_kd_rounding_mutant` (Note 4: Kd 0.80001 == 0.8, 0.8001 != 0.8)
  - `test_d_opacity_mutant` (Note 4: d 0.9 != 1.0)
  - `test_backslash_map_kd_equals_slash` (Note 4: backslash normalized to forward slash)
  - `test_same_name_textures_two_folders` (Note 1 & Note 4: multi-folder collision resolves exact MTL-relative path first, images == 2)
  - `test_reject_invalid_texture_paths` (Note 2: reject absolute, drive-letter, and '..' map_Kd paths using `_texture_rel`)
  - `test_two_different_byte_textures_same_kd` (Note 4: different bytes, same Kd -> different looks, images == 2)
  - `test_cli_fabricated_source_json` (Note 3 & Note 4: fabricated source.json, relative --out stays relative to cwd)
  - `test_cli_largest_look_group_printed_first` (Note 4: largest look group printed first)

- Red run (new tests on committed code dc54986):
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py -v -p no:cacheprovider )
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\PROJECTS\UC MODEL FIXER\.venv\Scripts\python.exe
rootdir: D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 19 items

engine/tests/test_campus_materials.py::test_parse_kd_d_defaults PASSED   [  5%]
engine/tests/test_campus_materials.py::test_parse_kd_d_parsed PASSED     [ 10%]
engine/tests/test_campus_materials.py::test_look_key_format PASSED       [ 15%]
engine/tests/test_campus_materials.py::test_build_materials_same_look_for_same_bytes_and_kd PASSED [ 21%]
engine/tests/test_campus_materials.py::test_build_materials_kd_differs_different_look PASSED [ 26%]
engine/tests/test_campus_materials.py::test_build_materials_missing_texture PASSED [ 31%]
engine/tests/test_campus_materials.py::test_build_materials_d_defaults_to_1 PASSED [ 36%]
engine/tests/test_campus_materials.py::test_build_materials_stats_4_material_fixture PASSED [ 42%]
engine/tests/test_campus_materials.py::test_build_materials_untextured PASSED [ 47%]
engine/tests/test_campus_materials.py::test_cli_campus_materials PASSED  [ 52%]
engine/tests/test_campus_materials.py::test_parse_kd_d_tr_support FAILED [ 57%]
engine/tests/test_campus_materials.py::test_kd_rounding_mutant PASSED    [ 63%]
engine/tests/test_campus_materials.py::test_d_opacity_mutant PASSED      [ 68%]
engine/tests/test_campus_materials.py::test_backslash_map_kd_equals_slash PASSED [ 73%]
engine/tests/test_campus_materials.py::test_same_name_textures_two_folders FAILED [ 78%]
engine/tests/test_campus_materials.py::test_reject_invalid_texture_paths FAILED [ 84%]
engine/tests/test_campus_materials.py::test_two_different_byte_textures_same_kd PASSED [ 89%]
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json FAILED [ 94%]
engine/tests/test_campus_materials.py::test_cli_largest_look_group_printed_first PASSED [100%]

================================== FAILURES ===================================
_________________________ test_parse_kd_d_tr_support __________________________
    def test_parse_kd_d_tr_support():
        mat_tr = MtlMaterial("tr_only", lines=["Tr 0.2"])
        kd, d = parse_kd_d(mat_tr)
>       assert d == pytest.approx(0.8)
E       assert 1.0 == 0.8 ± 8.0e-07
_____________________ test_same_name_textures_two_folders _____________________
    def test_same_name_textures_two_folders(tmp_path):
...
        res = build_materials(mtl, dir_a)
>       assert res["materials"]["mat_a"]["look"] != res["materials"]["mat_b"]["look"]
E       AssertionError: assert '3adbda8b228153e4' != '3adbda8b228153e4'
______________________ test_reject_invalid_texture_paths ______________________
    def test_reject_invalid_texture_paths(tmp_path):
...
        for name in ["mat_drive", "mat_abs", "mat_dotdot"]:
            m = res["materials"][name]
>           assert m["missing_texture"] is True
E           assert False is True
_______________________ test_cli_fabricated_source_json _______________________
    def test_cli_fabricated_source_json(tmp_path, monkeypatch):
...
        monkeypatch.chdir(tmp_path)
        ret = main(["campus-materials", "--source", str(source_json), "--out", "relative_out.json"])
        assert ret == 0
        rel_out = tmp_path / "relative_out.json"
>       assert rel_out.is_file()
E       AssertionError: assert False
======================== 4 failed, 15 passed in 1.07s =========================
```

- Green run (after fixes):
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py -v -p no:cacheprovider )
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\PROJECTS\UC MODEL FIXER\.venv\Scripts\python.exe
rootdir: D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 19 items

engine/tests/test_campus_materials.py::test_parse_kd_d_defaults PASSED   [  5%]
engine/tests/test_campus_materials.py::test_parse_kd_d_parsed PASSED     [ 10%]
engine/tests/test_campus_materials.py::test_look_key_format PASSED       [ 15%]
engine/tests/test_campus_materials.py::test_build_materials_same_look_for_same_bytes_and_kd PASSED [ 21%]
engine/tests/test_campus_materials.py::test_build_materials_kd_differs_different_look PASSED [ 26%]
engine/tests/test_campus_materials.py::test_build_materials_missing_texture PASSED [ 31%]
engine/tests/test_campus_materials.py::test_build_materials_d_defaults_to_1 PASSED [ 36%]
engine/tests/test_campus_materials.py::test_build_materials_stats_4_material_fixture PASSED [ 42%]
engine/tests/test_campus_materials.py::test_build_materials_untextured PASSED [ 47%]
engine/tests/test_campus_materials.py::test_cli_campus_materials PASSED  [ 52%]
engine/tests/test_campus_materials.py::test_parse_kd_d_tr_support PASSED [ 57%]
engine/tests/test_campus_materials.py::test_kd_rounding_mutant PASSED    [ 63%]
engine/tests/test_campus_materials.py::test_d_opacity_mutant PASSED      [ 68%]
engine/tests/test_campus_materials.py::test_backslash_map_kd_equals_slash PASSED [ 73%]
engine/tests/test_campus_materials.py::test_same_name_textures_two_folders PASSED [ 78%]
engine/tests/test_campus_materials.py::test_reject_invalid_texture_paths PASSED [ 84%]
engine/tests/test_campus_materials.py::test_two_different_byte_textures_same_kd PASSED [ 89%]
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json PASSED [ 94%]
engine/tests/test_campus_materials.py::test_cli_largest_look_group_printed_first PASSED [100%]

============================= 19 passed in 1.09s ==============================
```

- Notes on review fixes:
  1. `materials.py:43-52 _find_texture_file`: resolves exact MTL-relative path (`mtl_path.parent / rel`) FIRST, then `tex_dir / rel`, falling back to basename only as last resort.
  2. Reject invalid texture paths: reused `engine.campus.source._texture_rel`; paths that are absolute, contain drive letters (any ":"), or contain ".." are rejected, returning None which sets `missing_texture: True` and uses `missing:<map_kd>` look key.
  3. `cli.py`: removed hard-coded `D:/PROJECTS/UC MODEL FIXER` path and path guessing. Takes `Path(source_data["clean_mtl"]["path"])` and its sibling `SRC-TEX` directly from `source.json` (paths are absolute). A relative `--out` stays relative to cwd.
  4. Mutant-killing tests added for all 7 cases requested.
  5. `Tr` support added in `parse_kd_d`: when `d` is absent, `d = 1.0 - Tr`; when `d` is present, `d` takes precedence.
  6. Verified real data produces identical sha256 `28a0e0d328e025246f4908cb5e5dcde61862daec5fca1ed051b58aaec38e06a5`.

## Acceptance command outputs

### 1. Pytest suite for campus materials
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py -v -p no:cacheprovider )
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- D:\PROJECTS\UC MODEL FIXER\.venv\Scripts\python.exe
rootdir: D:\PROJECTS\UC MODEL FIXER\.hermes\worktrees\P0-09
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 19 items

engine/tests/test_campus_materials.py::test_parse_kd_d_defaults PASSED   [  5%]
engine/tests/test_campus_materials.py::test_parse_kd_d_parsed PASSED     [ 10%]
engine/tests/test_campus_materials.py::test_look_key_format PASSED       [ 15%]
engine/tests/test_campus_materials.py::test_build_materials_same_look_for_same_bytes_and_kd PASSED [ 21%]
engine/tests/test_campus_materials.py::test_build_materials_kd_differs_different_look PASSED [ 26%]
engine/tests/test_campus_materials.py::test_build_materials_missing_texture PASSED [ 31%]
engine/tests/test_campus_materials.py::test_build_materials_d_defaults_to_1 PASSED [ 36%]
engine/tests/test_campus_materials.py::test_build_materials_stats_4_material_fixture PASSED [ 42%]
engine/tests/test_campus_materials.py::test_build_materials_untextured PASSED [ 47%]
engine/tests/test_campus_materials.py::test_cli_campus_materials PASSED  [ 52%]
engine/tests/test_campus_materials.py::test_parse_kd_d_tr_support PASSED [ 57%]
engine/tests/test_campus_materials.py::test_kd_rounding_mutant PASSED    [ 63%]
engine/tests/test_campus_materials.py::test_d_opacity_mutant PASSED      [ 68%]
engine/tests/test_campus_materials.py::test_backslash_map_kd_equals_slash PASSED [ 73%]
engine/tests/test_campus_materials.py::test_same_name_textures_two_folders PASSED [ 78%]
engine/tests/test_campus_materials.py::test_reject_invalid_texture_paths PASSED [ 84%]
engine/tests/test_campus_materials.py::test_two_different_byte_textures_same_kd PASSED [ 89%]
engine/tests/test_campus_materials.py::test_cli_fabricated_source_json PASSED [ 94%]
engine/tests/test_campus_materials.py::test_cli_largest_look_group_printed_first PASSED [100%]

============================= 19 passed in 1.09s ==============================
```

### 2. Pytest suite for campus modules
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_campus_materials.py engine/tests/test_campus_source.py -q -p no:cacheprovider )
...................................                                      [100%]
35 passed in 4.63s
```

### 3. Pytest suite for tools
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest tools/tests -q -p no:cacheprovider )
........................................................................ [ 60%]
...............................................                          [100%]
119 passed in 16.78s
```

### 4. Real run of `campus-materials`
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m engine.cli campus-materials --source "D:/PROJECTS/UC MODEL FIXER/data/campus/source.json" --out "D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json" )
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

### 5. Checksum verification of `data/campus/materials.json`
```text
$ "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('D:/PROJECTS/UC MODEL FIXER/data/campus/materials.json').read_bytes()).hexdigest())"
28a0e0d328e025246f4908cb5e5dcde61862daec5fca1ed051b58aaec38e06a5
```

### 6. Full engine test suite (brief step 4)
```text
$ ( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-09" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests -q -p no:cacheprovider )
........................................................................ [ 10%]
........................................................................ [ 21%]
........................................................................ [ 32%]
........................................................................ [ 43%]
........................................................................ [ 53%]
........................................................................ [ 64%]
........................................................................ [ 75%]
........................................................................ [ 86%]
........................................................................ [ 96%]
.....x...............                                                    [100%]
668 passed, 1 xfailed in 401.82s (0:06:41)
```

## Unsure about
Nothing. All 19 tests pass, the full engine test suite passes (668 passed, 1 xfailed in 401.82s), all 6 review notes are fully addressed, and `materials.json` sha256 is verified byte-identical to `28a0e0d328e025246f4908cb5e5dcde61862daec5fca1ed051b58aaec38e06a5`.
