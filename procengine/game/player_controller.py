"""Player controller with input abstraction.

This module provides:
- Input abstraction layer for keyboard/mouse/gamepad
- PlayerController for translating input to player actions
- CameraController for third-person camera management
- InputManager for handling input state and bindings

The input system is designed to work with any backend (SDL, GLFW, etc.)
by abstracting input into actions that can be polled or event-driven.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from procengine.physics import Vec3

if TYPE_CHECKING:
    from procengine.game.game_api import Player, GameWorld, NPC, Entity

__all__ = [
    "InputAction",
    "InputState",
    "InputBinding",
    "InputManager",
    "PlayerController",
    "CameraController",
    "Camera",
]


# =============================================================================
# Input Actions
# =============================================================================


class InputAction(Enum):
    """Abstract input actions independent of physical keys."""

    # Movement
    MOVE_FORWARD = auto()
    MOVE_BACKWARD = auto()
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    JUMP = auto()
    SPRINT = auto()
    CROUCH = auto()

    # Camera
    LOOK_UP = auto()
    LOOK_DOWN = auto()
    LOOK_LEFT = auto()
    LOOK_RIGHT = auto()

    # Interaction
    INTERACT = auto()
    ATTACK = auto()
    USE_ITEM = auto()

    # UI
    INVENTORY = auto()
    JOURNAL = auto()
    MAP = auto()
    PAUSE = auto()
    CONSOLE = auto()

    # Dialogue
    DIALOGUE_NEXT = auto()
    DIALOGUE_OPTION_1 = auto()
    DIALOGUE_OPTION_2 = auto()
    DIALOGUE_OPTION_3 = auto()
    DIALOGUE_OPTION_4 = auto()

    # Debug
    DEBUG_TOGGLE = auto()
    DEBUG_FLYMODE = auto()


@dataclass
class InputState:
    """Current state of all input actions.

    Actions can be:
    - pressed: Currently held down
    - just_pressed: Pressed this frame (edge trigger)
    - just_released: Released this frame (edge trigger)
    """

    pressed: Set[InputAction] = field(default_factory=set)
    just_pressed: Set[InputAction] = field(default_factory=set)
    just_released: Set[InputAction] = field(default_factory=set)

    # Analog inputs (normalized -1 to 1)
    move_x: float = 0.0  # Left/right movement
    move_y: float = 0.0  # Forward/backward movement
    look_x: float = 0.0  # Horizontal look (mouse delta or stick)
    look_y: float = 0.0  # Vertical look (mouse delta or stick)

    # Mouse position (screen coordinates)
    mouse_x: float = 0.0
    mouse_y: float = 0.0
    mouse_delta_x: float = 0.0
    mouse_delta_y: float = 0.0

    def is_pressed(self, action: InputAction) -> bool:
        """Check if action is currently pressed."""
        return action in self.pressed

    def was_just_pressed(self, action: InputAction) -> bool:
        """Check if action was just pressed this frame."""
        return action in self.just_pressed

    def was_just_released(self, action: InputAction) -> bool:
        """Check if action was just released this frame."""
        return action in self.just_released

    def get_movement_vector(self) -> Tuple[float, float]:
        """Get normalized movement vector from input."""
        x = self.move_x
        y = self.move_y

        # Also check digital inputs
        if self.is_pressed(InputAction.MOVE_LEFT):
            x -= 1.0
        if self.is_pressed(InputAction.MOVE_RIGHT):
            x += 1.0
        if self.is_pressed(InputAction.MOVE_FORWARD):
            y += 1.0
        if self.is_pressed(InputAction.MOVE_BACKWARD):
            y -= 1.0

        # Normalize if magnitude > 1
        mag = math.sqrt(x * x + y * y)
        if mag > 1.0:
            x /= mag
            y /= mag

        return x, y

    def clear_frame_state(self) -> None:
        """Clear per-frame state (just_pressed, just_released, deltas)."""
        self.just_pressed.clear()
        self.just_released.clear()
        self.mouse_delta_x = 0.0
        self.mouse_delta_y = 0.0
        self.look_x = 0.0
        self.look_y = 0.0


# =============================================================================
# Input Binding
# =============================================================================


@dataclass
class InputBinding:
    """Binding from a physical key/button to an action."""

    action: InputAction
    key: str  # Key name (e.g., "W", "SPACE", "MOUSE1")
    modifiers: Set[str] = field(default_factory=set)  # e.g., {"CTRL", "SHIFT"}

    def matches(self, key: str, active_modifiers: Set[str]) -> bool:
        """Check if this binding matches the given key and modifiers."""
        if key != self.key:
            return False
        return self.modifiers.issubset(active_modifiers)


class InputManager:
    """Manages input bindings and state.

    The InputManager translates raw input events (key presses, mouse movement)
    into abstract InputActions that the game systems can use.
    """

    # Default key bindings
    DEFAULT_BINDINGS: List[Tuple[InputAction, str]] = [
        # Movement (WASD)
        (InputAction.MOVE_FORWARD, "W"),
        (InputAction.MOVE_BACKWARD, "S"),
        (InputAction.MOVE_LEFT, "A"),
        (InputAction.MOVE_RIGHT, "D"),
        (InputAction.JUMP, "SPACE"),
        (InputAction.SPRINT, "LSHIFT"),
        (InputAction.CROUCH, "LCTRL"),

        # Arrow keys alternative
        (InputAction.MOVE_FORWARD, "UP"),
        (InputAction.MOVE_BACKWARD, "DOWN"),
        (InputAction.MOVE_LEFT, "LEFT"),
        (InputAction.MOVE_RIGHT, "RIGHT"),

        # Interaction
        (InputAction.INTERACT, "E"),
        (InputAction.ATTACK, "MOUSE1"),
        (InputAction.USE_ITEM, "MOUSE2"),

        # UI
        (InputAction.INVENTORY, "I"),
        (InputAction.JOURNAL, "J"),
        (InputAction.MAP, "M"),
        (InputAction.PAUSE, "ESCAPE"),
        (InputAction.CONSOLE, "GRAVE"),

        # Dialogue
        (InputAction.DIALOGUE_NEXT, "SPACE"),
        (InputAction.DIALOGUE_NEXT, "RETURN"),
        (InputAction.DIALOGUE_OPTION_1, "1"),
        (InputAction.DIALOGUE_OPTION_2, "2"),
        (InputAction.DIALOGUE_OPTION_3, "3"),
        (InputAction.DIALOGUE_OPTION_4, "4"),

        # Debug
        (InputAction.DEBUG_TOGGLE, "F3"),
        (InputAction.DEBUG_FLYMODE, "F4"),
    ]

    def __init__(self) -> None:
        self.bindings: List[InputBinding] = []
        self.state = InputState()
        self._active_modifiers: Set[str] = set()

        # Key state tracking for edge detection
        self._keys_down: Set[str] = set()

        # Load default bindings
        self.load_default_bindings()

    def load_default_bindings(self) -> None:
        """Load the default key bindings."""
        self.bindings.clear()
        for action, key in self.DEFAULT_BINDINGS:
            self.bindings.append(InputBinding(action=action, key=key))

    def bind(self, action: InputAction, key: str, modifiers: Optional[Set[str]] = None) -> None:
        """Add a key binding for an action."""
        self.bindings.append(InputBinding(
            action=action,
            key=key,
            modifiers=modifiers or set(),
        ))

    def unbind(self, action: InputAction, key: Optional[str] = None) -> None:
        """Remove bindings for an action (optionally only for a specific key)."""
        self.bindings = [
            b for b in self.bindings
            if not (b.action == action and (key is None or b.key == key))
        ]

    def get_bindings_for_action(self, action: InputAction) -> List[str]:
        """Get all keys bound to an action."""
        return [b.key for b in self.bindings if b.action == action]

    def begin_frame(self) -> None:
        """Call at the start of each frame to prepare input state."""
        self.state.clear_frame_state()

    def on_key_down(self, key: str) -> None:
        """Handle a key press event."""
        key = key.upper()

        # Track modifier keys
        if key in ("LSHIFT", "RSHIFT", "SHIFT"):
            self._active_modifiers.add("SHIFT")
        elif key in ("LCTRL", "RCTRL", "CTRL"):
            self._active_modifiers.add("CTRL")
        elif key in ("LALT", "RALT", "ALT"):
            self._active_modifiers.add("ALT")

        # Check if this is a new press
        is_new = key not in self._keys_down
        self._keys_down.add(key)

        # Find matching bindings and update action state
        for binding in self.bindings:
            if binding.matches(key, self._active_modifiers):
                self.state.pressed.add(binding.action)
                if is_new:
                    self.state.just_pressed.add(binding.action)

    def on_key_up(self, key: str) -> None:
        """Handle a key release event."""
        key = key.upper()

        # Track modifier keys
        if key in ("LSHIFT", "RSHIFT", "SHIFT"):
            self._active_modifiers.discard("SHIFT")
        elif key in ("LCTRL", "RCTRL", "CTRL"):
            self._active_modifiers.discard("CTRL")
        elif key in ("LALT", "RALT", "ALT"):
            self._active_modifiers.discard("ALT")

        self._keys_down.discard(key)

        # Find matching bindings and update action state
        for binding in self.bindings:
            if binding.key == key:
                # Check if any other key is still holding this action
                other_keys_holding = any(
                    b.key in self._keys_down and b.action == binding.action
                    for b in self.bindings
                    if b.key != key
                )
                if not other_keys_holding:
                    self.state.pressed.discard(binding.action)
                    self.state.just_released.add(binding.action)

    def on_mouse_move(self, x: float, y: float, dx: float, dy: float) -> None:
        """Handle mouse movement."""
        self.state.mouse_x = x
        self.state.mouse_y = y
        self.state.mouse_delta_x += dx
        self.state.mouse_delta_y += dy

        # Apply mouse delta to look input (with sensitivity)
        sensitivity = 0.002
        self.state.look_x += dx * sensitivity
        self.state.look_y += dy * sensitivity

    def on_mouse_button(self, button: int, pressed: bool) -> None:
        """Handle mouse button events."""
        key = f"MOUSE{button + 1}"  # MOUSE1, MOUSE2, MOUSE3
        if pressed:
            self.on_key_down(key)
        else:
            self.on_key_up(key)

    def on_gamepad_axis(self, axis: str, value: float) -> None:
        """Handle gamepad analog input."""
        if axis == "LEFT_X":
            self.state.move_x = value
        elif axis == "LEFT_Y":
            self.state.move_y = value
        elif axis == "RIGHT_X":
            self.state.look_x = value * 2.0  # Scale for look speed
        elif axis == "RIGHT_Y":
            self.state.look_y = value * 2.0

    def save_bindings(self) -> Dict[str, List[str]]:
        """Export bindings as a dictionary for saving."""
        result: Dict[str, List[str]] = {}
        for binding in self.bindings:
            action_name = binding.action.name
            if action_name not in result:
                result[action_name] = []
            key_str = binding.key
            if binding.modifiers:
                key_str = "+".join(sorted(binding.modifiers)) + "+" + key_str
            result[action_name].append(key_str)
        return result

    def load_bindings(self, data: Dict[str, List[str]]) -> None:
        """Import bindings from a dictionary."""
        self.bindings.clear()
        for action_name, keys in data.items():
            try:
                action = InputAction[action_name]
            except KeyError:
                continue  # Unknown action, skip

            for key_str in keys:
                parts = key_str.split("+")
                key = parts[-1]
                modifiers = set(parts[:-1]) if len(parts) > 1 else set()
                self.bindings.append(InputBinding(
                    action=action,
                    key=key,
                    modifiers=modifiers,
                ))


# =============================================================================
# Camera
# =============================================================================


@dataclass
class Camera:
    """Camera state for rendering.

    Uses spherical coordinates for orbit-style third-person camera.
    """

    # Position (computed from target + offset)
    position: Vec3 = field(default_factory=Vec3)

    # Target (what the camera looks at)
    target: Vec3 = field(default_factory=Vec3)

    # Spherical offset from target
    distance: float = 5.0  # Distance from target
    yaw: float = 0.0  # Horizontal angle (radians)
    pitch: float = 0.3  # Vertical angle (radians), 0 = horizontal

    # Constraints
    min_pitch: float = -1.4  # About -80 degrees
    max_pitch: float = 1.4  # About 80 degrees
    min_distance: float = 1.0
    max_distance: float = 20.0

    # Smoothing
    position_smoothing: float = 10.0  # Higher = faster follow
    rotation_smoothing: float = 15.0

    # Collision
    collision_enabled: bool = True
    collision_radius: float = 0.3

    def get_forward(self) -> Vec3:
        """Get the camera's forward direction (toward target)."""
        direction = self.target - self.position
        length = direction.length()
        if length > 0:
            return direction / length
        return Vec3(0, 0, -1)

    def get_right(self) -> Vec3:
        """Get the camera's right direction."""
        forward = self.get_forward()
        up = Vec3(0, 1, 0)
        return forward.cross(up).normalized()

    def get_up(self) -> Vec3:
        """Get the camera's up direction."""
        forward = self.get_forward()
        right = self.get_right()
        return right.cross(forward).normalized()

    def update_position(self) -> None:
        """Update camera position based on spherical coordinates."""
        # Clamp pitch
        self.pitch = max(self.min_pitch, min(self.max_pitch, self.pitch))
        self.distance = max(self.min_distance, min(self.max_distance, self.distance))

        # Calculate offset from target using spherical coordinates
        cos_pitch = math.cos(self.pitch)
        sin_pitch = math.sin(self.pitch)
        cos_yaw = math.cos(self.yaw)
        sin_yaw = math.sin(self.yaw)

        offset = Vec3(
            self.distance * cos_pitch * sin_yaw,
            self.distance * sin_pitch,
            self.distance * cos_pitch * cos_yaw,
        )

        self.position = self.target + offset

    def to_dict(self) -> Dict:
        """Serialize camera state."""
        return {
            "distance": self.distance,
            "yaw": self.yaw,
            "pitch": self.pitch,
        }

    def from_dict(self, data: Dict) -> None:
        """Deserialize camera state."""
        self.distance = data.get("distance", 5.0)
        self.yaw = data.get("yaw", 0.0)
        self.pitch = data.get("pitch", 0.3)


