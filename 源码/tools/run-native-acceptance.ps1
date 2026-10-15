param([string]$Runtime='', [ValidateSet('All','Runtime','MR','CT','Measurements','Bookmarks','Display','Libraries','Shutdown')][string]$Suite='All', [switch]$UseBat)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if (!$Runtime) { $Runtime=Join-Path $root 'runtime' }
$Runtime=[System.IO.Path]::GetFullPath($Runtime)
$exe=Join-Path $Runtime 'CT3D.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Native CT3D launcher is missing; cannot accept source-only work' }
if ($UseBat -and $Runtime -ne [System.IO.Path]::GetFullPath((Join-Path $root 'runtime'))) { throw 'Main BAT always targets the n2 runtime' }
$env:CT3D_WORKSPACE_ROOT=$root
$env:CT3D_ACCEPTANCE_RUNTIME=$Runtime
$env:CT3D_TEST_SCRIPT_PREFLIGHT=$null
$env:PYTHONHOME=$null
$env:PYTHONPATH=$null
$env:DASHBOARD_TEST_FROM_CTEST='1'
$out=Join-Path $root 'verification/native-acceptance'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$cases=@(
    @{suite='Runtime';script='verify_native_runtime.py';result='native-runtime/results.json'},
    @{suite='MR';script='verify_native_review.py';result='native-review/results.json'},
    @{suite='CT';script='verify_native_ct.py';result='native-ct/ct-workflow.json'},
    @{suite='Measurements';script='verify_native_measurements.py';result='native-measurements/results.json'},
    @{suite='Bookmarks';script='verify_bookmarks.py';result='bookmarks/results.json'},
    @{suite='Display';script='verify_display_quality.py';result='display-quality-20261006/results.json'},
    @{suite='Libraries';script='verify_library_paths.py';result='library-paths-results.json'},
    @{suite='Shutdown';script='verify_native_shutdown.py';result='native-shutdown/results.json'}
)
$results=@()
foreach ($case in $cases) {
    if ($Suite -ne 'All' -and $case.suite -ne $Suite) { continue }
    $script=Join-Path $PSScriptRoot $case.script
    $env:CT3D_ACCEPTANCE_SCRIPT=$script
    $entryScript=Join-Path $PSScriptRoot 'native-acceptance-entry.py'
    $report=Join-Path (Join-Path $root 'verification') $case.result
    if (Test-Path -LiteralPath $report) {
        Copy-Item -LiteralPath $report -Destination (Join-Path $out ($case.suite+'-previous-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json'))
    }
    $started=Get-Date
    if ($UseBat) {
        # Exercise the same Chinese-named entry the user double-clicks.
        $batch=Join-Path $root '启动 CT3D.bat'
        if (!(Test-Path -LiteralPath $batch)) { throw 'User-facing BAT entry is missing' }
        $command='""'+$batch+'" --testing --python-script "'+$entryScript+'""'
        $process=Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/s','/c',$command) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out ($case.suite+'-stdout.log')) -RedirectStandardError (Join-Path $out ($case.suite+'-stderr.log'))
    } else {
        $process=Start-Process -FilePath $exe -ArgumentList @('--testing','--no-splash','--python-script',('"'+$entryScript+'"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out ($case.suite+'-stdout.log')) -RedirectStandardError (Join-Path $out ($case.suite+'-stderr.log'))
    }
    # Launcher exit can precede the application's exit. Require a fresh JSON report.
    $deadline=$started.AddMinutes(10)
    $fresh=$false
    do {
        Start-Sleep -Seconds 2
        $fresh=(Test-Path -LiteralPath $report) -and (Get-Item -LiteralPath $report).LastWriteTime -ge $started
        if ($fresh) {
            try { $data=Get-Content -LiteralPath $report -Raw | ConvertFrom-Json; $fresh=$data.status -in @('passed','failed') } catch { $fresh=$false }
        }
    } while (!$fresh -and (Get-Date) -lt $deadline)
    if (!$fresh) { throw ('No completed native report for '+$case.suite+'; inspect the CT3D process and application log') }
    # The script writes its report before Qt/VTK teardown. A passed report is
    # insufficient if a shutdown dialog keeps the launcher alive.
    $normalExit=$process.WaitForExit(30000)
    if (!$normalExit -or $process.ExitCode -ne 0) {
        $exitCode=if($normalExit){$process.ExitCode}else{$null}
        @{status='failed_exit_lifecycle';suite=$case.suite;launcher_pid=$process.Id;report=$report;exit_code=$exitCode;exited=$normalExit;checked_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out ($case.suite+'-exit-failure.json')) -Encoding utf8
        throw ('Native '+$case.suite+' report completed but the launcher did not exit successfully. Check shutdown diagnostics; do not start another suite.')
    }
    $results+=@{suite=$case.suite;status=$data.status;checks=@($data.checks).Count;report=$report;started_at=$started.ToString('o');elapsed_seconds=[math]::Round(((Get-Date)-$started).TotalSeconds,2);entry=$(if($UseBat){'main_bat'}else{'native_exe'});entry_path=$(if($UseBat){$batch}else{$exe});exit_code=$process.ExitCode;process_exit_verified=$true}
    $results | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'results.json') -Encoding utf8
    Write-Output ($case.suite+': '+$data.status+' ('+@($data.checks).Count+' checks)')
    if ($data.status -ne 'passed') { throw ('Native acceptance failed: '+$case.suite) }
    Start-Sleep -Seconds 2
}
