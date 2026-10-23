$ErrorActionPreference='Stop'
$taskRoot='D:/PROJECTS/UC MODEL FIXER'
$taskRun="$taskRoot/.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023"
$taskExpected=@{'2F'=@{pid=53936;start='2026-10-23T10:56:51.4928018Z'};'3F'=@{pid=56832;start='2026-10-23T10:57:36.6381631Z'}}
$env:TEMP="$taskRoot/data/tmp"
$env:TMP=$env:TEMP
$env:PYTHONPATH="$taskRoot/.claude/worktrees/MAIN-INFRA-CLEAN-20261023"
$taskPython=@'
import sys
sys.path.insert(0,'D:/PROJECTS/UC MODEL FIXER/.claude/worktrees/MAIN-INFRA-CLEAN-20261023')
from pathlib import Path
import json,os
from tools.main_infra_progress import load_progress,write_progress,utc_now
root=Path('D:/PROJECTS/UC MODEL FIXER')
path=root/'data/main-infra-fresh/current.json'
doc=load_progress(path)
now=utc_now()
observations=json.loads(os.environ['UC_MODEL_WORKER_OBSERVATIONS'])
run=root/'.claude/worktrees/MAIN-INFRA-E3-20261023/data/main-infra-e3/run-20261023'
running=[]
for floor in ('2F','3F'):
    if floor not in observations:
        continue
    process=observations[floor]
    state=json.loads(Path(process['worker_path']).read_text())
    row=doc['floors'][floor]
    if process['alive'] and state['state'] in ('running_checked_E3','loading_qualified_input'):
        desired='cleaning';step='Checked E3 engine running; default preservation checks and unsafe-site rollback' if state['state']=='running_checked_E3' else 'Loading hash-bound qualified fresh source for checked E3';running.append(floor)
    elif state['state']=='candidate_saved':
        desired='validating';step='E3 candidate saved; independent guard, native views and signed validation pending'
        row['pending_output_triangles']=state['output_triangles']
    else:
        desired='failed';step='Engine worker stopped: '+state.get('error',state['state'])
    if row['state']!=desired:
        row['last_work_event_at']=now
        doc['last_work_event_at']=now
    row.update(state=desired,step=step,worker_pid=state['pid'],worker_alive=process['alive'],worker_observed_at=now,worker_cpu_seconds=process.get('cpu'),worker_start_utc=process.get('start'),blocker=step if desired=='failed' else None)
if '1F' in observations:
    process=observations['1F']
    state=json.loads(Path(process['worker_path']).read_text())
    row=doc['floors']['1F']
    if process['alive'] and state['state'] in ('running','running_checked_E7','repairing','checking'):
        desired='cleaning';step='Checked E7 existing-vertex crack repair running; preservation checks and rollback active';running.insert(0,'1F')
    elif state['state'] in ('candidate_saved','saved'):
        desired='validating';step='New E7 candidate saved; original-fresh preservation and signed validation pending'
        row['pending_output_triangles']=state.get('output_triangles',state.get('triangles_after'))
    elif state['state'] in ('prepared','preparing','loading_qualified_input') and process['alive']:
        desired='cleaning';step='Loading hash-bound original source and preserved E3 stage for E7'
    elif state['state']=='checked_checkpoint_saved' and process['alive']:
        desired='cleaning';step='E7 checked checkpoint saved; verifying exact source/engine output and copied assets';running.insert(0,'1F')
    elif state['state'] in ('serializing','finalizing') and process['alive']:
        desired='cleaning';step='E7 site checks finished; saving exact source/engine pair and verifying copied assets';running.insert(0,'1F')
    else:
        desired='failed';step='E7 worker stopped: '+state.get('error',state['state'])
    if row['state']!=desired: row['last_work_event_at']=now;doc['last_work_event_at']=now
    row.update(state=desired,step=step,blocker=step if desired=='failed' else None,worker_pid=state['pid'],worker_alive=process['alive'],worker_observed_at=now,worker_cpu_seconds=process.get('cpu'),worker_start_utc=process.get('start'),engine_stage='E7')
failed=[f for f in ('1F','2F','3F') if doc['floors'][f]['state']=='failed']
details='; '.join(f+': '+str(doc['floors'][f].get('blocker','failed')) for f in failed)
doc.update(updated_at=now,heartbeat_at=now,state='running' if running else ('failed' if failed else 'reviewing'),step=('Actual checked engines running on '+','.join(running)+('; '+details if details else '')) if running else ('Engine checks stopped; '+details if failed else 'Engine workers finished; independent candidate review follows'))
active=','.join(running)
doc['next_action']=(f'Finish the active {active} repair and independently validate its saved output. ' if active else 'Independently validate saved output before publishing a new candidate. ')+ 'Run queued retries sequentially with fresh memory checks. Claude Code owns 4F-7F.'
doc['step']+=';1F E3 preservation PASS, remaining targets awaiting new independent measurement;Claude Code owns4F-7F'
source_refs=root/'data/siege-live-20261023/sources-published.json'
if source_refs.exists():
    sources=json.loads(source_refs.read_text())
    if sources['source_revision']!=doc['source_revision']: raise ValueError('source preview revision differs')
    for floor in ('2F','3F'):
        doc['floors'][floor]['source_preview']=sources['floors'][floor]
