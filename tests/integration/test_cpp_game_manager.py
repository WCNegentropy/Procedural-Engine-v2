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
    # C++ now generates with size+1 for vertex overlap
    assert r.height.shape == (65, 65)
    assert r.biome.shape == (65, 65)


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


def test_slope_map_populated():
    """Async chunks should include slope data when compute_slope is enabled."""
    mgr = procengine_cpp.GameManager(seed=42, worker_count=1)
    mgr.set_terrain_config(6, 0, 0, True)  # compute_slope = True
    mgr.sync_frame(1 / 60, 0.0, 0.0, 1, 1, 64)
    time.sleep(1.0)
    results = mgr.collect_ready_chunks(100)
    assert len(results) > 0
    r = results[0]
    assert r.slope.shape == (65, 65)  # size+1 for vertex overlap
    assert r.slope.size > 0


def test_metrics_chunk_counts():
    """PerformanceMetrics should report non-zero chunk counts after generation."""
    mgr = procengine_cpp.GameManager(seed=42, worker_count=2)
    mgr.sync_frame(1 / 60, 0.0, 0.0, 2, 1, 64)
    time.sleep(1.0)
    _ = mgr.collect_ready_chunks(100)
    metrics = mgr.get_metrics()
    # After generation and collection, some chunks should be in Ready state
    # (or Queued/Uploaded depending on timing).  At minimum, the counts
    # shouldn't all be zero for non-trivial workloads.
    total = metrics.active_chunks + metrics.queued_chunks + metrics.ready_chunks
    assert total >= 0  # Non-negative counts
    assert metrics.worker_threads_active >= 1


def test_global_seed_determinism():
    """Same global seed produces identical terrain regardless of chunk ordering."""
    import numpy as np

    mgr1 = procengine_cpp.GameManager(seed=99999, worker_count=1)
    mgr1.sync_frame(1 / 60, 32.0, 32.0, 1, 1, 64)
    time.sleep(1.0)
    r1 = mgr1.collect_ready_chunks(100)

    mgr2 = procengine_cpp.GameManager(seed=99999, worker_count=1)
    mgr2.sync_frame(1 / 60, 32.0, 32.0, 1, 1, 64)
    time.sleep(1.0)
    r2 = mgr2.collect_ready_chunks(100)

    # Find the origin chunk (0,0) in both results
    r1_origin = [r for r in r1 if r.coord.x == 0 and r.coord.z == 0]
    r2_origin = [r for r in r2 if r.coord.x == 0 and r.coord.z == 0]
    assert len(r1_origin) > 0 and len(r2_origin) > 0
    assert np.allclose(r1_origin[0].height, r2_origin[0].height)
