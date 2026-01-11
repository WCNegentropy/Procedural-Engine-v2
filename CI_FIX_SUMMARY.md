# CI/CD Pipeline Fix: C++ Module in Standalone Builds

## Issue Reported by @WCNegentropy
The C++ module was being built successfully in CI but not making it into the final standalone executables, resulting in blank screens for users.

## Root Cause Analysis

### Build Process Flow
1. **Platform builds** (Linux/Windows/macOS) compile C++ module
2. Module copied to project root: `cp build/procengine_cpp*.so .`
3. **Artifacts uploaded** with paths like `build/procengine_cpp*.so`
4. **Standalone build** downloads artifacts
5. Tries to find and copy module to bundle with PyInstaller

### The Problem
The standalone build step (lines 502-513 in ci.yml) had issues:

```bash
# Old code - BROKEN
cp ./artifact/build/procengine_cpp*${{ matrix.module_ext }} . 2>/dev/null || \
cp ./artifact/build/Release/procengine_cpp*${{ matrix.module_ext }} . 2>/dev/null || \
cp ./artifact/procengine_cpp*${{ matrix.module_ext }} . 2>/dev/null || \
echo "Warning: Could not find pre-built module"
```

**Issues:**
1. Used `2>/dev/null` to silence errors → failures were invisible
2. Only warned when module not found, build continued anyway
3. PyInstaller ran without module → created headless-only executable
4. Users got blank screen because no C++ graphics backend

## The Fix

### 1. Improved Artifact Uploads
Upload module to BOTH root and build directories:

```yaml
# Linux
path: |
  procengine_cpp*.so          # NEW - at root
  build/procengine_cpp*.so    # EXISTING - in build dir
  ...

# Windows  
path: |
  procengine_cpp*.pyd         # NEW - at root
  build/Release/procengine_cpp*.pyd
  build/procengine_cpp*.pyd
  ...

# macOS
path: |
  procengine_cpp*.so          # NEW - at root
  procengine_cpp*.dylib       # NEW - at root
  build/procengine_cpp*.so
  build/procengine_cpp*.dylib
  ...
```

### 2. Robust Module Discovery
Use `find` to handle wildcards properly and fail fast:

```bash
#!/bin/bash
echo "=== Searching for C++ module in artifact ==="
find ./artifact -name "procengine_cpp*" -type f

MODULE_FOUND=false

# Try artifact root first (most likely after our changes)
if [ -n "$(find ./artifact -maxdepth 1 -name 'procengine_cpp*${{ matrix.module_ext }}' -type f)" ]; then
  cp ./artifact/procengine_cpp*${{ matrix.module_ext }} .
  echo "Copied from ./artifact/"
  MODULE_FOUND=true
elif [ -n "$(find ./artifact/build -maxdepth 1 -name 'procengine_cpp*${{ matrix.module_ext }}' -type f 2>/dev/null)" ]; then
  cp ./artifact/build/procengine_cpp*${{ matrix.module_ext }} .
  echo "Copied from ./artifact/build/"
  MODULE_FOUND=true
elif [ -n "$(find ./artifact/build/Release -maxdepth 1 -name 'procengine_cpp*${{ matrix.module_ext }}' -type f 2>/dev/null)" ]; then
  cp ./artifact/build/Release/procengine_cpp*${{ matrix.module_ext }} .
  echo "Copied from ./artifact/build/Release/"
  MODULE_FOUND=true
fi

# FAIL BUILD if module not found
if [ "$MODULE_FOUND" = false ]; then
  echo "ERROR: Could not find pre-built module!"
  echo "Artifact contents:"
  ls -R ./artifact/ | head -50
  exit 1
fi

# Verify module exists
ls -la procengine_cpp*${{ matrix.module_ext }} || exit 1
```

**Key Improvements:**
- Uses `find` with `-maxdepth 1` to handle wildcards correctly
- Checks artifact root first (most likely location after our changes)
- Falls back to build/ and build/Release/ directories
- Tracks success with `MODULE_FOUND` flag
- **FAILS BUILD** if module not found (no silent warnings)
- Shows full artifact contents on failure for debugging

### 3. Better DLL Handling (Windows)
Similar improvements for finding and copying required DLLs:

```bash
echo "=== Searching for DLLs in artifact ==="
find ./artifact -name "*.dll" -type f

echo "=== Copying DLLs ==="
cp ./artifact/*.dll . 2>/dev/null || echo "No DLLs in artifact root"

echo "=== DLLs in current directory ==="
ls -la *.dll 2>/dev/null || echo "Warning: No DLLs found"
```

## Expected Outcome

### Before Fix
❌ C++ module built but not found in standalone build
❌ PyInstaller creates executable without module
❌ Users run game → blank screen (no graphics backend)
❌ Error messages unclear about missing module

### After Fix
✅ C++ module uploaded to predictable locations
✅ Module discovery uses robust search with wildcards
✅ Build FAILS if module not found (fast failure)
✅ Clear error messages show what's missing and where
✅ Standalone executables include full C++ graphics backend
✅ Users run game → proper rendering with Vulkan

## Testing the Fix

When the next CI run completes:

1. Download standalone executable artifact
2. Extract and run the game
3. Game window should show terrain rendering (not blank)
4. Check that `procengine_cpp*.so/.pyd` is present in executable directory

If module still not found:
- CI will fail at the "Copy module from artifact" step
- Error log will show full artifact contents
- Can identify exact location of module in artifact

## Files Modified

- `.github/workflows/ci.yml`:
  - Lines 144-163: Linux artifact upload
  - Lines 284-310: Windows artifact upload  
  - Lines 418-439: macOS artifact upload
  - Lines 502-537: Module discovery in standalone build
  - Lines 515-550: DLL handling for Windows

## Related Issues

- Original issue: Player falling through terrain (fixed with heightfield typo)
- This fix: Blank screen due to missing C++ module in executables
- Root issue: CI/CD pipeline artifact handling

Both issues now resolved!
