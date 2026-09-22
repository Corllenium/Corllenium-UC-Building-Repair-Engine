# HERMES Agent — Project Memory: UC MODEL FIXER

**Project Directory:** `D:\PROJECTS\UC MODEL FIXER`  
**Target File:** `UC-campus-FIXED-v2026-07-11 - CHECKPOINT-17.skp` (148 MB SketchUp export)  
**Target Engine:** Unity 6000.4.7f1 / URP 17.4.0 (`CampusDoubleSided.cs`, `_Cull = 0`)  
**Active Plan:** `docs/superpowers/plans/2026-09-22-dashboard-and-engine-continuation.md`

---

## 1. Dedicated Machine Ports & Host Rules
Never use default ports (5173, 8000, 5432) — other services run on this machine:
- **Web Dashboard:** `http://localhost:5190` (Vite `strictPort: true`)
- **API Server:** `http://127.0.0.1:8190` (FastAPI / Uvicorn)
- **PostgreSQL 16:** `127.0.0.1:5490` (Docker container `fixer-db`, container port 5432)
- *Host Services:* `uc-dashboard` on `127.0.0.1:8200`, `ui-tars-model` on `8090`, legacy preview on `5180`.

---

## 2. Hard Invariants & Guardrails
- **Double-sided rendering by default**: Match SketchUp & Unity campus shaders. Single-sided is only a diagnostic canvas toggle.
- **Vertices are never moved or invented**: Planar region merging triangulates over existing welded vertices only.
- **Blocked operations** (these previously destroyed model geometry):
  - Tolerance weld > 0.1 mm
  - Blender `select_interior_faces` (deleted 88% of geometry)
  - Generic hole-filling / "Make Manifold" / Decimation / Poisson or Voxel remeshing
  - Treating opposite-normal coincident pairs as duplicates
- **Invariants after every fix**:
  - Region surface area must never grow (cannot bridge openings).
  - Material count unchanged.
  - Bounding box identical.
  - Guard verdict pass: 0 holes, 0 changed materials across 26 orthographic views.

---

## 3. Project Structure
```
engine/       Pure computational geometry (no SQL/HTTP imports).
              - rays/: Intel Embree raycaster (4.9M rays/s) & numpy Moller-Trumbore oracle.
              - vis/: 128-direction Fibonacci exposure & orientation classification.
              - guard/: 26-view orthographic camera guard with rollback feedback.
              - fixes/: Zero-area drop, orientation flip, Shapely Delaunay planar merge.
              - io/: Exact f-line OBJ reader/writer, snapshot manager.
              - transport/: Binary meshbuf encoder.
              - tests/: 164 passing tests (pytest engine/tests -q).
api/          FastAPI + SQLAlchemy 2 + Alembic + Docker Postgres on port 5490.
              - Connects web frontend to engine.fixes.pipeline.
web/          Vue 3 + Vite + TypeScript + Three.js on port 5190.
              - Side-by-side synchronized viewports (BEFORE vs AFTER).
              - Edge overlays: blue gridlines, black outlines, gray diagonals, red x-ray hidden.
```

---

## 4. Current Progress & Execution State
- **Phase 0 & 1A**: Complete.
- **Phase 2E (Fix Pipeline)**: Complete, tested, and verified on real data (`CHTM_SIDE_WALK_2nd_floor` and `CHTM_2nd_to_3rd_building_sidewalk_outside` reduced by 43-65% tris with 0 damaged pixels).
- **Active Task**: Building the web dashboard (Task 1 to Task 8 in `docs/superpowers/plans/2026-09-22-dashboard-and-engine-continuation.md`) to drive the fix pipeline and visualize BEFORE / AFTER in real time.
