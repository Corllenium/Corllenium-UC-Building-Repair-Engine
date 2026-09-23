import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from engine.io.snapshot import (
    ManifestMismatch,
    SourceUnstable,
    read_manifest,
    read_manifest_stable,
    snapshot_object,
    wait_stable,
)

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


def test_mtl_changing_during_copy_raises_source_unstable(tmp_path):
    src = make_source(tmp_path / "src")
    mtl_path = tmp_path / "src" / "lib.mtl"
    dst_root = tmp_path / "snap"
    calls = {"n": 0}

    def sleep(_s):
        calls["n"] += 1
        if calls["n"] == 2:  # 1st call verifies the OBJ, 2nd call verifies the MTL
            mtl_path.write_text(mtl_path.read_text() + "\n# mutated during copy\n")

    with pytest.raises(SourceUnstable):
        snapshot_object(src, dst_root, expected_tris=1, interval_s=0, sleep=sleep)
    assert calls["n"] == 2
    assert list(dst_root.glob(".incoming-*")) == []


def test_texture_changing_during_copy_raises_source_unstable(tmp_path):
    src = make_source(tmp_path / "src")
    tex_path = tmp_path / "src" / "SRC-TEX" / "stone.png"
    dst_root = tmp_path / "snap"
    calls = {"n": 0}

    def sleep(_s):
        calls["n"] += 1
        if calls["n"] == 3:  # 1st = OBJ, 2nd = MTL, 3rd = the "stone" texture
            tex_path.write_bytes(tex_path.read_bytes() + b"\x00")

    with pytest.raises(SourceUnstable):
        snapshot_object(src, dst_root, expected_tris=1, interval_s=0, sleep=sleep)
    assert calls["n"] == 3
    assert list(dst_root.glob(".incoming-*")) == []


def test_source_mtl_kept_and_materials_subset_correct(tmp_path):
    src = make_source(tmp_path / "src")
    mtl_src_path = tmp_path / "src" / "lib.mtl"
    res = snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)
    assert res.source_mtl_path is not None
    assert res.source_mtl_path.name == "source.mtl"
    assert res.source_mtl_path.read_bytes() == mtl_src_path.read_bytes()
    subset_text = res.mtl_path.read_text()
    assert "stone" in subset_text and "other" not in subset_text


def test_read_manifest_stable_matches_read_manifest_when_unchanged(tmp_path):
    p = tmp_path / "_MANIFEST.txt"
    p.write_text(MANIFEST)
    assert read_manifest_stable(p, interval_s=0, sleep=lambda s: None) == read_manifest(p)


def test_read_manifest_stable_rejects_change_during_read(tmp_path):
    p = tmp_path / "_MANIFEST.txt"
    p.write_text(MANIFEST)

    def sleep(_s):
        p.write_text(MANIFEST + "extra line changes the byte count\n")

    with pytest.raises(SourceUnstable):
        read_manifest_stable(p, interval_s=0, sleep=sleep)


def test_failed_snapshot_leaves_no_incoming_dir(tmp_path):
    src = make_source(tmp_path / "src")
    dst_root = tmp_path / "snap"
    with pytest.raises(ManifestMismatch):
        snapshot_object(src, dst_root, expected_tris=99, interval_s=0, sleep=lambda s: None)
    assert list(dst_root.glob(".incoming-*")) == []


def test_two_sequential_calls_succeed_and_stale_incoming_dir_survives_untouched(tmp_path):
    src = make_source(tmp_path / "src")
    dst_root = tmp_path / "snap"
    dst_root.mkdir(parents=True)
    # A ".incoming-<stem>" directory left behind by a crashed run under the old, deterministic
    # naming scheme. A per-call tempfile.mkdtemp() name must never collide with, or trigger
    # cleanup logic against, this unrelated leftover directory.
    stale = dst_root / ".incoming-walk"
    stale.mkdir()
    (stale / "leftover.txt").write_text("crashed run debris")

    first = snapshot_object(src, dst_root, expected_tris=1, interval_s=0, sleep=lambda s: None)
    second = snapshot_object(src, dst_root, expected_tris=1, interval_s=0, sleep=lambda s: None)

    assert first.dir == second.dir and second.mesh.n_faces == 1
    assert stale.exists() and (stale / "leftover.txt").read_text() == "crashed run debris"
    assert [p for p in dst_root.glob(".incoming-*") if p != stale] == []


