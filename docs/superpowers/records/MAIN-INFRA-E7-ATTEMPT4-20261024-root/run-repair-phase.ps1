param([Parameter(Mandatory=$true)][string]$PhasePlan,[Parameter(Mandatory=$true)][string]$PhasePlanSha)
$ErrorActionPreference='Stop'
$phaseRun=Get-Content -Raw -LiteralPath $PhasePlan|ConvertFrom-Json
if((Get-FileHash -Algorithm SHA256 -LiteralPath $PhasePlan).Hash.ToLower() -ne $PhasePlanSha){throw 'Phase invocation hash changed'}
$observer='D:/LLM_BACKUP/Codex session/main-infra-e7-attempt3-20261023/05-Corllenium-UC-Building-Repair-Engine/data/main-infra-e7/attempt3-preflight/execute-resource-guard-v4.ps1'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $observer).Hash.ToLower() -ne '9cce36842bd6f45b88c5122f350ae7eda4cc0ec79d3a38c5c2959dd24dd6fd60'){throw 'Reviewed observer changed'}
. $observer -FunctionsOnly
$execEvidence=Join-Path (Split-Path $PhasePlan) ('monitor-'+$phaseRun.phase+'-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $execEvidence|Out-Null
$execHead=$phaseRun.HEAD
$execArgs=@($phaseRun.args)
$execPlan=$phaseRun.pins[0].path
$execPlanSha=$phaseRun.pins[0].sha256
$execExpectedChild=Normalize-ExecCommand ($execBasePython+' '+($execArgs -join ' '))
$execExpectedLauncher=Normalize-ExecCommand ($execVenvPython+' '+($execArgs -join ' '))
$execQuotedArgs=($execArgs|ForEach-Object {'"'+$_+'"'}) -join ' '
$env:PYTHONPATH=$execRoot;$env:OPENBLAS_NUM_THREADS='1';$env:OMP_NUM_THREADS='1';$env:MKL_NUM_THREADS='1';$env:NUMEXPR_NUM_THREADS='1'
function Check-PhasePins {
 if((Get-FileHash -Algorithm SHA256 -LiteralPath $PhasePlan).Hash.ToLower() -ne $PhasePlanSha){throw 'Phase invocation identity changed'}
 foreach($pin in $phaseRun.pins){if((Get-FileHash -Algorithm SHA256 -LiteralPath $pin.path).Hash.ToLower() -ne $pin.sha256){throw ('Pinned phase input changed: '+$pin.path)}}
}
Check-PhasePins
if((git rev-parse HEAD).Trim() -ne $execHead -or (git status --porcelain --untracked-files=no)){throw 'Frozen proof HEAD/tracked files changed'}
$gate=@()
for($i=0;$i -lt 3;$i++){
 $m=[UcE7ExecNative]::SystemMemory();Assert-ExecResources $m 0 0 0
 $gate += [pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');commit_bytes=$m[0];limit_bytes=$m[1];headroom_bytes=$m[1]-$m[0]}
 if($i -lt 2){Start-Sleep -Milliseconds 500}
}
$passed=(-not $phaseRun.gate_8gib) -or @($gate|Where-Object {$_.headroom_bytes -lt 8GB}).Count -eq 0
Write-ExecJson (Join-Path $execEvidence 'launch-gate.json') @{passed=$passed;require8GiB=$phaseRun.gate_8gib;samples=$gate}
if(-not $passed){Write-ExecJson (Join-Path $execEvidence 'result.json') @{state='HOLD';no_phase_started=$true;reason='Three fresh launch samples below8GiB'};Write-Output ('HOLD '+$execEvidence);exit 3}
$execWatch=[Diagnostics.Stopwatch]::StartNew();$cleanup=$null;$launcherExitCode=$null;$exitCode=$null
try{
 $launched=Start-Process -FilePath $execVenvPython -ArgumentList $execQuotedArgs -WorkingDirectory $execRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $execEvidence 'stdout.txt') -RedirectStandardError (Join-Path $execEvidence 'stderr.txt')
 $execStarted=$true;$execLauncher=Register-ExecLauncher $launched $execExpectedLauncher
 $early=[Diagnostics.Stopwatch]::StartNew()
 while(-not $execActual -and $early.Elapsed.TotalSeconds -lt 5){Discover-ExecOwned;Select-ExecActual;$m=[UcE7ExecNative]::SystemMemory();Assert-ExecResources $m 0 0 0;Start-Sleep -Milliseconds 25}
 if(-not $execActual){throw 'Actual interpreter not bound before5s limit'}
 $identity=[ordered]@{state='RUNNING';phase=$phaseRun.phase;actual_pid=$execActual.Pid;actual_creation_utc=$execActual.Start.ToString('o');launcher_pid=$execLauncher.Pid;monitor_pid=$PID;command=$execActual.Command;HEAD=$execHead;phase_plan_sha256=$PhasePlanSha;evidence=$execEvidence}
 Write-ExecJson (Join-Path $execEvidence 'actual-identity.json') $identity
 $identity|ConvertTo-Json -Compress
 while($true){
  Discover-ExecOwned;$m=[UcE7ExecNative]::SystemMemory();$rows=@();$treePrivate=[long]0;$actualPrivate=[long]0;$actualPeak=[long]0
  foreach($item in $execOwned.Values){
   if(-not [UcE7ExecNative]::Alive($item.Handle)){continue}
   try{$pm=[UcE7ExecNative]::ProcessMemory($item.Handle)}catch{if(-not [UcE7ExecNative]::Alive($item.Handle)){continue};throw}
   $treePrivate+=$pm[0]
   $rows += [pscustomobject]@{pid=$item.Pid;creation_utc=$item.Start.ToString('o');private_bytes=$pm[0];os_peak_commit_bytes=$pm[1]}
   if($item.Pid -eq $execActual.Pid){$actualPrivate=$pm[0];$actualPeak=$pm[1]}
   Assert-ExecResources $m $pm[0] $pm[1] $treePrivate
   if($pm[0] -ge 3GB -or $pm[1] -ge 3GB -or $treePrivate -ge 3GB){throw 'Resource abort: owned private/peak at3GiB'}
  }
  Assert-ExecResources $m $actualPrivate $actualPeak $treePrivate
  Check-PhasePins
  [ordered]@{utc=[DateTime]::UtcNow.ToString('o');actual_pid=$execActual.Pid;actual_creation_utc=$execActual.Start.ToString('o');actual_private_bytes=$actualPrivate;actual_os_peak_commit_bytes=$actualPeak;tree_private_bytes=$treePrivate;system_commit_bytes=$m[0];system_commit_limit_bytes=$m[1];headroom_bytes=$m[1]-$m[0];owned=$rows}|ConvertTo-Json -Depth 6 -Compress|Add-Content -LiteralPath (Join-Path $execEvidence 'resources.jsonl') -Encoding utf8
  if(@($execOwned.Values|Where-Object {[UcE7ExecNative]::Alive($_.Handle)}).Count -eq 0){break}
  Start-Sleep -Milliseconds 500
 }
 $execLauncher.Process.WaitForExit();$execActual.Process.WaitForExit();$launcherExitCode=$execLauncher.Process.ExitCode;$exitCode=$execActual.Process.ExitCode
 $state=if($exitCode -eq 0){'PROCESS_EXITED_ZERO'}else{'PROCESS_FAILED'}
}catch{
 $execAbort=$_.Exception.Message
 try{$cleanup=Stop-ExecTree}catch{$execAbort+='; '+$_.Exception.Message}
 $state=if($execStarted){'RESOURCE_OR_MONITOR_ABORT'}else{'HOLD'}
}finally{if($execAbort -and -not $cleanup){try{$cleanup=Stop-ExecTree}catch{$execAbort+='; '+$_.Exception.Message}}}
$execWatch.Stop()
$final=[ordered]@{state=$state;phase=$phaseRun.phase;abort_reason=$execAbort;actual_pid=$(if($execActual){$execActual.Pid}else{$null});actual_creation_utc=$(if($execActual){$execActual.Start.ToString('o')}else{$null});actual_exit_code=$exitCode;launcher_exit_code=$launcherExitCode;wall_s=$execWatch.Elapsed.TotalSeconds;HEAD=$execHead;phase_plan_sha256=$PhasePlanSha;all_owned_exited=(@($execOwned.Values|Where-Object {[UcE7ExecNative]::Alive($_.Handle)}).Count -eq 0);evidence=$execEvidence;ended_utc=[DateTime]::UtcNow.ToString('o');acceptance=$false}
Write-ExecJson (Join-Path $execEvidence 'result.json') $final
$final|ConvertTo-Json -Compress
if($execAbort){exit 4};exit $exitCode