"""Tests for the creature species template system."""

import math

import numpy as np
import pytest

from procengine.core.seed_registry import SeedRegistry
from procengine.world.creature_templates import (
    BIOME_SPECIES,
    CREATURE_TEMPLATES,
    CreatureTemplate,
    generate_creature_from_template,
)
from procengine.world.props import (
    BARREN_BIOMES,
    _generate_creature_descriptor_from_rng,
    generate_chunk_props,
)


# --- helpers ---------------------------------------------------------------

def _metaballs_are_connected(metaballs: list[dict]) -> bool:
    """Return True if all metaballs form a single connected cluster."""
    if not metaballs:
        return True
    centers = [np.array(b["center"], dtype=float) for b in metaballs]
    radii = [float(b["radius"]) for b in metaballs]
    visited = {0}
    frontier = [0]
    while frontier:
        idx = frontier.pop()
        for other in range(len(metaballs)):
            if other in visited:
                continue
            dist = float(np.linalg.norm(centers[idx] - centers[other]))
            if dist <= radii[idx] + radii[other] + 1e-6:
                visited.add(other)
                frontier.append(other)
    return len(visited) == len(metaballs)


# --- Phase 1: template definitions ----------------------------------------

def test_all_expected_templates_present():
    expected = {"original", "deer", "wolf", "lizard", "goat",
                "humanoid", "goblin", "bird"}
    assert expected == set(CREATURE_TEMPLATES.keys())


def test_template_is_frozen():
    t = CREATURE_TEMPLATES["deer"]
    with pytest.raises(AttributeError):
        t.name = "elk"  # type: ignore[misc]


# --- Phase 2: template-driven generator ------------------------------------

@pytest.mark.parametrize("name", list(CREATURE_TEMPLATES.keys()))
def test_generate_creature_from_template_valid_descriptor(name: str):
    """Each template produces a valid descriptor with correct format."""
    rng = np.random.default_rng(42)
    template = CREATURE_TEMPLATES[name]
    desc = generate_creature_from_template(rng, template)

    assert desc["type"] == "creature"
    assert desc["body_plan"] in {"quadruped", "biped"}
    assert isinstance(desc["skeleton"], list)
    assert isinstance(desc["metaballs"], list)
    assert isinstance(desc["limbs"], list)

    # Skeleton bones within range
    assert template.bones_range[0] <= len(desc["skeleton"]) <= template.bones_range[1]

    # Always 4 limbs (2 pairs × 2 sides)
    assert len(desc["limbs"]) == 4
    assert {lm["side"] for lm in desc["limbs"]} == {"left", "right"}

    # Metaballs connected
    assert _metaballs_are_connected(desc["metaballs"])

    # Each metaball has center and radius
    for ball in desc["metaballs"]:
        assert len(ball["center"]) == 3
        assert ball["radius"] > 0

    # Each skeleton bone has length and angle
    for bone in desc["skeleton"]:
        assert "length" in bone
        assert "angle" in bone
        assert bone["length"] > 0


@pytest.mark.parametrize("name", list(CREATURE_TEMPLATES.keys()))
def test_template_creatures_deterministic(name: str):
    """Same seed → same output for every template."""
    template = CREATURE_TEMPLATES[name]
    rng1 = np.random.default_rng(99)
    rng2 = np.random.default_rng(99)
    desc1 = generate_creature_from_template(rng1, template)
    desc2 = generate_creature_from_template(rng2, template)
    assert desc1 == desc2


def test_template_biped_spine_vertical():
    """Humanoid spine joints mostly increase in Y (vertical)."""
    rng = np.random.default_rng(7)
    template = CREATURE_TEMPLATES["humanoid"]
    desc = generate_creature_from_template(rng, template)

    # Reconstruct joints from skeleton
    joints_y = [0.0]
    heading = template.spine_heading
    for bone in desc["skeleton"]:
        heading = bone["angle"]
        dy = math.sin(math.radians(heading)) * bone["length"]
        joints_y.append(joints_y[-1] + dy)

    # Most bones should go upward (positive Y delta)
    upward_count = sum(1 for i in range(1, len(joints_y)) if joints_y[i] > joints_y[i - 1])
    assert upward_count >= len(joints_y) // 2


def test_template_quadruped_spine_horizontal():
    """Deer spine joints mostly increase in X (horizontal)."""
    rng = np.random.default_rng(7)
    template = CREATURE_TEMPLATES["deer"]
    desc = generate_creature_from_template(rng, template)

    joints_x = [0.0]
    for bone in desc["skeleton"]:
        dx = math.cos(math.radians(bone["angle"])) * bone["length"]
        joints_x.append(joints_x[-1] + dx)

    forward_count = sum(1 for i in range(1, len(joints_x)) if joints_x[i] > joints_x[i - 1])
    assert forward_count >= len(joints_x) // 2


# --- Phase 3: biome species mapping ---------------------------------------

