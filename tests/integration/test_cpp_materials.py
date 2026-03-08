"""
Tests for the C++ materials graph compiler module.

Tests the GLSL shader generation from material graph DSL.
"""

import pytest

cpp = pytest.importorskip("procengine_cpp")


# ============================================================================
# Node Creation Tests
# ============================================================================

class TestNodeCreation:
    """Test creation of individual node types."""

    def test_noise_node_defaults(self):
        """Test NoiseNode default values."""
        node = cpp.NoiseNode()
        assert node.seed == 0
        assert node.frequency == 1.0
        assert node.octaves == 4
        assert abs(node.persistence - 0.5) < 1e-6

    def test_noise_node_custom(self):
        """Test NoiseNode with custom values."""
        node = cpp.NoiseNode()
        node.seed = 12345
        node.frequency = 2.5
        node.octaves = 6
        node.persistence = 0.7

        assert node.seed == 12345
        assert abs(node.frequency - 2.5) < 1e-6
        assert node.octaves == 6
        assert abs(node.persistence - 0.7) < 1e-6

    def test_warp_node(self):
        """Test WarpNode creation."""
        node = cpp.WarpNode()
        node.input = "noise1"
        node.strength = 0.3

        assert node.input == "noise1"
        assert abs(node.strength - 0.3) < 1e-6

    def test_blend_node(self):
        """Test BlendNode creation."""
        node = cpp.BlendNode()
        node.input_a = "noise1"
        node.input_b = "noise2"
        node.factor = 0.6
        node.blend_mode = "multiply"

        assert node.input_a == "noise1"
        assert node.input_b == "noise2"
        assert abs(node.factor - 0.6) < 1e-6
        assert node.blend_mode == "multiply"

    def test_pbr_const_node(self):
        """Test PBRConstNode creation."""
        node = cpp.PBRConstNode()
        node.albedo = [0.8, 0.2, 0.1]
        node.roughness = 0.4
        node.metallic = 0.9

        assert abs(node.albedo[0] - 0.8) < 1e-6
        assert abs(node.albedo[1] - 0.2) < 1e-6
        assert abs(node.albedo[2] - 0.1) < 1e-6
        assert abs(node.roughness - 0.4) < 1e-6
        assert abs(node.metallic - 0.9) < 1e-6


# ============================================================================
# Material Graph Tests
# ============================================================================

class TestMaterialGraph:
    """Test MaterialGraph creation and structure."""

    def test_empty_graph(self):
        """Test empty graph creation."""
        graph = cpp.MaterialGraph()
        assert graph.output_node == ""

    def test_graph_output_node(self):
        """Test setting output node."""
        graph = cpp.MaterialGraph()
        graph.output_node = "final_output"
        assert graph.output_node == "final_output"


# ============================================================================
# Compiler Options Tests
# ============================================================================

class TestCompilerOptions:
    """Test CompilerOptions configuration."""

    def test_default_options(self):
        """Test default compiler options."""
        opts = cpp.CompilerOptions()
        assert opts.include_noise_functions == True
        assert opts.include_pbr_lighting == True
        assert opts.optimize == True
        assert opts.glsl_version == "450"

    def test_custom_options(self):
        """Test custom compiler options."""
        opts = cpp.CompilerOptions()
        opts.include_noise_functions = False
        opts.include_pbr_lighting = False
        opts.optimize = False
        opts.glsl_version = "330"

        assert opts.include_noise_functions == False
        assert opts.include_pbr_lighting == False
        assert opts.optimize == False
        assert opts.glsl_version == "330"


# ============================================================================
# Material Compiler Tests
# ============================================================================

