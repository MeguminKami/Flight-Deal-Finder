# CI build script for Windows (GitHub Actions)
# Produces exactly one primary deliverable under installers/win/output/

param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\").Path
$WinInstallerDir = Join-Path $ProjectRoot 'installers\win'
$WindowsOutDir = Join-Path $WinInstallerDir 'output'

$AppName = 'FlightDealFinder'
$Version = $Tag.TrimStart('v')

New-Item -ItemType Directory -Force -Path $WindowsOutDir | Out-Null

Push-Location $WinInstallerDir
try {
    # Repo-native build: PyInstaller + Inno Setup
    # Inno Setup is installed in the workflow.
    .\build.ps1 -Clean -Version $Version

    $builtInstaller = Get-ChildItem -Path (Join-Path $WinInstallerDir 'output') -Filter '*.exe' |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $builtInstaller) {
        throw 'Windows installer build succeeded but no .exe found under installers/win/output'
    }

    $destName = "$AppName-win-x64-$Tag.exe"
    $destPath = Join-Path $WindowsOutDir $destName

    Copy-Item -Force -Path $builtInstaller.FullName -Destination $destPath
    Write-Host "Windows artifact created: $destPath"
}
finally {
    Pop-Location
}
