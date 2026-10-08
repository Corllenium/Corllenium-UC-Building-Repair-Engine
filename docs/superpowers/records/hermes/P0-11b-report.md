# P0-11b — SDK check follow-ups: resolved --dll, full ambiguous definition, split rule pinned to groups.py

- Branch: hermes/P0-11b   Base: 76d74bb (feat/repair-p0)
- Commits:
  - c8fcd35 fix(campus): SDK cross-check follow-ups (P0-11b)
- Brief: docs/superpowers/records/briefs/P0-11b-skp-check-followups.md

## Items
### Item 1 — a relative `--dll` reaches the child resolved: DONE
- Tests added: `test_a_relative_dll_path_reaches_the_child_as_an_absolute_path`
- Red run (before the code):
```
FAILED engine/tests/test_skp_check.py::test_a_relative_dll_path_reaches_the_child_as_an_absolute_path
E           engine.campus.skp_check.WalkFailed: the SketchUp walk failed with exit code 1: Traceback (most recent call last): File "<string>", line 1, in <module> AssertionError: ['-c', 'C:\\Users\\Future26\\AppData\\Local\\Temp\\pytest-of-Future26\\pytest-427\\test_a_relative_dll_path_reach0\\m.skp', '--out', 'C:\\Users\\Future26\\AppData\\Local\\Temp\\pytest-of-Future26\\pytest-427\\test_a_relative_dll_path_reach0\\walk.json', '--dll', 'my_relative.dll']
```
- Green run (after):
```
engine\tests\test_skp_check.py .                                         [100%]
====================== 1 passed, 95 deselected in 0.58s =======================
```
- Notes: In `engine/campus/skp_check.py` (`run_walk`), resolved `dll_path` with `dll = Path(dll_path).resolve() if dll_path is not None else None`.

### Item 2 — the "Ambiguous" definition names every case: DONE
- Tests added: extended `test_files_decided_without_a_pairing_are_counted_and_do_not_count_as_ambiguous` to assert the full definition sentence, and added `test_a_family_with_more_files_than_groups_where_every_file_fits_every_group_stays_undecided`.
- Red run (before the code):
```
FAILED engine/tests/test_skp_check.py::test_files_decided_without_a_pairing_are_counted_and_do_not_count_as_ambiguous
E       AssertionError: assert 'Ambiguous: a file that matches some of several groups of one name but not others, or one where a family has more file... every group, so its verdict depends on a pairing the shapes cannot settle. Miss: no group of that name in the backup.' in '# SDK cross-check: the CHECKPOINT-17 export against its backup\n\nRun 2026-10-04T09:51:14+08:00. Backup `M - CHECKPOI...t is (`engine/campus/skp_check.py`), so a file is compared with the faces that went into it, not with a whole group.\n'
```
- Green run (after):
```
engine\tests\test_skp_check.py ..                                        [100%]
====================== 2 passed, 96 deselected in 0.98s =======================
```
- Notes: Updated `render_markdown` definition sentence to include `or one where a family has more files than groups and every file fits every group`. Regenerated `docs/superpowers/records/campus/skp-check.md`, which strictly matches `render_markdown(data/campus/skp_check.json)`.

### Item 3 — one split rule, pinned: DONE
- Tests added: `test_skp_check_and_campus_groups_give_the_same_split_name_for_every_path_in_group_index`
- Red run (before the code):
```
FAILED engine/tests/test_skp_check.py::test_skp_check_and_campus_groups_give_the_same_split_name_for_every_path_in_group_index
E           AttributeError: module 'engine.campus.skp_check' has no attribute 'split_path'
```
- Green run (after):
```
engine\tests\test_skp_check.py .                                         [100%]
====================== 1 passed, 97 deselected in 0.68s =======================
```
- Notes: Added `skp_check.split_path(path)` mapping OBJ tokens between `Mesh<N>` and `Model` (inner to outer) to the backup's `split_key` rule. Verified against `groups.split_name(tuple(p), skip_owner_slot=True)` across all 1,346 paths in `data/campus/group_index.json`: 0 differences found.

## Acceptance command outputs

Command:
```bash
PY="D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe"
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-11b" && PYTHONPATH="$PWD" "$PY" -m pytest engine/tests/test_skp_check.py engine/tests/test_campus_groups.py -q -p no:cacheprovider )
```
Output:
```
........................................................................ [ 68%]
.................................                                        [100%]
105 passed in 6.67s
```

Command:
```bash
( cd "D:/PROJECTS/UC MODEL FIXER/.hermes/worktrees/P0-11b" && PYTHONPATH="$PWD" "D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -c "
import json
from engine.campus.skp_check import render_markdown
from pathlib import Path

report = json.loads(Path('D:/PROJECTS/UC MODEL FIXER/data/campus/skp_check.json').read_text(encoding='utf-8'))
rendered = render_markdown(report)
committed = Path('docs/superpowers/records/campus/skp-check.md').read_text(encoding='utf-8')
assert rendered == committed
print('render_markdown output strictly matches docs/superpowers/records/campus/skp-check.md')
" )
```
Output:
```
render_markdown output strictly matches docs/superpowers/records/campus/skp-check.md
```

## Unsure about
Nothing: all three items implemented test-first, passing cleanly, and verified against real index and check files.
