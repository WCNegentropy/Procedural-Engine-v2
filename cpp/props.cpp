#include "props.h"
#include <cmath>
#include <algorithm>
#include <stack>

namespace props {

// Constants
static constexpr float PI = 3.14159265358979323846f;
static constexpr float DEG_TO_RAD = PI / 180.0f;

// ============================================================================
// Rock Mesh Generation (UV Sphere)
// ============================================================================

Mesh generate_rock_mesh(const RockDescriptor& desc, uint32_t segments, uint32_t rings) {
    Mesh mesh;

    // Generate UV sphere vertices
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

            // Position (scaled and translated)
            Vec3 vertex = desc.position + normal * desc.radius;

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

    return mesh;
}

// ============================================================================
// Tree Mesh Generation (L-System + Sweep Mesh)
// ============================================================================

std::string evaluate_lsystem(const LSystemRules& rules, uint32_t iterations) {
    std::string current = rules.axiom;

    for (uint32_t iter = 0; iter < iterations; ++iter) {
        std::string next;
        next.reserve(current.size() * 4);  // Estimate growth

        for (char c : current) {
            auto it = rules.rules.find(c);
            if (it != rules.rules.end()) {
                next += it->second;
            } else {
                next += c;
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

// Marching cubes edge table (simplified - 256 entries)
// This is a minimal implementation for the procedural engine

// Edge vertices for each of the 12 edges of a cube
static const int edge_vertices[12][2] = {
    {0, 1}, {1, 2}, {2, 3}, {3, 0},
    {4, 5}, {5, 6}, {6, 7}, {7, 4},
    {0, 4}, {1, 5}, {2, 6}, {3, 7}
};

// Vertex positions for cube corners
static const float cube_vertices[8][3] = {
    {0, 0, 0}, {1, 0, 0}, {1, 1, 0}, {0, 1, 0},
    {0, 0, 1}, {1, 0, 1}, {1, 1, 1}, {0, 1, 1}
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

    for (const auto& ball : desc.metaballs) {
        float r = ball.radius * 2.0f;  // Extend by radius
        min_bound.x = std::min(min_bound.x, ball.center.x - r);
        min_bound.y = std::min(min_bound.y, ball.center.y - r);
        min_bound.z = std::min(min_bound.z, ball.center.z - r);
        max_bound.x = std::max(max_bound.x, ball.center.x + r);
        max_bound.y = std::max(max_bound.y, ball.center.y + r);
        max_bound.z = std::max(max_bound.z, ball.center.z + r);
    }

    // Add some padding
    Vec3 padding(0.2f, 0.2f, 0.2f);
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

    // March through grid (simplified marching cubes)
    for (uint32_t iz = 0; iz < nz - 1; ++iz) {
        for (uint32_t iy = 0; iy < ny - 1; ++iy) {
            for (uint32_t ix = 0; ix < nx - 1; ++ix) {
                // Get field values at cube corners
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

                // Compute cube index
                int cube_index = 0;
                for (int c = 0; c < 8; ++c) {
                    if (values[c] >= threshold) {
                        cube_index |= (1 << c);
                    }
                }

                // Skip if entirely inside or outside
                if (cube_index == 0 || cube_index == 255) continue;

                // Find edge intersections
                Vec3 edge_verts[12];
                bool edge_used[12] = {false};

                for (int e = 0; e < 12; ++e) {
                    int v1 = edge_vertices[e][0];
                    int v2 = edge_vertices[e][1];

                    bool in1 = (values[v1] >= threshold);
                    bool in2 = (values[v2] >= threshold);

                    if (in1 != in2) {
                        edge_verts[e] = interpolate_edge(
                            positions[v1], positions[v2],
                            values[v1], values[v2], threshold
                        );
                        edge_used[e] = true;
                    }
                }

                // Generate triangles (simplified - just connect used edges)
                // This is a basic approach; full marching cubes uses lookup tables
                std::vector<int> used_edges;
                for (int e = 0; e < 12; ++e) {
                    if (edge_used[e]) {
                        used_edges.push_back(e);
                    }
                }

                // Create triangles from edge vertices (fan triangulation)
                if (used_edges.size() >= 3) {
                    uint32_t base = static_cast<uint32_t>(mesh.vertices.size());

                    for (int e : used_edges) {
                        mesh.vertices.push_back(edge_verts[e]);
                    }

                    // Compute normals using gradient of field
                    for (const auto& v : mesh.vertices) {
                        float eps = cell_size * 0.1f;
                        float fx = evaluate_metaball_field(desc.metaballs, v + Vec3(eps, 0, 0))
                                 - evaluate_metaball_field(desc.metaballs, v - Vec3(eps, 0, 0));
                        float fy = evaluate_metaball_field(desc.metaballs, v + Vec3(0, eps, 0))
                                 - evaluate_metaball_field(desc.metaballs, v - Vec3(0, eps, 0));
                        float fz = evaluate_metaball_field(desc.metaballs, v + Vec3(0, 0, eps))
                                 - evaluate_metaball_field(desc.metaballs, v - Vec3(0, 0, eps));
                        mesh.normals.push_back(Vec3(-fx, -fy, -fz).normalized());
                    }

                    // Fan triangulation
                    for (size_t i = 1; i + 1 < used_edges.size(); ++i) {
                        mesh.indices.push_back(base);
                        mesh.indices.push_back(base + static_cast<uint32_t>(i));
                        mesh.indices.push_back(base + static_cast<uint32_t>(i + 1));
                    }
                }
            }
        }
    }

    // Fix normals count if needed
    while (mesh.normals.size() < mesh.vertices.size()) {
        mesh.normals.push_back(Vec3(0, 1, 0));
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

} // namespace props
