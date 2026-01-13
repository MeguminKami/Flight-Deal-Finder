#!/bin/bash
# =============================================================================
# Flight Deal Finder - macOS Build Script
# Version: 2.0.0
# =============================================================================
# This script builds a macOS .app bundle and optionally creates a DMG installer.
# Compatible with macOS 10.15+ (Catalina), Intel and Apple Silicon Macs.
# =============================================================================

set -e  # Exit on error

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_NAME="FlightDealFinder"
APP_VERSION="2.0.0"
DMG_NAME="${APP_NAME}_${APP_VERSION}_macOS"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# Functions
# =============================================================================

log_status() {
    echo -e "${CYAN}[*]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[+]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[-]${NC} $1"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        return 1
    fi
    return 0
}

install_requirements() {
    log_status "Checking Python requirements..."

    # Upgrade pip
    python3 -m pip install --upgrade pip --quiet

    # Install project requirements
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        log_status "Installing project dependencies..."
        python3 -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
    fi

    # Install PyInstaller
    log_status "Installing/upgrading PyInstaller..."
    python3 -m pip install --upgrade pyinstaller --quiet

    log_success "Requirements installed"
}

clean_build() {
    log_status "Cleaning build directories..."

    rm -rf "$SCRIPT_DIR/dist"
    rm -rf "$SCRIPT_DIR/build"
    rm -rf "$SCRIPT_DIR/output"

    # Clean __pycache__
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    log_success "Build directories cleaned"
}

build_app() {
    log_status "Building macOS app with PyInstaller..."

    cd "$SCRIPT_DIR"

    # Create output directories
    mkdir -p dist
    mkdir -p build

    # Run PyInstaller
    python3 -m PyInstaller \
        --noconfirm \
        --clean \
        --distpath dist \
        --workpath build \
        "$SCRIPT_DIR/FlightDealFinder.spec"

    # Verify build
    if [ -d "$SCRIPT_DIR/dist/${APP_NAME}.app" ]; then
        log_success "App bundle built: dist/${APP_NAME}.app"
    else
        log_error "Build failed: ${APP_NAME}.app not found"
        exit 1
    fi
}

create_dmg() {
    log_status "Creating DMG installer..."

    mkdir -p "$SCRIPT_DIR/output"

    # Check for create-dmg
    if check_command create-dmg; then
        # Remove existing DMG if exists
        rm -f "$SCRIPT_DIR/output/${DMG_NAME}.dmg"

        # Create DMG with create-dmg (prettier result)
        create-dmg \
            --volname "Flight Deal Finder" \
            --volicon "$SCRIPT_DIR/icon.icns" \
            --window-pos 200 120 \
            --window-size 660 400 \
            --icon-size 100 \
            --icon "${APP_NAME}.app" 180 190 \
            --app-drop-link 480 190 \
            --hide-extension "${APP_NAME}.app" \
            --no-internet-enable \
            "$SCRIPT_DIR/output/${DMG_NAME}.dmg" \
            "$SCRIPT_DIR/dist/${APP_NAME}.app" \
            2>/dev/null || {
                # create-dmg may fail on some systems, fall back to hdiutil
                log_warning "create-dmg failed, falling back to hdiutil..."
                create_dmg_hdiutil
            }
    else
        log_warning "create-dmg not found. Using hdiutil instead."
        log_warning "For prettier DMG, install with: brew install create-dmg"
        create_dmg_hdiutil
    fi

    if [ -f "$SCRIPT_DIR/output/${DMG_NAME}.dmg" ]; then
        local dmg_size=$(du -h "$SCRIPT_DIR/output/${DMG_NAME}.dmg" | cut -f1)
        log_success "DMG created: output/${DMG_NAME}.dmg ($dmg_size)"
    fi
}

create_dmg_hdiutil() {
    # Fallback DMG creation using hdiutil (built into macOS)
    local temp_dmg="$SCRIPT_DIR/output/temp_${DMG_NAME}.dmg"
    local final_dmg="$SCRIPT_DIR/output/${DMG_NAME}.dmg"

    # Create temporary DMG
    hdiutil create \
        -volname "Flight Deal Finder" \
        -srcfolder "$SCRIPT_DIR/dist/${APP_NAME}.app" \
        -ov \
        -format UDRW \
        "$temp_dmg"

    # Convert to compressed read-only DMG
    hdiutil convert "$temp_dmg" \
        -format UDZO \
        -imagekey zlib-level=9 \
        -o "$final_dmg"

    # Clean up
    rm -f "$temp_dmg"
}

sign_app() {
    # Code signing (optional - requires Apple Developer certificate)
    if [ -n "$CODESIGN_IDENTITY" ]; then
        log_status "Signing app bundle..."

        codesign --force --deep --sign "$CODESIGN_IDENTITY" \
            --options runtime \
            --entitlements "$SCRIPT_DIR/entitlements.plist" \
            "$SCRIPT_DIR/dist/${APP_NAME}.app"

        log_success "App signed with identity: $CODESIGN_IDENTITY"
    else
        log_warning "CODESIGN_IDENTITY not set. App will not be signed."
        log_warning "Unsigned apps may show security warnings on macOS."
    fi
}

