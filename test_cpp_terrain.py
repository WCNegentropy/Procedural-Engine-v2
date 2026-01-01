"""Integration tests for the C++ terrain generation module."""

from __future__ import annotations

import numpy as np
import pytest

procengine_cpp = pytest.importorskip("procengine_cpp")


def test_generate_terrain_deterministic() -> None:
    """Same seed produces identical terrain maps."""
    seed = 12345

    h1, b1, r1 = procengine_cpp.generate_terrain_standalone(seed, size=32)
    h2, b2, r2 = procengine_cpp.generate_terrain_standalone(seed, size=32)

    assert np.allclose(h1, h2), "Heightmaps should be identical for same seed"
    assert np.array_equal(b1, b2), "Biome maps should be identical for same seed"
    assert np.array_equal(r1, r2), "River maps should be identical for same seed"


def test_generate_terrain_different_seeds_differ() -> None:
    """Different seeds produce different terrain."""
    h1, b1, r1 = procengine_cpp.generate_terrain_standalone(111, size=32)
    h2, b2, r2 = procengine_cpp.generate_terrain_standalone(222, size=32)

    assert not np.allclose(h1, h2), "Different seeds should produce different heightmaps"


def test_generate_terrain_output_shape_and_dtype() -> None:
    """Output arrays have correct shape and dtype."""
    size = 64
    height, biome, river = procengine_cpp.generate_terrain_standalone(42, size=size)

    assert height.shape == (size, size), f"Height shape should be ({size}, {size})"
    assert biome.shape == (size, size), f"Biome shape should be ({size}, {size})"
    assert river.shape == (size, size), f"River shape should be ({size}, {size})"

    assert height.dtype == np.float32, "Height should be float32"
    assert biome.dtype == np.uint8, "Biome should be uint8"
    assert river.dtype == np.uint8, "River should be uint8"


def test_generate_terrain_height_range() -> None:
    """Height values are normalized to [0, 1]."""
    height, _, _ = procengine_cpp.generate_terrain_standalone(999, size=64)

    assert height.min() >= 0.0, "Height minimum should be >= 0"
    assert height.max() <= 1.0, "Height maximum should be <= 1"
    # Ensure we have actual variation
    assert height.max() - height.min() > 0.1, "Height should have variation"


def test_generate_terrain_biome_variety() -> None:
    """Biome map contains multiple distinct biomes."""
    _, biome, _ = procengine_cpp.generate_terrain_standalone(42, size=64, macro_points=8)

    unique_biomes = np.unique(biome)
    assert len(unique_biomes) > 1, "Should have multiple biome types"
    assert biome.max() <= 15, "Biome index should be <= 15"


def test_generate_terrain_river_mask() -> None:
    """River mask contains binary values."""
    _, _, river = procengine_cpp.generate_terrain_standalone(123, size=64)

    unique_values = np.unique(river)
    assert all(v in (0, 1) for v in unique_values), "River mask should be binary"
    # With 5% probability, we should have some river cells
    assert river.sum() > 0, "Should have some river cells"


def test_generate_terrain_with_erosion() -> None:
    """Erosion modifies the heightmap deterministically."""
    seed = 777

    # Without erosion
    h_no_erosion, _, _ = procengine_cpp.generate_terrain_standalone(
        seed, size=32, erosion_iters=0
    )

    # With erosion - run twice to verify determinism
    h_eroded1, _, _ = procengine_cpp.generate_terrain_standalone(
        seed, size=32, erosion_iters=50
    )
    h_eroded2, _, _ = procengine_cpp.generate_terrain_standalone(
        seed, size=32, erosion_iters=50
    )

    # Erosion should be deterministic
    assert np.allclose(h_eroded1, h_eroded2), "Erosion should be deterministic"

    # Erosion should modify the heightmap
    assert not np.allclose(h_no_erosion, h_eroded1), "Erosion should modify heightmap"


def test_generate_terrain_with_slope() -> None:
    """Slope map generation works correctly."""
    seed = 888

    # Without slope
    result_no_slope = procengine_cpp.generate_terrain_standalone(
        seed, size=32, return_slope=False
    )
    assert len(result_no_slope) == 3, "Without slope should return 3 arrays"

    # With slope - verify determinism
    h1, b1, r1, s1 = procengine_cpp.generate_terrain_standalone(
        seed, size=32, return_slope=True
    )
    h2, b2, r2, s2 = procengine_cpp.generate_terrain_standalone(
        seed, size=32, return_slope=True
    )

    assert np.allclose(s1, s2), "Slope should be deterministic"
    assert s1.shape == (32, 32), "Slope shape should match terrain size"
    assert s1.dtype == np.float32, "Slope should be float32"
    assert s1.min() >= 0.0, "Slope minimum should be >= 0"
    assert s1.max() <= 1.0, "Slope maximum should be <= 1"


def test_generate_terrain_octaves() -> None:
    """Different octave counts produce different results."""
    seed = 555

    h_low, _, _ = procengine_cpp.generate_terrain_standalone(seed, size=32, octaves=2)
    h_high, _, _ = procengine_cpp.generate_terrain_standalone(seed, size=32, octaves=8)

    # More octaves = more detail, so the maps should differ
    assert not np.allclose(h_low, h_high), "Different octave counts should produce different terrain"


def test_generate_terrain_macro_points() -> None:
    """Macro points affect terrain generation."""
    seed = 444

    h_no_macro, _, _ = procengine_cpp.generate_terrain_standalone(
        seed, size=32, macro_points=0
    )
    h_with_macro, _, _ = procengine_cpp.generate_terrain_standalone(
        seed, size=32, macro_points=8
    )

    # Macro plates should modify the terrain
    assert not np.allclose(h_no_macro, h_with_macro), "Macro points should affect terrain"


def test_engine_generate_terrain() -> None:
    """Engine's generate_terrain method works correctly."""
    engine = procengine_cpp.Engine(42)

    height, biome, river = engine.generate_terrain(size=32)

    assert height.shape == (32, 32)
    assert biome.shape == (32, 32)
    assert river.shape == (32, 32)
    assert height.dtype == np.float32
    assert 0.0 <= height.min() and height.max() <= 1.0


def test_engine_generate_terrain_determinism() -> None:
    """Engine terrain generation is deterministic within the same engine."""
    # Two engines with the same seed
    engine1 = procengine_cpp.Engine(999)
    engine2 = procengine_cpp.Engine(999)

    h1, b1, r1 = engine1.generate_terrain(size=32)
    h2, b2, r2 = engine2.generate_terrain(size=32)

    assert np.allclose(h1, h2), "Same seed engines should produce same terrain"
    assert np.array_equal(b1, b2)
    assert np.array_equal(r1, r2)
