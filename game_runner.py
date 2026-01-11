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
from graphics_bridge import GraphicsBridge

if TYPE_CHECKING:
    from ui_system import UIManager
    import numpy as np

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
        # Set up SDL2 DLL path for Windows
        import os
        import sys
        if sys.platform == "win32":
            # Try multiple locations for SDL2.dll
            possible_paths = [
                os.path.dirname(os.path.abspath(__file__)),  # Same dir as script
                os.getcwd(),  # Current working directory
                os.path.dirname(sys.executable),  # Python executable dir
            ]
            
            # Also check if running from PyInstaller bundle
            if getattr(sys, 'frozen', False):
                possible_paths.insert(0, sys._MEIPASS)  # PyInstaller temp dir
                possible_paths.insert(0, os.path.dirname(sys.executable))
            
            for path in possible_paths:
                sdl2_dll = os.path.join(path, "SDL2.dll")
                if os.path.exists(sdl2_dll):
                    os.environ["PYSDL2_DLL_PATH"] = path
                    print(f"Found SDL2.dll at: {path}")
                    break
            else:
                print(f"SDL2.dll not found in: {possible_paths}")
        
        # Import is inside function to avoid hard dependency
        import sdl2
        import sdl2.ext

        class SDL2Backend(WindowBackend):
            """SDL2-based window backend with Vulkan support."""

            def __init__(self) -> None:
                self._window = None
                self._renderer = None
                self._width: int = 1920
                self._height: int = 1080
                self._focused: bool = True
                self._start_time: float = 0.0
                self._vk_surface: Optional[int] = None  # VkSurfaceKHR handle as int

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
                    print(f"SDL2 init failed: {sdl2.SDL_GetError()}")
                    return False

                # Add SDL_WINDOW_VULKAN flag for Vulkan rendering
                flags = sdl2.SDL_WINDOW_SHOWN | sdl2.SDL_WINDOW_RESIZABLE | sdl2.SDL_WINDOW_VULKAN
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
                    print(f"SDL2 window creation failed: {sdl2.SDL_GetError()}")
                    sdl2.SDL_Quit()
                    return False

                self._width = config.window_width
                self._height = config.window_height
                self._start_time = time.perf_counter()

                # Capture mouse for FPS-style controls
                sdl2.SDL_SetRelativeMouseMode(sdl2.SDL_TRUE)

                print(f"SDL2 window created with Vulkan support: {self._width}x{self._height}")
                return True

            def get_vulkan_instance_extensions(self) -> List[str]:
                """Get the Vulkan instance extensions required by SDL2.
                
                Returns a list of extension names that must be enabled when
                creating the Vulkan instance for SDL2 surface support.
                """
                import ctypes
                from sdl2 import vulkan as sdl_vulkan
                
                if not self._window:
                    return []
                
                # Get the count first
                count = ctypes.c_uint(0)
                if not sdl_vulkan.SDL_Vulkan_GetInstanceExtensions(
                    self._window, ctypes.byref(count), None
                ):
                    print(f"Failed to get Vulkan extension count: {sdl2.SDL_GetError()}")
                    return []
                
                if count.value == 0:
                    return []
                
                # Allocate array and get extensions
                extensions = (ctypes.c_char_p * count.value)()
                if not sdl_vulkan.SDL_Vulkan_GetInstanceExtensions(
                    self._window, ctypes.byref(count), extensions
                ):
                    print(f"Failed to get Vulkan extensions: {sdl2.SDL_GetError()}")
                    return []
                
                # Convert to Python list of strings, filtering out any null pointers
                result = [ext.decode('utf-8') for ext in extensions if ext is not None]
                print(f"SDL2 requires Vulkan extensions: {result}")
                return result

            def create_vulkan_surface(self, vk_instance: int) -> Optional[int]:
                """Create a Vulkan surface for this window.
                
                Parameters
                ----------
                vk_instance:
                    The VkInstance handle as an integer (from C++ get_instance_handle()).
                    
                Returns
                -------
                int or None:
                    The VkSurfaceKHR handle as an integer, or None on failure.
                """
                import ctypes
                from sdl2 import vulkan as sdl_vulkan
                
                if not self._window:
                    print("Cannot create Vulkan surface: no window")
                    return None
                
                if vk_instance == 0:
                    print("Cannot create Vulkan surface: invalid instance handle")
                    return None
                
                # Create surface
                surface = ctypes.c_uint64(0)  # VkSurfaceKHR is a 64-bit handle
                
                # Cast the instance handle to VkInstance (void pointer)
                vk_instance_ptr = ctypes.c_void_p(vk_instance)
                
                result = sdl_vulkan.SDL_Vulkan_CreateSurface(
                    self._window,
                    vk_instance_ptr,
                    ctypes.byref(surface)
                )
                
                if not result:
                    print(f"Failed to create Vulkan surface: {sdl2.SDL_GetError()}")
                    return None
                
                self._vk_surface = surface.value
                print(f"Vulkan surface created: handle={hex(self._vk_surface)}")
                return self._vk_surface

            @property
            def vulkan_surface(self) -> Optional[int]:
                """Get the Vulkan surface handle (or None if not created)."""
                return self._vk_surface

            def shutdown(self) -> None:
                # Note: The Vulkan surface is destroyed by the C++ GraphicsSystem
                # when it shuts down, not here. SDL2 cleanup should happen after.
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

    except ImportError as e:
        print(f"Note: SDL2 not available ({e}). Install with: pip install pysdl2 pysdl2-dll")
        return None
    except Exception as e:
        print(f"Warning: SDL2 backend creation failed: {e}")
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
            print(f"Using provided backend: {type(backend).__name__}")
        elif self.config.headless:
            self._backend = HeadlessBackend()
            print("Using HeadlessBackend (--headless mode)")
        else:
            # Try SDL2, fall back to headless
            sdl2_backend = create_sdl2_backend()
            if sdl2_backend:
                self._backend = sdl2_backend
                print("Using SDL2Backend (windowed mode)")
            else:
                self._backend = HeadlessBackend()
                print("Warning: Falling back to HeadlessBackend (no window)")
                print("         The game will run but without a visible window.")
                print("         To fix: pip install pysdl2 pysdl2-dll")

        # Game state
        self._state = GameState.LOADING
        self._running = False

        # Core systems
        self._world: Optional[GameWorld] = None
        self._player_controller: Optional[PlayerController] = None
        self._input_manager: Optional[InputManager] = None
        self._graphics_bridge: Optional[GraphicsBridge] = None

        # UI system (lazily loaded)
        self._ui_manager: Optional["UIManager"] = None

        # Cached mesh names for entities
        self._entity_meshes: Dict[str, str] = {}  # entity_id -> mesh_name
        self._terrain_mesh_name: str = "terrain"

        # Terrain data storage
        self._terrain_heightmap: Optional["np.ndarray"] = None
        self._terrain_biome: Optional["np.ndarray"] = None
        self._terrain_river: Optional["np.ndarray"] = None
        self._terrain_slope: Optional["np.ndarray"] = None

        # Timing
        self._last_time: float = 0.0
        self._accumulator: float = 0.0
        self._frame_count: int = 0
        self._fps: float = 0.0
        self._fps_update_time: float = 0.0
        self._fps_frame_count: int = 0
        self._frame_start_time: float = 0.0  # For frame rate limiting

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

        # Initialize graphics bridge, passing the backend for Vulkan surface creation
        self._graphics_bridge = GraphicsBridge()
        graphics_available = self._graphics_bridge.initialize(
            width=self.config.window_width,
            height=self.config.window_height,
            enable_validation=self.config.enable_debug,
            enable_vsync=self.config.vsync,
            window_backend=self._backend,  # Pass backend for Vulkan surface support
        )
        if graphics_available:
            self._init_graphics_resources()

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

        # Create player at center of terrain, high up initially
        spawn_x = self.config.chunk_size // 2
        spawn_z = self.config.chunk_size // 2
        self._world.create_player(name="Hero", position=Vec3(spawn_x, 50, spawn_z))

        # Initialize UI if enabled
        if self.config.enable_ui:
            self._init_ui()

        # Setup terrain
        self._setup_terrain()

        # Adjust player position to terrain height
        if self._terrain_heightmap is not None:
            player = self._world.get_player()
            if player:
                px = int(player.position.x) % self.config.chunk_size
                pz = int(player.position.z) % self.config.chunk_size
                terrain_y = self._terrain_heightmap[pz, px]
                # Position player on terrain and reset velocity to prevent falling
                player.position = Vec3(player.position.x, terrain_y + 2.0, player.position.z)
                player.velocity = Vec3(0, 0, 0)  # Reset velocity
                player.grounded = True  # Mark as grounded
                print(f"Player spawned at terrain height: {terrain_y + 2.0}")

        # Set initial camera to view terrain
        if self._graphics_bridge and self._player_controller:
            # Position camera above and behind player, looking at terrain center
            center = self.config.chunk_size // 2
            self._player_controller.camera.camera.position = Vec3(center, 50, center + 30)
            self._player_controller.camera.camera.target = Vec3(center, 0, center)

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

    def _init_graphics_resources(self) -> None:
        """Initialize graphics resources (pipelines, default meshes)."""
        if not self._graphics_bridge:
            return

        # Use C++ built-in default pipeline (has matching shader/uniform layout)
        try:
            if (self._graphics_bridge._graphics_system and 
                hasattr(self._graphics_bridge._graphics_system, 'create_default_pipeline')):
                
                pipeline = self._graphics_bridge._graphics_system.create_default_pipeline()
                
                if pipeline.is_valid():
                    self._graphics_bridge._pipelines["default"] = pipeline
                    print("Default rendering pipeline created")
                else:
                    print("WARNING: Failed to create default pipeline")
            else:
                print("WARNING: Graphics system does not support create_default_pipeline")
                
        except Exception as e:
            print(f"ERROR creating pipeline: {e}")
            import traceback
            traceback.print_exc()

        # Add default sun light
        self._graphics_bridge.add_light(
            position=(100.0, 200.0, 100.0),
            color=(1.0, 0.95, 0.9),
            intensity=1.0,
            radius=1000.0,
        )

    def _load_game_content(self) -> None:
        """Load game content from data files."""
        try:
            from data_loader import DataLoader

            loader = DataLoader()

            # Load NPCs (path relative to data_dir, not including 'data/')
            npcs = loader.load_npcs("npcs/village_npcs.json")
            for npc in npcs:
                self._world.spawn_entity(npc)

            # Load quests
            quests = loader.load_quests("quests/village_quests.json")
            for quest in quests:
                self._world.register_quest(quest)

            # Load items
            items = loader.load_items("items/items.json")
            for item in items:
                self._world.register_item_definition(item)

        except Exception as e:
            print(f"Warning: Could not load game content: {e}")

    def shutdown(self) -> None:
        """Shutdown all systems."""
        if self._ui_manager:
            self._ui_manager.shutdown()
        if self._graphics_bridge:
            self._graphics_bridge.shutdown()
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
        # Frame rate limiting (fallback if Vulkan vsync doesn't work)
        # Only apply limiting if target_fps is set and we're not in headless mode
        if self.config.target_fps > 0 and not isinstance(self._backend, HeadlessBackend):
            min_frame_time = 1.0 / self.config.target_fps
            if self._frame_start_time > 0:
                elapsed = self._backend.get_time() - self._frame_start_time
                if elapsed < min_frame_time:
                    sleep_time = min_frame_time - elapsed
                    time.sleep(sleep_time)
        
        self._frame_start_time = self._backend.get_time()
        
        # Debug once per second
        if self._frame_count % 60 == 0:
            self._debug_render_state()
        
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
        if self._graphics_bridge and not self._graphics_bridge.is_headless:
            # Update camera from player controller
            if self._player_controller:
                self._graphics_bridge.set_camera_from_controller(
                    self._player_controller.camera
                )

            # Begin rendering
            self._graphics_bridge.begin_frame()

            # Render terrain if available
            if self._terrain_mesh_name in self._graphics_bridge._meshes:
                from graphics_bridge import create_identity_matrix
                self._graphics_bridge.draw_mesh(
                    self._terrain_mesh_name,
                    "default",
                    create_identity_matrix(),
                )

            # Render all entities in the world
            if self._world:
                self._render_entities()

            # End rendering
            self._graphics_bridge.end_frame()

        if self._on_render:
            self._on_render()

    def _render_entities(self) -> None:
        """Render all visible entities in the game world."""
        if not self._world or not self._graphics_bridge:
            return

        # Render player
        player = self._world.get_player()
        if player:
            mesh_name = self._get_or_create_entity_mesh(player.entity_id, "player")
            self._graphics_bridge.draw_entity(
                mesh_name,
                "default",
                player.position,
                rotation=0.0,
                scale=1.0,
            )

        # Render NPCs
        for entity in self._world.get_entities_by_type(NPC):
            mesh_name = self._get_or_create_entity_mesh(entity.entity_id, "npc")
            self._graphics_bridge.draw_entity(
                mesh_name,
                "default",
                entity.position,
                rotation=0.0,
                scale=1.0,
            )

    def _get_or_create_entity_mesh(self, entity_id: str, entity_type: str) -> str:
        """Get or create a mesh for an entity.

        Parameters
        ----------
        entity_id:
            Unique entity identifier.
        entity_type:
            Type of entity (player, npc, prop, etc.).

        Returns
        -------
        str:
            Name of the mesh to use for rendering.
        """
        if entity_id in self._entity_meshes:
            return self._entity_meshes[entity_id]

        # Create mesh name
        mesh_name = f"{entity_type}_{entity_id}"

        # Create and upload mesh using graphics bridge
        if self._graphics_bridge:
            self._graphics_bridge.upload_entity_mesh(mesh_name, entity_type)

        self._entity_meshes[entity_id] = mesh_name
        return mesh_name

    def _setup_terrain(self) -> None:
        """Setup terrain mesh from world data using C++ terrain generation."""
        if not self._graphics_bridge or not self._world:
            return

        try:
            import numpy as np
            import procengine_cpp as cpp

            size = self.config.chunk_size
            seed = self.config.world_seed

            print(f"Generating terrain: size={size}, seed={seed}")

            # Use generate_terrain_standalone which is bound to Python
            result = cpp.generate_terrain_standalone(
                seed=seed,
                size=size,
                octaves=6,
                macro_points=8,
                erosion_iters=500,
                return_slope=True
            )
            
            # Unpack results (returns tuple of height, biome, river, slope)
            heightmap = result[0]
            biome_map = result[1]
            river_map = result[2]
            slope_map = result[3] if len(result) > 3 else None
            
            # Scale heights to world units
            HEIGHT_SCALE = 30.0
            heightmap = heightmap * HEIGHT_SCALE
            
            # Store terrain data for other systems
            self._terrain_heightmap = heightmap
            self._terrain_biome = biome_map
            self._terrain_river = river_map
            if slope_map is not None:
                self._terrain_slope = slope_map

            # Upload terrain mesh to GPU
            success = self._graphics_bridge.upload_terrain_mesh(
                self._terrain_mesh_name,
                heightmap,
                cell_size=1.0,
                biome_map=biome_map,  # Pass biome data for coloring
            )

            if success:
                print(f"Terrain mesh uploaded: {size}x{size}")

                # Position camera to view terrain after upload
                center = size / 2.0
                camera_height = size * 1.5  # High enough to see whole terrain
                camera_distance = size * 0.8

                self._graphics_bridge.set_camera_direct(
                    position=(center, camera_height, center + camera_distance),
                    target=(center, 0.0, center),
                    fov=60.0,
                )

                print(
                    f"Camera positioned at ({center}, {camera_height}, {center + camera_distance})"
                )
                print(f"Looking at ({center}, 0.0, {center})")
            else:
                print("Warning: Failed to upload terrain mesh")
                return

            # Update physics height field
            self._update_physics_terrain(heightmap, size)

        except ImportError as e:
            print(f"Warning: C++ module not available: {e}")
            self._setup_terrain_fallback()
        except AttributeError as e:
            print(f"Warning: C++ terrain API mismatch: {e}")
            self._setup_terrain_fallback()
        except Exception as e:
            print(f"Warning: Terrain setup failed: {e}")
            import traceback
            traceback.print_exc()
            self._setup_terrain_fallback()

    def _setup_terrain_fallback(self) -> None:
        """Fallback terrain using simple procedural generation."""
        try:
            import numpy as np
            
            size = self.config.chunk_size
            heightmap = np.zeros((size, size), dtype=np.float32)

            for z in range(size):
                for x in range(size):
                    heightmap[z, x] = (
                        np.sin(x * 0.05) * np.cos(z * 0.05) * 10.0 +
                        np.sin(x * 0.1 + 1.5) * np.cos(z * 0.08) * 5.0 +
                        np.sin(x * 0.2) * np.sin(z * 0.15) * 2.5 +
                        np.cos(x * 0.03) * np.sin(z * 0.04) * 15.0
                    )

            self._terrain_heightmap = heightmap
            
            self._graphics_bridge.upload_terrain_mesh(
                self._terrain_mesh_name,
                heightmap,
                cell_size=1.0,
            )
            print(f"Using fallback terrain: {size}x{size}")
            
            self._update_physics_terrain(heightmap, size)
            
        except Exception as e:
            print(f"Fallback terrain setup failed: {e}")

    def _update_physics_terrain(self, heightmap: "np.ndarray", size: int) -> None:
        """Update physics system with terrain height field."""
        try:
            from physics import HeightField2D
            
            height_field = HeightField2D(
                heightmap,  # Pass numpy array directly
                x0=0.0,
                z0=0.0,
                cell_size=1.0,
            )
            
            if hasattr(self._world, 'set_heightfield'):
                self._world.set_heightfield(height_field)
                print(f"Physics heightfield set: {size}x{size}, height range [{heightmap.min():.1f}, {heightmap.max():.1f}]")
            else:
                print("Warning: GameWorld does not have set_heightfield method")
        except Exception as e:
            print(f"Warning: Could not update physics terrain: {e}")
            import traceback
            traceback.print_exc()

    def _debug_render_state(self) -> None:
        """Print debug info about render state."""
        if not self._graphics_bridge:
            print("DEBUG: No graphics bridge!")
            return
        
        print("=== RENDER DEBUG ===")
        print(f"Headless: {self._graphics_bridge.is_headless}")
        print(f"Meshes: {list(self._graphics_bridge._meshes.keys())}")
        print(f"Pipelines: {list(self._graphics_bridge._pipelines.keys())}")
        print(f"Camera pos: {self._graphics_bridge._camera_position}")
        print(f"Camera target: {self._graphics_bridge._camera_target}")
        
        # Check terrain mesh
        terrain = self._graphics_bridge._meshes.get("terrain")
        if terrain:
            if isinstance(terrain, dict):
                print("Terrain: PLACEHOLDER (not on GPU!)")
            else:
                print(f"Terrain: GPU mesh, valid={terrain.is_valid()}")
        else:
            print("Terrain: NOT FOUND")
        
        # Check pipeline
        pipeline = self._graphics_bridge._pipelines.get("default")
        if pipeline:
            if isinstance(pipeline, dict):
                print("Pipeline: PLACEHOLDER")
            else:
                print(f"Pipeline: valid={pipeline.is_valid()}")
        else:
            print("Pipeline: NOT FOUND")
        print("====================")

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

    @property
    def graphics_bridge(self) -> Optional[GraphicsBridge]:
        """Get the graphics bridge for direct rendering control."""
        return self._graphics_bridge

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
