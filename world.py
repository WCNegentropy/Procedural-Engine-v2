from __future__ import annotations

"""High-level world chunk assembly utilities."""

from typing import Any, Dict, Tuple

from materials import generate_material_graph
from props import (
    generate_building_descriptors,
    generate_creature_descriptors,
    generate_rock_descriptors,
    generate_tree_descriptors,
)
from seed_registry import SeedRegistry
from terrain import generate_terrain_maps

__all__ = ["generate_chunk", "generate_world"]


def generate_chunk(
    registry: SeedRegistry,
    *,
    terrain_size: int = 64,
    terrain_octaves: int = 6,
    terrain_macro_points: int = 8,
    terrain_erosion_iters: int = 0,
    rock_count: int = 5,
    tree_count: int = 3,
    building_count: int = 0,
    creature_count: int = 0,
    include_slope: bool = False,
) -> Dict[str, Any]:
    """Return deterministic descriptors for a single world chunk.

    Parameters
    ----------
    registry:
        Shared :class:`SeedRegistry` controlling randomness.
    terrain_size:
        Width and height of the square terrain maps to generate.
    terrain_octaves:
        Number of FBM octaves used when synthesizing the heightmap.
    terrain_macro_points:
        Number of Voronoi sites used for macro plates. ``0`` disables the
        macro layer.
    terrain_erosion_iters:
        Iterations of the hydraulic erosion simulation to apply. ``0``
        disables erosion.
    rock_count:
        Number of rock descriptors to synthesize.
    tree_count:
        Number of tree descriptors to synthesize.
    building_count:
        Number of building descriptors to synthesize.
    creature_count:
        Number of creature descriptors to synthesize.
    include_slope:
        If ``True`` include a normalized slope map in the returned descriptor.
    """
    maps = generate_terrain_maps(
        registry,
        size=terrain_size,
        octaves=terrain_octaves,
        macro_points=terrain_macro_points,
        erosion_iters=terrain_erosion_iters,
        return_slope=include_slope,
    )
    if include_slope:
        height, biome, river, slope = maps
    else:
        height, biome, river = maps
    rocks = generate_rock_descriptors(registry, rock_count)
    trees = generate_tree_descriptors(registry, tree_count)
    buildings = generate_building_descriptors(registry, building_count)
    creatures = generate_creature_descriptors(registry, creature_count)
    material = generate_material_graph(registry)
    chunk = {
        "height": height,
        "biome": biome,
        "river": river,
        "rocks": rocks,
        "trees": trees,
        "buildings": buildings,
        "creatures": creatures,
        "material": material,
    }
    if include_slope:
        chunk["slope"] = slope
    return chunk


def generate_world(
    registry: SeedRegistry,
    width: int,
    height: int,
    *,
    terrain_size: int = 64,
    terrain_octaves: int = 6,
    terrain_macro_points: int = 8,
    terrain_erosion_iters: int = 0,
    rock_count: int = 5,
    tree_count: int = 3,
    building_count: int = 0,
    creature_count: int = 0,
    include_slope: bool = False,
) -> Dict[Tuple[int, int], Dict[str, Any]]:
    """Return deterministic chunk descriptors for a grid of size ``width``×``height``.

    Each chunk receives its own spawned :class:`SeedRegistry` to avoid
    cross-contamination of RNG streams.  The return value maps ``(x, y)``
    coordinates to the corresponding chunk descriptor produced by
    :func:`generate_chunk`.  When ``include_slope`` is true each chunk descriptor
    also contains a normalized slope map.
    """

    world: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for y in range(height):
        for x in range(width):
            chunk_registry = registry.spawn(f"chunk_{x}_{y}")
            world[(x, y)] = generate_chunk(
                chunk_registry,
                terrain_size=terrain_size,
                terrain_octaves=terrain_octaves,
                terrain_macro_points=terrain_macro_points,
                terrain_erosion_iters=terrain_erosion_iters,
                rock_count=rock_count,
                tree_count=tree_count,
                building_count=building_count,
                creature_count=creature_count,
                include_slope=include_slope,
            )
    return world
