# Standalone Distribution Guide

This document explains how to build and distribute Procedural Engine as a standalone executable for Steam and other platforms.

## Package Structure

The engine uses the `procengine/` package structure:

```
procengine/                 # Core Python package
├── __init__.py             # Version, public API exports
├── core/                   # Engine fundamentals
│   ├── engine.py           # Main engine class
│   └── seed_registry.py    # Deterministic sub-seeding
├── world/                  # World generation
│   ├── terrain.py          # Heightmap, biomes, erosion
│   ├── chunk.py            # ChunkManager, ChunkedHeightField
│   ├── props.py            # Rock, tree, building, creature generators
│   ├── creature_templates.py # Species template system (8 built-in templates)
│   ├── materials.py        # Material graph DSL
│   └── world.py            # Multi-chunk assembly
├── physics/                # Physics system
│   ├── bodies.py           # RigidBody, RigidBody3D, Vec3
│   ├── collision.py        # Sequential impulse solver
│   └── heightfield.py      # HeightField, HeightField2D
├── game/                   # Game layer
│   ├── game_api.py         # GameWorld, Entity, Events
│   ├── behavior_tree.py    # NPC and creature behavior trees
│   ├── player_controller.py # Input & camera system
│   ├── data_loader.py      # JSON data loading
│   ├── game_runner.py      # Main game loop, chunk orchestration
│   ├── harvesting.py       # Resource harvesting with drop tables
│   └── ui_system.py        # Dear ImGui UI (HUD, dialogue, inventory, crafting, console)
├── commands/               # Command system
│   ├── commands.py         # Command registry
│   ├── console.py          # In-game console
│   └── handlers/           # Command implementations
└── graphics/               # Rendering bridge
    └── graphics_bridge.py  # Vulkan/headless abstraction
```

## Overview

The engine supports two distribution methods:

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| **PyInstaller** | Easy, reliable, good Python compatibility | Larger size (~150MB), slower startup | Quick builds, testing |
| **C++ Launcher** | Smaller size, faster startup, tighter integration | More complex build, needs embedded Python | Production/Steam |

## Quick Start (PyInstaller)

### Linux/macOS

```bash
# Build standalone executable
./scripts/build_standalone.sh

# Output in dist/ProceduralEngine/
./dist/ProceduralEngine/ProceduralEngine --help
```

### Windows

```cmd
REM Build standalone executable
scripts\build_standalone.bat

REM Output in dist\ProceduralEngine\
dist\ProceduralEngine\ProceduralEngine.exe --help
```

## Build Options

### build_standalone.sh / build_standalone.bat

| Option | Description |
|--------|-------------|
| `--clean` / `/clean` | Clean build directories first |
| `--release` / `/release` | Build with optimizations (default) |
| `--debug` / `/debug` | Build with debug symbols |
| `--onefile` / `/onefile` | Single-file executable (slower startup) |
| `--no-vulkan` / `/novulkan` | Headless build without graphics |

## Directory Structure

After building, `dist/ProceduralEngine/` contains:

```
ProceduralEngine/
├── ProceduralEngine(.exe)     # Main executable
├── procengine_cpp.*.so/.pyd   # C++ extension module
├── python312.dll/.so          # Python runtime (if bundled)
├── procengine/                # Core Python package (included for moddability)
│   ├── core/
│   ├── world/
│   ├── physics/
│   ├── game/
│   ├── commands/
│   └── graphics/
├── data/                      # Game data files
│   ├── items/
│   ├── npcs/
│   └── quests/
├── lib/                       # Python standard library
│   ├── python3.12/
│   └── site-packages/
└── _internal/                 # PyInstaller internals (if present)
```

## Steam Distribution

### Package for Steam

```bash
# Create Steam-ready package
./scripts/package_steam.sh --appid YOUR_APP_ID

# Output in dist/steam/
```

### Steam Launch Options

In Steamworks partner portal, set:

- **Linux**: `./launch.sh %command%`
- **Windows**: `ProceduralEngine.exe %command%`
- **macOS**: `./launch.sh %command%`

