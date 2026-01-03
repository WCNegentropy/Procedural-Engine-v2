#include "physics.h"
#include <algorithm>
#include <cmath>

namespace physics {

// Hash function for grid cell coordinates
struct CellHash {
    size_t operator()(const std::pair<int, int>& cell) const {
        // Simple hash combining
        return std::hash<int>()(cell.first) ^ (std::hash<int>()(cell.second) << 1);
    }
};

std::vector<std::pair<size_t, size_t>> broad_phase_pairs(
    const std::vector<RigidBody>& bodies, float cell_size) {

    if (bodies.empty() || cell_size <= 0.0f) {
        return {};
    }

    // Build spatial grid
    std::unordered_map<std::pair<int, int>, std::vector<size_t>, CellHash> grid;

    for (size_t idx = 0; idx < bodies.size(); ++idx) {
        const auto& body = bodies[idx];
        int cx = static_cast<int>(std::floor(body.position.x / cell_size));
        int cy = static_cast<int>(std::floor(body.position.y / cell_size));
        grid[{cx, cy}].push_back(idx);
    }

    // Collect potential pairs
    std::set<std::pair<size_t, size_t>> pairs_set;

    // Sorted iteration over grid cells for determinism
    std::vector<std::pair<int, int>> sorted_cells;
    for (const auto& [cell, indices] : grid) {
        sorted_cells.push_back(cell);
    }
    std::sort(sorted_cells.begin(), sorted_cells.end());

    static const int neighbors[9][2] = {
        {-1, -1}, {-1, 0}, {-1, 1},
        { 0, -1}, { 0, 0}, { 0, 1},
        { 1, -1}, { 1, 0}, { 1, 1}
    };

    for (const auto& cell : sorted_cells) {
        auto& indices = grid[cell];
        std::sort(indices.begin(), indices.end());

        // Pairs within the same cell
        for (size_t i = 0; i < indices.size(); ++i) {
            for (size_t j = i + 1; j < indices.size(); ++j) {
                pairs_set.insert({indices[i], indices[j]});
            }
        }

        // Pairs with neighboring cells
        for (const auto& offset : neighbors) {
            if (offset[0] == 0 && offset[1] == 0) continue;

            auto neigh = std::make_pair(cell.first + offset[0], cell.second + offset[1]);
            auto it = grid.find(neigh);
            if (it == grid.end()) continue;

            for (size_t i : indices) {
                for (size_t j : it->second) {
                    if (i < j) {
                        pairs_set.insert({i, j});
                    } else if (j < i) {
                        pairs_set.insert({j, i});
                    }
                }
            }
        }
    }

    // Convert to sorted vector
    std::vector<std::pair<size_t, size_t>> result(pairs_set.begin(), pairs_set.end());
    std::sort(result.begin(), result.end());
    return result;
}

void step_physics(std::vector<RigidBody>& bodies,
                  const PhysicsConfig& config,
                  const HeightField* heightfield) {

    if (bodies.empty()) return;

    float dt = config.dt;
    uint32_t iterations = config.iterations;
    float restitution = config.restitution;
    float cell_size = config.cell_size;
    float gravity = config.gravity;
    float damping = config.damping;

    // Validate parameters
    if (dt <= 0.0f) return;
    if (iterations < 1) iterations = 1;

    // Apply gravity, damping, and integrate positions
    float damp_factor = std::max(0.0f, 1.0f - damping * dt);

    for (auto& body : bodies) {
        // Apply gravity (negative Y direction)
        if (gravity != 0.0f) {
            body.velocity.y += gravity * dt;
        }

        // Apply damping
        if (damping != 0.0f) {
            body.velocity *= damp_factor;
        }

        // Integrate position
        body.position += body.velocity * dt;
    }

    // Compute inverse masses
    std::vector<float> inv_masses(bodies.size());
    for (size_t i = 0; i < bodies.size(); ++i) {
        inv_masses[i] = bodies[i].inv_mass();
    }

    // Determine cell size if not specified
    if (cell_size <= 0.0f) {
        float max_radius = 0.0f;
        for (const auto& body : bodies) {
            max_radius = std::max(max_radius, body.radius);
        }
        cell_size = (max_radius > 0.0f) ? max_radius * 2.0f : 1.0f;
    }

    // Get collision pairs from broad phase
    auto pairs = broad_phase_pairs(bodies, cell_size);

    // Sequential impulse solver (Gauss-Seidel iterations)
    for (uint32_t iter = 0; iter < iterations; ++iter) {
        for (const auto& [i, j] : pairs) {
            RigidBody& a = bodies[i];
            RigidBody& b = bodies[j];

            // Compute separation vector
            Vec2 delta = b.position - a.position;
            float dist = delta.length();
            float min_dist = a.radius + b.radius;

            // Skip if not colliding or coincident
            if (dist >= min_dist || dist == 0.0f) continue;

            // Collision normal (from a to b)
            Vec2 n = delta * (1.0f / dist);

            // Relative velocity along normal
            Vec2 rel_vel = b.velocity - a.velocity;
            float rel_vel_n = rel_vel.dot(n);

            // Skip if separating
            if (rel_vel_n > 0.0f) continue;

            // Compute impulse magnitude
            float j_impulse = -(1.0f + restitution) * rel_vel_n;
            j_impulse /= (inv_masses[i] + inv_masses[j]);

            // Apply impulse
            Vec2 impulse = n * j_impulse;
            a.velocity -= impulse * inv_masses[i];
            b.velocity += impulse * inv_masses[j];
        }
    }

    // HeightField collision
    if (heightfield != nullptr && !heightfield->empty()) {
        for (auto& body : bodies) {
            float ground = heightfield->sample(body.position.x) + body.radius;

            if (body.position.y < ground) {
                body.position.y = ground;

                if (body.velocity.y < 0.0f) {
                    body.velocity.y = -body.velocity.y * restitution;
                }
            }
        }
    }
}

// PhysicsWorld implementation

size_t PhysicsWorld::add_body(const RigidBody& body) {
    bodies_.push_back(body);
    return bodies_.size() - 1;
}

RigidBody& PhysicsWorld::get_body(size_t index) {
    return bodies_.at(index);
}

const RigidBody& PhysicsWorld::get_body(size_t index) const {
    return bodies_.at(index);
}

void PhysicsWorld::step(const PhysicsConfig& config) {
    const HeightField* hf = heightfield_.empty() ? nullptr : &heightfield_;
    step_physics(bodies_, config, hf);
}

void PhysicsWorld::reset() {
    bodies_.clear();
    heightfield_ = HeightField();
}

// =============================================================================
// 3D Physics Implementation
// =============================================================================

void step_physics_3d(std::vector<RigidBody3D>& bodies,
                     const PhysicsConfig3D& config,
                     const HeightField2D* heightfield) {

    if (bodies.empty()) return;

    float dt = config.dt;
    uint32_t iterations = config.iterations;
    float restitution = config.restitution;
    float cell_size = config.cell_size;
    float gravity = config.gravity;
    float damping = config.damping;

    // Validate parameters
    if (dt <= 0.0f) return;
    if (iterations < 1) iterations = 1;

    // Phase 1: Y-axis gravity and terrain collision
    float damp_factor = std::max(0.0f, 1.0f - damping * dt);

    for (auto& body : bodies) {
        // Apply gravity to Y velocity
        body.velocity.y += gravity * dt;

        // Apply damping to all velocity components
        if (damping != 0.0f) {
            body.velocity *= damp_factor;
        }

        // Integrate Y position
        body.position.y += body.velocity.y * dt;

        // Terrain collision (Y axis)
        body.grounded = false;
        if (heightfield != nullptr && !heightfield->empty()) {
            float ground = heightfield->sample(body.position.x, body.position.z) + body.radius;

            if (body.position.y < ground) {
                body.position.y = ground;

                if (body.velocity.y < 0.0f) {
                    body.velocity.y = -body.velocity.y * restitution;
                }
                body.grounded = true;
            }
        }
    }

    // Phase 2: XZ plane collision using existing 2D solver
    // Project all bodies to 2D on XZ plane
    std::vector<RigidBody> bodies_2d;
    bodies_2d.reserve(bodies.size());
    for (const auto& body : bodies) {
        bodies_2d.push_back(body.to_2d());
    }

    // Create 2D physics config (no gravity/damping - already handled)
    PhysicsConfig config_2d;
    config_2d.dt = dt;
    config_2d.iterations = iterations;
    config_2d.restitution = restitution;
    config_2d.cell_size = cell_size;
    config_2d.gravity = 0.0f;    // Already handled in phase 1
    config_2d.damping = 0.0f;    // Already handled in phase 1

    // Run 2D physics step
    step_physics(bodies_2d, config_2d, nullptr);

    // Apply 2D results back to 3D bodies
    for (size_t i = 0; i < bodies.size(); ++i) {
        bodies[i].apply_2d_result(bodies_2d[i]);
    }
}

} // namespace physics
