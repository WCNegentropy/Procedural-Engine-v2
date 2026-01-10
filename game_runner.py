"""Game runner with window management and main loop.

This module provides the main game loop that orchestrates:
- Window creation and management (via backend abstraction)
- Input event processing
- Game state updates
- Rendering (when graphics backend available)
- UI rendering via Dear ImGui (when available)

The runner supports multiple backends:
- SDL2: Full windowed mode with input and rendering
- Headless: No window, for testing and CI environments

Usage:
    from game_runner import GameRunner, RunnerConfig

    config = RunnerConfig(
        window_title="Procedural Engine",
        window_width=1920,
        window_height=1080,
        headless=False,
    )
    runner = GameRunner(config)
    runner.run()
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from physics import Vec3, HeightField2D
from game_api import GameWorld, GameConfig, Player, NPC, Event, EventType
from player_controller import (
    InputManager,
    InputAction,
    InputState,
    PlayerController,
    CameraController,
    Camera,
)

if TYPE_CHECKING:
    from ui_system import UIManager

__all__ = [
    "RunnerConfig",
    "GameRunner",
    "WindowBackend",
    "HeadlessBackend",
]


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class RunnerConfig:
    """Configuration for the game runner."""

    # Window settings
    window_title: str = "Procedural Engine v2"
    window_width: int = 1920
    window_height: int = 1080
    fullscreen: bool = False
    vsync: bool = True

    # Game settings
    target_fps: int = 60
    fixed_timestep: float = 1.0 / 60.0
    max_frame_skip: int = 5

    # Mode settings
    headless: bool = False
    enable_ui: bool = True
    enable_debug: bool = False

    # World settings
    world_seed: int = 42
    world_size: int = 10
    chunk_size: int = 64


# =============================================================================
# Window Backend Abstraction
# =============================================================================


class WindowBackend(ABC):
    """Abstract window backend interface.

    Backends handle window creation, input events, and frame presentation.
    This abstraction allows the game to run with different windowing systems
    (SDL2, GLFW) or in headless mode for testing.
    """

    @abstractmethod
    def initialize(self, config: RunnerConfig) -> bool:
        """Initialize the window backend."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown the window backend."""
        pass

    @abstractmethod
    def poll_events(self, input_manager: InputManager) -> bool:
        """Poll window events and update input state.

        Returns False if the window should close.
        """
        pass

    @abstractmethod
    def begin_frame(self) -> None:
        """Begin a new frame (clear buffers, etc.)."""
        pass

    @abstractmethod
    def end_frame(self) -> None:
        """End frame and present (swap buffers)."""
        pass

    @abstractmethod
    def get_time(self) -> float:
        """Get current time in seconds."""
        pass

    @property
    @abstractmethod
    def width(self) -> int:
        """Window width."""
        pass

    @property
    @abstractmethod
    def height(self) -> int:
        """Window height."""
        pass

    @property
    @abstractmethod
    def is_focused(self) -> bool:
        """Whether window has focus."""
        pass


