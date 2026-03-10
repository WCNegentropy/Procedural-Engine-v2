#include "props.h"
#include <cmath>
#include <algorithm>
#include <sstream>
#include <stack>

namespace props {

// Constants
static constexpr float PI = 3.14159265358979323846f;
static constexpr float DEG_TO_RAD = PI / 180.0f;
// Quantize vertices to 1e-6 world units before hashing so shared surface
// vertices dedupe reliably without collapsing distinct points at creature scale.
static constexpr double VERTEX_CACHE_PRECISION_SCALE = 1000000.0;

// ============================================================================
// Rock Mesh Generation (Noise-displaced Sphere)
// ============================================================================

// Simple deterministic hash for noise grid (returns 0..1)
static float noise_hash(uint32_t seed, uint32_t x, uint32_t y) {
    uint32_t h = seed ^ (x * 2654435761u) ^ (y * 2246822519u);
    h ^= h >> 16;
    h *= 0x45d9f3bu;
    h ^= h >> 16;
    h *= 0x45d9f3bu;
    h ^= h >> 16;
    return static_cast<float>(h & 0xFFFFu) / 65535.0f;
}

// Smooth interpolation (Hermite/smoothstep)
static float smoothstep(float t) {
    return t * t * (3.0f - 2.0f * t);
}

// Sample spatially coherent noise on the sphere using bilinear interpolation
// over a coarse grid, producing smooth boulder-like deformation.
static float sphere_noise(uint32_t seed, float phi, float theta,
                          uint32_t grid_rings, uint32_t grid_segments) {
    // Map spherical coords to grid coordinates
    float gv = phi / PI * static_cast<float>(grid_rings);
    float gu = theta / (2.0f * PI) * static_cast<float>(grid_segments);

    // Grid cell corners
    uint32_t gv0 = static_cast<uint32_t>(gv) % grid_rings;
    uint32_t gv1 = (gv0 + 1) % (grid_rings + 1);
    uint32_t gu0 = static_cast<uint32_t>(gu) % grid_segments;
    uint32_t gu1 = (gu0 + 1) % grid_segments;

    // Fractional position within cell
    float fv = smoothstep(gv - std::floor(gv));
    float fu = smoothstep(gu - std::floor(gu));

    // Hash at four corners
    float h00 = noise_hash(seed, gu0, gv0);
    float h10 = noise_hash(seed, gu1, gv0);
    float h01 = noise_hash(seed, gu0, gv1);
    float h11 = noise_hash(seed, gu1, gv1);

    // Bilinear interpolation
    float top = h00 + (h10 - h00) * fu;
    float bot = h01 + (h11 - h01) * fu;
    return top + (bot - top) * fv;
}

Mesh generate_rock_mesh(const RockDescriptor& desc, uint32_t segments, uint32_t rings) {
    Mesh mesh;

    float noise_magnitude = desc.noise_scale * desc.radius;

    // Coarse noise grid resolution (controls bumpiness frequency)
    uint32_t grid_rings = 5;
    uint32_t grid_segments = 7;

    // Generate UV sphere vertices with smooth noise displacement
    for (uint32_t ring = 0; ring <= rings; ++ring) {
        float phi = PI * static_cast<float>(ring) / static_cast<float>(rings);
        float sin_phi = std::sin(phi);
        float cos_phi = std::cos(phi);

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            // Normal (unit sphere)
            Vec3 normal(sin_phi * cos_theta, cos_phi, sin_phi * sin_theta);

            // Spatially coherent noise: two octaves for natural variation
            float n1 = sphere_noise(desc.noise_seed, phi, theta,
                                    grid_rings, grid_segments);
            float n2 = sphere_noise(desc.noise_seed + 7919u, phi, theta,
                                    grid_rings * 2, grid_segments * 2);
            float noise = (n1 * 0.7f + n2 * 0.3f) * 2.0f - 1.0f;  // -1..+1

            float displaced_radius = desc.radius + noise * noise_magnitude;

            // Position (displaced and translated)
            Vec3 vertex = desc.position + normal * displaced_radius;

            mesh.vertices.push_back(vertex);
            mesh.normals.push_back(normal);
        }
    }

    // Generate indices
    for (uint32_t ring = 0; ring < rings; ++ring) {
        for (uint32_t seg = 0; seg < segments; ++seg) {
            uint32_t current = ring * (segments + 1) + seg;
            uint32_t next = current + segments + 1;

            // Two triangles per quad
            mesh.indices.push_back(current);
            mesh.indices.push_back(next);
            mesh.indices.push_back(current + 1);

            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(next);
            mesh.indices.push_back(next + 1);
        }
    }

    // Recompute normals from displaced geometry for correct lighting
    // Reset normals to zero
    for (auto& n : mesh.normals) {
        n = Vec3(0, 0, 0);
    }
    // Accumulate face normals
    for (size_t i = 0; i < mesh.indices.size(); i += 3) {
        uint32_t i0 = mesh.indices[i];
        uint32_t i1 = mesh.indices[i + 1];
        uint32_t i2 = mesh.indices[i + 2];
        Vec3 edge1 = mesh.vertices[i1] - mesh.vertices[i0];
        Vec3 edge2 = mesh.vertices[i2] - mesh.vertices[i0];
        Vec3 face_normal = edge1.cross(edge2);
        mesh.normals[i0] += face_normal;
        mesh.normals[i1] += face_normal;
        mesh.normals[i2] += face_normal;
    }
    // Normalize
    for (auto& n : mesh.normals) {
        float len = n.length();
        if (len > 1e-6f) {
            n = n / len;
        }
    }

    return mesh;
}

// ============================================================================
// Tree Mesh Generation (L-System + Sweep Mesh)
// ============================================================================

// Maximum L-system string length to prevent memory exhaustion
static constexpr size_t MAX_LSYSTEM_LENGTH = 1 * 1024 * 1024;  // FIX: Reduced to 1 MB (was 10 MB)
// Maximum L-system iterations to prevent runaway growth
static constexpr uint32_t MAX_LSYSTEM_ITERATIONS = 6;  // FIX: Reduced to 6 (was 15)

std::string evaluate_lsystem(const LSystemRules& rules, uint32_t iterations) {
    std::string current = rules.axiom;

    // Clamp iterations to prevent runaway growth
    uint32_t safe_iterations = std::min(iterations, MAX_LSYSTEM_ITERATIONS);

    for (uint32_t iter = 0; iter < safe_iterations; ++iter) {
        std::string next;
        // Estimate growth but don't exceed max length
        size_t estimated_size = std::min(current.size() * 4, MAX_LSYSTEM_LENGTH);
        next.reserve(estimated_size);

        for (char c : current) {
            auto it = rules.rules.find(c);
            if (it != rules.rules.end()) {
                next += it->second;
            } else {
                next += c;
            }

            // Check if we've exceeded maximum length
            if (next.size() > MAX_LSYSTEM_LENGTH) {
                // Return truncated result
                return next.substr(0, MAX_LSYSTEM_LENGTH);
            }
        }
        current = std::move(next);
    }

    return current;
}

