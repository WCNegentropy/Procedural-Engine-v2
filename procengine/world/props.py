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

import math
from typing import Dict, List, Optional, Sequence

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

QUADRUPED_START_HEIGHT = 0.6
TORSO_LATERAL_OFFSET_MIN = 0.60
TORSO_LATERAL_OFFSET_MAX = 0.75
METABALL_BRIDGE_RADIUS_EPSILON = 1e-3

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


def _sample_heightmap_bilinear(
    heightmap: np.ndarray,
    x: float,
    z: float,
    max_x: int,
    max_z: int,
) -> float:
    """Sample a heightmap at fractional coordinates with bilinear filtering.

    ``max_x`` and ``max_z`` describe the chunk-local sampling extent for prop
    placement. The underlying heightmap may be larger (for example
    ``chunk_size + 1`` overlap vertices), which allows interpolation to use the
    shared edge vertex near chunk boundaries without letting prop placement
    sample beyond the chunk's intended footprint.
    """

    sample_max_x = min(max_x, heightmap.shape[1] - 1)
    sample_max_z = min(max_z, heightmap.shape[0] - 1)
    fx = min(max(float(x), 0.0), float(sample_max_x))
    fz = min(max(float(z), 0.0), float(sample_max_z))

    x0 = int(np.floor(fx))
    z0 = int(np.floor(fz))
    x1 = min(x0 + 1, sample_max_x)
    z1 = min(z0 + 1, sample_max_z)

    tx = fx - float(x0)
    tz = fz - float(z0)

    h00 = float(heightmap[z0, x0])
    h10 = float(heightmap[z0, x1])
    h01 = float(heightmap[z1, x0])
    h11 = float(heightmap[z1, x1])

    top = h00 + (h10 - h00) * tx
    bottom = h01 + (h11 - h01) * tx
    return top + (bottom - top) * tz


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
    body_plans: tuple[str, ...] = ("quadruped", "biped"),
) -> List[Dict[str, object]]:
    """Return ``count`` deterministic creature descriptors.

    Each descriptor contains a skeleton-guided body plan, a coherent set of
    connected metaballs, and limb metadata for future animation/runtime use.
    """

    if count < 0:
        raise ValueError("count must be non-negative")
    if not body_plans:
        raise ValueError("body_plans must not be empty")

    rng = registry.get_rng("props_creature")
    descriptors: List[Dict[str, object]] = []
    for _ in range(count):
        descriptors.append(
            _generate_creature_descriptor_from_rng(
                rng,
                bones_range=bones_range,
                metaball_count_range=metaball_count_range,
                body_plans=body_plans,
            )
        )
    return descriptors


def _generate_spine_skeleton(
    rng: np.random.Generator, bone_count: int, body_plan: str
) -> tuple[list[dict[str, float]], list[np.ndarray]]:
    """Build a deterministic spine chain.

    Returns a tuple of ``(skeleton, joints)`` where ``skeleton`` is a list of
    ``{"length", "angle"}`` bone descriptors and ``joints`` contains the 3D
    joint positions traced by that chain.
    """
    if body_plan == "biped":
        heading = 90.0
        angle_jitter = 16.0
        length_range = (0.28, 0.48)
        start = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    else:
        heading = 4.0
        angle_jitter = 12.0
        length_range = (0.32, 0.56)
        start = np.array([0.0, QUADRUPED_START_HEIGHT, 0.0], dtype=np.float64)

    joints = [start]
    skeleton: list[dict[str, float]] = []
    for _ in range(bone_count):
        heading += float(rng.uniform(-angle_jitter, angle_jitter))
        length = float(rng.uniform(*length_range))
        direction = np.array(
            [math.cos(math.radians(heading)), math.sin(math.radians(heading)), 0.0],
            dtype=np.float64,
        )
        joints.append(joints[-1] + direction * length)
        skeleton.append({"length": length, "angle": heading})

    return skeleton, joints


def _body_radius_profile(index: int, count: int, body_plan: str) -> float:
    """Return a torso radius profile that peaks near the spine center.

    The profile narrows toward the head/tail ends and uses a slightly larger
    peak for quadrupeds than bipeds so both body plans stay readable after
    normalization.
    """
    if count <= 1:
        return 0.2 if body_plan == "biped" else 0.24
    center = (count - 1) * 0.5
    distance = abs(float(index) - center) / max(center, 1.0)
    fullness = 1.0 - 0.55 * distance
    base = 0.16 if body_plan == "biped" else 0.2
    peak = 0.28 if body_plan == "biped" else 0.34
    return base + (peak - base) * fullness


