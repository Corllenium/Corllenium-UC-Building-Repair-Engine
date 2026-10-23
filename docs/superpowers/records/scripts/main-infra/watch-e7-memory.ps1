param(
  [Parameter(Mandatory=$true)][int]$WorkerPid,
  [Parameter(Mandatory=$true)][string]$Output,
  [int]$IntervalMs=1000,
  [int]$MaxSamples=0
)
$ErrorActionPreference='Stop'
if ($IntervalMs -lt 1 -or $MaxSamples -lt 0) { throw 'Invalid observer interval or sample count' }
if (Test-Path -LiteralPath $Output) { throw 'Resource output exists; refusing overwrite' }
$e7Watched=Get-Process -Id $WorkerPid
$null=$e7Watched.Handle
New-Item -ItemType File -Path $Output -ErrorAction Stop | Out-Null
$e7SampleCount=0
try {
  while (-not $e7Watched.HasExited) {
    $e7Watched.Refresh()
    $e7Counters=(Get-Counter '\Memory\Committed Bytes','\Memory\Commit Limit','\Memory\Available MBytes').CounterSamples
    $e7Row=[ordered]@{
      utc=[DateTime]::UtcNow.ToString('o')
      worker_pid=$WorkerPid
      worker_private_bytes=$e7Watched.PrivateMemorySize64
      worker_peak_commit_bytes=$e7Watched.PeakPagedMemorySize64
      worker_working_set_bytes=$e7Watched.WorkingSet64
      worker_peak_working_set_bytes=$e7Watched.PeakWorkingSet64
      system_commit_bytes=[long]$e7Counters[0].CookedValue
      system_commit_limit_bytes=[long]$e7Counters[1].CookedValue
      system_available_mb=[long]$e7Counters[2].CookedValue
    }
    $e7Row | ConvertTo-Json -Compress | Add-Content -LiteralPath $Output -Encoding utf8
    $e7SampleCount++
    if ($MaxSamples -gt 0 -and $e7SampleCount -ge $MaxSamples) { break }
    if ($e7Watched.WaitForExit($IntervalMs)) { break }
  }
} finally {
  $e7Watched.Dispose()
}
[pscustomobject]@{samples=$e7SampleCount;output=$Output;worker_pid=$WorkerPid} | ConvertTo-Json -Compress
