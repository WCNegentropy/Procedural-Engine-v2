#pragma once

#include <cstdint>
#include <vector>
#include <array>
#include <string>
#include <unordered_map>
#include <cmath>

/**
 * Procedural prop mesh synthesis utilities.
 *
 * This module provides C++ implementations for generating meshes from
 * prop descriptors created by the Python reference implementation.
 * Supports:
 * - Rock meshes from CSG sphere descriptors
 * - Tree meshes from L-system skeleton descriptors
 * - Building meshes from BSP shape grammar descriptors
 * - Creature meshes from metaball implicit surface descriptors
 */

namespace props {

/**
 * 3D vector for mesh operations.
 */
struct Vec3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator*(float s) const { return Vec3(x * s, y * s, z * s); }
    Vec3 operator/(float s) const { return Vec3(x / s, y / s, z / s); }
    Vec3& operator+=(const Vec3& o) { x += o.x; y += o.y; z += o.z; return *this; }

    float dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    Vec3 cross(const Vec3& o) const {
        return Vec3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);
    }
    float length() const { return std::sqrt(x * x + y * y + z * z); }
    Vec3 normalized() const {
        float len = length();
        return (len > 0.0f) ? Vec3(x / len, y / len, z / len) : Vec3(0, 0, 0);
    }
};

/**
 * Triangle mesh data structure.
 */
struct Mesh {
    std::vector<Vec3> vertices;     // Vertex positions
    std::vector<Vec3> normals;      // Vertex normals (same count as vertices)
    std::vector<Vec3> colors;       // Vertex colors RGB (same count as vertices)
    std::vector<uint32_t> indices;  // Triangle indices (multiple of 3)

    void clear() {
        vertices.clear();
        normals.clear();
        colors.clear();
        indices.clear();
    }

    size_t vertex_count() const { return vertices.size(); }
    size_t triangle_count() const { return indices.size() / 3; }

    /**
     * Validate mesh integrity.
     */
    bool validate() const {
        if (vertices.size() != normals.size()) {
            return false;
        }
        // Colors are optional - if present, must match vertex count
        if (!colors.empty() && colors.size() != vertices.size()) {
            return false;
        }
        if (indices.size() % 3 != 0) {
            return false;
        }
        for (uint32_t idx : indices) {
            if (idx >= vertices.size()) {
                return false;
            }
        }
        return true;
    }

    /**
     * Ensure normals array matches vertices array size.
     */
    void ensure_normals() {
        while (normals.size() < vertices.size()) {
            normals.push_back(Vec3(0.0f, 1.0f, 0.0f));
        }
        if (normals.size() > vertices.size()) {
            normals.resize(vertices.size());
        }
    }

    /**
     * Ensure colors array matches vertices array size.
     * Fills missing colors with default white.
     */
    void ensure_colors() {
        while (colors.size() < vertices.size()) {
            colors.push_back(Vec3(1.0f, 1.0f, 1.0f));
        }
        if (colors.size() > vertices.size()) {
            colors.resize(vertices.size());
        }
    }

    /**
     * Set all vertex colors to a uniform color.
     * Useful for entity meshes that should have consistent coloring.
     */
    void set_uniform_color(const Vec3& color) {
        colors.clear();
        colors.reserve(vertices.size());
        for (size_t i = 0; i < vertices.size(); ++i) {
            colors.push_back(color);
        }
    }

    // Append another mesh
    void append(const Mesh& other) {
        uint32_t base_idx = static_cast<uint32_t>(vertices.size());
        vertices.insert(vertices.end(), other.vertices.begin(), other.vertices.end());
        normals.insert(normals.end(), other.normals.begin(), other.normals.end());
        colors.insert(colors.end(), other.colors.begin(), other.colors.end());
        for (uint32_t idx : other.indices) {
            indices.push_back(base_idx + idx);
        }
        ensure_normals();
        ensure_colors();
    }
};

// ============================================================================
// Rock Mesh Generation (Noise-displaced sphere)
// ============================================================================

/**
 * Rock descriptor from Python.
 */
struct RockDescriptor {
    Vec3 position;
    float radius = 0.5f;
    uint32_t noise_seed = 0;     // Seed for deterministic noise displacement
    float noise_scale = 0.15f;   // Displacement magnitude relative to radius
};

