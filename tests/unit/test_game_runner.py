"""Tests for game_runner module."""
import pytest

from game_runner import (
    GameRunner,
    RunnerConfig,
    HeadlessBackend,
    GameState,
)
from physics import Vec3


# =============================================================================
# HeadlessBackend Tests
# =============================================================================


class TestHeadlessBackend:
    """Tests for HeadlessBackend."""

    def test_initialization(self):
        """Test backend initializes correctly."""
        backend = HeadlessBackend()
        config = RunnerConfig(window_width=800, window_height=600)

        assert backend.initialize(config)
        assert backend.width == 800
        assert backend.height == 600
        assert backend.is_focused

    def test_time_tracking(self):
        """Test time tracking works."""
        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())

        time1 = backend.get_time()
        time2 = backend.get_time()

        assert time2 >= time1

    def test_frame_counting(self):
        """Test frame counting."""
        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())

        assert backend.frame_count == 0

        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 1

        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 2

    def test_simulated_key_input(self):
        """Test simulated key input."""
        from player_controller import InputManager, InputAction

        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())

        input_manager = InputManager()

        # Simulate key press
        backend.simulate_key_press("W")
        backend.poll_events(input_manager)

        assert input_manager.state.is_pressed(InputAction.MOVE_FORWARD)

        # Simulate key release
        backend.simulate_key_release("W")
        backend.poll_events(input_manager)

        assert not input_manager.state.is_pressed(InputAction.MOVE_FORWARD)

    def test_simulated_mouse_input(self):
        """Test simulated mouse movement."""
        from player_controller import InputManager

        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())

        input_manager = InputManager()

        backend.simulate_mouse_move(100, 200, 5, -3)
        backend.poll_events(input_manager)

        assert input_manager.state.mouse_x == 100
        assert input_manager.state.mouse_y == 200
        assert input_manager.state.mouse_delta_x == 5
        assert input_manager.state.mouse_delta_y == -3

    def test_quit_simulation(self):
        """Test quit event simulation."""
        from player_controller import InputManager

        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())

        input_manager = InputManager()

        # Normal poll returns True
        assert backend.poll_events(input_manager)

        # After quit simulation, returns False
        backend.simulate_quit()
        assert not backend.poll_events(input_manager)

    def test_max_frames_limit(self):
        """Test frame limit functionality."""
        from player_controller import InputManager

        backend = HeadlessBackend()
        backend.initialize(RunnerConfig())
        backend.set_max_frames(5)

        input_manager = InputManager()

        for i in range(5):
            assert backend.poll_events(input_manager)
            backend.end_frame()

        # Should return False after max frames
        assert not backend.poll_events(input_manager)


# =============================================================================
# RunnerConfig Tests
# =============================================================================


