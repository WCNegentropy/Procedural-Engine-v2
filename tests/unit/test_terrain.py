"""Tests covering deterministic terrain map generation."""

import numpy as np

from seed_registry import SeedRegistry
from terrain import generate_terrain_maps


def test_generate_terrain_maps_deterministic():
    reg1 = SeedRegistry(123)
    reg2 = SeedRegistry(123)
    h1, b1, r1 = generate_terrain_maps(reg1, size=16)
    h2, b2, r2 = generate_terrain_maps(reg2, size=16)
    assert np.allclose(h1, h2)
    assert np.array_equal(b1, b2)
    assert np.array_equal(r1, r2)


def test_generate_terrain_maps_range_and_dtype():
    reg = SeedRegistry(0)
    height, biome, river = generate_terrain_maps(reg, size=8)
    assert height.shape == (8, 8)
    assert biome.shape == (8, 8)
    assert river.shape == (8, 8)
    assert height.dtype == np.float32
    assert biome.dtype == np.uint8
    assert river.dtype == np.uint8
    assert 0.0 <= float(height.min()) <= 1.0
    assert 0.0 <= float(height.max()) <= 1.0


def test_macro_plates_and_biome_lut():
    reg1 = SeedRegistry(42)
    reg2 = SeedRegistry(42)
    h1, b1, r1 = generate_terrain_maps(reg1, size=32, macro_points=5)
    h2, b2, r2 = generate_terrain_maps(reg2, size=32, macro_points=5)
    assert np.allclose(h1, h2)
    assert np.array_equal(b1, b2)
    assert np.array_equal(r1, r2)
    # Ensure biome LUT introduces variety beyond water
    assert np.unique(b1).size > 1


def test_hydraulic_erosion_changes_heightmap_deterministically():
    reg1 = SeedRegistry(7)
    h1, _, _ = generate_terrain_maps(reg1, size=16, erosion_iters=20)
    reg2 = SeedRegistry(7)
    h2, _, _ = generate_terrain_maps(reg2, size=16, erosion_iters=20)
    assert np.allclose(h1, h2)

    reg3 = SeedRegistry(7)
    h_no, _, _ = generate_terrain_maps(reg3, size=16, erosion_iters=0)
    # Erosion should meaningfully modify the heightmap
    assert not np.allclose(h1, h_no)


def test_generate_terrain_maps_slope():
    reg_a = SeedRegistry(99)
    h_a, b_a, r_a, s_a = generate_terrain_maps(reg_a, size=16, return_slope=True)
    reg_b = SeedRegistry(99)
    h_b, b_b, r_b, s_b = generate_terrain_maps(reg_b, size=16, return_slope=True)
    assert np.allclose(h_a, h_b)
    assert np.array_equal(b_a, b_b)
    assert np.array_equal(r_a, r_b)
    assert np.allclose(s_a, s_b)
    assert s_a.shape == (16, 16)
    assert s_a.dtype == np.float32
    assert 0.0 <= float(s_a.min()) <= 1.0
    assert 0.0 <= float(s_a.max()) <= 1.0