class TestMaterialCompiler:
    """Test MaterialCompiler functionality."""

    def test_compiler_creation(self):
        """Test compiler instantiation."""
        compiler = cpp.MaterialCompiler()
        assert compiler is not None

    def test_compile_simple_noise(self):
        """Test compiling a simple noise material."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.5,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True
        assert len(shader.vertex_source) > 0
        assert len(shader.fragment_source) > 0
        assert shader.hash != 0
        assert "#version 450" in shader.vertex_source
        assert "#version 450" in shader.fragment_source

    def test_compile_pbr_const(self):
        """Test compiling a PBR constant material."""
        graph = {
            "nodes": {
                "pbr1": {
                    "type": "pbr_const",
                    "albedo": [0.8, 0.2, 0.1],
                    "roughness": 0.4,
                    "metallic": 0.9
                }
            },
            "output": "pbr1"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True
        assert "0.8" in shader.fragment_source or "albedo" in shader.fragment_source.lower()

    def test_compile_blend_material(self):
        """Test compiling a blend material with two inputs."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 1,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                },
                "noise2": {
                    "type": "noise",
                    "seed": 2,
                    "frequency": 2.0,
                    "octaves": 3,
                    "persistence": 0.6
                },
                "blend1": {
                    "type": "blend",
                    "input_a": "noise1",
                    "input_b": "noise2",
                    "factor": 0.5,
                    "blend_mode": "mix"
                }
            },
            "output": "blend1"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True
        assert "mix" in shader.fragment_source.lower() or "blend" in shader.fragment_source.lower()

    def test_compile_warp_material(self):
        """Test compiling a warp material."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                },
                "warp1": {
                    "type": "warp",
                    "input": "noise1",
                    "strength": 0.3
                }
            },
            "output": "warp1"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True
        assert len(shader.fragment_source) > 0

    def test_shader_contains_noise_functions(self):
        """Test that noise materials include noise function library."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader = cpp.compile_material_from_dict(graph)

        # Should include simplex noise function
        assert "simplex" in shader.fragment_source.lower() or "noise" in shader.fragment_source.lower()

    def test_shader_contains_pbr_functions(self):
        """Test that PBR materials include lighting functions."""
        graph = {
            "nodes": {
                "pbr1": {
                    "type": "pbr_const",
                    "albedo": [0.5, 0.5, 0.5],
                    "roughness": 0.5,
                    "metallic": 0.0
                }
            },
            "output": "pbr1"
        }

        shader = cpp.compile_material_from_dict(graph)

        # Should include PBR lighting functions
        assert "fresnel" in shader.fragment_source.lower() or "ggx" in shader.fragment_source.lower() or "brdf" in shader.fragment_source.lower()

    def test_different_glsl_version(self):
        """Test compiling with different GLSL version."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        # Use default version 450
        shader = cpp.compile_material_from_dict(graph)
        assert "#version 450" in shader.vertex_source


# ============================================================================
# Shader Cache Tests
# ============================================================================

class TestShaderCache:
    """Test ShaderCache functionality."""

    def test_cache_creation(self):
        """Test cache instantiation."""
        cache = cpp.ShaderCache()
        assert cache.size() == 0

    def test_cache_put_get(self):
        """Test storing and retrieving shaders."""
        cache = cpp.ShaderCache()

        # Compile a shader
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }
        shader = cpp.compile_material_from_dict(graph)

        # Store in cache
        cache.put(shader.hash, shader)
        assert cache.size() == 1

        # Retrieve from cache
        cached = cache.get(shader.hash)
        assert cached is not None
        assert cached.valid == True
        assert cached.hash == shader.hash

    def test_cache_miss(self):
        """Test cache miss returns None."""
        cache = cpp.ShaderCache()

        cached = cache.get(12345)
        assert cached is None

    def test_cache_clear(self):
        """Test clearing the cache."""
        cache = cpp.ShaderCache()

        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }
        shader = cpp.compile_material_from_dict(graph)
        cache.put(shader.hash, shader)
        assert cache.size() == 1

        cache.clear()
        assert cache.size() == 0

    def test_cache_multiple_shaders(self):
        """Test caching multiple different shaders."""
        cache = cpp.ShaderCache()

        # First shader
        graph1 = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 1,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }
        shader1 = cpp.compile_material_from_dict(graph1)
        cache.put(shader1.hash, shader1)

        # Second shader with different seed
        graph2 = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 2,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }
        shader2 = cpp.compile_material_from_dict(graph2)
        cache.put(shader2.hash, shader2)

        assert cache.size() == 2
        assert shader1.hash != shader2.hash


# ============================================================================
# Hash Determinism Tests
# ============================================================================

class TestHashDeterminism:
    """Test that shader hashing is deterministic."""

    def test_same_graph_same_hash(self):
        """Test identical graphs produce same hash."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.5,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader1 = cpp.compile_material_from_dict(graph)
        shader2 = cpp.compile_material_from_dict(graph)

        assert shader1.hash == shader2.hash

    def test_different_seed_different_hash(self):
        """Test different seeds produce different hashes."""
        graph1 = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 1,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }
        graph2 = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 2,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader1 = cpp.compile_material_from_dict(graph1)
        shader2 = cpp.compile_material_from_dict(graph2)

        assert shader1.hash != shader2.hash


