"""Identity fixtures only: no geometry or validation pass is represented here."""
import json
from pathlib import Path

import pytest

from tools.main_infra_2f_validation import bind_identity, recheck

REV = "7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511"
COMMIT = "531769cad83dd6d03214a94cbd21e0209f8f2f33"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    from hashlib import sha256
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bound(tmp_path):
    candidate = tmp_path / "run-20261023-attempt2" / "2F"
    candidate.mkdir(parents=True)
    paths = {}
    for name in ["qualification", "materials", "engine_baseline", "source_baseline",
                 "raw", "reference", "provenance", "runtime", "signed_targets"]:
        paths[name] = tmp_path / (name + ".json")
        write(paths[name], {})
    for name in ["candidate.engine.obj", "candidate.source.obj", "source-faces.json", "edit-log.jsonl"]:
        (candidate / name).write_bytes(name.encode())
    snapshot = tmp_path / "run-20261023-attempt2" / "before-snapshots" / "2F" / "frozen"
    snapshot.mkdir(parents=True)
    (snapshot / "before.obj").write_bytes(paths["engine_baseline"].read_bytes())
    audit = dict(cleanup_mode="e3_remove_only", executed_stages=["E3"],
                 builder_component_commit=COMMIT, input_triangles=56828, output_triangles=40000,
                 qualification_sha256=digest(paths["qualification"]),
                 materials_sha256=digest(paths["materials"]), before_snapshot=str(snapshot),
                 input_receipt=dict(floor_id="2F", source_revision=REV),
                 guard=dict(passed=False, state="independent strict guard pending"),
                 accepted=False)
    for name, field in [("candidate.engine.obj", "engine_candidate_sha256"),
                        ("candidate.source.obj", "source_candidate_sha256"),
                        ("source-faces.json", "source_faces_sha256"), ("edit-log.jsonl", "edit_log_sha256")]:
        audit[field] = digest(candidate / name)
    write(candidate / "stage-audit.json", audit)
    worker = candidate.parent / "worker-2F.json"
    state = dict(pid=41648, floor_id="2F", state="candidate_saved", started_at="2026-10-23T14:13:13.144530+00:00",
                 candidate=str(candidate), accepted=False, input_triangles=56828,
                 output_triangles=40000, builder_component_commit=COMMIT)
    write(worker, state)
    plan = dict(schema_version=1, job_id="MAIN-INFRA-CLEAN-20261023", floor_id="2F",
                source_revision=REV, attempt_namespace="run-20261023-attempt2",
                builder_component_commit=COMMIT, worker_pid=41648,
                worker_started_at=state["started_at"], worker=str(worker), candidate=str(candidate),
                before_snapshot_root=str(snapshot.parent), paths={k: str(v) for k,v in paths.items()},
                sha256={k: digest(v) for k,v in paths.items()})
    preparation = tmp_path / "preparation.json"
    write(preparation, plan)
    return preparation, candidate, worker, audit, state, plan


def run(bound):
    preparation, candidate, worker, *_ = bound
    return bind_identity(preparation, candidate, digest(candidate/"stage-audit.json"), digest(worker))


def test_terminal_actual_attempt_is_bound_while_builder_guard_is_pending(bound):
    receipt = run(bound)
    assert receipt["floor_id"] == "2F"
    assert receipt["input_triangles"] == 56828
    assert receipt["output_triangles"] == 40000
    assert receipt["builder_guard_passed"] is False
    assert receipt["acceptance"] is False
    recheck(receipt)


@pytest.mark.parametrize("field,value", [
    ("state", "running_checked_E3"), ("floor_id", "1F"), ("pid", 41649),
    ("builder_component_commit", "old"), ("input_triangles", 15856),
    ("started_at", "old"), ("output_triangles", 39999), ("accepted", True)])
def test_wrong_or_nonterminal_worker_is_refused(bound, field, value):
    bound[4][field] = value
    write(bound[2], bound[4])
    with pytest.raises(ValueError):
        run(bound)


@pytest.mark.parametrize("field,value", [
    ("builder_component_commit", "old"), ("input_triangles", 15856),
    ("qualification_sha256", "0"*64), ("materials_sha256", "0"*64),
    ("executed_stages", ["E3", "E7"]), ("cleanup_mode", "exact_duplicates"),
    ("accepted", True)])