std::vector<TreeSegment> generate_tree_skeleton(
    const std::string& lstring,
    float angle,
    float segment_length,
    float base_radius,
    float taper
) {
    std::vector<TreeSegment> segments;

    // Turtle state
    struct TurtleState {
        Vec3 position;
        Vec3 direction;
        float radius;
    };

    std::stack<TurtleState> state_stack;
    TurtleState turtle;
    turtle.position = Vec3(0, 0, 0);
    turtle.direction = Vec3(0, 1, 0);  // Start pointing up
    turtle.radius = base_radius;

    float angle_rad = angle * DEG_TO_RAD;

    for (char c : lstring) {
        switch (c) {
            case 'F': {
                // Move forward and draw
                Vec3 end = turtle.position + turtle.direction * segment_length;
                float end_radius = turtle.radius * taper;

                TreeSegment seg;
                seg.start = turtle.position;
                seg.end = end;
                seg.start_radius = turtle.radius;
                seg.end_radius = end_radius;
                segments.push_back(seg);

                turtle.position = end;
                turtle.radius = end_radius;
                break;
            }
            case '+': {
                // Rotate right (around Z axis in 2D, but we use 3D rotation)
                float cos_a = std::cos(angle_rad);
                float sin_a = std::sin(angle_rad);
                Vec3 d = turtle.direction;
                // Rotate around Z axis
                turtle.direction = Vec3(
                    d.x * cos_a - d.y * sin_a,
                    d.x * sin_a + d.y * cos_a,
                    d.z
                );
                break;
            }
            case '-': {
                // Rotate left
                float cos_a = std::cos(-angle_rad);
                float sin_a = std::sin(-angle_rad);
                Vec3 d = turtle.direction;
                turtle.direction = Vec3(
                    d.x * cos_a - d.y * sin_a,
                    d.x * sin_a + d.y * cos_a,
                    d.z
                );
                break;
            }
            case '[': {
                // Push state
                state_stack.push(turtle);
                break;
            }
            case ']': {
                // Pop state
                if (!state_stack.empty()) {
                    turtle = state_stack.top();
                    state_stack.pop();
                }
                break;
            }
            default:
                // Ignore unknown characters
                break;
        }
    }

    return segments;
}

// Helper: Generate a cylinder mesh between two points
static Mesh generate_cylinder(
    const Vec3& start, const Vec3& end,
    float start_radius, float end_radius,
    uint32_t segments
) {
    Mesh mesh;

    Vec3 axis = end - start;
    float length = axis.length();
    if (length < 1e-6f) return mesh;

    axis = axis / length;

    // Find perpendicular vectors
    Vec3 perp1, perp2;
    if (std::abs(axis.y) < 0.9f) {
        perp1 = Vec3(0, 1, 0).cross(axis).normalized();
    } else {
        perp1 = Vec3(1, 0, 0).cross(axis).normalized();
    }
    perp2 = axis.cross(perp1).normalized();

    // Generate vertices for start and end caps
    uint32_t base_start = 0;
    uint32_t base_end = segments;

    for (uint32_t i = 0; i < segments; ++i) {
        float theta = 2.0f * PI * static_cast<float>(i) / static_cast<float>(segments);
        float cos_t = std::cos(theta);
        float sin_t = std::sin(theta);

        Vec3 offset = perp1 * cos_t + perp2 * sin_t;

        // Start ring
        mesh.vertices.push_back(start + offset * start_radius);
        mesh.normals.push_back(offset);

        // End ring
        mesh.vertices.push_back(end + offset * end_radius);
        mesh.normals.push_back(offset);
    }

    // Generate indices for cylinder body
    for (uint32_t i = 0; i < segments; ++i) {
        uint32_t i0 = i * 2;
        uint32_t i1 = i * 2 + 1;
        uint32_t i2 = ((i + 1) % segments) * 2;
        uint32_t i3 = ((i + 1) % segments) * 2 + 1;

        // Two triangles per quad
        mesh.indices.push_back(i0);
        mesh.indices.push_back(i1);
        mesh.indices.push_back(i2);

        mesh.indices.push_back(i2);
        mesh.indices.push_back(i1);
        mesh.indices.push_back(i3);
    }

    return mesh;
}

Mesh generate_tree_mesh(const TreeDescriptor& desc, uint32_t segments_per_ring) {
    Mesh mesh;

    // Evaluate L-system
    std::string lstring = evaluate_lsystem(desc.lsystem, desc.iterations);

    // Generate skeleton
    auto skeleton = generate_tree_skeleton(lstring, desc.angle);

    // Generate cylinder for each segment
    for (const auto& seg : skeleton) {
        Mesh cylinder = generate_cylinder(
            seg.start, seg.end,
            seg.start_radius, seg.end_radius,
            segments_per_ring
        );
        mesh.append(cylinder);
    }

    return mesh;
}

// ============================================================================
// Building Mesh Generation (BSP Box Mesh)
// ============================================================================

// Helper: Generate a box mesh
static Mesh generate_box(const Vec3& size, const Vec3& offset) {
    Mesh mesh;

    float hx = size.x * 0.5f;
    float hy = size.y * 0.5f;
    float hz = size.z * 0.5f;

    // 8 vertices of a box
    Vec3 corners[8] = {
        offset + Vec3(-hx, -hy, -hz),
        offset + Vec3( hx, -hy, -hz),
        offset + Vec3( hx,  hy, -hz),
        offset + Vec3(-hx,  hy, -hz),
        offset + Vec3(-hx, -hy,  hz),
        offset + Vec3( hx, -hy,  hz),
        offset + Vec3( hx,  hy,  hz),
        offset + Vec3(-hx,  hy,  hz),
    };

    // Face normals
    Vec3 normals[6] = {
        Vec3( 0,  0, -1),  // Front
        Vec3( 0,  0,  1),  // Back
        Vec3(-1,  0,  0),  // Left
        Vec3( 1,  0,  0),  // Right
        Vec3( 0, -1,  0),  // Bottom
        Vec3( 0,  1,  0),  // Top
    };

    // Face vertex indices
    int faces[6][4] = {
        {0, 1, 2, 3},  // Front
        {5, 4, 7, 6},  // Back
        {4, 0, 3, 7},  // Left
        {1, 5, 6, 2},  // Right
        {4, 5, 1, 0},  // Bottom
        {3, 2, 6, 7},  // Top
    };

    for (int f = 0; f < 6; ++f) {
        uint32_t base = static_cast<uint32_t>(mesh.vertices.size());

        // Add 4 vertices for this face
        for (int v = 0; v < 4; ++v) {
            mesh.vertices.push_back(corners[faces[f][v]]);
            mesh.normals.push_back(normals[f]);
        }

        // Add 2 triangles
        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 1);
        mesh.indices.push_back(base + 2);

        mesh.indices.push_back(base + 0);
        mesh.indices.push_back(base + 2);
        mesh.indices.push_back(base + 3);
    }

    return mesh;
}

Mesh generate_block_mesh(const BuildingBlock& block, const Vec3& offset) {
    Mesh mesh;

    if (block.children.empty()) {
        // Leaf node: generate box
        mesh = generate_box(block.size, offset + block.position);
    } else {
        // Internal node: recurse to children
        Vec3 child_offset = offset + block.position;
        for (const auto& child : block.children) {
            Mesh child_mesh = generate_block_mesh(child, child_offset);
            mesh.append(child_mesh);
        }
    }

    return mesh;
}