def test_identical_bytes_under_another_name_reuse_the_existing_snapshot(tmp_path):
    # The snapshot directory is keyed on the OBJ bytes alone, so a second source file with the same
    # bytes but a different name lands on the directory the first one created -- and must load the
    # OBJ that directory actually holds, not look for its own file name there.
    src = make_source(tmp_path / "src")
    twin = src.with_name("twin.obj")
    twin.write_bytes(src.read_bytes())
    dst_root = tmp_path / "snap"

    first = snapshot_object(src, dst_root, expected_tris=1, interval_s=0, sleep=lambda s: None)
    second = snapshot_object(twin, dst_root, expected_tris=1, interval_s=0, sleep=lambda s: None)

    assert second.dir == first.dir and second.sha256 == first.sha256
    assert second.obj_path.name == "walk.obj" and second.mesh.n_faces == 1
    assert second.textures["stone"].exists() and second.flatness["stone"] == 0.0
    assert sorted(p.name for p in first.dir.glob("*.obj")) == ["walk.obj"]  # still one OBJ per snapshot


def test_snapshot_wraps_permission_error_during_copy_as_source_unstable(tmp_path, monkeypatch):
    src = make_source(tmp_path / "src")

    def boom(*_a, **_k):
        raise PermissionError("locked by another process")

    monkeypatch.setattr(shutil, "copyfile", boom)
    with pytest.raises(SourceUnstable, match="locked by another process"):
        snapshot_object(src, tmp_path / "snap", expected_tris=1, interval_s=0, sleep=lambda s: None)


def test_texture_basename_collision_between_different_source_paths_is_refused(tmp_path):
    src_dir = tmp_path / "src"
    (src_dir / "split").mkdir(parents=True)
    (src_dir / "a").mkdir(parents=True)
    (src_dir / "b").mkdir(parents=True)
    obj = src_dir / "split" / "walk.obj"
    obj.write_text(
        "mtllib ../lib.mtl\no walk\n"
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 1 0\n"
        "vt 0 0\nvt 1 0\nvt 0 1\n"
        "usemtl mat_a\nf 1/1 2/2 3/3\n"
        "usemtl mat_b\nf 1/1 2/2 4/3\n"
    )
    (src_dir / "lib.mtl").write_text("newmtl mat_a\nmap_Kd a/stone.png\n\nnewmtl mat_b\nmap_Kd b/stone.png\n")
    Image.fromarray(np.full((4, 4, 3), 200, np.uint8)).save(src_dir / "a" / "stone.png")
    Image.fromarray(np.full((4, 4, 3), 50, np.uint8)).save(src_dir / "b" / "stone.png")
    dst_root = tmp_path / "snap"

    with pytest.raises(ValueError) as exc_info:
        snapshot_object(obj, dst_root, expected_tris=2, interval_s=0, sleep=lambda s: None)
    msg = str(exc_info.value)
    assert "a/stone.png" in msg and "b/stone.png" in msg
    assert list(dst_root.glob(".incoming-*")) == []  # refused before any copying


def test_read_manifest_stable_wraps_os_error_as_source_unstable(tmp_path, monkeypatch):
    p = tmp_path / "_MANIFEST.txt"
    p.write_text(MANIFEST)

    def boom(self, *_a, **_k):
        raise PermissionError("locked by another process")

    monkeypatch.setattr(Path, "read_bytes", boom)
    with pytest.raises(SourceUnstable, match="locked by another process"):
        read_manifest_stable(p, interval_s=0, sleep=lambda s: None)
