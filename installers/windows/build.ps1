# Flight Deal Finder - Windows Build Script
# PowerShell script for building the Windows installer
# Version: 2.0.0

param(
    [switch]$SkipBuild,      # Skip PyInstaller build (use existing dist)
    [switch]$SkipInstaller,  # Skip Inno Setup compilation
    [switch]$Clean,          # Clean build directories before building
    [switch]$Verbose,        # Enable verbose output
    [string]$Version = "2.0.0"  # Version override
)

# =============================================================================
# Configuration
# =============================================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Speed up web requests

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..\..").Path
$InstallerDir = $ScriptDir
$DistDir = "$InstallerDir\dist"
$BuildDir = "$InstallerDir\build"
$OutputDir = "$InstallerDir\output"

$AppName = "FlightDealFinder"
$SpecFile = "$InstallerDir\$AppName.spec"
$IssFile = "$InstallerDir\installer.iss"

# Colors for output
function Write-Status { param($Message) Write-Host "[*] $Message" -ForegroundColor Cyan }
function Write-Success { param($Message) Write-Host "[+] $Message" -ForegroundColor Green }
function Write-Warning { param($Message) Write-Host "[!] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[-] $Message" -ForegroundColor Red }

# =============================================================================
# Functions
# =============================================================================

function Test-Command {
    param($Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

function Install-Requirements {
    Write-Status "Checking Python requirements..."

    # Install/upgrade pip
    python -m pip install --upgrade pip --quiet

    # Install project requirements
    if (Test-Path "$ProjectRoot\requirements.txt") {
        Write-Status "Installing project dependencies..."
        python -m pip install -r "$ProjectRoot\requirements.txt" --quiet
    }

    # Install PyInstaller
    Write-Status "Installing/upgrading PyInstaller..."
    python -m pip install --upgrade pyinstaller --quiet

    Write-Success "Requirements installed"
}

function Clean-BuildDirs {
    Write-Status "Cleaning build directories..."

    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
    if (Test-Path $OutputDir) { Remove-Item -Recurse -Force $OutputDir }

    # Also clean __pycache__
    Get-ChildItem -Path $ProjectRoot -Filter "__pycache__" -Recurse -Directory |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-Success "Build directories cleaned"
}

function Build-Executable {
    Write-Status "Building executable with PyInstaller..."

    # Create output directory
    if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
    if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }

    # Run PyInstaller
    $pyinstallerArgs = @(
        "--noconfirm"
        "--clean"
        "--distpath", $DistDir
        "--workpath", $BuildDir
        $SpecFile
    )

    if ($Verbose) {
        $pyinstallerArgs += "--log-level=DEBUG"
    }

    Write-Status "Running: pyinstaller $($pyinstallerArgs -join ' ')"

    Push-Location $ProjectRoot
    try {
        & pyinstaller @pyinstallerArgs
        if ($LASTEXITCODE -ne 0) {
            throw "PyInstaller failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    # Verify output
    $exePath = "$DistDir\$AppName\$AppName.exe"
    if (-not (Test-Path $exePath)) {
        throw "Build failed: $exePath not found"
    }

    $exeSize = (Get-Item $exePath).Length / 1MB
    Write-Success "Executable built: $exePath ({0:N2} MB)" -f $exeSize
}

function Build-Installer {
    Write-Status "Building installer with Inno Setup..."

    # Find Inno Setup
    $isccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe"
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    $iscc = $null
    foreach ($path in $isccPaths) {
        if (Test-Path $path) {
            $iscc = $path
            break
        }
    }

    if (-not $iscc) {
        Write-Error "Inno Setup not found!"
        Write-Host ""
        Write-Host "Please install Inno Setup 6 from: https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
        Write-Host ""
        throw "Inno Setup not installed"
    }

    Write-Status "Using Inno Setup: $iscc"

    # Create output directory
    if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }

    # Compile installer
    $isccArgs = @(
        "/O$OutputDir"
        "/DAppVersion=$Version"
        $IssFile
    )

    if ($Verbose) {
        $isccArgs = @("/V9") + $isccArgs
    } else {
        $isccArgs = @("/Q") + $isccArgs
    }

    Push-Location $InstallerDir
    try {
        & $iscc @isccArgs
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    # Find output file
    $installerFile = Get-ChildItem -Path $OutputDir -Filter "*.exe" | Select-Object -First 1
    if (-not $installerFile) {
        throw "Installer build failed: no output file found"
    }

    $installerSize = $installerFile.Length / 1MB
    Write-Success "Installer built: $($installerFile.FullName) ({0:N2} MB)" -f $installerSize

    return $installerFile.FullName
}

function Show-Summary {
    param($InstallerPath)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "                  BUILD COMPLETED SUCCESSFULLY              " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Installer: " -NoNewline
    Write-Host $InstallerPath -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Version:   " -NoNewline
    Write-Host $Version -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Test the installer on a clean Windows VM"
    Write-Host "  2. Sign the installer with a code signing certificate"
    Write-Host "  3. Upload to your distribution channel"
    Write-Host ""
}

# =============================================================================
# Main Script
# =============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "        Flight Deal Finder - Windows Build Script           " -ForegroundColor Cyan
Write-Host "                     Version $Version                        " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Status "Checking prerequisites..."

if (-not (Test-Command "python")) {
    throw "Python not found in PATH. Please install Python 3.10+ from python.org"
}

$pythonVersion = python --version 2>&1
Write-Status "Python version: $pythonVersion"

# Clean if requested
if ($Clean) {
    Clean-BuildDirs
}

# Install requirements
Install-Requirements

# Build executable
if (-not $SkipBuild) {
    Build-Executable
} else {
    Write-Warning "Skipping PyInstaller build (using existing dist)"
}

# Build installer
if (-not $SkipInstaller) {
    $installerPath = Build-Installer
    Show-Summary -InstallerPath $installerPath
} else {
    Write-Warning "Skipping Inno Setup build"
    Write-Success "PyInstaller build complete. Dist folder: $DistDir\$AppName"
}

