"""Integration tests for the C++ props mesh synthesis module."""

from __future__ import annotations

import numpy as np
import pytest

procengine_cpp = pytest.importorskip("procengine_cpp")


# ============================================================================
# Vec3 Tests
# ============================================================================

def test_vec3_basic_operations() -> None:
    """Vec3 class supports basic operations."""
    v1 = procengine_cpp.Vec3(1.0, 2.0, 3.0)
    assert v1.x == 1.0
    assert v1.y == 2.0
    assert v1.z == 3.0

    # Length
    v2 = procengine_cpp.Vec3(3.0, 4.0, 0.0)
    assert abs(v2.length() - 5.0) < 1e-6

    # Dot product
    v3 = procengine_cpp.Vec3(1.0, 0.0, 0.0)
    v4 = procengine_cpp.Vec3(1.0, 0.0, 0.0)
    assert abs(v3.dot(v4) - 1.0) < 1e-6


def test_vec3_cross_product() -> None:
    """Vec3 cross product works correctly."""
    x = procengine_cpp.Vec3(1.0, 0.0, 0.0)
    y = procengine_cpp.Vec3(0.0, 1.0, 0.0)
    z = x.cross(y)
    assert abs(z.x) < 1e-6
    assert abs(z.y) < 1e-6
    assert abs(z.z - 1.0) < 1e-6


# ============================================================================
# Mesh Tests
# ============================================================================

def test_mesh_basic() -> None:
    """Mesh class basic functionality."""
    mesh = procengine_cpp.Mesh()
    assert mesh.vertex_count() == 0
    assert mesh.triangle_count() == 0


# ============================================================================
# Rock Mesh Tests
# ============================================================================

def test_generate_rock_mesh() -> None:
    """Rock mesh generation produces valid mesh."""
    desc = procengine_cpp.RockDescriptor()
    desc.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.radius = 1.0

    mesh = procengine_cpp.generate_rock_mesh(desc, segments=8, rings=6)

    assert mesh.vertex_count() > 0
    assert mesh.triangle_count() > 0
    assert len(mesh.indices) % 3 == 0


def test_rock_mesh_from_python_dict() -> None:
    """Rock mesh can be created from Python descriptor dict."""
    py_desc = {
        "type": "rock",
        "position": [1.0, 2.0, 3.0],
        "radius": 0.5
    }

    cpp_desc = procengine_cpp.create_rock_from_dict(py_desc)
    mesh = procengine_cpp.generate_rock_mesh(cpp_desc)

    assert mesh.vertex_count() > 0
    # Check position is incorporated
    vertices = mesh.get_vertices_numpy()
    center = vertices.mean(axis=0)
    assert abs(center[0] - 1.0) < 0.5
    assert abs(center[1] - 2.0) < 0.5
    assert abs(center[2] - 3.0) < 0.5


def test_rock_mesh_deterministic() -> None:
    """Same rock descriptor produces identical mesh."""
    desc = procengine_cpp.RockDescriptor()
    desc.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.radius = 1.0

    mesh1 = procengine_cpp.generate_rock_mesh(desc)
    mesh2 = procengine_cpp.generate_rock_mesh(desc)

    v1 = mesh1.get_vertices_numpy()
    v2 = mesh2.get_vertices_numpy()
    assert np.allclose(v1, v2)


# ============================================================================
# Tree Mesh Tests
# ============================================================================

def test_evaluate_lsystem() -> None:
    """L-system evaluation produces expected output."""
    rules = procengine_cpp.LSystemRules()
    rules.axiom = "F"
    rules.rules = {"F": "FF"}

    result = procengine_cpp.evaluate_lsystem(rules, 3)
    assert result == "FFFFFFFF"  # F -> FF -> FFFF -> FFFFFFFF


def test_generate_tree_skeleton() -> None:
    """Tree skeleton generation works."""
    lstring = "F[+F]F[-F]F"
    segments = procengine_cpp.generate_tree_skeleton(lstring, angle=25.0)

    # Should have 5 F segments
    assert len(segments) == 5

    # All segments should have positive radii
    for seg in segments:
        assert seg.start_radius > 0
        assert seg.end_radius > 0


