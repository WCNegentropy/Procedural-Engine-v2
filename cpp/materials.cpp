#include "materials.h"
#include <sstream>
#include <algorithm>
#include <set>
#include <queue>
#include <functional>

namespace materials {

// ============================================================================
// Hash Utility
// ============================================================================

// FNV-1a hash for strings
static uint64_t fnv1a_hash(const std::string& str) {
    uint64_t hash = 14695981039346656037ULL;
    for (char c : str) {
        hash ^= static_cast<uint64_t>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

static uint64_t hash_combine(uint64_t h1, uint64_t h2) {
    return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
}

// ============================================================================
// MaterialCompiler Implementation
// ============================================================================

bool MaterialCompiler::topological_sort(MaterialGraph& graph) {
    // Build dependency graph
    std::unordered_map<std::string, std::set<std::string>> dependencies;
    std::unordered_map<std::string, int> in_degree;

    for (const auto& [name, node] : graph.nodes) {
        dependencies[name] = {};
        in_degree[name] = 0;
    }

    // Find dependencies
    for (const auto& [name, node] : graph.nodes) {
        if (std::holds_alternative<WarpNode>(node.data)) {
            const auto& warp = std::get<WarpNode>(node.data);
            if (graph.nodes.count(warp.input)) {
                dependencies[name].insert(warp.input);
                in_degree[name]++;
            }
        } else if (std::holds_alternative<BlendNode>(node.data)) {
            const auto& blend = std::get<BlendNode>(node.data);
            if (graph.nodes.count(blend.input_a)) {
                dependencies[name].insert(blend.input_a);
                in_degree[name]++;
            }
            if (graph.nodes.count(blend.input_b)) {
                dependencies[name].insert(blend.input_b);
                in_degree[name]++;
            }
        }
    }

    // Kahn's algorithm for topological sort
    std::queue<std::string> ready;
    for (const auto& [name, degree] : in_degree) {
        if (degree == 0) {
            ready.push(name);
        }
    }

    graph.evaluation_order.clear();
    while (!ready.empty()) {
        std::string current = ready.front();
        ready.pop();
        graph.evaluation_order.push_back(current);

        // Update dependents
        for (const auto& [name, deps] : dependencies) {
            if (deps.count(current)) {
                in_degree[name]--;
                if (in_degree[name] == 0) {
                    ready.push(name);
                }
            }
        }
    }

    // Check for cycles
    return graph.evaluation_order.size() == graph.nodes.size();
}

std::string MaterialCompiler::generate_noise_library() const {
    return R"(
// Simplex noise implementation
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;

    i = mod289(i);
    vec4 p = permute(permute(permute(
        i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;

    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);

    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);

    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x;
    p1 *= norm.y;
    p2 *= norm.z;
    p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

// FBM noise
float fbm(vec3 p, int octaves, float persistence) {
    float value = 0.0;
    float amplitude = 1.0;
    float frequency = 1.0;
    float maxValue = 0.0;

    for (int i = 0; i < octaves; i++) {
        value += amplitude * snoise(p * frequency);
        maxValue += amplitude;
        amplitude *= persistence;
        frequency *= 2.0;
    }

    return value / maxValue;
}

// Hash-based noise seed offset
vec3 hash_offset(int seed) {
    float s = float(seed);
    return vec3(
        fract(sin(s * 12.9898) * 43758.5453),
        fract(sin(s * 78.233) * 43758.5453),
        fract(sin(s * 45.164) * 43758.5453)
    ) * 1000.0;
}
)";
}

std::string MaterialCompiler::generate_pbr_library() const {
    return R"(
// PBR material structure
struct PBRMaterial {
    vec3 albedo;
    float roughness;
    float metallic;
    float ao;
};

// GGX/Trowbridge-Reitz normal distribution
float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;

    float nom = a2;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = 3.14159265 * denom * denom;

    return nom / max(denom, 0.0001);
}

// Schlick-GGX geometry function
float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = (roughness + 1.0);
    float k = (r * r) / 8.0;

    float nom = NdotV;
    float denom = NdotV * (1.0 - k) + k;

    return nom / max(denom, 0.0001);
}

// Smith's geometry function
float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2 = GeometrySchlickGGX(NdotV, roughness);
    float ggx1 = GeometrySchlickGGX(NdotL, roughness);

    return ggx1 * ggx2;
}

// Fresnel-Schlick approximation
vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(max(1.0 - cosTheta, 0.0), 5.0);
}