Mesh generate_building_mesh(const BuildingDescriptor& desc) {
    return generate_block_mesh(desc.root, Vec3());
}

// ============================================================================
// Creature Mesh Generation (Marching Cubes on Metaball Field)
// ============================================================================

float evaluate_metaball_field(const std::vector<Metaball>& metaballs, const Vec3& point) {
    float field = 0.0f;

    for (const auto& ball : metaballs) {
        Vec3 diff = point - ball.center;
        float dist_sq = diff.dot(diff);
        float r_sq = ball.radius * ball.radius;

        // Blinn's metaball: field = strength * exp(-dist^2 / (2*r^2))
        // Simplified: field = strength * r^2 / (dist^2 + epsilon)
        if (dist_sq > 0.0001f) {
            field += ball.strength * r_sq / dist_sq;
        } else {
            field += ball.strength * 10000.0f;  // Very close to center
        }
    }

    return field;
}

// Vertex positions for cube corners
static const float cube_vertices[8][3] = {
    {0, 0, 0}, {1, 0, 0}, {1, 1, 0}, {0, 1, 0},
    {0, 0, 1}, {1, 0, 1}, {1, 1, 1}, {0, 1, 1}
};

// Consistent tetrahedral subdivision of a cube. This avoids the ambiguous
// saddle/fan cases that were leaving holes in the old creature extractor.
static const int cube_tetrahedra[6][4] = {
    {0, 5, 1, 6},
    {0, 1, 2, 6},
    {0, 2, 3, 6},
    {0, 3, 7, 6},
    {0, 7, 4, 6},
    {0, 4, 5, 6}
};

// Interpolate vertex position along edge
static Vec3 interpolate_edge(
    const Vec3& p1, const Vec3& p2,
    float v1, float v2, float threshold
) {
    if (std::abs(v1 - v2) < 1e-6f) {
        return p1;
    }
    float t = (threshold - v1) / (v2 - v1);
    t = std::clamp(t, 0.0f, 1.0f);
    return p1 + (p2 - p1) * t;
}

static Vec3 evaluate_field_gradient(
    const std::vector<Metaball>& metaballs,
    const Vec3& point,
    float epsilon
) {
    float fx = evaluate_metaball_field(metaballs, point + Vec3(epsilon, 0.0f, 0.0f))
             - evaluate_metaball_field(metaballs, point - Vec3(epsilon, 0.0f, 0.0f));
    float fy = evaluate_metaball_field(metaballs, point + Vec3(0.0f, epsilon, 0.0f))
             - evaluate_metaball_field(metaballs, point - Vec3(0.0f, epsilon, 0.0f));
    float fz = evaluate_metaball_field(metaballs, point + Vec3(0.0f, 0.0f, epsilon))
             - evaluate_metaball_field(metaballs, point - Vec3(0.0f, 0.0f, epsilon));
    return Vec3(fx, fy, fz);
}

static std::string vertex_key(const Vec3& vertex) {
    std::ostringstream stream;
    stream << static_cast<long long>(std::llround(vertex.x * VERTEX_CACHE_PRECISION_SCALE))
           << ':'
           << static_cast<long long>(std::llround(vertex.y * VERTEX_CACHE_PRECISION_SCALE))
           << ':'
           << static_cast<long long>(std::llround(vertex.z * VERTEX_CACHE_PRECISION_SCALE));
    return stream.str();
}

static uint32_t get_or_add_vertex(
    Mesh& mesh,
    std::unordered_map<std::string, uint32_t>& vertex_cache,
    const Vec3& vertex
) {
    std::string key = vertex_key(vertex);
    auto it = vertex_cache.find(key);
    if (it != vertex_cache.end()) {
        return it->second;
    }
    uint32_t index = static_cast<uint32_t>(mesh.vertices.size());
    mesh.vertices.push_back(vertex);
    vertex_cache.emplace(std::move(key), index);
    return index;
}

static void emit_triangle(
    Mesh& mesh,
    std::unordered_map<std::string, uint32_t>& vertex_cache,
    const Vec3& v0,
    const Vec3& v1,
    const Vec3& v2
) {
    mesh.indices.push_back(get_or_add_vertex(mesh, vertex_cache, v0));
    mesh.indices.push_back(get_or_add_vertex(mesh, vertex_cache, v1));
    mesh.indices.push_back(get_or_add_vertex(mesh, vertex_cache, v2));
}

static void polygonise_tetrahedron(
    Mesh& mesh,
    std::unordered_map<std::string, uint32_t>& vertex_cache,
    const Vec3 positions[4],
    const float values[4],
    float threshold
) {
    int inside[4];
    int outside[4];
    int inside_count = 0;
    int outside_count = 0;

    for (int i = 0; i < 4; ++i) {
        if (values[i] >= threshold) {
            inside[inside_count++] = i;
        } else {
            outside[outside_count++] = i;
        }
    }

    if (inside_count == 0 || inside_count == 4) {
        return;
    }

    if (inside_count == 1 || inside_count == 3) {
        bool invert = inside_count == 3;
        int apex = invert ? outside[0] : inside[0];
        const int* ring = invert ? inside : outside;

        Vec3 v0 = interpolate_edge(
            positions[apex], positions[ring[0]], values[apex], values[ring[0]], threshold
        );
        Vec3 v1 = interpolate_edge(
            positions[apex], positions[ring[1]], values[apex], values[ring[1]], threshold
        );
        Vec3 v2 = interpolate_edge(
            positions[apex], positions[ring[2]], values[apex], values[ring[2]], threshold
        );

        if (invert) {
            emit_triangle(mesh, vertex_cache, v0, v2, v1);
        } else {
            emit_triangle(mesh, vertex_cache, v0, v1, v2);
        }
        return;
    }

    Vec3 quad[4] = {
        interpolate_edge(
            positions[inside[0]], positions[outside[0]],
            values[inside[0]], values[outside[0]], threshold
        ),
        interpolate_edge(
            positions[inside[0]], positions[outside[1]],
            values[inside[0]], values[outside[1]], threshold
        ),
        interpolate_edge(
            positions[inside[1]], positions[outside[0]],
            values[inside[1]], values[outside[0]], threshold
        ),
        interpolate_edge(
            positions[inside[1]], positions[outside[1]],
            values[inside[1]], values[outside[1]], threshold
        ),
    };

    emit_triangle(mesh, vertex_cache, quad[0], quad[1], quad[2]);
    emit_triangle(mesh, vertex_cache, quad[1], quad[3], quad[2]);
}

