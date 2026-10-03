import builtins
import inspect
import json
import os
from pathlib import Path

import pytest
from PIL import Image

from engine.campus.source import freeze_source
from engine.io.snapshot import ManifestMismatch

OBJ = "mtllib ../X.mtl\no {name}\nv 0 0 0\nv 10 0 0\nv 0 10 0\nvt 0 0\nvt 1 0\nvt 0 1\nusemtl m0\nf 1/1 2/2 3/3\n"
NO_SLEEP = dict(interval_s=0, sleep=lambda s: None)


def _png(path: Path, rgb=(200, 30, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), rgb).save(path)        # the importer opens textures with Pillow


def _export(tmp: Path, alpha_tris=1, clean_mtl="newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n",
            order=("Alpha", "Beta")):
    exp = tmp / "CKPT17"; split = exp / "split"
    split.mkdir(parents=True)
    (exp / "X.mtl").write_text("newmtl m0\nKd 1 1 1\nmap_Kd SRC-TEX/a.png\n")
    _png(exp / "SRC-TEX" / "a.png")
    for name in ("Alpha", "Beta"):
        (split / f"{name}.obj").write_text(OBJ.format(name=name))
    tris = {"Alpha": alpha_tris, "Beta": 1}
    (split / "_MANIFEST.txt").write_text(
        "file  tris  sketchup group\n" + "".join(f"{n}.obj  {tris[n]}  {n}\n" for n in order))
    (exp / "CKPT17-CLEAN.obj").write_text("mtllib CKPT17-CLEAN.mtl\n" + OBJ.format(name="all"))
    (exp / "CKPT17-CLEAN.mtl").write_text(clean_mtl)
    backup = tmp / "BACKUP"; backup.mkdir()
    (backup / "M.skp").write_bytes(b"skp"); (backup / "M.skb").write_bytes(b"skb")
    return exp, backup


def _freeze(tmp, exp, backup):
    return freeze_source(exp, backup, tmp / "campus", tmp / "snaps", **NO_SLEEP)


def _listing(d: Path):
    return sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns) for p in d.rglob("*"))


def test_freeze_writes_source_json_and_snapshots(tmp_path):
    exp, backup = _export(tmp_path)
    before = _listing(exp), _listing(backup)
    res = _freeze(tmp_path, exp, backup)
    data = json.loads(res.json_path.read_text())
    assert [s["file"] for s in data["snapshots"]] == ["Alpha.obj", "Beta.obj"]
    assert data["totals"] == {"files": 2, "tris": 2}
    frozen_tex = res.clean_mtl.parent / "SRC-TEX" / "a.png"
    from engine.io.snapshot import sha256_file
    assert data["textures"] == {"SRC-TEX/a.png": sha256_file(frozen_tex)}
    assert data["backup"]["M.skp"]["sha256"] == sha256_file(backup / "M.skp")
    assert set(data["backup"]) == {"M.skp", "M.skb"}
    assert res.clean_obj.exists() and res.clean_obj.read_bytes() == (exp / "CKPT17-CLEAN.obj").read_bytes()
    assert (_listing(exp), _listing(backup)) == before          # sources untouched


def test_snapshots_follow_manifest_order_not_alphabet(tmp_path):
    exp, backup = _export(tmp_path, order=("Beta", "Alpha"))
    data = json.loads(_freeze(tmp_path, exp, backup).json_path.read_text())
    assert [s["file"] for s in data["snapshots"]] == ["Beta.obj", "Alpha.obj"]


def test_manifest_mismatch_raises(tmp_path):
    exp, backup = _export(tmp_path, alpha_tris=2)
    with pytest.raises(ManifestMismatch):
        _freeze(tmp_path, exp, backup)


def test_rerun_reuses_content_addressed_snapshots_and_frozen_folder(tmp_path):
    exp, backup = _export(tmp_path)
    a = _freeze(tmp_path, exp, backup)
    b = _freeze(tmp_path, exp, backup)
    assert [s["dir"] for s in a.snapshots] == [s["dir"] for s in b.snapshots]
    assert a.clean_obj == b.clean_obj
    entries = sorted(p.name for p in (tmp_path / "campus" / "source").iterdir())
    assert len(entries) == 1 and not entries[0].startswith(".incoming-")


def test_changed_texture_under_same_obj_gets_its_own_frozen_folder(tmp_path):
    from engine.io.snapshot import sha256_file
    exp, backup = _export(tmp_path)
    a = _freeze(tmp_path, exp, backup)
    _png(exp / "SRC-TEX" / "a.png", (10, 200, 10))               # same OBJ, new texture bytes
    b = _freeze(tmp_path, exp, backup)
    data = json.loads(b.json_path.read_text())
    assert b.clean_obj.parent != a.clean_obj.parent
    assert data["textures"]["SRC-TEX/a.png"] == sha256_file(b.clean_mtl.parent / "SRC-TEX" / "a.png")
    assert data["clean_mtl"]["sha256"] == sha256_file(b.clean_mtl)


