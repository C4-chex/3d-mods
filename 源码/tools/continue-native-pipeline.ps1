param([switch]$RefreshConfiguration)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$out=Join-Path $root 'verification'
$result=Join-Path $out 'native-pipeline-result.json'
$started=(Get-Date).ToString('o')
function Write-PipelineState([string]$Phase,[string]$Status,[string]$Detail='') {
    @{phase=$Phase;status=$Status;detail=$Detail;pid=$PID;started_at=$started;updated_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $result -Encoding utf8
}
$phase='waiting_for_build'
try {
    Write-PipelineState $phase 'running'
    do {
        $build=Get-Content -LiteralPath (Join-Path $out 'native-build-result.json') -Raw | ConvertFrom-Json
        if ($build.status -eq 'paused_by_user') {
            Write-PipelineState $phase 'paused_by_user' 'Build is paused. Resume the build before restarting this pipeline.'
            return
        }
        if ($build.status -notin @('running','passed','failed')) { throw ('Unrecognized native build status: '+$build.status) }
        if ($build.status -eq 'running' -and (!(Get-Process -Id $build.pid -ErrorAction SilentlyContinue))) { throw 'Build status is stale: the recorded build process no longer exists' }
        if ($build.status -eq 'failed') { throw 'Native build failed; inspect native-build.log before continuing' }
        if ($build.status -ne 'passed') { Start-Sleep -Seconds 3 }
    } while ($build.status -ne 'passed')
    if ($RefreshConfiguration) {
        # Finish the current build before changing its generated configuration.
        Copy-Item -LiteralPath (Join-Path $out 'native-build.log') -Destination (Join-Path $out 'native-build-before-configuration-refresh.log')
        Copy-Item -LiteralPath (Join-Path $out 'native-build-result.json') -Destination (Join-Path $out 'native-build-before-configuration-refresh.json')
        $phase='refreshing_configuration'
        Write-PipelineState $phase 'running'
        & (Join-Path $PSScriptRoot 'native-build.ps1') -Action Configure *> (Join-Path $out 'native-configuration-refresh.log')
        if ($LASTEXITCODE -ne 0) { throw 'Native configuration refresh failed' }
        $phase='building_refreshed_configuration'
        Write-PipelineState $phase 'running'
        & (Join-Path $PSScriptRoot 'run-native-build.ps1') -Jobs 4
        if ($LASTEXITCODE -ne 0) { throw 'Native incremental rebuild after configuration refresh failed' }
    }
    $phase='packaging'
    Write-PipelineState $phase 'running'
    & (Join-Path $PSScriptRoot 'native-build.ps1') -Action Package *> (Join-Path $out 'native-package.log')
    if ($LASTEXITCODE -ne 0) { throw 'Native runtime packaging failed' }
    $phase='reference_preparation'
    Write-PipelineState $phase 'running'
    $python=Join-Path $root 'b/python-install/bin/PythonSlicer.exe'
    & $python (Join-Path $PSScriptRoot 'prepare-native-mr-reference.py') *> (Join-Path $out 'native-reference.log')
    if ($LASTEXITCODE -ne 0) { throw 'Independent MR pixel reference preparation failed' }
    $phase='automated_functional_acceptance'
    Write-PipelineState $phase 'running'
    & (Join-Path $PSScriptRoot 'run-native-acceptance.ps1') -Suite All *> (Join-Path $out 'native-acceptance.log')
    Copy-Item -LiteralPath (Join-Path $out 'native-acceptance/results.json') -Destination (Join-Path $out 'native-acceptance/all-suites.json')
    $phase='main_bat_acceptance'
    Write-PipelineState $phase 'running'
    & (Join-Path $PSScriptRoot 'run-native-acceptance.ps1') -Suite Runtime -UseBat *> (Join-Path $out 'native-bat-acceptance.log')
    Copy-Item -LiteralPath (Join-Path $out 'native-acceptance/results.json') -Destination (Join-Path $out 'native-acceptance/main-bat.json')
    $phase='preserving_original_acceptance'
    Write-PipelineState $phase 'running'
    $evidence=Join-Path $out ('native-acceptance/original-runtime-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $evidence | Out-Null
    foreach ($directory in @('native-runtime','native-review','native-ct','native-measurements','bookmarks','display-quality-20261006','native-shutdown')) {
        Copy-Item -LiteralPath (Join-Path $out $directory) -Destination (Join-Path $evidence $directory) -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $out 'library-paths-results.json') -Destination $evidence
    $phase='portable_relocation_acceptance'
    Write-PipelineState $phase 'running'
    & (Join-Path $PSScriptRoot 'run-native-portable-acceptance.ps1') *> (Join-Path $out 'native-portable-acceptance.log')
    Write-PipelineState 'awaiting_visual_and_clean_machine_review' 'automated_checks_passed' 'Inspect actual screenshots and perform clean-machine acceptance before declaring the release accepted.'
} catch {
    Write-PipelineState $phase 'failed' $_.Exception.Message
    throw
}
