"""Game runner with window management and main loop.

This module provides the main game loop that orchestrates:
- Window creation and management (via backend abstraction)
- Input event processing
- Game state updates
- Rendering (when graphics backend available)
- UI rendering via Dear ImGui (when available)
- Console for command input

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
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from procengine.physics import Vec3, HeightField2D
from procengine.game.game_api import GameWorld, GameConfig, Player, NPC, Prop, Event, EventType
from procengine.game.player_controller import (
    InputManager,
    InputAction,
    InputState,
    PlayerController,
    CameraController,
    Camera,
)
from procengine.graphics.graphics_bridge import GraphicsBridge
from procengine.commands.commands import registry as command_registry, CommandResult
from procengine.commands.console import Console

if TYPE_CHECKING:
    from procengine.game.ui_system import UIManager
    import numpy as np

__all__ = [
    "RunnerConfig",
    "GameRunner",
    "WindowBackend",
    "HeadlessBackend",
]


# =============================================================================
# Prop render-scale helper
# =============================================================================

def _prop_render_scale(prop_type: str, state: dict | None) -> float:
    """Return the world-space render scale for a prop entity.

    Rocks and boulder clusters scale by their radius so their visual size
    matches the generated descriptor.  Most other props are authored at
    final size so they use 1.0.
    """
    if state is None:
        return 1.0
    if prop_type == "rock":
        return state.get("radius", 1.0) * 2.0
    if prop_type == "bush":
        return state.get("radius", 0.6) * 2.0
    # Everything else is authored at its natural size
    return 1.0


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

    # Dynamic chunk loading settings
    enable_dynamic_chunks: bool = True  # Dynamic infinite world (default)
    render_distance: int = 6  # chunks radius for rendering (reduced from 8 for perf)
    sim_distance: int = 3  # chunks radius for physics/AI simulation (reduced from 4)

    # World loading settings
    loading_chunks_per_frame: int = 4  # chunks to generate per frame during LOADING
    min_loaded_chunks: int = 0  # auto-calculated from render_distance if 0


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

    @abstractmethod
    def set_mouse_capture(self, captured: bool) -> None:
        """Set mouse capture state (True=Locked/Hidden, False=Free/Visible)."""
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

    def set_mouse_capture(self, captured: bool) -> None:
        pass

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
                    # Letters (A-Z)
                    sdl2.SDL_SCANCODE_A: "A",
                    sdl2.SDL_SCANCODE_B: "B",
                    sdl2.SDL_SCANCODE_C: "C",
                    sdl2.SDL_SCANCODE_D: "D",
                    sdl2.SDL_SCANCODE_E: "E",
                    sdl2.SDL_SCANCODE_F: "F",
                    sdl2.SDL_SCANCODE_G: "G",
                    sdl2.SDL_SCANCODE_H: "H",
                    sdl2.SDL_SCANCODE_I: "I",
                    sdl2.SDL_SCANCODE_J: "J",
                    sdl2.SDL_SCANCODE_K: "K",
                    sdl2.SDL_SCANCODE_L: "L",
                    sdl2.SDL_SCANCODE_M: "M",
                    sdl2.SDL_SCANCODE_N: "N",
                    sdl2.SDL_SCANCODE_O: "O",
                    sdl2.SDL_SCANCODE_P: "P",
                    sdl2.SDL_SCANCODE_Q: "Q",
                    sdl2.SDL_SCANCODE_R: "R",
                    sdl2.SDL_SCANCODE_S: "S",
                    sdl2.SDL_SCANCODE_T: "T",
                    sdl2.SDL_SCANCODE_U: "U",
                    sdl2.SDL_SCANCODE_V: "V",
                    sdl2.SDL_SCANCODE_W: "W",
                    sdl2.SDL_SCANCODE_X: "X",
                    sdl2.SDL_SCANCODE_Y: "Y",
                    sdl2.SDL_SCANCODE_Z: "Z",
                    # Numbers
                    sdl2.SDL_SCANCODE_0: "0",
                    sdl2.SDL_SCANCODE_1: "1",
                    sdl2.SDL_SCANCODE_2: "2",
                    sdl2.SDL_SCANCODE_3: "3",
                    sdl2.SDL_SCANCODE_4: "4",
                    sdl2.SDL_SCANCODE_5: "5",
                    sdl2.SDL_SCANCODE_6: "6",
                    sdl2.SDL_SCANCODE_7: "7",
                    sdl2.SDL_SCANCODE_8: "8",
                    sdl2.SDL_SCANCODE_9: "9",
                    # Punctuation / symbols
                    sdl2.SDL_SCANCODE_PERIOD: "PERIOD",
                    sdl2.SDL_SCANCODE_COMMA: "COMMA",
                    sdl2.SDL_SCANCODE_MINUS: "MINUS",
                    sdl2.SDL_SCANCODE_EQUALS: "EQUALS",
                    sdl2.SDL_SCANCODE_SLASH: "SLASH",
                    sdl2.SDL_SCANCODE_BACKSLASH: "BACKSLASH",
                    sdl2.SDL_SCANCODE_SEMICOLON: "SEMICOLON",
                    sdl2.SDL_SCANCODE_APOSTROPHE: "QUOTE",
                    sdl2.SDL_SCANCODE_LEFTBRACKET: "LEFTBRACKET",
                    sdl2.SDL_SCANCODE_RIGHTBRACKET: "RIGHTBRACKET",
                    # Whitespace / editing
                    sdl2.SDL_SCANCODE_SPACE: "SPACE",
                    sdl2.SDL_SCANCODE_RETURN: "RETURN",
                    sdl2.SDL_SCANCODE_BACKSPACE: "BACKSPACE",
                    sdl2.SDL_SCANCODE_DELETE: "DELETE",
                    sdl2.SDL_SCANCODE_TAB: "TAB",
                    sdl2.SDL_SCANCODE_HOME: "HOME",
                    sdl2.SDL_SCANCODE_END: "END",
                    # Navigation
                    sdl2.SDL_SCANCODE_UP: "UP",
                    sdl2.SDL_SCANCODE_DOWN: "DOWN",
                    sdl2.SDL_SCANCODE_LEFT: "LEFT",
                    sdl2.SDL_SCANCODE_RIGHT: "RIGHT",
                    # Modifiers
                    sdl2.SDL_SCANCODE_LSHIFT: "LSHIFT",
                    sdl2.SDL_SCANCODE_RSHIFT: "RSHIFT",
                    sdl2.SDL_SCANCODE_LCTRL: "LCTRL",
                    sdl2.SDL_SCANCODE_RCTRL: "RCTRL",
                    sdl2.SDL_SCANCODE_LALT: "LALT",
                    sdl2.SDL_SCANCODE_RALT: "RALT",
                    # UI / special
                    sdl2.SDL_SCANCODE_ESCAPE: "ESCAPE",
                    sdl2.SDL_SCANCODE_GRAVE: "GRAVE",
                    # Function keys
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

            @property
            def sdl_window_handle(self) -> Optional[int]:
                """Get the SDL_Window pointer as an integer for C++ interop."""
                import ctypes
                if self._window:
                    return ctypes.cast(self._window, ctypes.c_void_p).value
                return None

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

            def set_mouse_capture(self, captured: bool) -> None:
                # True = Locked (Relative Mode), False = Free (Absolute Mode)
                mode = sdl2.SDL_TRUE if captured else sdl2.SDL_FALSE
                sdl2.SDL_SetRelativeMouseMode(mode)

                # Ensure cursor is visible when unlocked
                # SDL_DISABLE (0) hides cursor, SDL_ENABLE (1) shows it
                sdl2.SDL_ShowCursor(sdl2.SDL_DISABLE if captured else sdl2.SDL_ENABLE)

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

    # Height scale factor for terrain (converts normalized [0,1] to world units)
    HEIGHT_SCALE: float = 30.0

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

        # Console system
        self._console: Console = Console()
        self._console.on_open = self._on_console_open
        self._console.on_close = self._on_console_close

        # Keybinds (key -> command string)
        self.keybinds: Dict[str, str] = {}

        # Flags for runtime state
        self.flags: Dict[str, bool] = {}
        self.flags["debug_overlay"] = self.config.enable_debug
        self.flags["vsync"] = self.config.vsync

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

        # Chunk management (for dynamic chunks mode)
        self._chunk_manager: Optional[Any] = None

        # C++ GameManager for async chunk gen + dynamic tuning
        from procengine.managers.game_manager import GameManagerBridge, ManagerConfig
        self._game_manager = GameManagerBridge(
            seed=self.config.world_seed,
            config=ManagerConfig(
                terrain_octaves=6,
                terrain_macro_points=8,
                terrain_erosion_iters=0,
            ),
        )

        # LOD bias from GameManager directive (used by prop generation)
        self._current_lod_bias: float = 0.0

        # World loading state (progressive loading before gameplay starts)
        self._loading_total_chunks: int = 0  # Total chunks needed before PLAYING
        self._loading_chunks_done: int = 0  # Chunks loaded so far
        self._loading_complete: bool = False  # True when world is ready

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
        self._player_controller.on_console_toggle = self._on_console_toggle

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

        # Setup terrain (dynamic chunks or static)
        if self.config.enable_dynamic_chunks:
            self._setup_dynamic_terrain()
        else:
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
            # Get terrain height at center if available
            terrain_target_y = 0.0
            if self._terrain_heightmap is not None:
                # Safely clamp center to heightmap bounds
                h, w = self._terrain_heightmap.shape
                safe_z = min(center, h - 1)
                safe_x = min(center, w - 1)
                terrain_target_y = float(self._terrain_heightmap[safe_z, safe_x])
            camera_y = terrain_target_y + 35.0  # Above terrain
            self._player_controller.camera.camera.position = Vec3(center, camera_y, center + 30)
            self._player_controller.camera.camera.target = Vec3(center, terrain_target_y, center)

        # Load game content
        self._load_game_content()

        # Initialize command system
        self._init_commands()

        # Start in LOADING for dynamic chunks (world loads first, then player starts)
        # For static terrain, loading is already done so go straight to PLAYING
        if self.config.enable_dynamic_chunks and not self._loading_complete:
            self._state = GameState.LOADING
            print("Entering LOADING state — generating world terrain...")
        else:
            self._state = GameState.PLAYING

        self._last_time = self._backend.get_time()
        self._fps_update_time = self._last_time

        return True

    def _init_ui(self) -> None:
        """Initialize UI system.

        When running in windowed mode (not headless), attempts to create an
        ImGuiBackend backed by the C++ Dear ImGui renderer.  Falls back to the
        HeadlessUIBackend if the C++ module is unavailable.
        """
        try:
            from procengine.game.ui_system import UIManager

            backend = None
            if not self.config.headless:
                try:
                    from procengine.game.ui_system import ImGuiBackend
                    backend = ImGuiBackend()

                    # Initialize C++ ImGui context with the SDL window handle
                    # This bridges the gap between the Python UI system and C++ renderer
                    if self._backend and hasattr(self._backend, 'sdl_window_handle'):
                        handle = self._backend.sdl_window_handle
                        if handle and self._graphics_bridge:
                            success = self._graphics_bridge.init_imgui(handle)
                            if success:
                                print("UI: C++ ImGui context initialized successfully")
                            else:
                                print("UI: Failed to initialize C++ ImGui context")

                    print("UI: Using ImGuiBackend (C++ Dear ImGui renderer)")
                except (ImportError, Exception) as exc:
                    print(f"UI: ImGui backend not available ({exc}), using headless")

            self._ui_manager = UIManager(
                self._backend.width,
                self._backend.height,
                backend=backend,
            )
            self._ui_manager.set_world(self._world)

            # Wire the developer console to the UI so it can be rendered
            self._ui_manager.set_console(self._console)

            # Wire pause menu buttons to command registry / game runner methods
            self._ui_manager.set_pause_callbacks(
                on_resume=self._on_pause_pressed,
                on_save=lambda: self.execute_command("system.save"),
                on_load=lambda: self.execute_command("system.load"),
                on_settings=self._on_settings_open,
                on_quit=lambda: self.execute_command("system.quit"),
            )

            self._ui_manager.set_settings_callbacks(
                on_toggle_debug=self._toggle_debug_overlay,
                on_toggle_vsync=self._toggle_vsync,
                on_close=self._on_settings_close,
            )

            # Wire inventory Use/Drop buttons to command registry
            self._ui_manager.set_inventory_callbacks(
                on_use=lambda item_id: self.execute_command(f"player.use {item_id}"),
                on_drop=lambda item_id: self.execute_command(f"player.drop {item_id}"),
            )

            # Wire dialogue callbacks
            self._ui_manager.set_dialogue_callbacks(
                on_option=self._on_dialogue_option,
                on_advance=self._on_dialogue_advance,
            )

            # Set up debug overlay callbacks
            self._ui_manager.set_debug_callbacks(
                on_reset_world=self._on_reset_world,
            )
        except ImportError:
            # UI system not available
            pass

    def _on_reset_world(self) -> None:
        """Handle reset world button press from debug overlay."""
        if self._world:
            # Reset player position to spawn point
            player = self._world.get_player()
            if player:
                spawn_x = self.config.chunk_size // 2
                spawn_z = self.config.chunk_size // 2
                terrain_y = 0.0
                
                # Get terrain height if available
                if self._terrain_heightmap is not None:
                    px = int(spawn_x) % self.config.chunk_size
                    pz = int(spawn_z) % self.config.chunk_size
                    terrain_y = float(self._terrain_heightmap[pz, px])
                
                player.position = Vec3(spawn_x, terrain_y + 2.0, spawn_z)
                player.velocity = Vec3(0, 0, 0)
                player.grounded = True
                player.health = player.max_health
                
            # Reset game state to playing
            self._state = GameState.PLAYING
            if self._player_controller:
                self._player_controller.in_dialogue = False
                self._player_controller.in_menu = False
                self._player_controller.movement_enabled = True
                self._player_controller.interaction_enabled = True

    def _init_commands(self) -> None:
        """Initialize the command system."""
        # Import game commands to register them
        from procengine.commands.handlers import game_commands  # noqa: F401 - imported for side effects

        # Set the command registry context to this runner
        command_registry.set_context(self)

        # Print a welcome message
        self._console.print(f"Procedural Engine v2 Console")
        self._console.print(f"Type 'help' for available commands.")
        self._console.print("")

    def _on_console_open(self) -> None:
        """Called when console opens."""
        # Pause player input while console is open
        if self._player_controller:
            self._player_controller.movement_enabled = False
            self._player_controller.interaction_enabled = False

    def _on_console_close(self) -> None:
        """Called when console closes."""
        # Resume player input
        if self._player_controller:
            self._player_controller.movement_enabled = True
            self._player_controller.interaction_enabled = True

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
            from procengine.game.data_loader import DataLoader

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
        self._render()  # Now includes UI rendering before end_frame
        self._backend.end_frame()

        self._frame_count += 1
        return True

    def _update(self, dt: float) -> None:
        """Update game state."""

        # === LOADING STATE: progressively generate world chunks ===
        if self._state == GameState.LOADING:
            self._update_loading(dt)
            return

        # When the console is open, route keyboard input to it instead of
        # the player controller.  The console toggle key (GRAVE) is still
        # handled by PlayerController._handle_ui_input so the player can
        # close the console; all other per-frame keys are consumed here.
        if self._console.is_visible:
            self._process_console_input()
            # Still allow UI inputs so the user can close the console with ~
            if self._player_controller:
                self._player_controller.process_ui_inputs()
            # Call custom update callback
            if self._on_update:
                self._on_update(dt)
            return

        if self._state == GameState.PLAYING:
            # Update player controller
            player = self._world.get_player()
            if player and self._player_controller:
                self._player_controller.update(player, self._world, dt)

            # === GameManager-driven frame ===
            if self._game_manager.available and self.config.enable_dynamic_chunks and player:
                # Keep ChunkManager's player position in sync so
                # get_render_chunks() / get_sim_chunks() return the correct
                # set.  This does NOT modify load/unload queues (C++ handles
                # those), but it DOES update _player_chunk and sim flags.
                self._chunk_manager.sync_player_chunk(
                    player.position.x, player.position.z
                )

                directive = self._game_manager.sync_frame(
                    dt, player.position.x, player.position.z,
                    self.config.render_distance, self.config.sim_distance,
                    self.config.chunk_size,
                )
                # Apply dynamic tuning from C++
                self._chunk_manager.render_distance = directive.recommended_render_distance
                self._chunk_manager.sim_distance = directive.recommended_sim_distance

                # Collect async-generated chunks from C++ thread pool
                # Always allow at least one ready chunk to be uploaded so the
                # streaming frontier can keep moving forward under sustained
                # frame pressure. Otherwise a zero-budget directive can starve
                # dynamic terrain streaming after the initial load completes.
                ready_budget = max(1, directive.max_chunk_loads)
                ready = self._game_manager.collect_ready_chunks(ready_budget)
                for result in ready:
                    self._upload_async_chunk_result(result)

                # Generate props for chunks that entered prop range
                if self._chunk_manager:
                    prop_chunks = self._chunk_manager.process_prop_queue(max_per_frame=1)
                    for chunk in prop_chunks:
                        world_x, world_z = self._chunk_manager.chunk_to_world(chunk.coords)
                        self._spawn_chunk_props(chunk, world_x, world_z)

                # Unload distant chunks (C++ determines which)
                if self._chunk_manager:
                    unload_radius = self.config.render_distance + 2
                    pcx = int(player.position.x // self.config.chunk_size)
                    pcz = int(player.position.z // self.config.chunk_size)
                    for coord_obj in self._game_manager.get_chunks_to_unload(
                        pcx, pcz, unload_radius
                    ):
                        coord = (coord_obj.x, coord_obj.z)
                        if coord in self._chunk_manager.chunks:
                            chunk = self._chunk_manager.chunks.pop(coord)
                            self._cleanup_chunk(chunk)

                # Physics gating
                if not directive.skip_physics_step:
                    self._world.step(dt)
                # Store LOD bias for prop generation
                self._current_lod_bias = directive.lod_bias
            else:
                # Fallback: original synchronous path
                self._world.step(dt)
                if self.config.enable_dynamic_chunks and self._chunk_manager and player:
                    self._chunk_manager.update_player_position(
                        player.position.x, player.position.z
                    )
                    new_chunks = self._chunk_manager.process_load_queue(max_per_frame=1)
                    for chunk in new_chunks:
                        self._upload_chunk_mesh(chunk)
                    removed_chunks = self._chunk_manager.process_unload_queue(max_per_frame=2)
                    for chunk in removed_chunks:
                        self._cleanup_chunk(chunk)

        elif self._state == GameState.DIALOGUE:
            # Still allow dialogue input processing
            pass

        else:
            # For PAUSED, INVENTORY, MENU, and other states:
            # Process UI inputs (pause toggle, etc.) to allow unpausing
            # In PLAYING state, this is handled by player_controller.update()
            if self._player_controller:
                self._player_controller.process_ui_inputs()

        # Call custom update callback
        if self._on_update:
            self._on_update(dt)

    def _render(self) -> None:
        """Render the game world."""
        if self._graphics_bridge and not self._graphics_bridge.is_headless:

            # --- LOADING state: show progress screen only ---
            if self._state == GameState.LOADING:
                self._graphics_bridge.begin_frame()
                # Render already-loaded chunks so the player sees the world
                # building up during loading (visual feedback)
                if self.config.enable_dynamic_chunks and self._chunk_manager:
                    from procengine.graphics.graphics_bridge import (
                        create_translation_matrix,
                    )

                    for chunk in self._chunk_manager.get_render_chunks():
                        if chunk.is_mesh_uploaded:
                            world_x, world_z = self._chunk_manager.chunk_to_world(
                                chunk.coords
                            )
                            transform = create_translation_matrix(world_x, 0, world_z)
                            self._graphics_bridge.draw_mesh(
                                chunk.mesh_id, "default", transform
                            )
                # Render the loading progress UI on top
                self._render_loading_screen()
                self._graphics_bridge.end_frame()
                return

            # --- Normal PLAYING / PAUSED / etc. rendering ---
            # Update camera from player controller
            if self._player_controller:
                self._graphics_bridge.set_camera_from_controller(
                    self._player_controller.camera
                )

            # Begin rendering
            self._graphics_bridge.begin_frame()

            # Render terrain
            if self.config.enable_dynamic_chunks and self._chunk_manager:
                # Draw all active render chunks
                from procengine.graphics.graphics_bridge import create_translation_matrix
                
                for chunk in self._chunk_manager.get_render_chunks():
                    if chunk.is_mesh_uploaded:
                        # Calculate transform based on chunk coordinates
                        # Chunk (1, 0) needs to be drawn at world x=64, z=0 (if chunk_size=64)
                        world_x, world_z = self._chunk_manager.chunk_to_world(chunk.coords)
                        transform = create_translation_matrix(world_x, 0, world_z)
                        
                        self._graphics_bridge.draw_mesh(
                            chunk.mesh_id,
                            "default",
                            transform,
                        )
            else:
                # Static terrain rendering
                if self._terrain_mesh_name in self._graphics_bridge._meshes:
                    from procengine.graphics.graphics_bridge import create_identity_matrix
                    self._graphics_bridge.draw_mesh(
                        self._terrain_mesh_name,
                        "default",
                        create_identity_matrix(),
                    )

            # Render all entities in the world
            if self._world:
                self._render_entities()

            # Render UI *before* ending the frame so ImGui draw data is captured
            self._render_ui()

            # End rendering
            self._graphics_bridge.end_frame()
        else:
            # In headless mode, still process UI rendering so the
            # HeadlessUIBackend records calls for testing.
            self._render_ui()

        if self._on_render:
            self._on_render()

    def _render_entities(self) -> None:
        """Render visible entities in the game world.

        In dynamic-chunk mode, only entities belonging to render-distance
        chunks are drawn.  In static mode all entities are rendered.
        """
        if not self._world or not self._graphics_bridge:
            return

        # Always render player
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

        # In dynamic-chunk mode, restrict to entities in visible chunks
        if self.config.enable_dynamic_chunks and self._chunk_manager:
            visible_eids: set = set()
            for chunk in self._chunk_manager.get_render_chunks():
                visible_eids.update(chunk.entity_ids)

            for eid in visible_eids:
                entity = self._world.get_entity(eid)
                if entity is None:
                    continue
                if isinstance(entity, NPC):
                    mesh_name = self._get_or_create_entity_mesh(entity.entity_id, "npc")
                    self._graphics_bridge.draw_entity(
                        mesh_name,
                        "default",
                        entity.position,
                        rotation=0.0,
                        scale=1.0,
                    )
                elif isinstance(entity, Prop):
                    prop_type = entity.prop_type
                    mesh_name = self._get_or_create_entity_mesh(
                        entity.entity_id, prop_type, entity.state,
                    )
                    scale = _prop_render_scale(prop_type, entity.state)
                    self._graphics_bridge.draw_entity(
                        mesh_name,
                        "default",
                        entity.position,
                        rotation=entity.rotation,
                        scale=scale,
                    )
        else:
            # Static mode: render all entities (original behavior)
            for entity in self._world.get_entities_by_type(NPC):
                mesh_name = self._get_or_create_entity_mesh(entity.entity_id, "npc")
                self._graphics_bridge.draw_entity(
                    mesh_name,
                    "default",
                    entity.position,
                    rotation=0.0,
                    scale=1.0,
                )

            for entity in self._world.get_entities_by_type(Prop):
                prop_type = entity.prop_type
                mesh_name = self._get_or_create_entity_mesh(
                    entity.entity_id, prop_type, entity.state,
                )
                scale = _prop_render_scale(prop_type, entity.state)
                self._graphics_bridge.draw_entity(
                    mesh_name,
                    "default",
                    entity.position,
                    rotation=entity.rotation,
                    scale=scale,
                )

    def _get_or_create_entity_mesh(
        self, entity_id: str, entity_type: str, entity_state: dict | None = None,
    ) -> str:
        """Get or create a mesh for an entity.

        Parameters
        ----------
        entity_id:
            Unique entity identifier.
        entity_type:
            Type of entity (player, npc, prop, etc.).
        entity_state:
            Optional entity state with descriptor parameters.

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
            success = self._graphics_bridge.upload_entity_mesh(mesh_name, entity_type, entity_state)
            if not success:
                print(f"Warning: Failed to upload {entity_type} mesh for {entity_id}")
                # Try a simpler fallback mesh (small box via "default" entity type)
                fallback_success = self._graphics_bridge.upload_entity_mesh(mesh_name, "default")
                if not fallback_success:
                    print(f"Warning: Fallback mesh also failed for {entity_id}")

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
            heightmap = heightmap * self.HEIGHT_SCALE
            
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
                # Calculate terrain mean height for proper camera targeting
                terrain_mean_y = float(heightmap.mean())
                camera_height = terrain_mean_y + size * 1.2  # Above terrain
                camera_distance = size * 0.8

                self._graphics_bridge.set_camera_direct(
                    position=(center, camera_height, center + camera_distance),
                    target=(center, terrain_mean_y, center),  # Look at terrain center height
                    fov=60.0,
                )

                print(
                    f"Camera positioned at ({center}, {camera_height:.1f}, {center + camera_distance})"
                )
                print(f"Looking at ({center}, {terrain_mean_y:.1f}, {center})")
            else:
                print("Warning: Failed to upload terrain mesh")
                return

            # Update physics height field
            self._update_physics_terrain(heightmap, size)

            # Generate and spawn props on the terrain
            self._setup_props(heightmap, size)

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

    def _setup_dynamic_terrain(self) -> None:
        """Setup dynamic chunk-based terrain with ChunkManager.
        
        This method initializes the ChunkManager for infinite world generation,
        connecting it to the GameWorld and physics system. Chunks are loaded
        progressively during the LOADING state to avoid frame-rate drops.
        
        The game stays in LOADING state until enough chunks are generated
        to fill the initial view, then transitions to PLAYING and spawns
        the player on the terrain.
        """
        try:
            from procengine.world.chunk import ChunkManager, ChunkedHeightField
            from procengine.core.seed_registry import SeedRegistry
            
            print(f"Initializing Infinite World (Chunk Size: {self.config.chunk_size})")
            
            # Initialize Chunk Manager with reduced distances
            self._chunk_manager = ChunkManager(
                seed_registry=SeedRegistry(self.config.world_seed),
                chunk_size=self.config.chunk_size,
                render_distance=self.config.render_distance,
                sim_distance=self.config.sim_distance,
            )
            
            # Attach to World
            if self._world:
                self._world.set_chunk_manager(self._chunk_manager)
                
                # Use Chunked Physics HeightField
                heightfield = ChunkedHeightField(self._chunk_manager)
                self._world.set_heightfield(heightfield)
            
            # Calculate spawn position
            player = self._world.get_player() if self._world else None
            if player:
                spawn_x = player.position.x
                spawn_z = player.position.z
            else:
                spawn_x = self.config.chunk_size // 2
                spawn_z = self.config.chunk_size // 2
            
            # Queue all chunks, but don't generate them yet —
            # the LOADING state will process them progressively
            self._chunk_manager.update_player_position(spawn_x, spawn_z)
            
            # Only require sim-distance chunks before gameplay starts.
            # The sim_distance area is the minimum viable playable zone
            # (physics + AI active). Remaining render-distance chunks
            # stream in during gameplay at 1 chunk/frame.
            r = self.config.sim_distance
            min_chunks = self.config.min_loaded_chunks
            if min_chunks <= 0:
                min_chunks = sum(
                    1 for dx in range(-r, r + 1)
                    for dz in range(-r, r + 1)
                    if dx * dx + dz * dz <= r * r
                )
            
            self._loading_total_chunks = min_chunks
            self._loading_chunks_done = 0
            self._loading_complete = False
            
            # Force-load the one chunk directly under the player so we have
            # ground for the player spawn height calculation
            immediate = self._chunk_manager.process_load_queue(max_per_frame=1)
            for chunk in immediate:
                self._upload_chunk_mesh(chunk)
                self._loading_chunks_done += 1
            
            # Adjust player to terrain height of spawn chunk
            if player and immediate:
                chunk = self._chunk_manager.get_chunk_at_world(spawn_x, spawn_z)
                if chunk and chunk.heightmap is not None:
                    local_x = int(spawn_x) % self.config.chunk_size
                    local_z = int(spawn_z) % self.config.chunk_size
                    local_x = min(max(local_x, 0), self.config.chunk_size - 1)
                    local_z = min(max(local_z, 0), self.config.chunk_size - 1)
                    terrain_y = float(chunk.heightmap[local_z, local_x]) * self.HEIGHT_SCALE
                    player.position = Vec3(spawn_x, terrain_y + 2.0, spawn_z)
                    player.velocity = Vec3(0, 0, 0)
                    player.grounded = True
                    self._terrain_heightmap = chunk.heightmap * self.HEIGHT_SCALE
            
            print(
                f"Dynamic terrain initialized — "
                f"loading {self._loading_total_chunks} chunks before gameplay..."
            )
            
        except Exception as e:
            print(f"Warning: Dynamic terrain setup failed: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to static terrain
            print("Falling back to static terrain...")
            self._setup_terrain()
            # Mark loading as complete so we don't get stuck
            self._loading_complete = True

    def _cleanup_chunk(self, chunk: Any) -> None:
        """Clean up all resources associated with an unloaded chunk.

        Destroys the terrain mesh, despawns all entities that were spawned
        in the chunk, and frees their cached GPU meshes. This prevents
        orphaned entities from accumulating as the player explores.

        Parameters
        ----------
        chunk:
            The Chunk object being unloaded.
        """
        # Destroy the terrain mesh on the GPU
        if self._graphics_bridge:
            self._graphics_bridge.destroy_mesh(chunk.mesh_id)

        # Despawn all entities that belonged to this chunk
        if self._world and hasattr(chunk, 'entity_ids'):
            for eid in chunk.entity_ids:
                self._world.destroy_entity(eid)
                if eid in self._entity_meshes:
                    mesh_name = self._entity_meshes.pop(eid)
                    if self._graphics_bridge:
                        self._graphics_bridge.destroy_mesh(mesh_name)

    def _upload_chunk_mesh(self, chunk: Any) -> None:
        """Upload a chunk's terrain mesh to the GPU and spawn pending props.

        Parameters
        ----------
        chunk:
            The Chunk object containing heightmap, biome data, and pending props.
        """
        if not self._graphics_bridge or chunk.heightmap is None:
            return
        
        # Scale heights to world units
        scaled_heightmap = chunk.heightmap * self.HEIGHT_SCALE
        
        success = self._graphics_bridge.upload_terrain_mesh(
            chunk.mesh_id,
            scaled_heightmap,
            cell_size=1.0,
            biome_map=chunk.biome_map,
        )
        
        if success:
            chunk.is_mesh_uploaded = True
        else:
            print(f"Warning: Failed to upload chunk mesh {chunk.mesh_id}")
        
        # Spawn pending props as entities
        if self._world and hasattr(chunk, 'pending_props') and chunk.pending_props:
            # Get world-space origin for this chunk
            if hasattr(chunk, 'world_origin'):
                world_x, world_z = chunk.world_origin(self.config.chunk_size)
            else:
                world_x = chunk.coords[0] * self.config.chunk_size
                world_z = chunk.coords[1] * self.config.chunk_size
            
            self._spawn_chunk_props(chunk, world_x, world_z)

    def _upload_async_chunk_result(self, result: Any) -> None:
        """Upload a chunk that was generated asynchronously by the C++ GameManager.

        Creates a Chunk dataclass from the async result and delegates to
        the standard ``_upload_chunk_mesh`` pipeline.  Also generates props
        so that async chunks behave identically to synchronous ones.

        Parameters
        ----------
        result:
            A C++ ChunkResult object with coord, height, biome, river, and
            slope arrays.
        """
        import numpy as np
        from procengine.world.chunk import Chunk

        coord = (result.coord.x, result.coord.z)

        # C++ now generates with size+1 for vertex overlap (matching Python
        # ChunkManager._generate_chunk).
        gen_size = self.config.chunk_size + 1

        height = np.array(result.height, dtype=np.float32).reshape(gen_size, gen_size)
        biome = np.array(result.biome, dtype=np.uint8).reshape(gen_size, gen_size)
        river = np.array(result.river, dtype=np.uint8).reshape(gen_size, gen_size)

        slope_arr = np.array(result.slope, dtype=np.float32)
        slope = slope_arr.reshape(gen_size, gen_size) if slope_arr.size > 0 else None

        # Generate props using the same logic as ChunkManager._generate_chunk
        prop_descriptors = []
        has_props = False
        if self._chunk_manager:
            from procengine.world.props import generate_chunk_props
            chunk_name = f"chunk_{coord[0]}_{coord[1]}"
            chunk_registry = self._chunk_manager._registry.spawn(chunk_name)

            prop_descriptors = generate_chunk_props(
                chunk_registry,
                self.config.chunk_size,
                height[:self.config.chunk_size, :self.config.chunk_size],
                slope[:self.config.chunk_size, :self.config.chunk_size] if slope is not None else None,
                biome[:self.config.chunk_size, :self.config.chunk_size],
            )
            has_props = True

        chunk = Chunk(
            coords=coord,
            heightmap=height,
            biome_map=biome,
            river_map=river,
            slope_map=slope,
            pending_props=prop_descriptors,
            is_loaded=True,
            has_props=has_props,
        )
        # Register in ChunkManager
        if self._chunk_manager:
            self._chunk_manager.chunks[coord] = chunk
        # Upload mesh to GPU
        self._upload_chunk_mesh(chunk)
        # Notify C++ that the chunk is now uploaded
        self._game_manager.mark_chunk_uploaded(coord[0], coord[1])

    def _spawn_chunk_props(self, chunk: Any, world_x: float, world_z: float) -> None:
        """Spawn props from a chunk's pending_props list as game entities.

        Parameters
        ----------
        chunk:
            The Chunk object with pending_props to spawn.
        world_x:
            World X coordinate of the chunk's origin.
        world_z:
            World Z coordinate of the chunk's origin.
        """
        if not self._world or not hasattr(chunk, 'pending_props'):
            return

        # Vertical offset to lift rocks slightly above terrain to prevent clipping
        ROCK_Y_OFFSET = 0.1

        prop_count = 0
        for idx, prop_desc in enumerate(chunk.pending_props):
            prop_type = prop_desc.get("type", "unknown")
            local_pos = prop_desc.get("position", [0, 0, 0])

            # Convert local chunk position to global world position
            global_x = world_x + local_pos[0]
            global_y = local_pos[1] * self.HEIGHT_SCALE  # Scale height to world units
            global_z = world_z + local_pos[2]

            # Create unique entity ID using chunk coordinates
            entity_id = f"{prop_type}_{chunk.coords[0]}_{chunk.coords[1]}_{idx}"

            if prop_type == "rock":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y + ROCK_Y_OFFSET, global_z),
                    prop_type="rock",
                    state={
                        "radius": prop_desc.get("radius", 1.0),
                        "noise_seed": prop_desc.get("noise_seed", 0),
                    },
                )
            elif prop_type == "tree":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="tree",
                    state={
                        "axiom": prop_desc.get("axiom", "F"),
                        "rules": prop_desc.get("rules", {}),
                        "angle": prop_desc.get("angle", 25.0),
                        "iterations": prop_desc.get("iterations", 3),
                    },
                )
            elif prop_type == "bush":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y + ROCK_Y_OFFSET, global_z),
                    prop_type="bush",
                    state={
                        "radius": prop_desc.get("radius", 0.6),
                        "noise_seed": prop_desc.get("noise_seed", 0),
                        "leaf_density": prop_desc.get("leaf_density", 0.8),
                    },
                )
            elif prop_type == "pine_tree":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="pine_tree",
                    state={
                        "trunk_height": prop_desc.get("trunk_height", 3.0),
                        "trunk_radius": prop_desc.get("trunk_radius", 0.15),
                        "canopy_layers": prop_desc.get("canopy_layers", 3),
                        "canopy_radius": prop_desc.get("canopy_radius", 1.2),
                    },
                )
            elif prop_type == "dead_tree":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="dead_tree",
                    state={
                        "axiom": prop_desc.get("axiom", "F"),
                        "rules": prop_desc.get("rules", {"F": "F[+F][-F]"}),
                        "angle": prop_desc.get("angle", 35.0),
                        "iterations": prop_desc.get("iterations", 2),
                    },
                )
            elif prop_type == "fallen_log":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y + ROCK_Y_OFFSET, global_z),
                    prop_type="fallen_log",
                    state={
                        "length": prop_desc.get("length", 2.5),
                        "radius": prop_desc.get("radius", 0.2),
                        "rotation_y": prop_desc.get("rotation_y", 0.0),
                    },
                )
            elif prop_type == "boulder_cluster":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y + ROCK_Y_OFFSET, global_z),
                    prop_type="boulder_cluster",
                    state={
                        "sub_rocks": prop_desc.get("sub_rocks", []),
                    },
                )
            elif prop_type == "flower_patch":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="flower_patch",
                    state={
                        "stem_count": prop_desc.get("stem_count", 6),
                        "patch_radius": prop_desc.get("patch_radius", 0.5),
                        "color_seed": prop_desc.get("color_seed", 0),
                    },
                )
            elif prop_type == "mushroom":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="mushroom",
                    state={
                        "cap_radius": prop_desc.get("cap_radius", 0.3),
                        "stem_height": prop_desc.get("stem_height", 0.4),
                        "stem_radius": prop_desc.get("stem_radius", 0.06),
                    },
                )
            elif prop_type == "cactus":
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type="cactus",
                    state={
                        "main_height": prop_desc.get("main_height", 2.5),
                        "main_radius": prop_desc.get("main_radius", 0.18),
                        "arms": prop_desc.get("arms", []),
                    },
                )
            else:
                # Generic prop fallback
                prop = Prop(
                    entity_id=entity_id,
                    position=Vec3(global_x, global_y, global_z),
                    prop_type=prop_type,
                    state=prop_desc.get("state", {}),
                )

            spawned_id = self._world.spawn_entity(prop)
            if spawned_id:
                chunk.entity_ids.add(spawned_id)
                prop_count += 1

        # Clear pending props to save memory
        chunk.pending_props = []

        if prop_count > 0:
            print(f"Spawned {prop_count} props in chunk {chunk.coords}")

    # =========================================================================
    # World Loading (progressive chunk generation during LOADING state)
    # =========================================================================

    def _update_loading(self, dt: float) -> None:
        """Progressively load world chunks during the LOADING state.

        Called from ``_update`` when ``self._state == GameState.LOADING``.
        Generates several chunks per frame to fill the render distance as
        quickly as possible without blocking the render loop entirely,
        allowing the loading screen (with progress bar) to update smoothly.

        Once all required chunks are loaded, the player is repositioned on
        the terrain and the game transitions to ``PLAYING``.
        """
        if not self._chunk_manager:
            # No chunk manager — skip straight to playing
            self._loading_complete = True
            self._state = GameState.PLAYING
            return

        if self._game_manager.available:
            # Async path: C++ workers are generating; we just collect
            player = self._world.get_player() if self._world else None
            px = player.position.x if player else 0.0
            pz = player.position.z if player else 0.0
            self._game_manager.sync_frame(
                dt, px, pz,
                self.config.render_distance, self.config.sim_distance,
                self.config.chunk_size,
            )
            ready = self._game_manager.collect_ready_chunks(
                self.config.loading_chunks_per_frame
            )
            for result in ready:
                self._upload_async_chunk_result(result)
                self._loading_chunks_done += 1
        else:
            # Fallback: original synchronous loading
            batch = self.config.loading_chunks_per_frame
            new_chunks = self._chunk_manager.process_load_queue(max_per_frame=batch)
            for chunk in new_chunks:
                self._upload_chunk_mesh(chunk)
                self._loading_chunks_done += 1

        # Log progress periodically
        if self._loading_chunks_done > 0 and self._loading_chunks_done % 10 == 0:
            pct = (
                self._loading_chunks_done / max(self._loading_total_chunks, 1) * 100
            )
            print(
                f"Loading: {self._loading_chunks_done}/{self._loading_total_chunks} "
                f"chunks ({pct:.0f}%)"
            )

        # Check if we're done — require both enough chunks loaded AND
        # all sim-distance chunks have their meshes uploaded so the player
        # never spawns on invisible terrain.
        if self._game_manager.available:
            # C++ manages its own queue — don't check Python's (always empty)
            queue_empty = False
        else:
            queue_empty = len(self._chunk_manager._load_queue) == 0
        enough_chunks = self._loading_chunks_done >= self._loading_total_chunks

        if queue_empty or enough_chunks:
            sim_chunks = self._chunk_manager.get_sim_chunks()
            all_meshes_ready = all(c.is_mesh_uploaded for c in sim_chunks)
            if all_meshes_ready:
                self._finish_loading()

    def _finish_loading(self) -> None:
        """Transition from LOADING to PLAYING.

        Repositions the player on the terrain, resets physics velocity,
        and sets the game state to PLAYING.
        """
        self._loading_complete = True

        # Final player position adjustment
        player = self._world.get_player() if self._world else None
        if player and self._chunk_manager:
            spawn_x = player.position.x
            spawn_z = player.position.z
            chunk = self._chunk_manager.get_chunk_at_world(spawn_x, spawn_z)
            if chunk and chunk.heightmap is not None:
                local_x = int(spawn_x) % self.config.chunk_size
                local_z = int(spawn_z) % self.config.chunk_size
                local_x = min(max(local_x, 0), self.config.chunk_size - 1)
                local_z = min(max(local_z, 0), self.config.chunk_size - 1)
                terrain_y = float(chunk.heightmap[local_z, local_x]) * self.HEIGHT_SCALE
                player.position = Vec3(spawn_x, terrain_y + 2.0, spawn_z)
                player.velocity = Vec3(0, 0, 0)
                player.grounded = True
                self._terrain_heightmap = chunk.heightmap * self.HEIGHT_SCALE
                print(f"Player spawned at terrain height: {terrain_y + 2.0}")

        # Adjust NPC Y-positions to terrain height so they stand on the
        # surface instead of at their JSON-defined y=0 positions.
        if self._world and self._chunk_manager:
            for npc in self._world.get_npcs():
                chunk = self._chunk_manager.get_chunk_at_world(
                    npc.position.x, npc.position.z
                )
                if chunk and chunk.heightmap is not None:
                    wx, wz = self._chunk_manager.chunk_to_world(chunk.coords)
                    local_x = int(npc.position.x - wx)
                    local_z = int(npc.position.z - wz)
                    local_x = min(max(local_x, 0), self.config.chunk_size - 1)
                    local_z = min(max(local_z, 0), self.config.chunk_size - 1)
                    terrain_y = float(chunk.heightmap[local_z, local_x]) * self.HEIGHT_SCALE
                    npc.position = Vec3(npc.position.x, terrain_y + 1.0, npc.position.z)
                    self._world._update_entity_chunk(npc.entity_id, npc.position)

        # Set initial camera
        if self._graphics_bridge and self._player_controller:
            center = self.config.chunk_size // 2
            terrain_target_y = 0.0
            if self._terrain_heightmap is not None:
                h, w = self._terrain_heightmap.shape
                safe_z = min(center, h - 1)
                safe_x = min(center, w - 1)
                terrain_target_y = float(self._terrain_heightmap[safe_z, safe_x])
            camera_y = terrain_target_y + 35.0
            self._player_controller.camera.camera.position = Vec3(
                center, camera_y, center + 30
            )
            self._player_controller.camera.camera.target = Vec3(
                center, terrain_target_y, center
            )

        self._state = GameState.PLAYING
        print(
            f"World loaded! {self._loading_chunks_done} chunks generated. "
            f"Entering PLAYING state."
        )

    def _render_loading_screen(self) -> None:
        """Render a loading screen with progress bar via ImGui.

        Called from ``_render`` when the game is in ``LOADING`` state.
        Draws directly using the UI manager so it participates in the
        normal ImGui begin_frame / end_frame cycle.
        """
        if not self._ui_manager:
            return

        progress = (
            self._loading_chunks_done / max(self._loading_total_chunks, 1)
        )
        progress = min(progress, 1.0)

        left_down = False
        right_down = False
        if self._input_manager:
            left_down = self._input_manager.is_mouse_button_down(0)
            right_down = self._input_manager.is_mouse_button_down(2)

        self._ui_manager.begin_frame(
            dt=self.config.fixed_timestep,
            left_down=left_down,
            right_down=right_down,
        )

        # Centre the loading window
        w, h = 400, 120
        screen_w = self._backend.width if hasattr(self._backend, "width") else 1920
        screen_h = self._backend.height if hasattr(self._backend, "height") else 1080
        x = (screen_w - w) / 2
        y = (screen_h - h) / 2

        backend = self._ui_manager._backend
        if backend.begin_window("Loading World", x, y, w, h, flags=0):
            backend.text("Generating terrain...")
            backend.text(
                f"Chunks: {self._loading_chunks_done} / {self._loading_total_chunks}"
            )
            backend.progress_bar(progress, 350, 20)
            backend.text(f"{progress * 100:.0f}% complete")
            backend.text("")
            backend.text("Please wait...")
            backend.end_window()

        self._ui_manager.end_frame()

    def _update_physics_terrain(self, heightmap: "np.ndarray", size: int) -> None:
        """Update physics system with terrain height field."""
        try:
            from procengine.physics import HeightField2D
            
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

    def _setup_props(self, heightmap: "np.ndarray", size: int) -> None:
        """Generate and spawn props (rocks, trees) on the terrain."""
        if not self._world or not self._graphics_bridge:
            return

        try:
            import numpy as np
            from procengine.core.seed_registry import SeedRegistry
            from procengine.world.props import (
                generate_rock_descriptors,
                generate_tree_descriptors,
            )

            # Create a seed registry from world seed for deterministic prop generation
            registry = SeedRegistry(self.config.world_seed)

            # Generate rock descriptors
            rock_count = 15  # Number of rocks to generate
            rock_descriptors = generate_rock_descriptors(
                registry,
                rock_count,
                size=float(size),
            )

            # Generate tree descriptors
            tree_count = 10  # Number of trees to generate
            tree_descriptors = generate_tree_descriptors(
                registry,
                tree_count,
            )

            # Spawn rocks as Prop entities
            for i, rock_desc in enumerate(rock_descriptors):
                pos = rock_desc["position"]
                # Get terrain height at rock position
                px = int(pos[0]) % size
                pz = int(pos[2]) % size
                terrain_y = float(heightmap[pz, px])

                rock_prop = Prop(
                    entity_id=f"rock_{i}",
                    position=Vec3(pos[0], terrain_y + 0.1, pos[2]),  # Slightly above terrain
                    prop_type="rock",
                    state={
                        "radius": rock_desc["radius"],
                        "noise_seed": rock_desc.get("noise_seed", 0),
                    },
                )
                self._world.spawn_entity(rock_prop)

            # Spawn trees as Prop entities
            # Trees need position - use random positions based on seed
            tree_rng = registry.get_rng("tree_positions")
            for i, tree_desc in enumerate(tree_descriptors):
                # Generate position within terrain bounds
                pos_x = float(tree_rng.random() * size)
                pos_z = float(tree_rng.random() * size)

                # Get terrain height at tree position
                px = int(pos_x) % size
                pz = int(pos_z) % size
                terrain_y = float(heightmap[pz, px])

                tree_prop = Prop(
                    entity_id=f"tree_{i}",
                    position=Vec3(pos_x, terrain_y, pos_z),
                    prop_type="tree",
                    state={
                        "axiom": tree_desc["axiom"],
                        "rules": tree_desc["rules"],
                        "angle": tree_desc["angle"],
                        "iterations": tree_desc["iterations"],
                    },
                )
                self._world.spawn_entity(tree_prop)

            print(f"Props spawned: {rock_count} rocks, {tree_count} trees")

        except Exception as e:
            print(f"Warning: Could not setup props: {e}")
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
            
            # Get interaction target from player controller for UI prompts
            interaction_target = None
            if self._player_controller:
                interaction_target = self._player_controller.get_interaction_target()

            left_down = False
            right_down = False
            if self._input_manager:
                left_down = self._input_manager.is_mouse_button_down(0)
                right_down = self._input_manager.is_mouse_button_down(2)

            self._ui_manager.begin_frame(
                dt=self.config.fixed_timestep,
                left_down=left_down,
                right_down=right_down,
            )

            # Render appropriate UI based on state
            if self._state == GameState.PLAYING:
                self._ui_manager.render_hud(player, interaction_target)

            elif self._state == GameState.PAUSED:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_pause_menu()

            elif self._state == GameState.INVENTORY:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_inventory(player)

            elif self._state == GameState.DIALOGUE:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_dialogue()

            elif self._state == GameState.MENU:
                self._ui_manager.render_hud(player)
                self._ui_manager.render_settings(
                    debug_enabled=self.flags.get("debug_overlay", False),
                    vsync_enabled=self.flags.get("vsync", True),
                )

            # Developer console (rendered on top of any game state)
            if self._console.is_visible:
                self._ui_manager.render_console()

            # Notifications (rendered outside console, always visible)
            self._ui_manager.render_notifications()

            # Debug overlay
            if self.flags.get("debug_overlay", False):
                self._ui_manager.render_debug(
                    self._fps,
                    self._frame_count,
                    interaction_target,
                )

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
            self._backend.set_mouse_capture(False)
        elif self._state == GameState.PAUSED:
            self._state = GameState.PLAYING
            self._world.paused = False
            self._backend.set_mouse_capture(True)
        elif self._state in (GameState.INVENTORY, GameState.DIALOGUE):
            # Close current UI
            self._state = GameState.PLAYING
            if self._player_controller:
                self._player_controller.in_dialogue = False
                self._player_controller.in_menu = False
            self._backend.set_mouse_capture(True)

    def _on_inventory_pressed(self) -> None:
        """Handle inventory button press."""
        if self._state == GameState.PLAYING:
            self._state = GameState.INVENTORY
            if self._player_controller:
                self._player_controller.in_menu = True
            self._backend.set_mouse_capture(False)
        elif self._state == GameState.INVENTORY:
            self._state = GameState.PLAYING
            if self._player_controller:
                self._player_controller.in_menu = False
            self._backend.set_mouse_capture(True)

    def _on_settings_open(self) -> None:
        """Open settings menu."""
        if self._state == GameState.PAUSED:
            self._state = GameState.MENU
            if self._player_controller:
                self._player_controller.in_menu = True

    def _on_settings_close(self) -> None:
        """Close settings menu."""
        if self._state == GameState.MENU:
            self._state = GameState.PAUSED

    def _toggle_debug_overlay(self) -> None:
        """Toggle debug overlay setting."""
        self.flags["debug_overlay"] = not self.flags.get("debug_overlay", False)

    def _toggle_vsync(self) -> None:
        """Toggle vsync setting."""
        self.flags["vsync"] = not self.flags.get("vsync", True)
        if self._console:
            self._console.print("VSync setting will apply on next start.")

    def _on_dialogue_advance(self) -> None:
        """Handle dialogue advance."""
        if self._ui_manager and self._state == GameState.DIALOGUE:
            self._ui_manager.advance_dialogue()

    def _on_dialogue_option(self, option_index: int) -> None:
        """Handle dialogue option selection."""
        if self._ui_manager and self._state == GameState.DIALOGUE:
            self._ui_manager.select_dialogue_option(option_index)

    def _on_console_toggle(self) -> None:
        """Handle console toggle (tilde key)."""
        self._console.toggle()

    # Key-to-character mapping for console text input.
    _CONSOLE_CHAR_MAP: Dict[str, str] = {
        **{c: c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
        **{str(d): str(d) for d in range(10)},
        "SPACE": " ",
        "PERIOD": ".",
        "COMMA": ",",
        "MINUS": "-",
        "EQUALS": "=",
        "SLASH": "/",
        "BACKSLASH": "\\",
        "SEMICOLON": ";",
        "QUOTE": "'",
        "LEFTBRACKET": "[",
        "RIGHTBRACKET": "]",
    }

    def _process_console_input(self) -> None:
        """Route keyboard input to the Console when it is open.

        Reads the raw keys that were just pressed this frame from
        ``InputManager._keys_just_pressed`` and translates them into the
        appropriate Console method calls.  Supports modifier keys:

        - **Ctrl+Backspace** / **Ctrl+Delete** — delete word
        - **Ctrl+Left** / **Ctrl+Right** — move by word
        - **Shift+Left** / **Shift+Right** — extend selection
        - **Shift+Home** / **Shift+End** — select to line boundary
        - **Ctrl+A** — select all
        - **Ctrl+Z** — undo
        - **Ctrl+V** — paste (reads clipboard text from InputManager)
        """
        if not self._input_manager:
            return

        just = self._input_manager._keys_just_pressed
        mods = self._input_manager._active_modifiers
        ctrl_active = "CTRL" in mods or "LCTRL" in mods or "RCTRL" in mods
        shift_active = "SHIFT" in mods or "LSHIFT" in mods or "RSHIFT" in mods
        shift_map = {
            "COMMA": "<",
            "PERIOD": ">",
            "SLASH": "?",
            "MINUS": "_",
            "EQUALS": "+",
            "SEMICOLON": ":",
            "QUOTE": "\"",
            "LEFTBRACKET": "{",
            "RIGHTBRACKET": "}",
            "BACKSLASH": "|",
            "1": "!",
            "2": "@",
            "3": "#",
            "4": "$",
            "5": "%",
            "6": "^",
            "7": "&",
            "8": "*",
            "9": "(",
            "0": ")",
        }

        # --- Ctrl shortcuts ---
        if ctrl_active:
            if "A" in just:
                self._console.handle_select_all()
                return
            if "Z" in just:
                self._console.handle_undo()
                return
            if "V" in just:
                clipboard = getattr(self._input_manager, "get_clipboard_text", lambda: "")()
                if clipboard:
                    self._console.handle_paste(clipboard)
                return

        # --- Submit ---
        if "RETURN" in just:
            self._console.submit()
            return

        # --- Deletion ---
        if "BACKSPACE" in just:
            if ctrl_active:
                self._console.handle_backspace_word()
            else:
                self._console.handle_backspace()
        if "DELETE" in just:
            if ctrl_active:
                self._console.handle_delete_word()
            else:
                self._console.handle_delete()

        # --- Navigation ---
        if "UP" in just:
            self._console.handle_up()
        if "DOWN" in just:
            self._console.handle_down()
        if "LEFT" in just:
            if ctrl_active:
                self._console.handle_word_left(select=shift_active)
            else:
                self._console.handle_left(select=shift_active)
        if "RIGHT" in just:
            if ctrl_active:
                self._console.handle_word_right(select=shift_active)
            else:
                self._console.handle_right(select=shift_active)
        if "HOME" in just:
            self._console.handle_home(select=shift_active)
        if "END" in just:
            self._console.handle_end(select=shift_active)

        # --- Autocomplete / Escape ---
        if "TAB" in just:
            self._console.handle_tab()
        if "ESCAPE" in just:
            self._console.handle_escape()

        # --- Printable character input ---
        if not ctrl_active:
            for key in just:
                if shift_active and key in shift_map:
                    char = shift_map[key]
                else:
                    char = self._CONSOLE_CHAR_MAP.get(key)
                if char is not None:
                    self._console.handle_char(char)

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
            self._backend.set_mouse_capture(False)
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
        self._backend.set_mouse_capture(True)

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

    @property
    def console(self) -> Console:
        """Get the console."""
        return self._console

    def execute_command(self, command_str: str) -> CommandResult:
        """Execute a command string.

        Parameters
        ----------
        command_str:
            Command string to execute.

        Returns
        -------
        CommandResult:
            Result of command execution.
        """
        return command_registry.execute(command_str)

    def set_update_callback(self, callback: Callable[[float], None]) -> None:
        """Set custom update callback."""
        self._on_update = callback

    def set_render_callback(self, callback: Callable[[], None]) -> None:
        """Set custom render callback."""
        self._on_render = callback

    def set_ui_callback(self, callback: Callable[[], None]) -> None:
        """Set custom UI render callback.
        
        The callback is invoked after standard UI rendering is complete,
        allowing custom UI overlays (debug windows, ImGui panels, etc.)
        to be rendered. The callback is called once per frame.
        
        Example usage:
            def my_custom_ui():
                # Draw custom ImGui windows or overlays
                pass
            
            runner.set_ui_callback(my_custom_ui)
        """
        self._on_ui = callback

    @property
    def player_controller(self) -> Optional[PlayerController]:
        """Get the player controller.
        
        Provides access to camera, input state, and interaction context
        for custom UI rendering or external systems.
        """
        return self._player_controller

    @property
    def ui_manager(self) -> Optional["UIManager"]:
        """Get the UI manager.
        
        Provides access to UI components for custom rendering or
        direct component manipulation.
        """
        return self._ui_manager

    def quit(self) -> None:
        """Request game exit."""
        self._running = False