def _append_metaball(
    metaballs: list[dict[str, object]], center: np.ndarray, radius: float
) -> None:
    metaballs.append({"center": center.astype(float).tolist(), "radius": float(radius)})


def _place_spine_metaballs(
    rng: np.random.Generator,
    joints: Sequence[np.ndarray],
    body_plan: str,
    detail_count: int,
) -> list[dict[str, object]]:
    """Place torso metaballs along the spine with symmetric width."""
    metaballs: list[dict[str, object]] = []
    segment_count = max(len(joints) - 1, 1)

    for index in range(segment_count):
        start = joints[index]
        end = joints[index + 1]
        midpoint = (start + end) * 0.5
        radius = _body_radius_profile(index, segment_count, body_plan)
        _append_metaball(metaballs, midpoint, radius)

        if segment_count > 1:
            fullness = radius / (
                0.28 if body_plan == "biped" else 0.34
            )
            if fullness > 0.72:
                lateral = radius * float(
                    rng.uniform(TORSO_LATERAL_OFFSET_MIN, TORSO_LATERAL_OFFSET_MAX)
                )
                vertical = float(rng.uniform(-0.03, 0.03))
                for side in (-1.0, 1.0):
                    side_center = midpoint + np.array([0.0, vertical, side * lateral])
                    _append_metaball(metaballs, side_center, radius * 0.55)

    if detail_count > 0:
        spine_points = np.linspace(0.1, 0.9, num=detail_count)
        for fraction in spine_points:
            position = float(fraction) * segment_count
            index = min(int(position), segment_count - 1)
            local_t = position - float(index)
            point = joints[index] + (joints[index + 1] - joints[index]) * local_t
            radius = _body_radius_profile(index, segment_count, body_plan) * 0.72
            point = point + np.array(
                [
                    float(rng.uniform(-0.025, 0.025)),
                    float(rng.uniform(-0.025, 0.025)),
                    0.0,
                ]
            )
            _append_metaball(metaballs, point, radius)

    return metaballs


def _make_limb_descriptor(
    attach_bone: int,
    side: str,
    segments: Sequence[dict[str, float]],
    radii: Sequence[float],
) -> dict[str, object]:
    return {
        "attach_bone": attach_bone,
        "side": side,
        "segments": [{"length": float(s["length"]), "angle": float(s["angle"])} for s in segments],
        "metaballs": [
            {
                "offset": float(index / max(len(radii) - 1, 1)),
                "radius": float(radius),
            }
            for index, radius in enumerate(radii)
        ],
    }


