# Errors & fixes page — design

Date: 2026-09-26. Status: approved in the session, section by section, by the owner.

## Purpose

The owner wants the whole session documented inside the dashboard. That means:
- every error found in the two CHTM sidewalk exports and in the engine;
- what fixed each one, with the measured result;
- what was built (walls, bottoms, the `.skp` files);
- what is still open.

Each error shows the owner's own screenshot next to a render of the same spot today. The page is
documentation: it is read, filtered and shared, not edited.

**Success:**
- The owner opens `http://localhost:5190/errors`.
- They see every error with their own words and screenshot, and a matching AFTER image.
- They can filter by model, kind of error and engine file.
- Every number on the page traces to a report or a commit.

## Decisions (owner's answers, 2026-09-26)

| Question | Decision |
|---|---|
| Where | A new **"Errors & fixes" page** in the dashboard, not inside each workspace |
| Images per error | **Before/after pair**: the owner's screenshot as BEFORE, a fresh render of the same spot from the current `.skp` as AFTER |
| Sections besides the model errors | **What we built per file**, **Still open**, **Engine bugs from reviews**. Dashboard fixes are NOT included |
| Filters | **Model** (file A / file B), **Kind of error**, **Engine file**. There is no status filter; the status shows as a badge |
| Build approach | **A: documentation shipped with the dashboard.** A committed `errors.json`; the page filters in the browser; no database change |
| Owner's screenshots | **Kept out of git.** Stored in the git-ignored `data/errors_doc/img/` and served by a small API route. `errors.json` stays in git |

The owner answered "errors from the model" for the first filter. This spec reads it as the Model
filter: which model file the error is in.

## 1. The page

- **Route `/errors`**, view `web/src/views/ErrorsView.vue`. An "Errors & fixes" button sits in the
  Models page header next to Refresh, and the page has a "← Models" link back.
- **Header:** the title, one line of purpose, and "built from commit `<sha>`, `<date>`".
- **What we built:** one card per model file, from the `report.json` behind the owner's current `.skp`:
  - triangles before → after, and back-face pixels seen from outside before → after;
  - wall strips added and their total length, bottoms added, broken side pieces replaced;
  - hidden faces removed, and faces flipped;
  - the `.skp` path with a Copy button.
- **Filter bar:** Model (All / A / B), Kind (All / the kinds below), Engine file (All / the files below).
  - The filters combine (AND) and show "N of M errors", with a Clear button.
  - The state is kept in the URL query (`?model=A&kind=sides-bottoms&engine=solidify`), so a
    filtered view can be bookmarked.
- **Three sections**, in order:
  - "Fixed & partly fixed" (model errors);
  - "Still open";
  - "Engine bugs from reviews".

  Each heading shows its filtered count, and a section with no match hides.
- **Card:**
  - title (plain words), status badge (Fixed / Partly fixed / Open), and tags for model, kind and
    engine file;
  - **What you saw:** the owner's own words, with the date, and their screenshot(s) as BEFORE;
  - **AFTER:** the render(s) of the same spot. Any image enlarges on click (a lightbox with close
    and next/previous).
  - **The error** (owner, 2026-09-26: "just indicate details, the errors and description how you
    fixed it"): what it is, where it is in the model, and why it happened, in plain words (two to
    four sentences).
  - **How we fixed it:** a plain description of what the engine now does, step by step (two to five
    sentences). Under it, in small print: the engine file and function, and the commits.
  - **Result:** numbers per model, before → after;
  - for open errors, **What's left**: what remains and where its fix waits, a branch or a brief.
- **Other screenshots you sent:** a strip at the bottom for owner screenshots that show no error (for
  example the 09-21 dashboard examples). Every image the owner sent appears somewhere.

**Kinds:** `inside-faces`, `sides-bottoms`, `lines-gridlines`, `back-faces`, `layers-flicker`,
`fragments`, `engine-bug`.

**Engine files:**
- `vis/exposure.py`, `fixes/remove.py`, `fixes/solidify.py`, `fixes/merge.py`, `fixes/orient.py`,
  `fixes/overlap.py`;
- `detectors/fragments.py`, `detectors/folds.py`;
- `guard/compare.py`, `guard/piece_rays.py`;
- `io/skp_writer.py`, `topo/adjacency.py`, `topo/planes.py`.

Only files that some entry names appear in the filter.

## 2. Content and data

### `web/public/errors/errors.json` (committed; Vite copies it into `dist/errors/`)

