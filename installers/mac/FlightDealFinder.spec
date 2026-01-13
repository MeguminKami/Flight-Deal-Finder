# -*- mode: python ; coding: utf-8 -*-
# FlightDealFinder.spec - PyInstaller spec file for macOS build
# Note: CI passes version via tag; this spec is intentionally version-agnostic.

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.abspath(os.path.join(SPEC_DIR, '..', '..'))

APP_NAME = 'FlightDealFinder'

block_cipher = None

# macOS app icon (.icns) lives next to this spec file
MAC_ICON_PATH = os.path.join(SPEC_DIR, 'icon.icns')

nicegui_datas = collect_data_files('nicegui')

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

hidden_imports += collect_submodules('nicegui')
hidden_imports += collect_submodules('uvicorn')
hidden_imports += collect_submodules('starlette')

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'app.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'static'), 'static'),
        (os.path.join(PROJECT_ROOT, 'airports.json'), '.'),
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
    cipher=block_cipher,
    noarchive=False,
)

seen = set()
a.datas = [x for x in a.datas if not (x[0] in seen or seen.add(x[0]))]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# macOS: build a windowed .app bundle
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    icon=MAC_ICON_PATH if os.path.exists(MAC_ICON_PATH) else None,
)

app = BUNDLE(
    exe,
    name=f"{APP_NAME}.app",
    icon=MAC_ICON_PATH if os.path.exists(MAC_ICON_PATH) else None,
    bundle_identifier=None,
)

# Note: For a macOS .app bundle, BUNDLE() is the final build target.
# Using COLLECT() here can trigger "No EXE() instance was passed to COLLECT()" depending on PyInstaller version.
