# Flight Deal Finder - Windows Installer Build

This directory contains all the files needed to build a professional Windows installer for Flight Deal Finder.

## 📋 Overview

### Packaging Path Chosen: **Standalone Executable + Installer**

**Approach:** Use PyInstaller to bundle Python and all dependencies into a standalone executable, then wrap it with an Inno Setup wizard installer.

**Why this approach:**
| Pros | Cons |
|------|------|
| ✅ No Python installation required on target machine | ❌ Larger installer size (~50-100MB) |
| ✅ Works on any Windows 10/11 x64 machine | ❌ Slightly longer startup time |
| ✅ Professional wizard-based installation | |
| ✅ Proper uninstaller in Windows Apps & Features | |
| ✅ Start Menu and Desktop shortcuts | |
| ✅ Easy CI/CD integration | |
| ✅ Industry-standard tooling | |

## 🛠 Tooling

| Tool | Purpose | Version |
|------|---------|---------|
| **PyInstaller** | Bundle Python app into standalone executable | Latest |
| **Inno Setup 6** | Create wizard-based Windows installer | 6.x |
| **PowerShell** | Build automation script | 5.1+ |

## 📁 Files

```
installers/win/
├── FlightDealFinder.spec   # PyInstaller specification file
├── installer.iss           # Inno Setup installer script
├── build.ps1               # PowerShell build script
├── build.bat               # Batch wrapper (double-click friendly)
├── version_info.txt        # Windows version info for EXE
├── icon.ico                # Application icon
├── LICENSE.txt             # License file for installer
└── README.md               # This file
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.10+** installed and in PATH
2. **Inno Setup 6** installed from [jrsoftware.org](https://jrsoftware.org/isdl.php)

### Build the Installer

**Option 1: Double-click** (easiest)
```
Double-click build.bat
```

**Option 2: PowerShell**
```powershell
cd installers\win
.\build.ps1
```

**Option 3: With options**
```powershell
# Clean build
.\build.ps1 -Clean

# Verbose output
.\build.ps1 -Verbose

# Custom version
.\build.ps1 -Version "2.1.0"

# Skip steps
.\build.ps1 -SkipBuild      # Use existing dist
.\build.ps1 -SkipInstaller  # Only build EXE
```

### Output

After a successful build:
- **Installer:** `installers/win/output/FlightDealFinder_Setup_2.0.0_x64.exe`
- **Portable:** `installers/win/dist/FlightDealFinder/` (folder with all files)

## 📝 Build Steps (Manual)

If you prefer to run commands manually:

```powershell
# 1. Navigate to project root
cd C:\path\to\FlightSearchV2

# 2. Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# 3. Build with PyInstaller
cd installers\win
pyinstaller --noconfirm --clean --distpath dist --workpath build FlightDealFinder.spec

# 4. Build installer with Inno Setup
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /Ooutput installer.iss
```

## 🖥 Installer Features

### Wizard Pages

1. **Welcome Screen** - Branding and introduction
2. **License Agreement** - MIT License (user must accept)
3. **Directory Selection** - Default: `C:\Program Files\FlightDealFinder`
4. **Shortcut Selection**:
   - ☑ Create Start Menu shortcut (default: checked)
   - ☐ Create Desktop shortcut (default: unchecked)
5. **Ready to Install** - Summary before installation
6. **Installation Progress** - Progress bar
7. **Finish Screen** - Option to launch app immediately

### Uninstaller

- Listed in Windows Settings → Apps → Installed apps
- Removes all installed files
- Removes shortcuts
- **Optionally** removes user data from AppData (asks user)

## 🔐 Code Signing (Optional)

To avoid Windows SmartScreen warnings, sign the installer:

```powershell
# Sign the executable
signtool sign /f "certificate.pfx" /p "password" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "dist\FlightDealFinder\FlightDealFinder.exe"

# Sign the installer
signtool sign /f "certificate.pfx" /p "password" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "output\FlightDealFinder_Setup_2.0.0_x64.exe"
```

## 🔄 CI/CD Integration

A GitHub Actions workflow is provided at `.github/workflows/build-windows.yml`:

- **Trigger:** Push to main, tags starting with `v*`, or manual dispatch
- **Artifacts:** Uploads installer and portable build
- **Releases:** Automatically creates GitHub Release on version tags

To create a release:
```bash
git tag v2.0.0
git push origin v2.0.0
```

## ✅ Quality Checklist

### Common Pitfalls Avoided

| Issue | Solution |
|-------|----------|
| **UAC/Permissions** | `PrivilegesRequired=lowest` - installs per-user by default |
| **Program Files writing** | Uses `{autopf}` which respects user privileges |
| **Missing DLLs** | PyInstaller bundles all dependencies |
| **Antivirus false positives** | Code signing recommended; UPX compression used |
| **Firewall prompts** | App uses localhost for UI - typically no firewall needed |
| **Corrupted install** | Solid LZMA2 compression with integrity checks |

### Testing on Clean VM

1. Create a fresh Windows 10/11 VM (no Python installed)
2. Copy the installer to the VM
3. Run installer and verify:
   - [ ] Wizard pages display correctly
   - [ ] Can change installation directory
   - [ ] Shortcuts created as selected
   - [ ] App launches and works
   - [ ] App appears in Windows Apps list
   - [ ] Uninstaller removes all files
   - [ ] Shortcuts removed after uninstall

## 🔧 Customization

### Change Version

1. Update `version_info.txt` (filevers, prodvers, FileVersion, ProductVersion)
2. Update `installer.iss` (`#define AppVersion`)
3. Or pass `-Version` to build script: `.\build.ps1 -Version "2.1.0"`

### Change App Name/Publisher

Edit these files:
- `installer.iss`: `#define AppName`, `#define AppPublisher`
- `version_info.txt`: CompanyName, ProductName, etc.

### Add License

Replace `LICENSE.txt` with your license text. The installer shows this during installation.

### Change Icon

Replace `icon.ico` with your icon file (256x256, 128x128, 64x64, 48x48, 32x32, 16x16 sizes recommended).

## 📊 Expected Sizes

| Component | Approximate Size |
|-----------|------------------|
| Built EXE (in dist folder) | 15-25 MB |
| Full dist folder | 80-120 MB |
| Compressed installer | 40-60 MB |

## 🐛 Troubleshooting

### "Python not found"
Ensure Python is in your PATH: `python --version`

### "Inno Setup not found"
Install from https://jrsoftware.org/isdl.php or update path in build.ps1

### "Module not found" during PyInstaller
Add to `hiddenimports` in `.spec` file

### "DLL load failed" on target machine
Ensure the Visual C++ Redistributable is installed (usually bundled by PyInstaller)

### Antivirus blocks the build
Add exclusions for:
- Project folder
- PyInstaller temp folder (`%TEMP%\_MEI*`)
- dist/build folders

## 📚 Resources

- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
- [Inno Setup Documentation](https://jrsoftware.org/ishelp/)
- [NiceGUI + PyInstaller](https://nicegui.io/documentation/section_configuration_deployment#package_for_installation)

