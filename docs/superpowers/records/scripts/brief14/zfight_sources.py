"""Brief 14 item 1: every z-fight source in a run's FINAL output, and where each comes from.

A SOURCE is two final faces whose outlines overlap by more than `MIN_AREA` sq in within one plane:
parallel (|n . m| > `PARALLEL_DOT`), every corner of each within the guard's depth tolerance of the
other's plane -- the band the guard itself calls one surface -- same or opposite winding, any
material. Per source:
- the shared area, winding, materials, the largest distance between the planes;
- the UV offset: the UV difference at the shared area's centroid (tiles, u and v) and the
  residual from the nearest single whole-tile shift over all six corners
  (`engine.fixes.overlap.uv_mapping_residual`; 0 = the same mapping modulo whole tiles);
- `zfight_px`: pixels of the 26 guard views, rendered as the final guard renders the shipped
  mesh, whose first hit is one of the two and whose ray meets the other within the depth
  tolerance -- the pixels where the two can trade places, i.e. flicker in Unity;
- `guard_tie_px`: the final guard's own `zfight_tie` pixels attributed to the pair (the guard
  is re-run from the pickle with `engine.guard.compare._classify` wrapped, and its totals are
  checked against the run's `guard_final`);
- the trace: each face's reference sources (input face or solidify's), their windings (flipped
  by the per-face rule or the sheet rule), whether the sources already overlap before the
  merge, and at the duplicate-layer pass (the stage reconstructed from the pickle and checked
  against the run's own removals): each source's region and the part of it its own region
  covers.

Usage (repo root as cwd and PYTHONPATH): zfight_sources.py <result.pkl> [out.json]"""
from __future__ import annotations

import json
import pickle
import sys

import numpy as np
import shapely

import engine.guard.compare as compare
from engine.fixes.merge import default_collinear_tol
from engine.fixes.orient import flip_faces
from engine.fixes.overlap import covered_fractions, plan_overlap_removal, uv_mapping_residual
from engine.fixes.pipeline import _render, guard_depth_tol
from engine.fixes.remove import remove_faces
from engine.guard.compare import PX_ZFIGHT_TIE, compare_views, face_planes
from engine.pipeline import analyse_topology, flat_material_indices
from engine.rays.caster import EmbreeCaster
from engine.topo.planes import plane_basis
from engine.topo.weld import weld_exact

MIN_AREA = 1.0
PARALLEL_DOT = 0.999


def overlap_stage(cap):
    """The mesh `remove_overlaps` was handed, rebuilt from the run's own per-face verdicts:
    `(mesh_flipped, topo2, survivors, flat, topo)` -- `survivors[k]` the reference id of its face
    `k`. Checked: the duplicate-layer plan it gives removes exactly the run's `removed_overlap`."""
    r, profile = cap["result"], cap["profile"]
    ref = r.reference_mesh
    flat = flat_material_indices(cap["input"], cap["flatness"], profile.flat_texture_std)
    angles = {"coplanar_angle": profile.coplanar_angle, "soft_angle": profile.soft_angle}
    topo = analyse_topology(ref, flat, **angles)
    gone = (r.removed_hidden | r.removed_slit | (~topo.ok & ~r.restored_degenerate)
            | r.removed_fragments)
    survivors = np.nonzero(~gone)[0]
    mesh_fragments, _ = remove_faces(ref, gone)
    mesh_flipped = flip_faces(mesh_fragments, r.flipped[survivors])
    topo2 = analyse_topology(mesh_flipped, flat, **angles)
    plan = plan_overlap_removal(mesh_flipped, topo2)
    assert sorted(survivors[plan.remove].tolist()) == np.nonzero(r.removed_overlap)[0].tolist(), \
        "the rebuilt stage does not reproduce the run's duplicate-layer removals"
    return mesh_flipped, topo2, survivors, flat, topo


def find_sources(positions, face_v, tol):
    tri = np.asarray(positions, dtype=np.float64)[np.asarray(face_v, dtype=np.int64)]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(cross, axis=1)
    ok = length > 1e-12
    normal = np.zeros_like(cross)
    normal[ok] = cross[ok] / length[ok, None]
    lo, hi = tri.min(axis=1) - tol, tri.max(axis=1) + tol
    ids = np.nonzero(ok)[0]
    out = []
    for s in range(0, len(ids), 400):
        rows = ids[s:s + 400]
        near = ((lo[rows, None] <= hi[None, ids]) & (hi[rows, None] >= lo[None, ids])).all(axis=2)
        near &= np.abs(normal[rows] @ normal[ids].T) > PARALLEL_DOT
        near &= ids[None, :] > rows[:, None]
        for a, b in zip(*np.nonzero(near)):
            i, j = int(rows[a]), int(ids[b])
            sep = max(np.abs((tri[j] - tri[i][0]) @ normal[i]).max(),
                      np.abs((tri[i] - tri[j][0]) @ normal[j]).max())
            if sep > tol:
                continue
            e1, e2 = plane_basis(normal[i])
            basis = np.stack([e1, e2], axis=1)
            pi = shapely.Polygon((tri[i] - tri[i][0]) @ basis)
            pj = shapely.Polygon((tri[j] - tri[i][0]) @ basis)
            shared = pi.intersection(pj)
            if shared.area <= MIN_AREA:
                continue
            c = np.asarray(shared.centroid.coords[0])
            out.append({"faces": [i, j], "area": round(float(shared.area), 3),
                        "cover": [round(shared.area / pi.area, 3), round(shared.area / pj.area, 3)],
                        "opposite": bool(normal[i] @ normal[j] < 0.0), "separation": round(float(sep), 4),
                        "centroid": np.round(tri[i][0] + basis @ c, 2).tolist(),
                        "normal": np.round(normal[i], 4).tolist(),
                        "_basis": basis, "_c2": c})
    return out


