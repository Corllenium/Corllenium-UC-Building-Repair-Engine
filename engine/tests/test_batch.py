import json
import os
from pathlib import Path

import pytest

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


def test_object_name_falls_back_to_the_objs_g_line_like_read_obj_does(tmp_path):
    """A4: `object_name` must use `read_obj`'s own naming rule (the same one `cmd_fix` uses),
    not a separate hand parser that only understood `o ` lines -- `read_obj` also accepts a `g`
    line when there is no `o` line, which the old hand parser fell through to the file stem for."""
    d = tmp_path / "abc"
    d.mkdir()
    (d / "file_stem.obj").write_text("# c\nmtllib x.mtl\ng Chtm_2nd_floor\nv 0 0 0\n", encoding="utf-8")
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
    # A8: the exception came from PARSING the report, after the runner returned a real exit
    # code (0) -- that code must survive, not be overwritten with the runner-raised sentinel -1.
    assert res.exit_code == 0 and res.passed is False and "JSONDecodeError" in res.error


# ---------------------------------------------------------------------------------------------
# A6: `engine.io.atomic.atomic_write_text` -- write-then-`os.replace`, retrying briefly on the
# `PermissionError` Windows raises when another process has the destination open for read.
# ---------------------------------------------------------------------------------------------

def test_atomic_write_text_retries_on_permission_error_then_succeeds(tmp_path, monkeypatch):
    from engine.io import atomic as atomic_mod
    dest = tmp_path / "state.json"
    dest.write_text("old", encoding="utf-8")
    calls = {"n": 0}
    real_replace = os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("still open for read")
        return real_replace(src, dst)

    monkeypatch.setattr(atomic_mod.os, "replace", flaky_replace)
    sleeps = []
    atomic_mod.atomic_write_text(dest, "new", sleep=sleeps.append)

    assert dest.read_text(encoding="utf-8") == "new"
    assert calls["n"] == 3
    assert sleeps == [0.2, 0.2]
    assert not dest.with_suffix(".json.tmp").exists()


def test_atomic_write_text_gives_up_after_five_permission_errors(tmp_path, monkeypatch):
    from engine.io import atomic as atomic_mod
    dest = tmp_path / "state.json"
    dest.write_text("old", encoding="utf-8")

    def always_locked(src, dst):
        raise PermissionError("locked forever")

    monkeypatch.setattr(atomic_mod.os, "replace", always_locked)
    sleeps = []
    with pytest.raises(PermissionError):
        atomic_mod.atomic_write_text(dest, "new", sleep=sleeps.append)

    assert dest.read_text(encoding="utf-8") == "old"      # destination untouched
    assert sleeps == [0.2, 0.2, 0.2, 0.2]                  # 5 attempts, 4 sleeps between them


# ---------------------------------------------------------------------------------------------
# A1: a crashed child (non-zero exit, or no report at all) must never be reported PASS just
# because an earlier good run's report.json is still sitting in the output folder.
# ---------------------------------------------------------------------------------------------

def test_a_crashed_child_is_never_reported_as_passed_from_a_stale_report(tmp_path):
    item = BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj"))
    out_root = tmp_path / "out"
    out_dir = out_root / "a_obj"
    out_dir.mkdir(parents=True)
    (out_dir / "report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")

    def runner(snapshot_dir, out_root_, profile_path):
        # A1: the stale report must be gone BEFORE the runner is even invoked.
        assert not (out_root_ / snapshot_dir.name / "report.json").exists()
        return 1   # crashed, wrote nothing

    (res,) = run_batch([item], out_root, jobs=1, runner=runner)
    assert res.passed is False and res.exit_code == 1


# ---------------------------------------------------------------------------------------------
# A2: resume must know WHAT was fixed, not just that something with this canonical once passed --
# a different snapshot_dir or a different profile makes a recorded PASS stale.
# ---------------------------------------------------------------------------------------------

