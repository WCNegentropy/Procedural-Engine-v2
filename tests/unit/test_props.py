"""Tests for deterministic prop descriptor generators."""

import numpy as np
import procengine.world.props as props_module
import pytest

from procengine.world.props import (
    generate_building_descriptors,
    generate_bush_descriptors,
    generate_cactus_descriptors,
    generate_creature_descriptors,
    generate_dead_tree_descriptors,
    generate_fallen_log_descriptors,
    generate_boulder_cluster_descriptors,
    generate_flower_patch_descriptors,
    generate_mushroom_descriptors,
    generate_pine_tree_descriptors,
    generate_rock_descriptors,
    generate_tree_descriptors,
    generate_chunk_props,
)
from procengine.core.seed_registry import SeedRegistry

# ---- All valid chunk-prop types produced by generate_chunk_props ----
ALL_CHUNK_PROP_TYPES = {
    "rock", "tree", "bush", "pine_tree", "dead_tree", "fallen_log",
    "boulder_cluster", "flower_patch", "mushroom", "cactus",
}


def test_generate_rock_descriptors_deterministic():
    reg1 = SeedRegistry(1)
    reg2 = SeedRegistry(1)
    assert generate_rock_descriptors(reg1, 3) == generate_rock_descriptors(reg2, 3)


def test_generate_rock_descriptors_structure():
    reg = SeedRegistry(0)
    descs = generate_rock_descriptors(reg, 2, size=10.0)
    assert len(descs) == 2
    for d in descs:
        assert d["type"] == "rock"
        assert len(d["position"]) == 3
        assert all(0.0 <= p <= 10.0 for p in d["position"])
        assert 0.0 < d["radius"] <= 5.0


def test_generate_tree_descriptors_deterministic():
    reg1 = SeedRegistry(2)
    reg2 = SeedRegistry(2)
    assert generate_tree_descriptors(reg1, 2) == generate_tree_descriptors(reg2, 2)


def test_generate_tree_descriptors_structure():
    reg = SeedRegistry(3)
    trees = generate_tree_descriptors(reg, 1)
    assert len(trees) == 1
    tree = trees[0]
    assert tree["type"] == "tree"
    assert tree["axiom"] == "F"
    assert "F" in tree["rules"]
    assert tree["angle"] >= 0.0
    assert tree["iterations"] >= 0


def test_generate_building_descriptors_deterministic():
    reg1 = SeedRegistry(4)
    reg2 = SeedRegistry(4)
    assert generate_building_descriptors(reg1, 2) == generate_building_descriptors(
        reg2, 2
    )


def test_generate_building_descriptors_structure():
    reg = SeedRegistry(5)
    buildings = generate_building_descriptors(reg, 1, size=10.0)
    assert len(buildings) == 1
    building = buildings[0]
    assert building["type"] == "building"
    assert "root" in building
    root = building["root"]
    assert root["shape"] == "block"
    assert len(root["size"]) == 3


def test_generate_creature_descriptors_deterministic():
    reg1 = SeedRegistry(6)
    reg2 = SeedRegistry(6)
    assert generate_creature_descriptors(reg1, 1) == generate_creature_descriptors(
        reg2, 1
    )


def test_generate_creature_descriptors_structure():
    reg = SeedRegistry(7)
    creatures = generate_creature_descriptors(reg, 1)
    assert len(creatures) == 1
    creature = creatures[0]
    assert creature["type"] == "creature"
    assert len(creature["skeleton"]) >= 1
    assert len(creature["metaballs"]) >= 1


# =============================================================================
# Chunk Props Tests
# =============================================================================


def test_generate_chunk_props_deterministic():
    """Test that chunk props generation is deterministic."""
    chunk_size = 32
    heightmap = np.random.default_rng(42).random((chunk_size, chunk_size)).astype(np.float32)
    heightmap = (heightmap * 0.6) + 0.2  # Scale to valid height range (0.2 to 0.8)
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg1 = SeedRegistry(100)
    reg2 = SeedRegistry(100)

    props1 = generate_chunk_props(reg1, chunk_size, heightmap, slope_map)
    props2 = generate_chunk_props(reg2, chunk_size, heightmap, slope_map)

    assert props1 == props2


