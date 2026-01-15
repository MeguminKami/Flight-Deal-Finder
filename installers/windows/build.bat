@echo off
REM =============================================================================
REM Flight Deal Finder - Windows Build Script (Batch wrapper)
REM =============================================================================
REM This is a convenience wrapper for build.ps1
REM Double-click to run, or use from command line
REM =============================================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo        Flight Deal Finder - Windows Build Script
echo ============================================================
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check for PowerShell
where powershell >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: PowerShell not found!
    echo Please ensure PowerShell is installed and in PATH.
    pause
    exit /b 1
)

REM Parse arguments
set "PS_ARGS="
:parse_args
if "%~1"=="" goto run_build
if /i "%~1"=="--clean" set "PS_ARGS=%PS_ARGS% -Clean"
if /i "%~1"=="--skip-build" set "PS_ARGS=%PS_ARGS% -SkipBuild"
if /i "%~1"=="--skip-installer" set "PS_ARGS=%PS_ARGS% -SkipInstaller"
if /i "%~1"=="--verbose" set "PS_ARGS=%PS_ARGS% -Verbose"
if /i "%~1"=="--version" set "PS_ARGS=%PS_ARGS% -Version %~2" & shift
shift
goto parse_args

:run_build
REM Run PowerShell build script
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build.ps1" %PS_ARGS%

if %ERRORLEVEL% neq 0 (
    echo.
    echo Build failed with error code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Build completed successfully!
echo.

REM Pause only if double-clicked (no arguments)
if "%~1"=="" pause

exit /b 0

