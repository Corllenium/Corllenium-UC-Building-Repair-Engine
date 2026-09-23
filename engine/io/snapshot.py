from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
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
    source_mtl_path: Path | None = None


def _parse_manifest(text: str) -> dict[str, ManifestRow]:
    rows = {}
    for line in text.splitlines()[1:]:
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2 and parts[1].replace(",", "").isdigit():
            rows[parts[0]] = ManifestRow(parts[0], int(parts[1].replace(",", "")), parts[2] if len(parts) > 2 else "")
    return rows


def read_manifest(path: Path) -> dict[str, ManifestRow]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return _parse_manifest(text)


def read_manifest_stable(path: Path, interval_s: float = 1.0, sleep=time.sleep) -> dict[str, ManifestRow]:
    """Read and parse a manifest that may be rewritten live, verifying it did not
    change between the stability check and the read. Only this function and
    `wait_stable`/`_copy_verified` may touch the live source tree."""
    path = Path(path)
    if not path.exists():
        raise SourceUnstable(f"{path.name}: missing, source rebuilding")
    key = _key(path)
    sleep(interval_s)
    try:
        data = path.read_bytes()
        changed = not path.exists() or _key(path) != key or len(data) == 0
    except OSError as exc:
        # Includes PermissionError from a Windows file lock and FileNotFoundError when the
        # file vanishes mid-read: either way the live source is not in a readable, stable state.
        raise SourceUnstable(f"{path.name}: {exc}") from exc
    if changed:
        raise SourceUnstable(f"{path.name}: changed during read, source rebuilding")
    return _parse_manifest(data.decode("utf-8", errors="replace"))


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


def _copy_verified(src: Path, dst: Path, interval_s: float, sleep) -> tuple[int, int]:
    """The only way any file under the live source tree is ever opened: verify it
    is stable, copy it, then re-stat the source to make sure it did not change
    out from under the copy. Used for the OBJ, the MTL and every texture."""
    key = wait_stable(src, interval_s, sleep)
    try:
        shutil.copyfile(src, dst)
        stable = src.exists() and _key(src) == key
    except OSError as exc:
        # Includes PermissionError from a Windows file lock and FileNotFoundError when the
        # file vanishes mid-copy: either way the live source is not in a stable, copyable state.
        raise SourceUnstable(f"{src.name}: {exc}") from exc
    if not stable:
        raise SourceUnstable(f"{src.name}: changed during copy")
    return key


def snapshot_object(src_obj, dst_root, expected_tris=None, interval_s=1.0, sleep=time.sleep) -> SnapshotResult:
    src_obj, dst_root = Path(src_obj), Path(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)
    # A unique per-call directory: two concurrent snapshots of the same object must never share
    # (and so never race on creating, or delete out from under each other) an incoming dir. Any
    # stale ".incoming-*" left by a crashed run under the old deterministic name is a different
    # path and is never touched here.
    tmp = Path(tempfile.mkdtemp(prefix=".incoming-", dir=dst_root))
    try:
        obj_copy = tmp / src_obj.name
        _copy_verified(src_obj, obj_copy, interval_s, sleep)
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
            try:
                tmp.rename(final)
            except OSError:
                # Another call finished first and already created `final`: discard our copy
                # (the `finally` below removes tmp) and load the winner's result instead.
                if not final.exists():
                    raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _load(final, digest)


def _copy_assets(src_obj, mesh, tmp, interval_s, sleep):
    if not mesh.mtllib:
        return
    mtl_src = (src_obj.parent / mesh.mtllib).resolve()
    source_mtl_copy = tmp / "source.mtl"
    _copy_verified(mtl_src, source_mtl_copy, interval_s, sleep)
    # parse_mtl runs on our own copy from here on — never on the live source path.
    wanted = write_mtl_subset(parse_mtl(source_mtl_copy), mesh.materials, tmp / "materials.mtl")
    rels = sorted(set(wanted.values()))
    by_basename: dict[str, str] = {}
    for rel in rels:
        base = PurePosixPath(rel.replace("\\", "/")).name
        if base in by_basename and by_basename[base] != rel:
            raise ValueError(
                f"texture basename collision under tex/: {by_basename[base]!r} and {rel!r} "
                f"both flatten to {base!r}")
        by_basename[base] = rel
    (tmp / "tex").mkdir()
    missing = []
    for rel in rels:
        tex_src = mtl_src.parent / rel
        tex_dst = tmp / "tex" / PurePosixPath(rel.replace("\\", "/")).name
        if tex_src.exists():
            _copy_verified(tex_src, tex_dst, interval_s, sleep)
        else:
            missing.append(rel)
    (tmp / "missing_textures.txt").write_text("\n".join(missing), encoding="utf-8")


def _load(final: Path, digest: str) -> SnapshotResult:
    # `final` is named by the OBJ bytes alone, so its one OBJ carries the name of whichever source
    # first produced those bytes -- not necessarily the caller's (two exports can be identical).
    obj_paths = sorted(final.glob("*.obj"))
    if len(obj_paths) != 1:
        raise ValueError(f"{final}: expected exactly one .obj file, found {len(obj_paths)}")
    obj_path = obj_paths[0]
    mtl_path = final / "materials.mtl"
    source_mtl_path = final / "source.mtl"
    res = SnapshotResult(final, obj_path, digest, obj_path.stat().st_size, read_obj(obj_path),
                         mtl_path if mtl_path.exists() else None,
                         source_mtl_path=source_mtl_path if source_mtl_path.exists() else None)
    if res.mtl_path:
        for name, mat in parse_mtl(mtl_path).items():
            if mat.map_kd and (final / mat.map_kd).exists():
                res.textures[name] = final / mat.map_kd
                res.flatness[name] = texture_flatness(final / mat.map_kd)
        miss = final / "missing_textures.txt"
        res.missing_textures = [m for m in miss.read_text(encoding="utf-8").splitlines() if m] if miss.exists() else []
    return res
