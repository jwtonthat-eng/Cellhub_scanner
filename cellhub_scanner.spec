# PyInstaller spec file for Cellhub Scanner
# Build: pyinstaller cellhub_scanner.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Collect google libraries (dynamic imports)
google_datas, google_binaries, google_hidden = collect_all('google.api_core')
auth_datas, auth_binaries, auth_hidden = collect_all('google.auth')
oauth_datas, oauth_binaries, oauth_hidden = collect_all('google_auth_oauthlib')
drive_datas, drive_binaries, drive_hidden = collect_all('googleapiclient')

# Collect customtkinter assets (themes, images)
ctk_datas = collect_data_files('customtkinter')

all_datas = (
    ctk_datas
    + google_datas + auth_datas + oauth_datas + drive_datas
    + [
        ('patterns/patterns.json', 'patterns'),
        ('config/credentials', 'config/credentials'),
    ]
)

all_binaries = google_binaries + auth_binaries + oauth_binaries + drive_binaries

all_hidden = (
    google_hidden + auth_hidden + oauth_hidden + drive_hidden
    + [
        'google.api_core',
        'google.auth',
        'google.auth.transport.requests',
        'google_auth_oauthlib.flow',
        'googleapiclient.discovery',
        'googleapiclient.http',
        'pdfplumber',
        'pdfminer',
        'openpyxl',
        'pandas',
        'customtkinter',
    ]
)

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'notebook', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CellhubScanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Windows GUI app (no console window)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Replace with 'assets/icon.ico' if available
)