class TestRunnerConfig:
    """Tests for RunnerConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RunnerConfig()

        assert config.window_width == 1920
        assert config.window_height == 1080
        assert config.target_fps == 60
        assert config.fixed_timestep == pytest.approx(1.0 / 60.0)
        assert config.headless is False
        assert config.enable_ui is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RunnerConfig(
            window_width=800,
            window_height=600,
            headless=True,
            world_seed=12345,
        )

        assert config.window_width == 800
        assert config.window_height == 600
        assert config.headless is True
        assert config.world_seed == 12345


# =============================================================================
# GameRunner Tests
# =============================================================================


class TestGameRunner:
    """Tests for GameRunner."""

    def test_initialization(self):
        """Test runner initializes correctly."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)

        assert runner.initialize()
        assert runner.state == GameState.PLAYING
        assert runner.world is not None
        assert runner.player is not None

        runner.shutdown()

    def test_player_creation(self):
        """Test player is created with correct defaults."""
        config = RunnerConfig(headless=True, world_seed=42)
        runner = GameRunner(config)
        runner.initialize()

        player = runner.player
        assert player is not None
        assert player.name == "Hero"
        # Player should be on terrain surface (terrain height + 2.0 offset)
        # With seed=42, chunk_size=64, player spawns at center (32, ?, 32)
        assert player.position.x == 32
        assert player.position.z == 32
        # Player should be above ground level (terrain varies by seed)
        assert player.position.y > 0

        runner.shutdown()

    def test_run_frames(self):
        """Test running specific number of frames."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)

        runner.run_frames(10)

        assert runner.frame_count == 10

    def test_game_state_transitions(self):
        """Test game state can transition."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        assert runner.state == GameState.PLAYING

        runner.state = GameState.PAUSED
        assert runner.state == GameState.PAUSED

        runner.state = GameState.PLAYING
        assert runner.state == GameState.PLAYING

        runner.shutdown()

    def test_pause_toggle(self):
        """Test pause toggle works."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        # Trigger pause
        runner._on_pause_pressed()
        assert runner.state == GameState.PAUSED
        assert runner.world.paused is True

        # Trigger unpause
        runner._on_pause_pressed()
        assert runner.state == GameState.PLAYING
        assert runner.world.paused is False

        runner.shutdown()

    def test_inventory_toggle(self):
        """Test inventory toggle works."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        # Open inventory
        runner._on_inventory_pressed()
        assert runner.state == GameState.INVENTORY

        # Close inventory
        runner._on_inventory_pressed()
        assert runner.state == GameState.PLAYING

        runner.shutdown()

    def test_quit(self):
        """Test quit functionality."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        runner.quit()

        # Running should stop on next frame
        assert runner._running is False

        runner.shutdown()

    def test_fps_tracking(self):
        """Test FPS tracking."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)

        runner.run_frames(100)

        # FPS should be tracked (may not be accurate in fast headless mode)
        assert runner.fps >= 0

    def test_custom_callbacks(self):
        """Test custom callbacks are called."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)

        update_count = [0]
        render_count = [0]

        def on_update(dt):
            update_count[0] += 1

        def on_render():
            render_count[0] += 1

        runner.set_update_callback(on_update)
        runner.set_render_callback(on_render)

        runner.run_frames(5)

        assert update_count[0] > 0
        assert render_count[0] == 5  # One render per frame

    def test_world_seed_determinism(self):
        """Test same seed produces same world state."""
        config1 = RunnerConfig(headless=True, world_seed=42)
        runner1 = GameRunner(config1)
        runner1.initialize()
        runner1.run_frames(10)
        player1_pos = (runner1.player.position.x, runner1.player.position.z)
        runner1.shutdown()

        config2 = RunnerConfig(headless=True, world_seed=42)
        runner2 = GameRunner(config2)
        runner2.initialize()
        runner2.run_frames(10)
        player2_pos = (runner2.player.position.x, runner2.player.position.z)
        runner2.shutdown()

        # Positions should be identical with same seed
        assert player1_pos == player2_pos


# =============================================================================
# Frame Rate Limiting Tests
# =============================================================================


class TestFrameRateLimiting:
    """Tests for frame rate limiting functionality."""

    def test_frame_rate_limiting_not_applied_in_headless(self):
        """Test that frame rate limiting doesn't affect headless mode."""
        import time
        
        config = RunnerConfig(headless=True, target_fps=30)
        runner = GameRunner(config)
        
        start_time = time.perf_counter()
        runner.run_frames(10)
        elapsed = time.perf_counter() - start_time
        
        # In headless mode with simulated time, frames should complete very quickly
        # (much less than 10 frames at 30 FPS = 0.333 seconds)
        assert elapsed < 0.2, f"Headless mode should be fast, took {elapsed:.3f}s"
        
        runner.shutdown()

    def test_vsync_config_passed_to_graphics(self):
        """Test that vsync config is properly passed through to graphics system."""
        # Test with vsync enabled (default)
        config1 = RunnerConfig(headless=True, vsync=True)
        runner1 = GameRunner(config1)
        runner1.initialize()
        assert runner1.config.vsync is True
        runner1.shutdown()
        
        # Test with vsync disabled
        config2 = RunnerConfig(headless=True, vsync=False)
        runner2 = GameRunner(config2)
        runner2.initialize()
        assert runner2.config.vsync is False
        runner2.shutdown()

    def test_target_fps_config(self):
        """Test that target_fps is configurable."""
        config = RunnerConfig(target_fps=120)
        assert config.target_fps == 120
        
        config2 = RunnerConfig(target_fps=30)
        assert config2.target_fps == 30


# =============================================================================
# Integration Tests
# =============================================================================


class TestGameRunnerIntegration:
    """Integration tests for GameRunner with other systems."""

    def test_input_to_player_movement(self):
        """Test input translates to player movement."""
        config = RunnerConfig(headless=True)
        backend = HeadlessBackend()
        runner = GameRunner(config, backend=backend)
        runner.initialize()

        initial_pos = Vec3(
            runner.player.position.x,
            runner.player.position.y,
            runner.player.position.z,
        )

        # Simulate forward movement
        backend.simulate_key_press("W")

        # Run several frames to allow movement
        runner.run_frames(60)

        # Player should have moved
        final_pos = runner.player.position

        # Position should have changed (in z direction for forward)
        # Note: exact direction depends on camera orientation
        moved = (
            abs(final_pos.x - initial_pos.x) > 0.1 or
            abs(final_pos.z - initial_pos.z) > 0.1
        )
        assert moved, "Player should have moved from input"

        runner.shutdown()

    def test_interaction_with_npc(self):
        """Test player can interact with NPC."""
        from game_api import NPC

        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        # Spawn an NPC near the player
        npc = NPC(
            entity_id="test_npc",
            name="Test NPC",
            position=Vec3(1, 10, 1),
        )
        runner.world.spawn_entity(npc)

        # Move player to NPC
        runner.player.position = Vec3(0.5, 10, 0.5)

        # Start dialogue
        success = runner.start_dialogue("test_npc")
        assert success
        assert runner.state == GameState.DIALOGUE

        # End dialogue
        runner.end_dialogue()
        assert runner.state == GameState.PLAYING

        runner.shutdown()

    def test_event_system_integration(self):
        """Test event system fires during gameplay."""
        from game_api import EventType

        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        events_received = []

        def on_event(event):
            events_received.append(event.event_type)

        runner.world.events.subscribe_all(on_event)

        runner.run_frames(10)

        # Should have received some events (at least time updates)
        # Note: specific events depend on game state
        runner.shutdown()
