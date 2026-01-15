# -*- mode: python ; coding: utf-8 -*-
# FlightDealFinder.spec - PyInstaller spec file for Windows build
# Version: 2.0.0

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Get absolute path to project root
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.abspath(os.path.join(SPEC_DIR, '..', '..'))

# App metadata
APP_NAME = 'FlightDealFinder'
APP_VERSION = '2.0.0'

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
        (os.path.join(PROJECT_ROOT, 'config.env'), '.'),
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
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SPEC_DIR, 'icon.ico'),
    version=os.path.join(SPEC_DIR, 'version_info.txt') if os.path.exists(os.path.join(SPEC_DIR, 'version_info.txt')) else None,
    uac_admin=False,  # Does not require admin rights
    uac_uiaccess=False,
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
