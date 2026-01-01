#pragma once

#include <cstdint>
#include <array>
#include <vector>
#include <cmath>
#include "seed_registry.h"

/**
 * Deterministic terrain generation utilities.
 *
 * This module provides C++ implementations of terrain generation algorithms
 * matching the Python reference in terrain.py. All randomness flows through
 * SeedRegistry to satisfy the determinism contract.
 */

namespace terrain {

// Biome type enumeration matching Python LUT
enum class Biome : uint8_t {
    Water = 0,
    Tundra = 1,
    BorealForest = 2,
    Snow = 3,
    ColdSwamp = 4,
    Glacier = 5,
    Steppe = 6,
    Forest = 7,
    Mountain = 8,
    Swamp = 9,
    Alpine = 10,
    DesertPlateau = 11,
    Savanna = 12,
    Mesa = 13,
    Jungle = 14,
    RainforestHighland = 15
};

/**
 * 2D terrain map container.
 * Stores height, biome, river, and optional slope data.
 */
struct TerrainMaps {
    std::vector<float> height;      // Normalized [0,1] heightmap
    std::vector<uint8_t> biome;     // Biome indices
    std::vector<uint8_t> river;     // River mask (0 or 1)
    std::vector<float> slope;       // Optional slope map [0,1]
    uint32_t size;                  // Width/height of square maps
    bool has_slope;                 // Whether slope was computed
};

/**
 * Configuration for terrain generation.
 */
struct TerrainConfig {
    uint32_t size = 64;             // Map dimensions (size x size)
    uint32_t octaves = 6;           // FBM octave count (6-8 typical)
    uint32_t macro_points = 8;      // Voronoi sites for macro plates (0 disables)
    uint32_t erosion_iters = 0;     // Hydraulic erosion iterations (0 disables)
    bool compute_slope = false;     // Whether to compute slope map
};

/**
 * Simplex noise generator with deterministic permutation table.
 */
class SimplexNoise {
public:
    explicit SimplexNoise(SeedRegistry& registry);

    /**
     * Compute 2D simplex noise at coordinates (x, y).
     * @return Value in range [-1, 1]
     */
    float noise2d(float x, float y) const;

    /**
     * Generate a size x size grid of simplex noise.
     * @param size Grid dimensions
     * @param frequency Noise frequency multiplier
     * @return Flattened row-major grid of noise values
     */
    std::vector<float> grid(uint32_t size, float frequency) const;

private:
    std::array<uint8_t, 512> perm_;  // Permutation table (doubled for wrapping)

    static constexpr std::array<std::array<float, 2>, 8> GRAD2 = {{
        {1.0f, 1.0f}, {-1.0f, 1.0f}, {1.0f, -1.0f}, {-1.0f, -1.0f},
        {1.0f, 0.0f}, {-1.0f, 0.0f}, {0.0f, 1.0f}, {0.0f, -1.0f}
    }};
};

/**
 * Generate Fractal Brownian Motion heightmap.
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param octaves Number of noise layers (6-8 typical)
 * @return Normalized [0,1] heightmap (row-major)
 */
std::vector<float> generate_fbm(SeedRegistry& registry, uint32_t size, uint32_t octaves = 6);

/**
 * Generate Voronoi ridged noise for macro terrain plates.
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param points Number of Voronoi sites
 * @return Ridged noise map [0,1] (row-major)
 */
std::vector<float> generate_voronoi_ridged(SeedRegistry& registry, uint32_t size, uint32_t points = 8);

/**
 * Apply hydraulic erosion simulation to heightmap.
 *
 * @param height Input/output heightmap (modified in-place)
 * @param size Map dimensions
 * @param registry SeedRegistry for deterministic RNG
 * @param iterations Number of erosion iterations
 */
void apply_hydraulic_erosion(std::vector<float>& height, uint32_t size,
                             SeedRegistry& registry, uint32_t iterations);

/**
 * Compute normalized slope map from heightmap.
 *
 * @param height Input heightmap
 * @param size Map dimensions
 * @return Slope map [0,1] (row-major)
 */
std::vector<float> compute_slope_map(const std::vector<float>& height, uint32_t size);

/**
 * Generate biome map from temperature, humidity, and height.
 * Uses a 3x3x3 lookup table matching Python reference.
 *
 * @param temperature Temperature map [0,1]
 * @param humidity Humidity map [0,1]
 * @param height Height map [0,1]
 * @param size Map dimensions
 * @return Biome index map
 */
std::vector<uint8_t> generate_biome_map(const std::vector<float>& temperature,
                                         const std::vector<float>& humidity,
                                         const std::vector<float>& height,
                                         uint32_t size);

/**
 * Generate river mask.
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param probability Probability of river at each cell (default 0.05)
 * @return Binary river mask
 */
std::vector<uint8_t> generate_river_mask(SeedRegistry& registry, uint32_t size,
                                          float probability = 0.05f);

/**
 * Generate complete terrain maps (main entry point).
 *
 * Matches the Python generate_terrain_maps() function signature and behavior.
 *
 * @param registry SeedRegistry with root seed
 * @param config Terrain generation configuration
 * @return TerrainMaps structure with all generated data
 */
TerrainMaps generate_terrain_maps(SeedRegistry& registry, const TerrainConfig& config = {});

} // namespace terrain
