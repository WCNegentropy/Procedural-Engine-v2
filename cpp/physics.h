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

// =============================================================================
// 3D Physics (Hybrid 2D+Height approach)
// =============================================================================

/**
 * 3D vector for physics calculations.
 *
 * Provides full operator overloads and common vector operations.
 * Used for 3D position/velocity in the hybrid physics system.
 */
struct Vec3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;

    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& other) const {
        return Vec3(x + other.x, y + other.y, z + other.z);
    }
    Vec3 operator-(const Vec3& other) const {
        return Vec3(x - other.x, y - other.y, z - other.z);
    }
    Vec3 operator*(float scalar) const {
        return Vec3(x * scalar, y * scalar, z * scalar);
    }
    Vec3 operator/(float scalar) const {
        return Vec3(x / scalar, y / scalar, z / scalar);
    }
    Vec3 operator-() const {
        return Vec3(-x, -y, -z);
    }
    Vec3& operator+=(const Vec3& other) {
        x += other.x; y += other.y; z += other.z;
        return *this;
    }
    Vec3& operator-=(const Vec3& other) {
        x -= other.x; y -= other.y; z -= other.z;
        return *this;
    }
    Vec3& operator*=(float scalar) {
        x *= scalar; y *= scalar; z *= scalar;
        return *this;
    }
    bool operator==(const Vec3& other) const {
        return x == other.x && y == other.y && z == other.z;
    }

    float dot(const Vec3& other) const {
        return x * other.x + y * other.y + z * other.z;
    }

    Vec3 cross(const Vec3& other) const {
        return Vec3(
            y * other.z - z * other.y,
            z * other.x - x * other.z,
            x * other.y - y * other.x
        );
    }

    float length() const {
        return std::sqrt(x * x + y * y + z * z);
    }

    float length_squared() const {
        return x * x + y * y + z * z;
    }

    Vec3 normalized() const {
        float len = length();
        if (len > 0.0f) return Vec3(x / len, y / len, z / len);
        return Vec3(0.0f, 0.0f, 0.0f);
    }

    /**
     * Project to XZ plane as Vec2 for 2D physics.
     */
    Vec2 xz() const {
        return Vec2(x, z);
    }

    /**
     * Create Vec3 from XZ Vec2 with specified Y.
     */
    static Vec3 from_xz(const Vec2& v, float y = 0.0f) {
        return Vec3(v.x, y, v.y);
    }
};

/**
 * 3D rigid body for hybrid 2D+height physics.
 *
 * Uses the XZ plane for 2D collision resolution and Y for gravity/terrain.
 * The body is represented as a sphere with the given radius.
 */
struct RigidBody3D {
    Vec3 position;      // 3D position (Y is up)
    Vec3 velocity;      // 3D velocity
    float mass;         // Must be positive
    float radius;       // Collision radius (spherical)
    bool grounded;      // Whether on ground

    RigidBody3D()
        : position(), velocity(), mass(1.0f), radius(1.0f), grounded(false) {}

    RigidBody3D(Vec3 pos, Vec3 vel, float m, float r)
        : position(pos), velocity(vel), mass(m), radius(r), grounded(false) {}

    float inv_mass() const { return 1.0f / mass; }

    /**
     * Project to 2D RigidBody on XZ plane for collision.
     */
    RigidBody to_2d() const {
        return RigidBody(position.xz(), velocity.xz(), mass, radius);
    }

    /**
     * Apply 2D collision results back to 3D body.
     * Updates XZ position and velocity; Y components are preserved.
     */
    void apply_2d_result(const RigidBody& body_2d) {
        position.x = body_2d.position.x;
        position.z = body_2d.position.y;  // 2D Y maps to 3D Z
        velocity.x = body_2d.velocity.x;
        velocity.z = body_2d.velocity.y;  // 2D Y maps to 3D Z
    }
};

/**
 * 2D heightfield for terrain collision in 3D physics.
 *
 * Samples are arranged on a 2D grid (X, Z) and represent the ground
 * height (Y coordinate). Uses bilinear interpolation for smooth sampling.
 */
class HeightField2D {
public:
    HeightField2D() : x0_(0.0f), z0_(0.0f), cell_size_(1.0f), size_x_(0), size_z_(0) {}

    /**
     * Construct from height data.
     * @param heights Flat array of height values (row-major: [z][x])
     * @param size_x Number of samples in X direction
     * @param size_z Number of samples in Z direction
     * @param x0 X coordinate of first sample
     * @param z0 Z coordinate of first sample
     * @param cell_size Spacing between samples
     */
    HeightField2D(const std::vector<float>& heights,
                  size_t size_x, size_t size_z,
                  float x0 = 0.0f, float z0 = 0.0f, float cell_size = 1.0f)
        : heights_(heights), size_x_(size_x), size_z_(size_z),
          x0_(x0), z0_(z0), cell_size_(cell_size) {}

