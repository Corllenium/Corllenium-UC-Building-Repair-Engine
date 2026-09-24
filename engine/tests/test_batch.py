import json
from pathlib import Path

from engine.batch import BatchItem, discover_items, object_name, run_batch
from engine.io.obj_writer import write_obj
from engine.tests.fixtures.build import box_with_partition


def _fake_snapshot(root, name):
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.obj").write_text(f"o {name}\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    return d


def test_object_name_is_the_objs_o_line(tmp_path):
    d = tmp_path / "abc"
    d.mkdir()
    (d / "file_stem.obj").write_text("# c\nmtllib x.mtl\no Chtm_2nd_floor\nv 0 0 0\n", encoding="utf-8")
    assert object_name(d) == "Chtm_2nd_floor"


def test_run_batch_records_state_and_resumes(tmp_path):
    items = [BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj")),
             BatchItem("B", _fake_snapshot(tmp_path / "snap", "b_obj"))]
    out_root = tmp_path / "out"
    calls = []

    def runner(snapshot_dir, out_root_, profile_path):
        name = snapshot_dir.name
        calls.append(name)
        d = out_root_ / name
        d.mkdir(parents=True, exist_ok=True)
        code = 0 if name == "a_obj" else 2
        (d / "report.json").write_text(json.dumps({"passed": code == 0}), encoding="utf-8")
        return code

    results = run_batch(items, out_root, jobs=2, runner=runner)
    assert {r.canonical: (r.exit_code, r.passed) for r in results} == {"A": (0, True), "B": (2, False)}
    state = json.loads((out_root / "batch_state.json").read_text(encoding="utf-8"))
    assert state["schema"] == "corllenium.batch/1"
    assert state["objects"]["A"]["out_dir"] == str(out_root / "a_obj")
    assert sorted(calls) == ["a_obj", "b_obj"]

    calls.clear()
    again = run_batch(items, out_root, jobs=1, runner=runner)   # resume: only the failure re-runs
    assert calls == ["b_obj"] and {r.canonical for r in again} == {"A", "B"}

    calls.clear()
    run_batch(items, out_root, jobs=1, runner=runner, resume=False)
    assert sorted(calls) == ["a_obj", "b_obj"]


def test_discover_items_reads_the_ingest_manifest(tmp_path):
    root = tmp_path / "snapshots"
    (root / "CHTM").mkdir(parents=True)
    rows = [{"canonical": "CHTM_a", "status": "ok", "snapshot_dir": str(root / "CHTM" / "CHTM_a" / "abc")},
            {"canonical": "CHTM_b", "status": "missing", "snapshot_dir": None},
            {"canonical": "CHTM_c", "status": "unlisted", "snapshot_dir": str(root / "CHTM" / "CHTM_c" / "def")},
            {"canonical": "CHTM_d", "status": "manifest_mismatch", "snapshot_dir": None}]
    (root / "CHTM" / "ingest_manifest.json").write_text(
        json.dumps({"schema": "corllenium.ingest/1", "building": "CHTM", "rows": rows}), encoding="utf-8")
    items = discover_items(root, "CHTM")
    assert [(i.canonical, i.snapshot_dir.name) for i in items] == [("CHTM_a", "abc"), ("CHTM_c", "def")]


def test_run_batch_drives_the_real_cli_in_a_subprocess(tmp_path):
    """One real `python -m engine.cli fix` child on the smallest fixture with the fast profile."""
    m = box_with_partition()
    snap = tmp_path / "snap"
    snap.mkdir()
    write_obj(m, snap / f"{m.name}.obj")
    (snap / "materials.mtl").write_text(
        "".join(f"newmtl {mat}\nKd 0.8 0.8 0.8\n\n" for mat in m.materials), encoding="utf-8")
    profile = tmp_path / "fast.json"
    profile.write_text(json.dumps({"guard_size": [120, 80], "n_dirs": 32, "qa_size": [160, 100]}),
                       encoding="utf-8")
    out_root = tmp_path / "out"

    results = run_batch([BatchItem("BOX", snap)], out_root, jobs=1, profile_path=profile)

    assert results[0].exit_code == 0 and results[0].passed is True
    assert results[0].out_dir == str(out_root / m.name)
    assert (out_root / m.name / f"{m.name}.fixed.obj").exists()
    assert (out_root / m.name / "report.json").exists()


def test_run_batch_records_a_runner_exception_as_a_failed_result_and_continues(tmp_path):
    items = [BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj")),
             BatchItem("B", _fake_snapshot(tmp_path / "snap", "b_obj"))]
    out_root = tmp_path / "out"

    def runner(snapshot_dir, out_root_, profile_path):
        if snapshot_dir.name == "a_obj":
            raise FileNotFoundError("python.exe vanished")
        d = out_root_ / snapshot_dir.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
        return 0

    results = run_batch(items, out_root, jobs=2, runner=runner)
    by = {r.canonical: r for r in results}
    assert by["A"].exit_code == -1 and by["A"].passed is False
    assert by["A"].error.startswith("FileNotFoundError: python.exe vanished")
    assert by["B"].exit_code == 0 and by["B"].passed is True and by["B"].error == ""
    state = json.loads((out_root / "batch_state.json").read_text(encoding="utf-8"))
    assert state["objects"]["A"]["exit_code"] == -1 and "vanished" in state["objects"]["A"]["error"]
    # a failed item is re-run on resume, a passed one is not
    calls = []

    def counting_runner(snapshot_dir, out_root_, profile_path):
        calls.append(snapshot_dir.name)
        return runner(snapshot_dir, out_root_, profile_path)

    run_batch(items, out_root, jobs=1, runner=counting_runner)
    assert calls == ["a_obj"]


def test_run_batch_records_a_malformed_report_as_a_failed_result(tmp_path):
    items = [BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj"))]
    out_root = tmp_path / "out"

    def runner(snapshot_dir, out_root_, profile_path):
        d = out_root_ / snapshot_dir.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text("{not json", encoding="utf-8")
        return 0

    (res,) = run_batch(items, out_root, jobs=1, runner=runner)
    assert res.exit_code == -1 and res.passed is False and "JSONDecodeError" in res.error
