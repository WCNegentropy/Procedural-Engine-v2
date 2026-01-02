"""Tests for the :mod:`engine` module and its deterministic behaviour."""

from engine import Engine
from seed_registry import SeedRegistry
from terrain import generate_terrain_maps


def test_snapshot_deterministic():
    registry = SeedRegistry(99)
    height, biome, river = generate_terrain_maps(registry)

    h_bytes = memoryview(height.tobytes())
    b_bytes = memoryview(biome.tobytes())
    r_bytes = memoryview(river.tobytes())

    engine_a = Engine()
    engine_b = Engine()

    engine_a.enqueue_heightmap(h_bytes, b_bytes, r_bytes)
    engine_b.enqueue_heightmap(h_bytes, b_bytes, r_bytes)

    descriptor = [{"type": "rock", "seed": 1}]
    engine_a.enqueue_prop_descriptor(descriptor)
    engine_b.enqueue_prop_descriptor(descriptor)

    engine_a.step(1 / 60)
    engine_b.step(1 / 60)

    hash_a = engine_a.snapshot_state(1)
    hash_b = engine_b.snapshot_state(1)

    assert hash_a == hash_b


def test_hot_reload_affects_snapshot():
    engine_a = Engine()
    engine_b = Engine()

    engine_a.hot_reload(1234)
    engine_b.hot_reload(1234)

    engine_a.step(1 / 60)
    engine_b.step(1 / 60)

    assert engine_a.snapshot_state(1) == engine_b.snapshot_state(1)


def test_reset_clears_state():
    engine = Engine()
    engine.hot_reload(42)
    engine.step(1 / 60)
    assert engine._frame == 1

    engine.reset()
    # After reset the frame counter and hot-reload history should be cleared
    assert engine._frame == 0
    assert len(engine._hot_reload_hashes) == 0
    # A new snapshot at frame 0 should now be valid
    assert engine.snapshot_state(0) == Engine().snapshot_state(0)
