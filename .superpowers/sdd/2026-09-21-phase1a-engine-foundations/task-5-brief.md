### Task 5: Snapshot importer

**Files:** Create `engine\io\snapshot.py`, `engine\tests\test_snapshot.py`

**Interfaces — Consumes:** `read_obj`, `parse_mtl`, `write_mtl_subset`, `texture_flatness`.
**Produces:** `ManifestRow(file, tris, group)`, `read_manifest(path) -> dict[str, ManifestRow]`,
`SourceUnstable(Exception)`, `ManifestMismatch(Exception)`, `sha256_file(path) -> str`,
`wait_stable(path, interval_s=1.0, sleep=time.sleep) -> tuple[int, int]`,
`snapshot_object(src_obj, dst_root, expected_tris=None, interval_s=1.0, sleep=time.sleep) -> SnapshotResult`,
`SnapshotResult(dir, obj_path, sha256, size_bytes, mesh, mtl_path, textures: dict[str, Path], flatness: dict[str, float], missing_textures: list[str])`.

- [ ] **Step 1: failing test**

```python
import numpy as np
import pytest
from PIL import Image

from engine.io.snapshot import ManifestMismatch, SourceUnstable, read_manifest, snapshot_object, wait_stable

MANIFEST = """file                                                              tris   sketchup group
Main_Infrustructure_Building.obj                               142,248   Main_Infrustructure_Building
CHTM_SIDE_WALK_2nd_floor.obj                                     4,692   CHTM_SIDE_WALK_2nd_floor
"""
OBJ = "mtllib ../lib.mtl\no walk\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl stone\nf 1/1 2/2 3/3\n"


def make_source(tmp_path):
    (tmp_path / "split").mkdir()
    (tmp_path / "SRC-TEX").mkdir()
    (tmp_path / "split" / "walk.obj").write_text(OBJ)
    (tmp_path / "lib.mtl").write_text("newmtl stone\nmap_Kd SRC-TEX/stone.png\n\nnewmtl other\nmap_Kd SRC-TEX/gone.png\n")
    Image.fromarray(np.full((4, 4, 3), 220, np.uint8)).save(tmp_path / "SRC-TEX" / "stone.png")
    return tmp_path / "split" / "walk.obj"


def test_manifest_parses_thousands_commas(tmp_path):
    p = tmp_path / "_MANIFEST.txt"
    p.write_text(MANIFEST)
    rows = read_manifest(p)
    assert rows["CHTM_SIDE_WALK_2nd_floor.obj"].tris == 4692
    assert rows["Main_Infrustructure_Building.obj"].group == "Main_Infrustructure_Building"


def test_snapshot_copies_hashes_and_subsets(tmp_path):
    src = make_source(tmp_path / "src")
    res = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert res.obj_path.read_bytes() == src.read_bytes() and len(res.sha256) == 64
    assert res.dir.name == res.sha256[:12] and res.mesh.n_faces == 1
    assert "other" not in res.mtl_path.read_text() and res.textures["stone"].exists()
    assert res.flatness["stone"] == 0.0 and res.missing_textures == []
    again = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert again.dir == res.dir


def test_source_changing_during_read_is_rejected(tmp_path):
    src = make_source(tmp_path / "src")
    with pytest.raises(SourceUnstable):
        wait_stable(src, interval_s=0, sleep=lambda s: src.write_text(OBJ + "v 9 9 9\n"))


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(SourceUnstable):
        wait_stable(tmp_path / "nope.obj", interval_s=0, sleep=lambda s: None)


def test_manifest_mismatch(tmp_path):
    src = make_source(tmp_path / "src")
    with pytest.raises(ManifestMismatch):
        snapshot_object(src, tmp_path / "snap", expected_tris=99, interval_s=0, sleep=lambda s: None)
```

Run. Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 2: implementation**

