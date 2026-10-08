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


def test_parse_kd_d_tr_support():
    # Tr: use d = 1 - Tr when d is absent
    mat_tr = MtlMaterial("tr_only", lines=["Tr 0.2"])
    kd, d = parse_kd_d(mat_tr)
    assert d == pytest.approx(0.8)

    # When d is present, d wins
    mat_both = MtlMaterial("both", lines=["d 0.5", "Tr 0.2"])
    kd2, d2 = parse_kd_d(mat_both)
    assert d2 == 0.5


def test_kd_rounding_mutant():
    # Kd 0.80001 == 0.8 but 0.8001 != 0.8
    assert look_key(None, (0.80001, 0.8, 0.8), 1.0) == look_key(None, (0.8, 0.8, 0.8), 1.0)
    assert look_key(None, (0.8001, 0.8, 0.8), 1.0) != look_key(None, (0.8, 0.8, 0.8), 1.0)


def test_d_opacity_mutant():
    # d 0.9 != 1.0
    assert look_key(None, (1.0, 1.0, 1.0), 0.9) != look_key(None, (1.0, 1.0, 1.0), 1.0)


def test_backslash_map_kd_equals_slash(tmp_path):
    # "SRC-TEX\a.png" equals the slash form
    tex_dir = tmp_path / "SRC-TEX"
    tex_dir.mkdir(parents=True)
    (tex_dir / "a.png").write_bytes(b"image_a")

    mtl = tmp_path / "backslash.mtl"
    mtl.write_text(
        "newmtl slash\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n\nnewmtl backslash\nKd 1 1 1\nmap_Kd SRC-TEX\\a.png\n",
        encoding="utf-8",
    )
    res = build_materials(mtl, tex_dir)
    assert res["materials"]["slash"]["look"] == res["materials"]["backslash"]["look"]
    assert res["materials"]["backslash"]["map_kd"] == "SRC-TEX/a.png"
    assert res["stats"]["images"] == 1


def test_same_name_textures_two_folders(tmp_path):
    # same-name textures in two folders must stay apart (images must count 2)
    # even when tex_dir points to folder_a (which contains tile.png)
    dir_a = tmp_path / "folder_a"
    dir_b = tmp_path / "folder_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "tile.png").write_bytes(b"content_A")
    (dir_b / "tile.png").write_bytes(b"content_B")

    mtl = tmp_path / "two_folders.mtl"
    mtl.write_text(
        "newmtl mat_a\nKd 1 1 1\nmap_Kd folder_a/tile.png\n\nnewmtl mat_b\nKd 1 1 1\nmap_Kd folder_b/tile.png\n",
        encoding="utf-8",
    )
    # tex_dir is passed as folder_a: under the old code, mat_b resolves to folder_a/tile.png by basename!
    res = build_materials(mtl, dir_a)
    assert res["materials"]["mat_a"]["look"] != res["materials"]["mat_b"]["look"]
    assert res["stats"]["images"] == 2


def test_missing_exact_path_is_missing_texture(tmp_path):
    # folder_b/tile.png is absent and folder_a/tile.png exists.
    # A material whose map_Kd is folder_b/tile.png gets missing_texture: true,
    # is not given folder_a's bytes, and does not share folder_a's look.
    dir_a = tmp_path / "folder_a"
    dir_a.mkdir()
    (dir_a / "tile.png").write_bytes(b"content_A")
    # folder_b/tile.png is absent

    mtl = tmp_path / "missing_exact.mtl"
    mtl.write_text(
        "newmtl mat_a\nKd 1 1 1\nmap_Kd folder_a/tile.png\n\nnewmtl mat_b\nKd 1 1 1\nmap_Kd folder_b/tile.png\n",
        encoding="utf-8",
    )
    res = build_materials(mtl, dir_a)
    mat_a = res["materials"]["mat_a"]
    mat_b = res["materials"]["mat_b"]
    assert mat_b["missing_texture"] is True
    assert mat_b["tex_sha256"] is None
    assert mat_b["look"] != mat_a["look"]
    assert mat_b["look"] == look_key("missing:folder_b/tile.png", (1.0, 1.0, 1.0), 1.0)


def test_reject_invalid_texture_paths(tmp_path):
    # Reject absolute, drive-letter (any ":") and ".." map_Kd paths
    # Put the MTL in a subfolder so the ".." case stays inside tmp_path
    sub = tmp_path / "sub"
    sub.mkdir()
    escape_file = tmp_path / "escape.png"
    escape_file.write_bytes(b"escaped")

    mtl = sub / "invalid_paths.mtl"
    mtl.write_text(
        "newmtl mat_drive\nKd 1 1 1\nmap_Kd C:foo.png\n\n"
        "newmtl mat_abs\nKd 1 1 1\nmap_Kd /root/foo.png\n\n"
        "newmtl mat_dotdot\nKd 1 1 1\nmap_Kd ../escape.png\n",
        encoding="utf-8",
    )
    res = build_materials(mtl, sub)
    for name in ["mat_drive", "mat_abs", "mat_dotdot"]:
        m = res["materials"][name]
        assert m["missing_texture"] is True
        assert m["tex_sha256"] is None
        assert m["look"] == look_key(f"missing:{m['map_kd']}", (1.0, 1.0, 1.0), 1.0)


