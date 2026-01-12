# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Procedural Engine standalone executable.

This creates a distributable standalone application that bundles:
- Python 3.12 runtime (embedded)
- procengine_cpp extension module (C++ core)
- All Python game modules
- Data files (JSON configs, shaders)
- Required DLLs (Vulkan loader, OpenSSL)

Build commands:
    # Development build (one-folder)
    pyinstaller ProceduralEngine.spec

    # Production build (one-file, slower startup)
    pyinstaller ProceduralEngine.spec --onefile

    # Clean build
    pyinstaller ProceduralEngine.spec --clean --noconfirm
"""

import sys
import os
from pathlib import Path

# Detect platform
PLATFORM = sys.platform
IS_WINDOWS = PLATFORM == 'win32'
IS_MACOS = PLATFORM == 'darwin'
IS_LINUX = PLATFORM.startswith('linux')

# Project paths
PROJECT_ROOT = Path(SPECPATH).resolve()
DATA_DIR = PROJECT_ROOT / 'data'
CPP_DIR = PROJECT_ROOT / 'cpp'

# Find the compiled extension module
def find_extension():
    """Find the procengine_cpp extension module."""
    import glob
    patterns = [
        'procengine_cpp*.so',       # Linux
        'procengine_cpp*.pyd',      # Windows
        'procengine_cpp*.dylib',    # macOS (rare)
    ]
    for pattern in patterns:
        matches = glob.glob(str(PROJECT_ROOT / pattern))
        if matches:
            return matches[0]
        # Also check build directory
        matches = glob.glob(str(PROJECT_ROOT / 'build' / '**' / pattern), recursive=True)
        if matches:
            return matches[0]
    return None

EXT_MODULE = find_extension()
if EXT_MODULE:
    print(f"Found extension module: {EXT_MODULE}")
else:
    print("WARNING: Extension module not found. Build with 'pip install -e .' first.")

# =============================================================================
# Analysis - Collect all dependencies
# =============================================================================

block_cipher = None

# Python modules to include (from py-modules in pyproject.toml)
py_modules = [
    'engine',
    'seed_registry',
    'terrain',
    'physics',
    'props',
    'materials',
    'world',
    'seed_sweeper',
    'main',
    'game_api',
    'behavior_tree',
    'player_controller',
    'data_loader',
    'game_runner',
    'ui_system',
    'graphics_bridge',
]

# Hidden imports that PyInstaller might miss
hidden_imports = [
    'numpy',
    'numpy.core',
    'numpy.core._methods',
    'numpy.lib.format',
    'json',
    'hashlib',
    'dataclasses',
    'typing',
    'abc',
    'enum',
    'time',
    'pathlib',
    'argparse',
]

# Data files to include
datas = [
    # Game data files
    (str(DATA_DIR / 'items'), 'data/items'),
    (str(DATA_DIR / 'npcs'), 'data/npcs'),
    (str(DATA_DIR / 'quests'), 'data/quests'),
]

# Binaries to include
binaries = []

# Add extension module if found
if EXT_MODULE:
    ext_name = os.path.basename(EXT_MODULE)
    binaries.append((EXT_MODULE, '.'))

# Platform-specific binaries
if IS_WINDOWS:
    # Vulkan runtime (usually in Vulkan SDK or system)
    vulkan_dll = os.environ.get('VULKAN_SDK', '')
    if vulkan_dll:
        vulkan_loader = Path(vulkan_dll) / 'Bin' / 'vulkan-1.dll'
        if vulkan_loader.exists():
            binaries.append((str(vulkan_loader), '.'))

    # OpenSSL DLLs
    for ssl_dir in ['C:/Program Files/OpenSSL', 'C:/Program Files/OpenSSL-Win64']:
        ssl_path = Path(ssl_dir)
        if ssl_path.exists():
            for dll in ssl_path.glob('*.dll'):
                binaries.append((str(dll), '.'))
            break

elif IS_MACOS:
    # MoltenVK for Vulkan on macOS
    moltenvk_paths = [
        '/usr/local/lib/libMoltenVK.dylib',
        '/opt/homebrew/lib/libMoltenVK.dylib',
    ]
    for mvk in moltenvk_paths:
        if Path(mvk).exists():
            binaries.append((mvk, '.'))
            break

# Analysis
a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'PIL',
        'scipy',
        'pandas',
        'IPython',
        'notebook',
        'pytest',
        'mypy',
        'ruff',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# =============================================================================
# PYZ - Python bytecode archive
# =============================================================================

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# =============================================================================
# EXE - Executable
# =============================================================================

exe = EXE(
    pyz,
    a.scripts,
    [],  # Leave empty for one-folder mode
    exclude_binaries=True,  # True for one-folder mode
    name='ProceduralEngine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX if available
    console=True,  # Set to False for windowed app (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if IS_WINDOWS and Path('icon.ico').exists() else None,
)

# =============================================================================
# COLLECT - Bundle into directory
# =============================================================================

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ProceduralEngine',
)

# =============================================================================
# BUNDLE - macOS .app bundle (optional)
# =============================================================================

if IS_MACOS:
    app = BUNDLE(
        coll,
        name='ProceduralEngine.app',
        icon='icon.icns' if Path('icon.icns').exists() else None,
        bundle_identifier='com.proceduralengine.game',
        info_plist={
            'CFBundleName': 'Procedural Engine',
            'CFBundleDisplayName': 'Procedural Engine',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15',
        },
    )
