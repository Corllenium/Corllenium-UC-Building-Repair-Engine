"""Shared helpers for the brief-10 review probes (read-only review of dc24e9a).

Every probe builds a small synthetic mesh, runs the COMMITTED engine through `fix_object`, and
prints what ships. Run with PYTHONPATH pinned to the scratch worktree at dc24e9a, e.g.

    PYTHONPATH=<scratchpad>/review10/wt .venv/Scripts/python.exe <probe>.py
"""
from __future__ import annotations

import contextlib

import numpy as np
import shapely

import engine
from engine.fixes.pipeline import FixProfile, fix_object
from engine.tests.fixtures.build import _mesh, _quads

SMALL = FixProfile(guard_size=(240, 160), n_dirs=64)
REAL = FixProfile()                                   # 900 x 600, 128 directions


def where() -> None:
    print("engine:", engine.__file__)


def box(P, uvs, fv, fvt, fm, x0, x1, y0, y1, z0, z1, material=0, skip=()):
    """A box wound outward; `skip` names sides left out: 'bottom', 'top', 'y0', 'x1', 'y1', 'x0'.
    Returns the face ids per side."""
    b = len(P)
    P += [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
          [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    sides = {"bottom": (b + 0, b + 3, b + 2, b + 1), "top": (b + 4, b + 5, b + 6, b + 7),
             "y0": (b + 0, b + 1, b + 5, b + 4), "x1": (b + 1, b + 2, b + 6, b + 5),
             "y1": (b + 2, b + 3, b + 7, b + 6), "x0": (b + 3, b + 0, b + 4, b + 7)}
    ids = {}
    for name, quad in sides.items():
        if name in skip:
            continue
        first = len(fv)
        _quads(P, uvs, fv, fvt, fm, [quad], material=material)
        ids[name] = [first, first + 1]
    return ids


def quad(P, uvs, fv, fvt, fm, corners, material=0):
    """One quad from four corners (their order decides the winding). Returns its two face ids."""
    b = len(P)
    P += [list(map(float, c)) for c in corners]
    first = len(fv)
    _quads(P, uvs, fv, fvt, fm, [(b, b + 1, b + 2, b + 3)], material=material)
    return [first, first + 1]


def area_at(mesh, poly, z, faces=None, tol=1e-6):
    """Horizontal area of `mesh` at height `z` over the xy polygon `poly`."""
    tri = mesh.positions[mesh.face_v]
    ids = np.arange(mesh.n_faces) if faces is None else np.asarray(faces)
    tri = tri[ids]
    flat = (np.ptp(tri[:, :, 2], axis=1) <= tol) & (np.abs(tri[:, 0, 2] - z) <= tol)
    polys = [shapely.Polygon(t[:, :2]) for t in tri[flat]]
    return round(sum(p.intersection(poly).area for p in polys if p.is_valid), 3)


def fate(r, faces):
    """Per input face id: 'replaced' (a solidify piece), 'hidden' (deleted by the hidden pass),
    'kept' otherwise (still in the reference; the merge may rebuild it)."""
    kept_in = np.nonzero(~r.replaced_input)[0]
    ref_id = {int(f): i for i, f in enumerate(kept_in)}
    out = []
    for f in faces:
        if r.replaced_input[f]:
            out.append("replaced")
        elif bool(r.removed_hidden[ref_id[int(f)]]):
            out.append("hidden")
        else:
            out.append("kept")
    return out


def solidify_summary(r):
    s = r.solidify_report
    cg = [(h["round"], h["failing_pixels"], h["removed"], h.get("through_shell_px"),
           h.get("refused_together")) for h in s["cap_guard"]]
    return (f"processed {s['regions_processed']}, continued {s['top_regions_continued']}, "
            f"undersides {s['undersides_not_tops']}, blocks {s.get('blocks_standing_on_slabs')}, "
            f"walls built {s['skirts_added']} kept {s['sides_rebuilt']['edges']}, "
            f"bottoms {s['bottoms_added']}, refused walls/bottom faces "
            f"{s['walls_refused']['faces']} {s['walls_refused']['reasons']} / "
            f"{s['bottom_faces_refused']['faces']} {s['bottom_faces_refused']['reasons']}, "
            f"rep {s['representative_side_per_region']}, "
            f"cap guard (round, failing, refused, through_shell_px, together) {cg}")


@contextlib.contextmanager
def rule6_off():
    """Rule 6 switched off at dc24e9a: `_through_closed_shell` allows nothing (so `_refuse_together`
    has no records either). Everything else in the commit stays as it is."""
    from engine.guard import compare
    saved = compare._through_closed_shell

    def never(start, direction, gap, entry, planes_after, shell_caster, shell_ids, interior):
        return np.zeros(len(start), bool), np.full(len(start), -1, np.int64)

    compare._through_closed_shell = never
    try:
        yield
    finally:
        compare._through_closed_shell = saved


__all__ = ["SMALL", "REAL", "where", "box", "quad", "area_at", "fate", "solidify_summary",
           "rule6_off", "fix_object", "FixProfile", "_mesh", "np", "shapely"]