def _generate_limbs(
    rng: np.random.Generator,
    joints: Sequence[np.ndarray],
    body_plan: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Generate symmetric limb metadata and connected limb metaballs.

    Each attach pair produces two limbs (left + right) for bilateral symmetry.
    The maximum number of attach pairs is capped at 2 so that no creature
    exceeds 4 limbs total.
    """
    _MAX_LIMB_PAIRS = 2  # 2 pairs × 2 sides = 4 limbs max
    limbs: list[dict[str, object]] = []
    metaballs: list[dict[str, object]] = []
    bone_count = max(len(joints) - 1, 1)

    if body_plan == "biped":
        attach_pairs = [
            (max(0, min(1, bone_count - 1)), "arm"),
            (max(0, bone_count - 1), "leg"),
        ]
        lateral_base = 0.40
    else:
        attach_pairs = [
            (max(0, min(1, bone_count - 1)), "foreleg"),
            (max(0, bone_count - 2), "hindleg"),
        ]
        lateral_base = 0.50

    attach_pairs = attach_pairs[:_MAX_LIMB_PAIRS]

    for attach_bone, limb_kind in attach_pairs:
        attach_joint = joints[min(attach_bone, len(joints) - 1)]
        if limb_kind == "arm":
            segment_angles = (-118.0, -78.0)
            segment_lengths = (
                float(rng.uniform(0.32, 0.44)),
                float(rng.uniform(0.28, 0.40)),
            )
            base_radius = 0.24
        elif limb_kind == "leg":
            segment_angles = (-92.0, -80.0)
            segment_lengths = (
                float(rng.uniform(0.42, 0.58)),
                float(rng.uniform(0.36, 0.50)),
            )
            base_radius = 0.28
        elif limb_kind == "hindleg":
            segment_angles = (-100.0, -82.0)
            segment_lengths = (
                float(rng.uniform(0.40, 0.54)),
                float(rng.uniform(0.34, 0.46)),
            )
            base_radius = 0.27
        else:
            segment_angles = (-82.0, -94.0)
            segment_lengths = (
                float(rng.uniform(0.36, 0.50)),
                float(rng.uniform(0.30, 0.42)),
            )
            base_radius = 0.26

        segment_defs = [
            {"length": segment_lengths[0], "angle": segment_angles[0]},
            {"length": segment_lengths[1], "angle": segment_angles[1]},
        ]
        radius_profile = [base_radius, base_radius * 0.9, base_radius * 0.72]

        for side_name, side_sign in (("left", -1.0), ("right", 1.0)):
            lateral = lateral_base + float(rng.uniform(-0.015, 0.015))
            current = attach_joint + np.array([0.0, -0.03, side_sign * lateral])
            _append_metaball(metaballs, current, radius_profile[0])

            for segment_index, segment in enumerate(segment_defs):
                angle = float(segment["angle"]) + float(rng.uniform(-8.0, 8.0))
                if segment_index == 0:
                    lateral_angle = float(rng.uniform(0.50, 0.70))
                else:
                    lateral_angle = float(rng.uniform(0.25, 0.40))
                direction = np.array(
                    [math.cos(math.radians(angle)), math.sin(math.radians(angle)), side_sign * lateral_angle],
                    dtype=np.float64,
                )
                norm = np.linalg.norm(direction)
                if norm > 1e-8:
                    direction = direction / norm
                length = float(segment["length"])
                next_point = current + direction * length
                seg_radius = radius_profile[segment_index + 1]
                # Place 3 metaballs along the segment for continuous limb shape
                for frac in (0.25, 0.5, 0.75):
                    interp = current + (next_point - current) * frac
                    taper = 1.0 - 0.15 * abs(frac - 0.5)
                    _append_metaball(metaballs, interp, seg_radius * taper)
                current = next_point

            limbs.append(_make_limb_descriptor(attach_bone, side_name, segment_defs, radius_profile))

    return limbs, metaballs


def _normalize_creature_scale(
    skeleton: list[dict[str, float]],
    metaballs: list[dict[str, object]],
    limbs: list[dict[str, object]],
    target_major_axis: float,
) -> tuple[list[dict[str, float]], list[dict[str, object]], list[dict[str, object]]]:
    """Center and scale creature geometry into a stable world-space range."""
    centers = np.array([ball["center"] for ball in metaballs], dtype=np.float64)
    radii = np.array([float(ball["radius"]) for ball in metaballs], dtype=np.float64)
    mins = centers - radii[:, None]
    maxs = centers + radii[:, None]

    min_bound = mins.min(axis=0)
    max_bound = maxs.max(axis=0)
    span = np.maximum(max_bound - min_bound, 1e-6)
    scale = float(target_major_axis / float(span.max()))
    offset = np.array(
        [
            -0.5 * (min_bound[0] + max_bound[0]),
            -min_bound[1],
            -0.5 * (min_bound[2] + max_bound[2]),
        ],
        dtype=np.float64,
    )

    normalized_metaballs = []
    for ball in metaballs:
        center = (np.array(ball["center"], dtype=np.float64) + offset) * scale
        normalized_metaballs.append(
            {"center": center.astype(float).tolist(), "radius": float(ball["radius"]) * scale}
        )

    normalized_skeleton = [
        {"length": float(bone["length"]) * scale, "angle": float(bone["angle"])}
        for bone in skeleton
    ]
    normalized_limbs = []
    for limb in limbs:
        normalized_limb = {
            "attach_bone": int(limb["attach_bone"]),
            "side": str(limb["side"]),
            "segments": [
                {"length": float(segment["length"]) * scale, "angle": float(segment["angle"])}
                for segment in limb["segments"]
            ],
            "metaballs": [
                {"offset": float(ball["offset"]), "radius": float(ball["radius"]) * scale}
                for ball in limb["metaballs"]
            ],
        }
        normalized_limbs.append(normalized_limb)

    return normalized_skeleton, normalized_metaballs, normalized_limbs


def _connect_metaball_components(metaballs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Bridge disconnected metaball clusters with greedy linking balls.

    This mutates ``metaballs`` in place by appending the smallest bridge ball
    found between disconnected components, then returns the same list for
    convenience.
    """

    def build_components() -> list[set[int]]:
        components: list[set[int]] = []
        visited: set[int] = set()
        centers = [np.array(ball["center"], dtype=np.float64) for ball in metaballs]
        radii = [float(ball["radius"]) for ball in metaballs]

        for start in range(len(metaballs)):
            if start in visited:
                continue
            frontier = [start]
            component = {start}
            visited.add(start)
            while frontier:
                index = frontier.pop()
                for other in range(len(metaballs)):
                    if other in visited:
                        continue
                    distance = float(np.linalg.norm(centers[index] - centers[other]))
                    if distance <= radii[index] + radii[other] + 1e-6:
                        visited.add(other)
                        component.add(other)
                        frontier.append(other)
            components.append(component)
        return components

    components = build_components()
    while len(components) > 1:
        centers = [np.array(ball["center"], dtype=np.float64) for ball in metaballs]
        radii = [float(ball["radius"]) for ball in metaballs]
        best_pair: tuple[int, int] | None = None
        best_distance = float("inf")

        for left_index in components[0]:
            for component in components[1:]:
                for right_index in component:
                    distance = float(np.linalg.norm(centers[left_index] - centers[right_index]))
                    gap = distance - (radii[left_index] + radii[right_index])
                    if gap < best_distance:
                        best_distance = gap
                        best_pair = (left_index, right_index)

        if best_pair is None:
            break

        left_index, right_index = best_pair
        midpoint = (centers[left_index] + centers[right_index]) * 0.5
        half_distance = float(np.linalg.norm(centers[left_index] - centers[right_index])) * 0.5
        bridge_radius = max(
            half_distance - radii[left_index] + METABALL_BRIDGE_RADIUS_EPSILON,
            half_distance - radii[right_index] + METABALL_BRIDGE_RADIUS_EPSILON,
            min(radii[left_index], radii[right_index]) * 0.8,
        )
        metaballs.append({"center": midpoint.astype(float).tolist(), "radius": float(bridge_radius)})
        components = build_components()

    return metaballs


def _generate_creature_descriptor_from_rng(
    rng: np.random.Generator,
    *,
    bones_range: tuple[int, int],
    metaball_count_range: tuple[int, int],
    body_plans: Sequence[str],
) -> dict[str, object]:
    """Generate one coherent creature descriptor from an existing RNG."""
    body_plan = str(body_plans[int(rng.integers(0, len(body_plans)))])
    bone_count = int(rng.integers(bones_range[0], bones_range[1] + 1))
    skeleton, joints = _generate_spine_skeleton(rng, bone_count, body_plan)
    detail_count = int(rng.integers(metaball_count_range[0], metaball_count_range[1] + 1))
    torso_metaballs = _place_spine_metaballs(rng, joints, body_plan, detail_count)
    limbs, limb_metaballs = _generate_limbs(rng, joints, body_plan)
    all_metaballs = _connect_metaball_components(torso_metaballs)
    skeleton, metaballs, limbs = _normalize_creature_scale(
        skeleton,
        all_metaballs,
        limbs,
        target_major_axis=float(rng.uniform(0.8, 2.0)),
    )

    return {
        "type": "creature",
        "body_plan": body_plan,
        "skeleton": skeleton,
        "metaballs": metaballs,
        "limbs": limbs,
    }


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

    def get_terrain_height(x: float, z: float) -> float:
        """Get terrain height at position."""
        return _sample_heightmap_bilinear(heightmap, x, z, chunk_size, chunk_size)

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
        terrain_y = get_terrain_height(pos_x, pos_z)

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
        terrain_y = get_terrain_height(pos_x, pos_z)

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
        terrain_y = get_terrain_height(pos_x, pos_z)

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

        creature = _generate_creature_descriptor_from_rng(
            rng,
            bones_range=(3, 5),
            metaball_count_range=(3, 6),
            body_plans=("quadruped", "biped"),
        )
        creature["position"] = [pos_x, terrain_y, pos_z]
        descriptors.append(creature)

    return descriptors