def test_resume_reruns_when_the_snapshot_dir_or_profile_content_changed(tmp_path):
    out_root = tmp_path / "out"
    calls = []

    def runner(snapshot_dir, out_root_, profile_path):
        calls.append(str(snapshot_dir))
        d = out_root_ / snapshot_dir.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
        return 0

    dir_a = _fake_snapshot(tmp_path / "snap", "a_obj")
    dir_b = _fake_snapshot(tmp_path / "snap2", "a_obj")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"n_dirs": 8}), encoding="utf-8")

    run_batch([BatchItem("A", dir_a)], out_root, jobs=1, profile_path=profile, runner=runner)
    assert calls == [str(dir_a)]

    calls.clear()   # a different snapshot_dir, same canonical, same profile -> must re-run
    run_batch([BatchItem("A", dir_b)], out_root, jobs=1, profile_path=profile, runner=runner)
    assert calls == [str(dir_b)]

    calls.clear()   # same dir, but the profile file's CONTENT changed -> must re-run
    profile.write_text(json.dumps({"n_dirs": 16}), encoding="utf-8")
    run_batch([BatchItem("A", dir_b)], out_root, jobs=1, profile_path=profile, runner=runner)
    assert calls == [str(dir_b)]

    calls.clear()   # identical dir + identical (already-changed) profile content -> must NOT re-run
    run_batch([BatchItem("A", dir_b)], out_root, jobs=1, profile_path=profile, runner=runner)
    assert calls == []


def test_resume_ignores_a_recorded_entry_missing_the_new_tracking_keys(tmp_path):
    """A record saved by an older engine (before A2) has no `snapshot_dir`/`profile_sha256` keys
    at all -- it must be treated as stale and re-run, not crash and not be trusted blindly."""
    item = BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj"))
    out_root = tmp_path / "out"
    out_root.mkdir()
    old_record = {"canonical": "A", "exit_code": 0, "out_dir": str(out_root / "a_obj"),
                 "passed": True, "started": "t0", "finished": "t1", "error": ""}
    (out_root / "batch_state.json").write_text(
        json.dumps({"schema": "corllenium.batch/1", "objects": {"A": old_record}}), encoding="utf-8")

    calls = []

    def runner(snapshot_dir, out_root_, profile_path):
        calls.append(snapshot_dir.name)
        d = out_root_ / snapshot_dir.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
        return 0

    run_batch([item], out_root, jobs=1, runner=runner)
    assert calls == ["a_obj"]


# ---------------------------------------------------------------------------------------------
# A3: relative snapshot_dir/out_root/profile_path must not depend on the caller's cwd --
# `run_fix_subprocess` needs absolute paths since it always runs with `cwd=REPO_ROOT`.
# ---------------------------------------------------------------------------------------------