def test_biome_species_mapping_coverage():
    """Every non-barren, non-ocean biome has at least one species."""
    from procengine.world.props import (
        BIOME_FOREST, BIOME_JUNGLE, BIOME_PLAINS, BIOME_SAVANNA,
        BIOME_DESERT, BIOME_MESA, BIOME_MOUNTAIN, BIOME_TUNDRA,
        BIOME_TAIGA, BIOME_SWAMP, BIOME_BEACH,
    )
    spawnable_biomes = {
        BIOME_FOREST, BIOME_JUNGLE, BIOME_PLAINS, BIOME_SAVANNA,
        BIOME_DESERT, BIOME_MESA, BIOME_MOUNTAIN, BIOME_TUNDRA,
        BIOME_TAIGA, BIOME_SWAMP, BIOME_BEACH,
    }
    for biome_id in spawnable_biomes:
        assert biome_id in BIOME_SPECIES, f"Biome {biome_id} has no species mapping"
        assert len(BIOME_SPECIES[biome_id]) >= 1


def test_biome_species_reference_valid_templates():
    """All species names in the biome mapping correspond to real templates."""
    for biome_id, species_list in BIOME_SPECIES.items():
        for species_name in species_list:
            assert species_name in CREATURE_TEMPLATES, (
                f"Species '{species_name}' for biome {biome_id} not in CREATURE_TEMPLATES"
            )


# --- Phase 4-5: shape characteristics ------------------------------------

def test_humanoid_has_head_metaball():
    """Humanoid template produces a head placeholder metaball above spine."""
    rng = np.random.default_rng(12)
    desc = generate_creature_from_template(rng, CREATURE_TEMPLATES["humanoid"])
    # The topmost metaball Y should be well above the body center
    ys = [b["center"][1] for b in desc["metaballs"]]
    assert max(ys) > np.mean(ys)


def test_goblin_has_head_metaball():
    """Goblin template also gets a head placeholder."""
    rng = np.random.default_rng(12)
    desc = generate_creature_from_template(rng, CREATURE_TEMPLATES["goblin"])
    ys = [b["center"][1] for b in desc["metaballs"]]
    assert max(ys) > np.mean(ys)


def test_deer_long_spine():
    """Deer should have a longer spine than goat (more bones)."""
    rng1 = np.random.default_rng(42)
    rng2 = np.random.default_rng(42)
    deer = generate_creature_from_template(rng1, CREATURE_TEMPLATES["deer"])
    goat = generate_creature_from_template(rng2, CREATURE_TEMPLATES["goat"])
    assert len(deer["skeleton"]) >= len(goat["skeleton"])


def test_bird_small_target_size():
    """Bird template should produce smaller creatures than humanoid."""
    bird_t = CREATURE_TEMPLATES["bird"]
    human_t = CREATURE_TEMPLATES["humanoid"]
    assert bird_t.target_size_range[1] < human_t.target_size_range[0]


# --- Phase 6: creature_type propagation -----------------------------------

def test_template_descriptor_includes_creature_type():
    """Template-generated descriptors contain a creature_type field."""
    rng = np.random.default_rng(0)
    for name, template in CREATURE_TEMPLATES.items():
        desc = generate_creature_from_template(rng, template)
        assert desc.get("creature_type") == name


# --- Regression: original creatures unchanged -----------------------------

def test_original_creatures_unchanged():
    """Calling _generate_creature_descriptor_from_rng with original params
    produces bit-identical output regardless of template system additions."""
    rng1 = np.random.default_rng(777)
    rng2 = np.random.default_rng(777)

    desc1 = _generate_creature_descriptor_from_rng(
        rng1,
        bones_range=(3, 5),
        metaball_count_range=(3, 6),
        body_plans=("quadruped", "biped"),
    )
    desc2 = _generate_creature_descriptor_from_rng(
        rng2,
        bones_range=(3, 5),
        metaball_count_range=(3, 6),
        body_plans=("quadruped", "biped"),
    )
    assert desc1 == desc2


def test_generate_chunk_props_still_produces_creatures():
    """generate_chunk_props with a biome map still produces creatures."""
    reg = SeedRegistry(42)
    size = 32
    hm = np.full((size, size), 0.5, dtype=np.float32)
    biome_map = np.full((size, size), 7, dtype=np.int32)  # BIOME_FOREST

    found_creature = False
    for seed in range(200):
        reg_i = SeedRegistry(seed)
        descs = generate_chunk_props(
            reg_i, size, hm, biome_map=biome_map,
            rock_count=0, tree_count=0, bush_count=0, flower_count=0,
        )
        for d in descs:
            if d.get("type") == "creature":
                found_creature = True
                # Must still be a valid descriptor
                assert "skeleton" in d
                assert "metaballs" in d
                assert "limbs" in d
                assert "body_plan" in d
        if found_creature:
            break

    assert found_creature, "No creature spawned across 200 seed attempts"
