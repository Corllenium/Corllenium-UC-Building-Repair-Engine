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
    (tmp_path / "split").mkdir(parents=True)
    (tmp_path / "SRC-TEX").mkdir(parents=True)
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
