#!/bin/bash
# =============================================================================
# Package script for Steam distribution
# =============================================================================
#
# Creates a Steam-ready distribution package with:
# - Standalone executable
# - Required runtime dependencies
# - Game data files
# - Steam integration files
#
# Usage:
#   ./scripts/package_steam.sh [OPTIONS]
#
# Options:
#   --platform    Target platform: linux, windows, macos (auto-detected)
#   --output      Output directory (default: dist/steam)
#   --appid       Steam App ID for launch options
#   --skip-build  Skip build step (use existing dist/ProceduralEngine)
#
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect platform
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macos"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    PLATFORM="windows"
else
    PLATFORM="linux"
fi

# Default options
OUTPUT_DIR="${PROJECT_ROOT}/dist/steam"
STEAM_APPID=""
SKIP_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --appid)
            STEAM_APPID="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Steam Distribution Packager${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Platform: ${PLATFORM}"
echo -e "Output: ${OUTPUT_DIR}"
echo ""

cd "$PROJECT_ROOT"

# =============================================================================
# Step 1: Build if needed
# =============================================================================

if [ "$SKIP_BUILD" = false ]; then
    echo -e "${YELLOW}Building standalone executable...${NC}"
    ./scripts/build_standalone.sh --release
    echo ""
fi

# Check for build output
if [ ! -d "dist/ProceduralEngine" ]; then
    echo -e "${RED}Error: dist/ProceduralEngine not found. Run build first.${NC}"
    exit 1
fi

# =============================================================================
# Step 2: Create Steam directory structure
# =============================================================================

echo -e "${YELLOW}Creating Steam package structure...${NC}"

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy main distribution
cp -r dist/ProceduralEngine/* "$OUTPUT_DIR/"

# =============================================================================
# Step 3: Add Steam-specific files
# =============================================================================

echo -e "${YELLOW}Adding Steam integration files...${NC}"

# Create steam_appid.txt (for development/testing)
if [ -n "$STEAM_APPID" ]; then
    echo "$STEAM_APPID" > "$OUTPUT_DIR/steam_appid.txt"
    echo -e "Created steam_appid.txt with App ID: ${STEAM_APPID}"
fi

# Create launch script wrapper (Linux)
if [ "$PLATFORM" = "linux" ]; then
    cat > "$OUTPUT_DIR/launch.sh" << 'EOF'
#!/bin/bash
# Steam launch wrapper for Procedural Engine
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set library path for bundled libraries
export LD_LIBRARY_PATH="$SCRIPT_DIR/lib:$LD_LIBRARY_PATH"

# Launch game
exec ./ProceduralEngine "$@"
EOF
    chmod +x "$OUTPUT_DIR/launch.sh"
fi

# Create launch script wrapper (macOS)
if [ "$PLATFORM" = "macos" ]; then
    cat > "$OUTPUT_DIR/launch.sh" << 'EOF'
#!/bin/bash
# Steam launch wrapper for Procedural Engine
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set library path for bundled libraries
export DYLD_LIBRARY_PATH="$SCRIPT_DIR/lib:$DYLD_LIBRARY_PATH"

# Launch game
exec ./ProceduralEngine "$@"
EOF
    chmod +x "$OUTPUT_DIR/launch.sh"
fi

# =============================================================================
# Step 4: Create VDF files for Steamworks
# =============================================================================

echo -e "${YELLOW}Creating Steamworks depot files...${NC}"

mkdir -p "$OUTPUT_DIR/../steamworks"

# App build script
cat > "$OUTPUT_DIR/../steamworks/app_build.vdf" << EOF
"appbuild"
{
    "appid" "${STEAM_APPID:-480}"  // Use 480 (Spacewar) for testing if no ID
    "desc" "Procedural Engine build"
    "buildoutput" "../output/"
    "contentroot" "../steam/"
    "setlive" ""  // Set to "default" to auto-publish
    "preview" "0"
    "local" ""
    
    "depots"
    {
        "${STEAM_APPID:-480}" "depot_build_${PLATFORM}.vdf"
    }
}
EOF

# Depot build script
cat > "$OUTPUT_DIR/../steamworks/depot_build_${PLATFORM}.vdf" << EOF
"DepotBuildConfig"
{
    "DepotID" "${STEAM_APPID:-480}"
    "ContentRoot" "../steam/"
    "FileMapping"
    {
        "LocalPath" "*"
        "DepotPath" "."
        "recursive" "1"
    }
    "FileExclusion" "*.pdb"
    "FileExclusion" "*.log"
    "FileExclusion" "steam_appid.txt"
}
EOF

# =============================================================================
# Step 5: Create installscript.vdf (runtime prerequisites)
# =============================================================================

if [ "$PLATFORM" = "windows" ]; then
    cat > "$OUTPUT_DIR/installscript.vdf" << 'EOF'
"InstallScript"
{
    "Registry"
    {
        // No registry entries needed
    }
    
    "Run Process"
    {
        // Install Visual C++ Redistributable if needed
        "vc_redist.x64.exe"
        {
            "HasRunKey" "HKEY_LOCAL_MACHINE\\Software\\Valve\\Steam\\Apps\\Common\\ProceduralEngine"
            "process 1" "%INSTALLDIR%\\redist\\vc_redist.x64.exe"
            "command 1" "/install /quiet /norestart"
            "NoCleanUp" "1"
        }
    }
}
EOF
fi

# =============================================================================
# Step 6: Summary
# =============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Steam Package Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Package location: ${OUTPUT_DIR}"
echo ""
echo "Contents:"
ls -la "$OUTPUT_DIR" | head -20
echo ""

SIZE=$(du -sh "$OUTPUT_DIR" | cut -f1)
echo -e "Total size: ${SIZE}"
echo ""

echo "Next steps for Steam deployment:"
echo "  1. Set STEAM_APPID in steam_appid.txt (for your actual App ID)"
echo "  2. Download Steamworks SDK from partner.steamgames.com"
echo "  3. Configure app in Steamworks partner portal"
echo "  4. Run: steamcmd +login <user> +run_app_build steamworks/app_build.vdf +quit"
echo ""
echo "For local testing:"
echo "  - Copy steam_appid.txt with your App ID to test without Steam client"
echo "  - Or run directly: ${OUTPUT_DIR}/ProceduralEngine"
