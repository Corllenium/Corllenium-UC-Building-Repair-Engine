"""Diagnostic only (not shipped): where are the edge-flicker pixels that fail file A's merge guard?

Wraps `engine.fixes.pipeline.merge_regions` and `engine.fixes.pipeline.compare_views` for one run of
`fix_object` and records, for every pipeline-level guard call with a flicker cap above zero, the
per-pixel codes of every view (via `engine.guard.compare._classify`). Nothing in the engine changes.
"""
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

import engine.fixes.pipeline as P
import engine.guard.compare as C
from engine.cli import _load_snapshot

snap = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

captured = {"merge": None, "merge_args": None, "calls": []}

_orig_merge = P.merge_regions


def merge_wrap(*a, **k):
    r = _orig_merge(*a, **k)
    captured["merge"] = r
    captured["merge_args"] = a
    return r


P.merge_regions = merge_wrap

_orig_cv = P.compare_views
_orig_classify = C._classify


def cv_wrap(before, after, *a, **k):
    cap = k.get("edge_flicker_cap", 0.0)
    if cap <= 0.0:
        return _orig_cv(before, after, *a, **k)
    rec = {"cap": cap, "codes": [], "base": []}

    def classify_wrap(*ca, **ck):
        codes, base = _orig_classify(*ca, **ck)
        rec["codes"].append(codes.copy())
        rec["base"].append(base.copy())
        return codes, base

    C._classify = classify_wrap
    try:
        res = _orig_cv(before, after, *a, **k)
    finally:
        C._classify = _orig_classify
    rec["result"] = res
    rec["before"] = before
    rec["after"] = after
    rec["geometry_before"] = k.get("geometry_before")
    rec["geometry_after"] = k.get("geometry_after")
    captured["calls"].append(rec)
    return res


P.compare_views = cv_wrap

t0 = time.time()
obj_path, mesh, flatness, _ = _load_snapshot(snap)
result = P.fix_object(mesh, flatness, P.FixProfile())
print(f"fix_object {time.time() - t0:.1f}s passed={result.passed} tris={result.mesh.n_faces}")
print("guard calls with cap>0:", len(captured["calls"]))

rec = captured["calls"][0]                 # guard_merge_attempt
mr = captured["merge"]
print("merge attempt passed:", rec["result"].passed, "| merged tris", mr.mesh.n_faces)

rows = []
for vi, (codes, base) in enumerate(zip(rec["codes"], rec["base"])):
    fl = codes == C.PX_EDGE_FLICKER
    if not fl.any():
        continue
    (view, b), (_, a) = rec["before"][vi], rec["after"][vi]
    origins = b.origins
    for r, c in zip(*np.nonzero(fl)):
        bt, at = int(b.tri[r, c]), int(a.tri[r, c])
        bd, ad = float(b.depth[r, c]), float(a.depth[r, c])
        o = origins[r, c]
        pb = (o + bd * b.direction).tolist() if bt >= 0 else None
        pa = (o + ad * a.direction).tolist() if at >= 0 else None
        region = int(mr.face_region[at]) if at >= 0 else None
        rows.append(dict(view=vi, dir=list(view), r=int(r), c=int(c), base=int(base[r, c]),
                         before_tri=bt, after_tri=at, before_depth=bd, after_depth=ad,
                         after_region=region, p_before=pb, p_after=pa))

print(f"{len(rows)} flicker pixels over {len({x['view'] for x in rows})} views")
for x in rows:
    if x["view"] == 0:
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()
                          if k not in ("p_before", "p_after", "dir")}),
              "pB", None if x["p_before"] is None else [round(v, 2) for v in x["p_before"]],
              "pA", None if x["p_after"] is None else [round(v, 2) for v in x["p_after"]])

(out / "flicker_rows.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
# the pieces a follow-up needs, without the heavy renders
keep = {
    "rows": rows,
    "merged_positions": mr.mesh.positions, "merged_face_v": mr.mesh.face_v,
    "merged_face_region": mr.face_region, "rings": mr.rings,
    "source_faces": mr.source_faces,
    "geometry_before": rec["geometry_before"], "geometry_after": rec["geometry_after"],
    "view0_before_tri": rec["before"][0][1].tri, "view0_after_tri": rec["after"][0][1].tri,
    "view0_codes": rec["codes"][0], "view0_base": rec["base"][0],
}
with open(out / "flicker_capture.pkl", "wb") as f:
    pickle.dump(keep, f)
print("wrote", out)
