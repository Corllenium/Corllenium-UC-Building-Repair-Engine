# UC Repair Engine — P1 (kernel, speed, decision hook) and P2 (one engine per error kind) Implementation Plan

> **For agentic workers:**
> - **Claude:** REQUIRED SUB-SKILL superpowers:subagent-driven-development.
> - **Hermes:** start at `HERMES.md`; take only jobs marked `hermes` or `either`.
> - Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn today's fix pipeline into a kernel of independent engines:
- one engine per error kind, each hardened;
- each engine gated by the Validator (the owner's rule: textures there, problems solved, nothing visible
  deleted or covered, from outside and at eye height inside);
- each engine fast enough for the campus's 60-92 k-triangle units;
- a decision hook that lets Jev suggest the answers the rules cannot give.

**Architecture:**
- `engine/repair/`:
  - typed `Edit`s grouped into `Site`s;
  - an edit log keyed by face fingerprints;
  - `repair_unit` runs the engines in the proven order, validates every site and rolls back the failures
    by bisection;
  - `engine/repair/engines/e1..e8.py` wrap or extend today's modules.
- `engine/decide/`: the `Decider` (rules → Jev suggestion → owner queue).
- `engine/validate/visual.py`: the owner's close-up facade check. Before/after renders of every outside wall
  go to Gemini vision, which flags differences for the owner. This is a second opinion **next to** the exact
  Validator, never instead of it.