def test_generate_tree_mesh() -> None:
    """Tree mesh generation produces valid mesh."""
    desc = procengine_cpp.TreeDescriptor()
    desc.lsystem = procengine_cpp.LSystemRules()
    desc.lsystem.axiom = "F"
    desc.lsystem.rules = {"F": "F[+F]F[-F]F"}
    desc.angle = 25.0
    desc.iterations = 2

    mesh = procengine_cpp.generate_tree_mesh(desc)

    assert mesh.vertex_count() > 0
    assert mesh.triangle_count() > 0


def test_tree_mesh_from_python_dict() -> None:
    """Tree mesh can be created from Python descriptor dict."""
    py_desc = {
        "type": "tree",
        "axiom": "F",
        "rules": {"F": "F[+F]F[-F]F"},
        "angle": 30.0,
        "iterations": 2
    }

    cpp_desc = procengine_cpp.create_tree_from_dict(py_desc)
    mesh = procengine_cpp.generate_tree_mesh(cpp_desc)

    assert mesh.vertex_count() > 0
    assert mesh.triangle_count() > 0


def test_tree_mesh_deterministic() -> None:
    """Same tree descriptor produces identical mesh."""
    desc = procengine_cpp.TreeDescriptor()
    desc.lsystem = procengine_cpp.LSystemRules()
    desc.lsystem.axiom = "F"
    desc.lsystem.rules = {"F": "FF"}
    desc.angle = 25.0
    desc.iterations = 2

    mesh1 = procengine_cpp.generate_tree_mesh(desc)
    mesh2 = procengine_cpp.generate_tree_mesh(desc)

    v1 = mesh1.get_vertices_numpy()
    v2 = mesh2.get_vertices_numpy()
    assert np.allclose(v1, v2)


# ============================================================================
# Building Mesh Tests
# ============================================================================

def test_generate_building_mesh() -> None:
    """Building mesh generation produces valid mesh."""
    desc = procengine_cpp.BuildingDescriptor()
    desc.root = procengine_cpp.BuildingBlock()
    desc.root.size = procengine_cpp.Vec3(2.0, 3.0, 2.0)
    desc.root.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.root.children = []

    mesh = procengine_cpp.generate_building_mesh(desc)

    # A single block should produce a box mesh
    assert mesh.vertex_count() == 24  # 6 faces * 4 vertices
    assert mesh.triangle_count() == 12  # 6 faces * 2 triangles


def test_building_with_children() -> None:
    """Building with children generates composite mesh."""
    desc = procengine_cpp.BuildingDescriptor()
    desc.root = procengine_cpp.BuildingBlock()
    desc.root.size = procengine_cpp.Vec3(2.0, 2.0, 2.0)
    desc.root.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)

    child1 = procengine_cpp.BuildingBlock()
    child1.size = procengine_cpp.Vec3(1.0, 1.0, 1.0)
    child1.position = procengine_cpp.Vec3(-0.5, 0.0, 0.0)
    child1.children = []

    child2 = procengine_cpp.BuildingBlock()
    child2.size = procengine_cpp.Vec3(1.0, 1.0, 1.0)
    child2.position = procengine_cpp.Vec3(0.5, 0.0, 0.0)
    child2.children = []

    desc.root.children = [child1, child2]

    mesh = procengine_cpp.generate_building_mesh(desc)

    # Two children = two boxes
    assert mesh.vertex_count() == 48  # 2 boxes * 24 vertices
    assert mesh.triangle_count() == 24  # 2 boxes * 12 triangles


# ============================================================================
# Creature Mesh Tests
# ============================================================================

def test_evaluate_metaball_field() -> None:
    """Metaball field evaluation works correctly."""
    ball = procengine_cpp.Metaball()
    ball.center = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    ball.radius = 1.0
    ball.strength = 1.0

    metaballs = [ball]

    # At center, field should be very high
    center = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    field_center = procengine_cpp.evaluate_metaball_field(metaballs, center)
    assert field_center > 100.0

    # Further away, field should be lower
    far = procengine_cpp.Vec3(5.0, 0.0, 0.0)
    field_far = procengine_cpp.evaluate_metaball_field(metaballs, far)
    assert field_far < field_center