// Calculate PBR lighting
vec3 calculatePBR(PBRMaterial mat, vec3 N, vec3 V, vec3 L, vec3 lightColor) {
    vec3 H = normalize(V + L);

    vec3 F0 = vec3(0.04);
    F0 = mix(F0, mat.albedo, mat.metallic);

    float NDF = DistributionGGX(N, H, mat.roughness);
    float G = GeometrySmith(N, V, L, mat.roughness);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);

    vec3 numerator = NDF * G * F;
    float denominator = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0);
    vec3 specular = numerator / max(denominator, 0.001);

    vec3 kS = F;
    vec3 kD = vec3(1.0) - kS;
    kD *= 1.0 - mat.metallic;

    float NdotL = max(dot(N, L), 0.0);

    return (kD * mat.albedo / 3.14159265 + specular) * lightColor * NdotL;
}
)";
}

std::string MaterialCompiler::generate_node_code(const MaterialNode& node) const {
    std::ostringstream ss;

    if (std::holds_alternative<NoiseNode>(node.data)) {
        const auto& noise = std::get<NoiseNode>(node.data);
        ss << "    // Noise node: " << node.name << "\n";
        ss << "    vec3 " << node.name << "_offset = hash_offset(" << noise.seed << ");\n";
        ss << "    float " << node.name << "_value = fbm(worldPos * " << noise.frequency
           << " + " << node.name << "_offset, " << noise.octaves << ", " << noise.persistence << ");\n";
        ss << "    " << node.name << "_value = " << node.name << "_value * 0.5 + 0.5;\n";  // Normalize to [0,1]
        ss << "    PBRMaterial " << node.name << ";\n";
        ss << "    " << node.name << ".albedo = vec3(" << node.name << "_value);\n";
        ss << "    " << node.name << ".roughness = 1.0 - " << node.name << "_value * 0.5;\n";
        ss << "    " << node.name << ".metallic = 0.0;\n";
        ss << "    " << node.name << ".ao = 1.0;\n";

    } else if (std::holds_alternative<WarpNode>(node.data)) {
        const auto& warp = std::get<WarpNode>(node.data);
        ss << "    // Warp node: " << node.name << "\n";
        ss << "    vec3 " << node.name << "_warpOffset = vec3(\n";
        ss << "        snoise(worldPos + vec3(0.0)),\n";
        ss << "        snoise(worldPos + vec3(43.0)),\n";
        ss << "        snoise(worldPos + vec3(87.0))\n";
        ss << "    ) * " << warp.strength << ";\n";
        ss << "    PBRMaterial " << node.name << " = " << warp.input << ";\n";
        ss << "    " << node.name << ".albedo = " << warp.input << ".albedo + " << node.name << "_warpOffset * 0.1;\n";

    } else if (std::holds_alternative<BlendNode>(node.data)) {
        const auto& blend = std::get<BlendNode>(node.data);
        ss << "    // Blend node: " << node.name << "\n";
        ss << "    PBRMaterial " << node.name << ";\n";
        ss << "    " << node.name << ".albedo = mix(" << blend.input_a << ".albedo, "
           << blend.input_b << ".albedo, " << blend.factor << ");\n";
        ss << "    " << node.name << ".roughness = mix(" << blend.input_a << ".roughness, "
           << blend.input_b << ".roughness, " << blend.factor << ");\n";
        ss << "    " << node.name << ".metallic = mix(" << blend.input_a << ".metallic, "
           << blend.input_b << ".metallic, " << blend.factor << ");\n";
        ss << "    " << node.name << ".ao = mix(" << blend.input_a << ".ao, "
           << blend.input_b << ".ao, " << blend.factor << ");\n";

    } else if (std::holds_alternative<PBRConstNode>(node.data)) {
        const auto& pbr = std::get<PBRConstNode>(node.data);
        ss << "    // PBR constant node: " << node.name << "\n";
        ss << "    PBRMaterial " << node.name << ";\n";
        ss << "    " << node.name << ".albedo = vec3(" << pbr.albedo[0] << ", "
           << pbr.albedo[1] << ", " << pbr.albedo[2] << ");\n";
        ss << "    " << node.name << ".roughness = " << pbr.roughness << ";\n";
        ss << "    " << node.name << ".metallic = " << pbr.metallic << ";\n";
        ss << "    " << node.name << ".ao = 1.0;\n";

    } else if (std::holds_alternative<TextureNode>(node.data)) {
        const auto& tex = std::get<TextureNode>(node.data);
        ss << "    // Texture node: " << node.name << "\n";
        ss << "    vec4 " << node.name << "_tex = texture(" << tex.texture_name << ", " << tex.uv_input << ");\n";
        ss << "    PBRMaterial " << node.name << ";\n";
        ss << "    " << node.name << ".albedo = " << node.name << "_tex.rgb;\n";
        ss << "    " << node.name << ".roughness = 0.5;\n";
        ss << "    " << node.name << ".metallic = 0.0;\n";
        ss << "    " << node.name << ".ao = 1.0;\n";
    }

    ss << "\n";
    return ss.str();
}

