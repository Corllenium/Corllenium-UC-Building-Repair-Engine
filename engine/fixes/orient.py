"""Outward orientation: which faces the SketchUp export wound backwards (only their BACK side can
be seen from outside), and one-sided completeness (pixels a one-sided renderer like Unity would
drop even after hidden-face removal, because the surviving face there faces away from the camera).

`compute_side_exposure` (engine.vis.exposure) already tells a face's front-side and back-side
double-sided-visibility fractions apart; this module classifies that split and acts on it.
Vertices are never moved or invented here -- `flip_faces` only reorders each flipped face's own
three corners.

Brief 11 item 1 adds one rule on top of the per-face verdict, `orient_sheets`: a THIN face -- both
sides exposed, which the per-face rule never flips -- is wound like the connected near-coplanar
SHEET it belongs to, when that sheet's windings disagree and the change measures no more back
pixels over the guard views.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np
import shapely

from engine.guard.views import VIEWS_26, ortho_first_hit
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster, ReusableCaster
from engine.topo.adjacency import build_edge_table, edge_face_lists
from engine.topo.edges import COPLANAR_ANGLE
from engine.topo.planes import plane_basis

ORIENT_OK = 0
ORIENT_FLIP = 1
ORIENT_THIN_SHEET = 2


def classify_orientation(front: np.ndarray, back: np.ndarray, ok: np.ndarray,
                          sheet_ratio: float = 0.5) -> np.ndarray:
    """Per-face orientation verdict (uint8), from `compute_side_exposure`'s `front`/`back`
    fractions: `ORIENT_THIN_SHEET` when both sides are exposed (`front > 0` and `back > 0`) and
    roughly equally so (`min(front, back) / max(front, back) >= sheet_ratio`); else `ORIENT_FLIP`
    when `back > front` (the face's only real exposure is on the side its winding calls "back" --
    it was wound into the model); else `ORIENT_OK`.

    A hidden face (`front == back == 0`) or a degenerate (`not ok`) face is always `ORIENT_OK`:
    hidden faces get removed anyway (see `engine.fixes.pipeline.fix_object`), and a degenerate
    face has no orientation to speak of.

    THIN_SHEET WINS. A sheet that really is seen from both sides has no outward side to be wound
    towards, so "which side sees more sky" is not evidence about its winding -- anything standing
    near one of its faces tips `back > front` by a few per cent. Flipping one of those does not
    correct anything; it just moves the one-sided hole to the other side, which is strictly worse
    because that side was equally visible. The review found about 35 genuine thin sheets flipped
    on file A this way (47 reported where 82 were measured), each opening a hole. FLIP is reserved
    for the lopsided case the check was written for: a face whose front is blind (a panel wound
    into the model), where the ratio is nowhere near `sheet_ratio`.
    """
    front = np.asarray(front, dtype=np.float64)
    back = np.asarray(back, dtype=np.float64)
    ok = np.asarray(ok, dtype=bool)
    out = np.full(len(front), ORIENT_OK, dtype=np.uint8)

    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.minimum(front, back) / np.maximum(front, back)
    sheet = ok & (front > 0.0) & (back > 0.0) & (ratio >= sheet_ratio)
    out[sheet] = ORIENT_THIN_SHEET
    out[ok & ~sheet & (back > front)] = ORIENT_FLIP
    return out


def flip_faces(mesh: MeshData, flip: np.ndarray) -> MeshData:
    """Reverse the vertex order of `face_v` and `face_vt` for every face where `flip` (bool,
    `(mesh.n_faces,)`) is True, so their winding points outward; `positions` (and every other
    vertex/UV/normal ROW) is untouched -- only which of a face's already-existing corners comes
    first changes. The source `vn` of a flipped face is dropped to `-1` for all three corners
    rather than reversed: reordering a normal INDEX does not fix a normal VECTOR that still points
    the old (now wrong) way, and no vector is negated here (see module docstring)."""
    flip = np.asarray(flip, dtype=bool)
    if flip.shape != (mesh.n_faces,):
        raise ValueError(f"flip must have shape ({mesh.n_faces},), got {flip.shape}")

    face_v = mesh.face_v.copy()
    face_vt = mesh.face_vt.copy()
    face_vn = mesh.face_vn.copy()
    face_v[flip] = face_v[flip][:, ::-1]
    face_vt[flip] = face_vt[flip][:, ::-1]
    face_vn[flip] = -1
    return replace(mesh, face_v=face_v, face_vt=face_vt, face_vn=face_vn)


def face_unit_normals(positions_c: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """`(F, 3)` unit winding normal of every triangle of `faces` (rows of `positions_c`); an
    all-zero row for a zero-area triangle, which therefore never counts as seen from its back."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    tri = positions_c[np.asarray(faces, dtype=np.int64)]
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1)
    unit_normal = np.zeros_like(normal)
    safe = length > 0.0
    unit_normal[safe] = normal[safe] / length[safe, None]
    return unit_normal


