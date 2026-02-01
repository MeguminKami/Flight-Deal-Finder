# GitHub Deployment Fixes

## Overview
Fixed the GitHub Actions workflow to correctly create and publish versions for both macOS and Windows platforms.

## Changes Made

### 1. GitHub Actions Workflow (`.github/workflows/release.yml`)

#### Build Job Improvements
- **Split artifact uploads**: Changed from a single generic upload to separate, OS-specific uploads:
  - Windows: `windows-installer` artifact with path `installers/windows/FlightDealFinder-win-x64-*.exe`
  - macOS: `macos-app` artifact with path `installers/mac/output/FlightDealFinder-mac-arm64-*.zip`

- **Added verification steps**: After each build, the workflow now verifies that the expected files were created:
  - Windows: Checks for `.exe` installer and displays size
  - macOS: Checks for `.zip` bundle and displays size

#### Release Job Improvements
- **Separate artifact downloads**: Downloads each platform artifact separately into a unified `release-files/` directory
- **File verification**: Lists all files before creating the release
- **Auto-generated release notes**: Creates comprehensive release notes including:
  - Download links for each platform
  - Installation instructions
  - System requirements
  - Support information

### 2. Windows CI Build Script (`scripts/ci_build_windows.ps1`)

#### Simplified Output Location
- **Removed duplicate copying**: Previously copied the installer to both `installers/windows/output/` and `installers/windows/`
- **Single output location**: Now only copies to `installers/windows/` for consistency with workflow expectations
- This ensures the artifact upload step finds exactly one file

### 3. Workflow Features

#### Versioning
- Uses Git tag (e.g., `v2.0`) as the version identifier
- Automatically names files with the version: `FlightDealFinder-win-x64-v2.0.exe`

#### Artifact Naming
- Clear, descriptive artifact names:
  - `windows-installer` for Windows builds
  - `macos-app` for macOS builds

#### Release Creation
- Automatically creates/updates GitHub releases when a tag is pushed
- Includes both installers in the release assets
- Generates user-friendly release notes

## How to Use

### Creating a New Release

1. **Tag the release**:
   ```bash
   git tag v2.0
   git push origin v2.0
   ```

2. **GitHub Actions will automatically**:
   - Build Windows installer on `windows-latest`
   - Build macOS app bundle on `macos-14` (Apple Silicon)
   - Verify both builds completed successfully
   - Create a GitHub release with both artifacts
   - Generate release notes

3. **Release artifacts will be named**:
   - `FlightDealFinder-win-x64-v2.0.exe`
   - `FlightDealFinder-mac-arm64-v2.0.zip`

### Manual Testing

#### Test Windows Build Locally
```powershell
.\scripts\ci_build_windows.ps1 -Tag "v2.0"
```

#### Test macOS Build Locally
```bash
chmod +x ./scripts/ci_build_macos.sh
./scripts/ci_build_macos.sh "v2.0"
```

## File Structure

```
FlightSearchV2/
├── .github/
│   └── workflows/
│       └── release.yml          # ✅ Updated - Main CI/CD workflow
├── scripts/
│   ├── ci_build_windows.ps1     # ✅ Updated - Windows CI build
│   └── ci_build_macos.sh        # ✓ No changes needed
├── installers/
│   ├── windows/
│   │   ├── FlightDealFinder.spec
│   │   ├── build.ps1
│   │   ├── installer.iss
│   │   └── [output files here]  # ← Workflow expects files here
│   └── mac/
│       ├── FlightDealFinder.spec
│       └── output/              # ← Workflow expects files here
│           └── [output files]
```

## Key Improvements

1. ✅ **Consistent artifact naming** - Clear, version-tagged filenames
2. ✅ **Proper artifact handling** - Separate uploads/downloads for each platform
3. ✅ **Build verification** - Ensures files exist before uploading
4. ✅ **Auto-generated release notes** - Professional release documentation
5. ✅ **Single source of truth** - Version comes from Git tag
6. ✅ **Error detection** - Fails fast if builds don't produce expected files

## Testing Checklist

Before creating a new release tag:

- [ ] Local Windows build test passes
- [ ] Local macOS build test passes (if on macOS)
- [ ] Git tag follows `v*.*` pattern (e.g., `v2.0`, `v2.1`)
- [ ] All changes committed and pushed to main branch
- [ ] GitHub Actions enabled on repository
- [ ] Secrets configured (GITHUB_TOKEN is automatic)

## Troubleshooting

### "No files were found" Error
- Check that build scripts place files in correct locations
- Verify file naming matches the glob patterns in workflow
- Look at build script output for actual file locations

### Release Not Created
- Ensure tag follows `v*.*` pattern
- Check workflow permissions (needs `contents: write`)
- Verify GITHUB_TOKEN has necessary permissions

### Wrong Files in Release
- Check artifact upload paths in workflow
- Verify build scripts output to expected locations
- Review "List release files" step output in workflow

## Future Enhancements

Potential improvements for future iterations:

- [ ] Add checksums (SHA-256) to release notes
- [ ] Support for Intel macOS builds (`macos-latest`)
- [ ] Automated testing before release
- [ ] Code signing for both platforms
- [ ] Update checking mechanism in the app
- [ ] Linux build support