class CameraController:
    """Controls camera behavior for third-person view.

    Handles:
    - Following the player with smooth interpolation
    - Mouse/stick look for rotation
    - Zoom control
    - Collision with terrain to prevent clipping
    """

    def __init__(self, camera: Optional[Camera] = None) -> None:
        self.camera = camera or Camera()
        self._target_yaw: float = 0.0
        self._target_pitch: float = 0.3

    def update(
        self,
        target_position: Vec3,
        input_state: InputState,
        dt: float,
        heightfield: Optional["HeightField2D"] = None,
    ) -> None:
        """Update camera based on target and input.

        Parameters
        ----------
        target_position:
            Position to follow (usually player position + offset).
        input_state:
            Current input state for look control.
        dt:
            Delta time.
        heightfield:
            Optional terrain for collision.
        """
        # Update rotation from input
        self._target_yaw -= input_state.look_x
        self._target_pitch -= input_state.look_y

        # Clamp pitch
        self._target_pitch = max(
            self.camera.min_pitch,
            min(self.camera.max_pitch, self._target_pitch),
        )

        # Smooth rotation
        rot_speed = self.camera.rotation_smoothing * dt
        self.camera.yaw += (self._target_yaw - self.camera.yaw) * min(1.0, rot_speed)
        self.camera.pitch += (self._target_pitch - self.camera.pitch) * min(1.0, rot_speed)

        # Smooth target follow (with vertical offset for head height)
        target_with_offset = target_position + Vec3(0, 1.6, 0)
        pos_speed = self.camera.position_smoothing * dt

        self.camera.target = Vec3(
            self.camera.target.x + (target_with_offset.x - self.camera.target.x) * min(1.0, pos_speed),
            self.camera.target.y + (target_with_offset.y - self.camera.target.y) * min(1.0, pos_speed),
            self.camera.target.z + (target_with_offset.z - self.camera.target.z) * min(1.0, pos_speed),
        )

        # Update camera position
        self.camera.update_position()

        # Terrain collision
        if heightfield and self.camera.collision_enabled:
            self._resolve_terrain_collision(heightfield)

    def _resolve_terrain_collision(self, heightfield: "HeightField2D") -> None:
        """Prevent camera from going below terrain."""
        from procengine.physics import HeightField2D

        ground_height = heightfield.sample(
            self.camera.position.x,
            self.camera.position.z,
        )
        min_height = ground_height + self.camera.collision_radius

        if self.camera.position.y < min_height:
            self.camera.position = Vec3(
                self.camera.position.x,
                min_height,
                self.camera.position.z,
            )

    def zoom(self, delta: float) -> None:
        """Adjust camera distance (zoom in/out)."""
        self.camera.distance = max(
            self.camera.min_distance,
            min(self.camera.max_distance, self.camera.distance - delta),
        )

    def reset(self, yaw: float = 0.0, pitch: float = 0.3) -> None:
        """Reset camera rotation."""
        self._target_yaw = yaw
        self._target_pitch = pitch
        self.camera.yaw = yaw
        self.camera.pitch = pitch


