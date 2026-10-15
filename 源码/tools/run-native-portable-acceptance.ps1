param([string]$Runtime='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if (!$Runtime) { $Runtime=Join-Path $root 'runtime' }
$Runtime=[System.IO.Path]::GetFullPath($Runtime)
if (!(Test-Path -LiteralPath (Join-Path $Runtime 'CT3D.exe'))) { throw 'Packaged CT3D runtime is missing' }
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$out=Join-Path $root ('verification/portable-acceptance-'+$stamp)
New-Item -ItemType Directory -Path $out | Out-Null
# A complete copy checks relocation, spaces and non-ASCII paths without
# renaming or removing the original candidate runtime.
$relocated=Join-Path $out '独立程序 中文路径/runtime'
$statePath=Join-Path $out 'results.json'
$checks=@()
function Save-State([string]$Status,[string]$Phase,[string]$Detail='') {
    @{status=$Status;phase=$Phase;detail=$Detail;runtime=$relocated;original_runtime=$Runtime;checks=$checks;updated_at=(Get-Date).ToString('o')} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding utf8
}
$phase='copying_runtime'
try {
    Save-State 'running' $phase
    $destination=[System.IO.Path]::GetFullPath($relocated)
    $allowed=[System.IO.Path]::GetFullPath((Join-Path $root 'verification')).TrimEnd('\')+'\'
    if (!$destination.StartsWith($allowed,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Portable check target must stay inside verification' }
    New-Item -ItemType Directory -Path $relocated -Force | Out-Null
    Get-ChildItem -LiteralPath $Runtime -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $relocated -Recurse -Force }
    foreach ($suite in @('Runtime','MR','CT')) {
        $phase='accepting_'+$suite
        Save-State 'running' $phase
        & (Join-Path $PSScriptRoot 'run-native-acceptance.ps1') -Runtime $relocated -Suite $suite
        $report=Get-Content -LiteralPath (Join-Path $root 'verification/native-acceptance/results.json') -Raw | ConvertFrom-Json
        $checks+=@{suite=$suite;status=$report.status;checks=$report.checks;entry_path=$report.entry_path}
        Copy-Item -LiteralPath (Join-Path $root 'verification/native-acceptance/results.json') -Destination (Join-Path $out ($suite+'-acceptance.json'))
        $evidence= switch($suite) { 'Runtime' {'native-runtime'} 'MR' {'native-review'} 'CT' {'native-ct'} }
        Copy-Item -LiteralPath (Join-Path $root ('verification/'+$evidence)) -Destination (Join-Path $out $evidence) -Recurse
    }
    Save-State 'automated_checks_passed' 'awaiting_visual_and_clean_machine_review'
} catch {
    Save-State 'failed' $phase $_.Exception.Message
    throw
}
Write-Output $statePath
