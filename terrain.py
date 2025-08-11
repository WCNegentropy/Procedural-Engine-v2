"""Deterministic terrain map generation utilities.

This module provides reference implementations for generating height,
temperature, humidity, biome, and river maps using NumPy.  All randomness
flows through :class:`~seed_registry.SeedRegistry` to satisfy the
determinism contract defined in ``AGENTS.md``.  The algorithms are light
weight, NumPy based stand‑ins for their C++ counterparts and are intended
for tests and design exploration.
"""
from __future__ import annotations

from typing import Tuple

import math
import numpy as np

from seed_registry import SeedRegistry


__all__ = ["generate_terrain_maps"]


_GRAD2: np.ndarray = np.array(
    [
        [1, 1],
        [-1, 1],
        [1, -1],
        [-1, -1],
        [1, 0],
        [-1, 0],
        [0, 1],
        [0, -1],
    ],
    dtype=np.float32,
)


def _simplex2d(x: float, y: float, perm: np.ndarray) -> float:
    """Return 2D simplex noise value in ``[-1, 1]`` for coordinates ``(x, y)``.

    The implementation is a direct translation of Stefan Gustavson's reference
    algorithm and is intentionally loop based for clarity over speed.
    """

    F2 = 0.3660254037844386  # 0.5 * (sqrt(3) - 1)
    G2 = 0.21132486540518713  # (3 - sqrt(3)) / 6

    s = (x + y) * F2
    i = math.floor(x + s)
    j = math.floor(y + s)
    t = (i + j) * G2
    X0 = i - t
    Y0 = j - t
    x0 = x - X0
    y0 = y - Y0

    if x0 > y0:
        i1, j1 = 1, 0
    else:
        i1, j1 = 0, 1

    x1 = x0 - i1 + G2
    y1 = y0 - j1 + G2
    x2 = x0 - 1.0 + 2.0 * G2
    y2 = y0 - 1.0 + 2.0 * G2

    ii = i & 255
    jj = j & 255

    gi0 = perm[ii + perm[jj]] % 8
    gi1 = perm[ii + i1 + perm[jj + j1]] % 8
    gi2 = perm[ii + 1 + perm[jj + 1]] % 8

    n0 = 0.0
    n1 = 0.0
    n2 = 0.0

    t0 = 0.5 - x0 * x0 - y0 * y0
    if t0 > 0.0:
        t0 *= t0
        grad = _GRAD2[gi0]
        n0 = t0 * t0 * (grad[0] * x0 + grad[1] * y0)

    t1 = 0.5 - x1 * x1 - y1 * y1
    if t1 > 0.0:
        t1 *= t1
        grad = _GRAD2[gi1]
        n1 = t1 * t1 * (grad[0] * x1 + grad[1] * y1)

    t2 = 0.5 - x2 * x2 - y2 * y2
    if t2 > 0.0:
        t2 *= t2
        grad = _GRAD2[gi2]
        n2 = t2 * t2 * (grad[0] * x2 + grad[1] * y2)

    return 70.0 * (n0 + n1 + n2)


def _simplex_grid(perm: np.ndarray, size: int, frequency: float) -> np.ndarray:
    """Return a ``size`` × ``size`` grid of simplex noise."""

    grid = np.zeros((size, size), dtype=np.float32)
    for y in range(size):
        for x in range(size):
            nx = (x / size) * frequency
            ny = (y / size) * frequency
            grid[y, x] = _simplex2d(nx, ny, perm)
    return grid


def _fbm_noise(rng: np.random.Generator, size: int, octaves: int = 6) -> np.ndarray:
    """Generate fractal Brownian motion using 2D simplex noise."""

    perm = rng.permutation(256)
    perm = np.concatenate([perm, perm])

    height = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = 1.0
    for _ in range(octaves):
        height += _simplex_grid(perm, size, frequency) * amplitude
        amplitude *= 0.5
        frequency *= 2.0

    h_min = float(height.min())
    h_max = float(height.max())
    if h_max - h_min > 0.0:
        height = (height - h_min) / (h_max - h_min)
    return height


def _voronoi_ridged(
    rng: np.random.Generator, size: int, points: int = 8
) -> np.ndarray:
    """Return ridged Voronoi noise used for macro terrain plates."""

    seeds = rng.random((points, 2)) * size
    grid_y, grid_x = np.mgrid[0:size, 0:size]
    grid = np.stack((grid_x, grid_y), axis=-1)
    dists = np.linalg.norm(grid[:, :, None, :] - seeds[None, None, :, :], axis=-1)
    dists = dists.min(axis=-1)
    dists /= float(dists.max())
    ridged = 1.0 - dists
    return ridged.astype(np.float32)


