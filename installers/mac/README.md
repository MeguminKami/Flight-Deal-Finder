# Flight Deal Finder - macOS Installer Build

This directory contains all the files needed to build a macOS application bundle (`.app`) and DMG installer for Flight Deal Finder.

## 📋 Overview

### Packaging Path: **Standalone App Bundle + DMG Installer**

**Approach:** Use PyInstaller to bundle Python and all dependencies into a macOS `.app` bundle, then create a DMG disk image for distribution.

**Compatibility:**
- ✅ macOS 10.15+ (Catalina)
- ✅ MacBook 2020 and newer
- ✅ Intel Macs (x86_64)
- ✅ Apple Silicon Macs (arm64) - when built on Apple Silicon

| Pros | Cons |
|------|------|
| ✅ No Python installation required | ❌ Larger app size (~100-150MB) |
| ✅ Works on any supported Mac | ❌ Slightly longer startup time |
| ✅ Standard macOS app experience | ❌ Code signing requires Developer account |
| ✅ Drag-and-drop installation | |
| ✅ Proper app icon and metadata | |

## 🛠 Tooling

| Tool | Purpose | Installation |
|------|---------|--------------|
| **PyInstaller** | Bundle Python app into .app | `pip install pyinstaller` |
| **create-dmg** | Create DMG installer (optional) | `brew install create-dmg` |
| **hdiutil** | Fallback DMG creation | Built into macOS |

## 📁 Files

```
installers/mac/
├── FlightDealFinder.spec   # PyInstaller specification file
├── build.sh                # Build automation script
├── entitlements.plist      # Code signing entitlements
├── icon.icns               # macOS app icon (create from icon.png)
├── LICENSE.txt             # License file
└── README.md               # This file
```

## 🚀 Quick Start

### Prerequisites

1. **macOS 10.15+** (Catalina or newer)
2. **Python 3.10+** installed (via python.org or Homebrew)
3. **Xcode Command Line Tools**: `xcode-select --install`
4. **create-dmg** (optional): `brew install create-dmg`

### Build the Installer

```bash
# Make script executable
chmod +x build.sh

# Build app and DMG
./build.sh

# Build with options
./build.sh --clean          # Clean build
./build.sh --skip-dmg       # Only build .app, skip DMG
./build.sh --version 2.1.0  # Custom version
./build.sh --sign           # Sign the app (requires certificate)
```

### Output

After a successful build:
- **App Bundle:** `dist/FlightDealFinder.app`
- **DMG Installer:** `output/FlightDealFinder_2.0.0_macOS.dmg`

## 📝 Build Steps (Manual)

```bash
# 1. Navigate to project root
cd /path/to/FlightSearchV2

# 2. Install dependencies
pip3 install -r requirements.txt
pip3 install pyinstaller

# 3. Build with PyInstaller
cd installers/mac
python3 -m PyInstaller --noconfirm --clean --distpath dist --workpath build FlightDealFinder.spec

# 4. Create DMG (optional)
create-dmg \
    --volname "Flight Deal Finder" \
    --window-size 660 400 \
    --icon "FlightDealFinder.app" 180 190 \
    --app-drop-link 480 190 \
    "output/FlightDealFinder_2.0.0_macOS.dmg" \
    "dist/FlightDealFinder.app"
```

## 🍎 Creating the App Icon

macOS requires icons in `.icns` format. To create one:

### Option 1: Using iconutil (recommended)

```bash
# Create iconset directory
mkdir icon.iconset

# Add PNG files at required sizes (must be exact sizes)
# icon_16x16.png, icon_16x16@2x.png (32x32)
# icon_32x32.png, icon_32x32@2x.png (64x64)
# icon_128x128.png, icon_128x128@2x.png (256x256)
# icon_256x256.png, icon_256x256@2x.png (512x512)
# icon_512x512.png, icon_512x512@2x.png (1024x1024)

# Convert to icns
iconutil -c icns icon.iconset -o icon.icns
```

### Option 2: Using sips (simple)

```bash
# From a 1024x1024 PNG
sips -s format icns icon_1024.png --out icon.icns
```

### Option 3: Online converters
Use sites like https://cloudconvert.com/png-to-icns

## 🔐 Code Signing

To distribute the app without security warnings, you need to sign it with an Apple Developer certificate.

### Sign the App

```bash
# Set your signing identity
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"

# Build with signing
./build.sh --sign
```

### Manual Signing

