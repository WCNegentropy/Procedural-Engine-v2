"""Species template system for creature generation.

Each :class:`CreatureTemplate` is a frozen set of parameter constraints that
feeds into the *existing* spine, metaball, and limb pipelines so that new
creature types produce the same ``{type, body_plan, skeleton, metaballs,
limbs}`` descriptor format consumed by the C++ mesh backend.

Built-in templates cover deer, wolf, lizard, goat, humanoid, goblin, and bird
archetypes.  The ``"original"`` template replicates the current random-range
behavior for backward compatibility.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Sequence

import numpy as np

from procengine.world.props import (
    QUADRUPED_START_HEIGHT,
    METABALL_BRIDGE_RADIUS_EPSILON,
    _MAX_LIMB_PAIRS,
    _append_metaball,
    _connect_metaball_components,
    _make_limb_descriptor,
    _normalize_creature_scale,
)


# ---------------------------------------------------------------------------
# Template dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CreatureTemplate:
    """Frozen parameter set that constrains creature generation."""

    name: str
    body_plan: str  # "quadruped" or "biped"

    # Spine
    bones_range: tuple[int, int]
    spine_heading: float  # degrees – initial heading
    spine_jitter: float  # max ± deviation per bone
    bone_length_range: tuple[float, float]

    # Torso metaballs
    metaball_detail_range: tuple[int, int]
    torso_fullness: float  # 0.0–1.0, controls how "full" the body profile is
    torso_base_radius: float
    torso_peak_radius: float
    lateral_symmetry_factor: float  # multiplier on Z-offset for body width

    # Limbs
    limb_length_scale: float
    limb_radius_scale: float

    # Overall size
    target_size_range: tuple[float, float]

    # Head (torso protrusion)
    head_scale: float = 0.55  # head radius relative to front torso radius
    neck_length_scale: float = 1.2  # how far head extends from body edge

    # Gameplay defaults
    behavior: str = "wander"
    move_speed: float = 2.0
    mass: float = 30.0

    # Vision cone parameters (standardized across species, tunable per-template)
    vision_half_angle_deg: float = 60.0  # half-angle in degrees (120° total FOV)
    vision_range: float = 15.0  # maximum sight distance in world units
    turn_speed: float = 4.0  # radians per second for smooth rotation


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

CREATURE_TEMPLATES: Dict[str, CreatureTemplate] = {}


def _register(t: CreatureTemplate) -> CreatureTemplate:
    CREATURE_TEMPLATES[t.name] = t
    return t


_register(CreatureTemplate(
    name="original",
    body_plan="quadruped",  # ignored – original picks randomly
    bones_range=(3, 5),
    spine_heading=4.0,
    spine_jitter=12.0,
    bone_length_range=(0.32, 0.56),
    metaball_detail_range=(3, 6),
    torso_fullness=0.55,
    torso_base_radius=0.20,
    torso_peak_radius=0.34,
    lateral_symmetry_factor=1.0,
    limb_length_scale=1.0,
    limb_radius_scale=1.0,
    target_size_range=(0.8, 2.0),
    behavior="wander",
    move_speed=2.0,
    mass=30.0,
))

_register(CreatureTemplate(
    name="deer",
    body_plan="quadruped",
    bones_range=(6, 8),
    spine_heading=4.0,
    spine_jitter=4.0,  # very straight horizontal body
    bone_length_range=(0.35, 0.50),
    metaball_detail_range=(4, 7),
    torso_fullness=0.40,
    torso_base_radius=0.14,
    torso_peak_radius=0.22,
    lateral_symmetry_factor=0.8,
    limb_length_scale=1.4,
    limb_radius_scale=0.75,
    target_size_range=(1.2, 1.8),
    head_scale=0.45,
    neck_length_scale=1.8,
    behavior="prey",
    move_speed=3.5,
    mass=45.0,
    vision_half_angle_deg=75.0,  # wide FOV — prey animal
    vision_range=18.0,
    turn_speed=5.0,
))

_register(CreatureTemplate(
    name="wolf",
    body_plan="quadruped",
    bones_range=(4, 5),
    spine_heading=4.0,
    spine_jitter=6.0,
    bone_length_range=(0.30, 0.40),
    metaball_detail_range=(4, 6),
    torso_fullness=0.65,
    torso_base_radius=0.18,
    torso_peak_radius=0.30,
    lateral_symmetry_factor=1.0,
    limb_length_scale=1.0,
    limb_radius_scale=1.0,
    target_size_range=(0.9, 1.4),
    head_scale=0.65,
    neck_length_scale=1.3,
    behavior="predator",
    move_speed=3.0,
    mass=35.0,
    vision_half_angle_deg=55.0,  # forward-focused predator vision
    vision_range=20.0,
    turn_speed=5.0,
))

_register(CreatureTemplate(
    name="lizard",
    body_plan="quadruped",
    bones_range=(3, 4),
    spine_heading=4.0,
    spine_jitter=8.0,
    bone_length_range=(0.25, 0.35),
    metaball_detail_range=(3, 5),
    torso_fullness=0.75,
    torso_base_radius=0.20,
    torso_peak_radius=0.35,
    lateral_symmetry_factor=1.4,  # very wide body
    limb_length_scale=0.6,
    limb_radius_scale=0.9,
    target_size_range=(0.6, 1.0),
    head_scale=0.55,
    neck_length_scale=1.0,
    behavior="grazer",
    move_speed=1.5,
    mass=15.0,
    vision_half_angle_deg=80.0,  # nearly panoramic side-mounted eyes
    vision_range=10.0,
    turn_speed=3.0,
))

_register(CreatureTemplate(
    name="goat",
    body_plan="quadruped",
    bones_range=(3, 4),
    spine_heading=4.0,
    spine_jitter=6.0,
    bone_length_range=(0.30, 0.40),
    metaball_detail_range=(3, 5),
    torso_fullness=0.60,
    torso_base_radius=0.18,
    torso_peak_radius=0.28,
    lateral_symmetry_factor=1.0,
    limb_length_scale=0.8,
    limb_radius_scale=1.0,
    target_size_range=(0.8, 1.2),
    head_scale=0.55,
    neck_length_scale=1.4,
    behavior="grazer",
    move_speed=2.5,
    mass=40.0,
    vision_half_angle_deg=70.0,
    vision_range=12.0,
    turn_speed=3.5,
))

_register(CreatureTemplate(
    name="humanoid",
    body_plan="biped",
    bones_range=(5, 7),
    spine_heading=90.0,
    spine_jitter=8.0,  # tighter for upright posture
    bone_length_range=(0.28, 0.42),
    metaball_detail_range=(4, 7),
    torso_fullness=0.50,
    torso_base_radius=0.14,
    torso_peak_radius=0.26,
    lateral_symmetry_factor=1.0,
    limb_length_scale=1.0,
    limb_radius_scale=1.0,
    target_size_range=(1.0, 1.8),
    head_scale=0.60,
    neck_length_scale=1.0,
    behavior="wander",
    move_speed=1.5,
    mass=60.0,
))

_register(CreatureTemplate(
    name="goblin",
    body_plan="biped",
    bones_range=(3, 4),
    spine_heading=90.0,
    spine_jitter=12.0,
    bone_length_range=(0.24, 0.36),
    metaball_detail_range=(3, 5),
    torso_fullness=0.70,
    torso_base_radius=0.18,
    torso_peak_radius=0.30,
    lateral_symmetry_factor=1.1,
    limb_length_scale=0.85,
    limb_radius_scale=1.1,
    target_size_range=(0.6, 1.0),
    head_scale=0.65,
    neck_length_scale=0.9,
    behavior="wander",
    move_speed=2.0,
    mass=25.0,
))

_register(CreatureTemplate(
    name="bird",
    body_plan="biped",
    bones_range=(2, 3),
    spine_heading=90.0,
    spine_jitter=10.0,
    bone_length_range=(0.22, 0.34),
    metaball_detail_range=(2, 4),
    torso_fullness=0.60,
    torso_base_radius=0.16,
    torso_peak_radius=0.24,
    lateral_symmetry_factor=0.9,
    limb_length_scale=1.2,  # long legs
    limb_radius_scale=0.6,  # thin limbs
    target_size_range=(0.4, 0.8),
    head_scale=0.50,
    neck_length_scale=1.1,
    behavior="prey",
    move_speed=2.0,
    mass=5.0,
    vision_half_angle_deg=85.0,  # very wide FOV — bird lateral eyes
    vision_range=20.0,
    turn_speed=6.0,  # fast head turns
))


# ---------------------------------------------------------------------------
# Biome → species mapping
# ---------------------------------------------------------------------------
# Keys are biome IDs from procengine.world.props constants.
from procengine.world.props import (
    BIOME_FOREST,
    BIOME_JUNGLE,
    BIOME_PLAINS,
    BIOME_SAVANNA,
    BIOME_DESERT,
    BIOME_MESA,
    BIOME_MOUNTAIN,
    BIOME_TUNDRA,
    BIOME_TAIGA,
    BIOME_SWAMP,
    BIOME_BEACH,
    BIOME_SNOWY_MOUNTAIN,
)

BIOME_SPECIES: Dict[int, tuple[str, ...]] = {
    BIOME_FOREST:         ("deer", "wolf", "bird"),
    BIOME_JUNGLE:         ("lizard", "bird"),
    BIOME_PLAINS:         ("deer", "goat"),
    BIOME_SAVANNA:        ("deer", "lizard"),
    BIOME_DESERT:         ("lizard",),
    BIOME_MESA:           ("lizard", "goat"),
    BIOME_MOUNTAIN:       ("goat",),
    BIOME_TUNDRA:         ("wolf", "goat"),
    BIOME_TAIGA:          ("wolf", "deer"),
    BIOME_SWAMP:          ("lizard", "bird"),
    BIOME_BEACH:          ("bird",),
    BIOME_SNOWY_MOUNTAIN: ("goat", "wolf"),
}


# ---------------------------------------------------------------------------
# Template-driven spine generator
# ---------------------------------------------------------------------------

def _generate_templated_spine(
    rng: np.random.Generator,
    template: CreatureTemplate,
) -> tuple[list[dict[str, float]], list[np.ndarray]]:
    """Build a spine chain using template-specific constraints."""

    bone_count = int(rng.integers(template.bones_range[0], template.bones_range[1] + 1))
    heading = template.spine_heading
    jitter = template.spine_jitter
    length_range = template.bone_length_range

    if template.body_plan == "biped":
        start = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    else:
        start = np.array([0.0, QUADRUPED_START_HEIGHT, 0.0], dtype=np.float64)

    joints: list[np.ndarray] = [start]
    skeleton: list[dict[str, float]] = []

    for _ in range(bone_count):
        heading += float(rng.uniform(-jitter, jitter))
        length = float(rng.uniform(length_range[0], length_range[1]))
        direction = np.array(
            [math.cos(math.radians(heading)), math.sin(math.radians(heading)), 0.0],
            dtype=np.float64,
        )
        joints.append(joints[-1] + direction * length)
        skeleton.append({"length": length, "angle": heading})

    return skeleton, joints


# ---------------------------------------------------------------------------
# Template-driven torso metaball generator
# ---------------------------------------------------------------------------

def _templated_body_radius_profile(
    index: int,
    count: int,
    template: CreatureTemplate,
) -> float:
    """Radius profile controlled by template fullness/radius parameters."""
    if count <= 1:
        return template.torso_base_radius

    center = (count - 1) * 0.5
    distance = abs(float(index) - center) / max(center, 1.0)
    fullness = 1.0 - (1.0 - template.torso_fullness) * distance

    # Humanoid shoulder widening: top 25% of spine is wider
    if template.name == "humanoid" and count > 1:
        spine_frac = float(index) / float(count - 1)
        if spine_frac >= 0.75:
            fullness = min(fullness * 1.2, 1.0)
        elif 0.55 <= spine_frac <= 0.65:
            fullness *= 0.7  # waist narrowing

    # Wolf front-heavy bias
    if template.name == "wolf" and count > 1:
        spine_frac = float(index) / float(count - 1)
        fullness *= 0.85 + 0.3 * (1.0 - spine_frac)  # front heavier

    return template.torso_base_radius + (
        template.torso_peak_radius - template.torso_base_radius
    ) * fullness


def _generate_templated_torso(
    rng: np.random.Generator,
    joints: Sequence[np.ndarray],
    template: CreatureTemplate,
) -> list[dict[str, object]]:
    """Place torso metaballs using template-controlled shape profile."""
    metaballs: list[dict[str, object]] = []
    segment_count = max(len(joints) - 1, 1)
    detail_count = int(
        rng.integers(template.metaball_detail_range[0], template.metaball_detail_range[1] + 1)
    )
    lat_factor = template.lateral_symmetry_factor

    for index in range(segment_count):
        start = joints[index]
        end = joints[index + 1]
        midpoint = (start + end) * 0.5
        radius = _templated_body_radius_profile(index, segment_count, template)
        _append_metaball(metaballs, midpoint, radius)

        if segment_count > 1:
            fullness = radius / max(template.torso_peak_radius, 1e-6)
            if fullness > 0.72:
                lateral = radius * float(rng.uniform(0.60, 0.75)) * lat_factor
                vertical = float(rng.uniform(-0.03, 0.03))
                for side in (-1.0, 1.0):
                    side_center = midpoint + np.array([0.0, vertical, side * lateral])
                    _append_metaball(metaballs, side_center, radius * 0.55)

    # Detail fill
    if detail_count > 0:
        spine_points = np.linspace(0.1, 0.9, num=detail_count)
        for fraction in spine_points:
            position = float(fraction) * segment_count
            idx = min(int(position), segment_count - 1)
            local_t = position - float(idx)
            point = joints[idx] + (joints[idx + 1] - joints[idx]) * local_t
            radius = _templated_body_radius_profile(idx, segment_count, template) * 0.72
            point = point + np.array([
                float(rng.uniform(-0.025, 0.025)),
                float(rng.uniform(-0.025, 0.025)),
                0.0,
            ])
            _append_metaball(metaballs, point, radius)

    # Head as torso protrusion — extends from the "front" end of the spine.
    # Bipeds: head extends upward from the top joint (joints[-1]).
    # Quadrupeds: head extends forward from the front joint (joints[0]).
    if len(joints) > 1:
        if template.body_plan == "biped":
            # Head extends upward from the top of the vertical spine
            front_radius = _templated_body_radius_profile(
                segment_count - 1, segment_count, template
            )
            head_radius = front_radius * template.head_scale
            neck_offset = front_radius * template.neck_length_scale
            # Neck meatball — overlaps torso for a smooth transition
            neck_center = joints[-1] + np.array([0.0, neck_offset * 0.5, 0.0])
            _append_metaball(metaballs, neck_center, head_radius * 0.85)
            # Head meatball
            head_center = joints[-1] + np.array([0.0, neck_offset, 0.0])
            _append_metaball(metaballs, head_center, head_radius)
        else:
            # Quadruped: head extends forward from the front joint (joint[0])
            # Determine forward direction (opposite of spine direction at front)
            spine_dir = joints[1] - joints[0]
            spine_norm = float(np.linalg.norm(spine_dir))
            if spine_norm > 1e-8:
                spine_dir = spine_dir / spine_norm
            head_dir = -spine_dir  # forward = away from body interior
            head_dir[1] += 0.35  # tilt upward for natural head posture
            head_norm = float(np.linalg.norm(head_dir))
            if head_norm > 1e-8:
                head_dir = head_dir / head_norm

            front_radius = _templated_body_radius_profile(0, segment_count, template)
            head_radius = front_radius * template.head_scale
            neck_offset = front_radius * template.neck_length_scale

            # Neck meatball — bridges torso to head smoothly
            neck_center = joints[0] + head_dir * (neck_offset * 0.5)
            _append_metaball(metaballs, neck_center, head_radius * 0.85)
            # Head meatball
            head_center = joints[0] + head_dir * neck_offset
            _append_metaball(metaballs, head_center, head_radius)

    return metaballs


# ---------------------------------------------------------------------------
# Template-driven limb generator
# ---------------------------------------------------------------------------

def _generate_templated_limbs(
    rng: np.random.Generator,
    joints: Sequence[np.ndarray],
    template: CreatureTemplate,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Generate limbs with template-scaled proportions."""
    limbs: list[dict[str, object]] = []
    metaballs: list[dict[str, object]] = []
    bone_count = max(len(joints) - 1, 1)
    ls = template.limb_length_scale
    rs = template.limb_radius_scale

    if template.body_plan == "biped":
        attach_pairs: list[tuple[int, str]] = [
            (0, "arm"),
            (max(0, bone_count - 1), "leg"),
        ]
        lateral_base = 0.40
    else:
        attach_pairs = [
            (0, "foreleg"),
            (max(0, bone_count - 1), "hindleg"),
        ]
        lateral_base = 0.50

    attach_pairs = attach_pairs[:_MAX_LIMB_PAIRS]

    for attach_bone, limb_kind in attach_pairs:
        attach_joint = joints[min(attach_bone, len(joints) - 1)]

        if limb_kind == "arm":
            if template.name == "bird":
                # Tiny wing stubs
                segment_angles = (-130.0, -90.0)
                segment_lengths = (
                    float(rng.uniform(0.18, 0.26)) * ls,
                    float(rng.uniform(0.14, 0.22)) * ls,
                )
                base_radius = 0.18 * rs
            elif template.name == "humanoid":
                segment_angles = (-45.0, -90.0)
                segment_lengths = (
                    float(rng.uniform(0.34, 0.46)) * ls,
                    float(rng.uniform(0.30, 0.42)) * ls,
                )
                base_radius = 0.24 * rs
            else:
                segment_angles = (-118.0, -78.0)
                segment_lengths = (
                    float(rng.uniform(0.32, 0.44)) * ls,
                    float(rng.uniform(0.28, 0.40)) * ls,
                )
                base_radius = 0.24 * rs
        elif limb_kind == "leg":
            if template.name == "humanoid":
                # 55/45 upper/lower split
                total_leg = float(rng.uniform(0.78, 1.08)) * ls
                segment_lengths = (total_leg * 0.55, total_leg * 0.45)
                segment_angles = (-92.0, -80.0)
            elif template.name == "bird":
                segment_lengths = (
                    float(rng.uniform(0.48, 0.64)) * ls,
                    float(rng.uniform(0.40, 0.54)) * ls,
                )
                segment_angles = (-92.0, -80.0)
            else:
                segment_lengths = (
                    float(rng.uniform(0.42, 0.58)) * ls,
                    float(rng.uniform(0.36, 0.50)) * ls,
                )
                segment_angles = (-92.0, -80.0)
            base_radius = 0.28 * rs
        elif limb_kind == "hindleg":
            segment_lengths = (
                float(rng.uniform(0.40, 0.54)) * ls,
                float(rng.uniform(0.34, 0.46)) * ls,
            )
            segment_angles = (-100.0, -82.0)
            base_radius = 0.27 * rs
        else:  # foreleg
            segment_lengths = (
                float(rng.uniform(0.36, 0.50)) * ls,
                float(rng.uniform(0.30, 0.42)) * ls,
            )
            segment_angles = (-82.0, -94.0)
            base_radius = 0.26 * rs

        # Lizard splayed legs
        if template.name == "lizard" and limb_kind in ("foreleg", "hindleg"):
            segment_angles = (-60.0, -90.0)  # more horizontal splay

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
                    [
                        math.cos(math.radians(angle)),
                        math.sin(math.radians(angle)),
                        side_sign * lateral_angle,
                    ],
                    dtype=np.float64,
                )
                norm = float(np.linalg.norm(direction))
                if norm > 1e-8:
                    direction = direction / norm
                length = float(segment["length"])
                next_point = current + direction * length
                seg_radius = radius_profile[segment_index + 1]
                for frac in (0.25, 0.5, 0.75):
                    interp = current + (next_point - current) * frac
                    taper = 1.0 - 0.15 * abs(frac - 0.5)
                    _append_metaball(metaballs, interp, seg_radius * taper)
                current = next_point

            limbs.append(_make_limb_descriptor(attach_bone, side_name, segment_defs, radius_profile))

    return limbs, metaballs


# ---------------------------------------------------------------------------
# Main template-driven generator
# ---------------------------------------------------------------------------

def generate_creature_from_template(
    rng: np.random.Generator,
    template: CreatureTemplate,
) -> dict[str, object]:
    """Generate a creature descriptor using template-constrained parameters.

    Returns the **same descriptor format** as
    :func:`~procengine.world.props._generate_creature_descriptor_from_rng` so
    the C++ mesh pipeline requires no changes.
    """
    skeleton, joints = _generate_templated_spine(rng, template)
    torso_metaballs = _generate_templated_torso(rng, joints, template)
    limbs, limb_metaballs = _generate_templated_limbs(rng, joints, template)
    all_metaballs = _connect_metaball_components(torso_metaballs)

    target_size = float(rng.uniform(template.target_size_range[0], template.target_size_range[1]))
    skeleton, metaballs, limbs = _normalize_creature_scale(
        skeleton,
        all_metaballs,
        limbs,
        target_major_axis=target_size,
    )

    return {
        "type": "creature",
        "body_plan": template.body_plan,
        "creature_type": template.name,
        "skeleton": skeleton,
        "metaballs": metaballs,
        "limbs": limbs,
    }
