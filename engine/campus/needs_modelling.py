"""The per-floor "needs modelling" queue (job P2-E8c).

The owner's rule for holes (AGENTS.md section 5): the engine closes only the narrow flat fills (E8b), and every
other open spot is listed per floor so a person can model it in SketchUp. `build_needs_modelling(report, edit_log,
before_mesh)` makes that list from one `repair-unit` run:

- every row of report.json's `not_filled`: a hole E8b refused (rule and reason), or a fill the site check rolled
  back; kind `hole`. A patch's OUTER border is no hole: E8b counts those (`fill_stats.outer_boundaries`) and never
  lists them, and neither does this list: they are only counted (`counts.outer_boundaries`);
- every E8a piece the site check rolled back ON ITS OWN CHARGE: its slab side (kind `slab_side`, a wall) or slab
  bottom (kind `slab_bottom`) stays missing, so the hole stays open. Its border is the outline of the faces the piece
  would have built (report.json's `pieces[*].border`, written by `repair-unit`), its reason the Validator's reason
  that was charged most (all of them are in `detail`). A piece rolled back because its whole stage was rolled back
  (`stage_rolled_back`) is counted, not listed: it failed no check of its own. The edit log is the audit trail: a
  listed piece must have its rolled-back line there, or the report and the log describe different runs (ValueError).

Each entry (`ENTRY_KEYS`): `id` (the first 12 hex digits of the sha256 of the border's points, snapped to the OBJ's
print step, sorted and de-duplicated, so the face order of the mesh, where a loop starts and which way it runs change
nothing), `unit`, `kind`, `reason`, `rule`, `detail`, `site`/`loop`, `centroid`, `normal` (the plane's; its sign is
"up", or the largest component positive for a vertical plane: the view picks the side a viewer reaches), `bbox`,
`border` (points, in `ordered` loop order when `ordered`; an unordered set of open-edge points otherwise), `length_in`
(the closed perimeter of an ordered border; for an unordered set the BEFORE's open edges between its points, else
its bounding-box diagonal), `area_in2` (an ordered, planar, simple border: the polygon's area; a piece: its faces'
area; None otherwise), `suggested_view` and, when two spots have one border, `also` (the others; counted in
`counts.merged`). Entries are sorted by area, then length, descending (no area sorts last).

THE VIEW. `suggested_view` = `eye`, `target` (the centroid), `up`, `distance_in` (63 in = 1.6 m, the Validator's
eye height) and `source`. It is the position 1.6 m from the centroid, on the line to a Validator viewpoint
(`engine.validate.viewpoints`: its 128 outside directions, the ring of 24 cameras, the eye-height probes inside the
floors) that SAW the spot in BEFORE: a ray from the centroid to the viewpoint meets nothing on the way. Of those, the one
whose line is most square to the spot's plane wins (a spot with no plane: the most level one). Where no viewpoint saw
it, the view is 1.6 m along the normal, on a side where that line is clear (`source` "normal"). Model inches, Z up.

Only reads: nothing is written here, and `before_mesh` is not changed. Written next to `engine.fill_review`, which
draws the crops (`write_spot_crop`).
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict

import numpy as np

from engine.model import MeshData

SCHEMA_VERSION = 1
#: The camera stands this far from the centroid: the Validator's eye height, 1.6 m.
VIEW_DISTANCE = 63.0
#: A border is planar, for its area, when every point is within this many inches of its best plane.
PLANAR_TOL = 0.5
#: A viewing ray starts this far off the centroid along itself, so it does not start on a face lying under it.
_LIFT = 0.05
#: A ray from the centroid to a camera or probe has reached it when its first hit lies this close to it, or beyond.
_REACH = 0.01

KINDS = ("hole", "slab_side", "slab_bottom")
ENTRY_KEYS = ("id", "unit", "kind", "reason", "rule", "detail", "site", "loop", "centroid", "normal", "bbox",
              "border", "ordered", "length_in", "area_in2", "suggested_view")
VIEW_KEYS = ("eye", "target", "up", "distance_in", "source")
_PIECE_KIND = {"wall": "slab_side", "bottom": "slab_bottom"}
#: Rows of `not_filled` that are NOT holes (a patch's outer border), should one ever be in the list.
_NOT_A_HOLE = ("outer_boundary",)
#: Hole reasons whose `points` are not a loop in order.
_UNORDERED = ("not_a_simple_loop",)
#: Hole reasons for which a polygon area means nothing (the loop crosses itself, or is not a loop).
_NO_AREA = ("not_a_simple_loop", "self_crossing")


# ------------------------------------------------------------------------------------------ piece geometry

def piece_border(points: np.ndarray, faces: np.ndarray) -> dict:
    """The outline of a piece: `points` (n, 3) and `faces` (m, 3) indices into them. `border`: the longest closed ring
    of edges used by one face only, in order (3 decimals), else (a branching outline) the unordered boundary points
    with `ordered` False; `border_rings`: how many rings; `area_in2`: the faces' area; `normal`: their area-weighted
    mean normal (None when they cancel)."""
    points = np.asarray(points, np.float64).reshape(-1, 3)
    faces = np.asarray(faces, np.int64).reshape(-1, 3)
    tri = points[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    total = cross.sum(axis=0)
    norm = float(np.linalg.norm(total))
    uses: Counter = Counter()
    for a, b, c in faces.tolist():
        for u, v in ((a, b), (b, c), (c, a)):
            uses[(min(u, v), max(u, v))] += 1
    boundary = [e for e, n in uses.items() if n == 1]
    nbrs: dict = defaultdict(list)
    for u, v in boundary:
        nbrs[u].append(v)
        nbrs[v].append(u)
    rings, seen, ordered = [], set(), True
    if any(len(n) != 2 for n in nbrs.values()):
        ordered = False
    else:
        for start in sorted(nbrs):
            if start in seen:
                continue
            ring, prev, cur = [start], None, start
            while True:
                seen.add(cur)
                nxt = min(n for n in nbrs[cur] if n != prev)
                if nxt == start:
                    break
                ring.append(nxt)
                prev, cur = cur, nxt
            rings.append(ring)
    if ordered and rings:
        lengths = [float(np.linalg.norm(points[r] - points[r[1:] + r[:1]], axis=1).sum()) for r in rings]
        best = rings[int(np.argmax(lengths))]
        border = points[best]
    else:
        ordered = False
        border = points[sorted(nbrs)]
    return {"border": np.round(border, 3).tolist(), "border_ordered": ordered, "border_rings": len(rings),
            "area_in2": round(0.5 * float(np.linalg.norm(cross, axis=1).sum()), 4),
            "normal": None if norm < 1e-9 else np.round(total / norm, 6).tolist()}


# -------------------------------------------------------------------------------------------- small helpers

def _snapped_id(points: np.ndarray, step: float) -> str:
    """The stable id: sha256 over the border's points as integers of `step`, de-duplicated and in sorted order."""
    keys = np.unique(np.round(np.asarray(points, np.float64).reshape(-1, 3) / step).astype(np.int64), axis=0)
    return hashlib.sha256(keys.tobytes()).hexdigest()[:12]