static Mesh finalize_creature_mesh(
    const Mesh& raw_mesh,
    const std::vector<Metaball>& metaballs,
    float cell_size
) {
    Mesh mesh;
    mesh.vertices = raw_mesh.vertices;
    mesh.normals.assign(mesh.vertices.size(), Vec3(0.0f, 0.0f, 0.0f));

    // Sample gradients far enough away from the surface to avoid cancellation on
    // tiny cells, but still within the local neighborhood of the isosurface.
    float epsilon = std::max(cell_size * 0.25f, 1e-4f);
    // Reject nearly-zero-area triangles created by coplanar or duplicate edge
    // intersections without stripping legitimate small features.
    float area_epsilon = std::max(cell_size * cell_size * 1e-4f, 1e-8f);

    for (size_t i = 0; i + 2 < raw_mesh.indices.size(); i += 3) {
        uint32_t i0 = raw_mesh.indices[i];
        uint32_t i1 = raw_mesh.indices[i + 1];
        uint32_t i2 = raw_mesh.indices[i + 2];

        const Vec3& v0 = raw_mesh.vertices[i0];
        const Vec3& v1 = raw_mesh.vertices[i1];
        const Vec3& v2 = raw_mesh.vertices[i2];

        Vec3 face = (v1 - v0).cross(v2 - v0);
        float area = face.length();
        if (area <= area_epsilon) {
            continue;
        }

        Vec3 centroid = (v0 + v1 + v2) / 3.0f;
        Vec3 outward = evaluate_field_gradient(metaballs, centroid, epsilon) * -1.0f;
        if (outward.length() > 1e-6f && face.dot(outward) < 0.0f) {
            std::swap(i1, i2);
            face = face * -1.0f;
        }

        mesh.indices.push_back(i0);
        mesh.indices.push_back(i1);
        mesh.indices.push_back(i2);
        mesh.normals[i0] += face;
        mesh.normals[i1] += face;
        mesh.normals[i2] += face;
    }

    for (auto& normal : mesh.normals) {
        float len = normal.length();
        if (len > 1e-6f) {
            normal = normal / len;
        } else {
            normal = Vec3(0.0f, 1.0f, 0.0f);
        }
    }

    return mesh;
}

Mesh generate_creature_mesh(
    const CreatureDescriptor& desc,
    uint32_t grid_resolution,
    float threshold
) {
    Mesh mesh;

    if (desc.metaballs.empty()) return mesh;

    // Compute bounding box of metaballs
    Vec3 min_bound(1e10f, 1e10f, 1e10f);
    Vec3 max_bound(-1e10f, -1e10f, -1e10f);
    float max_radius = 0.0f;

    for (const auto& ball : desc.metaballs) {
        float r = ball.radius * 2.0f;
        min_bound.x = std::min(min_bound.x, ball.center.x - r);
        min_bound.y = std::min(min_bound.y, ball.center.y - r);
        min_bound.z = std::min(min_bound.z, ball.center.z - r);
        max_bound.x = std::max(max_bound.x, ball.center.x + r);
        max_bound.y = std::max(max_bound.y, ball.center.y + r);
        max_bound.z = std::max(max_bound.z, ball.center.z + r);
        max_radius = std::max(max_radius, ball.radius);
    }

    Vec3 padding(max_radius, max_radius, max_radius);
    min_bound = min_bound - padding;
    max_bound = max_bound + padding;

    Vec3 size = max_bound - min_bound;
    float cell_size = std::max({size.x, size.y, size.z}) / static_cast<float>(grid_resolution);

    uint32_t nx = static_cast<uint32_t>(std::ceil(size.x / cell_size)) + 1;
    uint32_t ny = static_cast<uint32_t>(std::ceil(size.y / cell_size)) + 1;
    uint32_t nz = static_cast<uint32_t>(std::ceil(size.z / cell_size)) + 1;

    // Evaluate field at grid points
    std::vector<float> field(nx * ny * nz);
    for (uint32_t iz = 0; iz < nz; ++iz) {
        for (uint32_t iy = 0; iy < ny; ++iy) {
            for (uint32_t ix = 0; ix < nx; ++ix) {
                Vec3 pos = min_bound + Vec3(
                    static_cast<float>(ix) * cell_size,
                    static_cast<float>(iy) * cell_size,
                    static_cast<float>(iz) * cell_size
                );
                size_t idx = ix + iy * nx + iz * nx * ny;
                field[idx] = evaluate_metaball_field(desc.metaballs, pos);
            }
        }
    }

    std::unordered_map<std::string, uint32_t> vertex_cache;

    // March through grid using a consistent tetrahedral decomposition.
    for (uint32_t iz = 0; iz < nz - 1; ++iz) {
        for (uint32_t iy = 0; iy < ny - 1; ++iy) {
            for (uint32_t ix = 0; ix < nx - 1; ++ix) {
                float values[8];
                Vec3 positions[8];

                for (int c = 0; c < 8; ++c) {
                    uint32_t cx = ix + static_cast<uint32_t>(cube_vertices[c][0]);
                    uint32_t cy = iy + static_cast<uint32_t>(cube_vertices[c][1]);
                    uint32_t cz = iz + static_cast<uint32_t>(cube_vertices[c][2]);

                    size_t idx = cx + cy * nx + cz * nx * ny;
                    values[c] = field[idx];
                    positions[c] = min_bound + Vec3(
                        static_cast<float>(cx) * cell_size,
                        static_cast<float>(cy) * cell_size,
                        static_cast<float>(cz) * cell_size
                    );
                }

                for (const auto& tetrahedron : cube_tetrahedra) {
                    Vec3 tetra_positions[4];
                    float tetra_values[4];
                    for (int t = 0; t < 4; ++t) {
                        tetra_positions[t] = positions[tetrahedron[t]];
                        tetra_values[t] = values[tetrahedron[t]];
                    }
                    polygonise_tetrahedron(
                        mesh,
                        vertex_cache,
                        tetra_positions,
                        tetra_values,
                        threshold
                    );
                }
            }
        }
    }

    return finalize_creature_mesh(mesh, desc.metaballs, cell_size);
}

// ============================================================================
// Bush Mesh Generation (Noise-displaced squashed sphere for foliage)
// ============================================================================

Mesh generate_bush_mesh(const BushDescriptor& desc, uint32_t segments, uint32_t rings) {
    Mesh mesh;

    float noise_magnitude = 0.15f * desc.radius;
    // Vertical squash factor — bushes are wider than tall
    float squash_y = 0.55f;

    uint32_t grid_rings = 4;
    uint32_t grid_segments = 6;

    for (uint32_t ring = 0; ring <= rings; ++ring) {
        float phi = PI * static_cast<float>(ring) / static_cast<float>(rings);
        float sin_phi = std::sin(phi);
        float cos_phi = std::cos(phi);

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 normal(sin_phi * cos_theta, cos_phi, sin_phi * sin_theta);

            // Noise for organic foliage shape — more noise at top half
            float n = sphere_noise(desc.noise_seed, phi, theta,
                                   grid_rings, grid_segments);
            float noise_factor = (n * 2.0f - 1.0f) * desc.leaf_density;
            float displaced_radius = desc.radius + noise_factor * noise_magnitude;

            Vec3 vertex = desc.position + Vec3(
                normal.x * displaced_radius,
                normal.y * displaced_radius * squash_y + desc.radius * squash_y * 0.5f,
                normal.z * displaced_radius
            );

            mesh.vertices.push_back(vertex);
            mesh.normals.push_back(normal);
        }
    }

    // Indices (same as sphere)
    for (uint32_t ring = 0; ring < rings; ++ring) {
        for (uint32_t seg = 0; seg < segments; ++seg) {
            uint32_t current = ring * (segments + 1) + seg;
            uint32_t next = current + segments + 1;
            mesh.indices.push_back(current);
            mesh.indices.push_back(next);
            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(next);
            mesh.indices.push_back(next + 1);
        }
    }

    // Recompute normals from displaced geometry
    for (auto& n : mesh.normals) { n = Vec3(0, 0, 0); }
    for (size_t i = 0; i < mesh.indices.size(); i += 3) {
        uint32_t i0 = mesh.indices[i], i1 = mesh.indices[i+1], i2 = mesh.indices[i+2];
        Vec3 edge1 = mesh.vertices[i1] - mesh.vertices[i0];
        Vec3 edge2 = mesh.vertices[i2] - mesh.vertices[i0];
        Vec3 fn = edge1.cross(edge2);
        mesh.normals[i0] += fn;
        mesh.normals[i1] += fn;
        mesh.normals[i2] += fn;
    }
    for (auto& n : mesh.normals) {
        float len = n.length();
        if (len > 1e-6f) n = n / len;
    }

    return mesh;
}