    /**
     * Sample height at (x, z) with bilinear interpolation.
     * Coordinates outside are clamped to nearest edge.
     */
    float sample(float x, float z) const {
        if (heights_.empty()) return 0.0f;

        // Convert world coordinates to grid coordinates
        float local_x = (x - x0_) / cell_size_;
        float local_z = (z - z0_) / cell_size_;

        // Get integer indices
        int ix0 = static_cast<int>(std::floor(local_x));
        int iz0 = static_cast<int>(std::floor(local_z));
        int ix1 = ix0 + 1;
        int iz1 = iz0 + 1;

        // Clamp indices to valid range
        ix0 = std::max(0, std::min(ix0, static_cast<int>(size_x_) - 1));
        ix1 = std::max(0, std::min(ix1, static_cast<int>(size_x_) - 1));
        iz0 = std::max(0, std::min(iz0, static_cast<int>(size_z_) - 1));
        iz1 = std::max(0, std::min(iz1, static_cast<int>(size_z_) - 1));

        // Fractional parts for interpolation
        float fx = local_x - std::floor(local_x);
        float fz = local_z - std::floor(local_z);
        fx = std::max(0.0f, std::min(1.0f, fx));
        fz = std::max(0.0f, std::min(1.0f, fz));

        // Bilinear interpolation (row-major indexing: [z * size_x + x])
        float h00 = heights_[iz0 * size_x_ + ix0];
        float h10 = heights_[iz0 * size_x_ + ix1];
        float h01 = heights_[iz1 * size_x_ + ix0];
        float h11 = heights_[iz1 * size_x_ + ix1];

        float h0 = h00 * (1.0f - fx) + h10 * fx;
        float h1 = h01 * (1.0f - fx) + h11 * fx;

        return h0 * (1.0f - fz) + h1 * fz;
    }

    /**
     * Check if coordinates are within bounds.
     */
    bool in_bounds(float x, float z) const {
        if (heights_.empty()) return false;
        float x_max = x0_ + cell_size_ * static_cast<float>(size_x_ - 1);
        float z_max = z0_ + cell_size_ * static_cast<float>(size_z_ - 1);
        return x >= x0_ && x <= x_max && z >= z0_ && z <= z_max;
    }

    bool empty() const { return heights_.empty(); }
    size_t size_x() const { return size_x_; }
    size_t size_z() const { return size_z_; }

private:
    std::vector<float> heights_;
    size_t size_x_;
    size_t size_z_;
    float x0_;
    float z0_;
    float cell_size_;
};

/**
 * Configuration for 3D physics simulation step.
 */
struct PhysicsConfig3D {
    float dt = DEFAULT_DT;          // Time step in seconds
    uint32_t iterations = 10;       // Gauss-Seidel iterations for 2D collision
    float restitution = 0.5f;       // Coefficient of restitution
    float cell_size = 0.0f;         // Broad-phase cell size (0 = auto)
    float gravity = -9.8f;          // Gravity acceleration (Y axis)
    float damping = 0.0f;           // Linear velocity damping per second
};

/**
 * Advance 3D physics using hybrid 2D+height approach.
 *
 * The solver uses a two-phase approach:
 * 1. Y-axis: Apply gravity, integrate Y position, resolve terrain collision
 * 2. XZ-plane: Project to 2D, run sequential impulse solver, apply back
 *
 * @param bodies Mutable vector of 3D rigid bodies (modified in-place)
 * @param config Physics simulation configuration
 * @param heightfield Optional 2D heightfield for terrain collision
 */
void step_physics_3d(std::vector<RigidBody3D>& bodies,
                     const PhysicsConfig3D& config = {},
                     const HeightField2D* heightfield = nullptr);

/**
 * 3D Physics world container for managing simulation state.
 */
class PhysicsWorld3D {
public:
    PhysicsWorld3D() = default;

    /**
     * Add a 3D rigid body to the simulation.
     * @return Index of the added body
     */
    size_t add_body(const RigidBody3D& body) {
        bodies_.push_back(body);
        return bodies_.size() - 1;
    }

    /**
     * Get a body by index.
     */
    RigidBody3D& get_body(size_t index) { return bodies_.at(index); }
    const RigidBody3D& get_body(size_t index) const { return bodies_.at(index); }

    /**
     * Get all bodies.
     */
    std::vector<RigidBody3D>& bodies() { return bodies_; }
    const std::vector<RigidBody3D>& bodies() const { return bodies_; }

    /**
     * Set the 2D heightfield for terrain collision.
     */
    void set_heightfield(const HeightField2D& hf) { heightfield_ = hf; }

    /**
     * Clear the heightfield.
     */
    void clear_heightfield() { heightfield_ = HeightField2D(); }

    /**
     * Step the simulation forward.
     */
    void step(const PhysicsConfig3D& config = {}) {
        const HeightField2D* hf = heightfield_.empty() ? nullptr : &heightfield_;
        step_physics_3d(bodies_, config, hf);
    }

    /**
     * Reset to initial state (clear all bodies).
     */
    void reset() {
        bodies_.clear();
        heightfield_ = HeightField2D();
    }

    /**
     * Get body count.
     */
    size_t body_count() const { return bodies_.size(); }

private:
    std::vector<RigidBody3D> bodies_;
    HeightField2D heightfield_;
};

} // namespace physics
