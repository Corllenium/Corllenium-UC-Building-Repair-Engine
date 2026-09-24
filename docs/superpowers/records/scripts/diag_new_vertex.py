"""Diagnostic only: which merge region is skipped as `new_vertex`, by which path, and by how much.

Wraps `engine.fixes.merge._pieces` (plan-time path: a union ring coordinate with no existing vertex
within snap_tol) and `engine.fixes.merge._cdt_triangles` (build-time path) for one `fix_object` run.
"""
import sys
from pathlib import Path

import numpy as np

import engine.fixes.merge as M
import engine.fixes.pipeline as P
from engine.cli import _load_snapshot

snap = Path(sys.argv[1])
events = []

_orig_pieces = M._pieces


def pieces_wrap(union, vertex_xy, vertex_ids, snap_tol):
    out = _orig_pieces(union, vertex_xy, vertex_ids, snap_tol)
    if out is None:
        worst = []
        for poly in M._polygons(union):
            for ring in [poly.exterior, *poly.interiors]:
                c = np.asarray(ring.coords)[:-1]
                d = np.sqrt(((c[:, None, :] - vertex_xy[None, :, :]) ** 2).sum(-1)).min(axis=1)
                bad = np.flatnonzero(d > snap_tol)
                worst.extend((float(d[i]), c[i].round(3).tolist()) for i in bad)
        worst.sort(reverse=True)
        events.append(dict(path="plan:_pieces None", n_vertices=len(vertex_ids), snap_tol=snap_tol,
                           n_bad=len(worst), worst=worst[:6]))
    return out


M._pieces = pieces_wrap

_orig_cdt = M._cdt_triangles


def cdt_wrap(polygon, plan, rings):
    got = _orig_cdt(polygon, plan, rings)
    if got is None:
        events.append(dict(path="build:_cdt_triangles None", region=plan.region,
                           n_members=len(plan.members), n_vertices=len(plan.vertex_ids),
                           normal=np.round(plan.normal, 4).tolist()))
    return got


M._cdt_triangles = cdt_wrap

# record the region id / member count / planarity of every region the plan loop visits, by
# wrapping the frame helper the loop calls first for each region
_orig_frame = M._region_frame
frames = []


def frame_wrap(positions_w, face_w, members):
    fr = _orig_frame(positions_w, face_w, members)
    if fr is not None:
        normal, origin, basis = fr
        vids = np.unique(face_w[members])
        resid = np.abs((positions_w[vids] - origin) @ normal)
        frames.append(dict(n_members=len(members), normal=np.round(normal, 4).tolist(),
                           max_off_plane=float(resid.max()), n_events_before=len(events)))
    return fr


M._region_frame = frame_wrap

obj_path, mesh, flatness, _ = _load_snapshot(snap)
res = P.fix_object(mesh, flatness, P.FixProfile())
print("tris", res.mesh.n_faces, "skipped", res.merge_report["regions_skipped"])
for e in events:
    # the region whose frame was taken last before this event is the one that failed
    owner = [f for f in frames if f["n_events_before"] <= events.index(e)]
    print(e)
    if owner and e["path"].startswith("plan"):
        f = owner[-1]
        print("   region: members", f["n_members"], "normal", f["normal"], "max off-plane %.4f in" % f["max_off_plane"])
