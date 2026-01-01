#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <unordered_map>
#include <array>
#include <memory>
#include <variant>

/**
 * Material graph compiler utilities.
 *
 * This module provides a C++ implementation for compiling material graph
 * specifications (JSON DSL) into GLSL shader code. The compiler supports:
 * - Noise nodes (procedural noise generation)
 * - Warp nodes (domain warping/distortion)
 * - Blend nodes (interpolation between inputs)
 * - PBR constant nodes (fixed PBR material values)
 *
 * The output is GLSL shader code that can be further compiled to SPIR-V
 * using external tools (glslc, shaderc, etc.).
 */

namespace materials {

// ============================================================================
// Node Types
// ============================================================================

/**
 * Base material output (PBR values).
 */
struct PBROutput {
    std::array<float, 3> albedo = {0.5f, 0.5f, 0.5f};
    float roughness = 0.5f;
    float metallic = 0.0f;
    float ao = 1.0f;
};

/**
 * Noise node: procedural noise generation.
 */
struct NoiseNode {
    uint32_t seed = 0;
    float frequency = 1.0f;
    uint32_t octaves = 4;
    float persistence = 0.5f;
};

/**
 * Warp node: domain warping/distortion.
 */
struct WarpNode {
    std::string input;
    float strength = 0.5f;
};

/**
 * Blend node: interpolate between two inputs.
 */
struct BlendNode {
    std::string input_a;
    std::string input_b;
    float factor = 0.5f;
    std::string blend_mode = "mix";  // "mix", "multiply", "add", "overlay"
};

/**
 * PBR constant node: fixed material values.
 */
struct PBRConstNode {
    std::array<float, 3> albedo = {0.5f, 0.5f, 0.5f};
    float roughness = 0.5f;
    float metallic = 0.0f;
};

/**
 * Texture sample node: sample from a texture.
 */
struct TextureNode {
    std::string texture_name;
    std::string uv_input = "uv0";
};

/**
 * Node variant type.
 */
using NodeData = std::variant<NoiseNode, WarpNode, BlendNode, PBRConstNode, TextureNode>;

/**
 * Material graph node.
 */
struct MaterialNode {
    std::string name;
    std::string type;
    NodeData data;
};

/**
 * Complete material graph.
 */
struct MaterialGraph {
    std::unordered_map<std::string, MaterialNode> nodes;
    std::string output_node;

    // Computed during compilation
    std::vector<std::string> evaluation_order;
};

// ============================================================================
// Compiled Shader
// ============================================================================

/**
 * Compiled shader output.
 */
struct CompiledShader {
    std::string vertex_source;      // GLSL vertex shader
    std::string fragment_source;    // GLSL fragment shader
    uint64_t hash;                  // Hash for caching
    bool valid = false;
    std::string error_message;
};

/**
 * Shader compilation options.
 */
struct CompilerOptions {
    bool include_noise_functions = true;
    bool include_pbr_lighting = true;
    bool optimize = true;
    std::string glsl_version = "450";
};

// ============================================================================
// Material Graph Compiler
// ============================================================================

/**
 * Material graph compiler.
 *
 * Compiles material graph specifications into GLSL shader code.
 */
class MaterialCompiler {
public:
    MaterialCompiler() = default;

    /**
     * Compile a material graph to GLSL shaders.
     *
     * @param graph Material graph to compile
     * @param options Compilation options
     * @return Compiled shader with vertex and fragment sources
     */
    CompiledShader compile(const MaterialGraph& graph,
                           const CompilerOptions& options = {});

    /**
     * Parse a material graph from JSON-like structure.
     * (Used for Python bindings)
     */
    static MaterialGraph parse_graph(
        const std::unordered_map<std::string,
            std::unordered_map<std::string, std::string>>& nodes_data,
        const std::string& output_node);

    /**
     * Compute hash for a material graph (for caching).
     */
    static uint64_t compute_hash(const MaterialGraph& graph);

private:
    /**
     * Topologically sort nodes for correct evaluation order.
     */
    bool topological_sort(MaterialGraph& graph);

    /**
     * Generate noise function library.
     */
    std::string generate_noise_library() const;

    /**
     * Generate PBR lighting functions.
     */
    std::string generate_pbr_library() const;

    /**
     * Generate GLSL code for a single node.
     */
    std::string generate_node_code(const MaterialNode& node) const;

    /**
     * Generate vertex shader.
     */
    std::string generate_vertex_shader(const CompilerOptions& options) const;

    /**
     * Generate fragment shader.
     */
    std::string generate_fragment_shader(const MaterialGraph& graph,
                                          const CompilerOptions& options) const;
};

// ============================================================================
// Shader Cache
// ============================================================================

/**
 * Simple shader cache using hash-based lookup.
 */
class ShaderCache {
public:
    ShaderCache() = default;

    /**
     * Get a cached shader by hash.
     * @return nullptr if not cached
     */
    const CompiledShader* get(uint64_t hash) const;

    /**
     * Store a shader in the cache.
     */
    void put(uint64_t hash, const CompiledShader& shader);

    /**
     * Clear the cache.
     */
    void clear();

    /**
     * Get cache size.
     */
    size_t size() const { return cache_.size(); }

private:
    std::unordered_map<uint64_t, CompiledShader> cache_;
};

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Create a simple noise material graph.
 */
MaterialGraph create_noise_material(uint32_t seed, float frequency);

/**
 * Create a PBR constant material graph.
 */
MaterialGraph create_pbr_material(const std::array<float, 3>& albedo,
                                   float roughness, float metallic = 0.0f);

/**
 * Create a blended material from two graphs.
 */
MaterialGraph create_blend_material(const MaterialGraph& a,
                                     const MaterialGraph& b,
                                     float factor);

} // namespace materials