def _hydraulic_erosion(
    height: np.ndarray, rng: np.random.Generator, iterations: int
) -> np.ndarray:
    """Apply a simple hydraulic erosion simulation to ``height``.

    The algorithm repeatedly samples random cells and relaxes them toward
    the mean of their local neighborhood.  While highly simplified compared
    to a real GPU implementation, it provides a deterministic stand‑in that
    smooths sharp peaks and fills small pits.
    """

    size = height.shape[0]
    h = height.copy()
    for _ in range(iterations):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        x0 = max(x - 1, 0)
        x1 = min(x + 1, size - 1)
        y0 = max(y - 1, 0)
        y1 = min(y + 1, size - 1)
        neighborhood = h[y0 : y1 + 1, x0 : x1 + 1]
        avg = float(neighborhood.mean())
        h[y, x] = (h[y, x] + avg) * 0.5

    np.clip(h, 0.0, 1.0, out=h)
    return h


def _slope_map(height: np.ndarray) -> np.ndarray:
    """Return a normalized slope map for ``height``."""

    gy, gx = np.gradient(height)
    slope = np.sqrt(gx * gx + gy * gy)
    s_min = float(slope.min())
    s_max = float(slope.max())
    if s_max > s_min:
        slope = (slope - s_min) / (s_max - s_min)
    else:
        slope.fill(0.0)
    return slope.astype(np.float32)


def generate_terrain_maps(
    registry: SeedRegistry,
    size: int = 64,
    *,
    octaves: int = 6,
    macro_points: int = 8,
    erosion_iters: int = 0,
    return_slope: bool = False,
) -> Tuple[np.ndarray, ...]:
    """Return deterministic terrain maps.

    Parameters
    ----------
    registry:
        Shared ``SeedRegistry`` providing deterministic RNG streams.
    size:
        Width and height of the generated square maps.
    octaves:
        Number of FBM layers used for heightmap synthesis.
    macro_points:
        Number of Voronoi sites used for macro plate ridges. ``0`` disables
        the macro layer.
    erosion_iters:
        Number of iterations of the simple hydraulic erosion simulation to
        run. ``0`` disables erosion.
    return_slope:
        If ``True`` also compute and return a normalized slope map derived from
        ``height``.
    """

    rng_height = registry.get_rng("terrain_height")
    height = _fbm_noise(rng_height, size=size, octaves=octaves)
    if macro_points > 0:
        rng_macro = registry.get_rng("terrain_macro")
        macro = _voronoi_ridged(rng_macro, size=size, points=macro_points)
        height = np.clip((height + macro) * 0.5, 0.0, 1.0)

    if erosion_iters > 0:
        rng_erosion = registry.get_rng("terrain_erosion")
        height = _hydraulic_erosion(height, rng_erosion, erosion_iters)

    # Temperature and humidity maps drive biome selection
    rng_temp = registry.get_rng("terrain_temp")
    temperature = _fbm_noise(rng_temp, size=size, octaves=2)
    rng_humid = registry.get_rng("terrain_humidity")
    humidity = _fbm_noise(rng_humid, size=size, octaves=2)

    temp_idx = np.digitize(temperature, [0.33, 0.66])
    humid_idx = np.digitize(humidity, [0.33, 0.66])
    height_idx = np.digitize(height, [0.3, 0.6])

    biome_lut = np.array(
        [
            # cold
            [
                [0, 0, 1],  # dry  -> water, water, tundra
                [0, 2, 3],  # normal -> water, boreal forest, snow
                [0, 4, 5],  # wet -> water, cold swamp, glacier
            ],
            # temperate
            [
                [0, 0, 6],  # dry -> water, water, steppe
                [0, 7, 8],  # normal -> water, forest, mountain
                [0, 9, 10],  # wet -> water, swamp, alpine
            ],
            # hot
            [
                [0, 0, 11],  # dry -> water, water, desert plateau
                [0, 12, 13],  # normal -> water, savanna, mesa
                [0, 14, 15],  # wet -> water, jungle, rainforest highland
            ],
        ],
        dtype=np.uint8,
    )

    biome = biome_lut[temp_idx, humid_idx, height_idx]

    rng_river = registry.get_rng("terrain_river")
    river = (rng_river.random((size, size)) < 0.05).astype(np.uint8)
    if return_slope:
        slope = _slope_map(height)
        return height.astype(np.float32), biome, river, slope
    return height.astype(np.float32), biome, river
