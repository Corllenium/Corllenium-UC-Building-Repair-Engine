### Task 1: Ray casters

**Files:** Create `engine\rays\__init__.py`, `engine\rays\caster.py`, `engine\tests\test_caster.py`. Modify `pyproject.toml`
(add `trimesh>=4.5`, `embreex>=4.4` to dependencies).

**Interfaces — Produces:**
`class RayCaster(Protocol)`: `any_hit(origins (R,3), directions (R,3)) -> np.ndarray[bool]`,
`first_hit(origins, directions) -> tuple[np.ndarray[int64] tri (-1 = miss), np.ndarray[float64] t (inf = miss)]`.
`EmbreeCaster(positions (V,3) float64, faces (F,3))` and `BruteCaster(positions, faces)` both implement it.
`tri` indexes into the `faces` passed in. Callers recentre positions before constructing (float32 inside embree).

`BruteCaster` is the Moller-Trumbore implementation from `spike\04_front_hit_oracle.py` (`brute`), generalised to
per-ray directions, chunked by 256 rays, float64, hit when `t > 1e-9`.

- [ ] **Step 1: failing tests** — unit cube fixture: ray from (5,5,20) down hits top at `t = 10`; ray missing the cube
  returns `tri == -1`, `t == inf`; `any_hit` agrees with `first_hit >= 0`; and the oracle test: 2,000 deterministic rays
  (`np.random.default_rng(7)`, test code only) against `grid_slab(10,10)` + `cube()` stacked, `EmbreeCaster` and
  `BruteCaster` agree on hit/miss for >= 99.9 % of rays and on `t` within 1e-3 for every ray both hit.
- [ ] **Step 2:** implement. `EmbreeCaster` wraps `trimesh.ray.ray_pyembree.RayMeshIntersector(trimesh.Trimesh(vertices, faces, process=False))`;
  `first_hit` uses `intersects_location(..., multiple_hits=False)` and computes `t = (loc - o) . d`.
- [ ] **Step 3:** tests pass. Commit `feat(engine): ray casters with brute-force oracle`.