```python
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from engine.io.mtl import parse_mtl, texture_flatness, write_mtl_subset
from engine.io.obj_reader import ObjFormatError, read_obj
from engine.model import MeshData


class SourceUnstable(Exception):
    pass


class ManifestMismatch(Exception):
    pass


@dataclass
class ManifestRow:
    file: str
    tris: int
    group: str


@dataclass
class SnapshotResult:
    dir: Path
    obj_path: Path
    sha256: str
    size_bytes: int
    mesh: MeshData
    mtl_path: Path | None
    textures: dict[str, Path] = field(default_factory=dict)
    flatness: dict[str, float] = field(default_factory=dict)
    missing_textures: list[str] = field(default_factory=list)


def read_manifest(path: Path) -> dict[str, ManifestRow]:
    rows = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2 and parts[1].replace(",", "").isdigit():
            rows[parts[0]] = ManifestRow(parts[0], int(parts[1].replace(",", "")), parts[2] if len(parts) > 2 else "")
    return rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _key(path: Path) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


def wait_stable(path: Path, interval_s: float = 1.0, sleep=time.sleep) -> tuple[int, int]:
    path = Path(path)
    if not path.exists():
        raise SourceUnstable(f"{path.name}: missing, source rebuilding")
    a = _key(path)
    sleep(interval_s)
    if not path.exists() or _key(path) != a or a[0] == 0:
        raise SourceUnstable(f"{path.name}: changed during read, source rebuilding")
    return a


def snapshot_object(src_obj, dst_root, expected_tris=None, interval_s=1.0, sleep=time.sleep) -> SnapshotResult:
    src_obj, dst_root = Path(src_obj), Path(dst_root)
    key = wait_stable(src_obj, interval_s, sleep)
    dst_root.mkdir(parents=True, exist_ok=True)
    tmp = dst_root / f".incoming-{src_obj.stem}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        obj_copy = tmp / src_obj.name
        shutil.copyfile(src_obj, obj_copy)
        if not src_obj.exists() or _key(src_obj) != key:
            raise SourceUnstable(f"{src_obj.name}: changed during copy")
        digest = sha256_file(obj_copy)
        try:
            mesh = read_obj(obj_copy)
        except (ObjFormatError, ValueError) as exc:
            raise SourceUnstable(f"{src_obj.name}: copy does not parse ({exc})") from exc
        if expected_tris is not None and mesh.n_faces != expected_tris:
            raise ManifestMismatch(f"{src_obj.name}: {mesh.n_faces} tris, manifest says {expected_tris}")
        final = dst_root / digest[:12]
        if not final.exists():
            _copy_assets(src_obj, mesh, tmp, interval_s, sleep)
            tmp.rename(final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _load(final, src_obj.name, digest)


def _copy_assets(src_obj, mesh, tmp, interval_s, sleep):
    if not mesh.mtllib:
        return
    mtl_src = (src_obj.parent / mesh.mtllib).resolve()
    wait_stable(mtl_src, interval_s, sleep)
    wanted = write_mtl_subset(parse_mtl(mtl_src), mesh.materials, tmp / "materials.mtl")
    (tmp / "tex").mkdir()
    missing = []
    for rel in sorted(set(wanted.values())):
        tex_src = mtl_src.parent / rel
        if tex_src.exists():
            shutil.copyfile(tex_src, tmp / "tex" / PurePosixPath(rel.replace("\\", "/")).name)
        else:
            missing.append(rel)
    (tmp / "missing_textures.txt").write_text("\n".join(missing), encoding="utf-8")


def _load(final: Path, obj_name: str, digest: str) -> SnapshotResult:
    obj_path = final / obj_name
    mtl_path = final / "materials.mtl"
    res = SnapshotResult(final, obj_path, digest, obj_path.stat().st_size, read_obj(obj_path),
                         mtl_path if mtl_path.exists() else None)
    if res.mtl_path:
        for name, mat in parse_mtl(mtl_path).items():
            if mat.map_kd and (final / mat.map_kd).exists():
                res.textures[name] = final / mat.map_kd
                res.flatness[name] = texture_flatness(final / mat.map_kd)
        miss = final / "missing_textures.txt"
        res.missing_textures = [m for m in miss.read_text(encoding="utf-8").splitlines() if m] if miss.exists() else []
    return res
```

- [ ] **Step 3:** Run tests. Expected: `5 passed`.
- [ ] **Step 4: real-data check** (not a unit test, source is live):

```
.venv\Scripts\python.exe -c "from pathlib import Path; from engine.io.snapshot import *; s=Path(r'D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\split'); m=read_manifest(s/'_MANIFEST.txt'); r=snapshot_object(s/'CHTM_SIDE_WALK_2nd_floor.obj', Path('data/snapshots'), m['CHTM_SIDE_WALK_2nd_floor.obj'].tris); print(r.sha256, r.mesh.n_faces, r.flatness, r.missing_textures)"
```

Expected: 64-hex sha, `4692`, flatness about `3.04`, `[]`. `SourceUnstable` means the other pipeline is mid-rebuild: wait and retry, do not work around it.

- [ ] **Step 5:** Commit `feat(engine): snapshot importer with stability and manifest checks`.

---