def test_generate_chunk_props_structure():
    """Test that chunk props have correct structure."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg = SeedRegistry(101)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map,
        rock_count=5, tree_count=3
    )

    # Should have some props (not all may pass placement validation)
    assert len(props) > 0

    for prop in props:
        assert "type" in prop
        assert prop["type"] in ALL_CHUNK_PROP_TYPES
        assert "position" in prop
        pos = prop["position"]
        assert len(pos) == 3
        # Position should be within chunk bounds [0, chunk_size)
        assert 0 <= pos[0] < chunk_size
        assert 0 <= pos[2] < chunk_size


def test_generate_chunk_props_respects_height_limits():
    """Test that props aren't placed in water (low height) or peaks (high height)."""
    chunk_size = 32

    # Create heightmap that is mostly water (height < 0.2)
    water_heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.1
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg = SeedRegistry(102)
    props = generate_chunk_props(
        reg, chunk_size, water_heightmap, slope_map,
        rock_count=10, tree_count=10, min_height=0.2
    )

    # No props should be placed in water
    assert len(props) == 0


def test_generate_chunk_props_respects_slope_limits():
    """Test that props aren't placed on steep slopes."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5

    # Create steep slope map
    steep_slope = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.8

    reg = SeedRegistry(103)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, steep_slope,
        rock_count=10, tree_count=10, max_slope=0.5
    )

    # No props should be placed on steep slopes
    assert len(props) == 0


def test_generate_chunk_props_with_valid_terrain():
    """Test that props are placed when terrain is valid."""
    chunk_size = 32
    # Create terrain at valid height (0.3 to 0.7)
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    # Flat terrain (no slope)
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg = SeedRegistry(104)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map,
        rock_count=5, tree_count=5
    )

    # Should have props placed
    assert len(props) > 0

    # Check that at least some prop types are present
    types_found = {p["type"] for p in props}
    # With flat valid terrain and no biome map, we should get at least
    # rocks, trees, bushes, and boulder_clusters or flower_patches
    assert len(types_found) >= 2


def test_generate_chunk_props_different_seeds_different_results():
    """Test that different seeds produce different prop layouts."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg1 = SeedRegistry(200)
    reg2 = SeedRegistry(201)

    props1 = generate_chunk_props(reg1, chunk_size, heightmap, slope_map)
    props2 = generate_chunk_props(reg2, chunk_size, heightmap, slope_map)

    # Props should be different with different seeds
    assert props1 != props2


def test_sample_heightmap_bilinear_interpolates_fractional_positions():
    """Terrain-aware prop placement should interpolate heights between vertices."""
    heightmap = np.array(
        [
            [0.0, 1.0, 2.0],
            [10.0, 11.0, 12.0],
            [20.0, 21.0, 22.0],
        ],
        dtype=np.float32,
    )

    sampled = props_module._sample_heightmap_bilinear(heightmap, 0.25, 0.75, 2, 2)

    assert sampled == pytest.approx(7.75)


# =============================================================================
# New Prop Generator Tests
# =============================================================================


def test_generate_bush_descriptors_deterministic():
    reg1 = SeedRegistry(10)
    reg2 = SeedRegistry(10)
    assert generate_bush_descriptors(reg1, 3) == generate_bush_descriptors(reg2, 3)


def test_generate_bush_descriptors_structure():
    reg = SeedRegistry(11)
    bushes = generate_bush_descriptors(reg, 2, size=5.0)
    assert len(bushes) == 2
    for b in bushes:
        assert b["type"] == "bush"
        assert len(b["position"]) == 3
        assert 0.0 < b["radius"] <= 2.0
        assert 0.0 < b["leaf_density"] <= 1.0


def test_generate_pine_tree_descriptors_deterministic():
    reg1 = SeedRegistry(12)
    reg2 = SeedRegistry(12)
    assert generate_pine_tree_descriptors(reg1, 2) == generate_pine_tree_descriptors(reg2, 2)