def _sign_up(n: np.ndarray) -> np.ndarray:
    """`n` flipped so z is positive, or, for a vertical plane, so its largest component is positive."""
    if abs(n[2]) > 1e-6:
        return n if n[2] > 0 else -n
    k = int(np.argmax(np.abs(n)))
    return n if n[k] > 0 else -n


def _plane(points: np.ndarray, ordered: bool):
    """`(normal, planarity)` of the points' best plane (unit normal with sign up, None when the points do not span a
    plane) and the largest distance of a point from it."""
    if len(points) < 3:
        return None, 0.0
    centre = points.mean(axis=0)
    if ordered:                                              # Newell's: the ring's own area vector
        ring = np.roll(points, -1, axis=0)
        area = 0.5 * np.cross(points - centre, ring - centre).sum(axis=0)
        if np.linalg.norm(area) > 1e-9:
            n = area / np.linalg.norm(area)
            return _sign_up(n), float(np.abs((points - centre) @ n).max())
    _u, s, vt = np.linalg.svd(points - centre, full_matrices=False)
    if s[1] < 1e-9:                                          # collinear: no plane
        return None, 0.0
    n = vt[2] / np.linalg.norm(vt[2])
    return _sign_up(n), float(np.abs((points - centre) @ n).max())


def _perimeter(points: np.ndarray) -> float:
    return float(np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1).sum())


