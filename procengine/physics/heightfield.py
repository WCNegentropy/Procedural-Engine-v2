"""Heightfield collision proxies for physics.

This module provides 1D and 2D heightfield terrain collision:
- HeightField: 1D heightfield for 2D physics
- HeightField2D: 2D heightfield for 3D physics with bilinear interpolation
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


__all__ = ["HeightField", "HeightField2D"]


@dataclass
class HeightField:
    """Simple 1D heightfield collision proxy.

    The field samples are spaced evenly along the X axis and represent the
    minimum allowed Y coordinate.  Bodies are kept above the sampled height
    plus their radius and may bounce with the configured restitution.
    """

    heights: np.ndarray
    x0: float = 0.0
    cell_size: float = 1.0

    def __post_init__(self) -> None:
        self.heights = np.asarray(self.heights, dtype=np.float32)
        if self.cell_size <= 0:
            raise ValueError("cell_size must be positive")

    def sample(self, x: float) -> float:
        """Return the height at horizontal coordinate ``x``."""

        idx = int(math.floor((x - self.x0) / self.cell_size))
        idx = max(0, min(int(len(self.heights) - 1), idx))
        return float(self.heights[idx])


@dataclass
class HeightField2D:
    """2D heightfield for terrain collision in 3D physics.

    Samples are arranged on a 2D grid (X, Z) and represent the ground
    height (Y coordinate). Uses bilinear interpolation for smooth sampling.

    Attributes
    ----------
    heights:
        2D numpy array of height values (shape: [size_z, size_x]).
    x0:
        X coordinate of the first sample.
    z0:
        Z coordinate of the first sample.
    cell_size:
        Spacing between samples in both X and Z directions.
    """

    heights: np.ndarray
    x0: float = 0.0
    z0: float = 0.0
    cell_size: float = 1.0

    def __post_init__(self) -> None:
        self.heights = np.asarray(self.heights, dtype=np.float32)
        if self.heights.ndim != 2:
            raise ValueError("heights must be a 2D array")
        if self.cell_size <= 0:
            raise ValueError("cell_size must be positive")

    @property
    def size_x(self) -> int:
        """Number of samples in X direction."""
        return self.heights.shape[1]

    @property
    def size_z(self) -> int:
        """Number of samples in Z direction."""
        return self.heights.shape[0]

    def in_bounds(self, x: float, z: float) -> bool:
        """Check if coordinates are within the heightfield bounds."""
        x_max = self.x0 + self.cell_size * (self.size_x - 1)
        z_max = self.z0 + self.cell_size * (self.size_z - 1)
        return self.x0 <= x <= x_max and self.z0 <= z <= z_max

    def sample(self, x: float, z: float) -> float:
        """Sample height at (x, z) with bilinear interpolation.

        Returns the interpolated height value. Coordinates outside
        the heightfield are clamped to the nearest edge.
        """
        if self.heights.size == 0:
            return 0.0

        # Convert world coordinates to grid coordinates
        local_x = (x - self.x0) / self.cell_size
        local_z = (z - self.z0) / self.cell_size

        # Get integer indices and fractional parts
        ix0 = int(math.floor(local_x))
        iz0 = int(math.floor(local_z))
        ix1 = ix0 + 1
        iz1 = iz0 + 1

        # Clamp indices to valid range
        ix0 = max(0, min(ix0, self.size_x - 1))
        ix1 = max(0, min(ix1, self.size_x - 1))
        iz0 = max(0, min(iz0, self.size_z - 1))
        iz1 = max(0, min(iz1, self.size_z - 1))

        # Fractional parts for interpolation
        fx = local_x - math.floor(local_x)
        fz = local_z - math.floor(local_z)
        fx = max(0.0, min(1.0, fx))
        fz = max(0.0, min(1.0, fz))

        # Bilinear interpolation
        h00 = float(self.heights[iz0, ix0])
        h10 = float(self.heights[iz0, ix1])
        h01 = float(self.heights[iz1, ix0])
        h11 = float(self.heights[iz1, ix1])

        h0 = h00 * (1.0 - fx) + h10 * fx
        h1 = h01 * (1.0 - fx) + h11 * fx

        return h0 * (1.0 - fz) + h1 * fz
