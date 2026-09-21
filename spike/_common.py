"""Throwaway spike helpers. NOT the engine. Nothing here is imported by engine/ or api/."""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "spike"
SNAP = OUT / "snapshot"
RESULTS = OUT / "results.json"
SOURCE = Path(r"D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17")
FILES = [
    "CHTM_SIDE_WALK_2nd_floor.obj",
    "CHTM_2nd_to_3rd_building_sidewalk_outside.obj",
]


def save(section, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    data[section] = payload
    RESULTS.write_text(json.dumps(data, indent=2))


def load_obj(path):
    v, vt, vn, fv, fvt, fvn, fm = [], [], [], [], [], [], []
    mats, cur, dec = [], -1, 0
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("v "):
            p = line.split()[1:4]
            v.append([float(x) for x in p])
            for x in p:
                if "." in x:
                    dec = max(dec, len(x.split(".")[1]))
        elif line.startswith("vt "):
            vt.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("vn "):
            vn.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("usemtl "):
            name = line[7:].strip()
            if name not in mats:
                mats.append(name)
            cur = mats.index(name)
        elif line.startswith("f "):
            toks = line.split()[1:]
            assert len(toks) == 3, f"non-triangle face: {line}"
            a = [t.split("/") for t in toks]
            fv.append([int(x[0]) - 1 for x in a])
            fvt.append([int(x[1]) - 1 if len(x) > 1 and x[1] else -1 for x in a])
            fvn.append([int(x[2]) - 1 if len(x) > 2 and x[2] else -1 for x in a])
            fm.append(cur)
    return dict(
        v=np.array(v, float).reshape(-1, 3),
        vt=np.array(vt, float).reshape(-1, 2),
        vn=np.array(vn, float).reshape(-1, 3),
        fv=np.array(fv, np.int64).reshape(-1, 3),
        fvt=np.array(fvt, np.int64).reshape(-1, 3),
        fvn=np.array(fvn, np.int64).reshape(-1, 3),
        fm=np.array(fm, np.int64),
        mats=mats,
        decimals=dec,
    )


def weld(m):
    """Exact weld on printed precision. Returns (unique positions, faces as welded ids)."""
    rounded = np.round(m["v"], m["decimals"]) + 0.0  # + 0.0 turns -0.0 into 0.0
    uniq, inv = np.unique(rounded, axis=0, return_inverse=True)
    return uniq, inv.reshape(-1)[m["fv"]]


def tri_geometry(P, fw):
    """area, unit normal (zeros when degenerate), longest edge, degenerate mask."""
    p = P[fw]
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    norm = np.linalg.norm(cr, axis=1)
    area = 0.5 * norm
    longest = np.linalg.norm(p - np.roll(p, -1, axis=1), axis=2).max(axis=1)
    degenerate = area <= 1e-7 * np.maximum(longest, 1e-300) ** 2
    n = np.zeros_like(cr)
    ok = ~degenerate
    n[ok] = cr[ok] / norm[ok, None]
    return area, n, longest, degenerate
