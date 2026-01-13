# FlightDealFinder (FlightSearchV2)

## Releasing

Create and push a version tag in the format `vX.Y` (example: `v2.1`). This triggers the GitHub Actions release workflow.

```bash
git tag v2.1
git push origin v2.1
```

### What gets produced

- **Windows x64**: a single installer `.exe` under `installers/windows/` (and uploaded as a GitHub Release asset)
- **macOS Apple Silicon (arm64)**: a single `.zip` containing the `.app` bundle, created strictly under `installers/mac/` (and uploaded as a GitHub Release asset)

No macOS code signing and no notarization are performed.