```json
{
  "built_from": { "commit": "ab22ff3", "date": "2026-09-25 23:53" },
  "models": [
    { "id": "A", "name": "CHTM_SIDE_WALK_2nd_floor",
      "skp": "D:/PROJECTS/UC MODEL FIXER/OBJ FIXED RESULT/CHTM_SIDE_WALK_2nd_floor.fixed.skp",
      "numbers": { "triangles": [4692, 881], "back_faces_px": [569108, 18348],
                   "wall_strips": 162, "wall_length_in": 4607, "bottoms_added": 16,
                   "pieces_replaced": 83, "hidden_removed": 2065, "faces_flipped": 672 },
      "source": "data/output_verified/CHTM_SIDE_WALK_2nd_floor/report.json at ab22ff3" }
  ],
  "errors": [
    { "id": "hidden-inside-faces", "section": "fixed", "status": "fixed",
      "title": "Hidden faces inside the slabs",
      "models": ["A", "B"], "kind": "inside-faces",
      "engine_files": ["vis/exposure.py", "fixes/remove.py"],
      "you_saw": [ { "date": "2026-09-21", "words": "how do we removed this inside of the obj ...",
                     "image": "you-0921-0809-1.png" } ],
      "after": [ { "image": "after-hidden-inside-A.png", "caption": "Same view now" } ],
      "error": "SketchUp exports every face it has, including the partition faces inside a slab. Nobody can see them from outside, but in X-ray they fill the slab, and in Unity they cost triangles and cause flicker.",
      "how_fixed": "The engine shoots 128 rays in every direction from four points on each face. A face that no ray from outside can reach is removed. Before it goes, the guard renders the model from 26 directions with and without it; if any pixel changes, the face is put back.",
      "engine_detail": "engine/vis/exposure.py compute_exposure, classify_exposure; engine/fixes/remove.py remove_faces; guard: engine/guard/compare.py guard_feedback",
      "commits": ["see the session record, section 3"],
      "result": { "A": "2,065 removed (43 put back by the guard)", "B": "2,771 removed (16 put back)" },
      "left": null,
      "source": "report.json n_removed_hidden, n_restored_by_guard" }
  ],
  "other_screenshots": [ { "date": "2026-09-21", "words": "...", "image": "you-0921-0346-1.png" } ]
}
```

Rules:
- `error` and `how_fixed` are required on every entry, in plain words. `how_fixed` on an open entry
  says what has been tried and where the fix waits.
- `section` is `fixed`, `open` or `engine-bug`. `status` is `fixed`, `partly` or `open`.
- `kind` and every `engine_files` value come from the lists in section 1.
- `image` values are plain file names matching `^[A-Za-z0-9_.-]+\.(png|webp|jpg)$`.
- Every number carries its `source`.

### Initial entries

These come from the session's records. Every number is re-read from the reports and `report.json`
when the file is written.

**Fixed & partly fixed:**
- Hidden inside faces.
- Gridlines and triangle edges on flat surfaces.
- T-junction lines.
- Lines inside flat surfaces in the `.skp`.
- Broken or missing slab sides.
- The ramp sawtooth, B region 309: close-up 43,696 → 948 back px.
- Missing bottoms.
- Reversed faces: back faces from outside A 569,108 → 18,348 px, B 464,939 → 2,869 px.
- A's margin strip wound backwards (A1).
- A's lower-landing stepped lines (A2).
- Stacked duplicate layers.
- Fragments, slivers and folds.
- Zero-area triangles.
- A's sloped-underside triangle lattice.

**Still open:**
- Double-layer sides that can flicker in Unity: A 28 / 3,724 sq in, B 2. The fix is parked on
  `wip/brief15-one-wall`.
- A's knife edge at x 2680.
- B region 107's bottom, partly rebuilt.
- M2: a real top taken for an underside.
- B4, the notch at the ramp junction.
- B8, the fin at the ramp toe.
- A's lower-landing hole 1, partly closed.
- Different-material overlaps, where "which face wins" is not built.
- Lines left in the `.skp`.

**Engine bugs from reviews:**
- Real surface deleted as debris.
- An underside taken for a top: 19,777 sq in of A's region 33 deleted.
- The side rebuild making its own double layers.
- A's merge rolled back on a pixel count.
- A floor taken as a slab's lower surface.
- The side band replacing any face.
- Rule 6 hiding real geometry.
- The regression at steps.
- The guard blind to double layers.

### The owner's screenshots

