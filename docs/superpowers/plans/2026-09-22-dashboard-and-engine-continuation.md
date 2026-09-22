# UC Model Fixer: Dashboard Build & Engine Continuation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the interactive web dashboard (FastAPI backend on port 8190, Vue 3 + Three.js frontend on port 5190, PostgreSQL on port 5490) connecting directly to the verified Phase 2E fix engine, establish the roadmap for continuing engine capabilities (coplanar overlaps, multi-object occlusion, thin sheets), and integrate specialized geometry libraries and machine learning auditing.

**Architecture:** 
The system operates in three clean tiers:
1. `engine\`: Pure computational geometry, ray casting via Intel Embree (`embreex`), planar merging with Shapely, and 26-view orthographic visual guard with rollback feedback. Independent of databases or web frameworks.
2. `api\`: FastAPI + SQLAlchemy 2 + PostgreSQL 16 (Docker) exposing snapshot import, mesh analysis, binary `meshbuf` streaming, and asynchronous fix jobs executing the engine pipeline.
3. `web\`: Vue 3 + TypeScript + Three.js delivering side-by-side synchronized viewports (BEFORE vs. AFTER), edge classification toggles (gridlines, outlines, diagonals, x-ray hidden), face picking mapped to exact source OBJ `f` lines, and visual guard diff inspection.

**Tech Stack:** 
- Backend/Engine: Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, Alembic, psycopg 3, Pydantic v2, NumPy 2, Shapely 2.1, Trimesh, Embreex 4.4, Pillow, Pytest.
- Database: PostgreSQL 16 in Docker (port 5490).
- Frontend: Node 22, pnpm, Vite 5, Vue 3, Vue Router, Three.js 0.170, OrbitControls, Vitest.
- Geometry & AI Options: Google Manifold (`manifold3d`), `libigl` (Generalized Winding Numbers), Vision-Language Model (VLM) for multimodal visual guard QA (port 8090).

**Spec:** `docs\superpowers\specs\2026-09-21-uc-model-fixer-design.md`
**Prior Plans:** `docs\superpowers\plans\2026-09-21-phase1a-engine-foundations.md`, `docs\superpowers\plans\2026-09-21-phase1b-api-and-canvas.md`, `docs\superpowers\plans\2026-09-21-phase2e-fix-pipeline.md`

---

## Global Constraints

- **Port Isolation**: Never use default ports 5173, 8000, or 5432 to avoid collision with existing services on the host machine.
  - Web Dashboard: **http://localhost:5190** (`strictPort: true` in Vite).
  - API Server: **http://127.0.0.1:8190**.
  - PostgreSQL: **127.0.0.1:5490** (container internal 5432).
  - Host Services: `uc-dashboard` runs on 8200, `ui-tars-model` runs on 8090.
- **Double-Sided Default**: Canvas and ray-casters must default to double-sided rendering (`_Cull = 0`), matching SketchUp and Unity campus shaders. Single-sided is strictly a diagnostic toggle.
- **Strict Invariants**:
  - Vertices are never moved and never invented. Merged regions triangulate over existing welded vertices only.
  - Bounding box must remain identical; material count must remain unchanged.
  - Region surface area must not grow (bridge openings).
  - Facade guard must pass with 0 holes and 0 changed materials across 26 views.
- **Data Safety**: Originals are immutable. Snapshots are never written to after creation. All fix outputs go to `data\output\`.

---

## Part 1: Project Understanding & Current State

### The Problem
The SketchUp campus model (`CHECKPOINT-17.skp`, 148 MB) exported to OBJ for Unity 6 (URP 17.4) carries severe modeling artifacts:
1. **Gridlines / Over-Subdivision**: Internal walls and SketchUp guides cut continuous flat slabs into thousands of tiny coplanar triangles, causing T-junction micro-cracks, shimmering pixels, and draw-call/vertex overhead.
2. **Hidden Interior Geometry**: Partition walls, interior floor plates, and structural faces trapped inside slabs that are 100% occluded from the outside.
3. **Reversed Winding**: 4-18% of faces have flipped normals. Unity hides this with `_Cull = 0`, which breaks standard PBR lighting and produces black surfaces or holes when backface culling is enabled.
4. **Non-Manifold Open Sheets**: The model is an open, non-manifold architectural assembly with thousands of edges shared by 3+ faces. **Black-box mesh repair tools (Blender `select_interior_faces`, Make Manifold, Poisson reconstruction, Remeshers) destroy the model** (Blender deleted 88% of valid geometry).

### What Has Been Built & Proven
- **Phase 0 (Spike)**: Verified that Intel Embree (`embreex`) achieves 4.9M rays/sec on CPU; proved double-sided visibility logic.
- **Phase 1A (Engine Foundations)**: Built OBJ reader/writer pinning exact `f` line indices, snapshot manager, topology weld/plane/edge extraction, and binary `meshbuf` transport.
- **Phase 2E (Fix Engine Pipeline)**: Built complete automated fix pipeline in `engine\fixes\pipeline.py` with 164 passing tests:
  - *Zero-area face removal*.
  - *Double-sided exposure calculation* via 128 Fibonacci ray directions.
  - *Hidden face removal* with an automated 26-view orthographic guard that rolls back any face removal causing even 1 pixel of visual damage.
  - *Outward orientation flipping* for back-facing visible surfaces.
  - *Planar region merging* with Shapely constrained Delaunay triangulation over existing vertices only.
  - *Polygon / NGON export* and honest edge classification.
  - **Real Data Results**:
    - `CHTM_SIDE_WALK_2nd_floor.obj`: 4,692 -> 2,656 tris (43.4% reduction), 1,819 hidden faces removed, 0 damaged guard pixels.
    - `CHTM_2nd_to_3rd_building_sidewalk_outside.obj`: 7,227 -> 2,499 tris (65.4% reduction), 2,381 hidden faces removed, 0 damaged guard pixels.

### Where the Dashboard Was Left Behind
Phase 1B was specified in detail (`docs\superpowers\plans\2026-09-21-phase1b-api-and-canvas.md`), but development prioritized proving the geometry engine first (Phase 2E). The dashboard code in `api\` and `web\` has not yet been implemented. Now that the engine is fully verified and producing real fixes, we can build the dashboard directly against the working fix pipeline.

---

## Part 2: Continuing the Engine Roadmap

Beyond the current pipeline (hidden removal + orientation flip + planar merge), the engine will be expanded with the following modules:

### Module A: Coplanar Overlap & Z-Fight Resolver (Phase 3b)
- **Problem**: Faces sharing the exact same plane and orientation fighting for the same pixels in Unity (flickering).
- **Engine Solution**:
  - Group coplanar faces by plane equation within `1.5 * sum(|n_i| * q_i)`.
  - Perform 2D polygon intersection in the plane coordinate system using Shapely.
  - If overlap coverage is $\ge 99\%$, mark the duplicate/redundant face for deletion.
  - If overlap is partial ($< 99\%$), compute polygon difference to clip the overlapping patch without introducing non-collinear vertices.

### Module B: Thin-Sheet Two-Sided Completer
- **Problem**: Balustrades, railings, and signs are modeled as zero-thickness single sheets. When Unity switches to standard backface culling (`_Cull = 2`), their backs disappear.
- **Engine Solution**:
  - The exposure module already detects `ORIENT_THIN_SHEET` (faces where front and back exposure are both $> 0$ with ratio $\ge 0.5$).
  - For accepted thin sheets, generate a twin opposite-facing triangle with inverted winding and offset normal, giving clean two-sided appearance under single-sided culling without duplicating internal solids.

### Module C: Multi-Object Neighbor Occlusion (Campus Assembly)
- **Problem**: In the full campus, a sidewalk meets a building facade or terrain. Currently, faces against the building are classified as outside because the building is not loaded during sidewalk fixing.
- **Engine Solution**:
  - Allow `fix_object` to accept `neighbour_casters: list[RayCaster]`.
  - Ray casting tests occlusion against `self_caster + neighbour_casters`.
  - Tag occluded faces as `EXP_HIDDEN_BY_NEIGHBOUR`. Guard verifies they are safe to remove when the neighbor is present.

### Module D: Boundary T-Junction Snapping & Seam Sealing
- **Problem**: When adjacent slabs have different subdivision levels along their shared boundary, floating vertices cause micro-gaps (sparkling pixels) in Unity.
- **Engine Solution**:
  - Extract boundary poly-lines.
  - Project boundary vertices from the more subdivided neighbor onto the collinear border edge of the simpler neighbor, splitting the border edge at exact projection points.

---

## Part 3: Special Libraries & Machine Learning Integration

### 1. Robust Geometric Computing Libraries
| Library | Capability | Integration Role in UC Model Fixer |
|---|---|---|
| **Google Manifold (`manifold3d`)** | Ultra-fast, exact topological booleans and spatial partitioning. | Can replace or augment 2D Shapely clipping for complex multi-plane intersections and 3D boolean overlaps without floating-point drift. |
| **`libigl`** | Fast Generalized Winding Numbers (Jacobson et al.). | Evaluates volumetric inside/outside status on open, defective polygon soups without requiring watertight shells. Ideal secondary heuristic for ambiguous interior geometry. |
| **Intel Embree (`embreex`)** | High-throughput BVH ray-tracing on CPU (already integrated). | Stays the core workhorse for 128-direction exposure calculation and 26-view orthographic guard (4.9M rays/sec). |

### 2. Machine Learning / AI Integration Opportunities
- **Why NOT Generative 3D or Neural Remeshers?**
  - Neural surface reconstruction (POCO, Points2Surf, Neural Dual Contouring, NeRF/Gaussian Splats, SDFs) converts geometry into continuous density fields or marching-cubes blobs.
  - **Fatal for CAD/BIM**: They destroy exact UV coordinates, round sharp 90-degree architectural edges, invent non-planar curvature, and wipe out multi-material assignments.
  - Strict computational geometry with mathematical invariants must remain the core geometry modifier.

- **Where Machine Learning Excels: Multimodal Visual Guard QA (VLM)**:
  - The engine generates 26-direction orthographic before/after/diff renders (`guard_<view>.png`).
  - **AI Integration**: Connect a Vision-Language Model (such as the local `ui-tars-model` running on port 8090, or Hermes/Gemini/Claude vision) to act as an automated architectural QA inspector:
    1. Scan the diff images for semantic defects: "Is a door frame missing?", "Is there texture stretching?", "Are curb outlines distorted?".
    2. Score visual fidelity and produce structured QA notes for the user dashboard.
  - **Semantic Geometry Classification**:
    - Train or prompt a lightweight classifier to tag regions as `road`, `walkway`, `curb`, `wall`, or `steps` based on plane normal, UV scale, and area, automatically assigning optimal tolerance profiles per element.

---

## Part 4: Step-by-Step Dashboard Implementation Plan

### Task 1: Docker Database & API Environment Scaffolding
**Files:**
- Create: `docker-compose.yml`, `.env.example`, `.env`
- Modify: `pyproject.toml`
- Create: `api\__init__.py`, `api\settings.py`, `api\db.py`, `api\main.py`
- Test: `api\tests\conftest.py`, `api\tests\test_health.py`

- [ ] **Step 1:** Update `docker-compose.yml` defining PostgreSQL 16 on port `5490` with database `fixer` and user `fixer`.
- [ ] **Step 2:** Start database container (`docker compose up -d db`) and verify connection on port `5490`.
- [ ] **Step 3:** Add backend dependencies to `pyproject.toml` (`fastapi>=0.115`, `uvicorn[standard]>=0.30`, `sqlalchemy>=2.0`, `psycopg[binary]>=3.2`, `alembic>=1.13`, `pydantic-settings>=2.4`, `httpx>=0.27`).
- [ ] **Step 4:** Implement `api\settings.py` (env-based configuration reading `FIXER_DATABASE_URL`, `FIXER_SOURCE_DIR`, `FIXER_DATA_DIR`).
- [ ] **Step 5:** Implement `api\db.py` (SQLAlchemy 2 engine, session factory, `get_db` dependency).
- [ ] **Step 6:** Implement `api\main.py` with `/api/health` endpoint reporting database status.
- [ ] **Step 7:** Run `pytest api/tests/test_health.py` and confirm PASS.

---

### Task 2: Database Models & Alembic Migrations
**Files:**
- Create: `alembic.ini`, `api\alembic\env.py`, `api\alembic\versions\0001_initial.py`
- Create: `api\models.py`
- Test: `api\tests\test_db_models.py`

- [ ] **Step 1:** Define SQLAlchemy models in `api\models.py`:
  - `Model`: `id`, `name`, `source_file`, `created_at`
  - `ModelVersion`: `id`, `model_id`, `kind` (`snapshot`, `preview`, `fixed`), `sha256`, `tri_count`, `coord_quantum`, `origin_offset`, `created_at`
  - `VersionAsset`: `id`, `version_id`, `kind` (`obj`, `mtl`, `texture`, `report`), `path`, `sha256`
  - `IssueType`: `key`, `name`, `description`, `default_action`
  - `FixRun`: `id`, `model_version_id`, `status`, `config`, `report_json`, `created_at`
- [ ] **Step 2:** Create initial Alembic migration `0001_initial.py` seeding core `issue_types` (`degenerate`, `excess_subdivision`, `oriented_visibility`, `coplanar_overlap`).
- [ ] **Step 3:** Run `alembic upgrade head` against database on port `5490`.
- [ ] **Step 4:** Write and run test verifying table schemas and seed data integrity.

---

### Task 3: API Importer & Snapshot Service
**Files:**
- Create: `api\services\importer.py`
- Create: `api\routers\source.py`, `api\routers\models.py`
- Modify: `api\main.py`
- Test: `api\tests\test_importer.py`

- [ ] **Step 1:** Implement `api\services\importer.py` wrapping `engine.io.snapshot.snapshot_object`:
  - Inspects manifest and source files under `FIXER_SOURCE_DIR`.
  - Creates snapshot version in `data\snapshots\`.
  - Persists `Model` and `ModelVersion` rows.
  - Idempotent: returns existing version when SHA256 matches.
- [ ] **Step 2:** Implement `GET /api/source/files`: lists available OBJ exports in the source directory.
- [ ] **Step 3:** Implement `POST /api/models/import`: takes file name, executes snapshot import, returns model info.
- [ ] **Step 4:** Implement `GET /api/models`: lists all imported models with latest snapshot and fixed versions.
- [ ] **Step 5:** Run tests verifying import idempotency and manifest validation.

---

### Task 4: Meshbuf Streaming, Fix Execution & Diff Endpoints
**Files:**
- Create: `api\routers\versions.py`, `api\routers\fixes.py`
- Modify: `api\main.py`
- Test: `api\tests\test_meshbuf_endpoint.py`, `api\tests\test_fix_endpoint.py`

- [ ] **Step 1:** Implement `GET /api/versions/{id}/meshbuf`: streams binary `meshbuf` for 3D canvas consumption with custom headers (`X-Tris-Count`, `X-Face-Count`).
- [ ] **Step 2:** Implement `GET /api/versions/{id}/textures/{name}`: serves snapshot material textures.
- [ ] **Step 3:** Implement `POST /api/versions/{id}/fix`: triggers `engine.fixes.pipeline.fix_object` as a background task, storing resulting fixed version, report, and guard images.
- [ ] **Step 4:** Implement `GET /api/runs/{id}`: returns fix execution status, progress, and `FixResult` metrics.
- [ ] **Step 5:** Implement `GET /api/runs/{id}/guard/{view}`: serves guard triptych PNGs for visual inspection.

---

### Task 5: Web Frontend Setup (Vue 3 + Vite + TypeScript)
**Files:**
- Create: `web\package.json`, `web\vite.config.ts`, `web\tsconfig.json`, `web\index.html`
- Create: `web\src\main.ts`, `web\src\App.vue`, `web\src\router.ts`
- Create: `web\src\api\client.ts`

- [ ] **Step 1:** Scaffold `web\` directory with `package.json` specifying Vue 3, Vite, TypeScript, Three.js (`three@0.170.0`, `@types/three`), and Pinia.
- [ ] **Step 2:** Configure `web\vite.config.ts` with `server.port = 5190`, `strictPort = true`, and proxy `/api` to `http://127.0.0.1:8190`.
- [ ] **Step 3:** Implement typed API client `web\src\api\client.ts` fetching models, triggering imports, and running fixes.
- [ ] **Step 4:** Configure Vue Router with `/` (Model List) and `/workspace/:id` (Dual-Canvas Workspace).
- [ ] **Step 5:** Verify frontend builds via `pnpm --dir web build`.

