# Quick Release Guide

## Creating a New Release

### 1. Prepare the Release
```bash
# Make sure all changes are committed
git status

# Update version in relevant files if needed
# - installers/windows/installer.iss (AppVersion)
# - installers/windows/FlightDealFinder.spec (APP_VERSION)
```

### 2. Create and Push Tag
```bash
# Create a tag (e.g., for version 2.0)
git tag v2.0

# Push the tag to trigger the release workflow
git push origin v2.0
```

### 3. Monitor the Build
1. Go to GitHub Actions: `https://github.com/YOUR_USERNAME/FlightSearchV2/actions`
2. Watch the "Release" workflow
3. Both Windows and macOS builds must succeed

### 4. Verify the Release
1. Go to Releases: `https://github.com/YOUR_USERNAME/FlightSearchV2/releases`
2. Check that both files are present:
   - `FlightDealFinder-win-x64-v2.0.exe`
   - `FlightDealFinder-mac-arm64-v2.0.zip`
3. Test download and installation

## Tag Naming Convention

✅ Correct:
- `v2.0`
- `v2.1`
- `v3.0`
- `v1.5.2`

❌ Incorrect:
- `2.0` (missing 'v' prefix)
- `version-2.0` (wrong format)
- `release-2.0` (wrong format)

## Local Testing (Before Tagging)

### Test Windows Build
```powershell
# From project root
.\scripts\ci_build_windows.ps1 -Tag "v2.0"

# Check output
ls installers\windows\*.exe
```

### Test macOS Build
```bash
# From project root
chmod +x ./scripts/ci_build_macos.sh
./scripts/ci_build_macos.sh "v2.0"

# Check output
ls -la installers/mac/output/*.zip
```

## Workflow Status

### Success ✅
- Green checkmarks on all jobs
- Both artifacts uploaded
- Release created with both files

### Failure ❌
Common issues:
1. **Build fails**: Check Python dependencies in `requirements.txt`
2. **Files not found**: Verify build script output paths
3. **Upload fails**: Check file naming patterns match workflow
4. **Release fails**: Verify `GITHUB_TOKEN` permissions

## Emergency: Delete and Recreate Release

If something goes wrong:

```bash
# Delete the tag locally
git tag -d v2.0

# Delete the tag remotely
git push origin :refs/tags/v2.0

# Delete the release on GitHub (via web UI)
# Then recreate the tag and push again
git tag v2.0
git push origin v2.0
```

## Workflow Output Locations

**Windows:**
- Build output: `installers/windows/dist/FlightDealFinder/`
- Final installer: `installers/windows/FlightDealFinder-win-x64-v*.exe`
- Artifact name: `windows-installer`

**macOS:**
- Build output: `installers/mac/dist/FlightDealFinder.app`
- Final bundle: `installers/mac/output/FlightDealFinder-mac-arm64-v*.zip`
- Artifact name: `macos-app`

## Getting Help

If builds fail:
1. Check the GitHub Actions logs
2. Look for red ❌ indicators
3. Read error messages in failed steps
4. Test build scripts locally
5. Verify file paths match expectations
