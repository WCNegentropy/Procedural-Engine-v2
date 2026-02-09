"""Setup script for building the Procedural Engine with C++ extensions."""

import os
import subprocess
import sys
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class CMakeExtension(Extension):
    """CMake-based extension for pybind11 module."""

    def __init__(self, name: str, sourcedir: str = "") -> None:
        super().__init__(name, sources=[])
        self.sourcedir = os.fspath(Path(sourcedir).resolve())


class CMakeBuild(build_ext):
    """Custom build command that invokes CMake."""

    def build_extension(self, ext: CMakeExtension) -> None:
        ext_fullpath = Path.cwd() / self.get_ext_fullpath(ext.name)
        extdir = ext_fullpath.parent.resolve()

        # CMake configuration
        cmake_args = [
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}{os.sep}",
            f"-DPYTHON_EXECUTABLE={sys.executable}",
            f"-DCMAKE_BUILD_TYPE=Release",
        ]

        # Check for CI environment or explicit headless mode
        if os.environ.get("CI") or os.environ.get("NO_GRAPHICS"):
            cmake_args.append("-DNO_GRAPHICS=ON")
            print("Building in headless mode (NO_GRAPHICS=ON)")

        # Platform-specific configuration
        if sys.platform.startswith("darwin"):
            # macOS: use Homebrew OpenSSL
            openssl_prefix = subprocess.run(
                ["brew", "--prefix", "openssl"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if openssl_prefix:
                cmake_args.append(f"-DOPENSSL_ROOT_DIR={openssl_prefix}")

        elif sys.platform == "win32":
            # Windows: use common OpenSSL location
            for openssl_path in [
                "C:/Program Files/OpenSSL",
                "C:/Program Files/OpenSSL-Win64",
            ]:
                if os.path.exists(openssl_path):
                    cmake_args.append(f"-DOPENSSL_ROOT_DIR={openssl_path}")
                    break

        build_args = ["--config", "Release", "--parallel"]

        # Build directory
        build_temp = Path(self.build_temp) / ext.name
        build_temp.mkdir(parents=True, exist_ok=True)

        # Run CMake configure
        subprocess.run(
            ["cmake", ext.sourcedir, *cmake_args],
            cwd=build_temp,
            check=True,
        )

        # Run CMake build
        subprocess.run(
            ["cmake", "--build", ".", *build_args],
            cwd=build_temp,
            check=True,
        )


setup(
    ext_modules=[CMakeExtension("procengine_cpp", sourcedir="cpp")],
    cmdclass={"build_ext": CMakeBuild},
)