notarize_app() {
    # Notarization (optional - requires Apple Developer account)
    if [ -n "$APPLE_ID" ] && [ -n "$APPLE_APP_PASSWORD" ] && [ -n "$APPLE_TEAM_ID" ]; then
        log_status "Notarizing app..."

        xcrun notarytool submit "$SCRIPT_DIR/output/${DMG_NAME}.dmg" \
            --apple-id "$APPLE_ID" \
            --password "$APPLE_APP_PASSWORD" \
            --team-id "$APPLE_TEAM_ID" \
            --wait

        # Staple the notarization ticket
        xcrun stapler staple "$SCRIPT_DIR/output/${DMG_NAME}.dmg"

        log_success "App notarized and stapled"
    else
        log_warning "Notarization skipped. Set APPLE_ID, APPLE_APP_PASSWORD, and APPLE_TEAM_ID to enable."
    fi
}

show_summary() {
    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}              BUILD COMPLETED SUCCESSFULLY                  ${NC}"
    echo -e "${GREEN}============================================================${NC}"
    echo ""
    echo -e "App Bundle:  ${YELLOW}$SCRIPT_DIR/dist/${APP_NAME}.app${NC}"

    if [ -f "$SCRIPT_DIR/output/${DMG_NAME}.dmg" ]; then
        echo -e "DMG Installer: ${YELLOW}$SCRIPT_DIR/output/${DMG_NAME}.dmg${NC}"
    fi

    echo ""
    echo -e "Version:     ${YELLOW}${APP_VERSION}${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Test the app on a clean Mac"
    echo "  2. Sign with: export CODESIGN_IDENTITY='Developer ID Application: Your Name'"
    echo "  3. Notarize with Apple Developer account"
    echo ""
}

show_help() {
    echo "Flight Deal Finder - macOS Build Script"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -c, --clean      Clean build directories before building"
    echo "  -s, --skip-dmg   Skip DMG creation (only build .app)"
    echo "  -v, --version    Specify version (default: 2.0.0)"
    echo "  --sign           Sign the app (requires CODESIGN_IDENTITY env var)"
    echo "  --notarize       Notarize the app (requires Apple Developer account)"
    echo ""
    echo "Environment variables:"
    echo "  CODESIGN_IDENTITY    Code signing identity (e.g., 'Developer ID Application: Name')"
    echo "  APPLE_ID             Apple ID email for notarization"
    echo "  APPLE_APP_PASSWORD   App-specific password for notarization"
    echo "  APPLE_TEAM_ID        Apple Developer Team ID"
    echo ""
}

# =============================================================================
# Main Script
# =============================================================================

# Parse arguments
CLEAN=false
SKIP_DMG=false
DO_SIGN=false
DO_NOTARIZE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        -s|--skip-dmg)
            SKIP_DMG=true
            shift
            ;;
        -v|--version)
            APP_VERSION="$2"
            DMG_NAME="${APP_NAME}_${APP_VERSION}_macOS"
            shift 2
            ;;
        --sign)
            DO_SIGN=true
            shift
            ;;
        --notarize)
            DO_NOTARIZE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}        Flight Deal Finder - macOS Build Script             ${NC}"
echo -e "${CYAN}                    Version ${APP_VERSION}                        ${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Check prerequisites
log_status "Checking prerequisites..."

if ! check_command python3; then
    log_error "Python 3 not found. Please install Python 3.10+ from python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
log_status "Python version: $PYTHON_VERSION"

# Check macOS version
MACOS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "Unknown")
log_status "macOS version: $MACOS_VERSION"

# Check for icon file
if [ ! -f "$SCRIPT_DIR/icon.icns" ]; then
    if [ -f "$SCRIPT_DIR/icon.ico" ]; then
        log_warning "icon.icns not found, but icon.ico exists."
        log_warning "Convert it on macOS: sips -s format icns icon.ico --out icon.icns"
        log_warning "Or use an online converter: https://cloudconvert.com/ico-to-icns"
    else
        log_warning "icon.icns not found. The app will use a default icon."
        log_warning "To create an icon, run: ./create_icon.sh /path/to/source_image.png"
    fi
fi

# Clean if requested
if [ "$CLEAN" = true ]; then
    clean_build
fi

# Install requirements
install_requirements

# Build app
build_app

# Sign if requested
if [ "$DO_SIGN" = true ]; then
    sign_app
fi

# Create DMG
if [ "$SKIP_DMG" = false ]; then
    create_dmg
fi

# Notarize if requested
if [ "$DO_NOTARIZE" = true ]; then
    notarize_app
fi

# Show summary
show_summary

