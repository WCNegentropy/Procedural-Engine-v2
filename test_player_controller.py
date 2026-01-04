"""Tests for player_controller module.

Tests cover:
- Input state management
- Input binding system
- Input manager
- Camera system
- Player controller
"""
import pytest
import math

from player_controller import (
    InputAction,
    InputState,
    InputBinding,
    InputManager,
    Camera,
    CameraController,
    PlayerController,
    create_default_controller,
)
from physics import Vec3, HeightField2D
from game_api import Player, NPC, Prop, GameWorld
import numpy as np


# =============================================================================
# InputState Tests
# =============================================================================

class TestInputState:
    """Test InputState class."""

    def test_initial_state(self):
        state = InputState()
        assert len(state.pressed) == 0
        assert len(state.just_pressed) == 0
        assert len(state.just_released) == 0

    def test_is_pressed(self):
        state = InputState()
        state.pressed.add(InputAction.MOVE_FORWARD)

        assert state.is_pressed(InputAction.MOVE_FORWARD)
        assert not state.is_pressed(InputAction.MOVE_BACKWARD)

    def test_just_pressed(self):
        state = InputState()
        state.just_pressed.add(InputAction.JUMP)

        assert state.was_just_pressed(InputAction.JUMP)
        assert not state.was_just_pressed(InputAction.INTERACT)

    def test_just_released(self):
        state = InputState()
        state.just_released.add(InputAction.SPRINT)

        assert state.was_just_released(InputAction.SPRINT)
        assert not state.was_just_released(InputAction.CROUCH)

    def test_movement_vector_digital(self):
        state = InputState()

        # Forward
        state.pressed.add(InputAction.MOVE_FORWARD)
        x, y = state.get_movement_vector()
        assert x == 0
        assert y == 1

        # Forward + Right (should be normalized)
        state.pressed.add(InputAction.MOVE_RIGHT)
        x, y = state.get_movement_vector()
        assert abs(x - 0.707) < 0.01
        assert abs(y - 0.707) < 0.01

    def test_movement_vector_analog(self):
        state = InputState()
        state.move_x = 0.5
        state.move_y = -0.3

        x, y = state.get_movement_vector()
        assert x == 0.5
        assert y == -0.3

    def test_clear_frame_state(self):
        state = InputState()
        state.just_pressed.add(InputAction.JUMP)
        state.just_released.add(InputAction.SPRINT)
        state.mouse_delta_x = 10.0
        state.look_x = 0.5

        state.clear_frame_state()

        assert len(state.just_pressed) == 0
        assert len(state.just_released) == 0
        assert state.mouse_delta_x == 0.0
        assert state.look_x == 0.0


# =============================================================================
# InputBinding Tests
# =============================================================================

class TestInputBinding:
    """Test InputBinding class."""

    def test_simple_binding(self):
        binding = InputBinding(action=InputAction.JUMP, key="SPACE")

        assert binding.matches("SPACE", set())
        assert not binding.matches("W", set())

    def test_binding_with_modifiers(self):
        binding = InputBinding(
            action=InputAction.DEBUG_TOGGLE,
            key="D",
            modifiers={"CTRL", "SHIFT"},
        )

        # Must have both modifiers
        assert binding.matches("D", {"CTRL", "SHIFT"})
        assert binding.matches("D", {"CTRL", "SHIFT", "ALT"})  # Extra modifier OK
        assert not binding.matches("D", {"CTRL"})  # Missing SHIFT
        assert not binding.matches("D", set())  # No modifiers


# =============================================================================
# InputManager Tests
# =============================================================================

