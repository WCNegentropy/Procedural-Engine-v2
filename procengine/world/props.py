"""Procedural prop descriptor generation utilities.

This module implements deterministic descriptor generation for simple props
such as rocks, trees, buildings, and creatures based on
 :class:`~seed_registry.SeedRegistry`.  The descriptors are stand-ins for
more complex definitions used by the C++ runtime.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from procengine.core.seed_registry import SeedRegistry

__all__ = [
    "generate_rock_descriptors",
    "generate_tree_descriptors",
    "generate_building_descriptors",
    "generate_creature_descriptors",
    "generate_chunk_props",
]


def generate_rock_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic rock descriptors.

    Each descriptor contains a ``type`` string, a three component ``position``
    within ``[0, size]`` cubed, and a ``radius`` in absolute world units.  All
    randomness flows through ``registry`` to satisfy the determinism
    contract.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_rock")
    descriptors: List[Dict[str, object]] = []
    for i in range(count):
        position = rng.random(3) * size
        radius = float(rng.uniform(0.3, 1.2))
        noise_seed = int(rng.integers(0, 2**31))
        descriptors.append(
            {
                "type": "rock",
                "position": position.tolist(),
                "radius": radius,
                "noise_seed": noise_seed,
            }
        )
    return descriptors


def generate_tree_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    iterations_range: tuple[int, int] = (2, 4),
    angle_range: tuple[float, float] = (15.0, 45.0),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic tree descriptors.

    Each descriptor encodes a basic L-system used by the C++ runtime to
    synthesize a sweep-meshed tree skeleton.  The ``iterations`` and branch
    ``angle`` are randomized through ``registry`` to ensure reproducible
    variation.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_tree")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        iterations = int(
            rng.integers(iterations_range[0], iterations_range[1] + 1)
        )
        angle = float(rng.uniform(angle_range[0], angle_range[1]))
        descriptors.append(
            {
                "type": "tree",
                "axiom": "F",
                "rules": {"F": "F[+F]F[-F]F"},
                "angle": angle,
                "iterations": iterations,
            }
        )
    return descriptors


def generate_building_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
    splits_range: tuple[int, int] = (1, 3),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic building descriptors.

    Each descriptor encodes a simple binary space partitioning scheme using a
    shape grammar.  Buildings start as a root block of ``size`` cubed and are
    recursively split along either the X or Z axis a deterministic number of
    times.  The resulting tree of blocks is expressed as nested dictionaries.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_building")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        root = {"shape": "block", "size": [size, size, size], "children": []}
        nodes = [root]
        splits = int(rng.integers(splits_range[0], splits_range[1] + 1))
        for _ in range(splits):
            node_idx = int(rng.integers(0, len(nodes)))
            node = nodes.pop(node_idx)
            axis = int(rng.integers(0, 2))  # 0 -> x, 1 -> z
            ratio = float(rng.uniform(0.3, 0.7))
            size_a = node["size"].copy()
            size_b = node["size"].copy()
            size_a[axis] *= ratio
            size_b[axis] *= 1.0 - ratio
            child_a = {"shape": "block", "size": size_a, "children": []}
            child_b = {"shape": "block", "size": size_b, "children": []}
            node["children"] = [child_a, child_b]
            nodes.extend([child_a, child_b])
        descriptors.append({"type": "building", "root": root})
    return descriptors


def generate_creature_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    bones_range: tuple[int, int] = (3, 5),
    metaball_count_range: tuple[int, int] = (3, 6),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic creature descriptors.

    Each descriptor contains a parameterized skeleton of ``bones`` segments and
    a set of metaballs defining the creature's implicit surface.  The output is
    a lightweight stand-in for a more sophisticated C++ implementation.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_creature")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        bone_count = int(rng.integers(bones_range[0], bones_range[1] + 1))
        skeleton = []
        for _ in range(bone_count):
            length = float(rng.uniform(0.5, 2.0))
            angle = float(rng.uniform(-45.0, 45.0))
            skeleton.append({"length": length, "angle": angle})

        metaball_count = int(
            rng.integers(metaball_count_range[0], metaball_count_range[1] + 1)
        )
        metaballs = []
        for _ in range(metaball_count):
            center = rng.random(3).tolist()
            radius = float(rng.uniform(0.1, 0.5))
            metaballs.append({"center": center, "radius": radius})

        descriptors.append(
            {"type": "creature", "skeleton": skeleton, "metaballs": metaballs}
        )
    return descriptors


def generate_chunk_props(
    registry: SeedRegistry,
    chunk_size: int,
    heightmap: np.ndarray,
    slope_map: np.ndarray | None = None,
    *,
    rock_count: int = 8,
    tree_count: int = 6,
    min_height: float = 0.2,
    max_height: float = 0.85,
    max_slope: float = 0.5,
) -> List[Dict[str, object]]:
    """Generate prop descriptors for a single chunk with terrain-aware placement.

    This function creates deterministic prop placement within a chunk boundary,
    using the heightmap and optional slope map to ensure valid positions (not
    underwater, not on steep slopes).

    Parameters
    ----------
    registry:
        SeedRegistry for this chunk (should be chunk-specific for determinism).
    chunk_size:
        Size of the chunk in world units.
    heightmap:
        2D array of terrain heights (normalized 0-1).
    slope_map:
        Optional 2D array of terrain slopes (normalized 0-1).
    rock_count:
        Number of rocks to attempt to place.
    tree_count:
        Number of trees to attempt to place.
    min_height:
        Minimum terrain height for prop placement (avoid water).
    max_height:
        Maximum terrain height for prop placement (avoid mountain peaks).
    max_slope:
        Maximum slope for prop placement (avoid cliff faces).

    Returns
    -------
    List[Dict[str, object]]
        List of prop descriptors with local positions (0 to chunk_size).
        Each descriptor contains 'type', 'position' (local x, y, z), and
        type-specific parameters.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if rock_count < 0 or tree_count < 0:
        raise ValueError("prop counts must be non-negative")

    rng = registry.get_rng("chunk_props")
    descriptors: List[Dict[str, object]] = []

    def is_valid_position(x: int, z: int) -> bool:
        """Check if position is valid for prop placement."""
        # Clamp to array bounds
        ix = min(max(x, 0), chunk_size - 1)
        iz = min(max(z, 0), chunk_size - 1)

        height = float(heightmap[iz, ix])
        if height < min_height or height > max_height:
            return False

        if slope_map is not None:
            slope = float(slope_map[iz, ix])
            if slope > max_slope:
                return False

        return True

    def get_terrain_height(x: int, z: int) -> float:
        """Get terrain height at position."""
        ix = min(max(x, 0), chunk_size - 1)
        iz = min(max(z, 0), chunk_size - 1)
        return float(heightmap[iz, ix])

    # Generate rocks
    for _ in range(rock_count):
        # Random position within chunk
        pos_x = float(rng.random() * chunk_size)
        pos_z = float(rng.random() * chunk_size)

        if is_valid_position(int(pos_x), int(pos_z)):
            terrain_y = get_terrain_height(int(pos_x), int(pos_z))
            radius = float(rng.uniform(0.3, 1.2))
            noise_seed = int(rng.integers(0, 2**31))

            descriptors.append({
                "type": "rock",
                "position": [pos_x, terrain_y, pos_z],
                "radius": radius,
                "noise_seed": noise_seed,
            })

    # Generate trees
    for _ in range(tree_count):
        pos_x = float(rng.random() * chunk_size)
        pos_z = float(rng.random() * chunk_size)

        if is_valid_position(int(pos_x), int(pos_z)):
            terrain_y = get_terrain_height(int(pos_x), int(pos_z))
            iterations = int(rng.integers(2, 5))
            angle = float(rng.uniform(15.0, 45.0))

            descriptors.append({
                "type": "tree",
                "position": [pos_x, terrain_y, pos_z],
                "axiom": "F",
                "rules": {"F": "F[+F]F[-F]F"},
                "angle": angle,
                "iterations": iterations,
            })

    return descriptors
