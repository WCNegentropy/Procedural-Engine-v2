#pragma once

#include <cstdint>
#include <vector>
#include <array>
#include <cmath>
#include <utility>
#include <unordered_map>
#include <set>

/**
 * Deterministic physics solver utilities.
 *
 * This module provides C++ implementations of a 2D sequential impulse physics
 * solver matching the Python reference in physics.py. The solver handles:
 * - Circular rigid body collisions
 * - HeightField terrain collision
 * - Uniform spatial grid broad-phase
 * - Gravity and linear damping
 *
 * All operations are fully deterministic for reproducible simulations.
 */

namespace physics {

// Default timestep: 60 Hz
static constexpr float DEFAULT_DT = 1.0f / 60.0f;

/**
 * 2D vector for physics calculations.
 */
struct Vec2 {
    float x = 0.0f;
    float y = 0.0f;

    Vec2() = default;
    Vec2(float x_, float y_) : x(x_), y(y_) {}

    Vec2 operator+(const Vec2& other) const { return Vec2(x + other.x, y + other.y); }
    Vec2 operator-(const Vec2& other) const { return Vec2(x - other.x, y - other.y); }
    Vec2 operator*(float scalar) const { return Vec2(x * scalar, y * scalar); }
    Vec2& operator+=(const Vec2& other) { x += other.x; y += other.y; return *this; }
    Vec2& operator-=(const Vec2& other) { x -= other.x; y -= other.y; return *this; }
    Vec2& operator*=(float scalar) { x *= scalar; y *= scalar; return *this; }

    float dot(const Vec2& other) const { return x * other.x + y * other.y; }
    float length() const { return std::sqrt(x * x + y * y); }
    float length_squared() const { return x * x + y * y; }

    Vec2 normalized() const {
        float len = length();
        if (len > 0.0f) return Vec2(x / len, y / len);
        return Vec2(0.0f, 0.0f);
    }
};

/**
 * Minimal rigid body representation for 2D collisions.
 *
 * Uses circular collision shapes for simplicity and determinism.
 */
struct RigidBody {
    Vec2 position;      // 2D position
    Vec2 velocity;      // 2D velocity
    float mass;         // Must be positive
    float radius;       // Collision radius

    RigidBody() : mass(1.0f), radius(1.0f) {}
    RigidBody(Vec2 pos, Vec2 vel, float m, float r)
        : position(pos), velocity(vel), mass(m), radius(r) {}

    float inv_mass() const { return 1.0f / mass; }
};

/**
 * Simple 1D heightfield collision proxy.
 *
 * Samples are spaced evenly along the X axis and represent the minimum
 * allowed Y coordinate. Bodies are kept above the sampled height plus
 * their radius.
 */
class HeightField {
public:
    HeightField() : x0_(0.0f), cell_size_(1.0f) {}

    HeightField(const std::vector<float>& heights, float x0 = 0.0f, float cell_size = 1.0f)
        : heights_(heights), x0_(x0), cell_size_(cell_size) {}

    /**
     * Sample height at horizontal coordinate x with linear interpolation.
     * Returns interpolated height for smoother boundary handling.
     */
    float sample(float x) const {
        if (heights_.empty()) return 0.0f;

        float local_x = (x - x0_) / cell_size_;
        int idx0 = static_cast<int>(std::floor(local_x));
        int idx1 = idx0 + 1;

        // Clamp indices
        idx0 = std::max(0, std::min(idx0, static_cast<int>(heights_.size()) - 1));
        idx1 = std::max(0, std::min(idx1, static_cast<int>(heights_.size()) - 1));

        // Linear interpolation between samples for smoother transitions
        float t = local_x - std::floor(local_x);
        t = std::max(0.0f, std::min(t, 1.0f));

        return heights_[idx0] * (1.0f - t) + heights_[idx1] * t;
    }

    /**
     * Check if coordinate x is within the heightfield bounds.
     */
    bool in_bounds(float x) const {
        if (heights_.empty()) return false;
        float x_max = x0_ + cell_size_ * static_cast<float>(heights_.size() - 1);
        return x >= x0_ && x <= x_max;
    }

    /**
     * Get the X coordinate range of the heightfield.
     */
    float x_min() const { return x0_; }
    float x_max() const {
        if (heights_.empty()) return x0_;
        return x0_ + cell_size_ * static_cast<float>(heights_.size() - 1);
    }

    bool empty() const { return heights_.empty(); }

private:
    std::vector<float> heights_;
    float x0_;
    float cell_size_;
};

/**
 * Configuration for physics simulation step.
 */
struct PhysicsConfig {
    float dt = DEFAULT_DT;          // Time step in seconds
    uint32_t iterations = 10;       // Gauss-Seidel iterations
    float restitution = 1.0f;       // Coefficient of restitution
    float cell_size = 0.0f;         // Broad-phase cell size (0 = auto)
    float gravity = 0.0f;           // Gravity acceleration (negative Y)
    float damping = 0.0f;           // Linear velocity damping per second
};

/**
 * Generate potential collision pairs using uniform spatial grid.
 *
 * The grid ensures only bodies within the same or neighboring cells are
 * considered for collision resolution. Cell size should be at least twice
 * the maximum body radius to guarantee no collisions are missed.
 *
 * @param bodies List of rigid bodies
 * @param cell_size Size of grid cells
 * @return Sorted vector of (i, j) pairs where i < j
 */
std::vector<std::pair<size_t, size_t>> broad_phase_pairs(
    const std::vector<RigidBody>& bodies, float cell_size);

/**
 * Advance physics simulation by one timestep.
 *
 * Uses a sequential impulse solver with Gauss-Seidel iterations over
 * potential collision pairs from a deterministic uniform grid broad-phase.
 * Circular body collisions are resolved with impulses. An optional HeightField
 * keeps bodies above terrain.
 *
 * The routine operates in-place and produces deterministic results given
 * the same initial body states.
 *
 * @param bodies Mutable vector of rigid bodies (modified in-place)
 * @param config Physics simulation configuration
 * @param heightfield Optional heightfield for terrain collision
 */
void step_physics(std::vector<RigidBody>& bodies,
                  const PhysicsConfig& config = {},
                  const HeightField* heightfield = nullptr);

/**
 * Physics world container for managing simulation state.
 */
class PhysicsWorld {
public:
    PhysicsWorld() = default;

    /**
     * Add a rigid body to the simulation.
     * @return Index of the added body
     */
    size_t add_body(const RigidBody& body);

    /**
     * Get a body by index.
     */
    RigidBody& get_body(size_t index);
    const RigidBody& get_body(size_t index) const;

    /**
     * Get all bodies.
     */
    std::vector<RigidBody>& bodies() { return bodies_; }
    const std::vector<RigidBody>& bodies() const { return bodies_; }

    /**
     * Set the heightfield for terrain collision.
     */
    void set_heightfield(const HeightField& hf) { heightfield_ = hf; }

    /**
     * Clear the heightfield.
     */
    void clear_heightfield() { heightfield_ = HeightField(); }

    /**
     * Step the simulation forward.
     */
    void step(const PhysicsConfig& config = {});

    /**
     * Reset to initial state (clear all bodies).
     */
    void reset();

    /**
     * Get body count.
     */
    size_t body_count() const { return bodies_.size(); }

private:
    std::vector<RigidBody> bodies_;
    HeightField heightfield_;
};

} // namespace physics