class TestInputManager:
    """Test InputManager class."""

    def test_default_bindings_loaded(self):
        manager = InputManager()

        # Should have WASD bindings
        w_bindings = manager.get_bindings_for_action(InputAction.MOVE_FORWARD)
        assert "W" in w_bindings

    def test_key_down_triggers_action(self):
        manager = InputManager()
        manager.begin_frame()

        manager.on_key_down("W")

        assert manager.state.is_pressed(InputAction.MOVE_FORWARD)
        assert manager.state.was_just_pressed(InputAction.MOVE_FORWARD)

    def test_key_up_releases_action(self):
        manager = InputManager()
        manager.begin_frame()

        manager.on_key_down("W")
        manager.begin_frame()  # Clear just_pressed
        manager.on_key_up("W")

        assert not manager.state.is_pressed(InputAction.MOVE_FORWARD)
        assert manager.state.was_just_released(InputAction.MOVE_FORWARD)

    def test_modifier_tracking(self):
        manager = InputManager()

        manager.on_key_down("LSHIFT")
        assert "SHIFT" in manager._active_modifiers

        manager.on_key_up("LSHIFT")
        assert "SHIFT" not in manager._active_modifiers

    def test_mouse_movement(self):
        manager = InputManager()
        manager.begin_frame()

        manager.on_mouse_move(100, 200, 5, -3)

        assert manager.state.mouse_x == 100
        assert manager.state.mouse_y == 200
        assert manager.state.mouse_delta_x == 5
        assert manager.state.mouse_delta_y == -3

    def test_mouse_button(self):
        manager = InputManager()
        manager.begin_frame()

        manager.on_mouse_button(0, True)  # Left click

        assert manager.state.is_pressed(InputAction.ATTACK)

    def test_gamepad_axis(self):
        manager = InputManager()
        manager.begin_frame()

        manager.on_gamepad_axis("LEFT_X", 0.5)
        manager.on_gamepad_axis("LEFT_Y", -0.3)

        assert manager.state.move_x == 0.5
        assert manager.state.move_y == -0.3

    def test_bind_and_unbind(self):
        manager = InputManager()

        # Add new binding
        manager.bind(InputAction.DEBUG_FLYMODE, "F")
        bindings = manager.get_bindings_for_action(InputAction.DEBUG_FLYMODE)
        assert "F" in bindings

        # Remove binding
        manager.unbind(InputAction.DEBUG_FLYMODE, "F")
        bindings = manager.get_bindings_for_action(InputAction.DEBUG_FLYMODE)
        assert "F" not in bindings

    def test_save_and_load_bindings(self):
        manager = InputManager()
        manager.bind(InputAction.DEBUG_TOGGLE, "F5")

        # Save
        data = manager.save_bindings()
        assert "DEBUG_TOGGLE" in data

        # Load into new manager
        manager2 = InputManager()
        manager2.bindings.clear()
        manager2.load_bindings(data)

        bindings = manager2.get_bindings_for_action(InputAction.DEBUG_TOGGLE)
        assert "F5" in bindings

    def test_multiple_keys_same_action(self):
        manager = InputManager()
        manager.begin_frame()

        # Press W (forward)
        manager.on_key_down("W")
        assert manager.state.is_pressed(InputAction.MOVE_FORWARD)

        # Press UP arrow (also forward)
        manager.on_key_down("UP")
        assert manager.state.is_pressed(InputAction.MOVE_FORWARD)

        # Release W, should still be pressed (UP is still down)
        manager.on_key_up("W")
        assert manager.state.is_pressed(InputAction.MOVE_FORWARD)

        # Release UP, now released
        manager.on_key_up("UP")
        assert not manager.state.is_pressed(InputAction.MOVE_FORWARD)


# =============================================================================
# Camera Tests
# =============================================================================

class TestCamera:
    """Test Camera class."""

    def test_initial_position(self):
        camera = Camera()
        camera.target = Vec3(0, 0, 0)
        camera.update_position()

        # Default: distance=5, pitch=0.3, yaw=0
        # Position should be behind and above target
        assert camera.position.z > 0  # Behind target
        assert camera.position.y > 0  # Above target

    def test_yaw_rotation(self):
        camera = Camera()
        camera.target = Vec3(0, 0, 0)
        camera.distance = 10
        camera.pitch = 0  # Horizontal

        # Yaw = 0 (facing -Z)
        camera.yaw = 0
        camera.update_position()
        assert abs(camera.position.z - 10) < 0.01
        assert abs(camera.position.x) < 0.01

        # Yaw = pi/2 (facing -X)
        camera.yaw = math.pi / 2
        camera.update_position()
        assert abs(camera.position.x - 10) < 0.01
        assert abs(camera.position.z) < 0.01

    def test_pitch_clamp(self):
        camera = Camera()
        camera.pitch = 2.0  # Above max
        camera.update_position()

        assert camera.pitch <= camera.max_pitch

    def test_distance_clamp(self):
        camera = Camera()
        camera.distance = 0.1  # Below min
        camera.update_position()

        assert camera.distance >= camera.min_distance

    def test_forward_direction(self):
        camera = Camera()
        camera.target = Vec3(10, 5, 10)
        camera.position = Vec3(0, 5, 0)

        forward = camera.get_forward()

        # Should point toward target
        assert forward.x > 0
        assert forward.z > 0
        assert abs(forward.length() - 1.0) < 0.01  # Normalized

    def test_right_direction(self):
        camera = Camera()
        camera.target = Vec3(0, 0, -10)
        camera.position = Vec3(0, 0, 0)

        right = camera.get_right()

        # Looking forward (-Z), right should be +X
        assert right.x > 0.9
        assert abs(right.y) < 0.01


