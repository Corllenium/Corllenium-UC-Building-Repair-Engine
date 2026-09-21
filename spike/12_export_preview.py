"""Export BEFORE/AFTER data for the throwaway preview page (preview/index.html).

BEFORE  all non-degenerate faces, hidden-inside faces flagged (double-sided visibility + guard feedback)
AFTER   hidden faces removed, then every flat region re-triangulated (UV ignored: textures are flat noise,
        every border vertex kept so no new cracks). AFTER is depth-guarded against BEFORE over 26 views.
"""
import itertools
import json
from pathlib import Path

import numpy as np
import shapely
from PIL import Image

from _common import FILES, ROOT, SNAP, load_obj, tri_geometry, weld

here = Path(__file__).parent


def funcs(filename, stop):
    nsx = {"__file__": str(here / filename)}
    exec(compile((here / filename).read_text(encoding="utf-8").split(stop)[0], filename, "exec"), nsx)
    return nsx


V10 = funcs("10_ds_visibility.py", "\ndef run(name, images):")
V11 = funcs("11_guard_feedback.py", "\n# 26 views")
R = V10["ns"]["R"]
first_hit, TOL = V11["first_hit"], V11["TOL"]
VIEWS = [tuple(np.array(v, float) + np.array([0.013, 0.007, 0.011]))
         for v in itertools.product((-1, 0, 1), repeat=3) if any(v)]
PREVIEW = ROOT / "preview" / "data"


def guard(before, Pc_after, faces_after, frame):
    ids = np.arange(len(faces_after))
    total = model = 0
    for (bd, _), v in zip(before, VIEWS):
        ad, _ = first_hit(Pc_after, faces_after, ids, v, frame)
        fb, fa = np.isfinite(bd), np.isfinite(ad)
        with np.errstate(invalid="ignore"):
            total += int(((fb & ~fa) | (fb & fa & (np.abs(bd - ad) > TOL))).sum())
        model += int(fb.sum())
    return total, model


def hidden_faces(Pc, fw, normals, ok):
    hidden = ok & (V10["escapes_double_sided"](Pc, fw, normals, ok) == 0)
    ids_ok = np.nonzero(ok)[0]
    before = [first_hit(Pc, fw[ids_ok], ids_ok, v, Pc) for v in VIEWS]
    for _ in range(8):
        keep = np.nonzero(ok & ~hidden)[0]
        restore, dmg_total = set(), 0
        for (bd, bt), v in zip(before, VIEWS):
            ad, _ = first_hit(Pc, fw[keep], keep, v, Pc)
            fb, fa = np.isfinite(bd), np.isfinite(ad)
            with np.errstate(invalid="ignore"):
                dmg = (fb & ~fa) | (fb & fa & (np.abs(bd - ad) > TOL))
            dmg_total += int(dmg.sum())
            t = bt[dmg]
            restore.update(t[hidden[t]].tolist())
        if dmg_total == 0 or not restore:
            break
        hidden[list(restore)] = False
    return hidden, before