def test_run_batch_resolves_relative_paths_before_use(tmp_path, monkeypatch):
    m = box_with_partition()
    snap = tmp_path / "snap"
    snap.mkdir()
    write_obj(m, snap / f"{m.name}.obj")
    (snap / "materials.mtl").write_text(
        "".join(f"newmtl {mat}\nKd 0.8 0.8 0.8\n\n" for mat in m.materials), encoding="utf-8")
    profile = tmp_path / "fast.json"
    profile.write_text(json.dumps({"guard_size": [120, 80], "n_dirs": 32, "qa_size": [160, 100]}),
                       encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    results = run_batch([BatchItem("BOX", Path("snap"))], "out", jobs=1, profile_path=Path("fast.json"))

    assert results[0].exit_code == 0 and results[0].passed is True
    out_root_abs = (tmp_path / "out").resolve()
    assert results[0].out_dir == str(out_root_abs / m.name)
    assert Path(results[0].snapshot_dir).is_absolute()
    assert results[0].snapshot_dir == str(snap.resolve())


# ---------------------------------------------------------------------------------------------
# A5: refuse duplicate output names or duplicate canonicals up front -- nothing runs, no state
# gets written, so a batch never partially clobbers one output folder with two objects.
# ---------------------------------------------------------------------------------------------

def test_run_batch_refuses_two_items_that_share_an_output_name(tmp_path):
    items = [BatchItem("A", _fake_snapshot(tmp_path / "snap", "same_obj")),
             BatchItem("B", _fake_snapshot(tmp_path / "snap2", "same_obj"))]
    out_root = tmp_path / "out"

    with pytest.raises(ValueError, match="same_obj"):
        run_batch(items, out_root, jobs=1, runner=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not run")))
    assert not (out_root / "batch_state.json").exists()


def test_run_batch_refuses_two_items_that_share_a_canonical(tmp_path):
    items = [BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj")),
             BatchItem("A", _fake_snapshot(tmp_path / "snap2", "b_obj"))]
    out_root = tmp_path / "out"

    with pytest.raises(ValueError, match="A"):
        run_batch(items, out_root, jobs=1, runner=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not run")))
    assert not (out_root / "batch_state.json").exists()


# ---------------------------------------------------------------------------------------------
# A6 (integration): the state file is schema-checked on load, and an unknown key in a saved
# record (from a newer engine) is dropped rather than crashing an older one.
# ---------------------------------------------------------------------------------------------

def test_run_batch_rejects_a_state_file_with_the_wrong_schema(tmp_path):
    item = BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj"))
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "batch_state.json").write_text(json.dumps({"schema": "other/1", "objects": {}}),
                                                encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        run_batch([item], out_root, jobs=1, runner=lambda *a, **k: 0)


def test_run_batch_tolerates_an_unknown_key_in_a_saved_record(tmp_path):
    item = BatchItem("A", _fake_snapshot(tmp_path / "snap", "a_obj"))
    out_root = tmp_path / "out"
    out_root.mkdir()
    rec = {"canonical": "A", "exit_code": 0, "out_dir": str(out_root / "a_obj"), "passed": True,
          "started": "t0", "finished": "t1", "error": "",
          "snapshot_dir": str((tmp_path / "snap" / "a_obj").resolve()), "profile_sha256": "",
          "totally_new_field_from_the_future": 123}
    (out_root / "batch_state.json").write_text(
        json.dumps({"schema": "corllenium.batch/1", "objects": {"A": rec}}), encoding="utf-8")

    def runner(*a, **k):
        raise AssertionError("must not re-run an already-passed, unknown-key-tolerant record")

    results = run_batch([item], out_root, jobs=1, runner=runner)
    assert results[0].canonical == "A" and results[0].passed is True


# ---------------------------------------------------------------------------------------------
# A7: Ctrl-C (KeyboardInterrupt from a runner) must stop the batch, not let the executor's
# default shutdown drain every already-queued item to completion first.
# ---------------------------------------------------------------------------------------------

def test_keyboard_interrupt_stops_the_batch_instead_of_draining_the_queue(tmp_path):
    items = [BatchItem(c, _fake_snapshot(tmp_path / "snap", n))
            for c, n in (("A", "a_obj"), ("B", "b_obj"), ("C", "c_obj"))]
    out_root = tmp_path / "out"
    calls = []

    def runner(snapshot_dir, out_root_, profile_path):
        calls.append(snapshot_dir.name)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run_batch(items, out_root, jobs=1, runner=runner)
    assert calls == ["a_obj"]


# ---------------------------------------------------------------------------------------------
# A8: honest values on the exception path -- `out_dir=""` only when it truly was never known,
# and the child's real exit code is kept (not overwritten with -1) once it is known.
# ---------------------------------------------------------------------------------------------

def test_exception_path_records_out_dir_empty_when_never_known(tmp_path):
    item = BatchItem("A", tmp_path / "does_not_exist")   # object_name() itself will raise
    out_root = tmp_path / "out"

    (res,) = run_batch([item], out_root, jobs=1, runner=lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not run: object_name should have failed first")))
    assert res.out_dir == "" and res.exit_code == -1 and res.passed is False