### Depot Configuration

The packager creates Steamworks VDF files in `dist/steamworks/`:

- `app_build.vdf` - Main app build configuration
- `depot_build_*.vdf` - Platform-specific depot configs

Upload with SteamCMD:

```bash
steamcmd +login <username> +run_app_build /path/to/app_build.vdf +quit
```

## C++ Launcher (Advanced)

For smaller size and faster startup, build the native launcher:

```bash
cd cpp
mkdir -p build && cd build
cmake .. -DBUILD_LAUNCHER=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --target ProceduralEngine
```

This creates `bin/ProceduralEngine` which embeds Python and links `procengine_cpp` statically.

### Requirements for C++ Launcher

You need to provide a Python distribution alongside the launcher:

1. **Windows**: Download "embeddable package" from python.org
2. **Linux**: Bundle Python from pyenv or system packages
3. **macOS**: Bundle Python.framework

Example embedded structure:

```
ProceduralEngine/
├── ProceduralEngine.exe
├── python312.dll           # Windows
├── python312.zip           # Compressed stdlib
├── vcruntime140.dll        # MSVC runtime
├── data/
└── *.py                    # Your Python modules
```

## Runtime Dependencies

### Windows

- Visual C++ Redistributable 2019+ (included or prompt user)
- Vulkan Runtime (usually from GPU drivers)

### Linux

- libc6 >= 2.17 (RHEL 7+ / Ubuntu 18.04+)
- libvulkan.so.1 (from GPU drivers or vulkan-loader)
- libssl, libcrypto (OpenSSL)

### macOS

- macOS 10.15+ (Catalina)
- MoltenVK (bundled or from Vulkan SDK)

## Troubleshooting

### "Python not found" errors

The executable needs Python stdlib. Ensure:
- `lib/python3.12/` exists (Linux/macOS)
- `python312.zip` exists (Windows)

### Vulkan errors

- Install latest GPU drivers
- Install Vulkan runtime from LunarG SDK
- Run with `--headless` to test without graphics

### Missing DLLs (Windows)

- Install Visual C++ Redistributable
- Copy missing DLLs from `C:\Windows\System32\` or Vulkan SDK

### Extension module not loading

Check that `procengine_cpp.*.so/.pyd` matches your Python version:
- Python 3.12 needs `procengine_cpp.cpython-312-*.so`
- Rebuild extension if version mismatch

## Size Optimization

To reduce distribution size:

1. **Use --onefile**: Creates single executable (slower startup)
2. **Strip debug symbols**: `strip ProceduralEngine` (Linux/macOS)
3. **UPX compression**: PyInstaller uses this automatically
4. **Exclude unused modules**: Edit `ProceduralEngine.spec`

Typical sizes:
- Development build: ~200MB
- Optimized build: ~80-120MB
- C++ launcher + embedded Python: ~50-80MB

## Testing the Build

Before distributing, test on a clean system:

```bash
# Test basic functionality
./ProceduralEngine --help
./ProceduralEngine --seed 42 --headless --benchmark

# Test with graphics (needs Vulkan)
./ProceduralEngine --seed 42

# Test data loading
./ProceduralEngine --seed 42 --verbose
```

## CI/CD Integration

Add to GitHub Actions for automated builds:

```yaml
jobs:
  build-standalone:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Build
        run: |
          pip install pyinstaller numpy pybind11
          pip install -e .
          pyinstaller ProceduralEngine.spec --noconfirm
      - uses: actions/upload-artifact@v4
        with:
          name: build-${{ matrix.os }}
          path: dist/ProceduralEngine/
```

The full CI/CD workflows are in `.github/workflows/`:
- `ci.yml` - Continuous integration (lint, test, build)
- `release.yml` - Release builds with standalone executables

## Version Information

- **Engine Version**: 2.0.0-alpha
- **Python**: 3.10-3.12
- **PyInstaller**: 6.0+
- **Vulkan**: 1.2+
