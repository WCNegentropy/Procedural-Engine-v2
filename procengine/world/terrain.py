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

from procengine.core.seed_registry import SeedRegistry


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


def _simplex_grid(
    perm: np.ndarray,
    size: int,
    frequency: float,
    offset_x: float = 0.0,
    offset_z: float = 0.0,
) -> np.ndarray:
    """Return a ``size`` × ``size`` grid of simplex noise.

    Parameters
    ----------
    perm:
        Permutation table for noise generation.
    size:
        Width and height of the grid.
    frequency:
        Frequency scale for noise (world units per cycle). Lower values
        create larger features. For seamless multi-chunk terrain, use
        values like 0.01 (one cycle per 100 world units).
    offset_x:
        World-space X offset for seamless tiling across chunks.
    offset_z:
        World-space Z offset for seamless tiling across chunks.
    """
    grid = np.zeros((size, size), dtype=np.float32)
    for y in range(size):
        for x in range(size):
            # Use true world coordinates for seamless tiling
            # No division by size - frequency controls feature scale directly
            world_x = float(x) + offset_x
            world_z = float(y) + offset_z
            nx = world_x * frequency
            nz = world_z * frequency
            grid[y, x] = _simplex2d(nx, nz, perm)
    return grid


def _fbm_noise(
    rng: np.random.Generator,
    size: int,
    octaves: int = 6,
    offset_x: float = 0.0,
    offset_z: float = 0.0,
    base_frequency: float = 0.01,
) -> np.ndarray:
    """Generate fractal Brownian motion using 2D simplex noise.

    Parameters
    ----------
    rng:
        NumPy random generator for deterministic permutation.
    size:
        Width and height of the grid.
    octaves:
        Number of noise layers to combine.
    offset_x:
        World-space X offset for seamless tiling across chunks.
    offset_z:
        World-space Z offset for seamless tiling across chunks.
    base_frequency:
        Base frequency for the lowest octave (default 0.01 = one cycle per
        100 world units, creating large features spanning ~2 chunks).
    """
    perm = rng.permutation(256)
    perm = np.concatenate([perm, perm])

    height = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = base_frequency
    total_amplitude = 0.0
    for _ in range(octaves):
        # Simplex noise is approx [-1, 1], so we accumulate amplitude
        height += _simplex_grid(perm, size, frequency, offset_x, offset_z) * amplitude
        total_amplitude += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    # Normalize globally based on theoretical range [-total, +total]
    # This ensures consistent scaling across all chunks
    if total_amplitude > 0.0:
        # Map [-total, total] -> [-1, 1] -> [0, 1]
        height = (height / total_amplitude) * 0.5 + 0.5
        np.clip(height, 0.0, 1.0, out=height)

    return height


def _voronoi_ridged(
    rng: np.random.Generator, size: int, points: int = 8
) -> np.ndarray:
    """Return ridged Voronoi noise used for macro terrain plates.

    .. deprecated::
        This function generates local Voronoi noise and causes seams at chunk
        boundaries. Use :func:`_global_ridged_voronoi` instead for seamless
        terrain across multiple chunks.
    """

    seeds = rng.random((points, 2)) * size
    grid_y, grid_x = np.mgrid[0:size, 0:size]
    grid = np.stack((grid_x, grid_y), axis=-1)
    dists = np.linalg.norm(grid[:, :, None, :] - seeds[None, None, :, :], axis=-1)
    dists = dists.min(axis=-1)
    dists /= float(dists.max())
    ridged = 1.0 - dists
    return ridged.astype(np.float32)


def _hash_coords(x: int, y: int, seed: int) -> Tuple[float, float]:
    """Deterministic hash returning a normalized 2D point [0,1] for grid coordinates.

    This function generates a pseudo-random offset for a cell in the global
    Voronoi grid. The same (x, y, seed) always returns the same result,
    ensuring seamless feature points across chunk boundaries.

    Parameters
    ----------
    x : int
        Cell X coordinate in the global grid.
    y : int
        Cell Y coordinate in the global grid.
    seed : int
        Global seed for the Voronoi pattern.

    Returns
    -------
    Tuple[float, float]
        Normalized (x, y) offset in range [0, 1] for the feature point within the cell.
    """
    # Simple integer mixing hash for speed and determinism
    h = (x * 374761393) ^ (y * 668265263) ^ seed
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF

    # Split 32-bit hash into two floats
    val_x = (h & 0xFFFF) / 65535.0
    val_y = ((h >> 16) & 0xFFFF) / 65535.0
    return val_x, val_y


