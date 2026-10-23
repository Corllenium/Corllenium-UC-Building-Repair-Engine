param([string]$RuntimePath = (Join-Path $PSScriptRoot '../../docs/superpowers/records/scripts/main-infra/live-worker-status-runtime.ps1'))
$ErrorActionPreference='Stop'
$tokens=$null;$parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($RuntimePath,[ref]$tokens,[ref]$parseErrors)
if($parseErrors.Count){throw 'Runtime must parse'}
$fn=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-UcStatusPublication'},$true)
if(-not $fn){throw 'Missing retry-safe publication function'}
Invoke-Expression $fn.Extent.Text
$taskRoot='D:/status-retry-fixture'
function Assert([bool]$Condition,[string]$Message){if(-not $Condition){throw $Message}}
function Reset-Fixture {
 $global:UploadCode=0;$global:PublishCode=0;$global:UploadThrows=$false
 $global:Uploads=0;$global:Publishes=0;$global:UploadArgs=@();$global:PublishArgs=@();$global:LASTEXITCODE=0
}
function global:scp {
 $global:Uploads++;$global:UploadArgs=@($args)
 if($global:UploadThrows){throw 'Fixture connection exception'}
 $global:LASTEXITCODE=$global:UploadCode
 'fixture upload output'
}
function global:ssh {
 $global:Publishes++;$global:PublishArgs=@($args);$global:LASTEXITCODE=$global:PublishCode
 'fixture remote output'
}
Reset-Fixture
$global:UploadCode=255
$first=Invoke-UcStatusPublication
Assert (-not $first.Succeeded -and $first.Stage -eq 'upload' -and $first.ExitCode -eq 255) 'Upload error must be reported'
Assert ($global:Publishes -eq 0) 'Failed upload must not execute remote publisher'
$global:UploadCode=0
$second=Invoke-UcStatusPublication
Assert ($second.Succeeded -and $global:Uploads -eq 2 -and $global:Publishes -eq 1) 'Later iteration must recover after transient upload failure'
Reset-Fixture
$global:PublishCode=255
$result=Invoke-UcStatusPublication
Assert (-not $result.Succeeded -and $result.Stage -eq 'publish' -and $result.ExitCode -eq 255) 'Remote timeout must remain retryable without false success'
Reset-Fixture
$global:UploadThrows=$true
$result=Invoke-UcStatusPublication
Assert (-not $result.Succeeded -and $global:Publishes -eq 0) 'Command exception must be retryable and fail closed'
Reset-Fixture
$result=Invoke-UcStatusPublication
Assert ($result.Succeeded -and $result.ExitCode -eq 0 -and $global:Uploads -eq 1 -and $global:Publishes -eq 1) 'Success requires upload and remote publisher'
Assert ($global:UploadArgs -contains 'ConnectTimeout=10' -and $global:PublishArgs -contains 'ConnectTimeout=10') 'Both network commands need bounded connection timeouts'
Assert ($global:UploadArgs -contains 'ServerAliveCountMax=1' -and $global:PublishArgs -contains 'ServerAliveCountMax=1') 'Both network commands need bounded keepalive failures'
$source=[IO.File]::ReadAllText($RuntimePath)
Assert (-not $source.Contains('1F E3 preservation PASS')) 'Global status must not assert the withdrawn earlier pass'
Assert ($source.Contains("throw 'Worker PID changed; refusing stale publication'") -and $source.Contains("throw 'Canonical progress validation failed'")) 'Identity and canonical-validation failures must remain terminal'
'PASS: upload failure, retry recovery, remote failure, exception, success, bounded networking and retained identity guards'
