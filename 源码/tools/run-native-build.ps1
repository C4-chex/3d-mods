param([ValidateRange(1,16)][int]$Jobs=4)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$out=Join-Path $root 'verification'
@{phase='Build';status='running';started_at=(Get-Date).ToString('o');pid=$PID;parallel_projects=$Jobs;compiler_parallelism=2} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'native-build-result.json') -Encoding utf8
$code=1
try {
    & (Join-Path $PSScriptRoot 'native-build.ps1') -Action Build -Jobs $Jobs *> (Join-Path $out 'native-build.log')
    $code=$LASTEXITCODE
} catch { $_ | Out-String | Add-Content -LiteralPath (Join-Path $out 'native-build.log') -Encoding utf8 }
@{phase='Build';status= $(if($code -eq 0){'passed'}else{'failed'});exit_code=$code;completed_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'native-build-result.json') -Encoding utf8
exit $code
