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

        # Initialize graphics bridge
        self._graphics_bridge = GraphicsBridge()
        graphics_available = self._graphics_bridge.initialize(
            width=self.config.window_width,
            height=self.config.window_height,
            enable_validation=self.config.enable_debug,
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

    def _init_graphics_resources(self) -> None:
        """Initialize graphics resources (pipelines, default meshes)."""
        if not self._graphics_bridge:
            return

        # Create default material pipelines
        default_vertex = """
            #version 450
            layout(location = 0) in vec3 inPosition;
            layout(location = 1) in vec3 inNormal;
            layout(location = 2) in vec2 inUV;
            layout(push_constant) uniform PushConstants {
                mat4 model;
                vec4 color;
            } push;
            layout(set = 0, binding = 0) uniform UBO {
                mat4 view;
                mat4 proj;
                vec3 cameraPos;
            } ubo;
            layout(location = 0) out vec3 fragNormal;
            layout(location = 1) out vec3 fragWorldPos;
            layout(location = 2) out vec2 fragUV;
            void main() {
                vec4 worldPos = push.model * vec4(inPosition, 1.0);
                gl_Position = ubo.proj * ubo.view * worldPos;
                fragNormal = mat3(push.model) * inNormal;
                fragWorldPos = worldPos.xyz;
                fragUV = inUV;
            }
        """

        default_fragment = """
            #version 450
            layout(location = 0) in vec3 fragNormal;
            layout(location = 1) in vec3 fragWorldPos;
            layout(location = 2) in vec2 fragUV;
            layout(push_constant) uniform PushConstants {
                mat4 model;
                vec4 color;
            } push;
            layout(location = 0) out vec4 outColor;
            void main() {
                vec3 lightDir = normalize(vec3(0.5, 1.0, 0.3));
                float diff = max(dot(normalize(fragNormal), lightDir), 0.0);
                vec3 ambient = 0.2 * push.color.rgb;
                vec3 diffuse = diff * push.color.rgb;
                outColor = vec4(ambient + diffuse, push.color.a);
            }
        """

        self._graphics_bridge.create_material_pipeline(
            "default",
            default_vertex,
            default_fragment,
        )

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
                    self._player_controller.camera_controller
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
            mesh_name = self._get_or_create_entity_mesh(player.id, "player")
            self._graphics_bridge.draw_entity(
                mesh_name,
                "default",
                player.position,
                rotation=0.0,
                scale=1.0,
            )

        # Render NPCs
        for entity in self._world.get_all_entities():
            if isinstance(entity, NPC):
                mesh_name = self._get_or_create_entity_mesh(entity.id, "npc")
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

        # For now, use a placeholder mesh name based on type
        # In a full implementation, this would generate/load the actual mesh
        mesh_name = f"{entity_type}_{entity_id}"

        # Create a placeholder mesh entry in headless mode
        if self._graphics_bridge and self._graphics_bridge.is_headless:
            self._graphics_bridge._meshes[mesh_name] = {
                "type": entity_type,
                "entity_id": entity_id,
            }
        else:
            # In real graphics mode, we would upload actual geometry here
            # For now, create a simple placeholder
            self._graphics_bridge._meshes[mesh_name] = {
                "type": entity_type,
                "entity_id": entity_id,
            }

        self._entity_meshes[entity_id] = mesh_name
        return mesh_name

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