def edge_sets(fw, include, plabel):
    pairs = np.sort(np.stack([fw[:, [0, 1]], fw[:, [1, 2]], fw[:, [2, 0]]], axis=1), axis=2)
    idx = np.nonzero(include)[0]
    flat = pairs[idx].reshape(-1, 2)
    owner = np.repeat(idx, 3)
    edges, inv = np.unique(flat, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    order = np.argsort(inv, kind="stable")
    splits = np.cumsum(np.bincount(inv, minlength=len(edges)))[:-1]
    return edges, np.split(owner[order], splits)


def flat(a, nd=3):
    return np.round(np.asarray(a, float).reshape(-1), nd).tolist()


def export(name):
    m = load_obj(SNAP / name)
    P, fw = weld(m)
    area, normals, _, deg = tri_geometry(P, fw)
    ok = ~deg
    Pc = P - (P.min(0) + P.max(0)) / 2
    _, quanta = R.axis_quanta(SNAP / name, P)
    hidden, before = hidden_faces(Pc, fw, normals, ok)
    visible = ok & ~hidden
    tri = Pc[fw]
    plabel, planes = R.cluster_planes(tri, normals, area, m["fm"], visible, quanta)

    # BEFORE edges: on the full mesh. grid = edge where a hidden wall meets two coplanar visible faces
    edges_all, owners_all = edge_sets(fw, ok, plabel)
    grid, tri_before, outline_before = [], [], []
    for e, faces in zip(edges_all, owners_all):
        vis = [f for f in faces if visible[f]]
        if not vis:
            continue
        labels = {int(plabel[f]) for f in vis}
        seg = Pc[e]
        if len(vis) >= 2 and len(labels) == 1:
            (grid if any(hidden[f] for f in faces) else tri_before).append(seg)
        else:
            outline_before.append(seg)

    # AFTER geometry: per plane cluster, union -> constrained Delaunay, lifted back onto the seed plane
    after_pos, after_mat, outline_after, tri_after = [], [], [], []
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        e1, e2 = R.plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        u = shapely.union_all(shapely.polygons(np.concatenate([xy, xy[:, :1]], axis=1)), grid_size=R.GRID)
        lift = lambda c: p0 + c[:, :1] * e1 + c[:, 1:2] * e2
        facing_up = None
        for poly in R.pieces(u):
            for ring in [poly.exterior, *poly.interiors]:
                c = lift(np.asarray(ring.coords))
                outline_after.extend(np.stack([c[:-1], c[1:]], axis=1))
            for g in shapely.constrained_delaunay_triangles(poly).geoms:
                if g.geom_type != "Polygon":
                    continue
                t3 = lift(np.asarray(g.exterior.coords)[:3])
                if np.cross(t3[1] - t3[0], t3[2] - t3[0]) @ n < 0:
                    t3 = t3[::-1]
                after_pos.append(t3)
                after_mat.append(int(m["fm"][members[0]]))
                tri_after.extend([[t3[0], t3[1]], [t3[1], t3[2]], [t3[2], t3[0]]])
    after_pos = np.array(after_pos).reshape(-1, 3, 3)
    dmg, model_px = guard(before, after_pos.reshape(-1, 3), np.arange(len(after_pos) * 3).reshape(-1, 3), Pc)

    colours = []
    mtl, cur = {}, None
    for line in (SNAP / "CKPT17-CLEAN.mtl").read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("newmtl "):
            cur = line[7:].strip()
        elif line.startswith("map_Kd ") and cur:
            mtl[cur] = line[7:].strip()
    for mat in m["mats"]:
        p = SNAP / mtl.get(mat, "")
        rgb = np.asarray(Image.open(p).convert("RGB"), float).reshape(-1, 3).mean(0) if p.is_file() else [200, 200, 200]
        colours.append({"name": mat, "color": [round(float(c) / 255, 4) for c in rgb]})

    ok_ids = np.nonzero(ok)[0]
    data = {
        "name": name[:-4],
        "stats": {"tris_total": int(len(fw)), "zero_area": int(deg.sum()), "before_tris": int(ok.sum()),
                  "hidden": int(hidden.sum()), "after_hidden_removed": int(visible.sum()),
                  "after_merged": int(len(after_pos)), "regions": len(planes),
                  "guard_views": len(VIEWS), "guard_model_px": model_px, "guard_damaged_px": dmg,
                  "guard_tol_in": TOL, "gridline_edges": len(grid)},
        "materials": colours,
        "before": {"pos": flat(tri[ok_ids]), "mat": m["fm"][ok_ids].tolist(), "hidden": hidden[ok_ids].astype(int).tolist()},
        "after": {"pos": flat(after_pos), "mat": after_mat},
        "edges": {"grid": flat(grid), "tri_before": flat(tri_before), "outline_before": flat(outline_before),
                  "outline_after": flat(outline_after), "tri_after": flat(tri_after)},
    }
    PREVIEW.mkdir(parents=True, exist_ok=True)
    (PREVIEW / f"{name[:-4]}.json").write_text(json.dumps(data, separators=(",", ":")))
    return data["stats"]


index = []
for name in FILES:
    s = export(name)
    index.append({"file": f"{name[:-4]}.json", "name": name[:-4]})
    print("==", name)
    for k, v in s.items():
        print(f"  {k}: {v}")
(PREVIEW / "index.json").write_text(json.dumps(index))