def _ring_area(points: np.ndarray, normal: np.ndarray) -> float:
    centre = points.mean(axis=0)
    return float(abs(0.5 * (np.cross(points - centre, np.roll(points, -1, axis=0) - centre) @ normal).sum()))


class _OpenEdges:
    """BEFORE's open edges (`analyse_topology`'s `EDGE_OPEN`), looked up lazily: their length between given points."""

    def __init__(self, mesh: MeshData | None):
        self._mesh, self._edges = mesh, None

    def run_length(self, points: np.ndarray) -> float | None:
        if self._mesh is None or not self._mesh.n_faces:
            return None
        if self._edges is None:
            from engine.pipeline import analyse_topology_memo
            from engine.topo.edges import EDGE_OPEN
            topo = analyse_topology_memo(self._mesh)
            rows = np.flatnonzero(np.asarray(topo.edge_class) == EDGE_OPEN)
            ends = np.asarray(topo.positions_w)[topo.table.edges[rows]] if len(rows) else np.zeros((0, 2, 3))
            self._edges = ends.reshape(-1, 2, 3)
        if not len(self._edges):
            return None
        step = 10.0 ** -int(self._mesh.coord_decimals)
        mine = {tuple(k) for k in np.round(points / step).astype(np.int64).tolist()}
        keys = np.round(self._edges / step).astype(np.int64)
        both = np.array([tuple(a) in mine and tuple(b) in mine for a, b in keys.tolist()], bool)
        if not both.any():
            return None
        return float(np.linalg.norm(self._edges[both][:, 0] - self._edges[both][:, 1], axis=1).sum())


# ------------------------------------------------------------------------------------------ the camera

class _Viewer:
    """The Validator's viewpoints for BEFORE, built once: `view(centroid, normal)` -> a `suggested_view` dict."""

    def __init__(self, before: MeshData | None):
        from engine.validate.checks import Settings
        from engine.validate.sampling import face_normals, recentred, used_bbox
        from engine.validate.viewpoints import interior_probes, outside_directions, pedestrian_ring
        from engine.validate.visibility import build_caster

        self.caster, self.centre = None, np.zeros(3)
        self.toward = np.zeros((0, 3))
        self.where = np.zeros((0, 3))
        self.source_of = []
        if before is None or not before.n_faces:
            return
        settings = Settings()
        b, self.centre = recentred(before)
        self.caster = build_caster(b)
        lo, hi = used_bbox(b)
        dirs = outside_directions(settings.n_directions)
        cams = pedestrian_ring((lo, hi), eye_z=lo[2] + settings.eye, n=settings.n_cameras,
                               margin=settings.camera_margin)
        probes = interior_probes(b, eye=settings.eye, caster=self.caster)
        self.toward = -dirs                                          # the Validator looks from `-dir`
        self.where = np.vstack([cams, probes]) if len(probes) else cams
        self.n_dirs, self.n_cams = len(dirs), len(cams)

    def _first(self, origins, directions):
        return self.caster.first_hit(origins, directions)

    def view(self, centroid, normal) -> dict:
        c = np.asarray(centroid, np.float64) - self.centre
        n = None if normal is None else np.asarray(normal, np.float64)
        best = None
        if self.caster is not None:
            toward = [self.toward]
            dist = [np.full(len(self.toward), np.inf)]
            if len(self.where):
                vec = self.where - c
                d = np.linalg.norm(vec, axis=1)
                toward.append(vec / np.maximum(d, 1e-9)[:, None])
                dist.append(d)
            toward, dist = np.vstack(toward), np.concatenate(dist)
            tri, t = self._first(c + _LIFT * toward, toward)
            seen = (tri < 0) | (t >= dist - _LIFT - _REACH)
            if seen.any():
                idx = np.flatnonzero(seen)
                score = np.abs(toward[idx] @ n) if n is not None else 1.0 - np.abs(toward[idx, 2])
                pick = int(idx[int(np.argmax(score))])           # argmax: the first of equals, a stable order
                source = "direction" if pick < self.n_dirs else "camera" if pick < self.n_dirs + self.n_cams else "probe"
                stand = min(VIEW_DISTANCE, float(dist[pick]))
                best = (toward[pick], stand, source)
        if best is None:
            axis = np.array([0.0, 0.0, 1.0]) if n is None else n
            best = (axis, VIEW_DISTANCE, "normal")
            if self.caster is not None:
                for sign in (1.0, -1.0):
                    tri, t = self._first((c + _LIFT * sign * axis)[None], (sign * axis)[None])
                    if tri[0] < 0 or t[0] >= VIEW_DISTANCE:
                        best = (sign * axis, VIEW_DISTANCE, "normal")
                        break
        direction, stand, source = best
        eye = c + stand * direction
        look = -direction
        up = [0.0, 1.0, 0.0] if abs(look[2]) > 0.99 else [0.0, 0.0, 1.0]
        r = lambda v: [round(float(x), 3) for x in v]
        return {"eye": r(eye + self.centre), "target": r(c + self.centre), "up": up,
                "distance_in": VIEW_DISTANCE, "source": source}


