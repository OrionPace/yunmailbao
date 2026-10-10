# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for 云邮宝 (AutoEmail)

import os
import sys

block_cipher = None

# --- 显式绑定与当前 Python 匹配的 OpenSSL DLL ---
# 该环境基于 conda/Miniforge，_ssl.pyd 依赖的 libcrypto/libssl 位于
# base_prefix\Library\bin。若不显式指定，PyInstaller 可能从 PATH 上其它
# conda 环境抓到版本不一致的 DLL，导致打包后报
# "ImportError: DLL load failed while importing _ssl: 找不到指定的程序"。
binaries = []
for _cand in (os.path.join(sys.base_prefix, 'Library', 'bin'),  # conda 布局
              os.path.join(sys.base_prefix, 'DLLs')):            # 标准 CPython 布局
    for _dll in ('libcrypto-3-x64.dll', 'libssl-3-x64.dll',
                 'libcrypto-3.dll', 'libssl-3.dll'):
        _p = os.path.join(_cand, _dll)
        if os.path.exists(_p):
            binaries.append((_p, '.'))

# Collect all data files
datas = [
    ('static', 'static'),           # Frontend UI files
    ('assets', 'assets'),
    ('LICENSE', '.'),
    ('THIRD_PARTY_NOTICES.md', '.'),
    ('packaging/licenses', 'packaging/licenses'),
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
    binaries=binaries,
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
    name='YunYouBao',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # Hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/branding/yunyoubao-fox-v1.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YunYouBao',
)
