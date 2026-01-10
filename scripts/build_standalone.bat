@echo off
REM =============================================================================
REM Build script for Procedural Engine standalone executable (Windows)
REM =============================================================================
REM
REM Usage:
REM   scripts\build_standalone.bat [OPTIONS]
REM
REM Options:
REM   /clean       Clean build directories before building
REM   /release     Build with optimizations (default)
REM   /debug       Build with debug symbols
REM   /onefile     Create single-file executable (slower startup)
REM   /novulkan    Build without Vulkan (headless mode)
REM
REM Requirements:
REM   - Python 3.10+
REM   - Visual Studio 2019+ with C++ tools
REM   - CMake 3.14+
REM   - Vulkan SDK (unless /novulkan)
REM   - PyInstaller (pip install pyinstaller)
REM
REM =============================================================================

setlocal enabledelayedexpansion

REM Script directory and project root
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "PROJECT_ROOT=%CD%"
popd

REM Default options
set CLEAN=false
set BUILD_TYPE=Release
set ONEFILE=false
set NO_VULKAN=false

REM Parse arguments
:parse_args
if "%~1"=="" goto end_parse
if /i "%~1"=="/clean" (
    set CLEAN=true
    shift
    goto parse_args
)
if /i "%~1"=="/release" (
    set BUILD_TYPE=Release
    shift
    goto parse_args
)
if /i "%~1"=="/debug" (
    set BUILD_TYPE=Debug
    shift
    goto parse_args
)
if /i "%~1"=="/onefile" (
    set ONEFILE=true
    shift
    goto parse_args
)
if /i "%~1"=="/novulkan" (
    set NO_VULKAN=true
    shift
    goto parse_args
)
echo Unknown option: %~1
exit /b 1
:end_parse

echo ========================================
echo Procedural Engine Build Script (Windows)
echo ========================================
echo.
echo Project root: %PROJECT_ROOT%
echo Build type: %BUILD_TYPE%
echo One-file mode: %ONEFILE%
echo No Vulkan: %NO_VULKAN%
echo.

cd /d "%PROJECT_ROOT%"

REM =============================================================================
REM Step 1: Clean if requested
REM =============================================================================

if "%CLEAN%"=="true" (
    echo Cleaning build directories...
    if exist build rmdir /s /q build
    if exist cpp\build rmdir /s /q cpp\build
    if exist dist rmdir /s /q dist
    del /q procengine_cpp*.pyd 2>nul
    echo Clean complete
    echo.
)

REM =============================================================================
REM Step 2: Check for Visual Studio
REM =============================================================================

where cmake >nul 2>&1
if errorlevel 1 (
    echo ERROR: CMake not found. Please install CMake and add to PATH.
    exit /b 1
)

REM Try to find Visual Studio
set VS_FOUND=false
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" (
    call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
    set VS_FOUND=true
)
if "%VS_FOUND%"=="false" (
    if exist "C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat" (
        call "C:\Program Files\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
        set VS_FOUND=true
    )
)
if "%VS_FOUND%"=="false" (
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat" (
        call "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
        set VS_FOUND=true
    )
)

REM =============================================================================
REM Step 3: Build C++ extension module
REM =============================================================================

echo Building C++ extension module...

if not exist cpp\build mkdir cpp\build
cd cpp\build

set CMAKE_ARGS=-DCMAKE_BUILD_TYPE=%BUILD_TYPE%
if "%NO_VULKAN%"=="true" (
    set CMAKE_ARGS=%CMAKE_ARGS% -DNO_GRAPHICS=ON
)

cmake .. %CMAKE_ARGS% -G "Visual Studio 17 2022" -A x64
if errorlevel 1 (
    REM Try VS 2019 if 2022 failed
    cmake .. %CMAKE_ARGS% -G "Visual Studio 16 2019" -A x64
)
if errorlevel 1 (
    echo ERROR: CMake configuration failed
    exit /b 1
)

cmake --build . --config %BUILD_TYPE% --parallel
if errorlevel 1 (
    echo ERROR: Build failed
    exit /b 1
)

cd /d "%PROJECT_ROOT%"

REM Copy the built module
for /r cpp\build %%f in (procengine_cpp*.pyd) do copy "%%f" . >nul 2>&1
for /r cpp\build %%f in (*procengine_cpp*.dll) do copy "%%f" . >nul 2>&1

if exist procengine_cpp*.pyd (
    echo C++ module built successfully
) else (
    echo ERROR: Failed to find built C++ module
    exit /b 1
)
echo.

REM =============================================================================
REM Step 4: Install Python dependencies
REM =============================================================================

echo Installing Python dependencies...

pip install --quiet pyinstaller numpy
pip install --quiet -e .

echo Dependencies installed
echo.

REM =============================================================================
REM Step 5: Run PyInstaller
REM =============================================================================

echo Building standalone executable with PyInstaller...

set PYINSTALLER_ARGS=ProceduralEngine.spec --noconfirm

pyinstaller %PYINSTALLER_ARGS%
if errorlevel 1 (
    echo ERROR: PyInstaller failed
    exit /b 1
)

echo PyInstaller build complete
echo.

REM =============================================================================
REM Step 6: Copy Vulkan runtime DLLs
REM =============================================================================

if "%NO_VULKAN%"=="false" (
    echo Copying Vulkan runtime...
    
    if defined VULKAN_SDK (
        if exist "%VULKAN_SDK%\Bin\vulkan-1.dll" (
            copy "%VULKAN_SDK%\Bin\vulkan-1.dll" dist\ProceduralEngine\ >nul 2>&1
            echo Copied vulkan-1.dll
        )
    )
)

REM Copy Visual C++ runtime (if not statically linked)
REM Users will need Visual C++ Redistributable installed, or we include the DLLs

REM =============================================================================
REM Step 7: Verify output
REM =============================================================================

echo Verifying build output...

if exist dist\ProceduralEngine\ProceduralEngine.exe (
    echo.
    echo ========================================
    echo BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Output directory: %PROJECT_ROOT%\dist\ProceduralEngine
    echo.
    echo Contents:
    dir /b dist\ProceduralEngine
    echo.
    
    REM Test run
    echo Testing executable...
    dist\ProceduralEngine\ProceduralEngine.exe --help >nul 2>&1
    if errorlevel 1 (
        echo Warning: Executable may require Vulkan runtime
    ) else (
        echo Executable runs successfully!
    )
) else (
    echo ERROR: Build failed - no executable found
    exit /b 1
)

echo.
echo To distribute:
echo   1. Copy dist\ProceduralEngine\ to your distribution folder
echo   2. Include Visual C++ Redistributable installer
echo   3. For Steam, use Steamworks SDK to create depot

endlocal