# ------------------------------------------------------------------------------------------------ the build

def _lines(edit_log) -> list[dict]:
    if edit_log is None:
        return []
    if isinstance(edit_log, (str, bytes)) or hasattr(edit_log, "read_text"):
        import json
        from pathlib import Path
        text = Path(edit_log).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return list(edit_log)


def _entry(unit, kind, reason, rule, detail, site, loop, border, ordered, area, normal, centroid, step, opens):
    pts = np.asarray(border, np.float64).reshape(-1, 3)
    plane_normal, planarity = _plane(pts, ordered)
    if normal is not None and np.linalg.norm(normal) > 1e-9:
        plane_normal = _sign_up(np.asarray(normal, np.float64) / np.linalg.norm(normal))
    if area is None and ordered and reason not in _NO_AREA and plane_normal is not None and planarity <= PLANAR_TOL:
        area = _ring_area(pts, plane_normal)
    if ordered and len(pts) >= 2:
        length = _perimeter(pts)
    else:
        length = opens.run_length(pts)
        if length is None:
            length = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    c = pts.mean(axis=0) if centroid is None else np.asarray(centroid, np.float64)
    r3 = lambda v: [round(float(x), 3) + 0.0 for x in v]
    return {"id": _snapped_id(pts, step), "unit": unit, "kind": kind, "reason": reason, "rule": rule,
            "detail": detail, "site": site, "loop": loop, "centroid": r3(c),
            "normal": None if plane_normal is None else [round(float(x), 6) + 0.0 for x in plane_normal],
            "bbox": [r3(pts.min(axis=0)), r3(pts.max(axis=0))], "border": [r3(p) for p in pts], "ordered": bool(ordered),
            "length_in": round(length, 3), "area_in2": None if area is None else round(float(area), 3)}


def build_needs_modelling(report: dict, edit_log, before_mesh: MeshData | None) -> dict:
    """The needs-modelling document of one `repair-unit` run (see the module docstring): `{"schema_version": 1,
    "unit", "counts", "entries"}`. `report`: report.json as a dict; `edit_log`: the lines of `edit_log.jsonl` (a list
    of dicts or the file's path; None skips the cross-check); `before_mesh`: the unit's BEFORE (read only). Nothing
    in the arguments is changed."""
    unit = report.get("unit") or report.get("snapshot")
    step = 10.0 ** -int(before_mesh.coord_decimals) if before_mesh is not None else 0.01
    opens = _OpenEdges(before_mesh)
    outer = int((report.get("fill_stats") or {}).get("outer_boundaries") or 0)
    entries: list[dict] = []
    for row in report.get("not_filled") or []:
        if row["reason"] in _NOT_A_HOLE:
            outer += 1
            continue
        entries.append(_entry(unit, "hole", row["reason"], row.get("rule"), row.get("detail"), row.get("site"),
                              row.get("loop"), row["points"], row["reason"] not in _UNORDERED, None, None,
                              row.get("centroid"), step, opens))
    rolled_lines = {line["site"] for line in _lines(edit_log)
                    if "check" not in line and line.get("rolled_back") and not line.get("flat_fill")}
    log_given = edit_log is not None
    stage_rolled = 0
    for piece in report.get("pieces") or []:
        if piece.get("kept"):
            continue
        reasons = dict(piece.get("reasons") or {})
        if "stage_rolled_back" in reasons:
            stage_rolled += 1
            continue
        if log_given and piece["site"] not in rolled_lines:
            raise ValueError(f"the report rolled piece site {piece['site']} back but the edit log has no rolled-back "
                             f"line for site {piece['site']}: they describe different runs")
        reason = (sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if reasons else "charged")
        if not piece.get("border"):
            continue
        entries.append(_entry(unit, _PIECE_KIND[piece["piece"]], reason, "E8-R1", reasons, int(piece["site"]), None,
                              piece["border"], piece.get("border_ordered", True), piece.get("area_in2"),
                              piece.get("normal"), None, step, opens))
    # two spots with one border are one spot
    merged, by_id = 0, {}
    for e in entries:
        if e["id"] in by_id:
            by_id[e["id"]].setdefault("also", []).append({"kind": e["kind"], "reason": e["reason"], "site": e["site"]})
            merged += 1
        else:
            by_id[e["id"]] = e
    entries = sorted(by_id.values(), key=lambda e: (-(-1.0 if e["area_in2"] is None else e["area_in2"]),
                                                    -e["length_in"], e["id"]))
    viewer = _Viewer(before_mesh)
    for e in entries:
        e["suggested_view"] = viewer.view(e["centroid"], e["normal"])
    counts = {"entries": len(entries),
              "by_kind": dict(sorted(Counter(e["kind"] for e in entries).items())),
              "by_reason": dict(sorted(Counter(e["reason"] for e in entries).items())),
              "outer_boundaries": outer, "stage_rolled_back_not_listed": stage_rolled, "merged": merged}
    return {"schema_version": SCHEMA_VERSION, "unit": unit, "counts": counts, "entries": entries}


