"""Freeze the CHECKPOINT-17 export (spec 2026-10-03, P0 task 7).

Every later step reads these frozen copies, never the live export folder, which has been rewritten
mid-read before. The live tree is opened only through `engine.io.snapshot` (a test audits this):
- every split OBJ becomes a content-addressed snapshot (checked against `_MANIFEST.txt`);
- `CKPT17-CLEAN.obj`, its MTL and every texture that MTL names are copied, stable-checked, into
  `<out>/source/<sha12 of the OBJ>-<asset digest>/`; textures keep their MTL-relative paths;
- the owner's CHECKPOINT-17 backup is only hashed in place.
The result is `<out>/source.json`, with absolute paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from engine.io.mtl import parse_mtl
from engine.io.snapshot import (SourceUnstable, copy_if_present, copy_verified, read_manifest_stable,
                                sha256_file, snapshot_object)

CLEAN_OBJ = "CKPT17-CLEAN.obj"


@dataclass
class SourceFreeze:
    json_path: Path
    clean_obj: Path
    clean_mtl: Path
    snapshots: list[dict] = field(default_factory=list)   # {"file","group","tris","dir","sha256"}


@dataclass
class _Clean:
    obj: Path
    mtl: Path
    textures: dict[str, str]        # MTL-relative posix path -> sha256
    missing: list[str]
    rejected: list[str]


def _texture_rel(map_kd: str) -> PurePosixPath | None:
    """The MTL-relative path of a texture, or None when it would leave the export folder."""
    rel = PurePosixPath(map_kd.replace("\\", "/"))
    # any ":" means a drive (C:foo.png is drive-relative on Windows), never a file under the export
    if rel.is_absolute() or ".." in rel.parts or any(":" in part for part in rel.parts):
        return None
    return rel


def _freeze_clean(export_dir: Path, out_root: Path, interval_s: float, sleep) -> _Clean:
    """Copy CKPT17-CLEAN.obj, its MTL and the MTL's textures into source/<sha12>-<assets8>/."""
    src_root = out_root / "source"
    src_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".incoming-", dir=src_root))
    try:
        obj_copy = tmp / CLEAN_OBJ
        copy_verified(export_dir / CLEAN_OBJ, obj_copy, interval_s, sleep)
        mtl_name = Path(CLEAN_OBJ).with_suffix(".mtl").name
        mtl_copy = tmp / mtl_name
        copy_verified(export_dir / mtl_name, mtl_copy, interval_s, sleep)
        textures: dict[str, str] = {}
        missing: list[str] = []
        rejected: list[str] = []
        for mat in parse_mtl(mtl_copy).values():            # our own copy, never the live MTL
            if not mat.map_kd:
                continue
            rel = _texture_rel(mat.map_kd)
            if rel is None:
                rejected.append(mat.map_kd.replace("\\", "/"))
                continue
            key = rel.as_posix()
            if key in textures or key in missing:
                continue
            if copy_if_present(export_dir / key, tmp / key, interval_s, sleep):
                textures[key] = sha256_file(tmp / key)
            else:
                missing.append(key)
        assets = hashlib.sha256()
        assets.update(f"{mtl_name}\0{sha256_file(mtl_copy)}\n".encode("utf-8"))
        for key in sorted(textures):
            assets.update(f"{key}\0{textures[key]}\n".encode("utf-8"))
        final = src_root / f"{sha256_file(obj_copy)[:12]}-{assets.hexdigest()[:8]}"
        if not final.exists():
            try:
                tmp.rename(final)
            except OSError:
                if not final.exists():           # not a lost race with an identical freeze
                    raise
        return _Clean(final / CLEAN_OBJ, final / mtl_name, textures, sorted(set(missing)),
                      sorted(set(rejected)))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _hash_backup(backup_dir: Path) -> dict:
    files = sorted(backup_dir.glob("*.sk[pb]"))
    if not files:
        raise FileNotFoundError(f"no .skp or .skb in the backup folder {backup_dir}")
    out = {}
    for path in files:
        before = path.stat()
        digest = sha256_file(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise SourceUnstable(f"{path.name}: changed while it was hashed")
        out[path.name] = {"sha256": digest, "size": after.st_size,
                          "mtime": datetime.fromtimestamp(after.st_mtime).astimezone().isoformat(timespec="seconds")}
    return out


def _write_json_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".source-", suffix=".json.tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def freeze_source(export_dir: Path, backup_dir: Path, out_root: Path, snapshots_root: Path,
                  interval_s: float = 1.0, sleep=time.sleep) -> SourceFreeze:
    # abspath, not resolve(): resolving would stat the live tree from outside engine/io/snapshot.py
    export_dir = Path(os.path.abspath(export_dir))
    backup_dir = Path(backup_dir).resolve()
    out_root, snapshots_root = Path(out_root).resolve(), Path(snapshots_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    rows = read_manifest_stable(export_dir / "split" / "_MANIFEST.txt", interval_s, sleep)
    if not rows:
        raise ValueError(f"{export_dir / 'split' / '_MANIFEST.txt'} lists no files")
    backup = _hash_backup(backup_dir)
    snapshots = []
    for row in rows.values():
        res = snapshot_object(export_dir / "split" / row.file, snapshots_root, expected_tris=row.tris,
                              interval_s=interval_s, sleep=sleep)
        snapshots.append({"file": row.file, "group": row.group, "tris": res.mesh.n_faces,
                          "dir": str(Path(res.dir).resolve()), "sha256": res.sha256})
    clean = _freeze_clean(export_dir, out_root, interval_s, sleep)
    data = {
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "export_dir": str(export_dir),
        "manifest": [{"file": r.file, "tris": r.tris, "group": r.group} for r in rows.values()],
        "snapshots": snapshots,
        "clean_obj": {"path": str(clean.obj), "sha256": sha256_file(clean.obj)},
        "clean_mtl": {"path": str(clean.mtl), "sha256": sha256_file(clean.mtl)},
        "textures": clean.textures,
        "missing_textures": clean.missing,
        "rejected_textures": clean.rejected,
        "backup": backup,
        "totals": {"files": len(snapshots), "tris": sum(s["tris"] for s in snapshots)},
    }
    json_path = out_root / "source.json"
    _write_json_atomic(json_path, data)
    return SourceFreeze(json_path=json_path, clean_obj=clean.obj, clean_mtl=clean.mtl, snapshots=snapshots)
