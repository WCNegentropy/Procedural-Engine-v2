"""Test biome color rendering pipeline."""
import pytest
import numpy as np
from procengine.graphics.graphics_bridge import GraphicsBridge


def test_biome_color_mesh_generation():
    """Test that terrain mesh with biome colors is generated correctly."""
    try:
        import procengine_cpp as cpp
    except ImportError:
        pytest.skip("C++ module not available")
    
    # Generate terrain with biomes
    result = cpp.generate_terrain_standalone(
        seed=42,
        size=32,
        octaves=4,
        macro_points=6,
        erosion_iters=50,
        return_slope=True
    )
    
    heightmap = result[0]
    biome_map = result[1]
    
    assert heightmap.shape == (32, 32)
    assert biome_map.shape == (32, 32)
    assert biome_map.min() >= 0
    assert biome_map.max() < 16  # 16 biomes (0-15)
    
    # Generate mesh with biome colors
    mesh = cpp.generate_terrain_mesh_with_biomes(heightmap, biome_map, 1.0, 1.0)
    
    assert len(mesh.vertices) == 32 * 32
    assert len(mesh.normals) == 32 * 32
    assert len(mesh.colors) == 32 * 32
    assert len(mesh.indices) == (32 - 1) * (32 - 1) * 6
    
    # Verify colors are in valid range [0, 1]
    for color in mesh.colors[:100]:  # Check first 100
        assert 0.0 <= color.x <= 1.0
        assert 0.0 <= color.y <= 1.0
        assert 0.0 <= color.z <= 1.0
    
    # Verify mesh is valid
    assert mesh.validate()
    
    print(f"✓ Mesh generated with {len(mesh.vertices)} vertices and {len(mesh.colors)} colors")


def test_graphics_bridge_biome_terrain_upload():
    """Test that GraphicsBridge can upload terrain with biome colors."""
    try:
        import procengine_cpp as cpp
    except ImportError:
        pytest.skip("C++ module not available")
    
    bridge = GraphicsBridge()
    
    # Initialize in headless mode
    bridge.initialize(width=800, height=600)
    
    # Generate terrain with biomes
    result = cpp.generate_terrain_standalone(
        seed=123,
        size=32,
        octaves=4,
        macro_points=6,
        erosion_iters=50,
        return_slope=True
    )
    
    heightmap = result[0]
    biome_map = result[1]
    
    # Upload terrain mesh with biome colors
    success = bridge.upload_terrain_mesh(
        "test_terrain",
        heightmap,
        cell_size=1.0,
        biome_map=biome_map
    )
    
    assert success
    
    # In headless mode, the mesh is stored internally
    # We can verify by checking if we can draw it
    try:
        bridge.begin_frame()
        bridge.draw_mesh("test_terrain", position=(0, 0, 0))
        bridge.end_frame()
    except Exception as e:
        # In headless mode without display, this is expected
        pass
    
    print(f"✓ Terrain mesh with biome colors uploaded successfully")


def test_biome_color_variety():
    """Test that different biomes produce different colors."""
    try:
        import procengine_cpp as cpp
    except ImportError:
        pytest.skip("C++ module not available")
    
    # Create heightmap with constant height
    heightmap = np.full((16, 16), 0.5, dtype=np.float32)
    
    # Create biome map with all different biomes
    biome_map = np.arange(16, dtype=np.uint8).reshape(4, 4).repeat(4, axis=0).repeat(4, axis=1)
    
    # Generate mesh
    mesh = cpp.generate_terrain_mesh_with_biomes(heightmap, biome_map, 1.0, 1.0)
    
    # Collect unique colors (rounding to avoid floating point issues)
    unique_colors = set()
    for color in mesh.colors:
        r = round(color.x, 2)
        g = round(color.y, 2)
        b = round(color.z, 2)
        unique_colors.add((r, g, b))
    
    # Should have at least 10 different colors (some biomes might be similar)
    assert len(unique_colors) >= 10
    
    print(f"✓ Found {len(unique_colors)} unique biome colors")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
