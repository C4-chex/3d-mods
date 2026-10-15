$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $packageRoot 'dist'
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$outputZip = Join-Path $outputDirectory 'CT3D-desktop-source.zip'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$files = @('README.md','RELEASE.md','CT3D_产品原则.md','.gitignore','.gitattributes','launch.bat','启动 CT3D.bat','input/README.md','output/README.md')
foreach ($directory in @('CT3D','ct part/CT3DCTLib')) {
    $files += Get-ChildItem -LiteralPath (Join-Path $packageRoot $directory) -Recurse -File -Filter '*.py' | ForEach-Object { $_.FullName.Substring($packageRoot.Length + 1) }
}
$files += Get-ChildItem -LiteralPath (Join-Path $packageRoot 'docs') -File | Where-Object { $_.Extension -in @('.md','.json') } | ForEach-Object { $_.FullName.Substring($packageRoot.Length + 1) }
$files += 'tools/package-release.ps1'
$files += Get-ChildItem -LiteralPath (Join-Path $packageRoot 'tools') -File -Filter 'verify_*.py' | ForEach-Object { $_.FullName.Substring($packageRoot.Length + 1) }
$files += 'AGENTS.md'
$files += 'LICENSE-INFO.txt'
$files += 'CT3D/CMakeLists.txt'
$files += 'tools/build-standalone.ps1'
$files += @('tools/native-build.ps1','tools/run-native-build.ps1','tools/package-native.ps1','tools/run-native-acceptance.ps1','tools/cache-build-dependencies.py','tools/apply-dependency-cache.py','tools/cache-ctk-dependencies.py','tools/archive-version-metadata.py')
$files += 'tools/prepare-native-mr-reference.py'
$files += 'tools/continue-native-pipeline.ps1'
$files += 'tools/run-native-portable-acceptance.ps1'
$files += 'tools/prepare-archive-metadata.py'
$files += 'tools/native-acceptance-entry.py'
$files += 'tools/package-slice-stack.py'
foreach ($sourceDirectory in @('desktop','licenses')) {
  $files += Get-ChildItem -LiteralPath (Join-Path $packageRoot $sourceDirectory) -Recurse -File | ForEach-Object { $_.FullName.Substring($packageRoot.Length + 1) }
}
$stream = [System.IO.File]::Open($outputZip, [System.IO.FileMode]::Create)
$archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relativeFile in ($files | Sort-Object -Unique)) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $packageRoot $relativeFile), ($relativeFile -replace '\\','/')) | Out-Null
    }
} finally { $archive.Dispose(); $stream.Dispose() }
Write-Output $outputZip