- **What the log holds:** the session log
  (`~/.claude/projects/D--PROJECTS-UC-MODEL-FIXER/5472478e-….jsonl`) holds 34 images the owner sent in
  27 messages, 2026-09-21 to 09-24:
  - direct messages: `type: "user"` with image blocks;
  - messages sent while work ran: `type: "attachment"`, `queued_command`.
- **`tools/errors_doc/extract_owner_images.py`** reads both kinds and writes each image to
  `data/errors_doc/img/you-<MMDD>-<HHMM>-<n>.<png|webp>`. It also writes
  `data/errors_doc/owner_images.json`: the file name, time, the owner's words and the log line.
- **Assignment:** the controller views every image and attaches it to the error it shows (in
  `errors.json`), or to `other_screenshots`.

### AFTER renders

- **`tools/errors_doc/render_after.py`** renders each card's AFTER view from the current owner `.skp`
  (read back with `engine/io/skp_writer.py::read_skp`):
  - double-sided, back faces purple;
  - only the edges SketchUp draws.
- **Starting code:** `docs/superpowers/records/scripts/render_skp.py`, which draws a `.skp` with only
  SketchUp's edges from fixed views, extended with a free camera. Brief 13's close-up renderer
  `docs/superpowers/records/scripts/render_skp_closeup.py` (on branch `feat/coincident-pairs`, not
  merged) already does close-ups and is copied from there.
- **Cameras** (eye, target, up, field of view, in model coordinates) live in
  `tools/errors_doc/cameras.json`, one per AFTER image. The controller sets each one to match the
  owner's screenshot.
- **Output:** `data/errors_doc/img/after-<id>.png`, at 1200 x 800.
- **Engine-bug cards** have no owner screenshot. They use the before/after renders from that round's
  report where one exists, copied into `data/errors_doc/img/`; otherwise they have no images.

### Serving the images

- `data/` is not visible to the web container, but the API mounts it, and it already serves textures
  and guard images from there.
- **New route `GET /api/docs/images/{name}`** (router `api/routers/docs.py`) returns
  `settings.data_dir / "errors_doc" / "img" / name`.
  - `name` must match `^[A-Za-z0-9_.-]+\.(png|webp|jpg)$`; anything else, or a missing file,
    returns 404.
  - The content type comes from the extension.
- The page builds image URLs as `/api/docs/images/<name>`, through nginx's `/api/` proxy on 5190.

## 3. Build, tests, deploy

**Units (test-first):**

| Unit | What it does | Tests |
|---|---|---|
| `web/src/utils/errorsDoc.ts` | Types for `errors.json`; `filterErrors`, `groupBySection`, `filterChoices`, `imageUrl` | vitest: each function; the filters combine; unknown query values are ignored |
| `web/src/views/ErrorsView.vue` | The page | vitest: mounted with sample data, a filter change changes the counts, empty sections hide |
| `web/public/errors/errors.json` | The content | vitest: every entry has the required fields, known kinds and engine files, valid image names |
| `web/src/router.ts`, `ModelsView.vue` | Route and header button | covered by the view test |
| `api/routers/docs.py` | Image route | pytest: served image and its type, missing name 404, traversal and bad extension 404 |
| `tools/errors_doc/extract_owner_images.py` | Extraction from the session log | pytest on a small sample log: both message kinds, png and webp, words kept |
| `tools/errors_doc/render_after.py` | AFTER renders | run on the real files; images read and checked by eye |
| `tools/errors_doc/check.py` | Every image named in `errors.json` exists in `data/errors_doc/img/` | run in the finish step |

**Deploy:**
- HANDOFF section 8, from a commit in the clean worktree `.claude/worktrees/dk`: rebuild the web image
  (for `dist/` with the page and `errors.json`) and the API image (for the new route).
- No database change: no migration, no write to `fixer`.
- Old images are tagged first, so a rollback is one command.

**Check:**
- `/errors` loads.
- Each filter changes the counts as expected.
- The network log shows every image 200.
- The lightbox works.
- A screenshot of the page goes to the owner.
- `check.py` passes.

**Backup:** once extracted, `data/errors_doc/img/` may be the only copy of the owner's screenshots,
because Claude Code prunes old session logs. It is zipped into `data/backups/errors_doc-<date>.zip`.

**Records:** HANDOFF sections 2 and 3, the session record's history, the ledger; all committed. Images
are never committed.

## Out of scope

- A "dashboard fixes" section (not chosen).
- A status filter (not chosen).
- Editing the content in the page.
- Database tables.
- A per-workspace error list with camera jumps.