// ============================================================================
// Pine Tree Mesh Generation (Trunk cylinder + stacked cone canopy)
// ============================================================================

Mesh generate_pine_tree_mesh(const PineTreeDescriptor& desc,
                              uint32_t trunk_segments,
                              uint32_t cone_segments) {
    Mesh mesh;

    // 1) Trunk cylinder (vertical, centered at position)
    Mesh trunk = generate_cylinder_mesh(desc.trunk_radius, desc.trunk_height, trunk_segments);
    // Shift trunk so its base sits at position
    for (auto& v : trunk.vertices) {
        v.y += desc.trunk_height * 0.5f;
        v = v + desc.position;
    }
    mesh.append(trunk);

    // 2) Stacked cone canopy layers
    float layer_height = desc.trunk_height * 0.6f / static_cast<float>(desc.canopy_layers);
    float base_y = desc.trunk_height * 0.45f;  // canopy starts slightly below trunk top

    for (uint32_t layer = 0; layer < desc.canopy_layers; ++layer) {
        float t = static_cast<float>(layer) / static_cast<float>(desc.canopy_layers);
        float cone_radius = desc.canopy_radius * (1.0f - t * 0.6f);
        float cone_height = layer_height * (1.2f - t * 0.3f);
        float y_offset = base_y + static_cast<float>(layer) * layer_height * 0.75f;

        Mesh cone = generate_cone_mesh(cone_radius, cone_height, cone_segments);
        // Position cone
        for (auto& v : cone.vertices) {
            v.y += y_offset;
            v = v + desc.position;
        }
        mesh.append(cone);
    }

    return mesh;
}

// ============================================================================
// Dead Tree Mesh Generation (L-system reuse, thinner)
// ============================================================================

Mesh generate_dead_tree_mesh(const DeadTreeDescriptor& desc,
                              uint32_t segments_per_ring) {
    Mesh mesh;

    std::string lstring = evaluate_lsystem(desc.lsystem, desc.iterations);
    // Thinner trunk, more aggressive taper for skeletal look
    auto skeleton = generate_tree_skeleton(lstring, desc.angle, 0.8f, 0.06f, 0.75f);

    for (const auto& seg : skeleton) {
        Mesh cylinder = generate_cylinder(
            seg.start, seg.end,
            seg.start_radius, seg.end_radius,
            segments_per_ring
        );
        mesh.append(cylinder);
    }

    return mesh;
}

// ============================================================================
// Fallen Log Mesh Generation (Horizontal cylinder)
// ============================================================================

Mesh generate_fallen_log_mesh(const FallenLogDescriptor& desc,
                               uint32_t segments) {
    Mesh mesh;

    // Generate cylinder aligned along X (lying on its side)
    Mesh cylinder = generate_cylinder_mesh(desc.radius, desc.length, segments);

    // Rotate 90 degrees around Z so it lies horizontally, then rotate around Y
    float rot_y = desc.rotation_y * DEG_TO_RAD;
    float cos_ry = std::cos(rot_y);
    float sin_ry = std::sin(rot_y);

    for (auto& v : cylinder.vertices) {
        // Swap Y and X to lay the cylinder on its side
        float orig_x = v.x;
        float orig_y = v.y;
        v.x = orig_y;
        v.y = orig_x;  // Low to ground

        // Rotate around Y axis
        float rx = v.x * cos_ry - v.z * sin_ry;
        float rz = v.x * sin_ry + v.z * cos_ry;
        v.x = rx;
        v.z = rz;

        // Translate to position, lift slightly above ground
        v = v + desc.position + Vec3(0, desc.radius, 0);
    }

    // Rotate normals too
    for (auto& n : cylinder.normals) {
        float orig_x = n.x;
        float orig_y = n.y;
        n.x = orig_y;
        n.y = orig_x;
        float rx = n.x * cos_ry - n.z * sin_ry;
        float rz = n.x * sin_ry + n.z * cos_ry;
        n.x = rx;
        n.z = rz;
    }

    mesh.append(cylinder);
    return mesh;
}

// ============================================================================
// Boulder Cluster Mesh Generation (Multiple displaced rocks)
// ============================================================================

Mesh generate_boulder_cluster_mesh(const BoulderClusterDescriptor& desc,
                                    uint32_t segments_per_rock,
                                    uint32_t rings_per_rock) {
    Mesh mesh;

    for (const auto& sub : desc.sub_rocks) {
        RockDescriptor rd;
        rd.position = desc.position + sub.offset;
        rd.radius = sub.radius;
        rd.noise_seed = sub.noise_seed;
        rd.noise_scale = 0.15f;

        Mesh rock = generate_rock_mesh(rd, segments_per_rock, rings_per_rock);
        mesh.append(rock);
    }

    return mesh;
}

// ============================================================================
// Flower Patch Mesh Generation (Cluster of thin stems with bud spheres)
// ============================================================================

Mesh generate_flower_patch_mesh(const FlowerPatchDescriptor& desc,
                                 uint32_t stem_segments) {
    Mesh mesh;

    float stem_height = 0.3f;
    float stem_radius = 0.015f;
    float bud_radius = 0.04f;

    for (uint32_t i = 0; i < desc.stem_count; ++i) {
        // Deterministic position within patch using hash
        float fi = static_cast<float>(i);
        float angle = fi * 2.3998628f;  // Golden angle in radians
        float r = desc.patch_radius * std::sqrt(fi / static_cast<float>(desc.stem_count));
        float sx = std::cos(angle) * r;
        float sz = std::sin(angle) * r;

        // Height varies slightly per stem
        float h = stem_height * (0.7f + noise_hash(desc.color_seed, i, 0) * 0.6f);

        Vec3 stem_base = desc.position + Vec3(sx, 0, sz);

        // Stem cylinder
        Mesh stem = generate_cylinder_mesh(stem_radius, h, stem_segments);
        for (auto& v : stem.vertices) {
            v.y += h * 0.5f;
            v = v + stem_base;
        }
        mesh.append(stem);

        // Small bud sphere at top (8 segments, 6 rings — very small)
        RockDescriptor bud_desc;
        bud_desc.position = stem_base + Vec3(0, h, 0);
        bud_desc.radius = bud_radius;
        bud_desc.noise_seed = desc.color_seed + i;
        bud_desc.noise_scale = 0.05f;
        Mesh bud = generate_rock_mesh(bud_desc, 6, 4);
        mesh.append(bud);
    }

    return mesh;
}

// ============================================================================
// Mushroom Mesh Generation (Stem cylinder + flattened hemisphere cap)
// ============================================================================

