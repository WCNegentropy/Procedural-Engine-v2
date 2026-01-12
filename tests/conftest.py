"""Pytest configuration ensuring project modules import correctly."""

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct module imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Add the procengine package directory
PROCENGINE = ROOT / "procengine"
if str(PROCENGINE) not in sys.path:
    sys.path.insert(0, str(PROCENGINE))

# Add the optional C++ build directory to sys.path for integration tests
BUILD = ROOT / "build"
if BUILD.exists() and str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))

# On Windows with MSVC, the output is in build/Release/
BUILD_RELEASE = BUILD / "Release"
if BUILD_RELEASE.exists() and str(BUILD_RELEASE) not in sys.path:
    sys.path.insert(0, str(BUILD_RELEASE))
