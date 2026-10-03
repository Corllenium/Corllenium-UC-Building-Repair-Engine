import json
import time
from pathlib import Path

import pytest
from PIL import Image

from engine.campus.source import freeze_source
from engine.io.snapshot import ManifestMismatch

OBJ = "mtllib ../X.mtl\no {name}\nv 0 0 0\nv 10 0 0\nv 0 10 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl m0\nf 1/1 2/2 3/3\n"


def _export(tmp: Path, alpha_tris=1):
    exp = tmp / "CKPT17"; split = exp / "split"; tex = exp / "SRC-TEX"
    split.mkdir(parents=True); tex.mkdir()
    (exp / "X.mtl").write_text("newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n")
    Image.new("RGB", (2, 2), (200, 30, 30)).save(tex / "a.png")   # the importer opens textures with Pillow
    for name in ("Alpha", "Beta"):
        (split / f"{name}.obj").write_text(OBJ.format(name=name))
    (split / "_MANIFEST.txt").write_text(
        "file  tris  sketchup group\n" f"Alpha.obj  {alpha_tris}  Alpha\n" "Beta.obj  1  Beta\n")
    (exp / "CKPT17-CLEAN.obj").write_text("mtllib CKPT17-CLEAN.mtl\n" + OBJ.format(name="all"))
    (exp / "CKPT17-CLEAN.mtl").write_text("newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n")
    backup = tmp / "BACKUP"; backup.mkdir()
    (backup / "M.skp").write_bytes(b"skp"); (backup / "M.skb").write_bytes(b"skb")
    return exp, backup


def _listing(d: Path):
    return sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns) for p in d.rglob("*"))


def test_freeze_writes_source_json_and_snapshots(tmp_path):
    exp, backup = _export(tmp_path)
    before = _listing(exp), _listing(backup)
    res = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    data = json.loads(res.json_path.read_text())
    assert [s["file"] for s in data["snapshots"]] == ["Alpha.obj", "Beta.obj"]
    assert data["totals"] == {"files": 2, "tris": 2}
    assert data["textures"]["a.png"] and set(data["backup"]) == {"M.skp", "M.skb"}
    assert res.clean_obj.exists() and res.clean_obj.read_bytes() == (exp / "CKPT17-CLEAN.obj").read_bytes()
    assert (_listing(exp), _listing(backup)) == before          # sources untouched


def test_manifest_mismatch_raises(tmp_path):
    exp, backup = _export(tmp_path, alpha_tris=2)
    with pytest.raises(ManifestMismatch):
        freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)


def test_rerun_reuses_content_addressed_snapshots(tmp_path):
    exp, backup = _export(tmp_path)
    a = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    b = freeze_source(exp, backup, tmp_path / "campus", tmp_path / "snaps", interval_s=0, sleep=lambda s: None)
    assert [s["dir"] for s in a.snapshots] == [s["dir"] for s in b.snapshots]
