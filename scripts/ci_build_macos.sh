#!/usr/bin/env bash
set -euo pipefail

# CI build script for macOS (GitHub Actions)
# Produces exactly one primary deliverable under installers/mac/

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  echo "Usage: $0 vX.Y" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAC_DIR="$PROJECT_ROOT/installers/mac"
DIST_DIR="$MAC_DIR/dist"
BUILD_DIR="$MAC_DIR/build"
OUT_DIR="$MAC_DIR/output"

APP_NAME="FlightDealFinder"

mkdir -p "$DIST_DIR" "$BUILD_DIR" "$OUT_DIR"

python3 -m pip install --upgrade pip
python3 -m pip install -r "$PROJECT_ROOT/requirements.txt"
python3 -m pip install --upgrade pyinstaller

# Spec lives under installers/mac and forces dist/work/output under installers/mac
pyinstaller --noconfirm --clean \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR" \
  "$MAC_DIR/$APP_NAME.spec"

APP_PATH="$DIST_DIR/$APP_NAME.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Expected .app not found at $APP_PATH" >&2
  exit 1
fi

ZIP_NAME="$APP_NAME-mac-arm64-$TAG.zip"
ZIP_PATH="$OUT_DIR/$ZIP_NAME"

# Create zip in-place (no signing/notarization)
rm -f "$ZIP_PATH"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"

echo "macOS artifact created: $ZIP_PATH"

