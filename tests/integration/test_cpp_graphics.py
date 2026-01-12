"""
Test suite for C++ Graphics system.

Tests the Vulkan-based graphics backend including:
- Graphics system initialization
- Mesh upload
- Material pipeline creation
- Camera and lighting
- Render stats
"""

import pytest

# Skip entire module if C++ module not available
pytest.importorskip("procengine_cpp")
import procengine_cpp as cpp


def test_graphics_system_creation():
    """Test that graphics system can be created."""
    gfx = cpp.GraphicsSystem()
    assert gfx is not None
    assert not gfx.is_initialized()


def test_graphics_system_initialization():
    """Test graphics system initialization (headless mode)."""
    gfx = cpp.GraphicsSystem()

    # Initialize in headless mode (no window)
    # Note: This may fail if Vulkan drivers aren't available
    try:
        result = gfx.initialize(width=800, height=600, enable_validation=False)
        if result:
            assert gfx.is_initialized()
            gfx.shutdown()
            assert not gfx.is_initialized()
        else:
            pytest.skip("Vulkan initialization failed (no GPU/drivers available)")
    except RuntimeError as e:
        pytest.skip(f"Vulkan not available: {e}")


def test_mesh_upload():
    """Test uploading a mesh to GPU."""
    gfx = cpp.GraphicsSystem()

    try:
        if not gfx.initialize(width=800, height=600, enable_validation=False):
            pytest.skip("Vulkan initialization failed")
    except RuntimeError:
        pytest.skip("Vulkan not available")

    # Create a simple rock mesh directly
    rock_desc = cpp.RockDescriptor()
    rock_desc.position = cpp.Vec3(0.0, 0.0, 0.0)
    rock_desc.radius = 1.0

    rock_mesh = cpp.generate_rock_mesh(rock_desc, segments=8, rings=6)

    # Upload to GPU
    gpu_mesh = gfx.upload_mesh(rock_mesh)
    assert gpu_mesh.is_valid()
    assert gpu_mesh.vertex_count > 0
    assert gpu_mesh.index_count > 0

    gfx.shutdown()


def test_material_pipeline_creation():
    """Test creating a material pipeline from GLSL."""
    gfx = cpp.GraphicsSystem()

    try:
        if not gfx.initialize(width=800, height=600, enable_validation=False):
            pytest.skip("Vulkan initialization failed")
    except RuntimeError:
        pytest.skip("Vulkan not available")

    # Simple vertex shader
    vertex_glsl = """
#version 450

layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;

layout(location = 0) out vec3 fragNormal;

void main() {
    gl_Position = vec4(position, 1.0);
    fragNormal = normal;
}
"""

    # Simple fragment shader
    fragment_glsl = """
#version 450

layout(location = 0) in vec3 fragNormal;
layout(location = 0) out vec4 outColor;

void main() {
    vec3 n = normalize(fragNormal);
    outColor = vec4(n * 0.5 + 0.5, 1.0);
}
"""

    pipeline = gfx.create_material_pipeline(vertex_glsl, fragment_glsl)
    # Note: Pipeline creation may be incomplete without a render pass
    # This tests that shader compilation works

    gfx.shutdown()


def test_camera_and_lights():
    """Test camera and light creation."""
    camera = cpp.Camera()
    assert camera.position == [0.0, 10.0, 10.0]
    assert camera.fov == 60.0

    camera.position = [5.0, 5.0, 5.0]
    camera.fov = 45.0
    assert camera.position == [5.0, 5.0, 5.0]
    assert camera.fov == 45.0

    light = cpp.Light()
    light.position = [10.0, 10.0, 10.0]
    light.color = [1.0, 1.0, 1.0]
    light.intensity = 100.0
    light.radius = 50.0

    assert light.position == [10.0, 10.0, 10.0]
    assert light.intensity == 100.0


def test_render_stats():
    """Test render statistics."""
    stats = cpp.RenderStats()
    assert stats.draw_calls == 0
    assert stats.triangles == 0
    assert stats.vertices == 0
    assert stats.frame_time_ms == 0.0


def test_graphics_with_materials_compiler():
    """Test integration between graphics and materials systems."""
    gfx = cpp.GraphicsSystem()

    try:
        if not gfx.initialize(width=800, height=600, enable_validation=False):
            pytest.skip("Vulkan initialization failed")
    except RuntimeError:
        pytest.skip("Vulkan not available")

    # Create a material graph
    graph_dict = {
        "nodes": {
            "base_color": {
                "type": "pbr_const",
                "albedo": [0.8, 0.5, 0.3],
                "roughness": 0.7,
                "metallic": 0.0
            }
        },
        "output": "base_color"
    }

    # Compile material graph to GLSL
    compiled = cpp.compile_material_from_dict(graph_dict)
    assert compiled.valid
    assert len(compiled.vertex_source) > 0
    assert len(compiled.fragment_source) > 0

    # Create pipeline from compiled shaders
    pipeline = gfx.create_material_pipeline(
        compiled.vertex_source,
        compiled.fragment_source
    )

    gfx.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
