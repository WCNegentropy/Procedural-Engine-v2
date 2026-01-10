#!/bin/bash
# =============================================================================
# Build script for Procedural Engine standalone executable (Linux/macOS)
# =============================================================================
#
# Usage:
#   ./scripts/build_standalone.sh [OPTIONS]
#
# Options:
#   --clean       Clean build directories before building
#   --release     Build with optimizations (default: release)
#   --debug       Build with debug symbols
#   --onefile     Create single-file executable (slower startup)
#   --no-vulkan   Build without Vulkan (headless mode)
#
# Requirements:
#   - Python 3.10+
#   - CMake 3.14+
#   - Vulkan SDK (unless --no-vulkan)
#   - PyInstaller (pip install pyinstaller)
#
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default options
CLEAN=false
BUILD_TYPE="Release"
ONEFILE=false
NO_VULKAN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --release)
            BUILD_TYPE="Release"
            shift
            ;;
        --debug)
            BUILD_TYPE="Debug"
            shift
            ;;
        --onefile)
            ONEFILE=true
            shift
            ;;
        --no-vulkan)
            NO_VULKAN=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Procedural Engine Build Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Project root: ${PROJECT_ROOT}"
echo -e "Build type: ${BUILD_TYPE}"
echo -e "One-file mode: ${ONEFILE}"
echo -e "No Vulkan: ${NO_VULKAN}"
echo ""

cd "$PROJECT_ROOT"

# =============================================================================
# Step 1: Clean if requested
# =============================================================================

if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}Cleaning build directories...${NC}"
    rm -rf build/
    rm -rf cpp/build/
    rm -rf dist/
    rm -f procengine_cpp*.so procengine_cpp*.pyd
    echo -e "${GREEN}Clean complete${NC}"
    echo ""
fi

# =============================================================================
# Step 2: Build C++ extension module
# =============================================================================

echo -e "${YELLOW}Building C++ extension module...${NC}"

mkdir -p cpp/build
cd cpp/build

CMAKE_ARGS="-DCMAKE_BUILD_TYPE=${BUILD_TYPE}"
if [ "$NO_VULKAN" = true ]; then
    CMAKE_ARGS="${CMAKE_ARGS} -DNO_GRAPHICS=ON"
fi

cmake .. ${CMAKE_ARGS}
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)

# Copy the built module to project root
cd "$PROJECT_ROOT"
find cpp/build -name "procengine_cpp*.so" -exec cp {} . \; 2>/dev/null || true
find cpp/build -name "procengine_cpp*.dylib" -exec cp {} . \; 2>/dev/null || true

if ls procengine_cpp*.so 1> /dev/null 2>&1 || ls procengine_cpp*.dylib 1> /dev/null 2>&1; then
    echo -e "${GREEN}C++ module built successfully${NC}"
else
    echo -e "${RED}Failed to build C++ module${NC}"
    exit 1
fi
echo ""

# =============================================================================
# Step 3: Install Python dependencies
# =============================================================================

echo -e "${YELLOW}Installing Python dependencies...${NC}"

pip install --quiet pyinstaller numpy

# Also install as editable to make sure extension is importable
pip install --quiet -e .

echo -e "${GREEN}Dependencies installed${NC}"
echo ""

# =============================================================================
# Step 4: Run PyInstaller
# =============================================================================

echo -e "${YELLOW}Building standalone executable with PyInstaller...${NC}"

PYINSTALLER_ARGS="ProceduralEngine.spec --noconfirm"

if [ "$ONEFILE" = true ]; then
    # Modify spec for onefile mode (create temp spec)
    sed 's/exclude_binaries=True/exclude_binaries=False/' ProceduralEngine.spec > /tmp/onefile.spec
    sed -i 's/\[\],  # Leave empty for one-folder mode/a.binaries, a.zipfiles, a.datas,/' /tmp/onefile.spec
    PYINSTALLER_ARGS="/tmp/onefile.spec --noconfirm"
fi

pyinstaller ${PYINSTALLER_ARGS}

echo -e "${GREEN}PyInstaller build complete${NC}"
echo ""

# =============================================================================
# Step 5: Verify output
# =============================================================================

echo -e "${YELLOW}Verifying build output...${NC}"

if [ -d "dist/ProceduralEngine" ]; then
    echo -e "${GREEN}Build successful!${NC}"
    echo ""
    echo -e "Output directory: ${PROJECT_ROOT}/dist/ProceduralEngine"
    echo ""
    echo "Contents:"
    ls -la dist/ProceduralEngine/ | head -20
    echo ""
    
    # Get size
    SIZE=$(du -sh dist/ProceduralEngine | cut -f1)
    echo -e "Total size: ${SIZE}"
    echo ""
    
    # Test run (headless)
    echo -e "${YELLOW}Testing executable...${NC}"
    if ./dist/ProceduralEngine/ProceduralEngine --help > /dev/null 2>&1; then
        echo -e "${GREEN}Executable runs successfully!${NC}"
    else
        echo -e "${YELLOW}Warning: Executable may require Vulkan runtime${NC}"
    fi
elif [ -f "dist/ProceduralEngine" ]; then
    echo -e "${GREEN}One-file build successful!${NC}"
    echo ""
    SIZE=$(du -sh dist/ProceduralEngine | cut -f1)
    echo -e "Executable: dist/ProceduralEngine (${SIZE})"
else
    echo -e "${RED}Build failed - no output found${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Build complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "To distribute:"
echo "  1. Copy dist/ProceduralEngine/ to your distribution folder"
echo "  2. Ensure Vulkan runtime is installed on target systems"
echo "  3. For Steam, use Steamworks SDK to create depot"