std::string MaterialCompiler::generate_vertex_shader(const CompilerOptions& options) const {
    std::ostringstream ss;

    ss << "#version " << options.glsl_version << "\n\n";

    ss << R"(
layout(location = 0) in vec3 aPosition;
layout(location = 1) in vec3 aNormal;
layout(location = 2) in vec2 aTexCoord;

layout(location = 0) out vec3 vWorldPos;
layout(location = 1) out vec3 vNormal;
layout(location = 2) out vec2 vTexCoord;

uniform mat4 uModel;
uniform mat4 uView;
uniform mat4 uProjection;
uniform mat3 uNormalMatrix;

void main() {
    vec4 worldPos = uModel * vec4(aPosition, 1.0);
    vWorldPos = worldPos.xyz;
    vNormal = normalize(uNormalMatrix * aNormal);
    vTexCoord = aTexCoord;
    gl_Position = uProjection * uView * worldPos;
}
)";

    return ss.str();
}

std::string MaterialCompiler::generate_fragment_shader(const MaterialGraph& graph,
                                                        const CompilerOptions& options) const {
    std::ostringstream ss;

    ss << "#version " << options.glsl_version << "\n\n";

    // Inputs
    ss << R"(
layout(location = 0) in vec3 vWorldPos;
layout(location = 1) in vec3 vNormal;
layout(location = 2) in vec2 vTexCoord;

layout(location = 0) out vec4 fragColor;

uniform vec3 uCameraPos;
uniform vec3 uLightPos;
uniform vec3 uLightColor;
uniform float uAmbientStrength;
)";

    // Add noise library if needed
    if (options.include_noise_functions) {
        ss << generate_noise_library();
    }

    // Add PBR library if needed
    if (options.include_pbr_lighting) {
        ss << generate_pbr_library();
    }

    // Main function
    ss << "\nvoid main() {\n";
    ss << "    vec3 worldPos = vWorldPos;\n";
    ss << "    vec3 N = normalize(vNormal);\n";
    ss << "    vec3 V = normalize(uCameraPos - vWorldPos);\n";
    ss << "    vec3 L = normalize(uLightPos - vWorldPos);\n";
    ss << "    vec2 uv0 = vTexCoord;\n\n";

    // Generate code for each node in evaluation order
    for (const auto& node_name : graph.evaluation_order) {
        auto it = graph.nodes.find(node_name);
        if (it != graph.nodes.end()) {
            ss << generate_node_code(it->second);
        }
    }

    // Final output
    ss << "    // Final material output\n";
    ss << "    PBRMaterial finalMaterial = " << graph.output_node << ";\n\n";

    if (options.include_pbr_lighting) {
        ss << "    // Calculate lighting\n";
        ss << "    float luminance = dot(finalMaterial.albedo, vec3(0.2126, 0.7152, 0.0722));\n";
        ss << "    finalMaterial.albedo = clamp(mix(vec3(luminance), finalMaterial.albedo, 1.3), 0.0, 1.0);\n";
        ss << "    vec3 ambient = uAmbientStrength * finalMaterial.albedo * finalMaterial.ao;\n";
        ss << "    vec3 Lo = calculatePBR(finalMaterial, N, V, L, uLightColor);\n";
        ss << "    vec3 color = ambient + Lo;\n\n";
        ss << "    // Gamma correction\n";
        ss << "    color = pow(color, vec3(1.0/2.2));\n\n";
        ss << "    fragColor = vec4(color, 1.0);\n";
    } else {
        ss << "    fragColor = vec4(finalMaterial.albedo, 1.0);\n";
    }

    ss << "}\n";

    return ss.str();
}

CompiledShader MaterialCompiler::compile(const MaterialGraph& graph,
                                          const CompilerOptions& options) {
    CompiledShader result;

    // Make a mutable copy for sorting
    MaterialGraph sorted_graph = graph;

    // Validate graph
    if (sorted_graph.nodes.empty()) {
        result.valid = false;
        result.error_message = "Empty material graph";
        return result;
    }

    if (sorted_graph.nodes.find(sorted_graph.output_node) == sorted_graph.nodes.end()) {
        result.valid = false;
        result.error_message = "Output node '" + sorted_graph.output_node + "' not found";
        return result;
    }

    // Topological sort
    if (!topological_sort(sorted_graph)) {
        result.valid = false;
        result.error_message = "Cyclic dependency detected in material graph";
        return result;
    }

    // Generate shaders
    result.vertex_source = generate_vertex_shader(options);
    result.fragment_source = generate_fragment_shader(sorted_graph, options);

    // Compute hash
    result.hash = compute_hash(graph);

    result.valid = true;
    return result;
}

