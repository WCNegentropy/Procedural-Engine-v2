"""Tests for deterministic prop descriptor generators."""

import numpy as np

from procengine.world.props import (
    generate_building_descriptors,
    generate_creature_descriptors,
    generate_rock_descriptors,
    generate_tree_descriptors,
    generate_chunk_props,
)
from procengine.core.seed_registry import SeedRegistry


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
        assert prop["type"] in ("rock", "tree")
        assert "position" in prop
        pos = prop["position"]
        assert len(pos) == 3
        # Position should be within chunk bounds
        assert 0 <= pos[0] <= chunk_size
        assert 0 <= pos[2] <= chunk_size


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

    # Check rock and tree types exist
    rock_count = sum(1 for p in props if p["type"] == "rock")
    tree_count = sum(1 for p in props if p["type"] == "tree")
    assert rock_count > 0
    assert tree_count > 0


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
