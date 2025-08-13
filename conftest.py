"""Pytest configuration ensuring project modules import correctly."""

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct module imports
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Add the optional C++ build directory to sys.path for integration tests
BUILD = ROOT / "build"
if BUILD.exists() and str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
