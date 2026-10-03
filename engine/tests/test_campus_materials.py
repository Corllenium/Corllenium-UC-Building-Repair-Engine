import json
from pathlib import Path
import pytest

from engine.campus.materials import parse_kd_d, look_key, build_materials
from engine.io.mtl import MtlMaterial


def test_parse_kd_d_defaults():
    mat = MtlMaterial("empty")
    kd, d = parse_kd_d(mat)
    assert kd == (1.0, 1.0, 1.0)
    assert d == 1.0


def test_parse_kd_d_parsed():
    mat = MtlMaterial("parsed", lines=["Kd 0.5 0.6 0.7", "d 0.8"])
    kd, d = parse_kd_d(mat)
    assert kd == (0.5, 0.6, 0.7)
    assert d == 0.8


def test_look_key_format():
    key1 = look_key("texhash123", (0.5, 0.5, 0.5), 1.0)
    key2 = look_key("texhash123", [0.5, 0.5, 0.5], 1.0)
    assert len(key1) == 16
    assert key1 == key2

    key_none = look_key(None, (1.0, 1.0, 1.0), 1.0)
    assert len(key_none) == 16
    assert key_none != key1


def _make_fixture_mtl(tmp_path: Path):
    tex_dir = tmp_path / "SRC-TEX"
    tex_dir.mkdir(parents=True)
    img_bytes = b"fake_png_image_data_here"
    (tex_dir / "img_a.png").write_bytes(img_bytes)
    (tex_dir / "img_b.png").write_bytes(img_bytes)  # identical content to img_a.png

    mtl_lines = [
        "newmtl mat_a",
        "Kd 0.8 0.8 0.8",
        "d 1.0",
        "map_Kd SRC-TEX/img_a.png",
        "",
        "newmtl mat_b",
        "Kd 0.8 0.8 0.8",
        "d 1.0",
        "map_Kd SRC-TEX/img_b.png",
        "",
        "newmtl mat_kd_diff",
        "Kd 0.2 0.2 0.2",
        "d 1.0",
        "map_Kd SRC-TEX/img_a.png",
        "",
        "newmtl mat_missing_tex",
        "Kd 0.8 0.8 0.8",
        "map_Kd SRC-TEX/nonexistent.png",
    ]
    mtl_file = tmp_path / "test.mtl"
    mtl_file.write_text("\n".join(mtl_lines), encoding="utf-8")
    return mtl_file, tex_dir


def test_build_materials_same_look_for_same_bytes_and_kd(tmp_path):
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    res = build_materials(mtl_file, tex_dir)
    assert res["materials"]["mat_a"]["look"] == res["materials"]["mat_b"]["look"]
    assert "mat_a" in res["looks"][res["materials"]["mat_a"]["look"]]
    assert "mat_b" in res["looks"][res["materials"]["mat_a"]["look"]]


def test_build_materials_kd_differs_different_look(tmp_path):
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    res = build_materials(mtl_file, tex_dir)
    assert res["materials"]["mat_a"]["look"] != res["materials"]["mat_kd_diff"]["look"]


def test_build_materials_missing_texture(tmp_path):
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    res = build_materials(mtl_file, tex_dir)
    m = res["materials"]["mat_missing_tex"]
    assert m["missing_texture"] is True
    assert m["tex_sha256"] is None
    expected_look = look_key("missing:SRC-TEX/nonexistent.png", (0.8, 0.8, 0.8), 1.0)
    assert m["look"] == expected_look


def test_build_materials_d_defaults_to_1(tmp_path):
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    res = build_materials(mtl_file, tex_dir)
    assert res["materials"]["mat_missing_tex"]["d"] == 1.0


def test_build_materials_stats_4_material_fixture(tmp_path):
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    res = build_materials(mtl_file, tex_dir)
    stats = res["stats"]
    assert stats["materials"] == 4
    assert stats["textured"] == 4
    assert stats["images"] == 1
    assert stats["looks"] == 3


def test_build_materials_untextured(tmp_path):
    mtl_file = tmp_path / "untextured.mtl"
    mtl_file.write_text("newmtl plain\nKd 0.5 0.5 0.5\nd 0.9\n", encoding="utf-8")
    res = build_materials(mtl_file, tmp_path)
    m = res["materials"]["plain"]
    assert m["map_kd"] is None
    assert m["tex_sha256"] is None
    assert m["missing_texture"] is False
    assert m["kd"] == [0.5, 0.5, 0.5]
    assert m["d"] == 0.9
    assert res["stats"]["materials"] == 1
    assert res["stats"]["textured"] == 0
    assert res["stats"]["images"] == 0
    assert res["stats"]["looks"] == 1


def test_cli_campus_materials(tmp_path, capsys):
    from engine.cli import main
    mtl_file, tex_dir = _make_fixture_mtl(tmp_path)
    out_json = tmp_path / "materials.json"
    ret = main(["campus-materials", "--mtl", str(mtl_file), "--tex-dir", str(tex_dir), "--out", str(out_json)])
    assert ret == 0
    assert out_json.is_file()
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["stats"]["materials"] == 4
    captured = capsys.readouterr()
    assert "materials: 4" in captured.out
    assert "wrote materials to" in captured.out

