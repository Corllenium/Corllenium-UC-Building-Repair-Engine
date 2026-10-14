import os
import shutil
from pathlib import Path

import pytest

from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import cube
from engine.unity import mirror
from engine.unity.mirror import MirrorError, mirror_import


def test_a_stale_importer_copy_is_refused_naming_both_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (False, "aaa", "bbb"))
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="aaa.*bbb"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out")


def test_a_missing_unity_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (True, "a", "a"))
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="Unity"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out", unity_exe=tmp_path / "nope.exe")


def test_a_timeout_kills_only_its_own_process_and_leaves_no_valid_dump(tmp_path, monkeypatch):
    monkeypatch.setattr(mirror, "_importer_ok", lambda: (True, "a", "a"))
    killed = []
    monkeypatch.setattr(mirror, "_kill_tree", lambda pid: killed.append(pid))
    fake = tmp_path / "sleep.cmd"
    fake.write_text("@ping -n 30 127.0.0.1 >nul\n")
    write_obj(cube(100.0), tmp_path / "b.obj")
    with pytest.raises(MirrorError, match="timed out"):
        mirror_import(tmp_path / "b.obj", tmp_path / "out", unity_exe=fake, timeout_s=2)
    assert len(killed) == 1
    assert not list((tmp_path / "out").glob("*.unity.json"))


UNITY = Path(os.environ.get("UC_UNITY_EXE", str(getattr(mirror, "DEFAULT_UNITY", ""))))


@pytest.mark.unity
@pytest.mark.skipif(not UNITY.is_file(), reason="Unity 6000.4.7f1 not installed")
def test_a_real_round_trip_under_a_neutral_preset_is_unity_safe(tmp_path):
    from engine import cli
    write_obj(cube(100.0), tmp_path / "b.obj")
    neutral = {"weldVertices": "false", "importNormals": "Import", "meshCompression": "Off",
               "indexFormat": "UInt32"}
    dump = mirror_import(tmp_path / "b.obj", tmp_path / "dump", overrides=neutral)
    assert cli.main(["unity-check", "--build", str(tmp_path / "b.obj"), "--unity", str(dump),
                     "--out", str(tmp_path / "chk")]) == 0
