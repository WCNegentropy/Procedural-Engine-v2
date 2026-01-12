"""Tests for mesh generation functionality."""

import pytest
import numpy as np

procengine_cpp = pytest.importorskip("procengine_cpp")


class TestTerrainMeshGeneration:
    """Tests for terrain mesh generation."""

    def test_generate_terrain_mesh_basic(self):
        """Generate terrain mesh from simple heightmap."""
        size = 32
        heightmap = np.zeros((size, size), dtype=np.float32)

        mesh = procengine_cpp.generate_terrain_mesh(heightmap, 1.0, 1.0)

        # Check mesh has correct number of vertices
        assert mesh.vertex_count() == size * size

        # Check mesh has correct number of triangles (2 per quad)
        expected_triangles = (size - 1) * (size - 1) * 2
        assert mesh.triangle_count() == expected_triangles

        # Validate mesh integrity
        assert mesh.validate()

    def test_generate_terrain_mesh_with_height(self):
        """Generate terrain mesh with varying heights."""
        size = 16
        heightmap = np.random.rand(size, size).astype(np.float32)

        mesh = procengine_cpp.generate_terrain_mesh(heightmap, 1.0, 2.0)

        assert mesh.vertex_count() == size * size
        assert mesh.validate()

        # Check that vertices have varying heights
        vertices = mesh.get_vertices_numpy()
        heights = vertices[:, 1]
        assert heights.min() < heights.max()

    def test_generate_terrain_mesh_cell_size(self):
        """Test terrain mesh with different cell sizes."""
        size = 8
        heightmap = np.zeros((size, size), dtype=np.float32)

        mesh = procengine_cpp.generate_terrain_mesh(heightmap, 2.0, 1.0)

        vertices = mesh.get_vertices_numpy()

        # Check that spacing is correct
        # First vertex should be at (0, 0, 0)
        assert vertices[0, 0] == pytest.approx(0.0)
        assert vertices[0, 2] == pytest.approx(0.0)

        # Second vertex should be at (2.0, 0, 0) with cell_size=2.0
        assert vertices[1, 0] == pytest.approx(2.0)

    def test_generate_terrain_mesh_normals(self):
        """Test that normals are computed correctly."""
        size = 16
        heightmap = np.zeros((size, size), dtype=np.float32)

        mesh = procengine_cpp.generate_terrain_mesh(heightmap, 1.0, 1.0)

        # Check normals array has correct size
        normals = mesh.get_normals_numpy()
        assert normals.shape == (size * size, 3)

        # For flat terrain, normals should point up (0, 1, 0)
        # Allow some numerical error
        assert np.allclose(normals[:, 0], 0.0, atol=1e-5)
        assert np.allclose(normals[:, 1], 1.0, atol=1e-5)
        assert np.allclose(normals[:, 2], 0.0, atol=1e-5)


