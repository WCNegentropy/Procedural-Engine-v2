"""Deterministic terrain map generation utilities.

This module provides reference implementations for generating height,
temperature, humidity, biome, and river maps using NumPy.  All randomness
flows through :class:`~seed_registry.SeedRegistry` to satisfy the
determinism contract defined in ``AGENTS.md``.  The algorithms are light
weight, NumPy based stand‑ins for their C++ counterparts and are intended
for tests and design exploration.

Height generation uses multi-layer noise combining:
- Continent-scale noise for large landmasses and ocean basins
- FBM detail noise for surface variation
- Ridged noise for mountain ranges and valleys
- Optional macro-plate (Voronoi) ridges

Biomes use a proper sea-level system: terrain below ``SEA_LEVEL`` is
classified as ocean (Deep Ocean, Ocean, or Frozen Ocean depending on
depth and temperature).  Land biomes are assigned via a temperature ×
humidity × elevation look-up table.
"""
from __future__ import annotations

from typing import Tuple

import math
import numpy as np

from procengine.core.seed_registry import SeedRegistry


__all__ = ["generate_terrain_maps", "SEA_LEVEL"]

# ---------------------------------------------------------------------------
# Global constants
# ---------------------------------------------------------------------------

SEA_LEVEL: float = 0.35
"""Height threshold separating ocean from land.  Terrain with height values
below this is classified as an ocean biome.  The value is chosen so that
roughly 35% of a uniform-random heightmap would be underwater, creating
a realistic land-to-water ratio."""


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


def _ridged_noise(
    rng: np.random.Generator,
    size: int,
    octaves: int = 5,
    offset_x: float = 0.0,
    offset_z: float = 0.0,
    base_frequency: float = 0.01,
) -> np.ndarray:
    """Generate ridged multi-fractal noise for mountain ranges.

    Ridged noise takes the absolute value of simplex noise, inverts it, and
    layers multiple octaves with decreasing amplitude.  The result has sharp
    ridge lines surrounded by smooth valleys — ideal for mountain chains.

    Parameters
    ----------
    rng:
        NumPy random generator for deterministic permutation.
    size:
        Width and height of the grid.
    octaves:
        Number of noise layers.
    offset_x / offset_z:
        World-space offsets for seamless tiling across chunks.
    base_frequency:
        Base frequency for the lowest octave.
    """
    perm = rng.permutation(256)
    perm = np.concatenate([perm, perm])

    height = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = base_frequency
    total_amplitude = 0.0
    prev = np.ones((size, size), dtype=np.float32)  # weight by previous octave

    for _ in range(octaves):
        raw = _simplex_grid(perm, size, frequency, offset_x, offset_z)
        # Ridged: 1 - |noise|  →  peaks become ridges
        ridged = 1.0 - np.abs(raw)
        ridged = ridged * ridged  # sharpen ridges
        ridged *= prev  # weight by previous layer for detail cascading
        height += ridged * amplitude
        total_amplitude += amplitude
        prev = ridged
        amplitude *= 0.5
        frequency *= 2.0

    if total_amplitude > 0.0:
        height /= total_amplitude
        np.clip(height, 0.0, 1.0, out=height)

    return height


