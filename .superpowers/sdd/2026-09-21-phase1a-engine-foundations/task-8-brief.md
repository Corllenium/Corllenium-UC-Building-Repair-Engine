### Task 8: Meshbuf

**Files:** Create `engine\transport\meshbuf.py`, `engine\tests\test_meshbuf.py`

**Interfaces — Consumes:** `MeshData`, `Topology`.
**Produces:** `pack_meshbuf(mesh, topo, textures: dict[str, str | None]) -> bytes`,
`unpack_meshbuf(buf) -> tuple[dict, dict[str, np.ndarray]]`.

Layout: `b"UCMB"`, `u32` version 1, `u32` header length, UTF-8 JSON header padded with spaces to 4 bytes, then blocks.
Block offsets in the header are relative to the first byte after the padded header. Every block is padded to 4 bytes.
Blocks: `positions f32 (F*3,3)` recentred to bbox centre, non-indexed; `uvs f32 (F*3,2)`; `normals f32 (F*3,3)`
(source `vn` when present, else face normal, `(0,0,1)` for degenerates); `tri_material u16 (F,)` (65535 = none);
`tri_face_id u32 (F,)`; `tri_region i32 (F,)`; `edge_positions f32 (E*2,3)`; `edge_class u8 (E,)`.
Non-indexed geometry means three.js `faceIndex` k maps to `tri_face_id[k]`.

- [ ] **Step 1: failing test**

```python
import numpy as np

from engine.pipeline import analyse_topology
from engine.tests.fixtures.build import cube
from engine.transport.meshbuf import pack_meshbuf, unpack_meshbuf


def test_round_trip_and_alignment():
    m = cube(10.0)
    buf = pack_meshbuf(m, analyse_topology(m), {"m0": "tex/stone.png"})
    assert buf[:4] == b"UCMB"
    header, blocks = unpack_meshbuf(buf)
    assert header["version"] == 1 and header["counts"] == {"faces": 12, "edges": 18}
    assert header["origin_offset"] == [5.0, 5.0, 5.0] and header["unit_scale_m"] == 0.0254
    assert header["materials"] == [{"name": "m0", "texture": "tex/stone.png"}]
    assert all(b["offset"] % 4 == 0 for b in header["blocks"])
    assert blocks["positions"].shape == (36, 3) and np.abs(blocks["positions"]).max() == 5.0
    assert blocks["tri_face_id"].tolist() == list(range(12))
    assert blocks["edge_positions"].shape == (36, 3) and blocks["edge_class"].shape == (18,)
    n = blocks["normals"].reshape(12, 3, 3)[:, 0]
    assert np.allclose(np.linalg.norm(n, axis=1), 1.0)
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
import json
import struct

import numpy as np

MAGIC, VERSION = b"UCMB", 1
_DT = {"f32": np.float32, "u16": np.uint16, "u32": np.uint32, "i32": np.int32, "u8": np.uint8}


def _pad4(b: bytes, fill: bytes = b"\0") -> bytes:
    return b + fill * (-len(b) % 4)


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
        "materials": [{"name": n, "texture": textures.get(n)} for n in mesh.materials],
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
```

- [ ] **Step 3:** Run tests. Expected: `1 passed`. Then the whole suite: `.venv\Scripts\python.exe -m pytest -q`. Expected: `27 passed`.
- [ ] **Step 4:** Commit `feat(engine): meshbuf transport for the canvas`.

---

## Phase 1A done when

- `.venv\Scripts\python.exe -m pytest -q` shows `27 passed`, output pasted in the completion message.
- Real-data checks of Task 5 and Task 7 were run and their printed numbers recorded.
- `git grep -n "fastapi\|sqlalchemy" engine` returns nothing.

Next: Phase 1B plan (PostgreSQL in Docker, FastAPI, Vue canvas). Canvas requirement from the spike:
**double-sided rendering by default**, one-sided as a diagnostic toggle only.
