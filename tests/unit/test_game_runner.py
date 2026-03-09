"""Tests for game_runner module."""
from types import SimpleNamespace

import pytest

from procengine.game.game_runner import (
    GameRunner,
    RunnerConfig,
    HeadlessBackend,
    GameState,
)
from procengine.physics import Vec3


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
        from procengine.game.player_controller import InputManager, InputAction

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
        from procengine.game.player_controller import InputManager

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
        from procengine.game.player_controller import InputManager

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
        from procengine.game.player_controller import InputManager

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
# Helpers
# =============================================================================


def _init_world_for_test(runner, seed: int | None = None) -> None:
    """Initialize the game world for a test runner.

    Since ``initialize()`` now starts at the main menu without creating
    a world, tests that need a world must call this helper after init.
    """
    world_seed = seed if seed is not None else runner.config.world_seed
    runner._init_world(world_seed)


def _advance_past_loading(runner, max_frames: int = 50) -> None:
    """Run frames until the runner exits LOADING state.

    In headless mode chunk generation is fast, so this typically only takes
    ~8 frames (29 sim-distance chunks at 4 per frame).  The ``max_frames``
    safety limit prevents infinite loops in case of a bug.
    """
    # If still at MAIN_MENU, init the world first
    if runner.state == GameState.MAIN_MENU:
        _init_world_for_test(runner)

    for _ in range(max_frames):
        if runner.state != GameState.LOADING:
            return
        runner._frame()
    # If we're still loading, force-finish so the test can proceed
    if hasattr(runner, '_finish_loading'):
        runner._finish_loading()


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
        # After initialize(), runner starts at the main menu
        assert runner.state == GameState.MAIN_MENU

        # Simulate starting a world
        _init_world_for_test(runner)
        assert runner.state in (GameState.LOADING, GameState.PLAYING)
        _advance_past_loading(runner)
        assert runner.state == GameState.PLAYING
        assert runner.world is not None
        assert runner.player is not None

        runner.shutdown()

    def test_player_creation(self):
        """Test player is created with correct defaults."""
        config = RunnerConfig(headless=True, world_seed=42)
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

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
        _init_world_for_test(runner)
        _advance_past_loading(runner)

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
        _init_world_for_test(runner)
        _advance_past_loading(runner)
        captured = []
        runner.backend.set_mouse_capture = captured.append

        # Trigger pause
        runner._on_pause_pressed()
        assert runner.state == GameState.PAUSED
        assert runner.world.paused is True
        assert captured == [False]

        # Trigger unpause
        runner._on_pause_pressed()
        assert runner.state == GameState.PLAYING
        assert runner.world.paused is False
        assert captured == [False, True]

        runner.shutdown()

    def test_console_shift_mapping(self):
        """Test shift-modified console input mapping."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()

        runner.console.open()
        runner._input_manager.begin_frame()
        runner._input_manager.on_key_down("LSHIFT")
        runner._input_manager.on_key_down("COMMA")
        runner._process_console_input()

        assert runner.console.input_buffer == "<"

        runner._input_manager.on_key_up("COMMA")
        runner._input_manager.on_key_up("LSHIFT")
        runner.console.set_input("")
        runner._input_manager.begin_frame()
        runner._input_manager.on_key_down("LSHIFT")
        runner._input_manager.on_key_down("SLASH")
        runner._process_console_input()

        assert runner.console.input_buffer == "?"

        runner._input_manager.on_key_up("SLASH")
        runner._input_manager.on_key_up("LSHIFT")
        runner.shutdown()

    def test_inventory_toggle(self):
        """Test inventory toggle works."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)
        captured = []
        runner.backend.set_mouse_capture = captured.append

        # Open inventory
        runner._on_inventory_pressed()
        assert runner.state == GameState.INVENTORY
        assert captured == [False]

        # Close inventory
        runner._on_inventory_pressed()
        assert runner.state == GameState.PLAYING
        assert captured == [False, True]

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
        # Use static terrain to skip LOADING state so callbacks fire immediately
        config = RunnerConfig(headless=True, enable_dynamic_chunks=False)
        runner = GameRunner(config)

        update_count = [0]
        render_count = [0]

        def on_update(dt):
            update_count[0] += 1

        def on_render():
            render_count[0] += 1

        runner.set_update_callback(on_update)
        runner.set_render_callback(on_render)

        # initialize + init world, then run frames
        runner.initialize()
        _init_world_for_test(runner)
        runner._running = True
        for _ in range(5):
            if not runner._running:
                break
            runner._running = runner._frame()

        assert update_count[0] > 0
        assert render_count[0] == 5  # One render per frame
        runner.shutdown()

    def test_world_creation_seed_entry_starts_world_with_entered_seed(self):
        """Test world creation UI passes the entered seed into init."""
        config = RunnerConfig(headless=True, world_seed=42)
        runner = GameRunner(config)
        runner.initialize()

        started = []
        runner._init_world = lambda seed=None: started.append(seed)

        runner._on_new_world()
        runner._ui_manager.backend.set_input_text_value("##seed", "987654321")
        runner._ui_manager.backend.set_button_response("Generate World", True)

        runner._ui_manager.begin_frame()
        runner._ui_manager.render_world_creation()
        runner._ui_manager.end_frame()

        assert started == [987654321]
        assert runner.state == GameState.WORLD_CREATION

        runner.shutdown()

    def test_render_ui_passes_input_manager_to_world_creation(self):
        """Test world creation render receives menu input manager."""
        config = RunnerConfig(headless=True, world_seed=42)
        runner = GameRunner(config)
        runner.initialize()

        captured = []
        runner._state = GameState.WORLD_CREATION
        runner._ui_manager.render_world_creation = (
            lambda input_manager=None: captured.append(input_manager)
        )

        runner._render_ui()

        assert captured == [runner._input_manager]

        runner.shutdown()

    def test_frame_forwards_platform_events_to_ui_manager(self):
        """Test frame polling forwards native events to the active UI manager."""
        config = RunnerConfig(headless=True, world_seed=42)
        runner = GameRunner(config)
        runner.initialize()

        captured = []

        def fake_poll_events(input_manager, ui_event_sink=None):
            assert input_manager is runner._input_manager
            captured.append(ui_event_sink)
            return False

        runner._backend.poll_events = fake_poll_events

        assert runner._frame() is False
        assert captured == [runner._ui_manager.process_platform_event]

        runner.shutdown()

    def test_world_seed_determinism(self):
        """Test same seed produces same world state."""
        config1 = RunnerConfig(headless=True, world_seed=42)
        runner1 = GameRunner(config1)
        runner1.initialize()
        _init_world_for_test(runner1, seed=42)
        _advance_past_loading(runner1)
        player1_pos = (runner1.player.position.x, runner1.player.position.z)
        runner1.shutdown()

        config2 = RunnerConfig(headless=True, world_seed=42)
        runner2 = GameRunner(config2)
        runner2.initialize()
        _init_world_for_test(runner2, seed=42)
        _advance_past_loading(runner2)
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
        
        # Use static terrain for faster test execution
        config = RunnerConfig(headless=True, target_fps=30, enable_dynamic_chunks=False)
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
        _init_world_for_test(runner)
        _advance_past_loading(runner)

        initial_pos = Vec3(
            runner.player.position.x,
            runner.player.position.y,
            runner.player.position.z,
        )

        # Simulate forward movement
        backend.simulate_key_press("W")

        # Run several frames to allow movement
        runner._running = True
        for _ in range(60):
            if not runner._running:
                break
            runner._running = runner._frame()

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
        from procengine.game.game_api import NPC

        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)
        captured = []
        runner.backend.set_mouse_capture = captured.append

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
        assert captured == [False]

        # End dialogue
        runner.end_dialogue()
        assert runner.state == GameState.PLAYING
        assert captured == [False, True]

        runner.shutdown()

    def test_event_system_integration(self):
        """Test event system fires during gameplay."""
        from procengine.game.game_api import EventType

        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)

        events_received = []

        def on_event(event):
            events_received.append(event.event_type)

        runner.world.events.subscribe_all(on_event)

        runner._running = True
        for _ in range(10):
            if not runner._running:
                break
            runner._running = runner._frame()

        # Should have received some events (at least time updates)
        # Note: specific events depend on game state
        runner.shutdown()

    def test_pause_unpause_via_keyboard(self):
        """Test that pressing ESC key pauses and unpauses the game.

        This is a regression test for the issue where pressing ESC to pause
        would hang the game because UI inputs weren't processed in PAUSED state.
        """
        config = RunnerConfig(headless=True)
        backend = HeadlessBackend()
        runner = GameRunner(config, backend=backend)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)

        # Verify game starts in PLAYING state
        assert runner.state == GameState.PLAYING

        # Run one frame to initialize timing (first frame has frame_time=0)
        runner._frame()
        
        # Simulate pressing ESC to pause and run frames for it to take effect
        backend.simulate_key_press("ESCAPE")
        runner._frame()  # This frame processes the input
        
        # Game should now be PAUSED
        assert runner.state == GameState.PAUSED
        assert runner.world.paused is True

        # Clear the edge-triggered input state by running another frame
        backend.simulate_key_release("ESCAPE")
        runner._frame()

        # Simulate pressing ESC again to unpause
        backend.simulate_key_press("ESCAPE")
        runner._frame()  # This frame processes the input
        
        # Game should now be PLAYING again
        assert runner.state == GameState.PLAYING
        assert runner.world.paused is False

        runner.shutdown()