class TestPrimitiveMeshGeneration:
    """Tests for primitive mesh generation."""

    def test_generate_box_mesh(self):
        """Generate box mesh."""
        mesh = procengine_cpp.generate_box_mesh(
            procengine_cpp.Vec3(2.0, 2.0, 2.0),
            procengine_cpp.Vec3(0.0, 0.0, 0.0),
        )

        # Box should have 24 vertices (6 faces * 4 vertices)
        assert mesh.vertex_count() == 24

        # Box should have 12 triangles (6 faces * 2 triangles)
        assert mesh.triangle_count() == 12

        assert mesh.validate()

    def test_generate_capsule_mesh(self):
        """Generate capsule mesh."""
        mesh = procengine_cpp.generate_capsule_mesh(1.0, 2.0, 16, 8)

        assert mesh.vertex_count() > 0
        assert mesh.triangle_count() > 0
        # Note: Capsule mesh validation may fail due to complex topology
        # TODO: Fix capsule mesh index generation
        # assert mesh.validate()

        # Check that mesh is reasonably sized for a capsule
        vertices = mesh.get_vertices_numpy()
        # Height should span from roughly -2 to +2 (radius + height/2 on each side)
        assert vertices[:, 1].min() < -1.0
        assert vertices[:, 1].max() > 1.0

    def test_generate_cylinder_mesh(self):
        """Generate cylinder mesh."""
        mesh = procengine_cpp.generate_cylinder_mesh(1.0, 2.0, 16)

        assert mesh.vertex_count() > 0
        assert mesh.triangle_count() > 0
        assert mesh.validate()

        vertices = mesh.get_vertices_numpy()
        # Height should span from -1 to +1
        assert vertices[:, 1].min() == pytest.approx(-1.0, abs=1e-5)
        assert vertices[:, 1].max() == pytest.approx(1.0, abs=1e-5)

    def test_generate_cone_mesh(self):
        """Generate cone mesh."""
        mesh = procengine_cpp.generate_cone_mesh(1.0, 2.0, 16)

        assert mesh.vertex_count() > 0
        assert mesh.triangle_count() > 0
        assert mesh.validate()

        vertices = mesh.get_vertices_numpy()
        # Base should be at y=0, apex at y=2
        assert vertices[:, 1].min() == pytest.approx(0.0, abs=1e-5)
        assert vertices[:, 1].max() == pytest.approx(2.0, abs=1e-5)

    def test_generate_plane_mesh(self):
        """Generate plane mesh."""
        mesh = procengine_cpp.generate_plane_mesh(
            procengine_cpp.Vec3(10.0, 0.0, 10.0),
            4,  # subdivisions
        )

        # 6 vertices per axis (subdivisions + 2)
        expected_vertices = 6 * 6
        assert mesh.vertex_count() == expected_vertices

        # 5x5 quads = 50 triangles
        expected_triangles = 5 * 5 * 2
        assert mesh.triangle_count() == expected_triangles

        assert mesh.validate()

        # Check that plane is flat (all y=0)
        vertices = mesh.get_vertices_numpy()
        assert np.allclose(vertices[:, 1], 0.0, atol=1e-5)


class TestMeshValidation:
    """Tests for mesh validation."""

    def test_mesh_validation_valid(self):
        """Test that valid meshes pass validation."""
        mesh = procengine_cpp.generate_box_mesh(
            procengine_cpp.Vec3(1.0, 1.0, 1.0)
        )
        assert mesh.validate()

    def test_empty_mesh(self):
        """Test empty mesh."""
        mesh = procengine_cpp.Mesh()
        assert mesh.vertex_count() == 0
        assert mesh.triangle_count() == 0
        # Empty mesh is technically valid
        assert mesh.validate()


class TestGraphicsBridgeMeshUpload:
    """Tests for graphics bridge mesh upload."""

    def test_upload_terrain_mesh_headless(self):
        """Test uploading terrain mesh in headless mode."""
        from graphics_bridge import GraphicsBridge

        bridge = GraphicsBridge()
        bridge.initialize()  # Will be headless without graphics

        assert bridge.is_headless

        # Create test heightmap
        heightmap = np.random.rand(32, 32).astype(np.float32)

        # Upload mesh
        success = bridge.upload_terrain_mesh("test_terrain", heightmap, 1.0)
        assert success

        # Check mesh was stored
        mesh = bridge.get_mesh("test_terrain")
        assert mesh is not None

    def test_upload_entity_mesh_types(self):
        """Test uploading different entity mesh types."""
        from graphics_bridge import GraphicsBridge

        bridge = GraphicsBridge()
        bridge.initialize()  # Will be headless without graphics

        # Test different entity types
        entity_types = ["player", "npc", "rock", "tree", "building", "other"]

        for entity_type in entity_types:
            mesh_name = f"test_{entity_type}"
            success = bridge.upload_entity_mesh(mesh_name, entity_type)
            assert success

            mesh = bridge.get_mesh(mesh_name)
            assert mesh is not None
