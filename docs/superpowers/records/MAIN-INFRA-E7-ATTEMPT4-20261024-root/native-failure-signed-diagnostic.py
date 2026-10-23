"""One-off unmodified signed diagnosis retaining failed native evidence; never publishable."""
from dataclasses import asdict
import hashlib,json,subprocess,time,traceback
from pathlib import Path
from tools import main_infra_e7_independent_attempt4 as caller
from engine.validate.checks import Settings,default_targets_path,load_targets,validate
from engine.validate.evidence import write_evidence
ROOT=Path(__file__).resolve().parents[2]
PROOF=ROOT/'data/main-infra-1f-validation/run-20261024-attempt4/1F'
OUT=PROOF/'native-failure-diagnostic'
PREPARED=PROOF/'prepared-inputs.json'
GUARD=PROOF/'guard/independent-guard.json'
NATIVE=PROOF/'native/native-readback.json'
PREPARED_SHA='4e80ed648780216562bd6ee746fe78d5b8efca009ec84b0a5c76a6a8c1e52d9b'
GUARD_SHA='53f54fc443971474afb7d67c82dc637fb45ad937cc9a97131ef1ea2c16902030'
NATIVE_SHA='eed21d6471660e612cf4b861fff15a08acc3e43b8885b7d16fdd19f20759d049'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    if subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()!='a50226737ac155f4f7a303e3c2afe48abd45c29d':
        raise ValueError('frozen diagnostic code differs')
    subprocess.run(['git','-C',str(ROOT),'diff','--exit-code','33606ce9','--','engine/guard','engine/validate','engine/fixes/pipeline.py'],check=True)
    caller.check(ROOT/'tools/main_infra_e7_independent_attempt4.py','8d1210feaf846d323083fd65864167014b838ca2e525096eedeb3d188ad77a39')
    source,before,after,looks,provenance,inputs=caller.load_prepared(PREPARED,PREPARED_SHA,PROOF)
    if before.n_faces!=15856 or after.n_faces!=10393 or inputs['stage_input_triangles']!=10136:
        raise ValueError('cumulative diagnostic input counts differ')
    caller.require_bound_proof(GUARD,GUARD_SHA,inputs,'guard')
    caller.check(NATIVE,NATIVE_SHA);native=caller.read(NATIVE);caller.recheck(native)
    identity=('job_id','floor_id','source_revision','variant','engine_run_id','attempt_namespace','original_source_triangles','stage_input_triangles','output_triangles','preparation_sha256','checkpoint_sha256','cut_receipt_sha256','run_receipt_sha256','asset_receipt_sha256','before_sha256','after_sha256','source_after_sha256','native_policy_sha256','policy_counts','policy_excluded_sites','native_policy_excluded_sites','signed_policy_excluded_sites')
    if (any(native.get(k)!=inputs[k] for k in identity)
            or any(native['paths'].get(k)!=v or native['hashes'].get(k)!=inputs['hashes'][k] for k,v in inputs['paths'].items())
            or native.get('before_source_role')!='qualified_baseline'
            or native.get('before_source_sha256')!=inputs['hashes']['baseline_source']
            or native.get('guard_receipt_sha256')!=GUARD_SHA
            or native.get('qualified_owner_views',{}).get('passed') is not False):
        raise ValueError('actual failed native record identity differs')
    caller.check(default_targets_path(),caller.TARGETS_SHA)
    targets=load_targets()
    if targets.get('signed') is not True:raise ValueError('signed default targets required')
    if OUT.name!='native-failure-diagnostic' or OUT.parent!=PROOF or OUT.exists():
        raise ValueError('exclusive noncanonical diagnostic namespace required')
    OUT.mkdir();started=time.time()
    context=dict(diagnostic_only=True,publication_eligible=False,not_publishable=True,acceptance=False,floor_accepted=False,
        native_preservation_passed=False,native_failure_retained=dict(path=str(NATIVE),sha256=NATIVE_SHA),
        purpose='Unmodified signed owner-rule diagnosis; failed native prerequisite remains blocking',
        signed_base='33606ce9',validator_component_commit='a50226737ac155f4f7a303e3c2afe48abd45c29d',
        default_settings=asdict(Settings()),input_binding=inputs)
    caller.write(OUT/'invocation.json',context)
    shown={'tenth':-1}
    def progress(done,total):
        tenth=int(10*done/max(total,1))
        if tenth!=shown['tenth']:
            shown['tenth']=tenth;print(f'{done}/{total} samples cast',flush=True)
    try:
        result=validate(before,after,looks,targets=targets,settings=Settings(),progress=progress)
        write_evidence(result,OUT)
        caller.recheck(inputs);caller.require_bound_proof(GUARD,GUARD_SHA,inputs,'guard')
        caller.check(NATIVE,NATIVE_SHA);caller.recheck(native)
        report=result.report
        report['inputs']=dict(before=inputs['before'],after=inputs['after'],before_sha256=sha(inputs['before']),after_sha256=sha(inputs['after']),materials=inputs['paths']['materials'],materials_sha256=inputs['hashes']['materials'],targets=str(default_targets_path()),targets_sha256=caller.TARGETS_SHA)
        report['diagnostic_context']=context
        caller.write(OUT/'validation.json',report)
        receipt=dict(context,verdict=report['verdict'],validation_json_sha256=sha(OUT/'validation.json'),
            post_validation_input_hashes=dict(before=sha(inputs['before']),after=sha(inputs['after']),matches_report=True),
            wall_s=time.time()-started,no_canonical_validation_or_independent_review_created=True)
        caller.write(OUT/'diagnostic-receipt.json',receipt)
        print(json.dumps(dict(diagnostic_only=True,publication_eligible=False,verdict=report['verdict'],report=str(OUT/'validation.json'),sha256=sha(OUT/'validation.json'))),flush=True)
        return 0 if result.passed else 2
    except Exception:
        (OUT/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8');raise
if __name__=='__main__':raise SystemExit(main())