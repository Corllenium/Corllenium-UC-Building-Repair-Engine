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