**Tech stack:** as P0. Optional: `typesafe-sdk` (Jev, from P0 task 17). Gemini vision through the existing
`D:\PROJECTS\UC\00-CLAUDE\visual-stack\research-agent\gemini-look.py` (the owner's key, local).

**Spec:** `docs/superpowers/specs/2026-10-03-uc-repair-engine-design.md` §4, §5, §9 (all approved 2026-10-03).

## Global Constraints

- **Everything in P0's Global Constraints applies.**
- **Integration branch:** `feat/repair-p1p2`, made from `feat-dashboard` after P0 merges. Each job runs on
  its own branch and worktree.
- **Rolling briefs.** A task here fixes the goal, files, interfaces, order and exit criteria. **The exact
  failing tests for an engine are written and committed by Claude just before its job is queued** (they
  depend on the measured census and the Validator v0 verdicts). A Hermes build job is always "make these
  committed tests pass without changing them".
- **Every engine's exit criteria (hardening):**
  - its fixtures and unit tests pass;
  - **mutation tests:** the Validator catches every deliberately broken variant of the engine;
  - deterministic: two runs give the identical result;
  - time and memory within budget on the largest golden unit;
  - kill-and-resume safe;
  - the **Validator PASSES** on the golden units: CHTM 5th floor, plus 3 diverse units chosen from the
    census;
  - every spot the owner marks wrong becomes a fixture.
- **The owner's rules are binding:**
  - the strict visible rule;
  - interiors count;
  - back-to-back pairs keep the side facing a viewer;
  - the E5 cut and the E8 flat fill are the only exceptions (`AGENTS.md` §4, §5).
  - Jev only suggests until promoted (`AGENTS.md` and spec §9).
- **Hermes branches never change** `engine/guard/**`, `FixProfile` thresholds or existing tests unless the
  brief says so; `hermes-reviewer` rejects them otherwise.

## Jobs

| Task | Job | Who | Depends on | Delivers |
|---|---|---|---|---|
| K1 Repair types | P1-K1 | claude | P0 merged | `engine/repair/types.py`: `Edit`, `Site`, `UnitState`, `RepairContext`, `RepairEngine` protocol, face fingerprints |
| K2 Observe-only kernel | P1-K2 | claude | P1-K1 | `repair_unit` wraps today's `fix_object` stages as engines; `report.json` byte-identical on A, B, CHTM 5th; edit log written |
| K3 Site validation + rollback | P1-K3 | claude | P1-K2, P0-16 | after each engine, validate the touched sites (Validator, fast mode); bisect and roll back the failing ones |
| D1 Decider, rules only | P1-D1 | either | P1-K1 | `engine/decide/decider.py`: question types, providers chain, log, cache by state hash, modes OFF/SUGGEST/AUTO, promotion stats |
| D2 Jev provider | P1-D2 | claude | P1-D1, P0-17 | the Jev provider behind the Decider, using the pilot's wrapper |
| S1 T-junction spatial hash | P1-S1 | **hermes** | P0-12 | `find_t_vertices` drops from edges × vertices to near-linear; identical output on every fixture and on CHTM 5th |
| S2 One topology per stage | P1-S2 | either | P1-K2 | `analyse_topology` reused instead of recomputed 4-5 times; byte-identical reports |
| S3 double_layers by plane | P1-S3 | **hermes** | P0-12 | the pair search grouped by plane, with a chunked pixel stage; identical pairs on the fixtures and CHTM 5th; memory bounded |
| E1 Loose, invisible only | P2-E1 | **hermes** | P1-K3 | fragment and sliver removal only where no viewpoint sees the piece; visible debris listed with a crop |
| E2 Reversed + single-sided check | P2-E2 | either | P1-K3 | `orient.py` as an engine; a Unity single-sided render check; a ray-parity second opinion |
| E3 Hidden, interior-aware | P2-E3 | claude | P1-K3, P0-14 | removal only when unseen from outside AND from the interior probes; never side meshes or room surfaces |
| E4 Same look | P2-E4 | claude review, hermes finish | P1-K3 | review and finish brief 13 (`feat/coincident-pairs`) and brief 15 item 2 (`wip/brief15-one-wall`) as an engine; tint looks per the owner's decision sheet |
| E5 Different look, both windings | P2-E5 | claude | P1-K3, P1-D1 | opposite pairs keep the side facing a viewer; same-facing pairs by the patch rule, then continuity, then the Decider; the cut along the winner's border; the named z-fight guard class |
| E6 Cracks + classify_edges | P2-E6 | claude | P1-K3 | the `classify_edges` T-junction bug fixed with A/B proof; threading kept |
| E7 Gridlines | P2-E7 | either | P1-K2 | the region merge as an engine (no behaviour change); area never grows |
| E8 Holes, strict | P2-E8 | claude | P1-K3 | solidify covers only 0 %-visible faces; the narrow flat fill (owner exception); the "needs modelling" queue with a SketchUp helper |
| V1 Close-up facade check | P2-V1 | **hermes** | P0-16 | `engine/validate/visual.py`: before/after close-up renders of every outside wall; Gemini vision compares each pair; `visual_check.json` plus flagged crops in the floor review |
| R1 Golden-unit runs | P2-R1 | either | each engine | the engine on the golden units, with Validator verdicts, timings and evidence, in the ledger |

**Order:**
1. K1 → K2 → (D1 ∥ S2) → K3.
2. S1 and S3 run as soon as the census exists (P0-12). They are speed-only and judged by identical outputs.
3. The engines in the pipeline's proven order: E8 solidify → E3 → E1 → E2 → E4 → E5 → E6 + E7.
4. V1 as soon as the Validator exists.
5. D2 after the Jev pilot.

---

### Task K1: repair types (claude)

**Files:** Create `engine/repair/__init__.py`, `engine/repair/types.py`, `engine/tests/test_repair_types.py`.

**Interfaces (produced, consumed by every engine and the kernel):**
```python
FaceKey = str     # sha256 of the 3 vertices snapped to the print step (sorted per face, winding kept) + look key

@dataclass(frozen=True)
class Edit:
    engine: str                    # "E1" .. "E8"
    kind: str                      # "remove" | "flip" | "add" | "cut"
    faces: tuple[int, ...]         # input face ids it removes, flips or replaces
    new_faces: np.ndarray | None   # (k, 3) vertex ids for "add" / "cut"
    new_points: np.ndarray | None  # (m, 3) new positions: only E8 solidify and the E5 cut
    site: int
    reason: str
    evidence: dict                 # the numbers behind it: exposure, coverage, areas, look keys
    decision: dict | None = None   # {"question", "provider", "answer", "confidence"} when the Decider was asked

@dataclass
class UnitState:  mesh: MeshData; topo; looks: dict[int, str]; viewpoints; neighbours: list[MeshData]
@dataclass
class RepairContext: profile: FixProfile; decider; validator; log: list
class RepairEngine(Protocol):
    name: str
    def plan(self, unit: UnitState, ctx: RepairContext) -> list[Edit]: ...
def face_keys(mesh: MeshData, looks: dict[int, str]) -> list[FaceKey]
def apply_edits(mesh: MeshData, edits: list[Edit]) -> tuple[MeshData, np.ndarray]   # new mesh + new→old face map
```

**Exit:**
- `face_keys` is stable under face and vertex reordering (property test);
- `apply_edits` with no edits returns an identical mesh;
- remove, flip, add and cut round-trip on fixtures;
- an `Edit` with `new_points` from any engine other than E5 or E8 raises.

### Task K2: observe-only kernel (claude)

- **Files:** Create `engine/repair/kernel.py`, `engine/repair/engines/legacy.py`, `engine/tests/test_kernel_observe.py`.
- **What:** `repair_unit(unit, ctx)` runs today's `fix_object` stages through thin engine wrappers, in the
  same order and with the same parameters, and writes `edit_log.jsonl`.
- **Exit:**
  - `report.json` is **byte-identical** to today's `engine.cli fix` on sidewalk A, sidewalk B and CHTM 5th;
  - the edit log accounts for every face removed or added.

### Task K3: site validation and rollback (claude)

- **What:** after each engine, run the Validator (P0) in fast mode on the touched sites only. A failing site
  is bisected down to the smallest failing set of edits; those are rolled back and logged with the
  Validator's evidence.
- **Exit:**
  - a deliberately bad edit mixed into good ones is the only one rolled back (fixture);
  - the time per site is within the budget measured on CHTM 5th.

### Task D1: Decider, rules only (either)

- **What:** spec §9:
  - question types with typed schemas and state builders;
  - the providers chain;
  - `data/decide/log.jsonl`;
  - a cache by state hash;
  - modes, and promotion statistics per question type (agreement with the owner's later decisions).
- **Exit:**
  - with only the rule provider, every question gets a rule answer or goes to the owner queue;
  - the log and cache round-trip;
  - promotion stays off below 50 decisions or below 95 %;
  - demotion happens below 90 % over the last 30.

### Task D2: Jev provider (claude)

- **What:** wire the P0-17 `JevDecider` in as a provider (SUGGEST by default); batch per floor; daily cost
  cap; the no-key fallback.
- **Exit:** with a fake client, answers flow, the gate respects confidence, and the cap stops calls. A live
  smoke run happens only with the owner's key.

### Tasks S1-S3: speed (S1 and S3 hermes; S2 either)

**Rule for all three:** outputs must be **identical** to before; the old function stays as the test oracle.

| Task | Change | Target | Exit |
|---|---|---|---|
| S1 | `engine/topo/adjacency.py::find_t_vertices`: replace the edge × vertex loop with a uniform-grid spatial hash (cell = the longest edge's bounding-box size, capped) | near-linear | same result as the old function on every fixture and on CHTM 5th; ≥ 10× faster on CHTM 5th, measured |
| S2 | reuse one `analyse_topology` per pipeline stage | — | byte-identical reports on A, B, CHTM 5th; time measured |
| S3 | `engine/fixes/overlap.py::double_layers`: group candidate pairs by fitted plane before the bounding-box test, and process the pixel stage in chunks of at most 1 M rows | — | identical `pair_list` on the fixtures and on CHTM 5th; peak memory measured and bounded |

### Tasks E1-E8: the engines

Each one:
- wraps or extends the module the spec names;
- is an `RepairEngine` with `plan()`;
- goes through K3's validation and rollback;
- meets the hardening exit criteria above.

The briefs, with failing tests, are written just before each is queued; the table above gives the owner and
the dependencies. Specifics already decided:

- **E1:** a debris piece is removed only if the Validator's viewpoints (outside plus interior probes) see
  none of its samples. Every visible piece goes to the floor review with a crop.
- **E2:** a flip must make the face's front face its viewers (single-sided check). Thin faces are never
  flipped alone.
- **E3:** faces unseen from outside AND from every interior probe, and not on a side mesh, may be removed.
  Winding-number second opinion (libigl; its install needs the owner's OK) only where exposure and probes
  disagree.
- **E4:** brief 13's coincident-pair rule; brief 15 item 2's one wall per side plane. Tint groups follow
  the owner's decision sheet (P0-13).
- **E5:**
  - Pairs are taken from `double_layers` with both windings.
  - Opposite pairs: remove the copy whose front faces away from every viewer. Both sides seen with
    different looks → the Decider (`e5.winner`), and the owner.
  - Same-facing pairs:
    - (a) a patch inside a bigger face of the same source group wins;
    - (b) else the look and UV continuing the plane's neighbours win;
    - (c) else the Decider.
  - The cut: `overlap.region_frame` → shapely difference → `constrained_delaunay_triangles` → `fit_uv`;
    the new points snap to the winner's border.
  - The guard class "z-fight resolved": AFTER equals one of the BEFORE candidates, at these sites only.
- **E6:** `topo/edges.py:80-87` keeps TJUNCTION only where a covering sub-edge exists. A/B: open-edge
  counts on A, B and CHTM 5th before and after, with every change explained.
- **E7:** today's merge, wrapped; "area never grows" except E8 fill sites.
- **E8:**
  - solidify's `cover_max_exposure` becomes 0 (the strict rule);
  - the narrow flat fill: a planar border matching a neighbour plane, earcut or constrained Delaunay on the
    existing points only, each fill shown in the review;
  - everything else goes to `needs_modelling.json`, with a SketchUp helper script that opens a view at the
    spot.

### Task V1: the owner's close-up facade check (hermes)

**Files:** Create `engine/validate/visual.py`, `engine/tests/test_validate_visual.py`. Add the CLI
`validate-visual`.

**What:**
1. For a unit, find the outside walls (facade faces, from the Validator's outside visibility) and group them
   into wall patches (about 3 × 3 m).
2. For each patch, render a close-up, 800 px, from 2 m in front, BEFORE and AFTER, with the same camera.
   Use the existing ray-cast renderer, textured with the frozen textures.
3. Compare each pair:
   - first, a pixel difference: equal pairs skip;
   - then Gemini vision through `gemini-look.py`, with a fixed prompt: "Same wall before and after a cleanup:
     is any surface, texture or opening different? Answer SAME or DIFFERENT and say where."
4. Write `visual_check.json` (per patch: pixel diff, Gemini answer, crop paths). DIFFERENT patches go to the
   floor review.

**Exit:**
- identical renders give SAME with no Gemini call;
- a deliberately removed facade face makes its patch DIFFERENT (Gemini call mocked in the tests; one live
  call in the acceptance run);
- the cost per floor is reported.

**Rule:** this is a second opinion for the owner. A DIFFERENT patch with an exact Validator PASS is a review
item, not an automatic failure. The exact Validator decides PASS or FAIL.

### Task R1: golden-unit runs (either)

Per engine, as it lands:
- the golden units (CHTM 5th plus 3 from the census);
- the Validator verdicts and the visual check;
- timings and memory;
- the evidence crops;
- triangle counts before and after.

All of it goes in the ledger and the floor-review data.

---

## After P2

- P3 (runner, the per-building outputs, the comparison `.skp`) gets its own plan.
- The owner's floor reviews start there.
- Hosting: the H-series jobs, from H1's facts, plan the VPS deploy of web + API + DB behind Traefik with a
  login. Heavy compute stays on the PC.