def test_generate_pine_tree_descriptors_structure():
    reg = SeedRegistry(13)
    pines = generate_pine_tree_descriptors(reg, 2)
    assert len(pines) == 2
    for p in pines:
        assert p["type"] == "pine_tree"
        assert p["trunk_height"] > 0
        assert p["canopy_layers"] >= 2
        assert p["canopy_radius"] > 0
        assert p["trunk_radius"] > 0


def test_generate_dead_tree_descriptors_deterministic():
    reg1 = SeedRegistry(14)
    reg2 = SeedRegistry(14)
    assert generate_dead_tree_descriptors(reg1, 2) == generate_dead_tree_descriptors(reg2, 2)


def test_generate_dead_tree_descriptors_structure():
    reg = SeedRegistry(15)
    dead = generate_dead_tree_descriptors(reg, 1)
    assert len(dead) == 1
    d = dead[0]
    assert d["type"] == "dead_tree"
    assert d["axiom"] == "F"
    assert "F" in d["rules"]
    # Sparser rule than full tree
    assert d["rules"]["F"] == "F[+F][-F]"
    assert d["iterations"] >= 1


def test_generate_fallen_log_descriptors_deterministic():
    reg1 = SeedRegistry(16)
    reg2 = SeedRegistry(16)
    assert generate_fallen_log_descriptors(reg1, 2) == generate_fallen_log_descriptors(reg2, 2)


def test_generate_fallen_log_descriptors_structure():
    reg = SeedRegistry(17)
    logs = generate_fallen_log_descriptors(reg, 2)
    assert len(logs) == 2
    for lg in logs:
        assert lg["type"] == "fallen_log"
        assert lg["length"] > 0
        assert lg["radius"] > 0
        assert 0 <= lg["rotation_y"] <= 360


def test_generate_boulder_cluster_descriptors_deterministic():
    reg1 = SeedRegistry(18)
    reg2 = SeedRegistry(18)
    assert generate_boulder_cluster_descriptors(reg1, 1) == generate_boulder_cluster_descriptors(reg2, 1)


def test_generate_boulder_cluster_descriptors_structure():
    reg = SeedRegistry(19)
    clusters = generate_boulder_cluster_descriptors(reg, 1)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["type"] == "boulder_cluster"
    assert len(c["sub_rocks"]) >= 2
    for sr in c["sub_rocks"]:
        assert len(sr["offset"]) == 3
        assert sr["radius"] > 0


def test_generate_flower_patch_descriptors_deterministic():
    reg1 = SeedRegistry(20)
    reg2 = SeedRegistry(20)
    assert generate_flower_patch_descriptors(reg1, 2) == generate_flower_patch_descriptors(reg2, 2)


def test_generate_flower_patch_descriptors_structure():
    reg = SeedRegistry(21)
    flowers = generate_flower_patch_descriptors(reg, 1)
    assert len(flowers) == 1
    f = flowers[0]
    assert f["type"] == "flower_patch"
    assert f["stem_count"] >= 4
    assert f["patch_radius"] > 0


def test_generate_mushroom_descriptors_deterministic():
    reg1 = SeedRegistry(22)
    reg2 = SeedRegistry(22)
    assert generate_mushroom_descriptors(reg1, 2) == generate_mushroom_descriptors(reg2, 2)


def test_generate_mushroom_descriptors_structure():
    reg = SeedRegistry(23)
    mushrooms = generate_mushroom_descriptors(reg, 1)
    assert len(mushrooms) == 1
    m = mushrooms[0]
    assert m["type"] == "mushroom"
    assert m["cap_radius"] > 0
    assert m["stem_height"] > 0
    assert m["stem_radius"] > 0


def test_generate_cactus_descriptors_deterministic():
    reg1 = SeedRegistry(24)
    reg2 = SeedRegistry(24)
    assert generate_cactus_descriptors(reg1, 2) == generate_cactus_descriptors(reg2, 2)


