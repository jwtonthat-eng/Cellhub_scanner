# PyInstaller spec file for Cellhub Scanner
# ─────────────────────────────────────────────────────────────────────────────
# HOW TO BUILD (run on a Windows machine with Python 3.11+):
#   1.  pip install -r requirements.txt
#   2.  pyinstaller cellhub_scanner.spec --noconfirm
#   Output: dist\CellhubScanner.exe   (single-file, no console, ~80-120 MB)
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# ── Dependency collection ────────────────────────────────────────────────────

def safe_collect(pkg):
    """collect_all without crashing when a package isn't installed."""
    try:
        return collect_all(pkg)
    except Exception:
        return [], [], []

g_datas,  g_bins,  g_hidden  = safe_collect('google.api_core')
ga_datas, ga_bins, ga_hidden = safe_collect('google.auth')
oa_datas, oa_bins, oa_hidden = safe_collect('google_auth_oauthlib')
dr_datas, dr_bins, dr_hidden = safe_collect('googleapiclient')
ctk_datas = collect_data_files('customtkinter')

# Bundle patterns.json and credentials folder (keep outside PYZ for easy editing)
extra_datas = [
    ('patterns/patterns.json', 'patterns'),
]
# Only bundle credentials folder if it exists and contains files
creds_dir = Path('config/credentials')
if creds_dir.exists() and any(creds_dir.iterdir()):
    extra_datas.append(('config/credentials', 'config/credentials'))

all_datas = (
    ctk_datas
    + g_datas + ga_datas + oa_datas + dr_datas
    + extra_datas
)
all_binaries = g_bins + ga_bins + oa_bins + dr_bins
all_hidden = (
    g_hidden + ga_hidden + oa_hidden + dr_hidden
    + [
        # Google stack
        'google.api_core',
        'google.auth',
        'google.auth.transport.requests',
        'google.auth.transport.urllib3',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.http',
        # PDF
        'pdfplumber',
        'pdfminer',
        'pdfminer.six',
        'pdfminer.high_level',
        'pdfminer.layout',
        'pdfminer.pdfpage',
        # Data
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'pandas',
        'pandas.io.formats.excel',
        # UI
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        # stdlib that PyInstaller sometimes misses
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'threading',
        'concurrent.futures',
        'statistics',
        'webbrowser',
    ]
)

# ── Analysis ─────────────────────────────────────────────────────────────────

a = Analysis(
    ['main.py'],
    pathex=[str(Path('.').resolve())],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'scipy', 'notebook', 'IPython',
        'pytest', 'unittest', 'doctest',
        'xml.etree.ElementTree',  # keep xml but drop heavy sub-modules
        'multiprocessing',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── EXE (single-file) ────────────────────────────────────────────────────────

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
    upx_exclude=['vcruntime140.dll', 'python3*.dll'],
    runtime_tmpdir=None,
    console=False,                  # No terminal window — GUI only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Place icon.ico in assets/ then uncomment:
    # icon='assets/icon.ico',
    version='version_info.txt',     # Optional: see below
)
