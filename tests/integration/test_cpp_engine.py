"""Integration tests for the C++ :class:`Engine` module."""

from __future__ import annotations

import pytest

from procengine.core.seed_registry import SeedRegistry
from procengine.world.terrain import generate_terrain_maps


procengine_cpp = pytest.importorskip("procengine_cpp")


def _terrain_bytes(registry: SeedRegistry) -> tuple[memoryview, memoryview, memoryview]:
    """Return terrain buffers as memoryviews for the C++ engine."""

    height, biome, river = generate_terrain_maps(registry)
    return (
        memoryview(height.tobytes()),
        memoryview(biome.tobytes()),
        memoryview(river.tobytes()),
    )


def test_snapshot_deterministic() -> None:
    """Two engines fed the same data should yield identical snapshots."""

    registry = SeedRegistry(99)
    h_bytes, b_bytes, r_bytes = _terrain_bytes(registry)

    engine_a = procengine_cpp.Engine(123)
    engine_b = procengine_cpp.Engine(123)

    engine_a.enqueue_heightmap(h_bytes, b_bytes, r_bytes)
    engine_b.enqueue_heightmap(h_bytes, b_bytes, r_bytes)

    descriptor = [{"type": "rock", "seed": 1}]
    engine_a.enqueue_prop_descriptor(descriptor)
    engine_b.enqueue_prop_descriptor(descriptor)

    engine_a.step(1 / 60)
    engine_b.step(1 / 60)

    assert engine_a.snapshot_state(1) == engine_b.snapshot_state(1)


def test_reset_returns_to_pristine_state() -> None:
    """Resetting should reproduce the initial snapshot."""

    engine = procengine_cpp.Engine(555)
    engine.hot_reload(42)
    engine.step(1 / 60)
    engine.reset()

    fresh = procengine_cpp.Engine(555)
    assert engine.snapshot_state(0) == fresh.snapshot_state(0)