---

### Task 6: Binary Meshbuf Decoder & Synced Dual Viewports
**Files:**
- Create: `web\src\three\meshbuf.ts`
- Create: `web\src\three\Viewport.ts`
- Create: `web\src\three\sync.ts`
- Create: `web\src\components\CanvasWorkspace.vue`

- [ ] **Step 1:** Implement `web\src\three\meshbuf.ts` parsing binary `meshbuf` (JSON header, Float32 vertex positions, Float32 vertex colors, edge flags, face IDs).
- [ ] **Step 2:** Implement `web\src\three\Viewport.ts` encapsulating Three.js Scene, Camera, WebGLRenderer, OrbitControls, double-sided lighting, and layer management.
- [ ] **Step 3:** Implement `web\src\three\sync.ts` binding two Viewports with bidirectional camera position and target synchronization.
- [ ] **Step 4:** Implement layer toggles:
  - `Gridlines` (blue lines on flat surface divisions).
  - `Region Outlines` (dark borders around planar patches).
  - `Triangle Diagonals` (gray mesh lines).
  - `X-Ray Hidden Faces` (transparent facade with red hidden faces highlighted).
  - `Diagnostic One-Sided` toggle.

---

### Task 7: Interactive Face Picking, Issue Overlays & Live Fix UI
**Files:**
- Create: `web\src\three\picking.ts`
- Create: `web\src\views\WorkspaceView.vue`
- Create: `web\src\views\ModelsView.vue`
- Create: `web\src\components\GuardDiffModal.vue`

