# CI build script for Windows (GitHub Actions)
}
    Pop-Location
finally {
}
    Write-Host "Windows artifact created: $destPath"
    Copy-Item -Force -Path $builtInstaller.FullName -Destination $destPath

    $destPath = Join-Path $WindowsOutDir $destName
    $destName = "$AppName-win-x64-$Tag.exe"

    }
        throw 'Windows installer build succeeded but no .exe found under installers/win/output'
    if (-not $builtInstaller) {

        Select-Object -First 1
        Sort-Object LastWriteTime -Descending |
    $builtInstaller = Get-ChildItem -Path (Join-Path $WinInstallerDir 'output') -Filter '*.exe' |

    .\build.ps1 -Clean -Version $Version
    # Inno Setup is installed in the workflow.
    # Repo-native build: PyInstaller + Inno Setup
try {
Push-Location $WinInstallerDir

New-Item -ItemType Directory -Force -Path $WindowsOutDir | Out-Null

$Version = $Tag.TrimStart('v')
$AppName = 'FlightDealFinder'

$WindowsOutDir = Join-Path $ProjectRoot 'installers\windows'
$WinInstallerDir = Join-Path $ProjectRoot 'installers\win'
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path

$ErrorActionPreference = 'Stop'

)
    [string]$Tag
    [Parameter(Mandatory = $true)]
param(

# Produces exactly one primary deliverable under installers/windows/