# ============================================================================
# Complex Graph Tests
# ============================================================================

class TestComplexGraphs:
    """Test compilation of complex material graphs."""

    def test_multi_layer_blend(self):
        """Test a multi-layer blended material."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 1,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                },
                "noise2": {
                    "type": "noise",
                    "seed": 2,
                    "frequency": 2.0,
                    "octaves": 3,
                    "persistence": 0.6
                },
                "noise3": {
                    "type": "noise",
                    "seed": 3,
                    "frequency": 4.0,
                    "octaves": 2,
                    "persistence": 0.7
                },
                "blend1": {
                    "type": "blend",
                    "input_a": "noise1",
                    "input_b": "noise2",
                    "factor": 0.5,
                    "blend_mode": "mix"
                },
                "blend2": {
                    "type": "blend",
                    "input_a": "blend1",
                    "input_b": "noise3",
                    "factor": 0.3,
                    "blend_mode": "add"
                }
            },
            "output": "blend2"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True
        assert len(shader.fragment_source) > 0

    def test_warp_chain(self):
        """Test a chain of warp nodes."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                },
                "warp1": {
                    "type": "warp",
                    "input": "noise1",
                    "strength": 0.2
                },
                "warp2": {
                    "type": "warp",
                    "input": "warp1",
                    "strength": 0.1
                }
            },
            "output": "warp2"
        }

        shader = cpp.compile_material_from_dict(graph)

        assert shader.valid == True


# ============================================================================
# Shader Output Validation Tests
# ============================================================================

class TestShaderOutput:
    """Test the structure of generated shader code."""

    def test_vertex_shader_structure(self):
        """Test vertex shader has required elements."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader = cpp.compile_material_from_dict(graph)

        vs = shader.vertex_source
        assert "#version" in vs
        assert "void main()" in vs or "void main(void)" in vs

    def test_fragment_shader_structure(self):
        """Test fragment shader has required elements."""
        graph = {
            "nodes": {
                "noise1": {
                    "type": "noise",
                    "seed": 42,
                    "frequency": 1.0,
                    "octaves": 4,
                    "persistence": 0.5
                }
            },
            "output": "noise1"
        }

        shader = cpp.compile_material_from_dict(graph)

        fs = shader.fragment_source
        assert "#version" in fs
        assert "void main()" in fs or "void main(void)" in fs

    def test_fragment_shader_uses_gamma_without_reinhard_tonemapping(self):
        """The material compiler should avoid non-HDR Reinhard compression."""
        graph = {
            "nodes": {
                "base_color": {
                    "type": "pbr_const",
                    "albedo": [0.8, 0.5, 0.3],
                    "roughness": 0.7,
                    "metallic": 0.0,
                }
            },
            "output": "base_color",
        }

        shader = cpp.compile_material_from_dict(graph)

        fs = shader.fragment_source
        assert "pow(color, vec3(1.0/2.2))" in fs
        assert "color = color / (color + vec3(1.0));" not in fs
        assert (
            "finalMaterial.albedo = clamp(mix(vec3(luminance), finalMaterial.albedo, 1.3), 0.0, 1.0);"
            in fs
        )

    def test_fragment_shader_includes_fog_with_dead_zone(self):
        """PBR fragment shader should apply distance fog with a dead zone."""
        graph = {
            "nodes": {
                "base_color": {
                    "type": "pbr_const",
                    "albedo": [0.6, 0.6, 0.6],
                    "roughness": 0.5,
                    "metallic": 0.0,
                }
            },
            "output": "base_color",
        }

        shader = cpp.compile_material_from_dict(graph)

        fs = shader.fragment_source
        # Fog uniforms should be declared
        assert "uniform float uFogStart;" in fs
        assert "uniform float uFogDensity;" in fs
        assert "uniform float uFogMax;" in fs
        assert "uniform vec3 uFogColor;" in fs
        # Fog should use a dead zone (subtract start distance before exp)
        assert "uFogStart" in fs
        assert "uFogDensity" in fs
        assert "mix(color, uFogColor, fogFactor)" in fs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