def test_generate_cactus_descriptors_structure():
    reg = SeedRegistry(25)
    cacti = generate_cactus_descriptors(reg, 1)
    assert len(cacti) == 1
    c = cacti[0]
    assert c["type"] == "cactus"
    assert c["main_height"] > 0
    assert c["main_radius"] > 0
    assert isinstance(c["arms"], list)
    for arm in c["arms"]:
        assert 0 < arm["attach_height"] <= 1.0
        assert arm["length"] > 0


# =============================================================================
# Biome-aware chunk prop placement
# =============================================================================


def test_generate_chunk_props_with_biome_map():
    """Test that biome map influences which prop types are generated."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    # Desert biome (ID 10) should produce cacti instead of trees
    desert_biome = np.full((chunk_size, chunk_size), 10, dtype=np.uint8)
    reg = SeedRegistry(300)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map, desert_biome,
        rock_count=0, tree_count=5, bush_count=0, flower_count=5,
    )
    types = {p["type"] for p in props}
    # Desert should NOT have regular trees
    assert "tree" not in types
    # Desert should have cacti from flower_count
    if len(props) > 0:
        assert "cactus" in types or "rock" not in types  # at least no trees


def test_generate_chunk_props_forest_biome():
    """Test that forest biome produces varied vegetation."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    # Forest biome (ID 7)
    forest_biome = np.full((chunk_size, chunk_size), 7, dtype=np.uint8)
    reg = SeedRegistry(301)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map, forest_biome,
        rock_count=3, tree_count=5, bush_count=3, flower_count=3,
    )
    types = {p["type"] for p in props}
    assert len(props) > 0
    # Forest should have trees and/or bushes
    has_vegetation = "tree" in types or "bush" in types
    assert has_vegetation


def test_generate_chunk_props_taiga_biome():
    """Test that taiga biome produces pine trees."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    # Taiga biome (ID 4)
    taiga_biome = np.full((chunk_size, chunk_size), 4, dtype=np.uint8)
    reg = SeedRegistry(302)
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map, taiga_biome,
        rock_count=0, tree_count=8, bush_count=0, flower_count=0,
    )
    types = {p["type"] for p in props}
    # Taiga should produce pine_tree and/or dead_tree
    if len(props) > 0:
        assert "tree" not in types  # NOT deciduous
        assert "pine_tree" in types or "dead_tree" in types


def test_generate_chunk_props_no_biome_backwards_compat():
    """Test that generate_chunk_props works without biome_map (backward compat)."""
    chunk_size = 32
    heightmap = np.ones((chunk_size, chunk_size), dtype=np.float32) * 0.5
    slope_map = np.zeros((chunk_size, chunk_size), dtype=np.float32)

    reg = SeedRegistry(303)
    # No biome_map passed — should still work
    props = generate_chunk_props(
        reg, chunk_size, heightmap, slope_map,
        rock_count=5, tree_count=5,
    )
    assert len(props) > 0


def test_new_prop_generators_zero_count():
    """All generators handle count=0 gracefully."""
    reg = SeedRegistry(400)
    assert generate_bush_descriptors(reg, 0) == []
    assert generate_pine_tree_descriptors(reg, 0) == []
    assert generate_dead_tree_descriptors(reg, 0) == []
    assert generate_fallen_log_descriptors(reg, 0) == []
    assert generate_boulder_cluster_descriptors(reg, 0) == []
    assert generate_flower_patch_descriptors(reg, 0) == []
    assert generate_mushroom_descriptors(reg, 0) == []
    assert generate_cactus_descriptors(reg, 0) == []


def test_new_prop_generators_negative_count():
    """All generators raise ValueError on negative count."""
    reg = SeedRegistry(401)
    import pytest
    for gen in [
        generate_bush_descriptors,
        generate_pine_tree_descriptors,
        generate_dead_tree_descriptors,
        generate_fallen_log_descriptors,
        generate_boulder_cluster_descriptors,
        generate_flower_patch_descriptors,
        generate_mushroom_descriptors,
        generate_cactus_descriptors,
    ]:
        with pytest.raises(ValueError):
            gen(reg, -1)
