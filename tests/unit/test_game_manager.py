"""Tests for GameManagerBridge fallback behavior."""
from procengine.managers.game_manager import GameManagerBridge, ManagerConfig, FrameDirective


class TestGameManagerFallback:
    """Verify the Python wrapper works when C++ is unavailable."""

    def test_fallback_when_cpp_unavailable(self):
        """Without C++ module, manager operates in fallback mode."""
        mgr = GameManagerBridge(seed=42)
        # May or may not be available depending on build
        directive = mgr.sync_frame(1 / 60, 0.0, 0.0, 6, 3, 64)
        assert hasattr(directive, "max_chunk_loads")

    def test_collect_ready_empty_fallback(self):
        mgr = GameManagerBridge(seed=42)
        if not mgr.available:
            assert mgr.collect_ready_chunks() == []

    def test_metrics_none_fallback(self):
        mgr = GameManagerBridge(seed=42)
        if not mgr.available:
            assert mgr.get_metrics() is None

    def test_mark_chunk_uploaded_no_error(self):
        """mark_chunk_uploaded should not raise when C++ is absent."""
        mgr = GameManagerBridge(seed=42)
        mgr.mark_chunk_uploaded(0, 0)

    def test_get_chunks_to_unload_empty(self):
        mgr = GameManagerBridge(seed=42)
        if not mgr.available:
            assert mgr.get_chunks_to_unload(0, 0, 8) == []


class TestManagerConfig:
    """Verify ManagerConfig defaults."""

    def test_default_config(self):
        cfg = ManagerConfig()
        assert cfg.frame_budget_ms == 13.0
        assert cfg.terrain_octaves == 6
        assert cfg.terrain_macro_points == 8
        assert cfg.terrain_erosion_iters == 0
        assert cfg.worker_threads == 0

    def test_custom_config(self):
        cfg = ManagerConfig(frame_budget_ms=16.0, worker_threads=4)
        assert cfg.frame_budget_ms == 16.0
        assert cfg.worker_threads == 4


class TestFrameDirectiveDefaults:
    """Verify the Python fallback FrameDirective defaults."""

    def test_default_values(self):
        d = FrameDirective()
        assert d.max_chunk_loads == 1
        assert d.lod_bias == 0.0
        assert d.skip_physics_step is False
        assert d.recommended_render_distance == 6
        assert d.recommended_sim_distance == 3
        assert d.recommended_erosion_iters == 0.0


class TestChunkManagerDistanceSetters:
    """Verify that ChunkManager render_distance/sim_distance setters work."""

    def test_render_distance_setter(self):
        from procengine.core.seed_registry import SeedRegistry
        from procengine.world.chunk import ChunkManager

        mgr = ChunkManager(SeedRegistry(42), render_distance=6, sim_distance=3)
        mgr.render_distance = 4
        assert mgr.render_distance == 4

    def test_sim_distance_setter(self):
        from procengine.core.seed_registry import SeedRegistry
        from procengine.world.chunk import ChunkManager

        mgr = ChunkManager(SeedRegistry(42), render_distance=6, sim_distance=3)
        mgr.sim_distance = 2
        assert mgr.sim_distance == 2

    def test_sim_distance_clamped_to_render(self):
        from procengine.core.seed_registry import SeedRegistry
        from procengine.world.chunk import ChunkManager

        mgr = ChunkManager(SeedRegistry(42), render_distance=4, sim_distance=3)
        # sim_distance should be clamped to render_distance
        mgr.sim_distance = 10
        assert mgr.sim_distance == 4

    def test_render_distance_min_one(self):
        from procengine.core.seed_registry import SeedRegistry
        from procengine.world.chunk import ChunkManager

        mgr = ChunkManager(SeedRegistry(42), render_distance=6, sim_distance=3)
        mgr.render_distance = 0
        assert mgr.render_distance == 1