def test_foreign_stage_or_qualification_is_refused(bound, field, value):
    bound[3][field] = value
    write(bound[1]/"stage-audit.json", bound[3])
    with pytest.raises(ValueError):
        run(bound)


def test_foreign_before_snapshot_is_refused_even_with_same_bytes(bound):
    foreign = bound[1].parent.parent/"old-snapshot"
    foreign.mkdir()
    (foreign/"before.obj").write_bytes(b"{}")
    bound[3]["before_snapshot"] = str(foreign)
    write(bound[1]/"stage-audit.json", bound[3])
    with pytest.raises(ValueError):
        run(bound)


@pytest.mark.parametrize("name", ["candidate.engine.obj", "candidate.source.obj", "source-faces.json", "edit-log.jsonl"])
def test_saved_artifact_tampering_is_refused(bound, name):
    (bound[1]/name).write_bytes(b"changed")
    with pytest.raises(ValueError):
        run(bound)


def test_post_readback_tampering_is_refused(bound):
    receipt = run(bound)
    Path(bound[5]["paths"]["materials"]).write_bytes(b"changed")
    with pytest.raises(ValueError):
        recheck(receipt)


def native_args(bound, tmp_path):
    preparation,candidate,worker,_audit,_state,plan=bound
    poses=tmp_path/"poses.json"
    write(poses,dict(poses=[dict(name=f"walking_{i}",viewpoint_class="actual_unchanged_qualified_walking_probe")
                           for i in range(16)]))
    plan["paths"]["native_poses"]=str(poses)
    plan["sha256"]["native_poses"]=digest(poses)
    plan["paths"]["native_renderer"]=str(tmp_path/"renderer.py")
    Path(plan["paths"]["native_renderer"]).write_bytes(b"raise RuntimeError('must never run')")
    plan["sha256"]["native_renderer"]=digest(Path(plan["paths"]["native_renderer"]))
    plan["evidence_root"]=str(tmp_path/"evidence")
    plan["blender"]=str(tmp_path/"never-execute-blender.exe")
    write(preparation,plan)
    binding=run(bound)
    guard=tmp_path/"guard.json"
    write(guard,dict(binding,guard=dict(passed=True),views=26,resolution=[900,600]))
    out=tmp_path/"evidence"/"native"
    args=["native-plan","--preparation",str(preparation),"--preparation-sha256",digest(preparation),
          "--candidate",str(candidate),"--audit-sha256",digest(candidate/"stage-audit.json"),
          "--worker-sha256",digest(worker),"--guard-receipt",str(guard),"--guard-sha256",digest(guard),
          "--out",str(out)]
    return args,out,guard


def test_native_plan_preserves_blender_failure_exit_and_launches_nothing(bound, tmp_path):
    from tools.main_infra_2f_validation import main
    args,out,_guard=native_args(bound,tmp_path)
    assert main(args)==0
    report=json.loads((out/"native-plan.json").read_text())
    command=report["command"]
    assert command[command.index("--python-exit-code")+1]=="13"
    assert command[command.index("--before-frame")+1]=="source"
    assert command[command.index("--after-frame")+1]=="source"
    assert report["render_launched"] is False


def test_native_plan_rechecks_assets_bound_by_the_actual_guard(bound,tmp_path):
    from tools.main_infra_2f_validation import main
    args,_out,guard=native_args(bound,tmp_path)
    data=json.loads(guard.read_text())
    texture=tmp_path/"guard-only-texture.png"
    texture.write_bytes(b"original bytes")
    data["paths"]["candidate_texture"]=str(texture)
    data["hashes"]["candidate_texture"]=digest(texture)
    write(guard,data)
    args[args.index("--guard-sha256")+1]=digest(guard)
    texture.write_bytes(b"changed since independent guard")
    with pytest.raises(ValueError):
        main(args)


@pytest.mark.parametrize("field,value", [
    ("source_revision","0"*64),("input_triangles",15856),("output_triangles",39999),
    ("views",1),("resolution",[90,60]),("worker_pid",41649)])
def test_native_plan_refuses_a_foreign_or_weaker_guard(bound,tmp_path,field,value):
    from tools.main_infra_2f_validation import main
    args,_out,guard=native_args(bound,tmp_path)
    data=json.loads(guard.read_text());data[field]=value;write(guard,data)
    args[args.index("--guard-sha256")+1]=digest(guard)
    with pytest.raises(ValueError):
        main(args)