# ----------------------------------------------------------------------------------------------- the schema

def validate_document(doc: dict) -> None:
    """Raise `ValueError` unless `doc` has the shape of `needs_modelling.json` version 1: `schema_version` 1, a
    `unit`, `counts` that agree with the entries, and entries with every key of `ENTRY_KEYS` of the right type
    (a `suggested_view` with `VIEW_KEYS`; a `crop`, when present, a string), no two with one id."""
    def need(ok, what):
        if not ok:
            raise ValueError(f"needs_modelling.json: {what}")

    def vec(v, n=3):
        return isinstance(v, list) and len(v) == n and all(isinstance(x, (int, float)) for x in v)

    need(isinstance(doc, dict) and doc.get("schema_version") == SCHEMA_VERSION, f"schema_version must be {SCHEMA_VERSION}")
    need("unit" in doc and isinstance(doc.get("entries"), list) and isinstance(doc.get("counts"), dict),
         "unit, counts and entries are required")
    ids = set()
    for k, e in enumerate(doc["entries"]):
        missing = [key for key in ENTRY_KEYS if key not in e]
        need(not missing, f"entry {k} lacks {missing}")
        need(isinstance(e["id"], str) and len(e["id"]) == 12 and e["id"] not in ids, f"entry {k}: id must be 12 hex, unique")
        ids.add(e["id"])
        need(e["kind"] in KINDS, f"entry {k}: kind {e['kind']!r} is not one of {KINDS}")
        need(isinstance(e["reason"], str) and vec(e["centroid"]), f"entry {k}: reason and centroid")
        need(e["normal"] is None or vec(e["normal"]), f"entry {k}: normal")
        need(isinstance(e["bbox"], list) and len(e["bbox"]) == 2 and all(vec(p) for p in e["bbox"]), f"entry {k}: bbox")
        need(isinstance(e["border"], list) and e["border"] and all(vec(p) for p in e["border"]), f"entry {k}: border")
        need(isinstance(e["length_in"], (int, float)) and (e["area_in2"] is None or isinstance(e["area_in2"], (int, float))),
             f"entry {k}: length_in and area_in2")
        view = e["suggested_view"]
        need(isinstance(view, dict) and all(key in view for key in VIEW_KEYS) and vec(view["eye"]) and vec(view["target"])
             and vec(view["up"]), f"entry {k}: suggested_view needs {VIEW_KEYS}")
        need("crop" not in e or isinstance(e["crop"], str), f"entry {k}: crop must be a path string")
    counts = doc["counts"]
    need(counts.get("entries") == len(doc["entries"]), "counts.entries disagrees with the entries")
    need(counts.get("by_kind") == dict(sorted(Counter(e["kind"] for e in doc["entries"]).items())),
         "counts.by_kind disagrees with the entries")
    need(counts.get("by_reason") == dict(sorted(Counter(e["reason"] for e in doc["entries"]).items())),
         "counts.by_reason disagrees with the entries")