Mesh generate_mushroom_mesh(const MushroomDescriptor& desc,
                             uint32_t cap_segments,
                             uint32_t cap_rings,
                             uint32_t stem_segments) {
    Mesh mesh;

    // 1) Stem cylinder
    Mesh stem = generate_cylinder_mesh(desc.stem_radius, desc.stem_height, stem_segments);
    for (auto& v : stem.vertices) {
        v.y += desc.stem_height * 0.5f;
        v = v + desc.position;
    }
    mesh.append(stem);

    // 2) Cap: top hemisphere of a capsule, squashed vertically
    float cap_squash = 0.45f;
    Vec3 cap_center = desc.position + Vec3(0, desc.stem_height, 0);

    for (uint32_t ring = 0; ring <= cap_rings; ++ring) {
        float phi = (PI * 0.5f) * static_cast<float>(ring) / static_cast<float>(cap_rings);
        float sin_phi = std::sin(phi);
        float cos_phi = std::cos(phi);

        for (uint32_t seg = 0; seg <= cap_segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(cap_segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 normal(sin_phi * cos_theta, cos_phi, sin_phi * sin_theta);
            Vec3 pos = cap_center + Vec3(
                normal.x * desc.cap_radius,
                normal.y * desc.cap_radius * cap_squash,
                normal.z * desc.cap_radius
            );

            mesh.vertices.push_back(pos);
            mesh.normals.push_back(normal);
        }
    }

    // Indices for cap hemisphere
    uint32_t cap_base = static_cast<uint32_t>(mesh.vertices.size()) -
                        (cap_rings + 1) * (cap_segments + 1);
    for (uint32_t ring = 0; ring < cap_rings; ++ring) {
        for (uint32_t seg = 0; seg < cap_segments; ++seg) {
            uint32_t current = cap_base + ring * (cap_segments + 1) + seg;
            uint32_t next = current + cap_segments + 1;
            mesh.indices.push_back(current);
            mesh.indices.push_back(next);
            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(next);
            mesh.indices.push_back(next + 1);
        }
    }

    return mesh;
}

// ============================================================================
// Cactus Mesh Generation (Main column cylinder + upward-bending arms)
// ============================================================================

Mesh generate_cactus_mesh(const CactusDescriptor& desc, uint32_t segments) {
    Mesh mesh;

    // 1) Main column
    Mesh main_col = generate_cylinder_mesh(desc.main_radius, desc.main_height, segments);
    for (auto& v : main_col.vertices) {
        v.y += desc.main_height * 0.5f;
        v = v + desc.position;
    }
    mesh.append(main_col);

    // 2) Arms — each arm is a horizontal cylinder + a short vertical tip
    for (const auto& arm : desc.arms) {
        float attach_y = desc.main_height * arm.attach_height;
        float arm_angle_rad = arm.angle * DEG_TO_RAD;
        float cos_a = std::cos(arm_angle_rad);
        float sin_a = std::sin(arm_angle_rad);

        Vec3 arm_start = desc.position + Vec3(
            desc.main_radius * cos_a,
            attach_y,
            desc.main_radius * sin_a
        );

        // Horizontal part of arm
        float arm_radius = desc.main_radius * 0.7f;
        float horiz_len = arm.length * 0.6f;
        Vec3 arm_dir(cos_a, 0, sin_a);
        Vec3 arm_end = arm_start + arm_dir * horiz_len;

        Mesh horiz = generate_cylinder_mesh(arm_radius, horiz_len, segments);
        // Rotate to lie horizontally along arm direction
        for (auto& v : horiz.vertices) {
            float orig_y = v.y;
            v.y = v.x;
            v.x = orig_y;
            // Rotate to arm direction
            float rx = v.x * cos_a - v.z * sin_a;
            float rz = v.x * sin_a + v.z * cos_a;
            v.x = rx;
            v.z = rz;
            // Translate
            Vec3 mid = arm_start + arm_dir * (horiz_len * 0.5f);
            v = v + mid;
        }
        for (auto& n : horiz.normals) {
            float orig_y = n.y;
            n.y = n.x;
            n.x = orig_y;
            float rx = n.x * cos_a - n.z * sin_a;
            float rz = n.x * sin_a + n.z * cos_a;
            n.x = rx;
            n.z = rz;
        }
        mesh.append(horiz);

        // Vertical tip (arm going upward)
        float vert_len = arm.length * 0.4f;
        Mesh tip = generate_cylinder_mesh(arm_radius, vert_len, segments);
        for (auto& v : tip.vertices) {
            v.y += vert_len * 0.5f + attach_y;
            v.x += arm_end.x - desc.position.x;
            v.z += arm_end.z - desc.position.z;
            v = v + desc.position;
        }
        mesh.append(tip);
    }

    return mesh;
}

// ============================================================================
// LOD Generation (Simple vertex clustering)
// ============================================================================

Mesh generate_lod(const Mesh& mesh, float target_ratio) {
    if (mesh.vertices.empty() || target_ratio >= 1.0f) {
        return mesh;
    }

    target_ratio = std::clamp(target_ratio, 0.1f, 1.0f);

    // Compute bounding box
    Vec3 min_bound(1e10f, 1e10f, 1e10f);
    Vec3 max_bound(-1e10f, -1e10f, -1e10f);

    for (const auto& v : mesh.vertices) {
        min_bound.x = std::min(min_bound.x, v.x);
        min_bound.y = std::min(min_bound.y, v.y);
        min_bound.z = std::min(min_bound.z, v.z);
        max_bound.x = std::max(max_bound.x, v.x);
        max_bound.y = std::max(max_bound.y, v.y);
        max_bound.z = std::max(max_bound.z, v.z);
    }

    Vec3 size = max_bound - min_bound;

    // Determine grid resolution based on target ratio
    float grid_scale = std::pow(target_ratio, 1.0f / 3.0f);
    uint32_t grid_res = static_cast<uint32_t>(std::max(2.0f, 32.0f * grid_scale));

    float cell_size_x = size.x / static_cast<float>(grid_res);
    float cell_size_y = size.y / static_cast<float>(grid_res);
    float cell_size_z = size.z / static_cast<float>(grid_res);

    // Map vertices to grid cells
    std::unordered_map<uint64_t, std::vector<uint32_t>> cell_vertices;

    for (uint32_t i = 0; i < mesh.vertices.size(); ++i) {
        const Vec3& v = mesh.vertices[i];
        uint32_t cx = static_cast<uint32_t>((v.x - min_bound.x) / cell_size_x);
        uint32_t cy = static_cast<uint32_t>((v.y - min_bound.y) / cell_size_y);
        uint32_t cz = static_cast<uint32_t>((v.z - min_bound.z) / cell_size_z);

        cx = std::min(cx, grid_res - 1);
        cy = std::min(cy, grid_res - 1);
        cz = std::min(cz, grid_res - 1);

        uint64_t key = (static_cast<uint64_t>(cx) << 40) |
                       (static_cast<uint64_t>(cy) << 20) |
                       static_cast<uint64_t>(cz);
        cell_vertices[key].push_back(i);
    }

    // Create simplified mesh
    Mesh lod;
    std::unordered_map<uint64_t, uint32_t> cell_to_vertex;

    // Average vertices in each cell
    for (const auto& [key, indices] : cell_vertices) {
        Vec3 avg_pos(0, 0, 0);
        Vec3 avg_normal(0, 0, 0);

        for (uint32_t idx : indices) {
            avg_pos += mesh.vertices[idx];
            if (idx < mesh.normals.size()) {
                avg_normal += mesh.normals[idx];
            }
        }

        avg_pos = avg_pos / static_cast<float>(indices.size());
        avg_normal = avg_normal.normalized();
        if (avg_normal.length() < 0.1f) {
            avg_normal = Vec3(0, 1, 0);
        }

        cell_to_vertex[key] = static_cast<uint32_t>(lod.vertices.size());
        lod.vertices.push_back(avg_pos);
        lod.normals.push_back(avg_normal);
    }

    // Remap triangles
    auto get_cell_key = [&](uint32_t idx) -> uint64_t {
        const Vec3& v = mesh.vertices[idx];
        uint32_t cx = static_cast<uint32_t>((v.x - min_bound.x) / cell_size_x);
        uint32_t cy = static_cast<uint32_t>((v.y - min_bound.y) / cell_size_y);
        uint32_t cz = static_cast<uint32_t>((v.z - min_bound.z) / cell_size_z);
        cx = std::min(cx, grid_res - 1);
        cy = std::min(cy, grid_res - 1);
        cz = std::min(cz, grid_res - 1);
        return (static_cast<uint64_t>(cx) << 40) |
               (static_cast<uint64_t>(cy) << 20) |
               static_cast<uint64_t>(cz);
    };

    for (size_t i = 0; i + 2 < mesh.indices.size(); i += 3) {
        uint64_t k0 = get_cell_key(mesh.indices[i]);
        uint64_t k1 = get_cell_key(mesh.indices[i + 1]);
        uint64_t k2 = get_cell_key(mesh.indices[i + 2]);

        // Skip degenerate triangles
        if (k0 == k1 || k1 == k2 || k0 == k2) continue;

        lod.indices.push_back(cell_to_vertex[k0]);
        lod.indices.push_back(cell_to_vertex[k1]);
        lod.indices.push_back(cell_to_vertex[k2]);
    }

    return lod;
}

// ============================================================================
// Primitive Mesh Generation
// ============================================================================

Mesh generate_box_mesh(const Vec3& size, const Vec3& center) {
    Mesh mesh;

    float hx = size.x * 0.5f;
    float hy = size.y * 0.5f;
    float hz = size.z * 0.5f;

    // Define 8 corners of the box
    Vec3 corners[8] = {
        center + Vec3(-hx, -hy, -hz), // 0: left-bottom-back
        center + Vec3( hx, -hy, -hz), // 1: right-bottom-back
        center + Vec3( hx,  hy, -hz), // 2: right-top-back
        center + Vec3(-hx,  hy, -hz), // 3: left-top-back
        center + Vec3(-hx, -hy,  hz), // 4: left-bottom-front
        center + Vec3( hx, -hy,  hz), // 5: right-bottom-front
        center + Vec3( hx,  hy,  hz), // 6: right-top-front
        center + Vec3(-hx,  hy,  hz), // 7: left-top-front
    };

    // Define face normals
    Vec3 normals[6] = {
        Vec3( 0,  0, -1), // Back
        Vec3( 0,  0,  1), // Front
        Vec3(-1,  0,  0), // Left
        Vec3( 1,  0,  0), // Right
        Vec3( 0, -1,  0), // Bottom
        Vec3( 0,  1,  0), // Top
    };

    // Define faces (4 vertices per face, 2 triangles)
    uint32_t faces[6][4] = {
        {0, 1, 2, 3}, // Back
        {4, 7, 6, 5}, // Front
        {0, 3, 7, 4}, // Left
        {1, 5, 6, 2}, // Right
        {0, 4, 5, 1}, // Bottom
        {3, 2, 6, 7}, // Top
    };

    // Generate vertices and indices
    for (uint32_t f = 0; f < 6; ++f) {
        uint32_t base_idx = static_cast<uint32_t>(mesh.vertices.size());

        // Add 4 vertices for this face
        for (uint32_t i = 0; i < 4; ++i) {
            mesh.vertices.push_back(corners[faces[f][i]]);
            mesh.normals.push_back(normals[f]);
        }

        // Add 2 triangles (6 indices)
        mesh.indices.push_back(base_idx + 0);
        mesh.indices.push_back(base_idx + 1);
        mesh.indices.push_back(base_idx + 2);

        mesh.indices.push_back(base_idx + 0);
        mesh.indices.push_back(base_idx + 2);
        mesh.indices.push_back(base_idx + 3);
    }

    return mesh;
}

Mesh generate_capsule_mesh(float radius, float height, uint32_t segments, uint32_t rings) {
    Mesh mesh;

    float half_height = height * 0.5f;

    // Generate top hemisphere
    for (uint32_t ring = 0; ring <= rings; ++ring) {
        float phi = (PI * 0.5f) * static_cast<float>(ring) / static_cast<float>(rings);
        float sin_phi = std::sin(phi);
        float cos_phi = std::cos(phi);
        float y = half_height + radius * cos_phi;
        float ring_radius = radius * sin_phi;

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 position(ring_radius * cos_theta, y, ring_radius * sin_theta);
            Vec3 normal = Vec3(sin_phi * cos_theta, cos_phi, sin_phi * sin_theta);

            mesh.vertices.push_back(position);
            mesh.normals.push_back(normal);
        }
    }

    // Generate cylindrical section
    for (uint32_t i = 0; i <= 1; ++i) {
        float y = (i == 0) ? half_height : -half_height;

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 position(radius * cos_theta, y, radius * sin_theta);
            Vec3 normal(cos_theta, 0.0f, sin_theta);

            mesh.vertices.push_back(position);
            mesh.normals.push_back(normal);
        }
    }

    // Generate bottom hemisphere
    // phi goes from 0 (equator at y=-half_height) to pi/2 (south pole at y=-half_height-radius)
    // Using sin(phi) for Y offset: at phi=0, y=-half_height (equator); at phi=pi/2, y=-half_height-radius (pole)
    // Using cos(phi) for radius: at phi=0, full radius (equator); at phi=pi/2, zero radius (pole point)
    for (uint32_t ring = 0; ring <= rings; ++ring) {
        // phi goes from 0 (equator, y=-half_height) to pi/2 (pole, y=-half_height-radius)
        float phi = (PI * 0.5f) * static_cast<float>(ring) / static_cast<float>(rings);
        float sin_phi = std::sin(phi);
        float cos_phi = std::cos(phi);
        // For bottom hemisphere: y goes down from -half_height
        float y = -half_height - radius * sin_phi;  // sin so ring=0 is at -half_height
        float ring_radius = radius * cos_phi;  // cos so ring=0 has full radius

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 position(ring_radius * cos_theta, y, ring_radius * sin_theta);
            // Normal points outward and downward
            Vec3 normal = Vec3(cos_phi * cos_theta, -sin_phi, cos_phi * sin_theta);

            mesh.vertices.push_back(position);
            mesh.normals.push_back(normal);
        }
    }

    // Generate indices for top hemisphere
    for (uint32_t ring = 0; ring < rings; ++ring) {
        for (uint32_t seg = 0; seg < segments; ++seg) {
            uint32_t current = ring * (segments + 1) + seg;
            uint32_t next = current + segments + 1;

            mesh.indices.push_back(current);
            mesh.indices.push_back(next);
            mesh.indices.push_back(current + 1);

            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(next);
            mesh.indices.push_back(next + 1);
        }
    }

    // Generate indices for cylindrical section
    uint32_t cyl_start = (rings + 1) * (segments + 1);
    for (uint32_t seg = 0; seg < segments; ++seg) {
        uint32_t current = cyl_start + seg;
        uint32_t next = current + segments + 1;

        mesh.indices.push_back(current);
        mesh.indices.push_back(next);
        mesh.indices.push_back(current + 1);

        mesh.indices.push_back(current + 1);
        mesh.indices.push_back(next);
        mesh.indices.push_back(next + 1);
    }

    // Generate indices for bottom hemisphere
    // Now bottom hemisphere has rings+1 rows of vertices (ring 0 to rings), so we connect rings pairs
    uint32_t bottom_start = cyl_start + 2 * (segments + 1);
    for (uint32_t ring = 0; ring < rings; ++ring) {
        for (uint32_t seg = 0; seg < segments; ++seg) {
            uint32_t current = bottom_start + ring * (segments + 1) + seg;
            uint32_t next = current + segments + 1;

            mesh.indices.push_back(current);
            mesh.indices.push_back(next);
            mesh.indices.push_back(current + 1);

            mesh.indices.push_back(current + 1);
            mesh.indices.push_back(next);
            mesh.indices.push_back(next + 1);
        }
    }

    return mesh;
}

