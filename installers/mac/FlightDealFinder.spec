# -*- mode: python ; coding: utf-8 -*-
# FlightDealFinder.spec - PyInstaller spec file for macOS build
# Version: 2.0.0
# Compatible with: macOS 10.15+ (Catalina), including MacBook 2020 (Intel & Apple Silicon)

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get absolute path to project root
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.abspath(os.path.join(SPEC_DIR, '..', '..'))

# App metadata
APP_NAME = 'FlightDealFinder'
APP_VERSION = '2.0.0'
BUNDLE_IDENTIFIER = 'com.joaoferreira.flightdealfinder'

block_cipher = None

# Collect all nicegui data files (templates, static assets, etc.)
nicegui_datas = collect_data_files('nicegui')

# Collect hidden imports for nicegui and its dependencies
hidden_imports = [
    'nicegui',
    'nicegui.elements',
    'nicegui.events',
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'httpx',
    'httpcore',
    'h11',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'starlette',
    'starlette.applications',
    'starlette.routing',
    'starlette.middleware',
    'starlette.responses',
    'starlette.staticfiles',
    'starlette.websockets',
    'fastapi',
    'python_multipart',
    'dotenv',
    'aiofiles',
    'watchfiles',
    'websockets',
    'engineio',
    'socketio',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    'markdown2',
    'pygments',
    'orjson',
    'itsdangerous',
    'jinja2',
    'markupsafe',
    'httptools',
    'click',
    'typing_extensions',
    'sniffio',
    'exceptiongroup',
]

# Additional submodules
hidden_imports += collect_submodules('nicegui')
hidden_imports += collect_submodules('uvicorn')
hidden_imports += collect_submodules('starlette')

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'app.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # App-specific data files
        (os.path.join(PROJECT_ROOT, 'static'), 'static'),
        (os.path.join(PROJECT_ROOT, 'airports.json'), '.'),
        # NiceGUI data files
        *nicegui_datas,
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate data files
seen = set()
a.datas = [x for x in a.datas if not (x[0] in seen or seen.add(x[0]))]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app - no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # Build for current architecture (universal2 requires special setup)
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS App Bundle
app = BUNDLE(
    coll,
    name=f'{APP_NAME}.app',
    icon=os.path.join(SPEC_DIR, 'icon.icns') if os.path.exists(os.path.join(SPEC_DIR, 'icon.icns')) else None,
    bundle_identifier=BUNDLE_IDENTIFIER,
    info_plist={
        # Basic app info
        'CFBundleName': 'Flight Deal Finder',
        'CFBundleDisplayName': 'Flight Deal Finder',
        'CFBundleExecutable': APP_NAME,
        'CFBundleIdentifier': BUNDLE_IDENTIFIER,
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,

        # macOS compatibility
        'LSMinimumSystemVersion': '10.15.0',  # macOS Catalina (2019) - supports MacBook 2020
        'NSHighResolutionCapable': True,

        # App behavior
        'LSBackgroundOnly': False,
        'NSSupportsAutomaticGraphicsSwitching': True,

        # Privacy descriptions (required for macOS 10.15+)
        'NSAppleEventsUsageDescription': 'Flight Deal Finder needs to control other apps to open links.',

        # App category
        'LSApplicationCategoryType': 'public.app-category.travel',

        # Document types (none for this app)
        'CFBundleDocumentTypes': [],

        # Copyright
        'NSHumanReadableCopyright': '© 2024-2026 João Ferreira. All rights reserved.',
    },
)

