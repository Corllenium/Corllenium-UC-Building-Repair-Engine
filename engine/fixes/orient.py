"""Outward orientation: which faces the SketchUp export wound backwards (only their BACK side can
be seen from outside), and one-sided completeness (pixels a one-sided renderer like Unity would
drop even after hidden-face removal, because the surviving face there faces away from the camera).

`compute_side_exposure` (engine.vis.exposure) already tells a face's front-side and back-side
double-sided-visibility fractions apart; this module classifies that split and acts on it.
Vertices are never moved or invented here -- `flip_faces` only reorders each flipped face's own
three corners.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

import numpy as np

from engine.guard.views import ortho_first_hit
from engine.model import MeshData
from engine.rays.caster import EmbreeCaster, ReusableCaster

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
