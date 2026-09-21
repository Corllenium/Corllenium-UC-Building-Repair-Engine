"""Are coplanar same-facing faces stacked on top of each other? Layering factor per plane.

layering = sum of triangle areas / area of their union.  1.0 = single layer, 2.0 = every spot covered twice.
"""
import importlib.util
from pathlib import Path

import numpy as np
import shapely

from _common import FILES, SNAP, load_obj, save, tri_geometry, weld

spec = importlib.util.spec_from_file_location("r", Path(__file__).with_name("_region.py"))
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def analyse(name):
    path = SNAP / name
    m = load_obj(path)
    P, fw = weld(m)
    area, normals, _, degenerate = tri_geometry(P, fw)
    ok = ~degenerate
    _, quanta = R.axis_quanta(path, P)
    tri = P[fw]
    uv_all = m["vt"][m["fvt"]]
    plabel, planes = R.cluster_planes(tri, normals, area, m["fm"], ok, quanta)

    rows = []
    for pi, (n, p0, _tol) in enumerate(planes):
        members = np.nonzero(plabel == pi)[0]
        e1, e2 = R.plane_basis(n)
        xy = np.stack([(tri[members] - p0) @ e1, (tri[members] - p0) @ e2], axis=2)
        polys = shapely.polygons(np.concatenate([xy, xy[:, :1]], axis=1))
        s = float(shapely.area(polys).sum())
        u = float(shapely.union_all(polys, grid_size=R.GRID).area)
        ulabel, fits = R.cluster_uv(xy, uv_all[members], area[members])
        rows.append({
            "normal": np.round(n, 3).tolist(),
            "tris": int(len(members)),
            "sum_area_in2": round(s, 1),
            "union_area_in2": round(u, 1),
            "layering": round(s / max(u, 1e-9), 3),
            "uv_classes": len(fits),
        })
    rows.sort(key=lambda r: -r["sum_area_in2"])
    tot_s = sum(r["sum_area_in2"] for r in rows)
    tot_u = sum(r["union_area_in2"] for r in rows)
    layered = [r for r in rows if r["layering"] > 1.01]
    return {
        "planes": len(rows),
        "overall_layering": round(tot_s / tot_u, 3),
        "planes_with_layering_over_1.01": len(layered),
        "tris_in_layered_planes": sum(r["tris"] for r in layered),
        "area_share_of_layered_planes_pct": round(100 * sum(r["sum_area_in2"] for r in layered) / tot_s, 1),
        "planes_with_1_tri": sum(1 for r in rows if r["tris"] == 1),
        "planes_with_2_tris": sum(1 for r in rows if r["tris"] == 2),
        "median_tris_per_plane": float(np.median([r["tris"] for r in rows])),
        "top10_planes_by_area": rows[:10],
    }


out = {name: analyse(name) for name in FILES}
save("layers", out)
for name, r in out.items():
    print("==", name)
    for k, v in r.items():
        if k == "top10_planes_by_area":
            print("  top10_planes_by_area:")
            for row in v:
                print("    ", row)
        else:
            print(f"  {k}: {v}")