def test_two_different_byte_textures_same_kd(tmp_path):
    # two different-byte textures with the same Kd give different looks and images == 2
    tex_dir = tmp_path / "SRC-TEX"
    tex_dir.mkdir(parents=True)
    (tex_dir / "tex1.png").write_bytes(b"texture_one_unique_bytes")
    (tex_dir / "tex2.png").write_bytes(b"texture_two_different_bytes")

    mtl = tmp_path / "diff_textures.mtl"
    mtl.write_text(
        "newmtl mat1\nKd 0.7 0.7 0.7\nmap_Kd SRC-TEX/tex1.png\n\n"
        "newmtl mat2\nKd 0.7 0.7 0.7\nmap_Kd SRC-TEX/tex2.png\n",
        encoding="utf-8",
    )
    res = build_materials(mtl, tex_dir)
    assert res["materials"]["mat1"]["look"] != res["materials"]["mat2"]["look"]
    assert res["stats"]["images"] == 2


def test_cli_fabricated_source_json(tmp_path, monkeypatch):
    # a --source run on a fabricated source.json; relative --out stays relative to cwd.
    # Runs from a cwd different from source.json's folder, with decoy SRC-TEX elsewhere,
    # asserting that the sibling of the MTL is the one used.
    import hashlib
    from engine.cli import main

    models_dir = tmp_path / "models"
    sibling_tex = models_dir / "SRC-TEX"
    sibling_tex.mkdir(parents=True)
    real_bytes = b"real_sibling_tile_data"
    (sibling_tex / "tile.png").write_bytes(real_bytes)
    mtl = models_dir / "clean.mtl"
    mtl.write_text(
        "newmtl mat1\nKd 1 1 1\nmap_Kd tile.png\n\n"
        "newmtl mat2\nKd 1 1 1\nmap_Kd SRC-TEX/tile.png\n",
        encoding="utf-8",
    )

    source_dir = tmp_path / "source_dir"
    source_dir.mkdir(parents=True)
    source_json = source_dir / "source.json"
    source_json.write_text(
        json.dumps({"clean_mtl": {"path": str(mtl)}}),
        encoding="utf-8",
    )
    # Decoy SRC-TEX next to source.json
    decoy_source_tex = source_dir / "SRC-TEX"
    decoy_source_tex.mkdir(parents=True)
    (decoy_source_tex / "tile.png").write_bytes(b"decoy_source_tile_data")

    # Run from a different cwd (work_dir != source_dir != models_dir)
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True)
    # Decoy SRC-TEX in work_dir
    decoy_work_tex = work_dir / "SRC-TEX"
    decoy_work_tex.mkdir(parents=True)
    (decoy_work_tex / "tile.png").write_bytes(b"decoy_work_tile_data")

    monkeypatch.chdir(work_dir)
    ret = main(["campus-materials", "--source", str(source_json), "--out", "relative_out.json"])
    assert ret == 0

    rel_out = work_dir / "relative_out.json"
    assert rel_out.is_file()
    assert not (source_dir / "relative_out.json").exists()
    assert not (models_dir / "relative_out.json").exists()

    data = json.loads(rel_out.read_text(encoding="utf-8"))
    assert data["stats"]["materials"] == 2
    assert data["stats"]["images"] == 1
    real_sha = hashlib.sha256(real_bytes).hexdigest()
    assert data["materials"]["mat1"]["tex_sha256"] == real_sha
    assert data["materials"]["mat2"]["tex_sha256"] == real_sha
    assert data["materials"]["mat1"]["missing_texture"] is False
    assert data["materials"]["mat2"]["missing_texture"] is False


def test_cli_largest_look_group_printed_first(tmp_path, capsys):
    # the largest look group printed first
    from engine.cli import main
    mtl = tmp_path / "groups.mtl"
    lines = [
        "newmtl a1\nKd 0.1 0.1 0.1",
        "newmtl a2\nKd 0.1 0.1 0.1",
        "newmtl a3\nKd 0.1 0.1 0.1",
        "newmtl b1\nKd 0.2 0.2 0.2",
        "newmtl c1\nKd 0.3 0.3 0.3",
        "newmtl c2\nKd 0.3 0.3 0.3",
    ]
    mtl.write_text("\n\n".join(lines), encoding="utf-8")
    out_json = tmp_path / "out.json"
    ret = main(["campus-materials", "--mtl", str(mtl), "--tex-dir", str(tmp_path), "--out", str(out_json)])
    assert ret == 0
    captured = capsys.readouterr()
    lines = [line.strip() for line in captured.out.splitlines() if "materials):" in line]
    assert len(lines) == 3
    assert "(3 materials):" in lines[0]
    assert "(2 materials):" in lines[1]
    assert "(1 materials):" in lines[2]


