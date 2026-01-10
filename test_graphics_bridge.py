"""Tests for graphics_bridge module."""
import pytest
import math

from graphics_bridge import (
    GraphicsBridge,
    RenderState,
    create_identity_matrix,
    create_translation_matrix,
    create_rotation_y_matrix,
    create_scale_matrix,
    create_transform_matrix,
    multiply_matrices,
)
from physics import Vec3


# =============================================================================
# Matrix Utility Tests
# =============================================================================


class TestMatrixUtilities:
    """Tests for matrix utility functions."""

    def test_identity_matrix(self):
        """Test identity matrix creation."""
        identity = create_identity_matrix()

        assert len(identity) == 16

        # Check diagonal is 1, rest is 0
        for i in range(4):
            for j in range(4):
                expected = 1.0 if i == j else 0.0
                assert identity[i + j * 4] == expected

    def test_translation_matrix(self):
        """Test translation matrix creation."""
        trans = create_translation_matrix(10, 20, 30)

        # Translation is in bottom row (column-major)
        assert trans[12] == 10  # x
        assert trans[13] == 20  # y
        assert trans[14] == 30  # z
        assert trans[15] == 1   # w

    def test_rotation_y_matrix(self):
        """Test Y-axis rotation matrix."""
        # 90 degree rotation
        angle = math.pi / 2
        rot = create_rotation_y_matrix(angle)

        # cos(90) = 0, sin(90) = 1
        assert rot[0] == pytest.approx(0, abs=1e-10)   # cos
        assert rot[2] == pytest.approx(-1, abs=1e-10)  # -sin
        assert rot[8] == pytest.approx(1, abs=1e-10)   # sin
        assert rot[10] == pytest.approx(0, abs=1e-10)  # cos

    def test_scale_matrix(self):
        """Test scale matrix creation."""
        scale = create_scale_matrix(2, 3, 4)

        assert scale[0] == 2   # sx
        assert scale[5] == 3   # sy
        assert scale[10] == 4  # sz
        assert scale[15] == 1  # w

    def test_matrix_multiply_identity(self):
        """Test multiplying by identity produces same matrix."""
        trans = create_translation_matrix(5, 10, 15)
        identity = create_identity_matrix()

        result = multiply_matrices(trans, identity)

        for i in range(16):
            assert result[i] == pytest.approx(trans[i])

    def test_transform_matrix_combined(self):
        """Test combined transform matrix."""
        pos = Vec3(10, 0, 20)
        rotation = math.pi / 4  # 45 degrees
        scale = 2.0

        transform = create_transform_matrix(pos, rotation, scale)

        # Should be 16 elements
        assert len(transform) == 16

        # Translation should be present
        assert transform[12] == pytest.approx(10)  # x
        assert transform[14] == pytest.approx(20)  # z


# =============================================================================
# RenderState Tests
# =============================================================================


class TestRenderState:
    """Tests for RenderState."""

    def test_default_values(self):
        """Test default render state values."""
        state = RenderState()

        assert state.frame_count == 0
        assert state.draw_calls == 0
        assert state.triangles == 0
        assert state.vertices == 0
        assert state.camera_position == (0.0, 0.0, 0.0)

    def test_state_update(self):
        """Test render state can be updated."""
        state = RenderState()

        state.frame_count = 100
        state.draw_calls = 50
        state.triangles = 10000
        state.camera_position = (1.0, 2.0, 3.0)

        assert state.frame_count == 100
        assert state.draw_calls == 50
        assert state.triangles == 10000
        assert state.camera_position == (1.0, 2.0, 3.0)


# =============================================================================
# GraphicsBridge Tests
# =============================================================================