Mesh generate_cylinder_mesh(float radius, float height, uint32_t segments) {
    Mesh mesh;

    float half_height = height * 0.5f;

    // Generate side vertices
    for (uint32_t i = 0; i <= 1; ++i) {
        float y = (i == 0) ? half_height : -half_height;

        for (uint32_t seg = 0; seg <= segments; ++seg) {
            float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
            float sin_theta = std::sin(theta);
            float cos_theta = std::cos(theta);

            Vec3 position(radius * cos_theta, y, radius * sin_theta);
            Vec3 normal(cos_theta, 0.0f, sin_theta);

            mesh.vertices.push_back(position);
            mesh.normals.push_back(normal);
        }
    }

    // Generate side indices
    for (uint32_t seg = 0; seg < segments; ++seg) {
        uint32_t current = seg;
        uint32_t next = current + segments + 1;

        mesh.indices.push_back(current);
        mesh.indices.push_back(next);
        mesh.indices.push_back(current + 1);

        mesh.indices.push_back(current + 1);
        mesh.indices.push_back(next);
        mesh.indices.push_back(next + 1);
    }

    // Generate top cap
    uint32_t top_center_idx = static_cast<uint32_t>(mesh.vertices.size());
    mesh.vertices.push_back(Vec3(0.0f, half_height, 0.0f));
    mesh.normals.push_back(Vec3(0.0f, 1.0f, 0.0f));

    for (uint32_t seg = 0; seg < segments; ++seg) {
        mesh.indices.push_back(top_center_idx);
        mesh.indices.push_back(seg);
        mesh.indices.push_back(seg + 1);
    }

    // Generate bottom cap
    uint32_t bottom_center_idx = static_cast<uint32_t>(mesh.vertices.size());
    mesh.vertices.push_back(Vec3(0.0f, -half_height, 0.0f));
    mesh.normals.push_back(Vec3(0.0f, -1.0f, 0.0f));

    uint32_t bottom_ring_start = segments + 1;
    for (uint32_t seg = 0; seg < segments; ++seg) {
        mesh.indices.push_back(bottom_center_idx);
        mesh.indices.push_back(bottom_ring_start + seg + 1);
        mesh.indices.push_back(bottom_ring_start + seg);
    }

    return mesh;
}