/**
 * Generate a noise-displaced sphere mesh for a rock.
 *
 * Each vertex is displaced along its normal by a deterministic hash-based
 * noise value, producing irregular rocky shapes that vary per seed.
 *
 * @param desc Rock descriptor with position, radius, and noise parameters
 * @param segments Number of horizontal segments (longitude)
 * @param rings Number of vertical rings (latitude)
 * @return Triangle mesh for the rock
 */
Mesh generate_rock_mesh(const RockDescriptor& desc, uint32_t segments = 16, uint32_t rings = 12);

// ============================================================================
// Tree Mesh Generation (L-System + Sweep Mesh)
// ============================================================================

/**
 * L-System rule set for tree generation.
 */
struct LSystemRules {
    std::string axiom;
    std::unordered_map<char, std::string> rules;
};

/**
 * Tree descriptor from Python.
 */
struct TreeDescriptor {
    LSystemRules lsystem;
    float angle;        // Branch angle in degrees
    uint32_t iterations;
};

/**
 * Segment of a tree skeleton.
 */
struct TreeSegment {
    Vec3 start;
    Vec3 end;
    float start_radius;
    float end_radius;
};

/**
 * Evaluate L-system string after N iterations.
 */
std::string evaluate_lsystem(const LSystemRules& rules, uint32_t iterations);

/**
 * Generate tree skeleton segments from L-system string.
 *
 * @param lstring Evaluated L-system string
 * @param angle Branch angle in degrees
 * @param segment_length Length of each 'F' segment
 * @param base_radius Starting trunk radius
 * @param taper Radius reduction factor per segment
 * @return Vector of skeleton segments
 */
std::vector<TreeSegment> generate_tree_skeleton(
    const std::string& lstring,
    float angle,
    float segment_length = 1.0f,
    float base_radius = 0.1f,
    float taper = 0.85f
);

/**
 * Generate tree mesh from descriptor.
 *
 * @param desc Tree descriptor with L-system rules
 * @param segments_per_ring Vertices around each cylinder
 * @return Triangle mesh for the tree
 */
Mesh generate_tree_mesh(const TreeDescriptor& desc, uint32_t segments_per_ring = 8);

// ============================================================================
// Building Mesh Generation (BSP Shape Grammar)
// ============================================================================

/**
 * Building block node (BSP tree node).
 */
struct BuildingBlock {
    Vec3 size;
    Vec3 position;  // Offset from parent
    std::vector<BuildingBlock> children;
};

/**
 * Building descriptor from Python.
 */
struct BuildingDescriptor {
    BuildingBlock root;
};

/**
 * Generate mesh for a building block (recursive).
 */
Mesh generate_block_mesh(const BuildingBlock& block, const Vec3& offset = Vec3());

/**
 * Generate building mesh from descriptor.
 */
Mesh generate_building_mesh(const BuildingDescriptor& desc);

// ============================================================================
// Creature Mesh Generation (Metaball Implicit Surface)
// ============================================================================

/**
 * Bone segment in creature skeleton.
 */
struct Bone {
    float length;
    float angle;  // Angle in degrees
};

/**
 * Metaball for implicit surface.
 */
struct Metaball {
    Vec3 center;
    float radius;
    float strength = 1.0f;
};

struct LimbSegment {
    float length = 0.0f;
    float angle = 0.0f;
};

struct LimbMetaball {
    float offset = 0.0f;
    float radius = 0.0f;
};

struct LimbDescriptor {
    uint32_t attach_bone = 0;
    std::string side = "left";
    std::vector<LimbSegment> segments;
    std::vector<LimbMetaball> metaballs;
};

/**
 * Creature descriptor from Python.
 */
struct CreatureDescriptor {
    std::string body_plan = "quadruped";
    std::vector<Bone> skeleton;
    std::vector<Metaball> metaballs;
    std::vector<LimbDescriptor> limbs;
};

/**
 * Evaluate metaball field at a point.
 * Returns the field strength (>= threshold means inside surface).
 */
float evaluate_metaball_field(const std::vector<Metaball>& metaballs, const Vec3& point);

/**
 * Generate creature mesh using marching cubes on metaball field.
 *
 * @param desc Creature descriptor
 * @param grid_resolution Resolution of marching cubes grid
 * @param threshold Field threshold for surface extraction
 * @return Triangle mesh for the creature
 */
Mesh generate_creature_mesh(
    const CreatureDescriptor& desc,
    uint32_t grid_resolution = 32,
    float threshold = 1.0f
);

