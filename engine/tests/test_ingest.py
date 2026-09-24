import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from engine.ingest import FloorMapEntry, ingest_building, load_floor_map

OBJ = ("mtllib ../lib.mtl\no {name}\nv 0 0 0\nv 1 0 0\nv 0 1 0\n"
       "vt 0 0\nvt 1 0\nvt 0 1\nusemtl stone\nf 1/1 2/2 3/3\n")
MANIFEST = ("file  tris   sketchup group\n"
            "walk.obj   1   walk\n"
            "bad.obj    5   bad\n")

ENTRIES = [
    {"building": "CHTM", "split_object": "walk", "canonical": "CHTM_walk_obj", "level_code": "GF", "role": "sidewalk"},
    {"building": "CHTM", "split_object": "gone", "canonical": "CHTM_gone_obj", "level_code": "2F", "role": "floor"},
    {"building": "CHTM", "split_object": "bad", "canonical": "CHTM_bad_obj", "level_code": "3F", "role": "floor"},
    {"building": "CHTM", "split_object": "extra", "canonical": "CHTM_extra_obj", "level_code": "4F", "role": "floor"},
    {"building": "PE", "split_object": "walk", "canonical": "PE_walk_obj", "level_code": "GF", "role": "floor"},
]


def make_source(root):
    split = root / "split"
    split.mkdir(parents=True)
    (root / "SRC-TEX").mkdir()
    for name in ("walk", "bad", "extra"):
        (split / f"{name}.obj").write_text(OBJ.format(name=name), encoding="utf-8")
    (root / "lib.mtl").write_text("newmtl stone\nmap_Kd SRC-TEX/stone.png\n", encoding="utf-8")
    Image.fromarray(np.full((4, 4, 3), 220, np.uint8)).save(root / "SRC-TEX" / "stone.png")
    (split / "_MANIFEST.txt").write_text(MANIFEST, encoding="utf-8")
    return split


def write_map(path, entries):
    path.write_text(json.dumps({"schema": "corllenium.floor_map/1", "entries": entries}), encoding="utf-8")


def test_load_floor_map_filters_by_building(tmp_path):
    p = tmp_path / "map.json"
    write_map(p, ENTRIES)
    chtm = load_floor_map(p, "CHTM")
    assert [e.canonical for e in chtm] == ["CHTM_walk_obj", "CHTM_gone_obj", "CHTM_bad_obj", "CHTM_extra_obj"]
    assert isinstance(chtm[0], FloorMapEntry) and chtm[0].role == "sidewalk"
    assert len(load_floor_map(p)) == 5


def test_load_floor_map_rejects_other_schemas(tmp_path):
    p = tmp_path / "map.json"
    p.write_text(json.dumps({"schema": "something/9", "entries": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_floor_map(p)


def test_ingest_building_snapshots_each_mapped_object_and_reports_every_status(tmp_path):
    split = make_source(tmp_path / "src")
    map_path = tmp_path / "map.json"
    write_map(map_path, ENTRIES)
    out_root = tmp_path / "snapshots"

    rows = ingest_building(split, split / "_MANIFEST.txt", "CHTM", map_path, out_root,
                           interval_s=0, sleep=lambda s: None)

    by = {r.canonical: r for r in rows}
    assert by["CHTM_walk_obj"].status == "ok" and by["CHTM_walk_obj"].tris == 1
    snap = Path(by["CHTM_walk_obj"].snapshot_dir)
    assert snap.is_dir() and (snap / "materials.mtl").exists() and len(by["CHTM_walk_obj"].sha256) == 64
    assert snap.parent == out_root / "CHTM" / "CHTM_walk_obj"
    assert by["CHTM_gone_obj"].status == "missing" and by["CHTM_gone_obj"].snapshot_dir is None
    assert by["CHTM_bad_obj"].status == "manifest_mismatch" and "manifest says 5" in by["CHTM_bad_obj"].detail
    assert by["CHTM_extra_obj"].status == "unlisted" and by["CHTM_extra_obj"].tris == 1
    assert "PE_walk_obj" not in by

    manifest = json.loads((out_root / "CHTM" / "ingest_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "corllenium.ingest/1" and manifest["building"] == "CHTM"
    assert [r["canonical"] for r in manifest["rows"]] == [r.canonical for r in rows]
    assert manifest["rows"][0]["level_code"] == "GF" and manifest["rows"][0]["role"] == "sidewalk"


def test_ingest_building_is_idempotent(tmp_path):
    split = make_source(tmp_path / "src")
    map_path = tmp_path / "map.json"
    write_map(map_path, ENTRIES[:1])
    out_root = tmp_path / "snapshots"
    first = ingest_building(split, split / "_MANIFEST.txt", "CHTM", map_path, out_root,
                            interval_s=0, sleep=lambda s: None)
    second = ingest_building(split, split / "_MANIFEST.txt", "CHTM", map_path, out_root,
                             interval_s=0, sleep=lambda s: None)
    assert first[0].snapshot_dir == second[0].snapshot_dir
    assert len(list((out_root / "CHTM" / "CHTM_walk_obj").iterdir())) == 1


def test_ingest_building_records_a_value_error_as_status_error_and_continues(tmp_path, monkeypatch):
    import engine.ingest as ingest_mod
    split = make_source(tmp_path / "src")
    map_path = tmp_path / "map.json"
    write_map(map_path, [ENTRIES[0], ENTRIES[3]])   # walk (ok) then extra (unlisted)
    out_root = tmp_path / "snapshots"
    real = ingest_mod.snapshot_object

    def flaky(src_obj, dst_root, **kw):
        if Path(src_obj).stem == "walk":
            raise ValueError("texture basename collision under tex/: stone.png")
        return real(src_obj, dst_root, **kw)

    monkeypatch.setattr(ingest_mod, "snapshot_object", flaky)
    rows = ingest_building(split, split / "_MANIFEST.txt", "CHTM", map_path, out_root,
                           interval_s=0, sleep=lambda s: None)
    by = {r.canonical: r for r in rows}
    assert by["CHTM_walk_obj"].status == "error" and "collision" in by["CHTM_walk_obj"].detail
    assert by["CHTM_walk_obj"].snapshot_dir is None
    assert by["CHTM_extra_obj"].status == "unlisted" and by["CHTM_extra_obj"].tris == 1
    manifest = json.loads((out_root / "CHTM" / "ingest_manifest.json").read_text(encoding="utf-8"))
    assert [r["status"] for r in manifest["rows"]] == ["error", "unlisted"]