- [ ] **Step 1:** Implement GPU/Raycast face picking in `web\src\three\picking.ts`: clicking any triangle retrieves its `face_id`, coordinates, normal, material, and corresponding source OBJ line.
- [ ] **Step 2:** Build `ModelsView.vue`: displays available source campus exports, import status, triangle counts, and one-click import button.
- [ ] **Step 3:** Build `WorkspaceView.vue`:
  - Top Toolbar: model selector, fix profile sliders (`slit_threshold`, `flat_texture_std`), layer checkboxes, and "Run Fix Pipeline" button.
  - Center: Synced BEFORE (Snapshot) and AFTER (Fixed) 3D viewports.
  - Bottom Stats Bar: Live reduction percentage, removed hidden count, flipped normals count, and guard verification status.
- [ ] **Step 4:** Build `GuardDiffModal.vue`: modal allowing the user to click through all 26 orthographic guard camera views to inspect before/after/diff PNGs.

---

### Task 8: Verification & End-to-End Delivery
**Files:**
- Test: `web\tests\e2e.test.ts` or interactive browser check

- [ ] **Step 1:** Start Docker DB (`docker compose up -d db`), start API (`.venv/Scripts/python.exe -m uvicorn api.main:app --port 8190`), start frontend (`pnpm --dir web dev`).
- [ ] **Step 2:** Import `CHTM_SIDE_WALK_2nd_floor.obj` via dashboard UI at `http://localhost:5190`.
- [ ] **Step 3:** Trigger fix pipeline from dashboard, verify live progress updates, and observe BEFORE vs. AFTER models loaded in synced canvases.
- [ ] **Step 4:** Verify edge class overlays, face picking, and guard diff modal render properly without errors.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-22-dashboard-and-engine-continuation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.
**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