def _continent_noise(
    rng: np.random.Generator,
    size: int,
    offset_x: float = 0.0,
    offset_z: float = 0.0,
    base_frequency: float = 0.003,
) -> np.ndarray:
    """Generate very-low-frequency continent-scale noise.

    This creates large, smooth landmasses surrounded by ocean basins.
    Using only 2–3 octaves at very low frequency produces broad features
    that span many chunks.  A cubic remapping steepens coastlines while
    keeping interiors smooth.

    Parameters
    ----------
    rng:
        NumPy random generator for deterministic permutation.
    size:
        Width and height of the grid.
    offset_x / offset_z:
        World-space offsets for seamless tiling across chunks.
    base_frequency:
        Base frequency (default 0.003 → one noise cycle per ~333 world
        units, giving continent-sized features).
    """
    perm = rng.permutation(256)
    perm = np.concatenate([perm, perm])

    height = np.zeros((size, size), dtype=np.float32)
    amplitude = 1.0
    frequency = base_frequency
    total_amplitude = 0.0
    for _ in range(3):  # only 3 octaves for broad features
        height += _simplex_grid(perm, size, frequency, offset_x, offset_z) * amplitude
        total_amplitude += amplitude
        amplitude *= 0.45
        frequency *= 2.0

    if total_amplitude > 0.0:
        height = (height / total_amplitude) * 0.5 + 0.5
        np.clip(height, 0.0, 1.0, out=height)

    # Cubic remap: steepen the coastline transition while keeping
    # deep ocean floors and continental interiors relatively flat.
    # Shift center slightly above 0.5 so that ~55-60% of area is land.
    height = np.clip(height * 1.1 - 0.05, 0.0, 1.0)
    # Power curve pushes lows lower (deeper oceans) while keeping
    # heights that are already 1.0 at 1.0.  No per-chunk normalisation
    # is applied so the output is globally consistent across chunks.
    height = height ** 1.5

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

    # Normalize: clip distances to [0, 1] range and invert for ridges.
    # In a standard Voronoi diagram with one point per unit cell, the maximum
    # distance from any point to its nearest feature is bounded by the cell
    # diagonal (sqrt(2) ≈ 1.41). Clipping to 1.0 captures most of the range
    # while ensuring consistent output. Inversion gives 1.0 at cell centers
    # (plate interiors) and lower values at cell edges (plate boundaries).
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

    Height is built from multiple noise layers:

    * **Continent noise** — very-low-frequency FBM that defines broad
      landmasses and ocean basins.
    * **Detail FBM** — standard fractal Brownian motion for surface texture.
    * **Ridged noise** — ridged multi-fractal for mountain chains and
      valleys.
    * **Macro plates** (optional) — global ridged-Voronoi features.

    Biomes are assigned using a sea-level threshold (``SEA_LEVEL``).
    Terrain below the threshold receives an ocean biome (Deep Ocean,
    Ocean, or Frozen Ocean).  Land terrain is classified by temperature,
    humidity, and elevation above sea level.

    Parameters
    ----------
    registry:
        Shared ``SeedRegistry`` providing deterministic RNG streams.
    size:
        Width and height of the generated square maps.
    octaves:
        Number of FBM layers used for detail heightmap synthesis.
    macro_points:
        Number of Voronoi sites used for macro plate ridges. ``0`` disables
        the macro layer.
    erosion_iters:
        Number of iterations of the simple hydraulic erosion simulation to
        run. ``0`` disables erosion.
    return_slope:
        If ``True`` also compute and return a normalized slope map derived
        from ``height``.
    offset_x:
        World-space X offset for seamless tiling across chunks.
    offset_z:
        World-space Z offset for seamless tiling across chunks.
    base_frequency:
        Base frequency for terrain noise (default 0.01 = one full noise
        cycle per 100 world units).
    """

    # ------------------------------------------------------------------
    # 1. Continent mask — broad landmasses & ocean basins
    # ------------------------------------------------------------------
    rng_continent = registry.get_rng("terrain_continent")
    continent = _continent_noise(
        rng_continent, size=size,
        offset_x=offset_x, offset_z=offset_z,
        base_frequency=base_frequency * 0.25,
    )

    # ------------------------------------------------------------------
    # 2. Detail FBM — fine surface variation
    # ------------------------------------------------------------------
    rng_height = registry.get_rng("terrain_height")
    detail = _fbm_noise(
        rng_height, size=size, octaves=octaves,
        offset_x=offset_x, offset_z=offset_z, base_frequency=base_frequency,
    )

    # ------------------------------------------------------------------
    # 3. Ridged noise — mountain ranges / valleys
    # ------------------------------------------------------------------
    rng_ridge = registry.get_rng("terrain_ridge")
    ridges = _ridged_noise(
        rng_ridge, size=size, octaves=min(octaves, 5),
        offset_x=offset_x, offset_z=offset_z,
        base_frequency=base_frequency * 0.5,
    )

    # ------------------------------------------------------------------
    # 4. Combine layers
    # ------------------------------------------------------------------
    #   continent   controls the broad shape  (weight 0.55)
    #   detail      adds surface roughness    (weight 0.20)
    #   ridges      carve mountain chains     (weight 0.25)
    height = continent * 0.55 + detail * 0.20 + ridges * 0.25
    np.clip(height, 0.0, 1.0, out=height)

    # ------------------------------------------------------------------
    # 5. Macro plates (optional Voronoi ridges)
    # ------------------------------------------------------------------
    macro_seed = 0
    macro_freq = 0.0
    if macro_points > 0:
        macro_seed = registry.get_subseed("terrain_macro") & 0xFFFFFFFF
        macro_freq = math.sqrt(macro_points) / float(size)

        macro = _global_ridged_voronoi(
            size=size,
            offset_x=offset_x,
            offset_z=offset_z,
            frequency=macro_freq,
            seed=macro_seed,
        )
        # Blend macro plates lightly so they influence shape without
        # dominating the continent/ridge structure.
        height = np.clip(height * 0.8 + macro * 0.2, 0.0, 1.0)

    # ------------------------------------------------------------------
    # 6. Hydraulic erosion (optional)
    # ------------------------------------------------------------------
    if erosion_iters > 0:
        rng_erosion = registry.get_rng("terrain_erosion")
        height = _hydraulic_erosion(height, rng_erosion, erosion_iters)

    # ------------------------------------------------------------------
    # 7. Temperature & humidity (for biome selection)
    # ------------------------------------------------------------------
    biome_frequency = base_frequency * 0.5
    rng_temp = registry.get_rng("terrain_temp")
    temperature = _fbm_noise(
        rng_temp, size=size, octaves=2,
        offset_x=offset_x, offset_z=offset_z, base_frequency=biome_frequency,
    )
    rng_humid = registry.get_rng("terrain_humidity")
    humidity = _fbm_noise(
        rng_humid, size=size, octaves=2,
        offset_x=offset_x, offset_z=offset_z, base_frequency=biome_frequency,
    )

    # ------------------------------------------------------------------
    # 8. Biome assignment with proper sea-level water
    # ------------------------------------------------------------------
    biome = _assign_biomes(height, temperature, humidity)

    # ------------------------------------------------------------------
    # 9. Rivers (coherent FBM threshold — only on land)
    # ------------------------------------------------------------------
    rng_river = registry.get_rng("terrain_river")
    river_noise = _fbm_noise(
        rng_river, size=size, octaves=4,
        offset_x=offset_x, offset_z=offset_z,
        base_frequency=base_frequency * 2.0,
    )
    river = (np.abs(river_noise - 0.5) < 0.025).astype(np.uint8)
    # Mask out rivers that fall in the ocean
    river[height < SEA_LEVEL] = 0

    # ------------------------------------------------------------------
    # 10. Slope (optional, with ghost-buffer padding)
    # ------------------------------------------------------------------
    if return_slope:
        slope = _compute_slope_with_ghost(
            registry, size, octaves, macro_points, macro_seed, macro_freq,
            offset_x, offset_z, base_frequency,
        )
        return height.astype(np.float32), biome, river, slope

    return height.astype(np.float32), biome, river


# -----------------------------------------------------------------------
# Biome assignment
# -----------------------------------------------------------------------

# Biome IDs (kept at 16 for C++ colour-palette compatibility)
#  0  DeepOcean       4  Taiga          8  Mountain     12  Mesa
#  1  Ocean           5  SnowyMountain  9  Swamp        13  Jungle
#  2  FrozenOcean     6  Plains        10  Desert       14  Beach
#  3  Tundra          7  Forest        11  Savanna      15  Glacier

# Land biome LUT: [temperature_bin][humidity_bin][elevation_bin]
# temperature bins: cold(0), temperate(1), hot(2)
# humidity bins:    dry(0), normal(1), wet(2)
# elevation bins above sea level: low(0), mid(1), high(2)
_LAND_BIOME_LUT = np.array(
    [
        # cold
        [
            [3, 3, 5],    # dry   -> Tundra, Tundra, SnowyMountain
            [4, 4, 5],    # normal -> Taiga, Taiga, SnowyMountain
            [4, 15, 15],  # wet   -> Taiga, Glacier, Glacier
        ],
        # temperate
        [
            [6, 6, 8],    # dry   -> Plains, Plains, Mountain
            [7, 7, 8],    # normal -> Forest, Forest, Mountain
            [9, 7, 8],    # wet   -> Swamp, Forest, Mountain
        ],
        # hot
        [
            [10, 10, 12],  # dry   -> Desert, Desert, Mesa
            [11, 11, 12],  # normal -> Savanna, Savanna, Mesa
            [13, 13, 12],  # wet   -> Jungle, Jungle, Mesa
        ],
    ],
    dtype=np.uint8,
)


def _assign_biomes(
    height: np.ndarray,
    temperature: np.ndarray,
    humidity: np.ndarray,
) -> np.ndarray:
    """Assign biome IDs based on height, temperature, and humidity.

    Below ``SEA_LEVEL`` the terrain receives an ocean biome; above it a
    land biome is chosen from the temperature × humidity × elevation LUT.
    A narrow beach band is applied at the coastline.
    """

    biome = np.zeros_like(height, dtype=np.uint8)

    # --- Ocean biomes ---
    is_water = height < SEA_LEVEL
    is_deep = height < (SEA_LEVEL * 0.55)
    is_cold = temperature < 0.3

    # Deep ocean
    biome[is_water & is_deep] = 0
    # Frozen ocean (cold + not deep)
    biome[is_water & ~is_deep & is_cold] = 2
    # Regular ocean
    biome[is_water & ~is_deep & ~is_cold] = 1

    # --- Land biomes ---
    is_land = ~is_water

    # Normalise land elevation: [SEA_LEVEL, 1] → [0, 1]
    land_elev = np.clip((height - SEA_LEVEL) / (1.0 - SEA_LEVEL), 0.0, 1.0)

    # Beach: narrow coastal strip just above sea level
    beach_threshold = 0.06  # ~4% of land-elevation range
    is_beach = is_land & (land_elev < beach_threshold)
    biome[is_beach] = 14  # Beach

    # Remaining land uses the LUT
    is_inland = is_land & ~is_beach

    temp_idx = np.digitize(temperature, [0.33, 0.66])
    humid_idx = np.digitize(humidity, [0.33, 0.66])
    elev_idx = np.digitize(land_elev, [0.25, 0.6])

    land_biome = _LAND_BIOME_LUT[temp_idx, humid_idx, elev_idx]
    biome[is_inland] = land_biome[is_inland]

    return biome


# -----------------------------------------------------------------------
# Slope with ghost buffer (extracted for clarity)
# -----------------------------------------------------------------------

def _compute_slope_with_ghost(
    registry: SeedRegistry,
    size: int,
    octaves: int,
    macro_points: int,
    macro_seed: int,
    macro_freq: float,
    offset_x: float,
    offset_z: float,
    base_frequency: float,
) -> np.ndarray:
    """Compute slope using a 1-pixel ghost buffer on each edge."""

    padded_size = size + 2
    padded_offset_x = offset_x - 1.0
    padded_offset_z = offset_z - 1.0

    # Reproduce the same height-build pipeline on the padded grid
    rng_continent_p = registry.get_rng("terrain_continent_slope")
    continent_p = _continent_noise(
        rng_continent_p, size=padded_size,
        offset_x=padded_offset_x, offset_z=padded_offset_z,
        base_frequency=base_frequency * 0.25,
    )

    rng_height_p = registry.get_rng("terrain_height_slope")
    detail_p = _fbm_noise(
        rng_height_p, size=padded_size, octaves=octaves,
        offset_x=padded_offset_x, offset_z=padded_offset_z,
        base_frequency=base_frequency,
    )

    rng_ridge_p = registry.get_rng("terrain_ridge_slope")
    ridges_p = _ridged_noise(
        rng_ridge_p, size=padded_size, octaves=min(octaves, 5),
        offset_x=padded_offset_x, offset_z=padded_offset_z,
        base_frequency=base_frequency * 0.5,
    )

    height_padded = continent_p * 0.55 + detail_p * 0.20 + ridges_p * 0.25
    np.clip(height_padded, 0.0, 1.0, out=height_padded)

    if macro_points > 0:
        macro_padded = _global_ridged_voronoi(
            size=padded_size,
            offset_x=padded_offset_x,
            offset_z=padded_offset_z,
            frequency=macro_freq,
            seed=macro_seed,
        )
        height_padded = np.clip(height_padded * 0.8 + macro_padded * 0.2, 0.0, 1.0)

    slope_padded = _slope_map(height_padded)
    return slope_padded[1:-1, 1:-1].copy()