def test_generate_creature_mesh() -> None:
    """Creature mesh generation produces valid mesh."""
    desc = procengine_cpp.CreatureDescriptor()

    # Add skeleton bones
    bone1 = procengine_cpp.Bone()
    bone1.length = 1.0
    bone1.angle = 0.0
    desc.skeleton = [bone1]

    # Add metaballs
    ball1 = procengine_cpp.Metaball()
    ball1.center = procengine_cpp.Vec3(0.5, 0.5, 0.5)
    ball1.radius = 0.3
    ball1.strength = 1.0

    ball2 = procengine_cpp.Metaball()
    ball2.center = procengine_cpp.Vec3(0.7, 0.5, 0.5)
    ball2.radius = 0.2
    ball2.strength = 1.0

    desc.metaballs = [ball1, ball2]

    mesh = procengine_cpp.generate_creature_mesh(desc, grid_resolution=16)

    # Should produce some geometry (metaballs create implicit surface)
    assert mesh.vertex_count() > 0


def test_creature_mesh_from_python_dict() -> None:
    """Creature mesh can be created from Python descriptor dict."""
    py_desc = {
        "type": "creature",
        "skeleton": [
            {"length": 1.0, "angle": 0.0},
            {"length": 0.8, "angle": 15.0}
        ],
        "metaballs": [
            {"center": [0.5, 0.5, 0.5], "radius": 0.3},
            {"center": [0.7, 0.5, 0.5], "radius": 0.2}
        ]
    }

    cpp_desc = procengine_cpp.create_creature_from_dict(py_desc)
    mesh = procengine_cpp.generate_creature_mesh(cpp_desc, grid_resolution=16)

    assert len(cpp_desc.skeleton) == 2
    assert len(cpp_desc.metaballs) == 2
    assert mesh.vertex_count() > 0


# ============================================================================
# LOD Tests
# ============================================================================

def test_generate_lod() -> None:
    """LOD generation simplifies mesh."""
    # Create a rock mesh
    desc = procengine_cpp.RockDescriptor()
    desc.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.radius = 1.0

    original = procengine_cpp.generate_rock_mesh(desc, segments=32, rings=24)
    lod = procengine_cpp.generate_lod(original, target_ratio=0.25)

    # LOD should have fewer vertices
    assert lod.vertex_count() < original.vertex_count()
    # But still have some geometry
    assert lod.vertex_count() > 0


def test_lod_deterministic() -> None:
    """LOD generation is deterministic."""
    desc = procengine_cpp.RockDescriptor()
    desc.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.radius = 1.0

    original = procengine_cpp.generate_rock_mesh(desc, segments=16, rings=12)

    lod1 = procengine_cpp.generate_lod(original, target_ratio=0.5)
    lod2 = procengine_cpp.generate_lod(original, target_ratio=0.5)

    assert lod1.vertex_count() == lod2.vertex_count()
    assert lod1.triangle_count() == lod2.triangle_count()


# ============================================================================
# Mesh Numpy Export Tests
# ============================================================================

def test_mesh_numpy_export() -> None:
    """Mesh data can be exported to numpy arrays."""
    desc = procengine_cpp.RockDescriptor()
    desc.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc.radius = 1.0

    mesh = procengine_cpp.generate_rock_mesh(desc, segments=8, rings=6)

    vertices = mesh.get_vertices_numpy()
    normals = mesh.get_normals_numpy()
    indices = mesh.get_indices_numpy()

    assert vertices.shape[1] == 3
    assert normals.shape[1] == 3
    assert len(indices) % 3 == 0
    assert vertices.dtype == np.float32
    assert normals.dtype == np.float32
    assert indices.dtype == np.uint32


def test_mesh_append() -> None:
    """Meshes can be combined."""
    desc1 = procengine_cpp.RockDescriptor()
    desc1.position = procengine_cpp.Vec3(0.0, 0.0, 0.0)
    desc1.radius = 0.5

    desc2 = procengine_cpp.RockDescriptor()
    desc2.position = procengine_cpp.Vec3(2.0, 0.0, 0.0)
    desc2.radius = 0.5

    mesh1 = procengine_cpp.generate_rock_mesh(desc1, segments=8, rings=6)
    mesh2 = procengine_cpp.generate_rock_mesh(desc2, segments=8, rings=6)

    v1_count = mesh1.vertex_count()
    t1_count = mesh1.triangle_count()

    mesh1.append(mesh2)

    # Combined mesh should have both meshes' data
    assert mesh1.vertex_count() == v1_count + mesh2.vertex_count()
    assert mesh1.triangle_count() == t1_count + mesh2.triangle_count()
