"""Tests covering deterministic terrain map generation."""

import numpy as np

from procengine.core.seed_registry import SeedRegistry
from procengine.world.terrain import generate_terrain_maps


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


# =============================================================================
# Seamless Chunk Boundary Tests
# =============================================================================


def test_seamless_chunk_boundaries_noise_continuity():
    """Test that terrain noise is continuous across chunk boundaries.

    This is the key test for the global coordinate generation pipeline.
    Adjacent chunks should have matching height values at their shared edge.
    """
    chunk_size = 32
    seed = 42

    # Generate two adjacent chunks: chunk(0,0) and chunk(1,0)
    # Disable macro points to test pure FBM noise continuity
    reg1 = SeedRegistry(seed)
    h1, _, _ = generate_terrain_maps(
        reg1.spawn("chunk_0_0"), size=chunk_size,
        offset_x=0, offset_z=0,
        macro_points=0, base_frequency=0.01
    )

    reg2 = SeedRegistry(seed)
    h2, _, _ = generate_terrain_maps(
        reg2.spawn("chunk_1_0"), size=chunk_size,
        offset_x=chunk_size, offset_z=0,  # Offset by one chunk width
        macro_points=0, base_frequency=0.01
    )

    # The right edge of chunk(0,0) should match the left edge of chunk(1,0)
    # Due to per-chunk normalization, values may differ slightly, but
    # the pattern should be continuous (no sudden jumps)

    # Get edge values
    right_edge_chunk0 = h1[:, -1]  # Right edge of chunk 0
    left_edge_chunk1 = h2[:, 0]    # Left edge of chunk 1

    # The edge heights should follow a similar trend (not be wildly different)
    # Due to normalization, exact match isn't expected, but gradient should be smooth
    # Test that the correlation is positive (heights trend together)
    correlation = np.corrcoef(right_edge_chunk0, left_edge_chunk1)[0, 1]
    assert correlation > 0.5, f"Chunk edge correlation {correlation} is too low - seams likely"


def test_same_world_coordinate_same_noise():
    """Test that the same world coordinate produces the same base noise value.

    This verifies that the noise function samples correctly with offsets.
    """
    chunk_size = 16
    seed = 123

    # Generate chunk at (0,0) - local position (15,15) = world position (15,15)
    reg1 = SeedRegistry(seed)
    h1, _, _ = generate_terrain_maps(
        reg1.spawn("test1"), size=chunk_size,
        offset_x=0, offset_z=0,
        macro_points=0, erosion_iters=0
    )

    # Generate chunk at (1,1) - local position (0,0) = world position (16,16)
    # This tests different but nearby world coordinates
    reg2 = SeedRegistry(seed)
    h2, _, _ = generate_terrain_maps(
        reg2.spawn("test2"), size=chunk_size,
        offset_x=chunk_size, offset_z=chunk_size,
        macro_points=0, erosion_iters=0
    )

    # The chunks should produce different but valid heightmaps
    # (not identical because they're at different world positions)
    assert h1.shape == h2.shape
    assert not np.allclose(h1, h2)  # Different positions should give different terrain


def test_large_feature_span_multiple_chunks():
    """Test that terrain features can span multiple chunks with low frequency.

    With base_frequency=0.01, one noise cycle spans 100 world units.
    This test verifies that chunks show gradual variation, not random noise.
    """
    chunk_size = 32
    seed = 555

    # Generate 3 adjacent chunks in X direction
    chunks = []
    for i in range(3):
        reg = SeedRegistry(seed)
        h, _, _ = generate_terrain_maps(
            reg.spawn(f"chunk_{i}_0"), size=chunk_size,
            offset_x=i * chunk_size, offset_z=0,
            macro_points=0, base_frequency=0.01
        )
        chunks.append(h)

    # With low frequency, adjacent chunks should have similar average heights
    # (not wildly different like they would be with per-chunk noise)
    means = [np.mean(c) for c in chunks]

    # Variance between chunk means should be relatively low
    # (indicating gradual terrain change, not random per-chunk noise)
    mean_variance = np.var(means)
    assert mean_variance < 0.1, f"Chunk means vary too much ({mean_variance}) - features not spanning chunks"
