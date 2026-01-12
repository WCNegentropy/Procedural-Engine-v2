"""Integration tests for chunk and world generation helpers."""

import numpy as np

from seed_registry import SeedRegistry
from world import generate_chunk, generate_world


def test_generate_chunk_deterministic():
    registry_a = SeedRegistry(123)
    registry_b = SeedRegistry(123)
    chunk_a = generate_chunk(registry_a)
    chunk_b = generate_chunk(registry_b)
    assert np.array_equal(chunk_a["height"], chunk_b["height"])
    assert np.array_equal(chunk_a["biome"], chunk_b["biome"])
    assert np.array_equal(chunk_a["river"], chunk_b["river"])
    assert chunk_a["rocks"] == chunk_b["rocks"]
    assert chunk_a["trees"] == chunk_b["trees"]
    assert chunk_a["material"] == chunk_b["material"]
    assert chunk_a["buildings"] == chunk_b["buildings"]
    assert chunk_a["creatures"] == chunk_b["creatures"]


def test_generate_chunk_slope_optional():
    reg = SeedRegistry(1)
    chunk_basic = generate_chunk(reg)
    assert "slope" not in chunk_basic
    reg2 = SeedRegistry(1)
    chunk_slope = generate_chunk(reg2, include_slope=True)
    assert "slope" in chunk_slope
    assert chunk_slope["slope"].shape == chunk_slope["height"].shape


def test_generate_chunk_shapes():
    registry = SeedRegistry(5)
    chunk = generate_chunk(
        registry,
        terrain_size=32,
        rock_count=2,
        tree_count=1,
        building_count=1,
        creature_count=1,
    )
    assert chunk["height"].shape == (32, 32)
    assert chunk["biome"].shape == (32, 32)
    assert chunk["river"].shape == (32, 32)
    assert len(chunk["rocks"]) == 2
    assert len(chunk["trees"]) == 1
    assert len(chunk["buildings"]) == 1
    assert len(chunk["creatures"]) == 1


def test_generate_chunk_macro_and_erosion_options():
    reg_a = SeedRegistry(42)
    reg_b = SeedRegistry(42)
    chunk_a = generate_chunk(
        reg_a,
        terrain_macro_points=5,
        terrain_erosion_iters=10,
    )
    chunk_b = generate_chunk(
        reg_b,
        terrain_macro_points=5,
        terrain_erosion_iters=10,
    )
    assert np.array_equal(chunk_a["height"], chunk_b["height"])

    reg_c = SeedRegistry(42)
    no_erosion = generate_chunk(
        reg_c,
        terrain_macro_points=5,
        terrain_erosion_iters=0,
    )
    assert not np.array_equal(chunk_a["height"], no_erosion["height"])


def test_generate_world_grid_deterministic():
    reg_a = SeedRegistry(9)
    reg_b = SeedRegistry(9)
    world_a = generate_world(reg_a, 2, 2, include_slope=True)
    world_b = generate_world(reg_b, 2, 2, include_slope=True)
    assert world_a.keys() == world_b.keys()
    for key in world_a:
        a = world_a[key]
        b = world_b[key]
        assert np.array_equal(a["height"], b["height"])
        assert np.array_equal(a["slope"], b["slope"])
        assert a["rocks"] == b["rocks"]


def test_generate_world_size():
    registry = SeedRegistry(0)
    world = generate_world(registry, 3, 1)
    assert len(world) == 3
