param([string]$Configuration='Release')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$cpack=Join-Path $root 'build-support/python-tools/cmake/data/bin/cpack.exe'
$config=Join-Path $root 'b/Slicer-build/CPackConfig.cmake'
if (!(Test-Path -LiteralPath $config)) { throw 'Native application configuration is not available yet' }
$output=Join-Path $root 'dist/native'
New-Item -ItemType Directory -Path $output -Force | Out-Null
# CPack runs Slicer's runtime component installation and dependency fixup.
# A plain cmake --install omits the bundle dependency collection workflow.
& $cpack --config $config -C $Configuration -G ZIP -B $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$zip=Get-ChildItem -LiteralPath $output -Filter '*.zip' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (!$zip) { throw 'CPack did not produce a portable archive' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
$stage=Join-Path $root ('runtime-stage-'+$stamp)
$packageRoot=[System.IO.Path]::GetFullPath($root).TrimEnd('\')+'\'
New-Item -ItemType Directory -Path $stage | Out-Null
$archive=[System.IO.Compression.ZipFile]::OpenRead($zip.FullName)
try {
    foreach ($entry in $archive.Entries) {
        $target=[System.IO.Path]::GetFullPath((Join-Path $stage $entry.FullName))
        if (!$target.StartsWith($stage+'\',[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path escapes staging directory' }
    }
    $launchers=@($archive.Entries | Where-Object { $_.Name -eq 'CT3D.exe' -and ($_.FullName -split '/').Count -le 2 })
    if ($launchers.Count -ne 1) { throw 'Expected exactly one main CT3D launcher in the package' }
    $relativeLauncher=$launchers[0].FullName
} finally { $archive.Dispose() }
[System.IO.Compression.ZipFile]::ExtractToDirectory($zip.FullName,$stage)
$source=Split-Path -Parent (Join-Path $stage $relativeLauncher)
$runtime=Join-Path $root 'runtime'
# Check all move targets explicitly; preserve previous runtime rather than deleting it.
foreach ($path in @($source,$runtime)) {
    $absolute=[System.IO.Path]::GetFullPath($path)
    if (!$absolute.StartsWith($packageRoot,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime target escapes n2' }
}
if (Test-Path -LiteralPath $runtime) {
    $old=Join-Path $root ('runtime-previous-'+$stamp)
    Move-Item -LiteralPath $runtime -Destination $old
}
Move-Item -LiteralPath $source -Destination $runtime
@{ status='packaged_not_accepted'; archive=$zip.FullName; sha256=(Get-FileHash -LiteralPath $zip.FullName -Algorithm SHA256).Hash; runtime=$runtime; created_at=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'verification/native-package-result.json') -Encoding utf8
Write-Output 'Portable runtime staged. Executable acceptance is still required.'