def _global_ridged_voronoi(
    size: int,
    offset_x: float,
    offset_z: float,
    frequency: float = 0.02,
    seed: int = 12345
) -> np.ndarray:
    """Generate seamless ridged Voronoi noise using a global cellular grid.

    Unlike :func:`_voronoi_ridged`, this function uses world coordinates to
    determine feature points, ensuring that plate boundaries align correctly
    across chunk boundaries.

    Parameters
    ----------
    size : int
        Width and height of the output grid.
    offset_x : float
        World-space X offset (typically ``chunk_x * chunk_size``).
    offset_z : float
        World-space Z offset (typically ``chunk_z * chunk_size``).
    frequency : float
        Density of Voronoi cells. Higher values = more, smaller plates.
        Default 0.02 creates approximately one plate per 50 world units.
    seed : int
        Global seed for deterministic plate positions.

    Returns
    -------
    np.ndarray
        A ``size × size`` array of float32 values in [0, 1], where 1.0 is at
        plate centers and 0.0 is at plate edges (ridges).
    """
    # Pre-calculate world coordinates for the entire chunk
    y_indices, x_indices = np.mgrid[0:size, 0:size]
    world_x = x_indices.astype(np.float32) + offset_x
    world_z = y_indices.astype(np.float32) + offset_z

    # Convert to cell space
    px = world_x * frequency
    pz = world_z * frequency

    # Identify the min/max cell indices needed for this chunk (with 1 cell buffer)
    min_cx = int(math.floor(float(px.min()))) - 1
    max_cx = int(math.floor(float(px.max()))) + 1
    min_cz = int(math.floor(float(pz.min()))) - 1
    max_cz = int(math.floor(float(pz.max()))) + 1

    # Initialize minDist with a large value
    min_dists = np.full((size, size), 100.0, dtype=np.float32)

    # Iterate over relevant grid cells
    for cz in range(min_cz, max_cz + 1):
        for cx in range(min_cx, max_cx + 1):
            # Get the feature point for this cell
            ox, oz = _hash_coords(cx, cz, seed)

            # Global position of the feature point
            fp_x = float(cx) + ox
            fp_z = float(cz) + oz

            # Vectorized distance calculation to this feature point
            dx = px - fp_x
            dz = pz - fp_z
            dist_sq = dx * dx + dz * dz

            # Update minimum distance
            min_dists = np.minimum(min_dists, dist_sq)

    # Sqrt to get euclidean distance
    dists = np.sqrt(min_dists)

    # Normalize (assuming max dist is roughly sqrt(2)/2 ~ 0.7 for standard voronoi)
    # We invert to get ridges (1.0 at center, 0.0 at edges)
    dists = 1.0 - np.clip(dists, 0.0, 1.0)

    return dists.astype(np.float32)


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
    offset_x: float = 0.0,
    offset_z: float = 0.0,
    base_frequency: float = 0.01,
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
    offset_x:
        World-space X offset for seamless tiling across chunks. When generating
        adjacent chunks, pass ``chunk_x * size`` here.
    offset_z:
        World-space Z offset for seamless tiling across chunks. When generating
        adjacent chunks, pass ``chunk_z * size`` here.
    base_frequency:
        Base frequency for terrain noise (default 0.01 = one full noise cycle
        per 100 world units). Lower values create larger terrain features that
        span multiple chunks for a more realistic infinite world.
    """

    rng_height = registry.get_rng("terrain_height")
    height = _fbm_noise(
        rng_height, size=size, octaves=octaves,
        offset_x=offset_x, offset_z=offset_z, base_frequency=base_frequency
    )
    if macro_points > 0:
        # Use a deterministic seed derived from the registry for global Voronoi
        # This ensures the same plate pattern regardless of chunk loading order
        macro_seed = registry.get_subseed("terrain_macro") & 0xFFFFFFFF

        # Heuristic to convert "points" parameter to frequency:
        # 8 points in 64 units -> ~1 point every 22 units -> freq ~0.045
        macro_freq = math.sqrt(macro_points) / float(size)

        macro = _global_ridged_voronoi(
            size=size,
            offset_x=offset_x,
            offset_z=offset_z,
            frequency=macro_freq,
            seed=macro_seed
        )
        height = np.clip((height + macro) * 0.5, 0.0, 1.0)

    if erosion_iters > 0:
        rng_erosion = registry.get_rng("terrain_erosion")
        height = _hydraulic_erosion(height, rng_erosion, erosion_iters)

    # Temperature and humidity maps drive biome selection
    # Use a lower frequency for biomes to create larger biome regions
    biome_frequency = base_frequency * 0.5  # Biomes span ~twice the area of terrain features
    rng_temp = registry.get_rng("terrain_temp")
    temperature = _fbm_noise(
        rng_temp, size=size, octaves=2,
        offset_x=offset_x, offset_z=offset_z, base_frequency=biome_frequency
    )
    rng_humid = registry.get_rng("terrain_humidity")
    humidity = _fbm_noise(
        rng_humid, size=size, octaves=2,
        offset_x=offset_x, offset_z=offset_z, base_frequency=biome_frequency
    )

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
