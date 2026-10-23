param([int]$GateMinutes=15,[switch]$FunctionsOnly)
$ErrorActionPreference='Stop'
$env:TEMP='D:/TEMP'; $env:TMP='D:/TEMP'
$execRoot=(Get-Location).Path
$execPlan='data/main-infra-e7/run-20261023-attempt3/preparation-1F.json'
$execPlanSha='e5af36dde9a242388985200cd6502b370dba87aba92ef152bec9e91b0f681e2a'
$execHead='18c8ae993cfed71ad7e978d7b253cecb8a1ec5c5'
$execWorker=Join-Path $execRoot 'data/main-infra-e7/run-20261023-attempt3/execution-1F/worker.json'
$execBasePython='C:\Users\Future26\AppData\Local\Programs\Python\Python312\python.exe'
$execVenvPython='D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe'
$execArgs=@('-B','-u','-m','tools.main_infra_e7_attempt3','execute','--plan',$execPlan,'--plan-sha256',$execPlanSha)
$execEvidence=Join-Path $execRoot ('data/main-infra-e7/attempt3-preflight/execute-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $execEvidence | Out-Null
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class UcE7ExecNative {
 [StructLayout(LayoutKind.Sequential)] struct Perf {
  public uint cb; public UIntPtr CommitTotal,CommitLimit,CommitPeak,PhysicalTotal,PhysicalAvailable,SystemCache,KernelTotal,KernelPaged,KernelNonpaged,PageSize;
  public uint HandleCount,ProcessCount,ThreadCount;
 }
 [StructLayout(LayoutKind.Sequential)] struct Memory {
  public uint cb,PageFaultCount; public UIntPtr PeakWorkingSetSize,WorkingSetSize,QuotaPeakPagedPoolUsage,QuotaPagedPoolUsage,QuotaPeakNonPagedPoolUsage,QuotaNonPagedPoolUsage,PagefileUsage,PeakPagefileUsage,PrivateUsage;
 }
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct Entry {
  public uint dwSize,cntUsage,th32ProcessID; public UIntPtr th32DefaultHeapID; public uint th32ModuleID,cntThreads,th32ParentProcessID; public int pcPriClassBase; public uint dwFlags;
  [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string szExeFile;
 }
 public class Row { public int Pid,Parent; public string Name; }
 [StructLayout(LayoutKind.Sequential)] struct Basic { public IntPtr ExitStatus,Peb,Affinity,Priority,Pid,Parent; }
 [DllImport("ntdll.dll")] static extern int NtQueryInformationProcess(IntPtr h,int cls,ref Basic b,int len,out int ret);
 [DllImport("ntdll.dll",EntryPoint="NtQueryInformationProcess")] static extern int NtQueryBuffer(IntPtr h,int cls,IntPtr b,int len,out int ret);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr h,int flags,System.Text.StringBuilder text,ref int size);
 [StructLayout(LayoutKind.Sequential)] struct FT { public uint Low,High; public long Value { get {return ((long)High<<32)|Low;} } }
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr h,out FT creation,out FT exit,out FT kernel,out FT user);
 public static DateTime[] Times(IntPtr h) { FT c,e,k,u;if(!GetProcessTimes(h,out c,out e,out k,out u))throw new Win32Exception();return new DateTime[]{DateTime.FromFileTimeUtc(c.Value),e.Value==0?DateTime.MaxValue:DateTime.FromFileTimeUtc(e.Value)}; }
 public static string Image(IntPtr h) { var b=new System.Text.StringBuilder(32768);int n=b.Capacity;if(!QueryFullProcessImageName(h,0,b,ref n))throw new Win32Exception();return b.ToString(); }
 public static string Command(IntPtr h) {
  int size=4096;
  for(int attempt=0;attempt<2;attempt++){
   IntPtr b=Marshal.AllocHGlobal(size);
   try {
    int required;int status=NtQueryBuffer(h,60,b,size,out required);
    if(status!=0){if(required>size&&required<=131072){size=required;continue;}throw new Exception("Native command query failed: "+status);}
    int length=(ushort)Marshal.ReadInt16(b);IntPtr value=Marshal.ReadIntPtr(b,IntPtr.Size==8?8:4);
    long offset=value.ToInt64()-b.ToInt64();
    if(length<=0 || (length%2)!=0 || offset<0 || offset+length>size)throw new Exception("Native command buffer invalid");
    return Marshal.PtrToStringUni(value,length/2);
   } finally {Marshal.FreeHGlobal(b);}
  }
  throw new Exception("Native command query exceeds bound");
 }
 public static int Parent(IntPtr h) { var b=new Basic(); int ret; if(NtQueryInformationProcess(h,0,ref b,Marshal.SizeOf(typeof(Basic)),out ret)!=0) throw new Exception("Native ancestry query failed"); return checked((int)b.Parent.ToInt64()); }
 [DllImport("psapi.dll",SetLastError=true)] static extern bool GetPerformanceInfo(ref Perf p,uint cb);
 [DllImport("psapi.dll",SetLastError=true)] static extern bool GetProcessMemoryInfo(IntPtr h,ref Memory p,uint cb);
 [DllImport("kernel32.dll",SetLastError=true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags,uint id);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool Process32FirstW(IntPtr h,ref Entry e);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool Process32NextW(IntPtr h,ref Entry e);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll",SetLastError=true)] public static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool TerminateProcess(IntPtr h,uint code);
 public static long[] SystemMemory() {
  var p=new Perf(); p.cb=(uint)Marshal.SizeOf(typeof(Perf));
  if(!GetPerformanceInfo(ref p,p.cb)) throw new Win32Exception();
  ulong page=p.PageSize.ToUInt64();
  return new long[]{checked((long)(p.CommitTotal.ToUInt64()*page)),checked((long)(p.CommitLimit.ToUInt64()*page)),checked((long)(p.PhysicalAvailable.ToUInt64()*page))};
 }
 public static long[] ProcessMemory(IntPtr h) {
  var p=new Memory(); p.cb=(uint)Marshal.SizeOf(typeof(Memory));
  if(!GetProcessMemoryInfo(h,ref p,p.cb)) throw new Win32Exception();
  return new long[]{checked((long)p.PrivateUsage.ToUInt64()),checked((long)p.PeakPagefileUsage.ToUInt64()),checked((long)p.WorkingSetSize.ToUInt64()),checked((long)p.PeakWorkingSetSize.ToUInt64())};
 }
 public static Row[] Processes() {
  var h=CreateToolhelp32Snapshot(2,0); if(h==new IntPtr(-1)) throw new Win32Exception();
  try {
   var e=new Entry(); e.dwSize=(uint)Marshal.SizeOf(typeof(Entry)); var rows=new List<Row>();
   if(!Process32FirstW(h,ref e)) throw new Win32Exception();
   do { rows.Add(new Row{Pid=(int)e.th32ProcessID,Parent=(int)e.th32ParentProcessID,Name=e.szExeFile}); } while(Process32NextW(h,ref e));
   return rows.ToArray();
  } finally { CloseHandle(h); }
 }
 public static bool Alive(IntPtr h) { uint r=WaitForSingleObject(h,0); if(r==0) return false; if(r==258) return true; throw new Win32Exception(); }
 public static void StopOwned(IntPtr h) { if(Alive(h) && !TerminateProcess(h,231)) throw new Win32Exception(); }
}
'@
function Normalize-ExecCommand([string]$value) { return (($value.Replace('"','').Replace('/','\') -replace '\s+',' ').Trim()) }
function Write-ExecJson([string]$path,$value) { [System.IO.File]::WriteAllText($path,($value|ConvertTo-Json -Depth 12),[System.Text.UTF8Encoding]::new($false)) }
function Check-ExecFrozen {
 if((git rev-parse HEAD).Trim() -ne $execHead -or (git status --porcelain --untracked-files=no)) { throw 'Frozen HEAD/tracked files changed' }
 if((Get-FileHash -LiteralPath $execPlan -Algorithm SHA256).Hash.ToLower() -ne $execPlanSha) { throw 'Pinned preparation changed' }
 $p=Get-Process -Id 41648
 if($p.StartTime.ToUniversalTime().ToString('o') -ne '2026-10-23T14:13:11.8254166Z') { throw '2F identity changed' }
 if(Test-Path -LiteralPath (Split-Path $execWorker)) { throw 'Execution namespace exists' }
}
$execOwned=@{}; $execActual=$null; $execLauncher=$null; $execAbort=$null; $execStarted=$false
$execExpectedChild=Normalize-ExecCommand ($execBasePython+' '+($execArgs -join ' '))
$execExpectedLauncher=Normalize-ExecCommand ($execVenvPython+' '+($execArgs -join ' '))
function Test-ExecLifetime([DateTime]$child,[DateTime]$parentStart,[DateTime]$parentExit) {
 return $child -ge $parentStart -and $child -le $parentExit
}
function Update-ExecIdentity($record,[string]$expectedCommand) {
 if([UcE7ExecNative]::Parent($record.Handle) -ne $record.Parent) { throw 'Owned native ancestry changed during binding' }
 $record.Image=[UcE7ExecNative]::Image($record.Handle)
 $record.Command=Normalize-ExecCommand ([UcE7ExecNative]::Command($record.Handle))
 $identity=[ordered]@{pid=$record.Pid;parent_pid=$record.Parent;creation_utc=$record.Start.ToString('o');image=$record.Image;command=$record.Command;first_seen_utc=[DateTime]::UtcNow.ToString('o');preparation_sha256=$execPlanSha;HEAD=$execHead}
 $identity|ConvertTo-Json -Depth 5 -Compress|Add-Content -LiteralPath (Join-Path $execEvidence 'identities.jsonl') -Encoding utf8
 if($expectedCommand -and -not [string]::Equals($record.Command,$expectedCommand,[StringComparison]::OrdinalIgnoreCase)) { throw 'Owned expected command failed' }
}
function Register-ExecLauncher([Diagnostics.Process]$process,[string]$expectedCommand) {
 $h=$process.Handle; $times=[UcE7ExecNative]::Times($h)
 $script:execLauncher=[pscustomobject]@{Pid=$process.Id;Parent=$PID;Start=$times[0];Handle=$h;Process=$process;Command='';Image=''}
 $execOwned[$process.Id]=$script:execLauncher
 Update-ExecIdentity $script:execLauncher $expectedCommand
 return $script:execLauncher
}
function Add-ExecOwned([int]$id,[int]$parentId) {
 if($id -in @(41648,55644,$PID)) { throw 'Protected foreign PID refused' }
 if(-not $execOwned.ContainsKey($parentId)) { return $null }
 $p=Get-Process -Id $id -ErrorAction SilentlyContinue
 if(-not $p) { return $null }
 $h=$p.Handle; $times=[UcE7ExecNative]::Times($h)
 $parent=$execOwned[$parentId]; $parentTimes=[UcE7ExecNative]::Times($parent.Handle)
 if([UcE7ExecNative]::Parent($h) -ne $parentId) { return $null }
 if(-not(Test-ExecLifetime $times[0] $parent.Start $parentTimes[1])) { return $null }
 $record=[pscustomobject]@{Pid=$id;Parent=$parentId;Start=$times[0];Handle=$h;Process=$p;Command='';Image=''}
 $execOwned[$id]=$record
 if([UcE7ExecNative]::Alive($h)) { Update-ExecIdentity $record $null }
 return $record
}
function Discover-ExecOwned {
 $entries=[UcE7ExecNative]::Processes()
 $changed=$true
 while($changed) {
  $changed=$false
  foreach($entry in $entries) {
   if($execOwned.ContainsKey($entry.Pid) -and [UcE7ExecNative]::Alive($execOwned[$entry.Pid].Handle)) { continue }
   if(-not $execOwned.ContainsKey($entry.Parent)) { continue }
   $prior=if($execOwned.ContainsKey($entry.Pid)){$execOwned[$entry.Pid].Start.Ticks}else{-1}
   $bound=Add-ExecOwned $entry.Pid $entry.Parent
   if($bound -and $bound.Start.Ticks -ne $prior) { $changed=$true }
  }
 }
}
function Test-ExecActualDescendant($record) {
 if(-not $execActual) { return $false }
 $ancestor=$record.Parent; $seen=@{}
 while($execOwned.ContainsKey($ancestor) -and -not $seen.ContainsKey($ancestor)) {
  if($ancestor -eq $execActual.Pid) { return $true }
  $seen[$ancestor]=$true; $ancestor=$execOwned[$ancestor].Parent
 }
 return $false
}
function Select-ExecActual {
 foreach($bound in $execOwned.Values) {
  if($bound.Parent -ne $execLauncher.Pid -or -not [UcE7ExecNative]::Alive($bound.Handle) -or [IO.Path]::GetFileName($bound.Image) -ine 'python.exe') { continue }
  if(-not [string]::Equals($bound.Image,$execBasePython,[StringComparison]::OrdinalIgnoreCase) -or -not [string]::Equals($bound.Command,$execExpectedChild,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected Python descendant identity' }
  if($script:execActual -and $script:execActual.Pid -ne $bound.Pid) { throw 'Unexpected second interpreter' }
  $script:execActual=$bound
 }
 $consoleImage=Join-Path $env:WINDIR 'System32/conhost.exe'
 $consoleCommand=Normalize-ExecCommand ('\??\'+$env:WINDIR+'\system32\conhost.exe 0x4')
 foreach($bound in $execOwned.Values) {
  if($bound.Pid -eq $execLauncher.Pid -or -not [UcE7ExecNative]::Alive($bound.Handle)) { continue }
  if($execActual -and $bound.Pid -eq $execActual.Pid) { continue }
  if($bound.Parent -eq $execLauncher.Pid -and [string]::Equals($bound.Image,$consoleImage,[StringComparison]::OrdinalIgnoreCase) -and [string]::Equals($bound.Command,$consoleCommand,[StringComparison]::OrdinalIgnoreCase)) { continue }
  if(Test-ExecActualDescendant $bound) { continue }
  throw 'Unexpected owned descendant'
 }
}
function Assert-ExecResources($memory,[long]$private,[long]$peak,[long]$treePrivate) {
 if($memory.Count -ne 3 -or $memory[0] -le 0 -or $memory[1] -le $memory[0] -or $memory[2] -lt 0 -or $private -lt 0 -or $peak -lt $private) { throw 'Invalid native memory counters' }
 if($private -gt 3GB -or $peak -gt 3GB -or $treePrivate -gt 3GB) { throw 'Resource abort: owned private/OSpeak above3GiB' }
 if(($memory[1]-$memory[0]) -lt 3.5GB) { throw 'Resource abort: systemic headroom below3.5GiB' }
}
function Stop-ExecTree {
 $errors=[Collections.Generic.List[string]]::new()
 $timer=[Diagnostics.Stopwatch]::StartNew()
 do {
  try { Discover-ExecOwned } catch { $errors.Add('Discovery: '+$_.Exception.Message) }
  foreach($item in @($execOwned.Values | Sort-Object Start)) {
   if($item.Pid -in @(41648,55644,$PID)) { $errors.Add('Protected PID encountered'); continue }
   try { [UcE7ExecNative]::StopOwned($item.Handle) } catch {
    if([UcE7ExecNative]::Alive($item.Handle)) { $errors.Add('Kill '+$item.Pid+': '+$_.Exception.Message) }
   }
  }
  Start-Sleep -Milliseconds 50
  try { Discover-ExecOwned } catch { $errors.Add('Post-kill discovery: '+$_.Exception.Message) }
  $alive=@($execOwned.Values|Where-Object {[UcE7ExecNative]::Alive($_.Handle)})
 } while($alive.Count -gt 0 -and $timer.Elapsed.TotalSeconds -lt 5)
 $receipt=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');all_owned_exited=($alive.Count -eq 0);alive_pids=@($alive|ForEach-Object {$_.Pid});owned_pids=@($execOwned.Values|ForEach-Object {$_.Pid});errors=@($errors);wall_s=$timer.Elapsed.TotalSeconds}
 Write-ExecJson (Join-Path $execEvidence 'cleanup.json') $receipt
 if($alive.Count -gt 0 -or $errors.Count -gt 0) { throw ('Owned cleanup failed: '+($receipt|ConvertTo-Json -Compress -Depth 5)) }
 return $receipt
}
if($FunctionsOnly) { return }
$execGateWatch=[Diagnostics.Stopwatch]::StartNew()
while($execGateWatch.Elapsed.TotalMinutes -lt $GateMinutes) {
 Check-ExecFrozen
 $gate=@()
 for($i=0;$i -lt 3;$i++) {
  $m=[UcE7ExecNative]::SystemMemory()
  Assert-ExecResources $m 0 0 0
  $gate += [pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');commit_bytes=$m[0];limit_bytes=$m[1];headroom_bytes=$m[1]-$m[0]}
  if($i -lt 2) { Start-Sleep -Milliseconds 500 }
 }
 $pass=@($gate|Where-Object {$_.headroom_bytes -lt 8GB}).Count -eq 0
 [pscustomobject]@{utc=[DateTime]::UtcNow.ToString('o');passed=$pass;samples=$gate}|ConvertTo-Json -Depth 6 -Compress|Add-Content -LiteralPath (Join-Path $execEvidence 'launch-gates.jsonl') -Encoding utf8
 if($pass) { break }
 [pscustomobject]@{state='HOLD';headroom_gib=@($gate|ForEach-Object {[math]::Round($_.headroom_bytes/1GB,4)});evidence=$execEvidence;retry_s=30}|ConvertTo-Json -Compress
 Start-Sleep -Seconds 29
}
if(-not $pass) { Write-ExecJson (Join-Path $execEvidence 'result.json') @{state='HOLD';reason='15minute launch gate expired';no_execute_started=$true}; exit 3 }
Check-ExecFrozen
$env:PYTHONPATH=$execRoot; $env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'; $env:NUMEXPR_NUM_THREADS='1'
$execWatch=[Diagnostics.Stopwatch]::StartNew()
try {
 $launched=Start-Process -FilePath $execVenvPython -ArgumentList $execArgs -WorkingDirectory $execRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $execEvidence 'stdout.txt') -RedirectStandardError (Join-Path $execEvidence 'stderr.txt')
 $execStarted=$true
 $execLauncher=Register-ExecLauncher $launched $execExpectedLauncher
 $early=[Diagnostics.Stopwatch]::StartNew()
 while(-not $execActual -and $early.Elapsed.TotalSeconds -lt 5) {
  Discover-ExecOwned
  Select-ExecActual
  $m=[UcE7ExecNative]::SystemMemory()
  Assert-ExecResources $m 0 0 0
  if(-not $execActual) { Start-Sleep -Milliseconds 50 }
 }
 if(-not $execActual) { throw 'Actual Python312 descendant could not be bound early' }
 $actualIdentity=[ordered]@{state='RUNNING';launcher_pid=$execLauncher.Pid;launcher_creation_utc=$execLauncher.Start.ToString('o');actual_pid=$execActual.Pid;actual_creation_utc=$execActual.Start.ToString('o');command=$execActual.Command;preparation_sha256=$execPlanSha;HEAD=$execHead;bound_before_worker_json=(-not(Test-Path -LiteralPath $execWorker));worker_path=$execWorker;evidence=$execEvidence;monitor_pid=$PID;private_limit_bytes=3GB;headroom_abort_bytes=3.5GB}
 Write-ExecJson (Join-Path $execEvidence 'actual-identity.json') $actualIdentity
 $actualIdentity|ConvertTo-Json -Depth 6 -Compress
 while($true) {
  Discover-ExecOwned
  $m=[UcE7ExecNative]::SystemMemory()
  if($m[0] -le 0 -or $m[1] -le $m[0]) { throw 'Invalid system memory counters' }
  $rows=@(); $treePrivate=[long]0; $actualPrivate=[long]0; $actualPeak=[long]0
  foreach($item in $execOwned.Values) {
   if(-not [UcE7ExecNative]::Alive($item.Handle)) { continue }
   try { $pm=[UcE7ExecNative]::ProcessMemory($item.Handle) } catch { if(-not [UcE7ExecNative]::Alive($item.Handle)){continue};throw }
   $treePrivate+=$pm[0]
   $rows += [pscustomobject]@{pid=$item.Pid;creation_utc=$item.Start.ToString('o');private_bytes=$pm[0];os_peak_commit_bytes=$pm[1]}
   if($item.Pid -eq $execActual.Pid) { $actualPrivate=$pm[0]; $actualPeak=$pm[1] }
   Assert-ExecResources $m $pm[0] $pm[1] $treePrivate
  }
  Assert-ExecResources $m $actualPrivate $actualPeak $treePrivate
  if((Get-FileHash -LiteralPath $execPlan -Algorithm SHA256).Hash.ToLower() -ne $execPlanSha) { throw 'Pinned preparation identity changed' }
  if(Test-Path -LiteralPath $execWorker) {
   $w=Get-Content -LiteralPath $execWorker -Raw|ConvertFrom-Json
   if($w.pid -ne $execActual.Pid -or $w.preparation_sha256 -ne $execPlanSha -or $w.components.HEAD -ne $execHead) { throw 'Worker identity mismatch' }
  }
  $row=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');actual_pid=$execActual.Pid;actual_creation_utc=$execActual.Start.ToString('o');actual_private_bytes=$actualPrivate;actual_os_peak_commit_bytes=$actualPeak;tree_private_bytes=$treePrivate;system_commit_bytes=$m[0];system_commit_limit_bytes=$m[1];headroom_bytes=$m[1]-$m[0];owned=$rows}
  $row|ConvertTo-Json -Depth 6 -Compress|Add-Content -LiteralPath (Join-Path $execEvidence 'resources.jsonl') -Encoding utf8
  if(@($execOwned.Values|Where-Object {[UcE7ExecNative]::Alive($_.Handle)}).Count -eq 0) { break }
  Start-Sleep -Milliseconds 500
 }
 $execLauncher.Process.WaitForExit()
 $execActual.Process.WaitForExit()
 $launcherExitCode=$execLauncher.Process.ExitCode
 $exitCode=$execActual.Process.ExitCode
 $state=if($exitCode -eq 0){'PROCESS_EXITED_ZERO'}else{'PROCESS_FAILED'}
} catch {
 $execAbort=$_.Exception.Message
 try { $cleanup=Stop-ExecTree } catch { $execAbort+='; '+$_.Exception.Message }
 $state=if($execStarted){'RESOURCE_OR_MONITOR_ABORT'}else{'HOLD'}
 $exitCode=$null
} finally {
 if($execAbort -and -not $cleanup) { try { $cleanup=Stop-ExecTree } catch { $execAbort+='; '+$_.Exception.Message } }
}
$execWatch.Stop()
$final=[ordered]@{schema_version=1;state=$state;abort_reason=$execAbort;wall_s=[math]::Round($execWatch.Elapsed.TotalSeconds,3);launcher_pid=$(if($execLauncher){$execLauncher.Pid}else{$null});actual_pid=$(if($execActual){$execActual.Pid}else{$null});actual_creation_utc=$(if($execActual){$execActual.Start.ToString('o')}else{$null});exit_code=$exitCode;actual_exit_code=$exitCode;launcher_exit_code=$launcherExitCode;preparation_sha256=$execPlanSha;HEAD=$execHead;evidence=$execEvidence;worker_path=$execWorker;ended_utc=[DateTime]::UtcNow.ToString('o');floor_accepted=$false}
Write-ExecJson (Join-Path $execEvidence 'result.json') $final
$final|ConvertTo-Json -Depth 6 -Compress
if($execAbort) { exit 4 }; if($exitCode -ne 0) { exit $exitCode }
