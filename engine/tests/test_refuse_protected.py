"""One output-path guard for every writer (P1-H1 item 2). The folders named here are only STRINGS in a temp tree:
nothing in these tests touches the real export, master or backup."""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import cli

EXPORT = "UC ENVIRONMENT BUILDING"


def _bad(tmp_path: Path, name: str) -> Path:
    return tmp_path / name / "REQUIREMENTS" / "out"


@pytest.mark.parametrize("bad", [
    r"D:\PROJECTS\UC ENVIRONMENT BUILDING\REQUIREMENTS\01-MODEL-EXPORT\CKPT17\x",
    r"D:\PROJECTS\UC\02-SKETCHUP\current\x.skp",
    r"D:\PROJECTS\UC MODEL FIXER\MODEL FIXER ENGINE FILES\02-SKETCHUP-MODELS\CHECKPOINT-17-BACKUP\x.skp",
    r"D:\PROJECTS\UC MODEL FIXER\..\UC\02-SKETCHUP\current\x.skp",
    "D:/PROJECTS/UC MODEL FIXER/../UC ENVIRONMENT BUILDING/x",
    "d:/projects/uc/02-sketchup/current/sub/../x.skp",
])
def test_the_resolved_path_decides(bad):
    from engine.io.protected import refuse_protected
    with pytest.raises(ValueError, match="protected"):
        refuse_protected(bad)


def test_a_relative_path_is_judged_where_it_lands(tmp_path, monkeypatch):
    from engine.io.protected import refuse_protected
    inside = tmp_path / "CHECKPOINT-17-BACKUP"
    inside.mkdir()
    monkeypatch.chdir(inside)
    with pytest.raises(ValueError, match="protected"):
        refuse_protected(Path("x.skp"))
    with pytest.raises(ValueError, match="protected"):
        refuse_protected(r"..\CHECKPOINT-17-BACKUP\y")


def test_an_ordinary_output_is_accepted(tmp_path):
    from engine.io.protected import refuse_protected
    assert refuse_protected(tmp_path / "results" / "x.json") is None
    assert refuse_protected(Path("data/campus/census.json")) is None


def test_error_export_uses_the_shared_guard():
    from engine.campus import error_export
    from engine.io import protected
    assert error_export.refuse_protected is protected.refuse_protected
    assert not hasattr(error_export, "_check_out")


def test_skp_check_refuses_an_output_in_the_export_folder_before_it_writes(tmp_path):
    from engine.campus import skp_check
    bad = _bad(tmp_path, EXPORT)
    with pytest.raises(ValueError, match="protected"):
        skp_check.check_source(tmp_path / "source.json", tmp_path / "backup", bad)
    assert not bad.exists()
    with pytest.raises(ValueError, match="protected"):
        skp_check.check_source(tmp_path / "source.json", tmp_path / "backup", tmp_path / "ok",
                               summary=_bad(tmp_path, EXPORT) / "s.md")
    assert not (tmp_path / "ok").exists()


def test_campus_skp_check_out_in_the_export_folder_is_refused(tmp_path, capsys):
    bad = _bad(tmp_path, EXPORT)
    assert cli.main(["campus-skp-check", "--backup", str(tmp_path / "b"), "--out", str(bad)]) == 2
    assert "protected" in capsys.readouterr().err
    assert not bad.exists()


@pytest.mark.parametrize("argv", [
    ["campus-skp-check", "--backup", "B", "--summary", "{bad}/s.md", "--out", "{ok}"],
    ["validate", "--before", "b", "--after", "a.obj", "--out", "{bad}"],
    ["census", "--out", "{bad}/census.json"],
    ["census", "--out", "{ok}/census.json", "--md", "{bad}/census.md"],
    ["census", "--out", "{ok}/census.json", "--errors-dir", "{bad}/errors"],
    ["campus-freeze", "--export", "E", "--backup", "B", "--out", "{bad}"],
    ["campus-freeze", "--export", "E", "--backup", "B", "--out", "{ok}", "--snapshots", "{bad}"],
    ["campus-index", "--out", "{bad}/group_index.json"],
    ["campus-materials", "--out", "{bad}/materials.json"],
    ["campus-inventory", "--out", "{bad}/map.json"],
    ["campus-inventory", "--out", "{ok}/map.json", "--md", "{bad}/map.md"],
    ["decide-pilot", "--out", "{bad}/jev_pilot.json"],
])
def test_every_writing_command_refuses_a_protected_output(argv, tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)                       # the default inputs do not exist here
    bad = _bad(tmp_path, "CHECKPOINT-17-BACKUP")
    args = [a.format(bad=bad, ok=tmp_path / "ok") for a in argv]
    assert cli.main(args) == 2
    assert "protected" in capsys.readouterr().err
    assert not bad.exists() and not (tmp_path / "ok").exists()


def test_the_functions_refuse_too_when_called_directly(tmp_path):
    from engine.campus.census import census
    from engine.campus.inventory import cmd_campus_inventory
    bad = _bad(tmp_path, EXPORT)
    with pytest.raises(ValueError, match="protected"):
        census(units=[], out_json=bad / "census.json")
    with pytest.raises(ValueError, match="protected"):
        cmd_campus_inventory(tmp_path / "s", tmp_path / "i", tmp_path / "m", bad / "m.json", tmp_path / "m.md")
    assert cli.cmd_validate(tmp_path / "b", tmp_path / "a.obj", tmp_path / "m.json", bad) == 2
    assert not bad.exists()


# ------------------------------------------- the older commands too (P1-H1b item 12)


@pytest.mark.parametrize("argv", [
    ["fix", "SNAP", "--out", "{bad}"],
    ["fix", "SNAP", "--out", "{ok}", "--skp-dir", "{bad}"],
    ["preview-data", "SNAP", "--out", "{bad}"],
    ["errors", "SNAP", "--out", "{bad}/errors.json"],
])
def test_fix_errors_and_preview_data_refuse_a_protected_output_before_they_read_anything(argv, tmp_path, capsys,
                                                                                         monkeypatch):
    monkeypatch.chdir(tmp_path)                       # SNAP does not exist: only the pre-check can answer
    bad = _bad(tmp_path, "CHECKPOINT-17-BACKUP")
    args = [a.format(bad=bad, ok=tmp_path / "ok") for a in argv]
    assert cli.main(args) == 2
    assert "protected" in capsys.readouterr().err
    assert not bad.exists() and not (tmp_path / "ok").exists()


def test_fix_with_an_ordinary_output_is_not_stopped_by_the_pre_check(tmp_path):
    args = cli.build_parser().parse_args(["fix", "SNAP", "--out", str(tmp_path / "o"), "--skp-dir", str(tmp_path / "s")])
    assert cli._refuse_protected_outputs(args) is None
    args = cli.build_parser().parse_args(["fix", "SNAP"])                    # the defaults are not protected
    assert cli._refuse_protected_outputs(args) is None