// ============================================================================
// LOD Generation
// ============================================================================

/**
 * Generate a simplified LOD version of a mesh.
 *
 * @param mesh Input high-detail mesh
 * @param target_ratio Target triangle count ratio (0.0 to 1.0)
 * @return Simplified mesh
 */
Mesh generate_lod(const Mesh& mesh, float target_ratio);

// ============================================================================
// Bush Mesh Generation (Noise-displaced foliage sphere)
// ============================================================================

/**
 * Bush descriptor from Python.
 */
struct BushDescriptor {
    Vec3 position;
    float radius = 0.6f;
    uint32_t noise_seed = 0;
    float leaf_density = 0.8f;  // How full the foliage looks (0.5-1.0)
};

/**
 * Generate a noise-displaced sphere mesh for a bush.
 *
 * Similar to rock mesh but squashed vertically and with more noise at the
 * top to simulate irregular foliage. Uses fewer segments for performance.
 *
 * @param desc Bush descriptor with position, radius, and noise seed
 * @param segments Horizontal segments (longitude)
 * @param rings Vertical rings (latitude)
 * @return Triangle mesh for the bush
 */
Mesh generate_bush_mesh(const BushDescriptor& desc, uint32_t segments = 12, uint32_t rings = 8);

// ============================================================================
// Pine Tree Mesh Generation (Stacked cones on trunk cylinder)
// ============================================================================

/**
 * Pine tree descriptor from Python.
 */
struct PineTreeDescriptor {
    Vec3 position;
    float trunk_height = 3.0f;
    float trunk_radius = 0.15f;
    uint32_t canopy_layers = 3;
    float canopy_radius = 1.2f;
};

/**
 * Generate a pine tree mesh: cylinder trunk + stacked cone canopy layers.
 *
 * @param desc Pine tree descriptor
 * @param trunk_segments Segments around the trunk
 * @param cone_segments Segments around each cone layer
 * @return Triangle mesh for the pine tree
 */
Mesh generate_pine_tree_mesh(const PineTreeDescriptor& desc,
                              uint32_t trunk_segments = 8,
                              uint32_t cone_segments = 12);

// ============================================================================
// Dead Tree Mesh Generation (Sparse L-system skeleton)
// ============================================================================

/**
 * Dead tree descriptor from Python.
 * Reuses LSystemRules/TreeDescriptor format with sparser rules.
 */
struct DeadTreeDescriptor {
    LSystemRules lsystem;
    float angle;
    uint32_t iterations;
};

/**
 * Generate a dead tree mesh from L-system (thinner, no leaves).
 *
 * @param desc Dead tree descriptor
 * @param segments_per_ring Segments around each branch cylinder
 * @return Triangle mesh for the dead tree
 */
Mesh generate_dead_tree_mesh(const DeadTreeDescriptor& desc,
                              uint32_t segments_per_ring = 6);

// ============================================================================
// Fallen Log Mesh Generation (Horizontal cylinder)
// ============================================================================

/**
 * Fallen log descriptor from Python.
 */
struct FallenLogDescriptor {
    Vec3 position;
    float length = 2.5f;
    float radius = 0.2f;
    float rotation_y = 0.0f;  // Degrees
};

/**
 * Generate a fallen log mesh (horizontal cylinder lying on the ground).
 *
 * @param desc Fallen log descriptor
 * @param segments Segments around the cylinder
 * @return Triangle mesh for the fallen log
 */
Mesh generate_fallen_log_mesh(const FallenLogDescriptor& desc,
                               uint32_t segments = 8);

// ============================================================================
// Boulder Cluster Mesh Generation (Multiple rocks in a group)
// ============================================================================

/**
 * Sub-rock within a boulder cluster.
 */
struct SubRock {
    Vec3 offset;        // Offset from cluster center
    float radius = 0.5f;
    uint32_t noise_seed = 0;
};

/**
 * Boulder cluster descriptor from Python.
 */
struct BoulderClusterDescriptor {
    Vec3 position;
    std::vector<SubRock> sub_rocks;
};

/**
 * Generate a boulder cluster mesh (multiple rocks packed together).
 *
 * @param desc Boulder cluster descriptor
 * @param segments_per_rock Segments per individual rock sphere
 * @param rings_per_rock Rings per individual rock sphere
 * @return Combined triangle mesh for the entire cluster
 */
