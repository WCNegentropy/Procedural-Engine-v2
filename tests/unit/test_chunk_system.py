"""Tests for the chunk system module.

Tests cover:
- Chunk data structure and coordinate calculations
- ChunkManager for dynamic loading/unloading
- World-to-chunk coordinate conversion
- Spatial partitioning and entity queries
- ChunkedHeightField for physics
- Deterministic chunk generation with SeedRegistry
"""
import pytest
import numpy as np
from typing import Tuple

from procengine.world.chunk import (
    Chunk,
    ChunkCoord,
    ChunkManager,
    ChunkedHeightField,
)
from procengine.core.seed_registry import SeedRegistry


# =============================================================================
# Chunk Data Structure Tests
# =============================================================================


class TestChunk:
    """Test the Chunk dataclass."""

    def test_chunk_creation_defaults(self):
        """Test creating a chunk with default values."""
        chunk = Chunk(coords=(0, 0))
        assert chunk.coords == (0, 0)
        assert chunk.mesh_id == "terrain_0_0"
        assert chunk.heightmap is None
        assert chunk.is_loaded is False
        assert chunk.is_mesh_uploaded is False
        assert chunk.is_simulating is False
        assert len(chunk.entity_ids) == 0

    def test_chunk_creation_with_data(self):
        """Test creating a chunk with terrain data."""
        heightmap = np.zeros((64, 64), dtype=np.float32)
        biome = np.zeros((64, 64), dtype=np.uint8)

        chunk = Chunk(
            coords=(5, -3),
            heightmap=heightmap,
            biome_map=biome,
            is_loaded=True,
        )

        assert chunk.coords == (5, -3)
        assert chunk.mesh_id == "terrain_5_-3"
        assert chunk.heightmap is not None
        assert chunk.biome_map is not None
        assert chunk.is_loaded is True

    def test_chunk_world_origin(self):
        """Test calculating world origin from chunk coordinates."""
        chunk_size = 64
        chunk = Chunk(coords=(2, 3))
        origin = chunk.world_origin(chunk_size)
        assert origin == (128.0, 192.0)

        chunk_neg = Chunk(coords=(-1, -2))
        origin_neg = chunk_neg.world_origin(chunk_size)
        assert origin_neg == (-64.0, -128.0)

    def test_chunk_contains_world_position(self):
        """Test checking if a position is inside a chunk."""
        chunk_size = 64
        chunk = Chunk(coords=(1, 1))

        # Position inside chunk (64 to 127)
        assert chunk.contains_world_position(70.0, 80.0, chunk_size) is True
        assert chunk.contains_world_position(64.0, 64.0, chunk_size) is True
        assert chunk.contains_world_position(127.9, 127.9, chunk_size) is True

        # Position outside chunk
        assert chunk.contains_world_position(63.0, 70.0, chunk_size) is False
        assert chunk.contains_world_position(128.0, 70.0, chunk_size) is False
        assert chunk.contains_world_position(70.0, 128.0, chunk_size) is False

    def test_chunk_entity_ids(self):
        """Test managing entity IDs in a chunk."""
        chunk = Chunk(coords=(0, 0))
        
        chunk.entity_ids.add("entity_1")
        chunk.entity_ids.add("entity_2")
        
        assert "entity_1" in chunk.entity_ids
        assert "entity_2" in chunk.entity_ids
        assert len(chunk.entity_ids) == 2
        
        chunk.entity_ids.discard("entity_1")
        assert "entity_1" not in chunk.entity_ids
        assert len(chunk.entity_ids) == 1


# =============================================================================
# ChunkManager Tests
# =============================================================================