```bash
# Sign the app bundle
codesign --force --deep --sign "$CODESIGN_IDENTITY" \
    --options runtime \
    --entitlements entitlements.plist \
    dist/FlightDealFinder.app

# Verify signature
codesign --verify --verbose dist/FlightDealFinder.app
```

## 📜 Notarization

For macOS 10.15+, apps must be notarized by Apple to run without security warnings.

### Prerequisites
- Apple Developer account ($99/year)
- App-specific password from appleid.apple.com

### Notarize

```bash
# Set environment variables
export APPLE_ID="your@email.com"
export APPLE_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export APPLE_TEAM_ID="XXXXXXXXXX"

# Build with notarization
./build.sh --sign --notarize
```

### Manual Notarization

```bash
# Submit for notarization
xcrun notarytool submit output/FlightDealFinder_2.0.0_macOS.dmg \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait

# Staple the ticket
xcrun stapler staple output/FlightDealFinder_2.0.0_macOS.dmg
```

## 🔄 CI/CD Integration (GitHub Actions)

Add to `.github/workflows/build-macos.yml`:

```yaml
name: Build macOS

on:
  push:
    tags: ['v*']

jobs:
  build-macos:
    runs-on: macos-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pyinstaller
        brew install create-dmg
    
    - name: Build app
      run: |
        cd installers/mac
        chmod +x build.sh
        ./build.sh
    
    - name: Upload DMG
      uses: actions/upload-artifact@v4
      with:
        name: macos-dmg
        path: installers/mac/output/*.dmg
```

## ✅ Quality Checklist

### Common macOS Issues Avoided

| Issue | Solution |
|-------|----------|
| **Gatekeeper blocks app** | Code signing + notarization |
| **"App is damaged"** | Proper code signature or: `xattr -cr /path/to/app` |
| **Missing resources** | `sys._MEIPASS` path handling in code |
| **stdout/stderr is None** | Redirect to `/dev/null` before imports |
| **Translocation** | DMG distribution (app copied from DMG) |
| **Retina display issues** | `NSHighResolutionCapable` in Info.plist |
| **Network permissions** | Entitlements for network access |

### Testing on Clean Mac

1. Create a fresh macOS VM or use a Mac without the app
2. Download and mount the DMG
3. Drag app to Applications
4. Verify:
   - [ ] App launches without security warnings (if signed)
   - [ ] App icon displays correctly
   - [ ] All features work
   - [ ] App appears in Launchpad
   - [ ] App can be uninstalled by dragging to Trash

### If App Won't Open (Unsigned)

Users can bypass Gatekeeper for unsigned apps:

```bash
# Remove quarantine attribute
xattr -cr /Applications/FlightDealFinder.app

# Or right-click → Open → Open anyway
```

## 🔧 Customization

### Change Version

Edit `build.sh` or pass `-v` flag:
```bash
./build.sh -v 2.1.0
```

Also update `FlightDealFinder.spec`:
```python
APP_VERSION = '2.1.0'
```

### Change Bundle Identifier

Edit `FlightDealFinder.spec`:
```python
BUNDLE_IDENTIFIER = 'com.yourcompany.flightdealfinder'
```

### Change App Name

Edit `FlightDealFinder.spec`:
```python
APP_NAME = 'YourAppName'
```

## 📊 Expected Sizes

| Component | Approximate Size |
|-----------|------------------|
| App Bundle (.app) | 100-150 MB |
| DMG Installer | 40-60 MB |

## 🐛 Troubleshooting

### "Python not found"
```bash
# Install Python via Homebrew
brew install python@3.12
```

### "PyInstaller not found"
```bash
pip3 install pyinstaller
```

### "create-dmg not found"
```bash
brew install create-dmg
# Or the script will fall back to hdiutil
```

### App crashes on launch
1. Run from Terminal to see errors:
   ```bash
   /Applications/FlightDealFinder.app/Contents/MacOS/FlightDealFinder
   ```
2. Check Console.app for crash logs

### "App is damaged and can't be opened"
```bash
xattr -cr /Applications/FlightDealFinder.app
```

### Build fails with "No module named X"
Add the module to `hiddenimports` in `FlightDealFinder.spec`

## 📚 Resources

- [PyInstaller macOS Bundling](https://pyinstaller.org/en/stable/spec-files.html#macos-bundles)
- [Apple Code Signing Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [create-dmg GitHub](https://github.com/create-dmg/create-dmg)
- [NiceGUI + PyInstaller](https://nicegui.io/documentation/section_configuration_deployment#package_for_installation)

