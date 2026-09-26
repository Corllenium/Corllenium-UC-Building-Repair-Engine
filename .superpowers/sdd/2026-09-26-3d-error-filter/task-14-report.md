# Task 14: The Facade Layer — Report

**Status:** SUCCESS

**SHA:** `0e15aee4fd128d6458d09acbcc811cdf7eeaae24`

**Files Modified:**
- `engine/detectors/errors.py` (+9, -2): Import `EXP_OUTSIDE`, compute `exposure_class` once, derive `hidden` and `facade` from it, add `spots["facade"]`, and populate `"layers"` and `"layer_counts"` keys in the returned dict.
- `engine/tests/test_errors.py` (+14, -0): Append two new tests verifying the facade layer for both `box_with_partition()` and `cube()`.

**Test Results:**
```
69 passed in 78.01s (0:01:18)
```

All tests pass, including:
- `test_the_facade_layer_is_every_face_seen_from_outside`: Verifies `box_with_partition()` has 12 facade faces (all outer faces, not the sealed partition) and 2 hidden faces, with non-zero spot value.
- `test_a_clean_cube_is_all_facade_and_still_has_no_errors`: Verifies `cube()` has 12 facade faces and no errors (all counts zero).
- All 67 existing tests continue to pass.

**Implementation Details:**
- `exposure_class = classify_exposure(front + back, ok, profile.slit_threshold)` computed once (line 57)
- `hidden = np.nonzero((exposure_class == EXP_HIDDEN) & ok)[0]` (line 58)
- `facade = np.nonzero((exposure_class == EXP_OUTSIDE) & ok)[0]` (line 59)
- `spots["facade"] = _face_group_spots("facade", pos, faces, facade, topo.face_region, area)` (line 93)
- `"layers": {"facade": [int(f) for f in facade]}` and `"layer_counts": {"facade": int(len(facade))}` added to return dict (lines 104–105)

**Concerns:** None. The implementation follows the brief exactly, both fixture tests pass with correct values (facade = 0..11, hidden = [12,13] for box_with_partition; facade = 0..11, errors = 0 for cube), and all CLI integration tests pass.