class HeadlessBackend(WindowBackend):
    """Headless backend for testing without a window.

    Simulates window behavior for automated testing and CI environments.
    Provides simulated frame timing to ensure physics updates execute.
    """

    def __init__(self, simulated_frame_time: float = 1.0 / 60.0) -> None:
        """Initialize headless backend.

        Parameters
        ----------
        simulated_frame_time:
            Simulated time per frame in seconds. Defaults to 1/60 (60 FPS).
            This ensures physics updates execute properly in headless mode.
        """
        self._width: int = 1920
        self._height: int = 1080
        self._start_time: float = 0.0
        self._simulated_time: float = 0.0
        self._simulated_frame_time: float = simulated_frame_time
        self._running: bool = True
        self._frame_count: int = 0
        self._max_frames: int = 0  # 0 = unlimited
        self._simulated_inputs: List[Dict] = []

    def initialize(self, config: RunnerConfig) -> bool:
        """Initialize headless backend."""
        self._width = config.window_width
        self._height = config.window_height
        self._start_time = time.perf_counter()
        self._simulated_time = 0.0
        self._running = True
        return True

    def shutdown(self) -> None:
        """Shutdown headless backend."""
        self._running = False

    def poll_events(self, input_manager: InputManager) -> bool:
        """Poll simulated events."""
        input_manager.begin_frame()

        # Process any simulated inputs
        for sim_input in self._simulated_inputs:
            if sim_input["type"] == "key_down":
                input_manager.on_key_down(sim_input["key"])
            elif sim_input["type"] == "key_up":
                input_manager.on_key_up(sim_input["key"])
            elif sim_input["type"] == "mouse_move":
                input_manager.on_mouse_move(
                    sim_input["x"],
                    sim_input["y"],
                    sim_input["dx"],
                    sim_input["dy"],
                )
            elif sim_input["type"] == "quit":
                self._running = False

        self._simulated_inputs.clear()

        # Check frame limit
        if self._max_frames > 0 and self._frame_count >= self._max_frames:
            return False

        return self._running

    def begin_frame(self) -> None:
        """Begin frame (no-op in headless)."""
        pass

    def end_frame(self) -> None:
        """End frame (increment counter and advance simulated time)."""
        self._frame_count += 1
        self._simulated_time += self._simulated_frame_time

    def get_time(self) -> float:
        """Get elapsed simulated time.

        Uses simulated time (not real time) to ensure consistent frame timing
        in headless mode, which allows physics updates to execute properly.
        """
        return self._simulated_time

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def is_focused(self) -> bool:
        return True

    # Headless-specific methods for testing

    def simulate_key_press(self, key: str) -> None:
        """Simulate a key press for testing."""
        self._simulated_inputs.append({"type": "key_down", "key": key})

    def simulate_key_release(self, key: str) -> None:
        """Simulate a key release for testing."""
        self._simulated_inputs.append({"type": "key_up", "key": key})

    def simulate_mouse_move(self, x: float, y: float, dx: float, dy: float) -> None:
        """Simulate mouse movement for testing."""
        self._simulated_inputs.append({
            "type": "mouse_move",
            "x": x,
            "y": y,
            "dx": dx,
            "dy": dy,
        })

    def simulate_quit(self) -> None:
        """Simulate quit event."""
        self._simulated_inputs.append({"type": "quit"})

    def set_max_frames(self, max_frames: int) -> None:
        """Set maximum frames to run (0 = unlimited)."""
        self._max_frames = max_frames

    @property
    def frame_count(self) -> int:
        """Get current frame count."""
        return self._frame_count


# =============================================================================
# SDL2 Backend (Optional)
# =============================================================================