def uv_at(mesh, tri, f, basis, origin, point2):
    if not (mesh.face_vt[f] >= 0).all():
        return None
    xy = (tri[f] - origin) @ basis
    a = np.column_stack([xy, np.ones(3)])
    m = np.linalg.solve(a, np.asarray(mesh.uvs, dtype=np.float64)[mesh.face_vt[f]])
    return np.array([point2[0], point2[1], 1.0]) @ m


def main(path, out_json=None):
    with open(path, "rb") as fh:
        cap = pickle.load(fh)
    r, profile = cap["result"], cap["profile"]
    ref, final = r.reference_mesh, r.mesh
    mesh_flipped, topo2, survivors, flat, topo = overlap_stage(cap)
    depth_tol = guard_depth_tol(topo.quanta, profile)
    centre = (topo.positions_w.min(axis=0) + topo.positions_w.max(axis=0)) / 2.0
    positions_c = topo.positions_w - centre
    _, remap = weld_exact(ref.positions, ref.coord_decimals)
    face_w_final = remap[final.face_v]
    tri_final = positions_c[face_w_final]

    sources = find_sources(positions_c, face_w_final, depth_tol)
    in_pair = {}
    for k, s in enumerate(sources):
        for f in s["faces"]:
            in_pair.setdefault(f, []).append(k)

    # ---- the final guard, re-run, its tie pixels kept -----------------------------------
    captured = []
    real = compare._classify

    def spy(before_depth, before_tri, after_depth, after_tri, *args, **kwargs):
        codes, base = real(before_depth, before_tri, after_depth, after_tri, *args, **kwargs)
        tie = codes == PX_ZFIGHT_TIE
        captured.append((np.asarray(before_tri)[tie], np.asarray(after_tri)[tie]))
        return codes, base

    before = _render(positions_c, topo.face_w, profile.guard_size)
    after = _render(positions_c, face_w_final, profile.guard_size)
    compare._classify = spy
    try:
        guard = compare_views(
            before, after, ref.face_material, final.face_material, flat, depth_tol,
            strict=r.strict_final, plane_before=face_planes(positions_c, topo.face_w),
            plane_after=face_planes(positions_c, face_w_final),
            edge_flicker_cap=(profile.edge_flicker_cap_final
                              if not r.merge_report.get("rolled_back") else profile.edge_flicker_cap_final),
            crack_closed_cap=profile.crack_closed_cap,
            geometry_before=(positions_c, topo.face_w), geometry_after=(positions_c, face_w_final),
            removed_before=r.removed_fragments,
            border_shift_tol=min(default_collinear_tol(topo.quanta), profile.depth_tol_max),
            exposed_after=r.exposed_final, fragment_removed_cap=profile.fragment_removed_cap)
    finally:
        compare._classify = real
    assert guard.totals == r.guard_final.totals, (guard.totals, r.guard_final.totals)
    ref_to_final = {}
    for k, s in enumerate(r.source_faces):
        for g in np.asarray(s).reshape(-1).tolist():
            ref_to_final.setdefault(g, set()).add(k)
    tie_px = [0] * len(sources)
    unattributed = []
    for b_tri, a_tri in captured[-len(after):] if captured else []:
        for g, f in zip(b_tri.tolist(), a_tri.tolist()):
            hit = [k for k in in_pair.get(f, [])
                   if set(sources[k]["faces"]) & ref_to_final.get(g, set())]
            if hit:
                tie_px[hit[0]] += 1
            else:
                unattributed.append({"after_face": f, "before_ref_face": g})

    # ---- z-fight pixels of each source in the shipped mesh's own renders -------------------
    caster = EmbreeCaster(positions_c, face_w_final)
    zf_px = [0] * len(sources)
    for _view, buf in after:
        hit = buf.tri >= 0
        mask = hit & np.isin(buf.tri, list(in_pair))
        if not mask.any():
            continue
        rows, cols = np.nonzero(mask)
        origins = buf.xs[cols][:, None] * buf.right + buf.ys[rows][:, None] * buf.up + buf.standoff
        ray, tri, t = caster.all_hits(origins, np.tile(buf.direction, (len(origins), 1)))
        first_f = buf.tri[rows, cols]
        first_t = buf.depth[rows, cols]
        near = np.abs(t - first_t[ray]) <= depth_tol
        met = {}
        for q, f in zip(ray[near].tolist(), tri[near].tolist()):
            met.setdefault(q, set()).add(f)
        for q in range(len(rows)):
            f = int(first_f[q])
            for k in in_pair[f]:
                other = [g for g in sources[k]["faces"] if g != f][0]
                if other in met.get(q, ()):
                    zf_px[k] += 1

    # ---- the trace -----------------------------------------------------------------------
    n_kept = int((~r.replaced_input).sum())
    input_of = np.nonzero(~r.replaced_input)[0]
    local_of = {int(g): k for k, g in enumerate(survivors.tolist())}
    needed = {local_of[g] for s in sources for f in s["faces"]
              for g in np.asarray(r.source_faces[f]).reshape(-1).tolist() if g in local_of}
    covered = covered_fractions(topo2, sorted(needed))
    ref_tri = positions_c[topo.face_w]
    report = []
    for k, s in enumerate(sources):
        i, j = s["faces"]
        origin = tri_final[i][0]
        ui = uv_at(final, tri_final, i, s["_basis"], origin, s["_c2"])
        uj = uv_at(final, tri_final, j, s["_basis"], origin, s["_c2"])
        entry = {
            **{key: v for key, v in s.items() if not key.startswith("_")},
            "centroid": (np.asarray(s["centroid"]) + centre).round(2).tolist(),
            "materials": [final.materials[int(final.face_material[f])] for f in (i, j)],
            "uv_offset": None if ui is None or uj is None else np.round(ui - uj, 3).tolist(),
            "uv_residual": round(uv_mapping_residual(final, tri_final, i, j), 4),
            "zfight_px": zf_px[k], "guard_tie_px": tie_px[k],
            "merged_region": [int(r.face_region_final[f]) for f in (i, j)],
            "sources": [],
        }
        for f in (i, j):
            src = []
            for g in np.asarray(r.source_faces[f]).reshape(-1).tolist():
                lk = local_of.get(g)
                src.append({
                    "ref": g, "input": int(input_of[g]) if g < n_kept else None,
                    "flipped": bool(r.flipped[g]), "sheet_flipped": bool(r.sheet_flipped[g]),
                    "thin": bool(r.thin_sheets[g]),
                    "region_at_overlap_pass": None if lk is None else int(topo2.face_region[lk]),
                    "own_region_covers": None if lk is None else round(covered.get(lk, 0.0), 3)})
            entry["sources"].append(src)
        # do the two faces' sources already overlap in the reference, before the merge?
        e1, e2 = plane_basis(np.asarray(s["normal"]))
        basis = np.stack([e1, e2], axis=1)
        polys = [shapely.union_all([shapely.Polygon((ref_tri[g] - origin) @ basis)
                                    for g in np.asarray(r.source_faces[f]).reshape(-1).tolist()])
                 for f in (i, j)]
        entry["sources_overlap_before_merge"] = round(float(polys[0].intersection(polys[1]).area), 3)
        report.append(entry)

    report.sort(key=lambda e: -e["area"])
    print(f"{final.name}: {len(report)} z-fight sources (> {MIN_AREA} sq in, planes within "
          f"{depth_tol:.3f} in); guard_final zfight_tie {r.guard_final.totals['zfight_tie']}, "
          f"attributed {sum(tie_px)}, unattributed {unattributed}")
    for e in report:
        print(f"  faces {e['faces']} {'OPPOSITE' if e['opposite'] else 'same-wound'} "
              f"{e['area']} sq in (cover {e['cover']}), sep {e['separation']} in, at {e['centroid']}, "
              f"n {e['normal']}; {e['materials']}; uv offset {e['uv_offset']} residual "
              f"{e['uv_residual']}; zfight_px {e['zfight_px']}, guard ties {e['guard_tie_px']}; "
              f"merged {e['merged_region']}; sources overlap before merge "
              f"{e['sources_overlap_before_merge']} sq in")
        for side, src in zip("ij", e["sources"]):
            print(f"      {side}: " + "; ".join(
                f"ref {s['ref']} (input {s['input']}{', flipped' if s['flipped'] else ''}"
                f"{', sheet' if s['sheet_flipped'] else ''}{', thin' if s['thin'] else ''}, "
                f"region {s['region_at_overlap_pass']}, own region covers {s['own_region_covers']})"
                for s in src[:6]) + (f" ... {len(src)} faces" if len(src) > 6 else ""))
    if out_json:
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump({"name": final.name, "depth_tol": depth_tol, "sources": report,
                       "guard_zfight_tie": r.guard_final.totals["zfight_tie"],
                       "unattributed_ties": unattributed}, fh, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
