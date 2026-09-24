### Task 2: Exposure

**Files:** Create `engine\vis\__init__.py`, `engine\vis\exposure.py`, `engine\tests\test_exposure.py`. Modify fixtures.

**Interfaces — Produces:**
`fib_dirs(n: int) -> (n,3)`, `BARY` (4x3: centroid + three 0.6/0.2/0.2 points), `EPS_IN = 0.02`,
`compute_exposure(positions_c, face_w, ok, caster_factory=EmbreeCaster, n_dirs=128) -> np.ndarray[float64] (F,)`
= escaping rays / (`n_dirs` * 4), 0.0 for degenerate faces. For each direction `w`: faces with `n.w > 1e-6` cast
from `p + EPS*n`, faces with `n.w < -1e-6` cast from `p - EPS*n`, all along `w`, against one caster built from
**all** `ok` faces.
`classify_exposure(exposure, ok, slit_threshold=0.05) -> np.ndarray[uint8]` with
`EXP_DEGENERATE=0, EXP_HIDDEN=1, EXP_SLIT=2, EXP_OUTSIDE=3`.

New fixtures: `box_with_partition()` closed cube plus one inner quad (2 tris) spanning its middle -> the 2 inner
tris are `EXP_HIDDEN`, all 12 outer tris `EXP_OUTSIDE`. `open_box_with_cells()` box with one side missing and
two inner partitions parallel to the missing side, one near the opening, one deep -> deep partition exposure is
lower than the near one, both > 0, and the box's own faces are `EXP_OUTSIDE`.

- [ ] **Step 1:** failing tests for both fixtures, plus determinism (`compute_exposure` twice -> identical arrays).
- [ ] **Step 2:** implement (port of `escapes_double_sided` in `spike\10_ds_visibility.py`).
- [ ] **Step 3: real-data check** on `data\snapshots\ce26e0392ab0\CHTM_SIDE_WALK_2nd_floor.obj`: hidden count must be
  **1,853**, slit (< 5 %) **164**, outside **2,458** (spike numbers, same sampling). A different number means the port
  differs from the spike: find out why before moving on, report the cause.
- [ ] **Step 4:** Commit `feat(engine): double-sided exposure and classes`.

