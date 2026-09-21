from __future__ import annotations

from pathlib import Path

import numpy as np

from engine.model import MeshData


class ObjFormatError(ValueError):
    pass


def _index(tok: str, count: int, line_no: int) -> int:
    i = int(tok)
    if i > 0:
        return i - 1
    if i < 0:
        return count + i
    raise ObjFormatError(f"line {line_no}: index 0 is invalid")


def read_obj(path: Path) -> MeshData:
    path = Path(path)
    v, vt, vn = [], [], []
    fv, fvt, fvn, fmat, fline = [], [], [], [], []
    materials: list[str] = []
    current, mtllib, name, decimals, sig = -1, None, None, 0, 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line[0] == "#":
                continue
            head, _, rest = line.partition(" ")
            rest = rest.strip()
            if head == "v":
                toks = rest.split()[:3]
                for t in toks:
                    if "e" in t or "E" in t:
                        raise ObjFormatError(
                            f"line {line_no}: exponent-form coordinate {t!r} is not supported "
                            "(breaks printed-decimal and significant-digit detection, and therefore the exact weld)")
                v.append([float(t) for t in toks])
                for t in toks:
                    if "." in t:
                        decimals = max(decimals, len(t.split(".")[1]))
                    sig = max(sig, len(t.lstrip("-").replace(".", "").lstrip("0")))
            elif head == "vt":
                vt.append([float(t) for t in rest.split()[:2]])
            elif head == "vn":
                vn.append([float(t) for t in rest.split()[:3]])
            elif head == "usemtl":
                if rest not in materials:
                    materials.append(rest)
                current = materials.index(rest)
            elif head == "mtllib":
                mtllib = rest
            elif head in ("o", "g") and name is None and rest:
                name = rest
            elif head == "f":
                toks = rest.split()
                if len(toks) != 3:
                    raise ObjFormatError(f"line {line_no}: face has {len(toks)} vertices, only triangles supported")
                parts = [t.split("/") for t in toks]
                fv.append([_index(p[0], len(v), line_no) for p in parts])
                fvt.append([_index(p[1], len(vt), line_no) if len(p) > 1 and p[1] else -1 for p in parts])
                fvn.append([_index(p[2], len(vn), line_no) if len(p) > 2 and p[2] else -1 for p in parts])
                fmat.append(current)
                fline.append(line_no)
    return MeshData(
        name=name or path.stem,
        positions=np.array(v, float).reshape(-1, 3), uvs=np.array(vt, float).reshape(-1, 2),
        normals=np.array(vn, float).reshape(-1, 3),
        face_v=np.array(fv, np.int64).reshape(-1, 3), face_vt=np.array(fvt, np.int64).reshape(-1, 3),
        face_vn=np.array(fvn, np.int64).reshape(-1, 3), face_material=np.array(fmat, np.int64),
        face_line=np.array(fline, np.int64), materials=materials, mtllib=mtllib,
        coord_decimals=decimals, sig_digits=sig)
