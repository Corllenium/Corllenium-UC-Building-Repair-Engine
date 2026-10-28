"""Job P1-K3b item 4: `engine.cli fix --kernel --validate-sites`.

The legacy stages are checked and logged, never rolled back (ruling K3-R2), so the run writes the very files the
kernel run writes, plus one `{"check": ...}` line per stage in `edit_log.jsonl`. Without `--validate-sites` nothing
changes (the K2 tests in test_kernel_observe.py hold that).
"""
import json

import pytest

from engine import cli
from engine.fixes.pipeline import FixProfile
from engine.repair.engines.legacy import STAGE_ENGINES
from engine.tests.fixtures.build import box_with_partition

_CLI = FixProfile(guard_size=(120, 80), n_dirs=32, qa_size=(160, 100))


def test_build_parser_fix_validate_sites_defaults_off_and_names_a_materials_file():
    args = cli.build_parser().parse_args(["fix", "somedir"])
    assert args.validate_sites is False and str(args.materials).replace("\\", "/") == "data/campus/materials.json"
    args = cli.build_parser().parse_args(["fix", "somedir", "--kernel", "--validate-sites", "--materials", "m.json"])
    assert args.validate_sites is True and str(args.materials) == "m.json"


def test_main_passes_validate_sites_and_the_materials_to_cmd_fix(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_fix", lambda *a, **k: calls.append(
        (k["kernel"], k["validate_sites"], str(k["materials"]))) or 0)
    assert cli.main(["fix", "snapdir", "--kernel", "--validate-sites", "--materials", "m.json"]) == 0
    assert cli.main(["fix", "snapdir"]) == 0
    assert calls[0] == (True, True, "m.json") and calls[1][:2] == (False, False)


def test_validate_sites_without_the_kernel_is_refused(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["fix", "snapdir", "--validate-sites"])
    assert stop.value.code == 2 and "--validate-sites needs --kernel" in capsys.readouterr().err


def test_cmd_fix_validate_sites_writes_the_kernels_files_and_a_check_line_per_stage(tmp_path):
    from engine.tests.test_cli import _write_snapshot
    mesh = box_with_partition()
    snap = _write_snapshot(tmp_path, mesh)
    materials = tmp_path / "materials.json"
    materials.write_text(json.dumps({"materials": {}}), encoding="utf-8")
    kernel_root, checked_root = tmp_path / "kernel", tmp_path / "checked"

    code_kernel = cli.cmd_fix(snap, kernel_root, accept_slit=False, profile=_CLI, skp=False, kernel=True)
    code_checked = cli.cmd_fix(snap, checked_root, accept_slit=False, profile=_CLI, skp=False, kernel=True,
                               validate_sites=True, materials=materials)

    kernel, checked = kernel_root / mesh.name, checked_root / mesh.name
    assert code_kernel == code_checked
    assert (kernel / "report.json").read_bytes() == (checked / "report.json").read_bytes()
    for name in (f"{mesh.name}.fixed.obj", f"{mesh.name}.fixed.ngon.obj"):
        assert (kernel / name).read_bytes() == (checked / name).read_bytes()
    plain = [json.loads(line) for line in (kernel / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    lines = [json.loads(line) for line in (checked / "edit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [line for line in lines if "check" not in line] == plain, "the edit lines are the kernel's, none rolled back"
    checks = [line["check"] for line in lines if "check" in line]
    assert [c["stage"] for c in checks] == [s for s, _ in STAGE_ENGINES]
    assert all(c["legacy"] is True and c["rolled_back"] == [] for c in checks)
    assert str(tmp_path) not in (checked / "edit_log.jsonl").read_text(encoding="utf-8")