# =============================================================================
# CameraController Tests
# =============================================================================

class TestCameraController:
    """Test CameraController class."""

    def test_follows_target(self):
        controller = CameraController()
        input_state = InputState()

        target = Vec3(10, 0, 10)
        controller.update(target, input_state, dt=1.0)

        # Camera target should move toward player position (with offset)
        assert controller.camera.target.x > 0
        assert controller.camera.target.z > 0

    def test_look_input_rotates_camera(self):
        controller = CameraController()
        input_state = InputState()
        input_state.look_x = 0.5  # Look right

        initial_yaw = controller.camera.yaw
        controller.update(Vec3(0, 0, 0), input_state, dt=0.1)

        # Yaw should have changed (negative because look_x is inverted)
        assert controller.camera.yaw != initial_yaw

    def test_zoom(self):
        controller = CameraController()
        initial_distance = controller.camera.distance

        controller.zoom(1.0)  # Zoom in

        assert controller.camera.distance < initial_distance

    def test_terrain_collision(self):
        controller = CameraController()
        controller.camera.collision_enabled = True
        controller.camera.target = Vec3(5, 10, 5)
        controller.camera.distance = 5
        controller.camera.pitch = -0.5  # Looking up, camera below target

        # Create terrain
        heights = np.full((20, 20), 8.0, dtype=np.float32)  # Ground at y=8
        heightfield = HeightField2D(heights=heights, cell_size=1.0)

        input_state = InputState()
        controller.update(Vec3(5, 10, 5), input_state, dt=0.1, heightfield=heightfield)

        # Camera should be above terrain
        ground = heightfield.sample(controller.camera.position.x, controller.camera.position.z)
        assert controller.camera.position.y >= ground


# =============================================================================
# PlayerController Tests
# =============================================================================