def test_same_basename_textures_in_two_folders_are_both_kept(tmp_path):
    mtl = "newmtl m0\nmap_Kd SRC-TEX/x/wall.png\nnewmtl m1\nmap_Kd SRC-TEX/y/wall.png\n"
    exp, backup = _export(tmp_path, clean_mtl=mtl)
    _png(exp / "SRC-TEX" / "x" / "wall.png", (1, 2, 3))
    _png(exp / "SRC-TEX" / "y" / "wall.png", (4, 5, 6))
    res = _freeze(tmp_path, exp, backup)
    data = json.loads(res.json_path.read_text())
    assert set(data["textures"]) == {"SRC-TEX/x/wall.png", "SRC-TEX/y/wall.png"}
    assert data["textures"]["SRC-TEX/x/wall.png"] != data["textures"]["SRC-TEX/y/wall.png"]
    assert (res.clean_mtl.parent / "SRC-TEX" / "y" / "wall.png").exists()


def test_missing_texture_is_recorded_not_fatal(tmp_path):
    exp, backup = _export(tmp_path, clean_mtl="newmtl m0\nmap_Kd SRC-TEX\\gone.png\n")
    data = json.loads(_freeze(tmp_path, exp, backup).json_path.read_text())
    assert data["missing_textures"] == ["SRC-TEX/gone.png"]


def test_texture_outside_the_export_is_rejected(tmp_path):
    exp, backup = _export(tmp_path, clean_mtl="newmtl m0\nmap_Kd ../outside/b.png\n")
    _png(tmp_path / "outside" / "b.png")
    res = _freeze(tmp_path, exp, backup)
    data = json.loads(res.json_path.read_text())
    assert data["rejected_textures"] == ["../outside/b.png"] and data["textures"] == {}
    assert not (tmp_path / "campus" / "source" / "outside").exists()


@pytest.mark.parametrize("bad", ["C:foo.png", "C:../x.png", "/abs/x.png", "D:\\x\\y.png"])
def test_drive_relative_and_absolute_texture_paths_are_rejected(tmp_path, bad):
    exp, backup = _export(tmp_path, clean_mtl=f"newmtl m0\nmap_Kd {bad}\n")
    res = _freeze(tmp_path, exp, backup)
    data = json.loads(res.json_path.read_text())
    assert data["rejected_textures"] == [bad.replace("\\", "/")] and data["textures"] == {}
    assert sorted(p.name for p in (tmp_path / "campus" / "source").iterdir()) == [res.clean_obj.parent.name]


def test_no_backup_files_raises(tmp_path):
    exp, backup = _export(tmp_path)
    for f in backup.iterdir():
        f.unlink()
    with pytest.raises(FileNotFoundError):
        _freeze(tmp_path, exp, backup)


def test_empty_manifest_raises_and_keeps_the_old_source_json(tmp_path):
    exp, backup = _export(tmp_path)
    good = _freeze(tmp_path, exp, backup).json_path.read_bytes()
    (exp / "split" / "_MANIFEST.txt").write_text("file  tris  sketchup group\n")
    with pytest.raises(ValueError):
        _freeze(tmp_path, exp, backup)
    assert (tmp_path / "campus" / "source.json").read_bytes() == good


def test_paths_in_source_json_are_absolute(tmp_path, monkeypatch):
    exp, backup = _export(tmp_path)
    monkeypatch.chdir(tmp_path)
    res = freeze_source(exp, backup, Path("campus"), Path("snaps"), **NO_SLEEP)
    data = json.loads(res.json_path.read_text())
    assert Path(data["clean_obj"]["path"]).is_absolute()
    assert all(Path(s["dir"]).is_absolute() for s in data["snapshots"])


def test_live_export_is_opened_only_through_the_snapshot_module(tmp_path, monkeypatch):
    """Every stat, open and listing under the export must come from engine/io/snapshot.py."""
    exp, backup = _export(tmp_path)
    root = str(exp.resolve()).lower()
    offenders: list[str] = []
    seen_from_snapshot: list[str] = []          # positive control: the audit must see real accesses

    def caller_module():
        for frame in inspect.stack()[2:]:
            name = frame.filename.replace("\\", "/")
            if "/engine/" in name and "/tests/" not in name:
                return name.rsplit("/engine/", 1)[1]
        return "?"

    def audited(fn):
        def wrapper(path, *args, **kwargs):
            try:
                p = os.fspath(path)
            except TypeError:
                p = None
            if isinstance(p, str) and os.path.abspath(p).lower().startswith(root):
                mod = caller_module()
                if mod == "io/snapshot.py":
                    seen_from_snapshot.append(fn.__name__)
                else:
                    offenders.append(f"{fn.__name__} {p} from {mod}")
            return fn(path, *args, **kwargs)
        wrapper.__name__ = getattr(fn, "__name__", "fn")
        return wrapper

    import io
    for name in ("stat", "lstat", "scandir", "listdir", "open", "access"):
        monkeypatch.setattr(os, name, audited(getattr(os, name)))
    monkeypatch.setattr(builtins, "open", audited(builtins.open))
    monkeypatch.setattr(io, "open", audited(io.open))       # Path.read_text/read_bytes/open go here
    _freeze(tmp_path, exp, backup)
    assert not offenders, offenders
    assert len(seen_from_snapshot) > 10, seen_from_snapshot  # the audit really watched the copies