class TestChunkManager:
    """Test the ChunkManager class."""

    def test_manager_creation(self):
        """Test creating a chunk manager with default settings."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry)

        assert manager.chunk_size == 64
        assert manager.render_distance == 8
        assert manager.sim_distance == 4
        assert len(manager.chunks) == 0
        assert manager.player_chunk == (0, 0)

    def test_manager_creation_custom(self):
        """Test creating a chunk manager with custom settings."""
        registry = SeedRegistry(123)
        manager = ChunkManager(
            registry,
            chunk_size=32,
            render_distance=4,
            sim_distance=2,
        )

        assert manager.chunk_size == 32
        assert manager.render_distance == 4
        assert manager.sim_distance == 2

    def test_world_to_chunk_conversion(self):
        """Test converting world coordinates to chunk coordinates."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64)

        # Positive coordinates
        assert manager.world_to_chunk(0.0, 0.0) == (0, 0)
        assert manager.world_to_chunk(32.0, 32.0) == (0, 0)
        assert manager.world_to_chunk(63.9, 63.9) == (0, 0)
        assert manager.world_to_chunk(64.0, 64.0) == (1, 1)
        assert manager.world_to_chunk(128.0, 192.0) == (2, 3)

        # Negative coordinates
        assert manager.world_to_chunk(-1.0, -1.0) == (-1, -1)
        assert manager.world_to_chunk(-64.0, -64.0) == (-1, -1)
        assert manager.world_to_chunk(-65.0, -65.0) == (-2, -2)

    def test_chunk_to_world_conversion(self):
        """Test converting chunk coordinates to world origin."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64)

        assert manager.chunk_to_world((0, 0)) == (0.0, 0.0)
        assert manager.chunk_to_world((1, 1)) == (64.0, 64.0)
        assert manager.chunk_to_world((-1, -1)) == (-64.0, -64.0)
        assert manager.chunk_to_world((2, 3)) == (128.0, 192.0)

    def test_update_player_position_loads_chunks(self):
        """Test that updating player position queues chunks for loading."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        # Initially empty
        assert len(manager.chunks) == 0
        assert manager.get_load_queue_size() == 0

        # Update player position
        manager.update_player_position(32.0, 32.0)

        # Should have queued chunks around (0, 0)
        # With radius 1 (circular), should have 5 chunks: center + 4 cardinal
        assert manager.get_load_queue_size() == 5
        assert manager.player_chunk == (0, 0)

    def test_process_load_queue_generates_chunks(self):
        """Test that processing the load queue generates chunk data."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=1)

        manager.update_player_position(16.0, 16.0)
        
        # Process one chunk
        generated = manager.process_load_queue(max_per_frame=1)
        
        assert len(generated) == 1
        chunk = generated[0]
        assert chunk.is_loaded is True
        assert chunk.heightmap is not None
        assert chunk.heightmap.shape == (32, 32)
        assert chunk.biome_map is not None
        assert chunk.coords in manager.chunks

    def test_process_load_queue_respects_limit(self):
        """Test that load queue respects max_per_frame limit."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=2)

        manager.update_player_position(16.0, 16.0)
        initial_queue = manager.get_load_queue_size()
        
        # Process only 2 chunks
        generated = manager.process_load_queue(max_per_frame=2)
        
        assert len(generated) == 2
        assert manager.get_load_queue_size() == initial_queue - 2

    def test_unload_queue_on_player_move(self):
        """Test that moving player away queues old chunks for unload."""
        registry = SeedRegistry(42)
        manager = ChunkManager(
            registry,
            chunk_size=64,
            render_distance=1,
            unload_buffer=0,  # Immediate unload
        )

        # Start at origin
        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        # Move far away
        manager.update_player_position(1000.0, 1000.0)

        # Old chunks should be queued for unload
        assert manager.get_unload_queue_size() > 0

    def test_process_unload_queue(self):
        """Test that processing unload queue removes chunks."""
        registry = SeedRegistry(42)
        manager = ChunkManager(
            registry,
            chunk_size=64,
            render_distance=1,
            unload_buffer=0,
        )

        # Start at origin and load chunks
        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)
        
        initial_chunk_count = len(manager.chunks)
        
        # Move far away
        manager.update_player_position(1000.0, 1000.0)
        
        # Process unloads
        unloaded = manager.process_unload_queue(max_per_frame=100)
        
        assert len(unloaded) > 0
        assert len(manager.chunks) < initial_chunk_count

    def test_get_render_chunks(self):
        """Test getting chunks within render distance."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        render_chunks = manager.get_render_chunks()
        assert len(render_chunks) == 5  # circular: center + 4 cardinal directions

    def test_get_sim_chunks(self):
        """Test getting chunks within simulation distance."""
        registry = SeedRegistry(42)
        manager = ChunkManager(
            registry,
            chunk_size=64,
            render_distance=2,
            sim_distance=1,
        )

        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=100)

        sim_chunks = manager.get_sim_chunks()
        # Simulation distance 1 (circular) = 5 chunks
        assert len(sim_chunks) == 5

    def test_get_chunk_at_world(self):
        """Test getting a specific chunk by world position."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        chunk = manager.get_chunk_at_world(32.0, 32.0)
        assert chunk is not None
        assert chunk.coords == (0, 0)

        # Position outside loaded area
        chunk_outside = manager.get_chunk_at_world(1000.0, 1000.0)
        assert chunk_outside is None

    def test_get_stats(self):
        """Test getting chunk manager statistics."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        manager.update_player_position(32.0, 32.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        stats = manager.get_stats()
        
        assert "active_chunks" in stats
        assert "render_chunks" in stats
        assert "sim_chunks" in stats
        assert "load_queue" in stats
        assert "unload_queue" in stats
        assert "total_generated" in stats
        assert "player_chunk" in stats
        assert stats["active_chunks"] == 5  # circular: center + 4 cardinal


# =============================================================================
# Deterministic Chunk Generation Tests
# =============================================================================


class TestChunkDeterminism:
    """Test deterministic chunk generation."""

    def test_same_seed_same_terrain(self):
        """Test that same seed produces identical terrain."""
        registry1 = SeedRegistry(42)
        registry2 = SeedRegistry(42)
        
        manager1 = ChunkManager(registry1, chunk_size=32, render_distance=0)
        manager2 = ChunkManager(registry2, chunk_size=32, render_distance=0)

        # Generate chunk at (1, 2)
        manager1.update_player_position(48.0, 80.0)  # Center of chunk (1, 2)
        manager2.update_player_position(48.0, 80.0)

        chunks1 = manager1.process_load_queue(max_per_frame=1)
        chunks2 = manager2.process_load_queue(max_per_frame=1)

        assert len(chunks1) == 1
        assert len(chunks2) == 1
        
        # Heightmaps should be identical
        np.testing.assert_array_equal(
            chunks1[0].heightmap,
            chunks2[0].heightmap,
        )

    def test_different_coords_different_terrain(self):
        """Test that different coordinates produce different terrain."""
        registry = SeedRegistry(42)
        # Use radius 2 to ensure both (0,0) and (1,0) are loaded
        manager = ChunkManager(registry, chunk_size=32, render_distance=2)

        manager.update_player_position(48.0, 48.0)  # chunk (1, 1)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=20)

        # Test adjacent chunks (both within circular radius 2 of (1,1))
        chunk_center = manager.chunks.get((1, 1))
        chunk_north = manager.chunks.get((1, 2))

        assert chunk_center is not None
        assert chunk_north is not None
        
        # Heights should be different
        assert not np.array_equal(chunk_center.heightmap, chunk_north.heightmap)

    def test_revisiting_chunk_same_data(self):
        """Test that revisiting a chunk after unload regenerates identical data."""
        registry = SeedRegistry(42)
        manager = ChunkManager(
            registry,
            chunk_size=32,
            render_distance=1,
            unload_buffer=0,
        )

        # Load chunk at origin
        manager.update_player_position(16.0, 16.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        original_chunk = manager.chunks.get((0, 0))
        original_heightmap = original_chunk.heightmap.copy()

        # Move far away to unload
        manager.update_player_position(1000.0, 1000.0)
        while manager.get_unload_queue_size() > 0:
            manager.process_unload_queue(max_per_frame=10)

        assert (0, 0) not in manager.chunks

        # Return to origin
        manager.update_player_position(16.0, 16.0)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=10)

        new_chunk = manager.chunks.get((0, 0))
        
        # Should be identical to before
        np.testing.assert_array_equal(new_chunk.heightmap, original_heightmap)


# =============================================================================
# ChunkedHeightField Tests
# =============================================================================


class TestChunkedHeightField:
    """Test the ChunkedHeightField for physics queries."""

    def test_sample_in_loaded_chunk(self):
        """Test sampling height in a loaded chunk."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=0)

        manager.update_player_position(16.0, 16.0)
        manager.process_load_queue(max_per_frame=1)

        heightfield = ChunkedHeightField(manager, height_scale=30.0)
        
        # Sample at various points
        height = heightfield.sample(16.0, 16.0)
        assert isinstance(height, float)
        assert 0.0 <= height <= 30.0  # Scaled height

    def test_sample_unloaded_chunk_returns_default(self):
        """Test that sampling unloaded area returns default height."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=0)

        heightfield = ChunkedHeightField(manager, default_height=-10.0)
        
        # No chunks loaded
        height = heightfield.sample(1000.0, 1000.0)
        assert height == -10.0

    def test_sample_interpolated(self):
        """Test bilinear interpolated height sampling."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=0)

        manager.update_player_position(16.0, 16.0)
        manager.process_load_queue(max_per_frame=1)

        heightfield = ChunkedHeightField(manager, height_scale=30.0)
        
        # Interpolated sample
        height = heightfield.sample_interpolated(16.5, 16.5)
        assert isinstance(height, float)

    def test_get_normal(self):
        """Test computing surface normal."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=0)

        manager.update_player_position(16.0, 16.0)
        manager.process_load_queue(max_per_frame=1)

        heightfield = ChunkedHeightField(manager, height_scale=30.0)
        
        normal = heightfield.get_normal(16.0, 16.0)
        
        assert len(normal) == 3
        # Normal should be roughly unit length
        length = (normal[0]**2 + normal[1]**2 + normal[2]**2) ** 0.5
        assert 0.99 < length < 1.01


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


class TestChunkEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_negative_chunk_coordinates(self):
        """Test chunks with negative coordinates."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        # Position that maps to negative chunks
        manager.update_player_position(-100.0, -100.0)
        
        assert manager.player_chunk == (-2, -2)
        
        manager.process_load_queue(max_per_frame=10)
        
        # Should have chunks with negative coords
        negative_chunks = [c for c in manager.chunks.keys() if c[0] < 0 or c[1] < 0]
        assert len(negative_chunks) > 0

    def test_chunk_boundary_crossing(self):
        """Test behavior when player crosses chunk boundaries."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        # Start at edge of chunk (0, 0)
        manager.update_player_position(63.0, 63.0)
        assert manager.player_chunk == (0, 0)

        # Cross into chunk (1, 1)
        manager.update_player_position(65.0, 65.0)
        assert manager.player_chunk == (1, 1)

    def test_empty_load_queue(self):
        """Test processing empty load queue."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=0)

        # No chunks queued
        generated = manager.process_load_queue(max_per_frame=10)
        assert len(generated) == 0

    def test_empty_unload_queue(self):
        """Test processing empty unload queue."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=0)

        # No chunks to unload
        unloaded = manager.process_unload_queue(max_per_frame=10)
        assert len(unloaded) == 0

    def test_render_distance_change(self):
        """Test changing render distance dynamically."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=1)

        manager.render_distance = 2
        assert manager.render_distance == 2

        # Should accept minimum of 1
        manager.render_distance = 0
        assert manager.render_distance == 1

    def test_sim_distance_capped_by_render(self):
        """Test that sim distance cannot exceed render distance."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=64, render_distance=2, sim_distance=1)

        # Try to set sim distance higher than render
        manager.sim_distance = 10
        assert manager.sim_distance == 2  # Capped at render_distance


# =============================================================================
# Chunk Props Generation Tests
# =============================================================================


class TestChunkPropsGeneration:
    """Test chunk prop generation integration."""

    def test_chunk_has_pending_props_field(self):
        """Test that Chunk dataclass has pending_props field."""
        chunk = Chunk(coords=(0, 0))
        assert hasattr(chunk, 'pending_props')
        assert isinstance(chunk.pending_props, list)
        assert len(chunk.pending_props) == 0

    def test_generated_chunk_has_pending_props(self):
        """Test that generated chunks include pending props."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=0)

        manager.update_player_position(16.0, 16.0)
        generated = manager.process_load_queue(max_per_frame=1)

        assert len(generated) == 1
        chunk = generated[0]

        # Chunk should have pending_props (list may be empty due to terrain validation)
        assert hasattr(chunk, 'pending_props')
        assert isinstance(chunk.pending_props, list)

    def test_chunk_props_deterministic(self):
        """Test that chunk props are deterministically generated."""
        registry1 = SeedRegistry(42)
        registry2 = SeedRegistry(42)

        manager1 = ChunkManager(registry1, chunk_size=32, render_distance=0)
        manager2 = ChunkManager(registry2, chunk_size=32, render_distance=0)

        manager1.update_player_position(16.0, 16.0)
        manager2.update_player_position(16.0, 16.0)

        chunks1 = manager1.process_load_queue(max_per_frame=1)
        chunks2 = manager2.process_load_queue(max_per_frame=1)

        # Both should have identical pending props
        assert chunks1[0].pending_props == chunks2[0].pending_props

    def test_different_chunks_different_props(self):
        """Test that different chunks get different prop layouts."""
        registry = SeedRegistry(42)
        manager = ChunkManager(registry, chunk_size=32, render_distance=2)

        manager.update_player_position(48.0, 48.0)  # chunk (1, 1)
        while manager.get_load_queue_size() > 0:
            manager.process_load_queue(max_per_frame=20)

        chunk_a = manager.chunks.get((1, 1))
        chunk_b = manager.chunks.get((1, 2))

        assert chunk_a is not None
        assert chunk_b is not None

        # Props should be different (with high probability given random positions)
        # If both have props, they should differ
        if chunk_a.pending_props and chunk_b.pending_props:
            # Compare positions - they should differ since they're in different chunks
            pos_a = [p.get('position', []) for p in chunk_a.pending_props]
            pos_b = [p.get('position', []) for p in chunk_b.pending_props]
            # At least positions should be different (they're in different chunk spaces)
            assert pos_a != pos_b
