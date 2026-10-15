param([ValidateSet('Configure','Build','Package')][string]$Action='Configure',[int]$Jobs=4,[string]$Qt5Dir='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$cmake=Join-Path $root 'build-support/python-tools/cmake/data/bin/cmake.exe'
$qt=$Qt5Dir
if (!$qt) { $qt=Join-Path (Split-Path -Parent $root) 'in-need/Qt/5.15.2/msvc2019_64/lib/cmake/Qt5' }
if (!(Test-Path -LiteralPath $cmake)) { throw 'Project CMake not installed' }
$existing=& subst
if (Test-Path 'R:\') {
    if (!(Test-Path 'R:\desktop/upstream-lock.json') -or [System.IO.File]::ReadAllText('R:\desktop/upstream-lock.json') -ne [System.IO.File]::ReadAllText((Join-Path $root 'desktop/upstream-lock.json'))) { throw 'R drive belongs to another workspace' }
} else { & subst R: $root; if ($LASTEXITCODE) { throw 'Cannot create short workspace path' } }
$env:CMAKE_TLS_VERIFY='1'
$env:CMAKE_BUILD_PARALLEL_LEVEL=[string]$Jobs
$env:VSLANG='1033'
if ($env:CL -notmatch '(?i)(^|\s)/MP\d*(\s|$)') { $env:CL=($env:CL+' /MP2').Trim() }
$env:GIT_CONFIG_COUNT='1'
$env:GIT_CONFIG_KEY_0='http.version'
$env:GIT_CONFIG_VALUE_0='HTTP/1.1'
$env:PATH='D:\Git\cmd;D:\Git\usr\bin;'+$env:PATH
# Avoid detecting unrelated Python installs in this build process only.
$env:PYTHONHOME=$null
$env:PYTHONPATH=$null
if ($Action -eq 'Configure') {
    if (!(Test-Path -LiteralPath (Join-Path $qt 'Qt5Config.cmake'))) { throw 'Qt installation incomplete' }
    & $cmake -C R:/build-support/local-dependencies.cmake -S R:/desktop -B R:/b -G 'Visual Studio 17 2022' -A x64 "-DQt5_DIR:PATH=$qt" -Dslicersources_SOURCE_DIR:PATH=R:/core -DCMAKE_CONFIGURATION_TYPES:STRING=Release -DSlicer_BUILD_WIN32_CONSOLE:BOOL=OFF -DPatch_EXECUTABLE:FILEPATH=D:/Git/usr/bin/patch.exe -DSlicer_CMake_HTTPS_Supported:BOOL=ON
} elseif ($Action -eq 'Build') {
    & $cmake --build R:/b --config Release --parallel $Jobs
} else {
    & (Join-Path $PSScriptRoot 'package-native.ps1')
}
exit $LASTEXITCODE