def backface_counts(rendered, normals: np.ndarray) -> list[int]:
    """Per render of `rendered` (`(view, HitBuffers)` pairs, as `engine.fixes.pipeline._render`
    returns them), in that order: how many pixels' FIRST hit is a face met on its BACK side --
    the face's winding normal points away from the viewer, `n . direction > 0` along the ray.

    That is SketchUp's blue-purple, measured: SketchUp paints a face's back side in its own
    colour, and a one-sided renderer (Unity) drops those pixels altogether. `normals` is a unit
    normal per `tri` id of the renders (`face_unit_normals` of the faces they were cast with), so
    counting a render the caller already made costs nothing."""
    normals = np.asarray(normals, dtype=np.float64)
    out: list[int] = []
    for _view, buf in rendered:
        hit = buf.tri >= 0
        if not hit.any():
            out.append(0)
            continue
        direction = np.asarray(buf.direction, dtype=np.float64)
        out.append(int(((normals[buf.tri[hit]] @ direction) > 1e-9).sum()))
    return out


def backface_pixels(positions_c: np.ndarray, faces: np.ndarray, face_ids: np.ndarray,
                    views: Sequence[Sequence[float]], size: tuple[int, int],
                    caster_factory=EmbreeCaster) -> list[int]:
    """Render `faces` over `views` and count, per view in `views` order, the pixels that DO hit
    in a double-sided render (`ortho_first_hit` never culls backfaces) but whose first-hit face
    is back-facing to that view's camera -- see `backface_counts`. `faces`/`face_ids` follow
    `ortho_first_hit`'s own convention: `faces[i]` is labelled `face_ids[i]`, so callers may
    render a named subset. The camera is framed on `positions_c`, so two calls over the same
    `positions_c` (the input's faces and the final mesh's, say) count the same pixels."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    face_ids = np.asarray(face_ids, dtype=np.int64)

    unit_normal = face_unit_normals(positions_c, faces)
    normals_by_id = np.zeros((int(face_ids.max()) + 1 if len(face_ids) else 0, 3))
    if len(face_ids):
        normals_by_id[face_ids] = unit_normal

    # ReusableCaster: one embree BVH build for this geometry, reused across every view.
    reused_caster = ReusableCaster(caster_factory)
    rendered = ((view, ortho_first_hit(positions_c, faces, face_ids, view, positions_c, size,
                                       reused_caster)) for view in views)
    return backface_counts(rendered, normals_by_id)


def one_sided_holes(positions_c: np.ndarray, faces: np.ndarray, face_ids: np.ndarray,
                     views: Sequence[Sequence[float]], size: tuple[int, int],
                     caster_factory=EmbreeCaster) -> int:
    """Count, over every view, the pixels that DO hit in a double-sided render (`ortho_first_hit`
    never culls backfaces) but whose first-hit face is back-facing to that view's camera --
    exactly the pixels a one-sided renderer (Unity, by default) would leave as a hole even though
    hidden-face removal already ran. `faces`/`face_ids` follow `ortho_first_hit`'s own convention:
    `faces[i]` is labelled `face_ids[i]` in the returned hit buffer, so callers may render a named
    subset. Reported once as a single total across all `views` -- the sum of `backface_pixels`,
    which keeps the per-view breakdown."""
    return int(sum(backface_pixels(positions_c, faces, face_ids, views, size, caster_factory)))


@dataclass
class SheetOrientation:
    #: Bool over the faces `orient_sheets` was given: re-wound by the sheet rule -- on top of,
    #: never instead of, the per-face verdict's own flips.
    flip: np.ndarray
    #: See `orient_sheets`.
    report: dict


def _sheet_labels(positions_c: np.ndarray, faces: np.ndarray, normals: np.ndarray,
                  include: np.ndarray, cos_angle: float) -> np.ndarray:
    """A sheet label per face (-1 where not `include`d): faces joined through a shared edge when
    their planes agree within the angle whose cosine is `cos_angle`, WHATEVER their windings
    (`|n . n'|`), and when they lie on OPPOSITE sides of that edge -- two faces folded onto the
    same side of it overlap, which is a fold or a double layer, not one surface running on."""
    n = len(faces)
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    table = build_edge_table(faces, include)
    for e, members in enumerate(edge_face_lists(table)):
        if len(members) < 2:
            continue
        a, b = (int(v) for v in table.edges[e])
        pa, t = positions_c[a], positions_c[b] - positions_c[a]
        members = [int(f) for f in members]
        for i, f in enumerate(members):
            side = np.cross(t, normals[f])
            third_f = next(int(v) for v in faces[f] if v != a and v != b)
            s_f = float((positions_c[third_f] - pa) @ side)
            for g in members[i + 1:]:
                if abs(float(normals[f] @ normals[g])) < cos_angle:
                    continue
                third_g = next(int(v) for v in faces[g] if v != a and v != b)
                if s_f * float((positions_c[third_g] - pa) @ side) < 0.0:
                    parent[find(f)] = find(g)
    labels = np.full(n, -1, np.int64)
    roots: dict[int, int] = {}
    for f in np.nonzero(include)[0]:
        labels[f] = roots.setdefault(find(int(f)), len(roots))
    return labels


def _lying_on_another(positions_c: np.ndarray, faces: np.ndarray, normals: np.ndarray,
                      area: np.ndarray, include: np.ndarray, f: int, cos_angle: float,
                      tol: float) -> bool:
    """Does another `include`d face lie ON face `f` -- parallel to it within the sheet angle,
    every corner within `tol` of its plane, and overlapping it in that plane by more than a
    thousandth of the smaller one's area (`engine.fixes.solidify._Planes.lying_on`'s test)?"""
    tri = positions_c[faces]
    lo, hi = tri[f].min(axis=0) - tol, tri[f].max(axis=0) + tol
    cand = np.nonzero(include & (tri.max(axis=1) >= lo).all(axis=1)
                      & (tri.min(axis=1) <= hi).all(axis=1))[0]
    cand = cand[(cand != f) & (np.abs(normals[cand] @ normals[f]) >= cos_angle)]
    cand = cand[np.abs((tri[cand] - tri[f][0]) @ normals[f]).max(axis=1) <= tol]
    if not len(cand):
        return False
    e1, e2 = plane_basis(normals[f])
    basis = np.stack([e1, e2], axis=1)
    mine = shapely.Polygon((tri[f] - tri[f][0]) @ basis)
    for g in cand.tolist():
        shared = mine.intersection(shapely.Polygon((tri[g] - tri[f][0]) @ basis)).area
        if shared > max(1e-4, 1e-3 * min(float(area[f]), float(area[g]))):
            return True
    return False


def orient_sheets(positions_c: np.ndarray, faces: np.ndarray, front: np.ndarray,
                  back: np.ndarray, flipped: np.ndarray, thin: np.ndarray, ok: np.ndarray, *,
                  tol: float, angle_deg: float = COPLANAR_ANGLE,
                  views: Sequence[Sequence[float]] = VIEWS_26, size: tuple[int, int] = (900, 600),
                  caster_factory=EmbreeCaster, centre: np.ndarray | None = None
                  ) -> SheetOrientation:
    """Brief 11 item 1: wind every THIN face consistently with the connected near-coplanar sheet
    it belongs to, and measure it.

    WHY. The per-face rule (`classify_orientation`) never flips a thin face -- both sides
    exposed, roughly equally -- because on its own such a face has no outward side (R1a). But a
    thin face is often one cell of a larger surface whose outward side is plain: file A's big
    landing has a sloped underside of 234 faces in one plane, and the cells of its east strip
    that have no top are single faces of that plane seen from above as well as from below. Wound
    up while the rest of the underside faces down, they showed their back to every view from
    below (triage A1: five purple strips), and SketchUp drew a line along every border between
    two cells wound opposite ways (brief 10 item 7).

    THE RULE. Faces (`faces`, welded rows of `positions_c`, all present in the state being
    oriented) form SHEETS: joined through a shared edge when their planes agree within
    `angle_deg`, whichever way each is wound, and when they lie on opposite sides of that edge
    (`_sheet_labels`). Windings are read AFTER the per-face verdict (`flipped`). A sheet whose
    windings disagree is made consistent where the evidence allows:
    1. its side is the one the sheet as a whole is more exposed on -- the area-weighted side
       exposure (`front`/`back`, as each face is wound in `faces`, swapped for a face in
       `flipped`), ties to the side of its largest face;
    2. only its THIN faces (`thin`) facing the other way are re-wound. A lopsided face keeps its
       own verdict: it was seen from one side, and that is evidence the sheet's total is not;
    3. never a face another face lies ON (`_lying_on_another`): re-winding one of an
       opposite-wound coincident pair would make it look like a duplicate layer to the overlap
       pass, and that is the one operation that must never happen to such a pair -- nor can the
       guard see it happen, since a flip never changes a double-sided render. (Brief 13 reduces
       an EXACT same-material, same-UV pair to one face, by its own measured conditions, in
       `engine.fixes.overlap.plan_coincident_removal` -- never by re-winding here.);
    4. MEASURED: the sheet is re-wound only when its back pixels -- pixels over `views` at
       `size` whose first hit is one of its faces met on its back -- do not go up. Flipping never
       changes a double-sided render, so ONE render of `faces` counts every face's pixels on each
       side, and a sheet's count after the change is exact.

    A sheet whose windings already agree is left as it is, thin faces and all: that is R1a's
    free-standing sheet, whose "more exposed side" is noise.

    Returns `SheetOrientation(flip, report)`, `flip` bool over `faces`. `report`:
    `{"sheets_mixed", "sheets_made_consistent", "sheets_refused", "faces_flipped",
    "faces_lying_on_another", "back_px": {"before", "after"}, "sheets": [...]}` -- `back_px` over
    every face given, before and after the re-winding; `sheets` one entry per sheet whose
    windings disagreed, `{"faces", "thin_against", "flipped", "back_px": [before, after],
    "front": unit normal of the side chosen, "bbox": [[min], [max]] in the model's coordinates
    (`positions_c + centre`), "verdict": "made_consistent" | "refused" | "nothing_to_flip"}`,
    sorted by bbox. Deterministic: sheets are labelled in face order."""
    positions_c = np.asarray(positions_c, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    front = np.asarray(front, dtype=np.float64)
    back = np.asarray(back, dtype=np.float64)
    flipped = np.asarray(flipped, dtype=bool)
    thin = np.asarray(thin, dtype=bool)
    ok = np.asarray(ok, dtype=bool)
    centre = np.zeros(3) if centre is None else np.asarray(centre, dtype=np.float64)
    n_faces = len(faces)
    flip = np.zeros(n_faces, dtype=bool)
    report = {"sheets_mixed": 0, "sheets_made_consistent": 0, "sheets_refused": 0,
              "faces_flipped": 0, "faces_lying_on_another": 0,
              "back_px": {"before": 0, "after": 0}, "sheets": []}
    if not n_faces:
        return SheetOrientation(flip, report)

    tri = positions_c[faces]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = 0.5 * np.linalg.norm(cross, axis=1)
    include = ok & (area > 0.0)
    normals = np.zeros_like(cross)
    normals[include] = cross[include] / (2.0 * area[include, None])
    sign = np.where(flipped, -1.0, 1.0)
    current = normals * sign[:, None]                     # each face's normal as it will ship
    side_front = np.where(flipped, back, front)           # exposure of the side `current` faces
    side_back = np.where(flipped, front, back)
    cos_angle = float(np.cos(np.radians(angle_deg)))

    # every face's pixels on its current front and back, from ONE render per view
    front_px = np.zeros(n_faces, dtype=np.int64)
    back_px = np.zeros(n_faces, dtype=np.int64)
    ids = np.arange(n_faces, dtype=np.int64)
    reused = ReusableCaster(caster_factory)
    for view in views:
        buf = ortho_first_hit(positions_c, faces, ids, view, positions_c, size, reused)
        hit = buf.tri >= 0
        if not hit.any():
            continue
        f = buf.tri[hit]
        seen_back = (current[f] @ np.asarray(buf.direction, dtype=np.float64)) > 1e-9
        np.add.at(back_px, f[seen_back], 1)
        np.add.at(front_px, f[~seen_back], 1)
    before_total = int(back_px.sum())

    labels = _sheet_labels(positions_c, faces, normals, include, cos_angle)
    order = np.argsort(labels, kind="stable")
    bounds = np.flatnonzero(np.diff(labels[order])) + 1
    for members in np.split(order, bounds):
        if len(members) < 2 or labels[members[0]] < 0:
            continue
        largest = int(members[np.lexsort((members, -area[members]))[0]])
        s = np.sign(current[members] @ current[largest])
        if (s > 0).all() or (s < 0).all():
            continue
        report["sheets_mixed"] += 1
        plus = float((area[members] * np.where(s > 0, side_front[members],
                                                side_back[members])).sum())
        minus = float((area[members] * np.where(s > 0, side_back[members],
                                                 side_front[members])).sum())
        want = 1.0 if plus >= minus else -1.0
        against = members[(s != want) & thin[members]]
        lying = {int(f) for f in against
                 if _lying_on_another(positions_c, faces, normals, area, include, int(f),
                                      cos_angle, tol)}
        report["faces_lying_on_another"] += len(lying)
        candidates = np.array([int(f) for f in against if int(f) not in lying], np.int64)
        before = int(back_px[members].sum())
        after = before + int(front_px[candidates].sum() - back_px[candidates].sum())
        if not len(candidates):
            verdict = "nothing_to_flip"
        elif after <= before:
            verdict = "made_consistent"
            flip[candidates] = True
            report["sheets_made_consistent"] += 1
            report["faces_flipped"] += int(len(candidates))
        else:
            verdict = "refused"
            report["sheets_refused"] += 1
        corners = tri[members].reshape(-1, 3) + centre
        report["sheets"].append({
            "faces": int(len(members)), "thin_against": int(len(against)),
            "flipped": int(len(candidates)) if verdict == "made_consistent" else 0,
            "back_px": [before, after if verdict == "made_consistent" else before],
            "front": np.round(current[largest] * want, 4).tolist(),
            "bbox": [np.round(corners.min(axis=0), 2).tolist(),
                     np.round(corners.max(axis=0), 2).tolist()],
            "verdict": verdict})
    report["sheets"].sort(key=lambda d: (d["bbox"], d["faces"]))
    after_total = before_total + int(front_px[flip].sum() - back_px[flip].sum())
    report["back_px"] = {"before": before_total, "after": after_total}
    return SheetOrientation(flip, report)
