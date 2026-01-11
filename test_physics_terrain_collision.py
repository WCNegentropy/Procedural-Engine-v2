"""Test that player physics properly collides with terrain.

This test verifies the fix for the falling-through-terrain bug.
"""
import pytest
import numpy as np
from game_runner import GameRunner, RunnerConfig, HeadlessBackend
from physics import Vec3


def test_player_spawns_on_terrain():
    """Test that player spawns on terrain surface."""
    config = RunnerConfig(
        headless=True,
        chunk_size=64,
        world_seed=42,
    )
    
    backend = HeadlessBackend()
    backend.set_max_frames(1)
    
    runner = GameRunner(config, backend)
    assert runner.initialize(), "Failed to initialize runner"
    
    player = runner.world.get_player()
    assert player is not None, "Player not created"
    
    # Player should spawn above terrain (not at Y=50 initial spawn)
    assert player.position.y > 0, f"Player at invalid Y position: {player.position.y}"
    assert player.position.y < 30, f"Player still at initial spawn height: {player.position.y}"
    
    # Velocity should be reset
    assert abs(player.velocity.y) < 0.1, f"Player has non-zero Y velocity: {player.velocity.y}"
    
    # Player should be marked as grounded
    assert player.grounded, "Player not marked as grounded"
    
    runner.shutdown()


def test_player_stays_on_terrain():
    """Test that player doesn't fall through terrain during simulation."""
    config = RunnerConfig(
        headless=True,
        chunk_size=64,
        world_seed=42,
    )
    
    backend = HeadlessBackend()
    backend.set_max_frames(300)  # 5 seconds
    
    runner = GameRunner(config, backend)
    assert runner.initialize(), "Failed to initialize runner"
    
    player = runner.world.get_player()
    initial_y = player.position.y
    
    # Run simulation for 5 seconds
    runner.run_frames(300)
    
    # Player should not have fallen significantly
    final_y = player.position.y
    assert final_y > -10, f"Player fell through terrain! Y={final_y}"
    
    # Player should be near initial height (may settle slightly)
    height_change = abs(final_y - initial_y)
    assert height_change < 5.0, f"Player height changed too much: {height_change}"
    
    runner.shutdown()


def test_heightfield_is_set():
    """Test that heightfield is properly set in game world."""
    config = RunnerConfig(
        headless=True,
        chunk_size=64,
        world_seed=42,
    )
    
    backend = HeadlessBackend()
    backend.set_max_frames(1)
    
    runner = GameRunner(config, backend)
    assert runner.initialize(), "Failed to initialize runner"
    
    # Check that world has heightfield
    assert runner.world._heightfield is not None, "Heightfield not set in world"
    
    # Check heightfield properties
    hf = runner.world._heightfield
    assert hf.size_x == 64, f"Heightfield wrong X size: {hf.size_x}"
    assert hf.size_z == 64, f"Heightfield wrong Z size: {hf.size_z}"
    
    # Sample heightfield at player position
    player = runner.world.get_player()
    ground_height = hf.sample(player.position.x, player.position.z)
    
    # Player should be just above ground
    assert player.position.y >= ground_height, \
        f"Player below ground! Player Y={player.position.y}, Ground={ground_height}"
    assert player.position.y < ground_height + 5.0, \
        f"Player too far above ground! Player Y={player.position.y}, Ground={ground_height}"
    
    runner.shutdown()


def test_player_falls_and_lands():
    """Test that player falls from height and lands on terrain."""
    config = RunnerConfig(
        headless=True,
        chunk_size=64,
        world_seed=42,
    )
    
    backend = HeadlessBackend()
    backend.set_max_frames(500)  # Give more time
    
    runner = GameRunner(config, backend)
    assert runner.initialize(), "Failed to initialize runner"
    
    player = runner.world.get_player()
    hf = runner.world._heightfield
    
    # Move player high above terrain
    ground_at_spawn = hf.sample(player.position.x, player.position.z)
    player.position = Vec3(player.position.x, ground_at_spawn + 20.0, player.position.z)
    player.velocity = Vec3(0, 0, 0)
    player.grounded = False
    
    initial_y = player.position.y
    
    # Run simulation until player lands and settles
    landed_frames = 0
    for _ in range(500):
        if not runner._frame():
            break
        
        # Check if player has landed and velocity is small
        if player.grounded and abs(player.velocity.y) < 1.0:
            landed_frames += 1
            if landed_frames > 10:  # Wait for stable landing
                break
        else:
            landed_frames = 0
    
    # Player should have fallen
    assert player.position.y < initial_y, "Player didn't fall"
    
    # Player should be on ground
    ground_height = hf.sample(player.position.x, player.position.z)
    assert abs(player.position.y - ground_height - player.radius) < 2.0, \
        f"Player not on ground! Y={player.position.y}, Ground={ground_height}, Diff={player.position.y - ground_height - player.radius}"
    
    # Player should be grounded
    assert player.grounded, f"Player not grounded after landing (velocity.y={player.velocity.y})"
    
    # Velocity should be small (may have small bounce)
    assert abs(player.velocity.y) < 3.0, f"Player velocity too high: velocity.y={player.velocity.y}"
    
    runner.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
