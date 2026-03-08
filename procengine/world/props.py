"""Procedural prop descriptor generation utilities.

This module implements deterministic descriptor generation for simple props
such as rocks, trees, bushes, buildings, and creatures based on
 :class:`~seed_registry.SeedRegistry`.  The descriptors are stand-ins for
more complex definitions used by the C++ runtime.

Prop Types
----------
- **rock** — Noise-displaced sphere; radius varies per biome.
- **boulder_cluster** — Group of 2-5 tightly-placed rocks sharing a seed.
- **tree** — L-system skeleton with varied rules per biome variant.
- **pine_tree** — Conifer tree (cone canopy on cylinder trunk).
- **dead_tree** — Leafless branching skeleton (shorter, sparser L-system).
- **fallen_log** — Horizontal trunk segment (cylinder on its side).
- **bush** — Low-height sphere with foliage noise and leaf color.
- **flower_patch** — Cluster of small vertical stems (flat placement).
- **mushroom** — Cap-on-stem toadstool shape.
- **cactus** — Branching columnar form (desert-only).
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from procengine.core.seed_registry import SeedRegistry

# ---- Biome ID constants (mirrors procengine.world.terrain) ----
BIOME_DEEP_OCEAN = 0
BIOME_OCEAN = 1
BIOME_FROZEN_OCEAN = 2
BIOME_TUNDRA = 3
BIOME_TAIGA = 4
BIOME_SNOWY_MOUNTAIN = 5
BIOME_PLAINS = 6
BIOME_FOREST = 7
BIOME_MOUNTAIN = 8
BIOME_SWAMP = 9
BIOME_DESERT = 10
BIOME_SAVANNA = 11
BIOME_MESA = 12
BIOME_JUNGLE = 13
BIOME_BEACH = 14
BIOME_GLACIER = 15

# ---- Biome groupings for prop placement rules ----
FOREST_BIOMES = {BIOME_FOREST, BIOME_TAIGA, BIOME_JUNGLE, BIOME_SWAMP}
DRY_BIOMES = {BIOME_DESERT, BIOME_MESA, BIOME_SAVANNA}
COLD_BIOMES = {BIOME_TUNDRA, BIOME_TAIGA, BIOME_SNOWY_MOUNTAIN, BIOME_GLACIER,
               BIOME_FROZEN_OCEAN}
WET_BIOMES = {BIOME_SWAMP, BIOME_JUNGLE}
BARREN_BIOMES = {BIOME_DEEP_OCEAN, BIOME_OCEAN, BIOME_FROZEN_OCEAN, BIOME_GLACIER}

__all__ = [
    "generate_rock_descriptors",
    "generate_tree_descriptors",
    "generate_bush_descriptors",
    "generate_pine_tree_descriptors",
    "generate_dead_tree_descriptors",
    "generate_fallen_log_descriptors",
    "generate_boulder_cluster_descriptors",
    "generate_flower_patch_descriptors",
    "generate_mushroom_descriptors",
    "generate_cactus_descriptors",
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
    # FIX: Reduced range from (2, 4) to (2, 3)
    # 3 iterations provides plenty of detail without exponential explosion
    iterations_range: tuple[int, int] = (2, 3),
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


# =========================================================================
# New prop generators — bushes, pine trees, dead trees, logs, clusters, etc.
# =========================================================================


def generate_bush_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic bush descriptors.

    Each bush is a low, wide noise-displaced sphere with a foliage color
    seed. The radius stays small (0.4–1.0) to keep them visually distinct
    from rocks.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_bush")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        position = rng.random(3) * size
        radius = float(rng.uniform(0.4, 1.0))
        noise_seed = int(rng.integers(0, 2**31))
        # Leaf density controls how full the foliage looks (0.5–1.0)
        leaf_density = float(rng.uniform(0.5, 1.0))
        descriptors.append({
            "type": "bush",
            "position": position.tolist(),
            "radius": radius,
            "noise_seed": noise_seed,
            "leaf_density": leaf_density,
        })
    return descriptors


def generate_pine_tree_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    trunk_height_range: tuple[float, float] = (2.0, 5.0),
    canopy_layers_range: tuple[int, int] = (2, 5),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic pine/conifer tree descriptors.

    Pine trees use a stacked-cone canopy model rather than L-systems.
    Each descriptor encodes a trunk height and a number of cone layers
    that taper toward the top.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_pine_tree")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        trunk_height = float(rng.uniform(*trunk_height_range))
        canopy_layers = int(rng.integers(canopy_layers_range[0],
                                         canopy_layers_range[1] + 1))
        # Base radius of the widest canopy layer
        canopy_radius = float(rng.uniform(0.8, 1.8))
        trunk_radius = float(rng.uniform(0.1, 0.25))
        descriptors.append({
            "type": "pine_tree",
            "trunk_height": trunk_height,
            "trunk_radius": trunk_radius,
            "canopy_layers": canopy_layers,
            "canopy_radius": canopy_radius,
        })
    return descriptors


def generate_dead_tree_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    iterations_range: tuple[int, int] = (1, 2),
    angle_range: tuple[float, float] = (20.0, 55.0),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic dead-tree descriptors.

    Dead trees reuse the L-system skeleton but with fewer iterations and
    a sparser rule set, producing leafless branching silhouettes.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_dead_tree")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        iterations = int(rng.integers(iterations_range[0],
                                       iterations_range[1] + 1))
        angle = float(rng.uniform(*angle_range))
        # Sparser rule: fewer branches than full trees
        descriptors.append({
            "type": "dead_tree",
            "axiom": "F",
            "rules": {"F": "F[+F][-F]"},
            "angle": angle,
            "iterations": iterations,
        })
    return descriptors


def generate_fallen_log_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic fallen-log descriptors.

    A fallen log is a horizontal cylinder lying on the terrain with a
    randomized length and rotation angle around Y.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_fallen_log")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        position = rng.random(3) * size
        length = float(rng.uniform(1.5, 4.0))
        log_radius = float(rng.uniform(0.15, 0.35))
        rotation_y = float(rng.uniform(0.0, 360.0))
        descriptors.append({
            "type": "fallen_log",
            "position": position.tolist(),
            "length": length,
            "radius": log_radius,
            "rotation_y": rotation_y,
        })
    return descriptors


def generate_boulder_cluster_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic boulder-cluster descriptors.

    Each cluster places 2-5 rocks close together sharing a single noise
    seed family. Individual sub-rock offsets and radii are encoded.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_boulder_cluster")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        center = rng.random(3) * size
        sub_count = int(rng.integers(2, 6))
        base_seed = int(rng.integers(0, 2**31))
        sub_rocks: List[Dict[str, object]] = []
        for k in range(sub_count):
            offset = (rng.random(3) * 1.2 - 0.6).tolist()
            radius = float(rng.uniform(0.3, 0.9))
            sub_rocks.append({
                "offset": offset,
                "radius": radius,
                "noise_seed": (base_seed + k) % (2**31),
            })
        descriptors.append({
            "type": "boulder_cluster",
            "position": center.tolist(),
            "sub_rocks": sub_rocks,
        })
    return descriptors


def generate_flower_patch_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic flower-patch descriptors.

    Each patch is a small cluster of simple stem+petal shapes scattered in
    a circle. The descriptor stores a stem count and colour seed.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_flower_patch")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        position = rng.random(3) * size
        stem_count = int(rng.integers(4, 12))
        patch_radius = float(rng.uniform(0.3, 0.8))
        color_seed = int(rng.integers(0, 2**31))
        descriptors.append({
            "type": "flower_patch",
            "position": position.tolist(),
            "stem_count": stem_count,
            "patch_radius": patch_radius,
            "color_seed": color_seed,
        })
    return descriptors


def generate_mushroom_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic mushroom descriptors.

    Each mushroom has a stem (thin cylinder) and a cap (flattened
    hemisphere).  Cap radius and stem height are randomized.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_mushroom")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        position = rng.random(3) * size
        cap_radius = float(rng.uniform(0.15, 0.5))
        stem_height = float(rng.uniform(0.2, 0.6))
        stem_radius = float(rng.uniform(0.04, 0.1))
        descriptors.append({
            "type": "mushroom",
            "position": position.tolist(),
            "cap_radius": cap_radius,
            "stem_height": stem_height,
            "stem_radius": stem_radius,
        })
    return descriptors


def generate_cactus_descriptors(
    registry: SeedRegistry,
    count: int,
    *,
    size: float = 1.0,
    arm_count_range: tuple[int, int] = (0, 3),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic cactus descriptors.

    Each cactus is a columnar cylinder with 0-3 lateral arms.  Arms are
    encoded as offsets and heights to be synthesized in C++.
    """
    if count < 0:
        raise ValueError("count must be non-negative")

    rng = registry.get_rng("props_cactus")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        position = rng.random(3) * size
        main_height = float(rng.uniform(1.5, 4.0))
        main_radius = float(rng.uniform(0.12, 0.25))
        arm_count = int(rng.integers(arm_count_range[0],
                                      arm_count_range[1] + 1))
        arms: List[Dict[str, float]] = []
        for _ in range(arm_count):
            # Height ratio along main column where arm attaches
            attach_height = float(rng.uniform(0.3, 0.8))
            arm_length = float(rng.uniform(0.4, 1.2))
            arm_angle = float(rng.uniform(0.0, 360.0))
            arms.append({
                "attach_height": attach_height,
                "length": arm_length,
                "angle": arm_angle,
            })
        descriptors.append({
            "type": "cactus",
            "position": position.tolist(),
            "main_height": main_height,
            "main_radius": main_radius,
            "arms": arms,
        })
    return descriptors


