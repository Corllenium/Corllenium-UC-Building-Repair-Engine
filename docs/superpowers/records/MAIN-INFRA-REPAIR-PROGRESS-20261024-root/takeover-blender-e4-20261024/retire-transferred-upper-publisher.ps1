$ErrorActionPreference='Stop'
$taskRoot='D:/PROJECTS/UC MODEL FIXER'
$taskNative='D:/LLM_BACKUP/Codex session/main-infra-resource-monitor-v5-20261024/05-Corllenium-UC-Building-Repair-Engine/docs/superpowers/records/MAIN-INFRA-RESOURCE-MONITOR-V5-20261024/execute-resource-guard-v5.ps1'
function Assert-TaskHash([string]$path,[string]$expected) {
 if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw "Pinned file differs: $path"}
}
Assert-TaskHash $taskNative 'f158802651c955b6b322140ff9567496c527cd1bac0e63598171c45eeea60e12'
Assert-TaskHash "$taskRoot/data/iv-handoff-audit-20261024/controller-grant-floors4-7.json" 'bbeb6a7f7a21e4d4556e9f2bc5a0365f3ce7d0b90e6a154527be2f78937f6dfa'
Assert-TaskHash "$taskRoot/data/iv-handoff-audit-20261024/recipient-atomic-claim.json" 'e1b4cdbc9625cb01cc30f72b99aacd64f53e8d0195ac2d36c72a701ec26196b6'
$taskQueue=Get-Content -LiteralPath "$taskRoot/data/jobs/queue.json" -Raw | ConvertFrom-Json
$taskJob=@($taskQueue.jobs | Where-Object id -eq 'MAIN-INFRA-CLAUDE-4F-7F-20261023')
if($taskJob.Count -ne 1 -or $taskJob[0].status -ne 'claimed' -or $taskJob[0].holder -ne 'Codex-Upper-Floors' -or $taskJob[0].branch -ne 'codex/main-infra-upper-floor-retention-20261024'){throw 'Current queue ownership differs'}
. $taskNative -FunctionsOnly
$taskProcess=[Diagnostics.Process]::GetProcessById(33720)
$taskHandle=$taskProcess.Handle
$taskExpectedStart=[DateTime]::Parse('2026-10-24T01:54:16.5213028Z').ToUniversalTime()
function Assert-TaskLifetime {
 if(-not [UcE7ExecNative]::Alive($taskHandle)){throw 'Transferred publisher already exited'}
 if([UcE7ExecNative]::Times($taskHandle)[0].Ticks -ne $taskExpectedStart.Ticks){throw 'Transferred publisher creation differs'}
 if([UcE7ExecNative]::Image($taskHandle) -ine 'C:\Users\Future26\AppData\Local\Programs\Python\Python312\python.exe'){throw 'Transferred publisher executable differs'}
 if([UcE7ExecNative]::Parent($taskHandle) -ne 40264){throw 'Transferred publisher parent differs'}
 $taskCommand=[UcE7ExecNative]::Command($taskHandle)
 $taskHash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($taskCommand))).ToLowerInvariant()
 if($taskHash -ne '0d106f2f1010deaa603dffabc0caeb496e0628eebdd91642006946126b98b4ee'){throw 'Transferred publisher command differs'}
}
$taskLog="$taskRoot/.claude/worktrees/MAIN-INFRA-CLAUDE-4F-7F-20261023/data/main-infra-fresh/run-claude-4f-7f-20261023/logs/live-publisher.log"
function Get-TaskLog {
 $taskStream=[IO.File]::Open($taskLog,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
 try {
  $taskReader=[IO.StreamReader]::new($taskStream)
  try {$taskText=$taskReader.ReadToEnd()} finally {$taskReader.Dispose()}
 } finally {$taskStream.Dispose()}
 $taskTail=@($taskText.TrimEnd().Split([char]10) | Select-Object -Last 1)[0].TrimEnd([char]13)
 [pscustomobject]@{Line=$taskTail;Length=(Get-Item -LiteralPath $taskLog).Length;LastWrite=(Get-Item -LiteralPath $taskLog).LastWriteTimeUtc}
}
Assert-TaskLifetime
$taskWatch=[Diagnostics.Stopwatch]::StartNew()
$taskIdle=$null
while($taskWatch.Elapsed.TotalSeconds -lt 45){
 Assert-TaskLifetime
 $taskLogState=Get-TaskLog
 $taskAge=([DateTime]::UtcNow-$taskLogState.LastWrite).TotalSeconds
 $taskChildren=@([UcE7ExecNative]::Processes() | Where-Object Parent -eq 33720)
 if($taskAge -ge 1 -and $taskAge -le 8 -and $taskChildren.Count -eq 0 -and $taskLogState.Line -match '^\d{2}:\d{2}:\d{2} (live publish failed:|uploaded |unchanged )'){
  Start-Sleep -Milliseconds 250
  Assert-TaskLifetime
  $taskCheck=Get-TaskLog
  $taskChildren=@([UcE7ExecNative]::Processes() | Where-Object Parent -eq 33720)
  if($taskChildren.Count -eq 0 -and $taskCheck.Length -eq $taskLogState.Length -and $taskCheck.LastWrite -eq $taskLogState.LastWrite){$taskIdle=$taskCheck;break}
 }
 Start-Sleep -Milliseconds 250
}
if($null -eq $taskIdle){throw 'No fresh completed-publish zero-child idle window; no action taken'}
Assert-TaskLifetime
if(@([UcE7ExecNative]::Processes() | Where-Object Parent -eq 33720).Count -ne 0){throw 'Publisher child appeared; no action taken'}
$taskBefore=[DateTime]::UtcNow
[UcE7ExecNative]::StopOwned($taskHandle)
if([UcE7ExecNative]::WaitForSingleObject($taskHandle,5000) -ne 0){throw 'Transferred publisher did not terminate in bound'}
$taskTimes=[UcE7ExecNative]::Times($taskHandle)
$taskProcess.Refresh()
$taskReceipt=[ordered]@{
 schema_version=1;action='retire transferred upper-floor status publisher after human STOP and atomic recipient claim';
 pid=33720;creation_utc=$taskTimes[0].ToString('o');end_utc=$taskTimes[1].ToString('o');exit_code=$taskProcess.ExitCode;
 command_sha256='0d106f2f1010deaa603dffabc0caeb496e0628eebdd91642006946126b98b4ee';
 source_claim_sha256='e1b4cdbc9625cb01cc30f72b99aacd64f53e8d0195ac2d36c72a701ec26196b6';
 completed_log_line=$taskIdle.Line;completed_log_write_utc=$taskIdle.LastWrite.ToString('o');action_at_utc=$taskBefore.ToString('o');
 immediate_children_at_action=0;native_handle_bound=$true;pid_only_kill=$false;
 protected_root_publisher_4056_touched=$false;other_helper_52472_touched=$false;blender_14540_touched=$false;
 no_source_model_changes=$true;remote_write=$false
}
$taskOutput="$taskRoot/data/iv-handoff-audit-20261024/transferred-publisher-retirement.json"
if(Test-Path -LiteralPath $taskOutput){throw 'Exclusive retirement receipt already exists'}
[IO.File]::WriteAllText($taskOutput,($taskReceipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
$taskReceipt|ConvertTo-Json -Depth 8 -Compress