Mesh generate_cone_mesh(float radius, float height, uint32_t segments) {
    Mesh mesh;

    // Generate base vertices
    for (uint32_t seg = 0; seg <= segments; ++seg) {
        float theta = 2.0f * PI * static_cast<float>(seg) / static_cast<float>(segments);
        float sin_theta = std::sin(theta);
        float cos_theta = std::cos(theta);

        Vec3 position(radius * cos_theta, 0.0f, radius * sin_theta);
        
        // Side normal points outward and upward
        Vec3 tangent(-sin_theta, 0.0f, cos_theta);
        Vec3 up(0.0f, 1.0f, 0.0f);
        Vec3 radial(cos_theta, 0.0f, sin_theta);
        float slant = std::atan2(radius, height);
        Vec3 normal = (radial * std::cos(slant) + up * std::sin(slant)).normalized();

        mesh.vertices.push_back(position);
        mesh.normals.push_back(normal);
    }

    // Apex vertex
    uint32_t apex_idx = static_cast<uint32_t>(mesh.vertices.size());
    mesh.vertices.push_back(Vec3(0.0f, height, 0.0f));
    mesh.normals.push_back(Vec3(0.0f, 1.0f, 0.0f));

    // Generate side triangles
    for (uint32_t seg = 0; seg < segments; ++seg) {
        mesh.indices.push_back(seg);
        mesh.indices.push_back(apex_idx);
        mesh.indices.push_back(seg + 1);
    }

    // Generate base cap (center point)
    uint32_t base_center_idx = static_cast<uint32_t>(mesh.vertices.size());
    mesh.vertices.push_back(Vec3(0.0f, 0.0f, 0.0f));
    mesh.normals.push_back(Vec3(0.0f, -1.0f, 0.0f));

    for (uint32_t seg = 0; seg < segments; ++seg) {
        mesh.indices.push_back(base_center_idx);
        mesh.indices.push_back(seg + 1);
        mesh.indices.push_back(seg);
    }

    return mesh;
}

Mesh generate_plane_mesh(const Vec3& size, uint32_t subdivisions) {
    Mesh mesh;

    float hx = size.x * 0.5f;
    float hz = size.z * 0.5f;
    uint32_t verts_per_axis = subdivisions + 2;

    // Generate vertices
    for (uint32_t z = 0; z < verts_per_axis; ++z) {
        for (uint32_t x = 0; x < verts_per_axis; ++x) {
            float fx = -hx + (size.x * static_cast<float>(x)) / static_cast<float>(verts_per_axis - 1);
            float fz = -hz + (size.z * static_cast<float>(z)) / static_cast<float>(verts_per_axis - 1);

            mesh.vertices.push_back(Vec3(fx, 0.0f, fz));
            mesh.normals.push_back(Vec3(0.0f, 1.0f, 0.0f));
        }
    }

    // Generate indices
    for (uint32_t z = 0; z < verts_per_axis - 1; ++z) {
        for (uint32_t x = 0; x < verts_per_axis - 1; ++x) {
            uint32_t tl = z * verts_per_axis + x;
            uint32_t tr = tl + 1;
            uint32_t bl = (z + 1) * verts_per_axis + x;
            uint32_t br = bl + 1;

            mesh.indices.push_back(tl);
            mesh.indices.push_back(bl);
            mesh.indices.push_back(tr);

            mesh.indices.push_back(tr);
            mesh.indices.push_back(bl);
            mesh.indices.push_back(br);
        }
    }

    return mesh;
}

} // namespace props
