param(
    [string]$Qt5Dir = $env:Qt5_DIR,
    [ValidateSet('Check','Configure','Build','Package')][string]$Action = 'Check',
    [int]$Jobs = 4
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$missing = @()
$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (!$cmake) {
    $localCmake=Join-Path $root 'build-support/python-tools/cmake/data/bin/cmake.exe'
    if (Test-Path -LiteralPath $localCmake) { $cmake=[pscustomobject]@{Source=$localCmake} }
}
if (!$Qt5Dir) { $Qt5Dir=Join-Path (Split-Path -Parent $root) 'in-need/Qt/5.15.2/msvc2019_64/lib/cmake/Qt5' }
$git = Get-Command git -ErrorAction SilentlyContinue
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$visualStudio = $null
if (Test-Path -LiteralPath $vswhere) {
    $visualStudio = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (!$cmake) { $missing += 'CMake (required by the pinned Slicer build)' }
if (!$git) { $missing += 'Git' }
if (!$visualStudio) { $missing += 'Visual Studio 2022 C++ Build Tools, x64 compiler and Windows SDK' }
if (!$Qt5Dir -or !(Test-Path -LiteralPath (Join-Path $Qt5Dir 'Qt5Config.cmake'))) { $missing += 'Qt5_DIR: matching Qt 5 development installation with Qt5Config.cmake' }
New-Item -ItemType Directory -Path (Join-Path $root 'verification') -Force | Out-Null
@{ action=$Action; ready=($missing.Count -eq 0); missing=$missing; independent_exe_exists=(Test-Path -LiteralPath (Join-Path $root 'runtime/CT3D.exe')); source=(Join-Path $root 'desktop') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'verification/standalone-preflight.json') -Encoding utf8
if ($missing.Count) {
    Write-Output ('Missing prerequisites: ' + ($missing -join '; '))
    exit 2
}
if ($Action -eq 'Check') { Write-Output 'Build prerequisites found. Compilation and runtime acceptance still required.'; exit 0 }
# Use the same build tree and cache as the logged native build.
& (Join-Path $PSScriptRoot 'native-build.ps1') -Action $Action -Jobs $Jobs -Qt5Dir $Qt5Dir
exit $LASTEXITCODE
