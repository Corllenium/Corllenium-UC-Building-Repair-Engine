# Task 1 Report: `double_layers` returns every pair with its partner

## Implementation Summary

Modified the `double_layers()` function in `engine/fixes/overlap.py` to return a `pair_list` field containing every flicker pair with its partner, sorted by shared area descending, then by face indices.

**What was implemented:**
- Added `"pair_list": []` to the `empty` dict returned when there are no faces
- Extracted and sorted all pairs from the `pairs` list into a new structure: `[i, j, shared_area, opposite]` 
- Sorted by `(-shared_area, i, j)` to list largest overlaps first
- Added `pair_list` to the return dict alongside existing fields

## TDD Evidence

### RED (Failing Test)
```
Command: pytest engine/tests/test_overlap.py::test_double_layers_lists_every_pair_with_its_partner -q
Output:
  KeyError: 'pair_list'
```
Test correctly failed before implementation because `double_layers` returned no `pair_list` key.

### GREEN (Passing Test)
```
Command: pytest engine/tests/test_overlap.py -q -p no:cacheprovider
Output:
  18 passed in 11.83s
```
All 18 overlap tests pass, including the new test that validates:
- The pair list contains exactly one entry for the back-to-back test fixture
- Face indices are ordered (i < j) as (0, 1)
- The `opposite` flag is True (faces wound opposite directions)
- Shared area matches the total area reported

### Full Suite
```
Command: pytest engine/tests -q -p no:cacheprovider
Output:
  611 passed, 1 xfailed in 327.38s (0:05:27)
```
No regressions. Fixed one additional test in `test_cli.py` that checked for exact set of keys in the report.

## Files Changed

**engine/fixes/overlap.py** (3 changes)
- Line 438: Added `"pair_list": []` to empty dict
- Lines 538-539: Added pair_list extraction and sorting logic
- Line 541: Added `"pair_list": pair_list` to return dict

**engine/tests/test_overlap.py** (2 changes)
- Line 266: Updated empty dict assertion to include `"pair_list": []`
- Lines 269-281: Added new test `test_double_layers_lists_every_pair_with_its_partner`

**engine/tests/test_cli.py** (1 change)
- Line 1151: Updated set assertion to include `"pair_list"` in expected keys

## Self-Review

**Strengths:**
- Follows the brief's exact specifications for the data structure and sorting
- Maintains backward compatibility in the function signature
- Properly handles empty case (no pairs) with empty `pair_list: []`
- Rounding to 3 decimal places matches existing precision conventions
- Sorting by (-shared_area, i, j) produces deterministic, sensible ordering
- All existing tests updated to expect the new field

**Data Integrity:**
- Converts all values to correct types: `int(i)`, `int(j)`, `round(float(s), 3)`, `bool(o)`
- `i < j` constraint maintained by list comprehension iterating over existing `pairs`
- Shared area rounding matches existing code style (3 decimal places)
- Boolean `opposite` flag preserved correctly

**No Concerns** — implementation is clean, minimal, and all tests pass.

## Commit

**SHA:** `0fde3ca`
**Subject:** `feat(engine): double_layers lists every flicker pair with its partner`
**Message:** Includes rationale that the 3D error filter's click card names the face a face fights with; the planes alone only gave counts.

---

## Fix 1 (Review Finding: Sort Order Not Verified)

**Issue:** The first test `test_double_layers_lists_every_pair_with_its_partner` only has one pair, so the sort order cannot be tested (sorted() returns the same single-element list regardless of sort key correctness).

**Changes Made:**

1. **Added comprehensive sort-order test** (`test_double_layers_pair_list_sorted_by_descending_shared_area`)
   - Uses `split_double_layer()` fixture which produces multiple pairs with different shared areas (6.667, 13.333, 20.0 sq in)
   - Verifies `pair_list` is sorted by descending shared area: `areas[idx] >= areas[idx+1]`
   - Verifies `i < j` constraint on every pair
   - Verifies correct types: `shared` is numeric, `opposite` is bool
   - For equal-area pairs, verifies secondary sort by `(i, j)`

2. **Verified test catches regressions** by temporarily reversing the sort key:
   - Changed `key=lambda p: (-p[2], p[0], p[1])` to `key=lambda p: (p[2], p[0], p[1])`
   - Test correctly failed with `AssertionError: pair_list not sorted by descending area: [6.667, 13.333, 20.0]`
   - Restored correct sort key and test passes

3. **Updated docstring** in `double_layers()` to document `pair_list` structure:
   - Added sentence explaining `pair_list` contains `[i, j, shared, opposite]`
   - Documented sorting: by descending shared area, then by `(i, j)`
   - Updated return dict documentation to include `pair_list`

**Test Results:**

```
Command: PYTHONPATH="$PWD" "/d/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe" -m pytest engine/tests/test_overlap.py -q -p no:cacheprovider
Output:
  19 passed in 24.14s
```

All 19 overlap tests pass (18 original + 1 new sort-order test).

**Commit:**

**SHA:** `5b6ebb2`
**Subject:** `test(engine): verify pair_list sort order is correct`
**Message:** Add comprehensive test that verifies sort order is correct and catches regressions. Update docstring to document pair_list structure and sorting.
