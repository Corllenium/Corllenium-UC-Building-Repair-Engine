# 3D error filter — design

Date: 2026-09-26. Status: approved in the session, section by section, by the owner.

## Purpose

The owner wants to **understand** the errors in any exported building, not only fix them. In the
owner's words: "I'm not asking you to fix this, I just want you to understand the errors too". The
dashboard's 3D workspace gets a real-time filter that lights up each kind of error on the model,
especially flicker. The worked example is CHTM 5th floor, `chtm_5ft_floor.obj` from
`D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\split\`.
- It is read only through the snapshot importer (copy plus checksum), never written.
- It is imported into the dashboard as model 2, version 6: snapshot c0c877002500, 20,599 triangles.

**Success:**
- The owner opens CHTM 5th floor in the workspace and presses "Find errors".
- They toggle each error kind, isolate it, watch the flicker blink, and click a face to see what is
  wrong with it and which face it fights.
- They fly to the worst spots.
- The counts match the engine's own measurement.

## The example: what CHTM 5th floor's export contains (measured 2026-09-26)

Raw export (`chtm5_scan.py`, 20,599 triangles, 6,458 welded vertices, 18 materials,
134.5 x 128 x 16.4 ft):
- **Flicker:** 13,947 double-layer face pairs, 2,208,192 sq in shared, over 325 planes.
  - Almost all are opposite-wound, back-to-back layers inside the building.
  - Where two layers can visibly trade places: 4,876 px over the 26 guard views.
- **Exact duplicate faces:** 95 groups. All are opposite-wound, and 48 have a different material on
  each copy (texture on texture).
- **Edges:** 2,142 used by one face (open edges: holes, broken sides) and 6,066 by three or more
  (inside partitions).
- **Zero-area triangles:** 1,055.

Engine run (test only, scratch folders; `data/out_chtm5/chtm_5ft_floor/report.json`):
- 13,290 hidden inside faces (65% of the triangles).
- 2,241 T-junction points.
- 39 faces to flip, 46 thin sheets.
- 43 same-material and 49 different-material overlapping pairs.
- After the engine, 155 double-layer pairs are still left (32,215 sq in, 2,679 visible px).

## Decisions (owner's answers, 2026-09-26)

| Question | Decision |
|---|---|
| Kinds the filter lights up | **Flicker** (z-fighting), **hidden inside faces**, **reversed / back faces**, **cracks and loose bits** (T-junction points, open edges, zero-area triangles, stray fragments) |
| Where | **Both panels**: BEFORE (the raw export, every error) and AFTER (what the engine left), driven by one filter |
| What you can do | **Colour + legend with counts**, **isolate**, **blink flicker**, **click for details + a worst-spots list with fly-to** |
| When errors are computed | **A: "Find errors" once per version.** The result is saved, and filtering is instant after that. A fix run writes its AFTER version's file automatically |
| Import CHTM 5th floor | **Yes**, done: model 2, version 6 |

## 1. The workspace

- **Errors panel** beside the existing overlay toggles.
  - A panel with no error file shows a **Find errors** button with progress.
  - After that it shows the legend, with the face count per kind for that panel.
- **Legend kinds and colours** (each toggled live):

  | Kind | Colour |
  |---|---|
  | Flicker, texture on texture (different materials) | red |
  | Flicker, same material | orange |
  | Hidden inside faces | blue (drawn through walls) |
  | Reversed / back faces | purple |
  | Open edges | green lines |
  | Cracks (T-junction points) | cyan dots |
  | Zero-area triangles and stray fragments | magenta |

- **Isolate:** faces not in any checked kind fade to a faint ghost.
- **Blink flicker:** each face in a flicker pair alternates, about 4 times a second, with its partner's
  material, in both panels in step.
- **Click a face:**
  - a card shows its kind(s), face number, OBJ line, material, area and facing;
  - for flicker, it also shows the partner face (material, OBJ line, shared area) and a "select
    partner" button.
- **Worst spots:** the 20 worst places per kind (flicker by visible pixels, the rest by area), each with
  a "fly to" button that moves both synced cameras.

## 2. Engine, storage, API

- **`engine/detectors/errors.py::find_errors(mesh, profile)`** is read-only, so the mesh is never
  changed. It reuses what the fix pipeline already trusts:

  | Kind | Source |
  |---|---|
  | Hidden | `vis/exposure.py` (128 directions); `EXP_HIDDEN` |
  | Reversed | `fixes/orient.py`'s back-exposure classification |
  | Flicker | `fixes/overlap.py::double_layers`, each pair with partner, shared area, visible pixels, and same or different material |
  | Cracks | `topo/adjacency.py::find_t_vertices` |
  | Open edges | edges used by one face |
  | Zero-area and stray bits | `topo/adjacency.py::degenerate_mask`, `detectors/fragments.py` |

- **Speed:**
  - Today `double_layers` compares all faces with all. It took about 10 minutes on the raw
    CHTM 5th floor.
  - It will bucket faces by plane first, like `overlap.plane_groups`, and must return exactly the same
    pairs.
  - Target: CHTM 5th floor's whole `find_errors` in under a minute, measured.
- **Storage:** `data/errors/version-<id>.json`, holding:
  - a summary;
  - face lists per kind;
  - the flicker pairs;
  - the worst spots, with centre and camera target.

  There is no database change.
- **API:**
  - `POST /api/versions/{id}/errors` runs `find_errors` for that version.
  - `GET /api/versions/{id}/errors` returns the file, or 404 with "not computed yet".
  - The fix route writes the file for its new AFTER version.
- **CLI:** `python -m engine.cli errors <snapshot> --out <file>`.

## 3. Build, tests, deploy

- **Engine (pytest, test-first):** one fixture per kind with a known answer:
  - two coincident faces with different materials: a red pair with its partner;
  - a face sealed in a box: hidden;
  - a face turned inside out: reversed;
  - an open box edge;
  - a vertex on another triangle's edge: a crack;
  - a collapsed triangle.

  Also: the plane-bucketed flicker search equals the old one on the existing double-layer fixtures.
  The CHTM 5th floor timing is measured on the real file, not in the unit suite.
- **API (pytest, test-first, per-session test database):**
  - "not computed yet" before the button, and the file after it;
  - a fix run writes its AFTER file;
  - an unknown version is refused.
- **Web (vitest, test-first):** `web/src/utils/errorLayers.ts` holds the kinds, colours, visibility
  per face, blink schedule and worst-spots order. Then the workspace wiring: per-face colours through
  the meshbuf face ids, isolate, blink, the click card and fly-to.
- **Check on CHTM 5th floor (model 2):**
  - Find errors on BEFORE and on AFTER (after a dashboard fix run, if the owner wants one);
  - counts match `find_errors` and the report;
  - every toggle, the blink, a click and a fly-to work;
  - screenshots go to the owner.
- **Deploy:** HANDOFF section 8, from a commit. Back up the database and tag the old images first, then
  rebuild the API and web images. No migration.
- **Records:** HANDOFF, session record, ledger.

## Out of scope

- Fixing CHTM 5th floor or any building. This is for understanding.
- Database tables for errors.
- Browser-only detection.
- The Errors & fixes documentation page, which has its own spec,
  `2026-09-26-errors-and-fixes-page-design.md`. The two can share one implementation plan.
