"""Independent 2F attempt2 E3 proof caller; heavy phases require controller scheduling."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

JOB = "MAIN-INFRA-CLEAN-20261023"
REV = "7b2f7451b5723f724a1e074fdedc07dbcf7291d330ae550066f4926886136511"
COMPONENT = "531769cad83dd6d03214a94cbd21e0209f8f2f33"
ATTEMPT = "run-20261023-attempt2"
REVIEWER = "/root/main_infra_delivery_review"
RETAINED_1F = "e3_1f_retain_visible_20261024"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def check(path, expected):
    if not isinstance(expected, str) or len(expected) != 64 or digest(path) != expected:
        raise ValueError("Independent input hash mismatch: " + str(path))


def floor_size(floor_id, *, profile=None):
    if profile == RETAINED_1F and floor_id == '1F':
        return 15856
    if profile is not None:
        raise ValueError('Explicit matching floor validation profile required')
    if floor_id not in ('2F','3F'):
        raise ValueError('Explicit 2F or 3F validation profile required')
    return {'2F':56828,'3F':53602}[floor_id]


def require_qualification(proof, floor_id, *, profile=None):
    floor_size(floor_id, profile=profile)
    job_ok = proof.get('job_id') == JOB
    if floor_id == '1F' and 'job_id' not in proof:
        job_ok = True
    if (proof.get('qualified') is not True or proof.get('floor_id') != floor_id
            or not job_ok or proof.get('source_revision') != REV):
        raise ValueError('Independent original floor import qualification required')


def require_terminal(plan,worker,paths,hashes):
    if 'worker_terminal' not in paths or 'worker_phase_plan' not in paths:
        raise ValueError('Actual 3F worker terminal and phase plan required')
    terminal=read(paths['worker_terminal'])
    if (terminal.get('state')!='PROCESS_EXITED_ZERO' or terminal.get('phase')!='E3-3F-attempt2'
            or terminal.get('actual_pid')!=worker['pid']
            or terminal.get('actual_creation_utc')!=plan.get('worker_creation_utc')
            or not isinstance(plan.get('worker_creation_utc'),str)
            or terminal.get('actual_exit_code')!=0 or terminal.get('launcher_exit_code')!=0
            or terminal.get('abort_reason') is not None or terminal.get('all_owned_exited') is not True
            or terminal.get('HEAD')!=COMPONENT or terminal.get('acceptance') is not False
            or terminal.get('phase_plan_sha256')!=hashes['worker_phase_plan']):
        raise ValueError('Actual successful 3F owned terminal required')


def bind_identity(preparation, candidate, audit_sha256, worker_sha256, *, floor_id='2F'):
    original_triangles=floor_size(floor_id)
    preparation, candidate = Path(preparation).resolve(), Path(candidate).resolve()
    plan = read(preparation)
    if (plan.get("schema_version") != 1 or plan.get("job_id") != JOB or plan.get("floor_id") != floor_id
            or plan.get("source_revision") != REV or plan.get("attempt_namespace") != ATTEMPT
            or plan.get("builder_component_commit") != COMPONENT
            or candidate != Path(plan["candidate"]).resolve()
            or candidate.name != floor_id or candidate.parent.name != ATTEMPT):
        raise ValueError("Fresh floor attempt2 preparation identity required")
    worker_path, audit_path = Path(plan["worker"]).resolve(), candidate / "stage-audit.json"
    if worker_path != candidate.parent / f"worker-{floor_id}.json":
        raise ValueError("Fresh attempt2 worker path required")
    check(worker_path, worker_sha256)
    check(audit_path, audit_sha256)
    worker, audit = read(worker_path), read(audit_path)
    if (worker.get("state") != "candidate_saved" or worker.get("floor_id") != floor_id
            or type(worker.get("pid")) is not int or worker["pid"] != plan["worker_pid"]
            or worker.get("started_at") != plan["worker_started_at"]
            or Path(worker["candidate"]).resolve() != candidate
            or worker.get("builder_component_commit") != COMPONENT
            or worker.get("accepted") is not False or worker.get("input_triangles") != original_triangles):
        raise ValueError("Actual saved floor worker identity required")
    if (audit.get("builder_component_commit") != COMPONENT or audit.get("cleanup_mode") != "e3_remove_only"
            or audit.get("executed_stages") != ["E3"] or audit.get("input_triangles") != original_triangles
            or type(audit.get("output_triangles")) is not int
            or not 0 < audit["output_triangles"] <= original_triangles
            or audit["output_triangles"] != worker.get("output_triangles")
            or audit.get("accepted") is not False
            or audit.get("qualification_sha256") != plan["sha256"]["qualification"]
            or audit.get("materials_sha256") != plan["sha256"]["materials"]
            or audit.get("input_receipt", {}).get("floor_id") != floor_id
            or audit["input_receipt"].get("source_revision") != REV):
        raise ValueError("New sole-E3 stage audit differs")
    paths = {key: Path(value).resolve() for key, value in plan["paths"].items()}
    hashes = dict(plan["sha256"])
    if set(paths) != set(hashes):
        raise ValueError("Preparation input inventory differs")
    for key, path in paths.items():
        check(path, hashes[key])
    if floor_id=='3F':
        require_terminal(plan,worker,paths,hashes)
    snapshot = Path(audit["before_snapshot"]).resolve()
    if not snapshot.is_relative_to(Path(plan["before_snapshot_root"]).resolve()):
        raise ValueError("Fresh original BEFORE snapshot namespace required")
    snapshots = list(snapshot.glob("*.obj"))
    if len(snapshots) != 1:
        raise ValueError("Exactly one saved original BEFORE required")
    check(snapshots[0], hashes["engine_baseline"])
    paths.update(preparation=preparation, worker=worker_path, audit=audit_path, before=snapshots[0])
    hashes.update(preparation=digest(preparation), worker=worker_sha256, audit=audit_sha256,
                  before=hashes["engine_baseline"])
    for filename, key in [("candidate.engine.obj", "engine_candidate_sha256"),
                          ("candidate.source.obj", "source_candidate_sha256"),
                          ("source-faces.json", "source_faces_sha256"), ("edit-log.jsonl", "edit_log_sha256")]:
        paths[filename] = candidate / filename
        hashes[filename] = audit.get(key)
        check(paths[filename], hashes[filename])
    return dict(job_id=JOB, floor_id=floor_id, source_revision=REV, attempt_namespace=ATTEMPT,
                reviewer=REVIEWER, builder_component_commit=COMPONENT, worker_pid=worker["pid"],
                input_triangles=original_triangles, output_triangles=audit["output_triangles"],
                builder_guard_passed=audit.get("guard", {}).get("passed") is True,
                candidate=str(candidate), paths={k: str(v) for k,v in paths.items()}, hashes=hashes,
                before=str(snapshots[0]), after=str(candidate/"candidate.engine.obj"),
                before_sha256=hashes["engine_baseline"], after_sha256=hashes["candidate.engine.obj"],
                source_after_sha256=hashes["candidate.source.obj"], acceptance=False)


def recheck(receipt):
    for key, path in receipt["paths"].items():
        check(path, receipt["hashes"][key])


def load_meshes(receipt):
    floor_id=receipt['floor_id'];original_triangles=floor_size(floor_id)
    import numpy as np
    from dataclasses import replace
    from engine.io.minecraft_floor import Frame, parse_floor
    from engine.io.obj_reader import read_obj
    from engine.io.mtl import parse_mtl
    from engine.validate.checks import (load_looks, LookTable, face_look_ids, face_fingerprints,
                                       print_step, depth_tolerance, _rows_in)
    from tools.main_infra_e3_binding import bind_saved_e3
    from tools.main_infra_physical_validation import _same_mesh, _verify_assets
    p = {key: Path(value) for key,value in receipt["paths"].items()}
    candidate = Path(receipt["candidate"])
    proof, audit, native, provenance = (read(p[key]) for key in ["qualification", "audit", "reference", "provenance"])
    require_qualification(proof,floor_id,profile=receipt.get('validation_profile'))
    for field,key in [("source_obj_sha256","raw"),("native_reference_sha256","reference"),
                      ("source_triangles_sha256","source_baseline"),("engine_obj_sha256","engine_baseline")]:
        check(p[key], proof.get(field))
    if native.get("source_sha256") != proof["source_obj_sha256"] or native.get("unmatched_polygons") != 0:
        raise ValueError("Original floor native tessellation binding differs")
    source = parse_floor(p["raw"].read_text(encoding="utf-8"),
                         triangulations={int(k):v for k,v in native["polygons"].items()})
    frame = Frame(1000/25.4, provenance.get("frame_evidence", ""))
    if not np.array_equal(frame.matrix, np.asarray(provenance["source_to_engine"])):
        raise ValueError("Owner metre/block frame differs")
    expected = source.in_frame(frame).mesh
    before, after, source_after = (read_obj(p[key]) for key in ["before","candidate.engine.obj","candidate.source.obj"])
    _same_mesh(before, expected)
    _same_mesh(read_obj(p["source_baseline"]), source.mesh)
    if before.n_faces != original_triangles or after.n_faces != receipt["output_triangles"]:
        raise ValueError("Saved floor triangle counts differ")
    contract = bind_saved_e3(candidate=candidate, audit=audit, before_engine=expected,
                            after_engine=after, before_source=source.mesh, after_source=source_after)
    assets = _verify_assets(p["raw"], p["engine_baseline"].parent, candidate, p["before"].parent,
                            source.mesh, provenance, audit)
    for i, row in enumerate(provenance["assets"]):
        for label,root in [("raw",p["raw"].parent),("baseline",p["engine_baseline"].parent),("candidate",candidate)]:
            path = (root/row["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("Asset escapes its package")
            receipt["paths"][f"asset_{label}_{i}"] = str(path)
            receipt["hashes"][f"asset_{label}_{i}"] = row["sha256"]
    for path in p["before"].parent.rglob("*"):
        if path.is_file():
            key = "snapshot_" + path.relative_to(p["before"].parent).as_posix()
            receipt["paths"][key], receipt["hashes"][key] = str(path), digest(path)
    looks = load_looks(p["materials"], [(parse_mtl(p["before"].parent/"materials.mtl"),p["before"].parent),
                                      (parse_mtl(candidate/after.mtllib),candidate)])
    if looks.unknown(before) or looks.unknown(after):
        raise ValueError("Unqualified material names")
    before, after = (replace(mesh,physical_quanta=expected.physical_quanta) for mesh in [before,after])
    table=LookTable()
    lb,la=face_look_ids(before,looks,table),face_look_ids(after,looks,table)
    indices=np.asarray(read(p["source-faces.json"])["source_faces"],dtype=np.int64)
    drop=np.ones(before.n_faces,bool);drop[indices]=False
    masks=[];precision=[]
    for label,step in [("stored",print_step(before)),("physical",max(expected.physical_quanta))]:
        fb,fa=face_fingerprints(before,step,lb),face_fingerprints(after,step,la)
        missing,added=~_rows_in(fb,fa),~_rows_in(fa,fb)
        if not np.array_equal(fb[indices],fa) or np.any(missing&~drop) or added.any():
            raise ValueError("Appearance changes outside exact E3 survivors")
        masks.append(missing)
        precision.append(dict(grid=label,step_inches=step,depth_tolerance_inches=depth_tolerance(step)))
    if not np.array_equal(*masks) or precision[0]["depth_tolerance_inches"]!=precision[1]["depth_tolerance_inches"]:
        raise ValueError("Stored/physical numerical membership differs")
    receipt.update(contract=contract,assets=assets,precision=precision,
                   physical_axis_quanta_inches=list(expected.physical_quanta),
                   source_to_engine=frame.matrix.tolist(),pid=os.getpid())
    recheck(receipt)
    return source,before,after,looks,provenance


def require_guard(args, receipt):
    if not args.guard_receipt or not args.guard_sha256:
        raise ValueError("Actual independent guard receipt and external hash required")
    check(args.guard_receipt,args.guard_sha256)
    guard=read(args.guard_receipt)
    identity = ("job_id", "floor_id", "source_revision", "attempt_namespace", "reviewer",
                "builder_component_commit", "worker_pid", "input_triangles", "output_triangles",
                "before_sha256", "after_sha256", "source_after_sha256")
    if (any(guard.get(key) != receipt.get(key) for key in identity)
            or guard.get("guard",{}).get("passed") is not True
            or guard.get("views") != 26 or guard.get("resolution") != [900,600]
            or guard.get("hashes",{}).get("audit") != receipt["hashes"]["audit"]):
        raise ValueError("Independent guard is not bound to this 2F attempt2 candidate")
    recheck(guard)


def native_pose_inventory(poses,floor_id,*,profile=None):
    floor_size(floor_id,profile=profile)
    walking_class='qualified_walking' if floor_id=='1F' else 'actual_unchanged_qualified_walking_probe'
    walking=[p for p in poses if p.get('viewpoint_class')==walking_class]
    if len(walking)!=16:
        raise ValueError('Original qualified native walking cohort required')
    if floor_id=='2F':
        return dict(qualified_walking=len(walking))
    outside=[p for p in poses if p.get('name','').startswith('view_') and int(p['name'].rsplit('_',1)[1])>=0]
    if floor_id in ('1F','3F') and (len(poses)!=46 or len({p['name'] for p in poses})!=46
            or len(outside)!=17 or any(p.get('projection')!='ORTHO' for p in outside)
            or any(p.get('projection')!='PERSP' for p in walking)):
        raise ValueError('Original 3F native33qualified/13diagnostic cohort required')
    if floor_id=='1F' and any(p.get('headroom_clear') is not True
            or not 1.6 <= p.get('eye_height_above_floor_metres',0) < 1.601 for p in walking):
        raise ValueError('Original1F qualified walking camera height/clearance differs')
    return dict(qualified_walking=len(walking),qualified_outside=len(outside),diagnostic=len(poses)-len(walking)-len(outside))


def main(argv=None, *, floor_id="2F"):
    floor_size(floor_id)
    parser=argparse.ArgumentParser(description=__doc__.replace("2F",floor_id))
    parser.add_argument("phase",choices=["guard","validate","native-plan"])
    for name in ["preparation","candidate","out"]:
        parser.add_argument("--"+name,type=Path,required=True)
    for name in ["preparation-sha256","audit-sha256","worker-sha256"]:
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--guard-receipt",type=Path)
    parser.add_argument("--guard-sha256")
    args=parser.parse_args(argv)
    check(args.preparation,args.preparation_sha256)
    receipt=bind_identity(args.preparation,args.candidate,args.audit_sha256,args.worker_sha256,floor_id=floor_id)
    plan=read(args.preparation)
    out=args.out.resolve()
    if not out.is_relative_to(Path(plan["evidence_root"]).resolve()) or out.exists():
        raise ValueError("New owned independent evidence namespace required")
    if args.phase!="guard":
        require_guard(args,receipt)
    started=time.perf_counter()
    if args.phase=="native-plan":
        poses=read(receipt["paths"]["native_poses"])["poses"]
        native_pose_inventory(poses,floor_id)
        out.mkdir(parents=True)
        command=[plan["blender"],"--background","--factory-startup","--python-exit-code","13","--python",receipt["paths"]["native_renderer"],"--",
                 "--before",receipt["paths"]["source_baseline"],"--after",receipt["paths"]["candidate.source.obj"],
                 "--before-frame","source","--after-frame","source","--poses",receipt["paths"]["native_poses"],
                 "--out",str(out/"paired"),"--size","512"]
        recheck(receipt)
        write(out/"native-plan.json",dict(binding=receipt,command=command,poses=poses,render_launched=False,
             note="Fixed below-ground/cavity cameras remain diagnostic; qualified walking and above-horizon views assessed separately."))
        print(json.dumps(dict(native_plan=str(out/"native-plan.json"),render_launched=False)))
        return 0
    source,before,after,looks,provenance=load_meshes(receipt)
    out.mkdir(parents=True)
    write(out/"input-readback.json",receipt)
    if args.phase=="guard":
        from dataclasses import asdict,replace
        import numpy as np
        helper=Path(receipt["paths"]["strict_guard_helper"])
        spec=importlib.util.spec_from_file_location("independent_existing_strict_guard_2f",helper)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        names={name:i for i,name in enumerate(before.materials)}
        if not set(after.materials).issubset(names):
            raise ValueError("Guard material namespace differs")
        canonical=np.array([-1 if i<0 else names[after.materials[int(i)]] for i in after.face_material],dtype=np.int64)
        guarded_after=replace(after,face_material=canonical,materials=before.materials.copy())
        report,tol=module.strict_guard(before,guarded_after,source.mesh,provenance)
        recheck(receipt)
        receipt.update(guard=asdict(report),guard_depth_tol_inches=tol,views=26,resolution=[900,600],
                       wall_s=round(time.perf_counter()-started,3))
        write(out/"independent-guard.json",receipt)
        print(json.dumps(dict(guard_passed=report.passed,path=str(out/"independent-guard.json"))))
        return 0 if report.passed else 2
    from engine.validate.checks import validate,Settings,load_targets,default_targets_path
    from engine.validate.evidence import write_evidence
    if Path(default_targets_path()).resolve()!=Path(receipt["paths"]["signed_targets"]).resolve():
        raise ValueError("Signed default target path differs")
    targets=load_targets()
    if targets.get("signed") is not True:
        raise ValueError("Default signed targets required")
    result=validate(before,after,looks,targets=targets,settings=Settings(),
                    progress=lambda done,total:print(f"{done}/{total} samples cast",flush=True) if done==total else None)
    write_evidence(result,out)
    recheck(receipt);check(args.guard_receipt,args.guard_sha256)
    report=result.report
    report["inputs"]=dict(before=receipt["before"],after=receipt["after"],
         before_sha256=receipt["before_sha256"],after_sha256=receipt["after_sha256"],
         materials=receipt["paths"]["materials"],materials_sha256=receipt["hashes"]["materials"],
         targets=receipt["paths"]["signed_targets"],targets_sha256=receipt["hashes"]["signed_targets"])
    report["independent_cumulative_binding"]=receipt
    report["independent_guard_sha256"]=args.guard_sha256
    report["wall_s"]=round(time.perf_counter()-started,3)
    write(out/"validation.json",report)
    print(json.dumps(dict(verdict=report["verdict"],path=str(out/"validation.json"))))
    return 0 if result.passed else 2


if __name__=="__main__":
    raise SystemExit(main())
