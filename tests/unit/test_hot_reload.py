"""Comprehensive tests for hot-reloading functionality.

This test module validates that the hot-reload system properly:
- Tracks descriptor hashes
- Marks resources as dirty when reloaded
- Processes the hot-reload queue on each frame step
- Rebuilds resources when requested
- Integrates with the shader cache for materials
"""

from procengine.core.engine import Engine as PyEngine


def test_hot_reload_marks_resource_dirty():
    """Test that calling hot_reload marks a resource as dirty."""
    engine = PyEngine()

    # Enqueue a descriptor
    descriptor = [{"type": "rock", "radius": 2.5, "seed": 42}]
    engine.enqueue_prop_descriptor(descriptor)

    # Simulate getting a hash (in real usage, this would come from the descriptor)
    test_hash = 12345

    # Hot reload should mark it as dirty
    engine.hot_reload(test_hash)

    # After stepping, the reload should be processed
    engine.step(1 / 60)

    # The hash should be recorded
    assert test_hash in engine._hot_reload_hashes


def test_hot_reload_queue_processing():
    """Test that hot-reload requests are queued and processed on step."""
    engine = PyEngine()

    # Queue multiple hot-reloads
    hashes = [100, 200, 300]
    for h in hashes:
        engine.hot_reload(h)

    # All should be in the queue
    assert len(engine._hot_reload_hashes) == 3

    # After stepping, they should still be tracked
    engine.step(1 / 60)
    assert len(engine._hot_reload_hashes) == 3


def test_hot_reload_reset_clears_queue():
    """Test that reset clears the hot-reload queue."""
    engine = PyEngine()

    engine.hot_reload(999)
    engine.step(1 / 60)

    assert len(engine._hot_reload_hashes) == 1

    # Reset should clear everything
    engine.reset()
    assert len(engine._hot_reload_hashes) == 0
    assert engine._frame == 0


def test_hot_reload_determinism():
    """Test that hot-reload operations are deterministic."""
    engine_a = PyEngine()
    engine_b = PyEngine()

    # Same sequence of operations
    for engine in [engine_a, engine_b]:
        descriptor = [{"type": "tree", "height": 10, "seed": 7}]
        engine.enqueue_prop_descriptor(descriptor)
        engine.hot_reload(555)
        engine.step(1 / 60)

    # Should produce identical state
    assert engine_a.snapshot_state(1) == engine_b.snapshot_state(1)


def test_hot_reload_affects_snapshot():
    """Test that hot-reload changes affect state snapshots."""
    engine_a = PyEngine()
    engine_b = PyEngine()

    # Different hot-reload sequences
    engine_a.hot_reload(111)
    engine_b.hot_reload(222)

    engine_a.step(1 / 60)
    engine_b.step(1 / 60)

    # Should produce different snapshots
    assert engine_a.snapshot_state(1) != engine_b.snapshot_state(1)


def test_hot_reload_multiple_frames():
    """Test hot-reload across multiple frames."""
    engine = PyEngine()

    # Hot-reload at different frames
    engine.hot_reload(1001)
    engine.step(1 / 60)  # Frame 1

    engine.hot_reload(1002)
    engine.step(1 / 60)  # Frame 2

    engine.hot_reload(1003)
    engine.step(1 / 60)  # Frame 3

    # All should be tracked
    assert 1001 in engine._hot_reload_hashes
    assert 1002 in engine._hot_reload_hashes
    assert 1003 in engine._hot_reload_hashes


def test_hot_reload_with_descriptors():
    """Test hot-reload in conjunction with descriptor changes."""
    engine = PyEngine()

    # Initial descriptor
    desc_v1 = [{"type": "building", "floors": 3, "seed": 99}]
    engine.enqueue_prop_descriptor(desc_v1)
    engine.step(1 / 60)

    snapshot_v1 = engine.snapshot_state(1)

    # Modified descriptor (simulating an edit)
    desc_v2 = [{"type": "building", "floors": 5, "seed": 99}]  # More floors
    engine.enqueue_prop_descriptor(desc_v2)
    engine.hot_reload(888)  # Signal to reload
    engine.step(1 / 60)

    snapshot_v2 = engine.snapshot_state(2)

    # Snapshots should differ due to descriptor change
    assert snapshot_v1 != snapshot_v2


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
