"""Freeze the CHECKPOINT-17 export (spec 2026-10-03, P0 task 7).

Every later step reads these frozen copies, never the live export folder, which has been rewritten
mid-read before. The live tree is opened only through `engine.io.snapshot`:
- every split OBJ becomes a content-addressed snapshot (checked against `_MANIFEST.txt`);
- `CKPT17-CLEAN.obj`, its MTL and every texture that MTL names are copied, stable-checked, into
  `<out>/source/<sha12 of the OBJ>/`;
- the owner's CHECKPOINT-17 backup is only hashed in place.
The result is `<out>/source.json`.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from engine.io.mtl import parse_mtl
from engine.io.snapshot import copy_verified, read_manifest_stable, sha256_file, snapshot_object

CLEAN_OBJ = "CKPT17-CLEAN.obj"


@dataclass
class SourceFreeze:
    json_path: Path
    snapshots: list[dict] = field(default_factory=list)   # {"file","group","tris","dir","sha256"}
    clean_obj: Path | None = None
    clean_mtl: Path | None = None


def _freeze_clean(export_dir: Path, out_root: Path, interval_s: float, sleep) -> tuple[Path, Path, dict, list]:
    """Copy CKPT17-CLEAN.obj, its MTL and the MTL's textures into source/<sha12>/."""
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
        for mat in parse_mtl(mtl_copy).values():
            if not mat.map_kd:
                continue
            rel = Path(mat.map_kd.replace("\\", "/"))
            src_tex = export_dir / rel
            if not src_tex.exists():
                missing.append(str(rel))
                continue
            dst_tex = tmp / rel
            if rel.name in textures:
                continue
            dst_tex.parent.mkdir(parents=True, exist_ok=True)
            copy_verified(src_tex, dst_tex, interval_s, sleep)
            textures[rel.name] = sha256_file(dst_tex)
        final = src_root / sha256_file(obj_copy)[:12]
        if final.exists():
            shutil.rmtree(tmp)
        else:
            tmp.rename(final)
        return final / CLEAN_OBJ, final / mtl_name, textures, sorted(set(missing))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _hash_backup(backup_dir: Path) -> dict:
    out = {}
    for path in sorted(backup_dir.glob("*.sk[pb]")):
        stat = path.stat()
        out[path.name] = {"sha256": sha256_file(path), "size": stat.st_size,
                          "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")}
    return out


def freeze_source(export_dir: Path, backup_dir: Path, out_root: Path, snapshots_root: Path,
                  interval_s: float = 1.0, sleep=time.sleep) -> SourceFreeze:
    export_dir, backup_dir = Path(export_dir), Path(backup_dir)
    out_root, snapshots_root = Path(out_root), Path(snapshots_root)
    out_root.mkdir(parents=True, exist_ok=True)
    rows = read_manifest_stable(export_dir / "split" / "_MANIFEST.txt", interval_s, sleep)
    snapshots = []
    for row in rows.values():
        res = snapshot_object(export_dir / "split" / row.file, snapshots_root, expected_tris=row.tris,
                              interval_s=interval_s, sleep=sleep)
        snapshots.append({"file": row.file, "group": row.group, "tris": res.mesh.n_faces,
                          "dir": str(res.dir), "sha256": res.sha256})
    clean_obj, clean_mtl, textures, missing = _freeze_clean(export_dir, out_root, interval_s, sleep)
    data = {
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "export_dir": str(export_dir),
        "manifest": [{"file": r.file, "tris": r.tris, "group": r.group} for r in rows.values()],
        "snapshots": snapshots,
        "clean_obj": {"path": str(clean_obj), "sha256": sha256_file(clean_obj)},
        "clean_mtl": {"path": str(clean_mtl), "sha256": sha256_file(clean_mtl)},
        "textures": textures,
        "missing_textures": missing,
        "backup": _hash_backup(backup_dir),
        "totals": {"files": len(snapshots), "tris": sum(s["tris"] for s in snapshots)},
    }
    json_path = out_root / "source.json"
    tmp_json = json_path.with_suffix(".json.tmp")
    tmp_json.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp_json.replace(json_path)
    return SourceFreeze(json_path=json_path, snapshots=snapshots, clean_obj=clean_obj, clean_mtl=clean_mtl)