class TestPlayerController:
    """Test PlayerController class."""

    def test_creation(self):
        controller = create_default_controller()
        assert controller.input is not None
        assert controller.camera is not None

    def test_movement_updates_velocity(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0))
        world = GameWorld()

        # Simulate forward input
        controller.input.on_key_down("W")
        controller.input.begin_frame()
        controller.input.on_key_down("W")  # Re-trigger for just_pressed

        controller.update(player, world, dt=0.016)

        # Player should have velocity
        velocity_mag = math.sqrt(
            player.velocity.x ** 2 + player.velocity.z ** 2
        )
        assert velocity_mag > 0

    def test_sprint_increases_speed(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0), move_speed=5.0, sprint_multiplier=2.0)
        world = GameWorld()

        # Forward + Sprint
        controller.input.on_key_down("W")
        controller.input.on_key_down("LSHIFT")
        controller.input.begin_frame()
        controller.input.on_key_down("W")
        controller.input.on_key_down("LSHIFT")

        controller.update(player, world, dt=0.016)

        assert player.is_sprinting

    def test_jump_when_grounded(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0), jump_velocity=10.0)
        player.grounded = True
        world = GameWorld()

        # Jump
        controller.input.begin_frame()
        controller.input.on_key_down("SPACE")

        controller.update(player, world, dt=0.016)

        assert player.velocity.y == 10.0
        assert player.is_jumping

    def test_no_jump_when_airborne(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 10, 0))
        player.grounded = False
        player.velocity = Vec3(0, -5, 0)  # Falling
        world = GameWorld()

        # Try to jump
        controller.input.begin_frame()
        controller.input.on_key_down("SPACE")

        controller.update(player, world, dt=0.016)

        assert player.velocity.y == -5  # Unchanged

    def test_interaction_with_npc(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0), interaction_range=3.0)
        world = GameWorld()
        world._entities["player"] = player
        world._player = player

        # Create NPC in range
        npc = NPC(
            entity_id="test_npc",
            name="Test NPC",
            position=Vec3(1, 0, 0),
            dialogue_range=5.0,
        )
        world.spawn_entity(npc)

        # Interact
        controller.input.begin_frame()
        controller.input.on_key_down("E")

        controller.update(player, world, dt=0.016)

        assert controller.in_dialogue
        assert player.current_interaction_target == "test_npc"

    def test_dialogue_mode_disables_movement(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0))
        world = GameWorld()

        controller.in_dialogue = True

        # Try to move
        controller.input.begin_frame()
        controller.input.on_key_down("W")

        initial_velocity = Vec3(player.velocity.x, player.velocity.y, player.velocity.z)
        controller.update(player, world, dt=0.016)

        # Velocity should not change
        assert player.velocity.x == initial_velocity.x
        assert player.velocity.z == initial_velocity.z

    def test_menu_mode_disables_movement(self):
        controller = PlayerController()
        player = Player(position=Vec3(0, 0, 0))
        world = GameWorld()

        controller.in_menu = True

        # Try to move
        controller.input.begin_frame()
        controller.input.on_key_down("W")

        controller.update(player, world, dt=0.016)

        # Should not move
        assert player.velocity.x == 0
        assert player.velocity.z == 0

    def test_ui_callbacks(self):
        controller = PlayerController()
        player = Player()
        world = GameWorld()

        inventory_opened = [False]
        pause_opened = [False]

        controller.on_inventory_toggle = lambda: inventory_opened.__setitem__(0, True)
        controller.on_pause_toggle = lambda: pause_opened.__setitem__(0, True)

        # Press I for inventory
        controller.input.begin_frame()
        controller.input.on_key_down("I")
        controller.update(player, world, dt=0.016)
        assert inventory_opened[0]

        # Press ESC for pause
        controller.input.begin_frame()
        controller.input.on_key_down("ESCAPE")
        controller.update(player, world, dt=0.016)
        assert pause_opened[0]

    def test_dialogue_option_selection(self):
        controller = PlayerController()
        player = Player()
        world = GameWorld()
        controller.in_dialogue = True

        selected_option = [None]
        controller.on_dialogue_option = lambda i: selected_option.__setitem__(0, i)

        # Press 2 for option 2
        controller.input.begin_frame()
        controller.input.on_key_down("2")
        controller.update(player, world, dt=0.016)

        assert selected_option[0] == 1  # 0-indexed

    def test_end_dialogue(self):
        controller = PlayerController()
        controller.in_dialogue = True

        controller.end_dialogue()

        assert not controller.in_dialogue

    def test_menu_state(self):
        controller = PlayerController()

        controller.enter_menu()
        assert controller.in_menu

        controller.exit_menu()
        assert not controller.in_menu


# =============================================================================
# Integration Tests
# =============================================================================

class TestPlayerControllerIntegration:
    """Integration tests for player controller with game systems."""

    def test_full_movement_cycle(self):
        controller = create_default_controller()
        player = Player(position=Vec3(0, 0, 0), move_speed=5.0)
        world = GameWorld()

        # Create terrain
        heights = np.zeros((20, 20), dtype=np.float32)
        heightfield = HeightField2D(heights=heights, cell_size=1.0)
        world.set_heightfield(heightfield)
        world._player = player
        world._entities["player"] = player

        # Simulate multiple frames of forward movement
        controller.input.on_key_down("W")

        for _ in range(10):
            controller.input.begin_frame()
            controller.input.on_key_down("W")  # Keep held
            controller.update(player, world, dt=1/60)
            world.physics_step()

        # Player should have moved
        # Note: exact position depends on camera orientation
        velocity_mag = math.sqrt(player.velocity.x ** 2 + player.velocity.z ** 2)
        assert velocity_mag > 0

    def test_camera_follows_player(self):
        controller = create_default_controller()
        player = Player(position=Vec3(100, 0, 100))
        world = GameWorld()

        input_state = InputState()

        # Update controller
        controller.camera.update(player.position, input_state, dt=1.0)

        # Camera target should be near player
        dist_to_player = (controller.camera.camera.target - player.position).length()
        assert dist_to_player < 5  # Within reasonable distance (accounting for head offset)