def create_sdl2_backend() -> Optional[WindowBackend]:
    """Try to create an SDL2 backend if available."""
    try:
        # Import is inside function to avoid hard dependency
        import sdl2
        import sdl2.ext

        class SDL2Backend(WindowBackend):
            """SDL2-based window backend."""

            def __init__(self) -> None:
                self._window = None
                self._renderer = None
                self._width: int = 1920
                self._height: int = 1080
                self._focused: bool = True
                self._start_time: float = 0.0

                # Key mapping from SDL2 scancodes to our key names
                self._key_map: Dict[int, str] = {
                    sdl2.SDL_SCANCODE_W: "W",
                    sdl2.SDL_SCANCODE_A: "A",
                    sdl2.SDL_SCANCODE_S: "S",
                    sdl2.SDL_SCANCODE_D: "D",
                    sdl2.SDL_SCANCODE_SPACE: "SPACE",
                    sdl2.SDL_SCANCODE_LSHIFT: "LSHIFT",
                    sdl2.SDL_SCANCODE_RSHIFT: "RSHIFT",
                    sdl2.SDL_SCANCODE_LCTRL: "LCTRL",
                    sdl2.SDL_SCANCODE_RCTRL: "RCTRL",
                    sdl2.SDL_SCANCODE_LALT: "LALT",
                    sdl2.SDL_SCANCODE_RALT: "RALT",
                    sdl2.SDL_SCANCODE_E: "E",
                    sdl2.SDL_SCANCODE_I: "I",
                    sdl2.SDL_SCANCODE_J: "J",
                    sdl2.SDL_SCANCODE_M: "M",
                    sdl2.SDL_SCANCODE_ESCAPE: "ESCAPE",
                    sdl2.SDL_SCANCODE_GRAVE: "GRAVE",
                    sdl2.SDL_SCANCODE_RETURN: "RETURN",
                    sdl2.SDL_SCANCODE_UP: "UP",
                    sdl2.SDL_SCANCODE_DOWN: "DOWN",
                    sdl2.SDL_SCANCODE_LEFT: "LEFT",
                    sdl2.SDL_SCANCODE_RIGHT: "RIGHT",
                    sdl2.SDL_SCANCODE_1: "1",
                    sdl2.SDL_SCANCODE_2: "2",
                    sdl2.SDL_SCANCODE_3: "3",
                    sdl2.SDL_SCANCODE_4: "4",
                    sdl2.SDL_SCANCODE_F3: "F3",
                    sdl2.SDL_SCANCODE_F4: "F4",
                }

            def initialize(self, config: RunnerConfig) -> bool:
                if sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_EVENTS) < 0:
                    return False

                flags = sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE
                if config.fullscreen:
                    flags |= sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP

                self._window = sdl2.SDL_CreateWindow(
                    config.window_title.encode(),
                    sdl2.SDL_WINDOWPOS_CENTERED,
                    sdl2.SDL_WINDOWPOS_CENTERED,
                    config.window_width,
                    config.window_height,
                    flags,
                )

                if not self._window:
                    sdl2.SDL_Quit()
                    return False

                self._width = config.window_width
                self._height = config.window_height
                self._start_time = time.perf_counter()

                # Capture mouse for FPS-style controls
                sdl2.SDL_SetRelativeMouseMode(sdl2.SDL_TRUE)

                return True

            def shutdown(self) -> None:
                if self._window:
                    sdl2.SDL_DestroyWindow(self._window)
                sdl2.SDL_Quit()

            def poll_events(self, input_manager: InputManager) -> bool:
                input_manager.begin_frame()

                event = sdl2.SDL_Event()
                while sdl2.SDL_PollEvent(event):
                    if event.type == sdl2.SDL_QUIT:
                        return False

                    elif event.type == sdl2.SDL_KEYDOWN:
                        key = self._key_map.get(event.key.keysym.scancode)
                        if key:
                            input_manager.on_key_down(key)

                    elif event.type == sdl2.SDL_KEYUP:
                        key = self._key_map.get(event.key.keysym.scancode)
                        if key:
                            input_manager.on_key_up(key)

                    elif event.type == sdl2.SDL_MOUSEMOTION:
                        input_manager.on_mouse_move(
                            float(event.motion.x),
                            float(event.motion.y),
                            float(event.motion.xrel),
                            float(event.motion.yrel),
                        )

                    elif event.type == sdl2.SDL_MOUSEBUTTONDOWN:
                        input_manager.on_mouse_button(event.button.button - 1, True)

                    elif event.type == sdl2.SDL_MOUSEBUTTONUP:
                        input_manager.on_mouse_button(event.button.button - 1, False)

                    elif event.type == sdl2.SDL_WINDOWEVENT:
                        if event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_GAINED:
                            self._focused = True
                        elif event.window.event == sdl2.SDL_WINDOWEVENT_FOCUS_LOST:
                            self._focused = False
                        elif event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                            self._width = event.window.data1
                            self._height = event.window.data2

                return True

            def begin_frame(self) -> None:
                pass  # Graphics system handles this

            def end_frame(self) -> None:
                pass  # Graphics system handles presentation

            def get_time(self) -> float:
                return time.perf_counter() - self._start_time

            @property
            def width(self) -> int:
                return self._width

            @property
            def height(self) -> int:
                return self._height

            @property
            def is_focused(self) -> bool:
                return self._focused

        return SDL2Backend()

    except ImportError:
        return None


# =============================================================================
# Game Runner
# =============================================================================


class GameState(Enum):
    """Current state of the game."""

    LOADING = auto()
    PLAYING = auto()
    PAUSED = auto()
    DIALOGUE = auto()
    INVENTORY = auto()
    MENU = auto()