upper_root=root/'.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh'
upper=json.loads((upper_root/'current-upper.json').read_text())
if upper['source_revision']!=doc['source_revision'] or upper['job_id']!='MAIN-INFRA-CLAUDE-4F-7F-20261023':
    raise ValueError('Claude status job/source differs')
for floor in ('4F','5F','6F','7F'):
    reported=upper['floors'][floor]
    row=doc['floors'][floor]
    desired=reported['state']
    if desired in ('accepted','needs_review'): desired='validating'
    row.update(state=desired,step='Claude Code reports: '+reported['step'],blocker=reported.get('blocker'),owner_run_id=upper['run_id'],owner_reported_at=upper['updated_at'])
    for key in ('input_triangles','output_triangles','last_work_event_at'):
        if key in reported: row[key]=reported[key]
    witness=upper_root/'run-claude-4f-7f-20261023/e3'/f'worker-{floor}.json'
    if witness.exists():
        actual=json.loads(witness.read_text())
        row['owner_worker_pid']=actual['pid']
        if actual['state']=='candidate_saved':
            row['output_triangles']=actual['output_triangles']
            if desired not in ('blocked','failed','cancelled'):
                row.update(state='validating',step='Claude Code E3 candidate saved; independent preservation and signed targets pending')
        elif actual['state']=='failed':
            row.update(state='failed',step='Claude Code engine reports failure: '+actual.get('error','unknown'))
write_progress(path,doc)
print(json.dumps(dict(updated_at=now,running=running,floors={f:doc['floors'][f]['state'] for f in ('2F','3F')})))
'@
do {
    $taskObserved=@{}
    $taskAlive=0
    $taskExtraPath="$taskRoot/data/siege-live-20261023/extra-workers.json"
    $taskWitnessPaths=@{'2F'="$taskRun/worker-2F.json";'3F'="$taskRun/worker-3F.json"}
    $taskE3ExtraPath="$taskRoot/data/siege-live-20261023/extra-e3-workers.json"
    if(Test-Path -LiteralPath $taskE3ExtraPath){
        $taskE3Extra=Get-Content -LiteralPath $taskE3ExtraPath -Raw | ConvertFrom-Json
        foreach($taskItem in $taskE3Extra.PSObject.Properties){
            if($taskItem.Name -notin @('2F','3F')){throw 'Unexpected E3 retry floor'}
            if($taskItem.Value.deferred){
                $null=$taskWitnessPaths.Remove($taskItem.Name)
                continue
            }
            $taskExpected[$taskItem.Name]=@{pid=$taskItem.Value.pid;start=$taskItem.Value.start}
            $taskWitnessPaths[$taskItem.Name]=$taskItem.Value.worker_path
        }
    }
    if(Test-Path -LiteralPath $taskExtraPath){
        $taskExtra=Get-Content -LiteralPath $taskExtraPath -Raw | ConvertFrom-Json
        $taskExpected['1F']=@{pid=$taskExtra.pid;start=$taskExtra.start}
        $taskWitnessPaths['1F']=$taskExtra.worker_path
    }
    foreach($taskFloor in $taskWitnessPaths.Keys) {
        $taskWitness=Get-Content -LiteralPath $taskWitnessPaths[$taskFloor] -Raw | ConvertFrom-Json
        if($taskWitness.pid -ne $taskExpected[$taskFloor].pid){throw 'Worker PID changed; refusing stale publication'}
        $taskProcess=Get-Process -Id $taskExpected[$taskFloor].pid -ErrorAction SilentlyContinue
        $taskEntry=@{alive=$false}
        if($taskProcess){
            $taskStart=$taskProcess.StartTime.ToUniversalTime()
            $taskExpectedUtc=([datetimeoffset]$taskExpected[$taskFloor].start).UtcDateTime
            $taskDelta=[math]::Abs(($taskStart-$taskExpectedUtc).TotalSeconds)
            if($taskDelta -gt 1){throw 'PID creation time differs; refusing publication'}
            $taskEntry=@{alive=$true;cpu=[math]::Round($taskProcess.CPU,2);start=$taskStart.ToString('o')}
            $taskAlive++
        }
        $taskEntry['worker_path']=$taskWitnessPaths[$taskFloor]
        $taskObserved[$taskFloor]=$taskEntry
    }
    $env:UC_MODEL_WORKER_OBSERVATIONS=ConvertTo-Json $taskObserved -Compress
    & "$taskRoot/.venv/Scripts/python.exe" -B -c $taskPython
    if($LASTEXITCODE -ne 0){throw 'Canonical progress validation failed'}
    & scp -q -P 27015 -i 'C:/Users/Future26/.ssh/corllenium_siege_ed25519' -o IdentitiesOnly=yes -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=yes -o UserKnownHostsFile=deploy/known_hosts "$taskRoot/data/main-infra-fresh/current.json" 'devenvir@sv70.ifastnet.com:/home/devenvir/corllenium/data/main-infra-current-codex-20261023.json'
    if($LASTEXITCODE -ne 0){throw 'Worker feed upload failed'}
    & ssh -p 27015 -i 'C:/Users/Future26/.ssh/corllenium_siege_ed25519' -o IdentitiesOnly=yes -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=yes -o UserKnownHostsFile=deploy/known_hosts devenvir@sv70.ifastnet.com 'python3 /home/devenvir/corllenium/data/publish-workers-remote.py'
    if($LASTEXITCODE -ne 0){throw 'Live worker status publication failed'}
    Start-Sleep -Seconds 30
} while($true)