# =============================================================================
# Player Controller
# =============================================================================


class PlayerController:
    """Translates input into player actions.

    Handles:
    - Movement based on camera direction
    - Jumping with ground check
    - Sprinting toggle
    - Interaction with nearby entities
    - UI toggles
    """

    def __init__(
        self,
        input_manager: Optional[InputManager] = None,
        camera_controller: Optional[CameraController] = None,
    ) -> None:
        self.input = input_manager or InputManager()
        self.camera = camera_controller or CameraController()

        # Controller state
        self.movement_enabled: bool = True
        self.interaction_enabled: bool = True
        self.in_dialogue: bool = False
        self.in_menu: bool = False

        # Callbacks for UI events
        self.on_inventory_toggle: Optional[Callable[[], None]] = None
        self.on_journal_toggle: Optional[Callable[[], None]] = None
        self.on_map_toggle: Optional[Callable[[], None]] = None
        self.on_pause_toggle: Optional[Callable[[], None]] = None
        self.on_console_toggle: Optional[Callable[[], None]] = None
        self.on_dialogue_advance: Optional[Callable[[], None]] = None
        self.on_dialogue_option: Optional[Callable[[int], None]] = None

    def update(
        self,
        player: "Player",
        world: "GameWorld",
        dt: float,
    ) -> None:
        """Update player based on input.

        Parameters
        ----------
        player:
            The player entity to control.
        world:
            The game world for context.
        dt:
            Delta time.
        """
        state = self.input.state

        # Handle UI inputs first (always active)
        self._handle_ui_input(state)

        # Handle dialogue input if in dialogue
        if self.in_dialogue:
            self._handle_dialogue_input(state)
            return  # Skip movement while in dialogue

        # Skip movement if disabled or in menu
        if not self.movement_enabled or self.in_menu:
            return

        # Update camera
        self.camera.update(
            player.position,
            state,
            dt,
            world._heightfield,
        )

        # Get movement input
        move_x, move_y = state.get_movement_vector()

        if move_x != 0 or move_y != 0:
            # Transform movement relative to camera direction
            cam_forward = self.camera.camera.get_forward()
            cam_right = self.camera.camera.get_right()

            # Project to XZ plane
            forward_xz = Vec3(cam_forward.x, 0, cam_forward.z).normalized()
            right_xz = Vec3(cam_right.x, 0, cam_right.z).normalized()

            # Calculate world-space movement direction
            move_dir = (right_xz * move_x + forward_xz * move_y).normalized()

            # Apply speed
            speed = player.get_move_speed()
            player.is_sprinting = state.is_pressed(InputAction.SPRINT)

            # Update velocity (physics will handle actual movement)
            player.velocity = Vec3(
                move_dir.x * speed,
                player.velocity.y,  # Preserve vertical velocity
                move_dir.z * speed,
            )

            # Face movement direction
            if move_dir.length() > 0.1:
                player.rotation = math.atan2(move_dir.x, move_dir.z)
        else:
            # No input, stop horizontal movement
            player.velocity = Vec3(0, player.velocity.y, 0)
            player.is_sprinting = False

        # Handle jumping
        if state.was_just_pressed(InputAction.JUMP) and player.grounded:
            player.velocity = Vec3(
                player.velocity.x,
                player.jump_velocity,
                player.velocity.z,
            )
            player.is_jumping = True
            player.grounded = False

        # Handle interaction
        if state.was_just_pressed(InputAction.INTERACT):
            self._handle_interaction(player, world)

    def _handle_ui_input(self, state: InputState) -> None:
        """Handle UI toggle inputs."""
        if state.was_just_pressed(InputAction.INVENTORY) and self.on_inventory_toggle:
            self.on_inventory_toggle()

        if state.was_just_pressed(InputAction.JOURNAL) and self.on_journal_toggle:
            self.on_journal_toggle()

        if state.was_just_pressed(InputAction.MAP) and self.on_map_toggle:
            self.on_map_toggle()

        if state.was_just_pressed(InputAction.PAUSE) and self.on_pause_toggle:
            self.on_pause_toggle()

        if state.was_just_pressed(InputAction.CONSOLE) and self.on_console_toggle:
            self.on_console_toggle()

    def _handle_dialogue_input(self, state: InputState) -> None:
        """Handle dialogue navigation inputs."""
        if state.was_just_pressed(InputAction.DIALOGUE_NEXT):
            if self.on_dialogue_advance:
                self.on_dialogue_advance()

        for i, action in enumerate([
            InputAction.DIALOGUE_OPTION_1,
            InputAction.DIALOGUE_OPTION_2,
            InputAction.DIALOGUE_OPTION_3,
            InputAction.DIALOGUE_OPTION_4,
        ]):
            if state.was_just_pressed(action) and self.on_dialogue_option:
                self.on_dialogue_option(i)

    def _handle_interaction(self, player: "Player", world: "GameWorld") -> None:
        """Handle interaction with nearby entities."""
        if not self.interaction_enabled:
            return

        # Find interactable entities in range
        nearby = world.get_entities_in_range(player.position, player.interaction_range)

        best_target: Optional[Entity] = None
        best_distance = float("inf")

        for entity in nearby:
            if entity.entity_id == player.entity_id:
                continue

            # Check if entity is interactable
            from procengine.game.game_api import NPC, Prop

            if isinstance(entity, NPC):
                if entity.can_talk(player.position):
                    distance = (entity.position - player.position).length()
                    if distance < best_distance:
                        best_target = entity
                        best_distance = distance

            elif isinstance(entity, Prop):
                if entity.interactable:
                    distance = (entity.position - player.position).length()
                    if distance < best_distance:
                        best_target = entity
                        best_distance = distance

        # Interact with best target
        if best_target:
            from procengine.game.game_api import NPC, Prop

            if isinstance(best_target, NPC):
                world.initiate_dialogue(best_target.entity_id)
                self.in_dialogue = True
                player.current_interaction_target = best_target.entity_id

            elif isinstance(best_target, Prop):
                # Execute prop interaction
                self._interact_with_prop(best_target, player, world)

    def _interact_with_prop(
        self,
        prop: "Prop",
        player: "Player",
        world: "GameWorld",
    ) -> None:
        """Handle interaction with a prop."""
        from procengine.game.game_api import Prop, Item

        action = prop.interaction_action

        if action == "open":
            # Toggle open state (for doors, chests)
            prop.state["open"] = not prop.state.get("open", False)

        elif action == "pickup":
            # Pick up as item
            item_id = prop.state.get("item_id")
            count = prop.state.get("count", 1)
            if item_id:
                added = player.inventory.add_item(item_id, count)
                if added > 0:
                    world.destroy_entity(prop.entity_id)

        elif action == "activate":
            # Generic activation (triggers, switches)
            prop.state["activated"] = True

    def end_dialogue(self) -> None:
        """Called when dialogue ends."""
        self.in_dialogue = False

    def enter_menu(self) -> None:
        """Called when entering a menu."""
        self.in_menu = True

    def exit_menu(self) -> None:
        """Called when exiting a menu."""
        self.in_menu = False


# =============================================================================
# Convenience Functions
# =============================================================================


def create_default_controller() -> PlayerController:
    """Create a PlayerController with default settings."""
    return PlayerController(
        input_manager=InputManager(),
        camera_controller=CameraController(),
    )
