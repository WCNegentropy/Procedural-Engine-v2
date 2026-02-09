#pragma once

#include <cstdint>
#include <array>
#include <vector>
#include <cmath>
#include "seed_registry.h"
#include "props.h"

/**
 * Deterministic terrain generation utilities.
 *
 * This module provides C++ implementations of terrain generation algorithms
 * matching the Python reference in terrain.py. All randomness flows through
 * SeedRegistry to satisfy the determinism contract.
 */

namespace terrain {

// Sea level threshold matching Python SEA_LEVEL constant
static constexpr float SEA_LEVEL = 0.35f;

// Biome type enumeration matching Python biome IDs
enum class Biome : uint8_t {
    DeepOcean = 0,
    Ocean = 1,
    FrozenOcean = 2,
    Tundra = 3,
    Taiga = 4,
    SnowyMountain = 5,
    Plains = 6,
    Forest = 7,
    Mountain = 8,
    Swamp = 9,
    Desert = 10,
    Savanna = 11,
    Mesa = 12,
    Jungle = 13,
    Beach = 14,
    Glacier = 15
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
    float offset_x = 0.0f;          // World-space X offset for seamless chunk tiling
    float offset_z = 0.0f;          // World-space Z offset for seamless chunk tiling
    float base_frequency = 0.01f;   // Base frequency (0.01 = one cycle per 100 world units)
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
     * @param offset_x World-space X offset for seamless chunk tiling
     * @param offset_z World-space Z offset for seamless chunk tiling
     * @return Flattened row-major grid of noise values
     */
    std::vector<float> grid(uint32_t size, float frequency,
                            float offset_x = 0.0f, float offset_z = 0.0f) const;

private:
    std::array<uint8_t, 512> perm_;  // Permutation table (doubled for wrapping)

    static constexpr std::array<std::array<float, 2>, 8> GRAD2 = {{
        {1.0f, 1.0f}, {-1.0f, 1.0f}, {1.0f, -1.0f}, {-1.0f, -1.0f},
        {1.0f, 0.0f}, {-1.0f, 0.0f}, {0.0f, 1.0f}, {0.0f, -1.0f}
    }};
};

/**
 * Default base frequency for terrain generation.
 * 0.01 means one full noise cycle per 100 world units.
 */
static constexpr float DEFAULT_BASE_FREQUENCY = 0.01f;

/**
 * Generate Fractal Brownian Motion heightmap.
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param octaves Number of noise layers (6-8 typical)
 * @param offset_x World-space X offset for seamless chunk tiling
 * @param offset_z World-space Z offset for seamless chunk tiling
 * @param base_frequency Base frequency for noise (0.01 = one cycle per 100 units)
 * @return Normalized [0,1] heightmap (row-major)
 */
std::vector<float> generate_fbm(SeedRegistry& registry, uint32_t size, uint32_t octaves = 6,
                                 float offset_x = 0.0f, float offset_z = 0.0f,
                                 float base_frequency = DEFAULT_BASE_FREQUENCY);

/**
 * Generate continent-scale noise for broad landmasses and ocean basins.
 *
 * Uses only 3 octaves at very low frequency with a cubic remap to create
 * large features spanning many chunks.  Matches Python _continent_noise().
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param offset_x World-space X offset for seamless chunk tiling
 * @param offset_z World-space Z offset for seamless chunk tiling
 * @param base_frequency Base frequency (default 0.003 = continent-scale features)
 * @return Normalized [0,1] heightmap (row-major)
 */
std::vector<float> generate_continent_noise(SeedRegistry& registry, uint32_t size,
                                             float offset_x = 0.0f, float offset_z = 0.0f,
                                             float base_frequency = 0.003f);

/**
 * Generate ridged multi-fractal noise for mountain ranges.
 *
 * Takes the absolute value of simplex noise, inverts it, and layers
 * multiple octaves with detail cascading.  Matches Python _ridged_noise().
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param octaves Number of noise layers (capped at 5 typical)
 * @param offset_x World-space X offset for seamless chunk tiling
 * @param offset_z World-space Z offset for seamless chunk tiling
 * @param base_frequency Base frequency for noise
 * @return Normalized [0,1] heightmap (row-major)
 */
std::vector<float> generate_ridged_noise(SeedRegistry& registry, uint32_t size,
                                          uint32_t octaves = 5,
                                          float offset_x = 0.0f, float offset_z = 0.0f,
                                          float base_frequency = 0.005f);

/**
 * Generate Voronoi ridged noise for macro terrain plates.
 *
 * @deprecated Use generate_global_voronoi_ridged for seamless chunk boundaries.
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param points Number of Voronoi sites
 * @return Ridged noise map [0,1] (row-major)
 */
std::vector<float> generate_voronoi_ridged(SeedRegistry& registry, uint32_t size, uint32_t points = 8);

/**
 * Generate seamless ridged Voronoi noise using global cellular/Worley noise.
 *
 * Unlike generate_voronoi_ridged, this uses world coordinates to determine
 * feature points, ensuring plate boundaries align across chunk boundaries.
 *
 * @param seed Global seed for deterministic plate positions
 * @param size Map dimensions
 * @param offset_x World-space X offset for seamless chunk tiling
 * @param offset_z World-space Z offset for seamless chunk tiling
 * @param frequency Density of Voronoi cells (higher = more, smaller plates)
 * @return Ridged noise map [0,1] (row-major)
 */
std::vector<float> generate_global_voronoi_ridged(uint64_t seed, uint32_t size,
                                                   float offset_x, float offset_z, float frequency);

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
 * Generate seamless river mask using coherent FBM noise.
 *
 * Rivers are generated using thresholded noise, ensuring they cross
 * chunk boundaries naturally as continuous winding paths.
 *
 * @param registry SeedRegistry for deterministic RNG
 * @param size Map dimensions
 * @param offset_x World-space X offset for seamless chunk tiling
 * @param offset_z World-space Z offset for seamless chunk tiling
 * @param base_frequency Base frequency for river noise (default 0.01)
 * @return Binary river mask
 */
std::vector<uint8_t> generate_river_mask(SeedRegistry& registry, uint32_t size,
                                          float offset_x = 0.0f, float offset_z = 0.0f,
                                          float base_frequency = DEFAULT_BASE_FREQUENCY);

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

/**
 * Generate terrain mesh from heightmap with biome colors.
 *
 * @param heightmap Flattened row-major heightmap (size x size)
 * @param biome_map Optional biome indices (size x size), nullptr for height-based coloring
 * @param size Width and height of heightmap
 * @param cell_size Size of each grid cell in world units (default 1.0)
 * @param height_scale Vertical scaling factor for height values (default 1.0)
 * @return Mesh with vertices, normals, colors, and triangle indices
 */
::props::Mesh generate_terrain_mesh(
    const std::vector<float>& heightmap,
    const std::vector<uint8_t>* biome_map,
    uint32_t size,
    float cell_size = 1.0f,
    float height_scale = 1.0f
);

// Overload for backwards compatibility (no biome map)
inline ::props::Mesh generate_terrain_mesh(
    const std::vector<float>& heightmap,
    uint32_t size,
    float cell_size = 1.0f,
    float height_scale = 1.0f
) {
    return generate_terrain_mesh(heightmap, nullptr, size, cell_size, height_scale);
}

} // namespace terrain
