import json
import struct
from pathlib import Path

import numpy as np

MAGIC, VERSION = b"UCMB", 1
_DT = {"f32": np.float32, "u16": np.uint16, "u32": np.uint32, "i32": np.int32, "u8": np.uint8}


def _pad4(b: bytes, fill: bytes = b"\0") -> bytes:
    return b + fill * (-len(b) % 4)


def _texture_value(v: "str | Path | None") -> str | None:
    return None if v is None else Path(v).as_posix()


def pack_meshbuf(mesh, topo, textures) -> bytes:
    lo, hi = mesh.bbox()
    origin = (lo + hi) / 2
    tri = mesh.positions[mesh.face_v]
    cr = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(cr, axis=1)
    face_n = np.where(ln[:, None] > 0, cr / np.maximum(ln, 1e-300)[:, None], np.array([0.0, 0.0, 1.0]))
    normals = np.repeat(face_n[:, None, :], 3, axis=1)
    has_vn = (mesh.face_vn >= 0).all(axis=1)
    if has_vn.any():
        normals[has_vn] = mesh.normals[mesh.face_vn[has_vn]]
    uvs = np.zeros((mesh.n_faces, 3, 2))
    has_vt = (mesh.face_vt >= 0).all(axis=1)
    if has_vt.any():
        uvs[has_vt] = mesh.uvs[mesh.face_vt[has_vt]]
    arrays = [
        ("positions", "f32", (tri - origin).reshape(-1, 3)),
        ("uvs", "f32", uvs.reshape(-1, 2)),
        ("normals", "f32", normals.reshape(-1, 3)),
        ("tri_material", "u16", np.where(mesh.face_material >= 0, mesh.face_material, 65535)),
        ("tri_face_id", "u32", np.arange(mesh.n_faces)),
        ("tri_region", "i32", topo.face_region),
        ("edge_positions", "f32", (topo.positions_w[topo.table.edges] - origin).reshape(-1, 3)),
        ("edge_class", "u8", topo.edge_class),
    ]
    body, blocks = b"", []
    for name, dt, arr in arrays:
        raw = np.ascontiguousarray(arr, dtype=_DT[dt]).tobytes()
        blocks.append({"name": name, "dtype": dt, "shape": list(np.shape(arr)), "offset": len(body), "nbytes": len(raw)})
        body += _pad4(raw)
    header = {
        "version": VERSION, "name": mesh.name, "units": mesh.units, "unit_scale_m": 0.0254,
        "origin_offset": origin.tolist(), "bbox": {"min": lo.tolist(), "max": hi.tolist()},
        "materials": [{"name": n, "texture": _texture_value(textures.get(n))} for n in mesh.materials],
        "counts": {"faces": mesh.n_faces, "edges": int(len(topo.table.edges))}, "blocks": blocks,
    }
    hjson = _pad4(json.dumps(header, separators=(",", ":")).encode("utf-8"), b" ")
    return MAGIC + struct.pack("<II", VERSION, len(hjson)) + hjson + body


def unpack_meshbuf(buf: bytes):
    assert buf[:4] == MAGIC, "not a meshbuf"
    _version, hlen = struct.unpack("<II", buf[4:12])
    header = json.loads(buf[12:12 + hlen].decode("utf-8"))
    start = 12 + hlen
    blocks = {b["name"]: np.frombuffer(buf, dtype=_DT[b["dtype"]], count=int(np.prod(b["shape"])),
                                       offset=start + b["offset"]).reshape(b["shape"])
              for b in header["blocks"]}
    return header, blocks
