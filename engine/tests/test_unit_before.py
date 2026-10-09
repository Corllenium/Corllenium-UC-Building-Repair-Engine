"""A campus unit's BEFORE for the Validator (P1-H1 item 9): its members' frozen snapshots combined, the banded
members cut by face-centre z (lo <= z < hi), written as a snapshot-shaped folder `validate --before` takes."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from engine import cli
from engine.io.mtl import parse_mtl
from engine.io.obj_reader import read_obj
from engine.io.snapshot import sha256_file


def _png() -> bytes:
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (200, 60, 40)).save(buf, format="PNG")
    return buf.getvalue()


PNG_BRICK = _png()


def _tri(z: float, x0: float = 0.0) -> list:
    """One triangle whose centre is at height z."""
    return [(x0, 0.0, z - 1.0), (x0 + 10.0, 0.0, z - 1.0), (x0, 0.0, z + 2.0)]


def _write_snapshot(root: Path, name: str, tris: list, mats: list, mtl: str, textures: dict) -> dict:
    """tris: list of (z, material index); returns the source.json snapshot row."""
    d = root / name
    (d / "tex").mkdir(parents=True)
    lines, faces = ["mtllib materials.mtl", f"o {name}"], []
    for k, (z, _m) in enumerate(tris):
        for p in _tri(z, x0=20.0 * k):
            lines.append("v %s %s %s" % p)
    lines += ["vt 0 0", "vt 1 0", "vt 0 1"]
    current = None
    for k, (_z, m) in enumerate(tris):
        if m != current:
            faces.append(f"usemtl {mats[m]}")
            current = m
        a = 3 * k + 1
        faces.append(f"f {a}/1 {a + 1}/2 {a + 2}/3")
    obj = d / f"{name}.obj"
    obj.write_text("\n".join(lines + faces) + "\n", encoding="utf-8")
    (d / "materials.mtl").write_text(mtl, encoding="utf-8")
    for tex, data in textures.items():
        (d / "tex" / tex).write_bytes(data)
    return {"file": f"{name}.obj", "group": name, "tris": len(tris), "dir": str(d), "sha256": sha256_file(obj)}


MTL_A = "newmtl brick\nKd 0.5 0.5 0.5\nd 1\nmap_Kd tex/brick.png\n\nnewmtl glass\nKd 0.1 0.2 0.3\nd 0.5\n"
MTL_B = "newmtl brick\nKd 0.5 0.5 0.5\nd 1\nmap_Kd tex/brick.png\n\nnewmtl paint\nKd 0.9 0.9 0.9\nd 1\n"


@pytest.fixture
def campus(tmp_path):
    snaps = tmp_path / "snapshots"
    a = _write_snapshot(snaps, "Floor_A", [(10.0, 0), (60.0, 1), (95.0, 0)], ["brick", "glass"], MTL_A,
                        {"brick.png": PNG_BRICK})
    # B: centres 20, 50, exactly 100 (belongs to band 2, not band 1), 150, 250
    b = _write_snapshot(snaps, "Shell_B", [(20.0, 0), (50.0, 1), (100.0, 0), (150.0, 1), (250.0, 0)],
                        ["brick", "paint"], MTL_B, {"brick.png": PNG_BRICK})
    source = {"snapshots": [a, b]}
    cmap = {"units": [
        {"unit": "B-L01", "members": [
            {"group": "Floor_A", "file": "Floor_A.obj", "sha256": a["sha256"], "tris": 3, "faces": "all"},
            {"group": "Shell_B", "file": "Shell_B.obj", "sha256": b["sha256"], "tris": 2, "faces": "band 1",
             "z_range": [None, 100.0]}]},
        {"unit": "B-L02", "members": [
            {"group": "Shell_B", "file": "Shell_B.obj", "sha256": b["sha256"], "tris": 2, "faces": "band 2",
             "z_range": [100.0, 200.0]}]},
        {"unit": "B-L03", "members": [
            {"group": "Shell_B", "file": "Shell_B.obj", "sha256": b["sha256"], "tris": 1, "faces": "band 3",
             "z_range": [200.0, None]}]},
    ], "excluded": []}
    (tmp_path / "campus_map.json").write_text(json.dumps(cmap), encoding="utf-8")
    (tmp_path / "source.json").write_text(json.dumps(source), encoding="utf-8")
    return tmp_path


def _build(campus, unit, **kw):
    from engine.campus.unit_before import build_unit_before
    cmap = json.loads((campus / "campus_map.json").read_text(encoding="utf-8"))
    source = json.loads((campus / "source.json").read_text(encoding="utf-8"))
    return build_unit_before(cmap, source, unit, campus / "out" / unit, **kw)


def test_an_all_member_and_a_banded_member_combine(campus):
    report = _build(campus, "B-L01")
    mesh = read_obj(Path(report["obj"]))
    assert mesh.n_faces == 3 + 2 == report["faces"]
    assert [m["faces"] for m in report["members"]] == [3, 2] and report["matches_campus_map"] is True
    cz = mesh.positions[mesh.face_v][:, :, 2].mean(axis=1)
    assert sorted(np.round(cz, 3)) == [10.0, 20.0, 50.0, 60.0, 95.0]      # band 1: 20 and 50 (not 100, 150, 250)


def test_a_face_exactly_on_a_band_edge_belongs_to_the_upper_band(campus):
    l2 = read_obj(Path(_build(campus, "B-L02")["obj"]))
    cz = l2.positions[l2.face_v][:, :, 2].mean(axis=1)
    assert sorted(np.round(cz, 3)) == [100.0, 150.0]                       # lo <= z < hi
    l3 = read_obj(Path(_build(campus, "B-L03")["obj"]))
    assert l3.n_faces == 1


def test_the_bands_of_one_group_partition_it(campus):
    total = sum(_build(campus, u)["members"][-1]["faces"] for u in ("B-L01", "B-L02", "B-L03"))
    assert total == 5


def test_materials_are_merged_by_name_and_faces_keep_theirs(campus):
    report = _build(campus, "B-L01")
    mesh = read_obj(Path(report["obj"]))
    assert sorted(mesh.materials) == ["brick", "glass", "paint"]
    names = [mesh.materials[i] for i in mesh.face_material]
    assert sorted(names) == sorted(["brick", "glass", "brick", "brick", "paint"])   # A: b g b; B kept: 20 b, 50 p
    assert mesh.mtllib == "materials.mtl"


def test_the_output_is_a_snapshot_folder_the_validator_can_load_and_textures_are_referenced(campus):
    report = _build(campus, "B-L01")
    out = Path(report["obj"]).parent
    obj, mesh, _flat, mtl = cli._load_snapshot(out)                       # what `validate --before` calls
    assert obj.name == "B-L01.obj" and mesh.n_faces == 5
    assert set(mtl) == {"brick", "glass", "paint"}
    brick = (campus / "snapshots" / "Floor_A" / "tex" / "brick.png").resolve()
    assert Path(mtl["brick"].map_kd).resolve() == brick                      # referenced in place ...
    assert not (out / "tex").exists()                                       # ... and not copied


def test_textures_are_copied_only_when_asked(campus):
    report = _build(campus, "B-L01", copy_textures=True)
    out = Path(report["obj"]).parent
    assert (out / "tex" / "brick.png").read_bytes() == PNG_BRICK
    assert parse_mtl(out / "materials.mtl")["brick"].map_kd == "tex/brick.png"


def test_one_material_name_with_two_definitions_is_refused(campus):
    bad = campus / "snapshots" / "Shell_B" / "materials.mtl"
    bad.write_text(MTL_B.replace("Kd 0.5 0.5 0.5", "Kd 0.6 0.5 0.5"), encoding="utf-8")
    with pytest.raises(ValueError, match="brick"):
        _build(campus, "B-L01")


def test_a_snapshot_that_changed_since_the_freeze_is_refused(campus):
    obj = campus / "snapshots" / "Floor_A" / "Floor_A.obj"
    obj.write_text(obj.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        _build(campus, "B-L01")


def test_an_unknown_unit_and_a_protected_output_are_refused(campus):
    with pytest.raises(ValueError, match="no unit"):
        _build(campus, "NOPE-L09")
    from engine.campus.unit_before import build_unit_before
    cmap = json.loads((campus / "campus_map.json").read_text(encoding="utf-8"))
    source = json.loads((campus / "source.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="protected"):
        build_unit_before(cmap, source, "B-L01", campus / "CHECKPOINT-17-BACKUP" / "x")


def test_a_face_count_that_differs_from_the_campus_map_is_reported(campus):
    cmap = json.loads((campus / "campus_map.json").read_text(encoding="utf-8"))
    cmap["units"][0]["members"][1]["tris"] = 7
    (campus / "campus_map.json").write_text(json.dumps(cmap), encoding="utf-8")
    report = _build(campus, "B-L01")
    assert report["matches_campus_map"] is False
    assert report["members"][1]["expected"] == 7 and report["members"][1]["faces"] == 2


def test_the_cli_subcommand_builds_the_folder(campus, capsys):
    out = campus / "cli_out"
    rc = cli.main(["campus-unit-before", "--unit", "B-L02", "--map", str(campus / "campus_map.json"),
                   "--source", str(campus / "source.json"), "--out", str(out)])
    assert rc == 0
    assert (out / "B-L02.obj").is_file() and (out / "materials.mtl").is_file()
    assert "B-L02" in capsys.readouterr().out


def test_the_cli_refuses_a_protected_output_and_an_unknown_unit(campus, capsys):
    base = ["campus-unit-before", "--map", str(campus / "campus_map.json"), "--source", str(campus / "source.json")]
    assert cli.main([*base, "--unit", "B-L01", "--out", str(campus / "UC ENVIRONMENT BUILDING" / "x")]) == 2
    assert "protected" in capsys.readouterr().err
    assert cli.main([*base, "--unit", "NOPE", "--out", str(campus / "o")]) == 2
    assert "no unit" in capsys.readouterr().err
