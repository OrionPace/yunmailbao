# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for 云邮宝 (AutoEmail)

import os

block_cipher = None

# Collect all data files
datas = [
    ('static', 'static'),           # Frontend UI files
    ('.env.example', '.'),          # Example env file (will be copied to runtime dir on first run)
]

# Add core module as data since it's imported at runtime
# PyInstaller should pick it up via analysis, but be explicit
hiddenimports = [
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
    'uvicorn.lifespan.off',
    'fastapi',
    'starlette',
    'starlette.responses',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'pandas',
    'openpyxl',
    'jinja2',
    'dotenv',
    'webview',
    'webview.platforms.edgechromium',
    'clr_loader',
    'pythonnet',
    'email',
    'email.mime',
    'email.mime.multipart',
    'email.mime.text',
    'email.mime.image',
    'email.mime.application',
    'email.utils',
    'email.header',
    'smtplib',
    'core',
    'core.engine',
    'core.email_sender',
    'multipart',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy.testing',
        'test',
        'setuptools',
        'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='云邮宝',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='云邮宝',
)