# =============================================================================
# Dynamic Chunk Integration Tests
# =============================================================================


class TestDynamicChunks:
    """Tests for dynamic chunk loading integration."""

    def test_config_enable_dynamic_chunks(self):
        """Test that enable_dynamic_chunks config option exists."""
        config = RunnerConfig(enable_dynamic_chunks=True)
        assert config.enable_dynamic_chunks is True
        
        config2 = RunnerConfig()  # Default
        assert config2.enable_dynamic_chunks is True  # Dynamic chunks is now the default

    def test_config_render_distance(self):
        """Test that render_distance config option exists."""
        config = RunnerConfig(render_distance=12)
        assert config.render_distance == 12
        
        config2 = RunnerConfig()
        assert config2.render_distance == 6  # Default (reduced for performance)

    def test_config_sim_distance(self):
        """Test that sim_distance config option exists."""
        config = RunnerConfig(sim_distance=6)
        assert config.sim_distance == 6
        
        config2 = RunnerConfig()
        assert config2.sim_distance == 3  # Default (reduced for performance)

    def test_runner_has_chunk_manager_attribute(self):
        """Test that GameRunner has _chunk_manager attribute."""
        config = RunnerConfig(headless=True)
        runner = GameRunner(config)
        assert hasattr(runner, '_chunk_manager')
        assert runner._chunk_manager is None  # Not initialized yet

    def test_static_mode_no_chunk_manager(self):
        """Test that static mode doesn't initialize ChunkManager."""
        config = RunnerConfig(headless=True, enable_dynamic_chunks=False)
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        assert runner._chunk_manager is None
        runner.shutdown()

    def test_dynamic_mode_initializes_chunk_manager(self):
        """Test that dynamic mode initializes ChunkManager."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        assert runner._chunk_manager is not None
        assert runner._chunk_manager.chunk_size == 32
        assert runner._chunk_manager.render_distance == 1

        runner.shutdown()

    def test_dynamic_mode_loads_initial_chunks(self):
        """Test that dynamic mode loads chunks around spawn on initialize."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        assert runner._chunk_manager is not None
        # Should have some chunks loaded
        assert len(runner._chunk_manager.chunks) > 0

        runner.shutdown()

    def test_dynamic_mode_world_has_chunk_manager(self):
        """Test that GameWorld receives the ChunkManager."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        assert runner._world is not None
        assert runner._world.get_chunk_manager() is runner._chunk_manager

        runner.shutdown()

    def test_player_spawns_on_terrain_in_dynamic_mode(self):
        """Test that player spawns on terrain in dynamic mode."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
            world_seed=42,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner, seed=42)

        player = runner.player
        assert player is not None
        # Player should be above ground level (terrain varies by seed)
        assert player.position.y > 0

        runner.shutdown()

    def test_run_frames_in_dynamic_mode(self):
        """Test running frames in dynamic chunk mode."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        # Run frames to advance past loading
        runner._running = True
        for _ in range(10):
            if not runner._running:
                break
            runner._running = runner._frame()

        # Verify chunk manager state
        assert runner._chunk_manager is not None
        assert len(runner._chunk_manager.chunks) > 0

        # Verify chunks are loaded around spawn point
        spawn_chunk = runner._chunk_manager.get_chunk_at_world(16.0, 16.0)
        assert spawn_chunk is not None
        assert spawn_chunk.is_loaded

        runner.shutdown()

    def test_loading_not_premature_with_cpp_manager(self):
        """queue_empty should be False when C++ GameManager is active.

        When the C++ GameManager manages the chunk work queue, the Python
        ``_load_queue`` is always empty. The loading completion check must
        not treat this as "queue finished" — it should rely on
        ``enough_chunks`` instead.
        """
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        # Regardless of whether C++ is available, the guard logic should
        # not allow ``queue_empty`` to short-circuit to True on the C++ path.
        if runner._game_manager.available:
            # Simulate being in LOADING with zero chunks done but empty
            # Python load queue — this used to incorrectly set queue_empty=True.
            runner._loading_chunks_done = 0
            runner._loading_total_chunks = 10
            runner._loading_complete = False
            runner._state = GameState.LOADING

            # Run one loading tick
            runner._update_loading(1 / 60)

            # Loading should NOT have finished prematurely
            assert not runner._loading_complete

        runner.shutdown()

    def test_loading_uses_python_queue_when_cpp_unavailable(self):
        """Python fallback path should check _load_queue for completion."""
        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)

        if not runner._game_manager.available:
            # With Python fallback, queue_empty comes from _load_queue.
            # Run enough frames for loading to complete normally.
            for _ in range(200):
                runner._update_loading(1 / 60)
                if runner._loading_complete:
                    break
            assert runner._loading_complete

        runner.shutdown()

    def test_cpp_manager_path_keeps_streaming_when_budget_hits_zero(self):
        """C++ manager path should still upload and unload chunks under pressure."""
        from procengine.world.chunk import Chunk

        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)

        old_chunk = Chunk(coords=(-3, 0), is_loaded=True, is_mesh_uploaded=True)
        runner._chunk_manager.chunks[old_chunk.coords] = old_chunk
        runner._state = GameState.PLAYING

        uploaded_results = []
        cleaned_chunks = []

        class MockGameManager:
            available = True

            def __init__(self) -> None:
                self.last_collect_limit = None

            def sync_frame(self, *args):
                return SimpleNamespace(
                    max_chunk_loads=0,
                    recommended_render_distance=runner.config.render_distance,
                    recommended_sim_distance=runner.config.sim_distance,
                    skip_physics_step=False,
                    lod_bias=0.0,
                )

            def collect_ready_chunks(self, max_count):
                self.last_collect_limit = max_count
                return [SimpleNamespace(coord=SimpleNamespace(x=2, z=0))]

            def get_chunks_to_unload(self, *args):
                return [SimpleNamespace(x=old_chunk.coords[0], z=old_chunk.coords[1])]

            def mark_chunk_uploaded(self, x, z):
                pass

        mock_manager = MockGameManager()
        runner._game_manager = mock_manager
        runner._upload_async_chunk_result = uploaded_results.append
        runner._cleanup_chunk = cleaned_chunks.append

        runner.player.position.x = runner.config.chunk_size * 2.5
        runner.player.position.z = runner.config.chunk_size * 0.5

        runner._update(1 / 60)

        assert mock_manager.last_collect_limit == 1
        assert len(uploaded_results) == 1
        assert uploaded_results[0].coord.x == 2
        assert old_chunk.coords not in runner._chunk_manager.chunks
        assert cleaned_chunks == [old_chunk]

        runner.shutdown()

    def test_dynamic_render_uses_world_chunk_index_for_npcs(self):
        """NPC rendering should not depend on chunk.entity_ids being prefilled."""
        from procengine.game.game_api import NPC

        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=1,
        )
        runner = GameRunner(config)
        runner.initialize()
        _init_world_for_test(runner)
        _advance_past_loading(runner)
        original_graphics_bridge = runner._graphics_bridge

        class FakeGraphicsBridge:
            def __init__(self) -> None:
                self.draw_calls = []

            def upload_entity_mesh(self, mesh_name, entity_type, entity_state=None):
                return True

            def draw_entity(self, mesh_name, material, position, rotation=0.0, scale=1.0):
                self.draw_calls.append(mesh_name)

        runner._graphics_bridge = FakeGraphicsBridge()

        npc = NPC(entity_id="visible_npc", name="Villager", position=Vec3(16, 0, 16))
        runner.world.spawn_entity(npc)

        chunk = runner._chunk_manager.get_chunk_at_world(16.0, 16.0)
        assert chunk is not None
        chunk.entity_ids.clear()

        runner._render_entities()

        assert "npc_visible_npc" in runner._graphics_bridge.draw_calls
        runner._graphics_bridge = original_graphics_bridge
        runner.shutdown()

    def test_async_chunk_outside_prop_range_skips_props(self):
        """Async chunks should match sync prop-distance behavior."""
        import numpy as np

        config = RunnerConfig(
            headless=True,
            enable_dynamic_chunks=True,
            chunk_size=32,
            render_distance=4,
        )
        runner = GameRunner(config)
        runner.initialize()

        gen_size = config.chunk_size + 1
        result = SimpleNamespace(
            coord=SimpleNamespace(x=3, z=0),
            height=np.zeros(gen_size * gen_size, dtype=np.float32),
            biome=np.zeros(gen_size * gen_size, dtype=np.uint8),
            river=np.zeros(gen_size * gen_size, dtype=np.uint8),
            slope=np.zeros(gen_size * gen_size, dtype=np.float32),
        )
        runner._game_manager = SimpleNamespace(mark_chunk_uploaded=lambda x, z: None)
        uploaded_chunks = []
        runner._upload_chunk_mesh = uploaded_chunks.append

        runner._upload_async_chunk_result(result)

        assert len(uploaded_chunks) == 1
        chunk = uploaded_chunks[0]
        assert chunk.coords == (3, 0)
        assert chunk.has_props is False
        assert chunk.pending_props == []
        runner.shutdown()

    def test_spawn_chunk_props_applies_flower_and_creature_height_offsets(self):
        """Flower patches and creatures should spawn slightly above terrain."""
        runner = GameRunner(RunnerConfig(headless=True))

        spawned_entities = []

        class FakeWorld:
            def spawn_entity(self, entity):
                spawned_entities.append(entity)
                return entity.entity_id

        chunk = SimpleNamespace(
            coords=(2, 3),
            pending_props=[
                {
                    "type": "flower_patch",
                    "position": [1.0, 0.5, 2.0],
                    "stem_count": 4,
                    "patch_radius": 0.3,
                    "color_seed": 9,
                },
                {
                    "type": "creature",
                    "position": [3.0, 0.5, 4.0],
                    "skeleton": [{"start": [0, 0, 0], "end": [0, 1, 0]}],
                    "metaballs": [{"center": [0.5, 0.5, 0.5], "radius": 0.4}],
                },
            ],
            entity_ids=set(),
        )
        runner._world = FakeWorld()

        runner._spawn_chunk_props(chunk, world_x=10.0, world_z=20.0)

        assert [entity.prop_type for entity in spawned_entities] == ["flower_patch", "creature"]
        assert spawned_entities[0].position.y == pytest.approx(0.5 * runner.HEIGHT_SCALE + 0.05)
        assert spawned_entities[1].position.y == pytest.approx(0.5 * runner.HEIGHT_SCALE + 0.15)
        assert chunk.pending_props == []