Mesh generate_boulder_cluster_mesh(const BoulderClusterDescriptor& desc,
                                    uint32_t segments_per_rock = 10,
                                    uint32_t rings_per_rock = 8);

// ============================================================================
// Flower Patch Mesh Generation (Cluster of simple stems)
// ============================================================================

/**
 * Flower patch descriptor from Python.
 */
struct FlowerPatchDescriptor {
    Vec3 position;
    uint32_t stem_count = 6;
    float patch_radius = 0.5f;
    uint32_t color_seed = 0;
};

/**
 * Generate a flower patch mesh (cluster of thin stems with small spheres).
 *
 * @param desc Flower patch descriptor
 * @param stem_segments Segments around each stem cylinder
 * @return Triangle mesh for the flower patch
 */
Mesh generate_flower_patch_mesh(const FlowerPatchDescriptor& desc,
                                 uint32_t stem_segments = 4);

// ============================================================================
// Mushroom Mesh Generation (Cap + Stem)
// ============================================================================

/**
 * Mushroom descriptor from Python.
 */
struct MushroomDescriptor {
    Vec3 position;
    float cap_radius = 0.3f;
    float stem_height = 0.4f;
    float stem_radius = 0.06f;
};

/**
 * Generate a mushroom mesh (cylinder stem + flattened hemisphere cap).
 *
 * @param desc Mushroom descriptor
 * @param cap_segments Segments around the cap
 * @param cap_rings Rings in the cap hemisphere
 * @param stem_segments Segments around the stem
 * @return Triangle mesh for the mushroom
 */
Mesh generate_mushroom_mesh(const MushroomDescriptor& desc,
                             uint32_t cap_segments = 12,
                             uint32_t cap_rings = 6,
                             uint32_t stem_segments = 8);

// ============================================================================
// Cactus Mesh Generation (Column + arms)
// ============================================================================

/**
 * Cactus arm descriptor.
 */
struct CactusArm {
    float attach_height = 0.5f;  // Height ratio (0-1) along main column
    float length = 0.6f;
    float angle = 0.0f;         // Degrees around Y axis
};

/**
 * Cactus descriptor from Python.
 */
struct CactusDescriptor {
    Vec3 position;
    float main_height = 2.5f;
    float main_radius = 0.18f;
    std::vector<CactusArm> arms;
};

/**
 * Generate a cactus mesh (main cylinder column + upward-bending arms).
 *
 * @param desc Cactus descriptor
 * @param segments Segments around each cylinder
 * @return Triangle mesh for the cactus
 */
Mesh generate_cactus_mesh(const CactusDescriptor& desc,
                           uint32_t segments = 8);

// ============================================================================
// Primitive Mesh Generation
// ============================================================================

/**
 * Generate an axis-aligned box mesh.
 *
 * @param size Size of the box (width, height, depth)
 * @param center Center position of the box
 * @return Triangle mesh for the box
 */
Mesh generate_box_mesh(const Vec3& size, const Vec3& center = Vec3(0, 0, 0));

/**
 * Generate a capsule mesh (cylinder with hemisphere caps).
 *
 * @param radius Radius of the capsule
 * @param height Height of the cylindrical section (excluding caps)
 * @param segments Number of segments around the circumference
 * @param rings Number of rings in each hemisphere cap
 * @return Triangle mesh for the capsule
 */
Mesh generate_capsule_mesh(float radius, float height, uint32_t segments = 16, uint32_t rings = 8);

/**
 * Generate a cylinder mesh.
 *
 * @param radius Radius of the cylinder
 * @param height Height of the cylinder
 * @param segments Number of segments around the circumference
 * @return Triangle mesh for the cylinder
 */
Mesh generate_cylinder_mesh(float radius, float height, uint32_t segments = 16);

/**
 * Generate a cone mesh.
 *
 * @param radius Base radius of the cone
 * @param height Height of the cone
 * @param segments Number of segments around the base
 * @return Triangle mesh for the cone
 */
Mesh generate_cone_mesh(float radius, float height, uint32_t segments = 16);

/**
 * Generate a subdivided plane mesh.
 *
 * @param size Size of the plane (width, depth)
 * @param subdivisions Number of subdivisions per axis
 * @return Triangle mesh for the plane
 */
Mesh generate_plane_mesh(const Vec3& size, uint32_t subdivisions = 1);

} // namespace props