def generate_chunk_props(
    registry: SeedRegistry,
    chunk_size: int,
    heightmap: np.ndarray,
    slope_map: np.ndarray | None = None,
    biome_map: np.ndarray | None = None,
    *,
    rock_count: int = 8,
    tree_count: int = 6,
    bush_count: int = 5,
    flower_count: int = 4,
    min_height: float = 0.2,
    max_height: float = 0.85,
    max_slope: float = 0.5,
) -> List[Dict[str, object]]:
    """Generate prop descriptors for a single chunk with terrain-aware placement.

    This function creates deterministic prop placement within a chunk boundary,
    using the heightmap, optional slope map, and optional biome map to ensure
    valid positions and biome-appropriate prop selection.

    When a *biome_map* is provided, prop types are selected per-biome:

    - **Forest / Jungle**: more trees, bushes, mushrooms, fallen logs
    - **Taiga / Cold**: pine trees replace deciduous, dead trees appear
    - **Desert / Mesa**: cacti replace trees; fewer bushes
    - **Savanna**: scattered trees, more rocks
    - **Swamp**: dead trees, mushrooms, flower patches
    - **Plains / Beach**: flowers, bushes, scattered rocks
    - **Mountain**: boulder clusters, sparse dead trees

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
    biome_map:
        Optional 2D array of biome IDs (uint8). When provided, enables
        biome-specific prop selection.
    rock_count:
        Number of rocks to attempt to place.
    tree_count:
        Number of trees to attempt to place.
    bush_count:
        Number of bushes to attempt to place.
    flower_count:
        Number of flower/mushroom/extra props to attempt to place.
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
    if rock_count < 0 or tree_count < 0 or bush_count < 0 or flower_count < 0:
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

    def get_biome(x: int, z: int) -> int:
        """Get biome ID at position, or -1 if no biome map."""
        if biome_map is None:
            return -1
        ix = min(max(x, 0), chunk_size - 1)
        iz = min(max(z, 0), chunk_size - 1)
        return int(biome_map[iz, ix])

    def _random_pos() -> tuple[float, float]:
        """Random position within chunk bounds."""
        px = float(rng.uniform(0.0, float(chunk_size) - 0.001))
        pz = float(rng.uniform(0.0, float(chunk_size) - 0.001))
        return px, pz

    # -----------------------------------------------------------------
    # Rock placement
    # -----------------------------------------------------------------
    for _ in range(rock_count):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # Skip rocks in dense forest/jungle (they hide under canopy so
        # reduce density) — keep ~40 % chance
        if biome in FOREST_BIOMES and rng.random() > 0.4:
            continue

        radius = float(rng.uniform(0.3, 1.2))
        noise_seed = int(rng.integers(0, 2**31))

        descriptors.append({
            "type": "rock",
            "position": [pos_x, terrain_y, pos_z],
            "radius": radius,
            "noise_seed": noise_seed,
        })

    # -----------------------------------------------------------------
    # Boulder clusters (mountains, mesa, tundra)
    # -----------------------------------------------------------------
    boulder_attempts = 3
    for _ in range(boulder_attempts):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # Boulder clusters prefer rocky biomes
        if biome != -1 and biome not in {BIOME_MOUNTAIN, BIOME_MESA,
                                          BIOME_TUNDRA, BIOME_SNOWY_MOUNTAIN,
                                          BIOME_SAVANNA}:
            # 20 % chance in non-rocky biomes
            if rng.random() > 0.2:
                continue

        sub_count = int(rng.integers(2, 5))
        base_seed = int(rng.integers(0, 2**31))
        sub_rocks: List[Dict[str, object]] = []
        for k in range(sub_count):
            offset = (rng.random(3) * 1.2 - 0.6).tolist()
            sub_radius = float(rng.uniform(0.3, 0.9))
            sub_rocks.append({
                "offset": offset,
                "radius": sub_radius,
                "noise_seed": (base_seed + k) % (2**31),
            })

        descriptors.append({
            "type": "boulder_cluster",
            "position": [pos_x, terrain_y, pos_z],
            "sub_rocks": sub_rocks,
        })

    # -----------------------------------------------------------------
    # Tree placement (biome-aware type selection)
    # -----------------------------------------------------------------
    for _ in range(tree_count):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # No trees in desert/mesa — cacti handle that biome
        if biome in {BIOME_DESERT, BIOME_MESA}:
            continue

        # Pick tree variant based on biome
        if biome in {BIOME_TAIGA, BIOME_SNOWY_MOUNTAIN}:
            # Conifer / pine tree
            trunk_height = float(rng.uniform(2.0, 5.0))
            canopy_layers = int(rng.integers(2, 6))
            canopy_radius = float(rng.uniform(0.8, 1.8))
            trunk_radius = float(rng.uniform(0.1, 0.25))
            descriptors.append({
                "type": "pine_tree",
                "position": [pos_x, terrain_y, pos_z],
                "trunk_height": trunk_height,
                "trunk_radius": trunk_radius,
                "canopy_layers": canopy_layers,
                "canopy_radius": canopy_radius,
            })
        elif biome == BIOME_SWAMP:
            # Swamps get a mix of dead trees and normal trees
            if rng.random() < 0.5:
                iterations = int(rng.integers(1, 3))
                angle = float(rng.uniform(20.0, 55.0))
                descriptors.append({
                    "type": "dead_tree",
                    "position": [pos_x, terrain_y, pos_z],
                    "axiom": "F",
                    "rules": {"F": "F[+F][-F]"},
                    "angle": angle,
                    "iterations": iterations,
                })
            else:
                iterations = int(rng.integers(2, 4))
                angle = float(rng.uniform(15.0, 45.0))
                descriptors.append({
                    "type": "tree",
                    "position": [pos_x, terrain_y, pos_z],
                    "axiom": "F",
                    "rules": {"F": "F[+F]F[-F]F"},
                    "angle": angle,
                    "iterations": iterations,
                })
        elif biome == BIOME_TUNDRA:
            # Tundra: sparse dead trees only
            if rng.random() < 0.3:
                iterations = int(rng.integers(1, 2))
                angle = float(rng.uniform(25.0, 50.0))
                descriptors.append({
                    "type": "dead_tree",
                    "position": [pos_x, terrain_y, pos_z],
                    "axiom": "F",
                    "rules": {"F": "F[+F][-F]"},
                    "angle": angle,
                    "iterations": iterations,
                })
        elif biome == BIOME_SAVANNA:
            # Savanna: wide-angle, sparse trees
            iterations = int(rng.integers(2, 3))
            angle = float(rng.uniform(35.0, 60.0))
            descriptors.append({
                "type": "tree",
                "position": [pos_x, terrain_y, pos_z],
                "axiom": "F",
                "rules": {"F": "F[+F]F[-F]F"},
                "angle": angle,
                "iterations": iterations,
            })
        else:
            # Default deciduous tree (forest, jungle, plains, beach, etc.)
            iterations = int(rng.integers(2, 4))
            angle = float(rng.uniform(15.0, 45.0))
            descriptors.append({
                "type": "tree",
                "position": [pos_x, terrain_y, pos_z],
                "axiom": "F",
                "rules": {"F": "F[+F]F[-F]F"},
                "angle": angle,
                "iterations": iterations,
            })

    # -----------------------------------------------------------------
    # Fallen logs (forest, swamp, taiga)
    # -----------------------------------------------------------------
    log_attempts = 3
    for _ in range(log_attempts):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # Fallen logs in forested or swamp biomes
        if biome != -1 and biome not in FOREST_BIOMES:
            if rng.random() > 0.1:
                continue

        length = float(rng.uniform(1.5, 4.0))
        log_radius = float(rng.uniform(0.15, 0.35))
        rotation_y = float(rng.uniform(0.0, 360.0))

        descriptors.append({
            "type": "fallen_log",
            "position": [pos_x, terrain_y, pos_z],
            "length": length,
            "radius": log_radius,
            "rotation_y": rotation_y,
        })

    # -----------------------------------------------------------------
    # Bush placement
    # -----------------------------------------------------------------
    for _ in range(bush_count):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # No bushes in desert/mesa/glacier
        if biome in {BIOME_DESERT, BIOME_MESA, BIOME_GLACIER}:
            continue

        radius = float(rng.uniform(0.4, 1.0))
        noise_seed = int(rng.integers(0, 2**31))
        leaf_density = float(rng.uniform(0.5, 1.0))

        descriptors.append({
            "type": "bush",
            "position": [pos_x, terrain_y, pos_z],
            "radius": radius,
            "noise_seed": noise_seed,
            "leaf_density": leaf_density,
        })

    # -----------------------------------------------------------------
    # Flower patches, mushrooms, cacti (biome-dependent extras)
    # -----------------------------------------------------------------
    for _ in range(flower_count):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        if biome in {BIOME_DESERT, BIOME_MESA}:
            # Desert → cactus
            main_height = float(rng.uniform(1.5, 4.0))
            main_radius = float(rng.uniform(0.12, 0.25))
            arm_count = int(rng.integers(0, 4))
            arms: List[Dict[str, float]] = []
            for _ in range(arm_count):
                arms.append({
                    "attach_height": float(rng.uniform(0.3, 0.8)),
                    "length": float(rng.uniform(0.4, 1.2)),
                    "angle": float(rng.uniform(0.0, 360.0)),
                })
            descriptors.append({
                "type": "cactus",
                "position": [pos_x, terrain_y, pos_z],
                "main_height": main_height,
                "main_radius": main_radius,
                "arms": arms,
            })
        elif biome in WET_BIOMES:
            # Swamp/jungle → mushrooms
            cap_radius = float(rng.uniform(0.15, 0.5))
            stem_height = float(rng.uniform(0.2, 0.6))
            stem_radius = float(rng.uniform(0.04, 0.1))
            descriptors.append({
                "type": "mushroom",
                "position": [pos_x, terrain_y, pos_z],
                "cap_radius": cap_radius,
                "stem_height": stem_height,
                "stem_radius": stem_radius,
            })
        elif biome in {BIOME_GLACIER, BIOME_FROZEN_OCEAN, BIOME_DEEP_OCEAN,
                       BIOME_OCEAN}:
            # No vegetation on water/ice
            continue
        else:
            # Flower patches for everything else (plains, forest, savanna, etc.)
            stem_count = int(rng.integers(4, 12))
            patch_radius = float(rng.uniform(0.3, 0.8))
            color_seed = int(rng.integers(0, 2**31))
            descriptors.append({
                "type": "flower_patch",
                "position": [pos_x, terrain_y, pos_z],
                "stem_count": stem_count,
                "patch_radius": patch_radius,
                "color_seed": color_seed,
            })

    # -----------------------------------------------------------------
    # Creature spawning (rare, biome-dependent)
    # -----------------------------------------------------------------
    creature_attempts = 2
    for _ in range(creature_attempts):
        pos_x, pos_z = _random_pos()
        if not is_valid_position(int(pos_x), int(pos_z)):
            continue
        biome = get_biome(int(pos_x), int(pos_z))
        terrain_y = get_terrain_height(int(pos_x), int(pos_z))

        # Creatures don't spawn in water/ice biomes
        if biome in BARREN_BIOMES:
            continue
        # Low spawn chance to keep creatures rare
        if rng.random() > 0.15:
            continue

        bone_count = int(rng.integers(3, 6))
        skeleton = []
        for _ in range(bone_count):
            skeleton.append({
                "length": float(rng.uniform(0.5, 2.0)),
                "angle": float(rng.uniform(-45.0, 45.0)),
            })
        metaball_count = int(rng.integers(3, 7))
        metaballs = []
        for _ in range(metaball_count):
            metaballs.append({
                "center": rng.random(3).tolist(),
                "radius": float(rng.uniform(0.1, 0.5)),
            })
        descriptors.append({
            "type": "creature",
            "position": [pos_x, terrain_y, pos_z],
            "skeleton": skeleton,
            "metaballs": metaballs,
        })

    return descriptors
