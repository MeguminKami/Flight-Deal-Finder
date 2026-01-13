#!/bin/bash
# =============================================================================
# Create macOS .icns icon from a source image
# =============================================================================
# Usage: ./create_icon.sh source_image.png
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for source image
if [ -z "$1" ]; then
    echo "Usage: $0 <source_image.png>"
    echo ""
    echo "The source image should be at least 1024x1024 pixels."
    echo ""
    echo "If you don't have an image, you can:"
    echo "  1. Convert the Windows .ico file using an online converter"
    echo "  2. Use a placeholder icon"
    echo ""
    exit 1
fi

SOURCE_IMAGE="$1"
OUTPUT_ICNS="$SCRIPT_DIR/icon.icns"
ICONSET_DIR="$SCRIPT_DIR/icon.iconset"

# Check if source exists
if [ ! -f "$SOURCE_IMAGE" ]; then
    echo "Error: Source image not found: $SOURCE_IMAGE"
    exit 1
fi

# Check if sips is available (macOS built-in)
if ! command -v sips &> /dev/null; then
    echo "Error: sips command not found. This script requires macOS."
    exit 1
fi

echo "Creating iconset from: $SOURCE_IMAGE"

# Create iconset directory
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

# Generate all required sizes
# Standard sizes
sips -z 16 16     "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_16x16.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_16x16@2x.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_32x32.png"
sips -z 64 64     "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_32x32@2x.png"
sips -z 128 128   "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_128x128.png"
sips -z 256 256   "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_128x128@2x.png"
sips -z 256 256   "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_256x256.png"
sips -z 512 512   "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_256x256@2x.png"
sips -z 512 512   "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_512x512.png"
sips -z 1024 1024 "$SOURCE_IMAGE" --out "$ICONSET_DIR/icon_512x512@2x.png"

# Convert iconset to icns
iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"

# Clean up
rm -rf "$ICONSET_DIR"

echo "Icon created: $OUTPUT_ICNS"
ls -la "$OUTPUT_ICNS"