class GameRunner:
    """Main game runner that orchestrates the game loop.

    The runner manages:
    - Window backend (SDL2, headless, etc.)
    - Game world and player
    - Input processing
    - Game state updates
    - Rendering (when available)
    - UI rendering (when available)
    """

    def __init__(
        self,
        config: Optional[RunnerConfig] = None,
        backend: Optional[WindowBackend] = None,
    ) -> None:
        """Initialize game runner.

        Parameters
        ----------
        config:
            Runner configuration. Uses defaults if not provided.
        backend:
            Window backend. Auto-selects if not provided.
        """
        self.config = config or RunnerConfig()

        # Select backend
        if backend:
            self._backend = backend
        elif self.config.headless:
            self._backend = HeadlessBackend()
        else:
            # Try SDL2, fall back to headless
            self._backend = create_sdl2_backend() or HeadlessBackend()

        # Game state
        self._state = GameState.LOADING
        self._running = False

        # Core systems
        self._world: Optional[GameWorld] = None
        self._player_controller: Optional[PlayerController] = None
        self._input_manager: Optional[InputManager] = None

        # UI system (lazily loaded)
        self._ui_manager: Optional["UIManager"] = None

        # Timing
        self._last_time: float = 0.0
        self._accumulator: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._fps_update_time: float = 0.0
        self._fps_frame_count: int = 0

        # Callbacks
        self._on_update: Optional[Callable[[float], None]] = None
        self._on_render: Optional[Callable[[], None]] = None
        self._on_ui: Optional[Callable[[], None]] = None

    def initialize(self) -> bool:
        """Initialize all game systems.

        Returns True on success, False on failure.
        """
        # Initialize window backend
        if not self._backend.initialize(self.config):
            print("Failed to initialize window backend")
            return False

        # Create input manager and player controller
        self._input_manager = InputManager()
        self._player_controller = PlayerController(
            input_manager=self._input_manager,
            camera_controller=CameraController(),
        )

        # Set up UI callbacks
        self._player_controller.on_pause_toggle = self._on_pause_pressed
        self._player_controller.on_inventory_toggle = self._on_inventory_pressed
        self._player_controller.on_dialogue_advance = self._on_dialogue_advance
        self._player_controller.on_dialogue_option = self._on_dialogue_option

        # Create game world
        world_config = GameConfig(
            seed=self.config.world_seed,
            world_size=self.config.world_size,
            chunk_size=self.config.chunk_size,
        )
        self._world = GameWorld(world_config)

        # Create player
        self._world.create_player(name="Hero", position=Vec3(0, 10, 0))

        # Initialize UI if enabled
        if self.config.enable_ui:
            self._init_ui()

        # Load game content
        self._load_game_content()

        self._state = GameState.PLAYING
        self._last_time = self._backend.get_time()
        self._fps_update_time = self._last_time

        return True

    def _init_ui(self) -> None:
        """Initialize UI system."""
        try:
            from ui_system import UIManager

            self._ui_manager = UIManager(
                self._backend.width,
                self._backend.height,
            )
            self._ui_manager.set_world(self._world)
        except ImportError:
            # UI system not available
            pass

    def _load_game_content(self) -> None:
        """Load game content from data files."""
        try:
            from data_loader import DataLoader

            loader = DataLoader()

            # Load NPCs
            npcs = loader.load_npcs("data/npcs/village_npcs.json")
            for npc in npcs:
                self._world.spawn_entity(npc)

            # Load quests
            quests = loader.load_quests("data/quests/village_quests.json")
            for quest in quests:
                self._world.register_quest(quest)

            # Load items
            items = loader.load_items("data/items/items.json")
            for item in items:
                self._world.register_item_definition(item)

        except Exception as e:
            print(f"Warning: Could not load game content: {e}")

    def shutdown(self) -> None:
        """Shutdown all systems."""
        if self._ui_manager:
            self._ui_manager.shutdown()
        self._backend.shutdown()

    def run(self) -> None:
        """Run the main game loop.

        This is the primary entry point for running the game.
        """
        if not self.initialize():
            return

        self._running = True

        try:
            while self._running:
                self._running = self._frame()
        finally:
            self.shutdown()

    def run_frames(self, count: int) -> None:
        """Run a specific number of frames (for testing).

        Parameters
        ----------
        count:
            Number of frames to run.
        """
        if not self.initialize():
            return

        self._running = True

        try:
            for _ in range(count):
                if not self._running:
                    break
                self._running = self._frame()
        finally:
            self.shutdown()

    def _frame(self) -> bool:
        """Process a single frame.

        Returns False if the game should exit.
        """
        # Timing
        current_time = self._backend.get_time()
        frame_time = current_time - self._last_time
        self._last_time = current_time

        # Cap frame time to prevent spiral of death
        if frame_time > 0.25:
            frame_time = 0.25

        # Update FPS counter
        self._fps_frame_count += 1
        if current_time - self._fps_update_time >= 1.0:
            self._fps = self._fps_frame_count / (current_time - self._fps_update_time)
            self._fps_frame_count = 0
            self._fps_update_time = current_time

        # Poll input events
        if not self._backend.poll_events(self._input_manager):
            return False

        # Fixed timestep game updates
        self._accumulator += frame_time
        updates = 0

        while self._accumulator >= self.config.fixed_timestep:
            self._update(self.config.fixed_timestep)
            self._accumulator -= self.config.fixed_timestep
            updates += 1

            # Prevent too many updates in one frame
            if updates >= self.config.max_frame_skip:
                self._accumulator = 0.0
                break

        # Render
        self._backend.begin_frame()
        self._render()
        self._render_ui()
        self._backend.end_frame()

        self._frame_count += 1
        return True

    def _update(self, dt: float) -> None:
        """Update game state."""
        if self._state == GameState.PLAYING:
            # Update player controller
            player = self._world.get_player()
            if player and self._player_controller:
                self._player_controller.update(player, self._world, dt)

            # Update world (physics, NPCs, etc.)
            self._world.step(dt)

        elif self._state == GameState.DIALOGUE:
            # Still allow dialogue input processing
            pass

        # Call custom update callback
        if self._on_update:
            self._on_update(dt)

    def _render(self) -> None:
        """Render the game world."""
        # In headless mode or without graphics, this is a no-op
        # With graphics enabled, this would render through Vulkan

        if self._on_render:
            self._on_render()

    def _render_ui(self) -> None:
        """Render UI elements."""
        if self._ui_manager and self.config.enable_ui:
            player = self._world.get_player() if self._world else None

            self._ui_manager.begin_frame()

            # Render appropriate UI based on state
            if self._state == GameState.PLAYING:
                self._ui_manager.render_hud(player)

            elif self._state == GameState.PAUSED:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_pause_menu()

            elif self._state == GameState.INVENTORY:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_inventory(player)

            elif self._state == GameState.DIALOGUE:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_dialogue()

            # Debug overlay
            if self.config.enable_debug:
                self._ui_manager.render_debug(self._fps, self._frame_count)

            self._ui_manager.end_frame()

        if self._on_ui:
            self._on_ui()

    # -------------------------------------------------------------------------
    # UI Callbacks
    # -------------------------------------------------------------------------

    def _on_pause_pressed(self) -> None:
        """Handle pause button press."""
        if self._state == GameState.PLAYING:
            self._state = GameState.PAUSED
            self._world.paused = True
        elif self._state == GameState.PAUSED:
            self._state = GameState.PLAYING
            self._world.paused = False
        elif self._state in (GameState.INVENTORY, GameState.DIALOGUE):
            # Close current UI
            self._state = GameState.PLAYING
            if self._player_controller:
                self._player_controller.in_dialogue = False
                self._player_controller.in_menu = False

    def _on_inventory_pressed(self) -> None:
        """Handle inventory button press."""
        if self._state == GameState.PLAYING:
            self._state = GameState.INVENTORY
            if self._player_controller:
                self._player_controller.in_menu = True
        elif self._state == GameState.INVENTORY:
            self._state = GameState.PLAYING
            if self._player_controller:
                self._player_controller.in_menu = False

    def _on_dialogue_advance(self) -> None:
        """Handle dialogue advance."""
        if self._ui_manager and self._state == GameState.DIALOGUE:
            self._ui_manager.advance_dialogue()

    def _on_dialogue_option(self, option_index: int) -> None:
        """Handle dialogue option selection."""
        if self._ui_manager and self._state == GameState.DIALOGUE:
            self._ui_manager.select_dialogue_option(option_index)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start_dialogue(self, npc_id: str) -> bool:
        """Start dialogue with an NPC.

        Parameters
        ----------
        npc_id:
            ID of the NPC to talk to.

        Returns
        -------
        bool:
            True if dialogue started successfully.
        """
        if self._world.initiate_dialogue(npc_id):
            self._state = GameState.DIALOGUE
            if self._player_controller:
                self._player_controller.in_dialogue = True
            if self._ui_manager:
                npc = self._world.get_entity(npc_id)
                if isinstance(npc, NPC):
                    self._ui_manager.start_dialogue(npc)
            return True
        return False

    def end_dialogue(self) -> None:
        """End current dialogue."""
        if self._player_controller:
            player = self._world.get_player()
            if player and player.current_interaction_target:
                self._world.end_dialogue(player.current_interaction_target)
            self._player_controller.end_dialogue()
        self._state = GameState.PLAYING

    @property
    def world(self) -> Optional[GameWorld]:
        """Get the game world."""
        return self._world

    @property
    def player(self) -> Optional[Player]:
        """Get the player entity."""
        return self._world.get_player() if self._world else None

    @property
    def state(self) -> GameState:
        """Get current game state."""
        return self._state

    @state.setter
    def state(self, value: GameState) -> None:
        """Set game state."""
        self._state = value

    @property
    def fps(self) -> float:
        """Get current FPS."""
        return self._fps

    @property
    def frame_count(self) -> int:
        """Get total frame count."""
        return self._frame_count

    @property
    def backend(self) -> WindowBackend:
        """Get window backend."""
        return self._backend

    def set_update_callback(self, callback: Callable[[float], None]) -> None:
        """Set custom update callback."""
        self._on_update = callback

    def set_render_callback(self, callback: Callable[[], None]) -> None:
        """Set custom render callback."""
        self._on_render = callback

    def set_ui_callback(self, callback: Callable[[], None]) -> None:
        """Set custom UI render callback."""
        self._on_ui = callback

    def quit(self) -> None:
        """Request game exit."""
        self._running = False