class TestGraphicsBridge:
    """Tests for GraphicsBridge."""

    def test_initialization_headless(self):
        """Test bridge initializes in headless mode."""
        bridge = GraphicsBridge()

        # Without graphics module, should fall back to headless
        result = bridge.initialize()

        assert bridge.is_initialized
        assert bridge.is_headless  # No Vulkan in test environment

    def test_camera_direct_set(self):
        """Test setting camera directly."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.set_camera_direct(
            position=(10, 20, 30),
            target=(0, 0, 0),
            fov=75.0,
        )

        assert bridge.render_state.camera_position == (10, 20, 30)
        assert bridge.render_state.camera_target == (0, 0, 0)

    def test_camera_from_controller(self):
        """Test setting camera from controller."""
        from player_controller import CameraController, Camera

        bridge = GraphicsBridge()
        bridge.initialize()

        controller = CameraController()
        controller.camera.position = Vec3(5, 10, 15)
        controller.camera.target = Vec3(0, 0, 0)

        bridge.set_camera_from_controller(controller)

        assert bridge.render_state.camera_position == (5, 10, 15)
        assert bridge.render_state.camera_target == (0, 0, 0)

    def test_mesh_upload_headless(self):
        """Test mesh upload in headless mode."""
        bridge = GraphicsBridge()
        bridge.initialize()

        # In headless mode, upload should succeed and store reference
        result = bridge.upload_mesh("test_mesh", {"vertices": [], "indices": []})
        assert result is True

        mesh = bridge.get_mesh("test_mesh")
        assert mesh is not None

    def test_mesh_destroy(self):
        """Test mesh destruction."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.upload_mesh("temp_mesh", {})
        assert bridge.get_mesh("temp_mesh") is not None

        bridge.destroy_mesh("temp_mesh")
        assert bridge.get_mesh("temp_mesh") is None

    def test_terrain_mesh_upload(self):
        """Test terrain mesh upload."""
        import numpy as np

        bridge = GraphicsBridge()
        bridge.initialize()

        heightmap = np.random.rand(64, 64).astype(np.float32)

        result = bridge.upload_terrain_mesh("terrain", heightmap, cell_size=1.0)
        assert result is True

        mesh = bridge.get_mesh("terrain")
        assert mesh is not None
        assert mesh["type"] == "terrain"

    def test_pipeline_creation_headless(self):
        """Test pipeline creation in headless mode."""
        bridge = GraphicsBridge()
        bridge.initialize()

        vertex_shader = "void main() { gl_Position = vec4(0); }"
        fragment_shader = "void main() { gl_FragColor = vec4(1); }"

        result = bridge.create_material_pipeline("test_mat", vertex_shader, fragment_shader)
        assert result is True

        pipeline = bridge.get_pipeline("test_mat")
        assert pipeline is not None

    def test_frame_rendering(self):
        """Test frame begin/end."""
        bridge = GraphicsBridge()
        bridge.initialize()

        initial_frame = bridge.render_state.frame_count

        bridge.begin_frame()
        bridge.end_frame()

        assert bridge.render_state.frame_count == initial_frame + 1

    def test_draw_mesh_increments_draw_calls(self):
        """Test drawing mesh increments draw call counter."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.upload_mesh("box", {})
        bridge.create_material_pipeline("basic", "", "")

        bridge.begin_frame()
        assert bridge.render_state.draw_calls == 0

        bridge.draw_mesh("box", "basic")
        assert bridge.render_state.draw_calls == 1

        bridge.draw_mesh("box", "basic")
        assert bridge.render_state.draw_calls == 2

        bridge.end_frame()

    def test_draw_entity(self):
        """Test drawing entity with transform."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.upload_mesh("character", {})
        bridge.create_material_pipeline("skin", "", "")

        bridge.begin_frame()

        bridge.draw_entity(
            "character",
            "skin",
            position=Vec3(10, 0, 20),
            rotation=math.pi / 4,
            scale=1.5,
        )

        assert bridge.render_state.draw_calls == 1

        bridge.end_frame()

    def test_light_management(self):
        """Test light addition."""
        bridge = GraphicsBridge()
        bridge.initialize()

        assert bridge.render_state.light_count == 0

        bridge.add_light(
            position=(0, 10, 0),
            color=(1.0, 0.9, 0.8),
            intensity=2.0,
            radius=15.0,
        )

        assert bridge.render_state.light_count == 1

        bridge.add_light(position=(10, 10, 0))
        assert bridge.render_state.light_count == 2

    def test_clear_lights(self):
        """Test clearing lights."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.add_light(position=(0, 10, 0))
        bridge.add_light(position=(10, 10, 0))
        assert bridge.render_state.light_count == 2

        bridge.clear_lights()
        assert bridge.render_state.light_count == 0

    def test_get_stats(self):
        """Test getting render statistics."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.begin_frame()
        bridge.upload_mesh("m", {})
        bridge.create_material_pipeline("p", "", "")
        bridge.draw_mesh("m", "p")
        bridge.end_frame()

        stats = bridge.get_stats()

        assert "frame_count" in stats
        assert "draw_calls" in stats
        assert "triangles" in stats
        assert "vertices" in stats
        assert stats["frame_count"] == 1
        assert stats["draw_calls"] == 1

    def test_shutdown(self):
        """Test bridge shutdown."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.shutdown()
        assert bridge.is_initialized is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestGraphicsBridgeIntegration:
    """Integration tests for GraphicsBridge."""

    def test_full_render_frame(self):
        """Test complete render frame with multiple objects."""
        import numpy as np

        bridge = GraphicsBridge()
        bridge.initialize()

        # Set up scene
        bridge.set_camera_direct((0, 10, 20), (0, 0, 0))

        # Upload assets
        bridge.upload_mesh("ground", {})
        bridge.upload_mesh("player", {})
        bridge.upload_mesh("tree", {})

        bridge.create_material_pipeline("terrain", "", "")
        bridge.create_material_pipeline("character", "", "")
        bridge.create_material_pipeline("foliage", "", "")

        # Add lights
        bridge.add_light((0, 50, 0), (1, 1, 0.9), 1.0, 100)
        bridge.add_light((10, 5, 10), (1, 0.5, 0), 2.0, 10)

        # Render frame
        bridge.begin_frame()

        bridge.draw_mesh("ground", "terrain")
        bridge.draw_entity("player", "character", Vec3(0, 0, 0), 0, 1)
        bridge.draw_entity("tree", "foliage", Vec3(5, 0, 5), 0, 1)
        bridge.draw_entity("tree", "foliage", Vec3(-5, 0, 3), 0, 1)
        bridge.draw_entity("tree", "foliage", Vec3(3, 0, -5), 0, 1)

        bridge.end_frame()

        stats = bridge.get_stats()
        assert stats["draw_calls"] == 5
        assert stats["frame_count"] == 1

    def test_camera_follows_player(self):
        """Test camera updates to follow player position."""
        from player_controller import CameraController

        bridge = GraphicsBridge()
        bridge.initialize()

        controller = CameraController()

        # Simulate player moving and camera following
        for i in range(10):
            player_pos = Vec3(i * 2, 0, i)

            # Update camera (simplified - normally done in CameraController.update)
            controller.camera.target = player_pos + Vec3(0, 1.6, 0)
            controller.camera.update_position()

            bridge.set_camera_from_controller(controller)

            bridge.begin_frame()
            bridge.end_frame()

        # Camera should have moved
        assert bridge.render_state.camera_target[0] > 0

    def test_multiple_frame_consistency(self):
        """Test rendering multiple frames maintains state."""
        bridge = GraphicsBridge()
        bridge.initialize()

        bridge.upload_mesh("obj", {})
        bridge.create_material_pipeline("mat", "", "")

        for frame in range(100):
            bridge.begin_frame()
            bridge.draw_mesh("obj", "mat")
            bridge.end_frame()

        assert bridge.render_state.frame_count == 100

        # Stats should reflect current frame only
        stats = bridge.get_stats()
        assert stats["draw_calls"] == 1  # Reset each frame