uint64_t MaterialCompiler::compute_hash(const MaterialGraph& graph) {
    uint64_t hash = fnv1a_hash(graph.output_node);

    // Sort node names for deterministic hashing
    std::vector<std::string> names;
    for (const auto& [name, _] : graph.nodes) {
        names.push_back(name);
    }
    std::sort(names.begin(), names.end());

    for (const auto& name : names) {
        hash = hash_combine(hash, fnv1a_hash(name));

        const auto& node = graph.nodes.at(name);
        hash = hash_combine(hash, fnv1a_hash(node.type));

        // Hash node-specific data
        if (std::holds_alternative<NoiseNode>(node.data)) {
            const auto& n = std::get<NoiseNode>(node.data);
            hash = hash_combine(hash, static_cast<uint64_t>(n.seed));
            hash = hash_combine(hash, static_cast<uint64_t>(n.frequency * 1000));
        } else if (std::holds_alternative<WarpNode>(node.data)) {
            const auto& w = std::get<WarpNode>(node.data);
            hash = hash_combine(hash, fnv1a_hash(w.input));
            hash = hash_combine(hash, static_cast<uint64_t>(w.strength * 1000));
        } else if (std::holds_alternative<BlendNode>(node.data)) {
            const auto& b = std::get<BlendNode>(node.data);
            hash = hash_combine(hash, fnv1a_hash(b.input_a));
            hash = hash_combine(hash, fnv1a_hash(b.input_b));
            hash = hash_combine(hash, static_cast<uint64_t>(b.factor * 1000));
        } else if (std::holds_alternative<PBRConstNode>(node.data)) {
            const auto& p = std::get<PBRConstNode>(node.data);
            hash = hash_combine(hash, static_cast<uint64_t>(p.albedo[0] * 1000));
            hash = hash_combine(hash, static_cast<uint64_t>(p.albedo[1] * 1000));
            hash = hash_combine(hash, static_cast<uint64_t>(p.albedo[2] * 1000));
            hash = hash_combine(hash, static_cast<uint64_t>(p.roughness * 1000));
        }
    }

    return hash;
}

// ============================================================================
// ShaderCache Implementation
// ============================================================================

const CompiledShader* ShaderCache::get(uint64_t hash) const {
    auto it = cache_.find(hash);
    if (it != cache_.end()) {
        return &it->second;
    }
    return nullptr;
}

void ShaderCache::put(uint64_t hash, const CompiledShader& shader) {
    cache_[hash] = shader;
}

void ShaderCache::clear() {
    cache_.clear();
}

// ============================================================================
// Utility Functions
// ============================================================================

MaterialGraph create_noise_material(uint32_t seed, float frequency) {
    MaterialGraph graph;

    MaterialNode noise_node;
    noise_node.name = "noise";
    noise_node.type = "noise";
    NoiseNode noise_data;
    noise_data.seed = seed;
    noise_data.frequency = frequency;
    noise_node.data = noise_data;

    graph.nodes["noise"] = noise_node;
    graph.output_node = "noise";

    return graph;
}

MaterialGraph create_pbr_material(const std::array<float, 3>& albedo,
                                   float roughness, float metallic) {
    MaterialGraph graph;

    MaterialNode pbr_node;
    pbr_node.name = "pbr";
    pbr_node.type = "pbr_const";
    PBRConstNode pbr_data;
    pbr_data.albedo = albedo;
    pbr_data.roughness = roughness;
    pbr_data.metallic = metallic;
    pbr_node.data = pbr_data;

    graph.nodes["pbr"] = pbr_node;
    graph.output_node = "pbr";

    return graph;
}

MaterialGraph create_blend_material(const MaterialGraph& a,
                                     const MaterialGraph& b,
                                     float factor) {
    MaterialGraph graph;

    // Copy nodes from both graphs with prefixes
    for (const auto& [name, node] : a.nodes) {
        MaterialNode copy = node;
        copy.name = "a_" + name;
        graph.nodes[copy.name] = copy;
    }

    for (const auto& [name, node] : b.nodes) {
        MaterialNode copy = node;
        copy.name = "b_" + name;
        graph.nodes[copy.name] = copy;
    }

    // Create blend node
    MaterialNode blend_node;
    blend_node.name = "blend";
    blend_node.type = "blend";
    BlendNode blend_data;
    blend_data.input_a = "a_" + a.output_node;
    blend_data.input_b = "b_" + b.output_node;
    blend_data.factor = factor;
    blend_node.data = blend_data;

    graph.nodes["blend"] = blend_node;
    graph.output_node = "blend";

    return graph;
}

} // namespace materials
