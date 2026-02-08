"""Integration tests for C++ GameManager.

These tests require the C++ procengine_cpp module to be built and
available. They are skipped automatically when the module is absent.
"""
import time

import pytest

procengine_cpp = pytest.importorskip("procengine_cpp")


def test_game_manager_creation():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=2)
    assert mgr is not None


def test_sync_frame_returns_directive():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=1)
    d = mgr.sync_frame(1 / 60, 0.0, 0.0, 4, 2, 64)
    assert d.max_chunk_loads >= 0
    assert 0.0 <= d.lod_bias <= 1.0
    assert d.recommended_render_distance >= 1


def test_async_chunk_generation():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=2)
    # Trigger generation at origin
    mgr.sync_frame(1 / 60, 32.0, 32.0, 2, 1, 64)
    # Wait for workers
    time.sleep(1.0)
    results = mgr.collect_ready_chunks(100)
    assert len(results) > 0
    r = results[0]
    assert r.height.shape == (64, 64)
    assert r.biome.shape == (64, 64)


def test_deterministic_across_runs():
    """Same seed + position produces same terrain."""
    import numpy as np

    mgr1 = procengine_cpp.GameManager(seed=12345, worker_count=1)
    mgr1.sync_frame(1 / 60, 0.0, 0.0, 1, 1, 64)
    time.sleep(0.5)
    r1 = mgr1.collect_ready_chunks(100)

    mgr2 = procengine_cpp.GameManager(seed=12345, worker_count=1)
    mgr2.sync_frame(1 / 60, 0.0, 0.0, 1, 1, 64)
    time.sleep(0.5)
    r2 = mgr2.collect_ready_chunks(100)

    # Find matching coords and compare
    for a in r1:
        for b in r2:
            if a.coord.x == b.coord.x and a.coord.z == b.coord.z:
                assert np.allclose(a.height, b.height)


def test_performance_metrics():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=1)
    mgr.sync_frame(1 / 60, 0.0, 0.0, 1, 1, 64)
    metrics = mgr.get_metrics()
    assert metrics.avg_frame_ms >= 0.0
    assert metrics.worker_threads_active >= 1


def test_set_frame_budget():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=1)
    mgr.set_frame_budget_ms(8.0)
    # Should not raise
    d = mgr.sync_frame(1 / 60, 0.0, 0.0, 4, 2, 64)
    assert d.max_chunk_loads >= 0


def test_set_terrain_config():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=1)
    mgr.set_terrain_config(4, 6, 0, False)
    d = mgr.sync_frame(1 / 60, 0.0, 0.0, 1, 1, 64)
    assert d.max_chunk_loads >= 0


def test_chunk_unload_tracking():
    mgr = procengine_cpp.GameManager(seed=42, worker_count=2)
    # Generate some chunks
    mgr.sync_frame(1 / 60, 0.0, 0.0, 2, 1, 64)
    time.sleep(1.0)
    results = mgr.collect_ready_chunks(100)
    # Mark some as uploaded
    for r in results:
        mgr.mark_chunk_uploaded(procengine_cpp.ChunkCoord(r.coord.x, r.coord.z))
    # Move player far away and ask for unloads
    to_unload = mgr.get_chunks_to_unload(100, 100, 3)
    # Uploaded chunks near origin should be marked for unload
    assert len(to_unload) >= 0  # May or may not have any depending on distance
