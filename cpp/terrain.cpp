#include "terrain.h"
#include "props.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace terrain {

// ============================================================================
// Robust Noise Implementation
// ============================================================================

// Permutation table (will be initialized in constructor)
static std::array<uint8_t, 512> PERM;

// Gradient vectors
static const float GRAD3[][3] = {
    {1,1,0}, {-1,1,0}, {1,-1,0}, {-1,-1,0},
    {1,0,1}, {-1,0,1}, {1,0,-1}, {-1,0,-1},
    {0,1,1}, {0,-1,1}, {0,1,-1}, {0,-1,-1}
};

SimplexNoise::SimplexNoise(SeedRegistry& registry) {
    // Initialize permutation table
    std::array<uint8_t, 256> p;
    for (int i = 0; i < 256; i++) {
        p[i] = static_cast<uint8_t>(i);
    }

    // Shuffle using registry RNG
    for (int i = 255; i > 0; --i) {
        uint64_t r = registry.next_u64();
        int j = static_cast<int>(r % (i + 1));
        std::swap(p[i], p[j]);
    }

    // Fill the global table (doubled)
    for (int i = 0; i < 512; i++) {
        PERM[i] = p[i & 255];
    }
}

// Standard 2D Simplex Noise
// Source: Stefan Gustavson's reference implementation
float SimplexNoise::noise2d(float x, float y) const {
    const float F2 = 0.366025403f; // 0.5*(sqrt(3.0)-1.0)
    const float G2 = 0.211324865f; // (3.0-sqrt(3.0))/6.0

    float n0, n1, n2; // Noise contributions from the three corners

    // Skew the input space to determine which simplex cell we're in
    float s = (x + y) * F2;
    int i = static_cast<int>(std::floor(x + s));
    int j = static_cast<int>(std::floor(y + s));

    float t = (i + j) * G2;
    float X0 = i - t;
    float Y0 = j - t;
    float x0 = x - X0;
    float y0 = y - Y0;

    // Determine which simplex we are in
    int i1, j1; 
    if (x0 > y0) { i1 = 1; j1 = 0; } // lower triangle
    else         { i1 = 0; j1 = 1; } // upper triangle

    float x1 = x0 - i1 + G2;
    float y1 = y0 - j1 + G2;
    float x2 = x0 - 1.0f + 2.0f * G2;
    float y2 = y0 - 1.0f + 2.0f * G2;

    // Work with hashed gradient indices
    // This masking is where the previous implementation failed for infinite worlds
    // We must ensure continuity.
    int ii = i & 255;
    int jj = j & 255;

    int gi0 = PERM[ii + PERM[jj]] % 12;
    int gi1 = PERM[ii + i1 + PERM[jj + j1]] % 12;
    int gi2 = PERM[ii + 1 + PERM[jj + 1]] % 12;

    // Calculate the contribution from the three corners
    float t0 = 0.5f - x0*x0 - y0*y0;
    if (t0 < 0) n0 = 0.0f;
    else {
        t0 *= t0;
        n0 = t0 * t0 * (GRAD3[gi0][0]*x0 + GRAD3[gi0][1]*y0); 
    }

    float t1 = 0.5f - x1*x1 - y1*y1;
    if (t1 < 0) n1 = 0.0f;
    else {
        t1 *= t1;
        n1 = t1 * t1 * (GRAD3[gi1][0]*x1 + GRAD3[gi1][1]*y1);
    }

    float t2 = 0.5f - x2*x2 - y2*y2;
    if (t2 < 0) n2 = 0.0f;
    else {
        t2 *= t2;
        n2 = t2 * t2 * (GRAD3[gi2][0]*x2 + GRAD3[gi2][1]*y2);
    }

    // Add contributions from each corner to get the final noise value.
    // The result is scaled to return values in the interval [-1,1].
    return 70.0f * (n0 + n1 + n2);
}

std::vector<float> SimplexNoise::grid(uint32_t size, float frequency,
                                      float offset_x, float offset_z) const {
    std::vector<float> result(size * size);
    
    // Pre-calculate coordinate scaling to avoid doing it in the inner loop
    for (uint32_t y = 0; y < size; ++y) {
        float world_z = (static_cast<float>(y) + offset_z) * frequency;
        
        for (uint32_t x = 0; x < size; ++x) {
            float world_x = (static_cast<float>(x) + offset_x) * frequency;
            result[y * size + x] = noise2d(world_x, world_z);
        }
    }
    return result;
}

// Generate Fractal Brownian Motion heightmap
std::vector<float> generate_fbm(SeedRegistry& registry, uint32_t size, uint32_t octaves,
                                float offset_x, float offset_z, float base_frequency) {
    SimplexNoise noise(registry);

    std::vector<float> height(size * size, 0.0f);
    float amplitude = 1.0f;
    float frequency = base_frequency;
    float max_possible_value = 0.0f;

    for (uint32_t oct = 0; oct < octaves; ++oct) {
        auto layer = noise.grid(size, frequency, offset_x, offset_z);
        for (size_t i = 0; i < height.size(); ++i) {
            height[i] += layer[i] * amplitude;
        }
        max_possible_value += amplitude;
        amplitude *= 0.5f;
        frequency *= 2.0f;
    }

    // Normalize strictly to [0, 1] based on theoretical max
    // DO NOT use min/max of the current chunk, as that causes seams between chunks
    // where one chunk might have a mountain and another is flat.
    float inv_max = 1.0f / max_possible_value;
    for (auto& h : height) {
        // Shift from [-max, max] to [0, 1]
        h = (h * inv_max + 1.0f) * 0.5f;
        // Clamp for safety
        h = std::clamp(h, 0.0f, 1.0f);
    }

    return height;
}

std::vector<float> generate_voronoi_ridged(SeedRegistry& registry, uint32_t size, uint32_t points) {
    // Generate random seed points
    std::vector<float> seeds_x(points);
    std::vector<float> seeds_y(points);

    for (uint32_t p = 0; p < points; ++p) {
        // Generate random float in [0, size) matching Python's rng.random() * size
        uint64_t rx = registry.next_u64();
        uint64_t ry = registry.next_u64();
        // Convert to [0, 1) then scale to size
        seeds_x[p] = static_cast<float>(rx >> 11) * (1.0f / 9007199254740992.0f) * static_cast<float>(size);
        seeds_y[p] = static_cast<float>(ry >> 11) * (1.0f / 9007199254740992.0f) * static_cast<float>(size);
    }

    std::vector<float> result(size * size);
    float max_dist = 0.0f;

    // Compute minimum distance to any seed point for each cell
    for (uint32_t y = 0; y < size; ++y) {
        for (uint32_t x = 0; x < size; ++x) {
            float min_dist = std::numeric_limits<float>::max();
            float fx = static_cast<float>(x);
            float fy = static_cast<float>(y);

            for (uint32_t p = 0; p < points; ++p) {
                float dx = fx - seeds_x[p];
                float dy = fy - seeds_y[p];
                float dist = std::sqrt(dx * dx + dy * dy);
                min_dist = std::min(min_dist, dist);
            }

            result[y * size + x] = min_dist;
            max_dist = std::max(max_dist, min_dist);
        }
    }

    // Normalize and invert to get ridges
    if (max_dist > 0.0f) {
        float inv_max = 1.0f / max_dist;
        for (auto& d : result) {
            d = 1.0f - d * inv_max;  // Ridged: high at boundaries
        }
    }

    return result;
}

void apply_hydraulic_erosion(std::vector<float>& height, uint32_t size,
                             SeedRegistry& registry, uint32_t iterations) {
    for (uint32_t iter = 0; iter < iterations; ++iter) {
        // Random cell selection matching Python's rng.integers(0, size)
        uint64_t rx = registry.next_u64();
        uint64_t ry = registry.next_u64();
        int x = static_cast<int>(rx % size);
        int y = static_cast<int>(ry % size);

        // Compute neighborhood bounds
        int x0 = std::max(x - 1, 0);
        int x1 = std::min(x + 1, static_cast<int>(size) - 1);
        int y0 = std::max(y - 1, 0);
        int y1 = std::min(y + 1, static_cast<int>(size) - 1);

        // Compute neighborhood average
        float sum = 0.0f;
        int count = 0;
        for (int ny = y0; ny <= y1; ++ny) {
            for (int nx = x0; nx <= x1; ++nx) {
                sum += height[ny * size + nx];
                ++count;
            }
        }
        float avg = sum / static_cast<float>(count);

        // Relax toward average
        size_t idx = static_cast<size_t>(y * size + x);
        height[idx] = (height[idx] + avg) * 0.5f;
    }

    // Clamp to [0, 1]
    for (auto& h : height) {
        h = std::clamp(h, 0.0f, 1.0f);
    }
}

std::vector<float> compute_slope_map(const std::vector<float>& height, uint32_t size) {
    std::vector<float> slope(size * size);

    // Compute gradient magnitude using central differences
    for (uint32_t y = 0; y < size; ++y) {
        for (uint32_t x = 0; x < size; ++x) {
            // X gradient (central difference with boundary handling)
            float gx;
            if (x == 0) {
                gx = height[y * size + 1] - height[y * size];
            } else if (x == size - 1) {
                gx = height[y * size + x] - height[y * size + x - 1];
            } else {
                gx = (height[y * size + x + 1] - height[y * size + x - 1]) * 0.5f;
            }

            // Y gradient
            float gy;
            if (y == 0) {
                gy = height[size + x] - height[x];
            } else if (y == size - 1) {
                gy = height[y * size + x] - height[(y - 1) * size + x];
            } else {
                gy = (height[(y + 1) * size + x] - height[(y - 1) * size + x]) * 0.5f;
            }

            slope[y * size + x] = std::sqrt(gx * gx + gy * gy);
        }
    }

    // Normalize to [0, 1]
    float s_min = *std::min_element(slope.begin(), slope.end());
    float s_max = *std::max_element(slope.begin(), slope.end());

    if (s_max > s_min) {
        float inv_range = 1.0f / (s_max - s_min);
        for (auto& s : slope) {
            s = (s - s_min) * inv_range;
        }
    } else {
        std::fill(slope.begin(), slope.end(), 0.0f);
    }

    return slope;
}

std::vector<uint8_t> generate_biome_map(const std::vector<float>& temperature,
                                         const std::vector<float>& humidity,
                                         const std::vector<float>& height,
                                         uint32_t size) {
    // Biome LUT matching Python reference: [temp_idx][humid_idx][height_idx]
    // temp_idx: 0=cold, 1=temperate, 2=hot
    // humid_idx: 0=dry, 1=normal, 2=wet
    // height_idx: 0=low, 1=mid, 2=high
    static constexpr uint8_t BIOME_LUT[3][3][3] = {
        // Cold
        {
            {0, 0, 1},    // dry  -> water, water, tundra
            {0, 2, 3},    // normal -> water, boreal forest, snow
            {0, 4, 5},    // wet -> water, cold swamp, glacier
        },
        // Temperate
        {
            {0, 0, 6},    // dry -> water, water, steppe
            {0, 7, 8},    // normal -> water, forest, mountain
            {0, 9, 10},   // wet -> water, swamp, alpine
        },
        // Hot
        {
            {0, 0, 11},   // dry -> water, water, desert plateau
            {0, 12, 13},  // normal -> water, savanna, mesa
            {0, 14, 15},  // wet -> water, jungle, rainforest highland
        },
    };

    std::vector<uint8_t> biome(size * size);

    for (size_t i = 0; i < size * size; ++i) {
        // Clamp inputs to [0, 1] to ensure valid LUT indices
        float temp_clamped = std::clamp(temperature[i], 0.0f, 1.0f);
        float humid_clamped = std::clamp(humidity[i], 0.0f, 1.0f);
        float height_clamped = std::clamp(height[i], 0.0f, 1.0f);

        // Digitize temperature: [0, 0.33) -> 0, [0.33, 0.66) -> 1, [0.66, 1] -> 2
        int temp_idx;
        if (temp_clamped < 0.33f) temp_idx = 0;
        else if (temp_clamped < 0.66f) temp_idx = 1;
        else temp_idx = 2;

        // Digitize humidity
        int humid_idx;
        if (humid_clamped < 0.33f) humid_idx = 0;
        else if (humid_clamped < 0.66f) humid_idx = 1;
        else humid_idx = 2;

        // Digitize height
        int height_idx;
        if (height_clamped < 0.3f) height_idx = 0;
        else if (height_clamped < 0.6f) height_idx = 1;
        else height_idx = 2;

        biome[i] = BIOME_LUT[temp_idx][humid_idx][height_idx];
    }

    return biome;
}

std::vector<uint8_t> generate_river_mask(SeedRegistry& registry, uint32_t size, float probability) {
    std::vector<uint8_t> river(size * size);

    for (size_t i = 0; i < size * size; ++i) {
        uint64_t r = registry.next_u64();
        // Convert to [0, 1) float
        float val = static_cast<float>(r >> 11) * (1.0f / 9007199254740992.0f);
        river[i] = (val < probability) ? 1 : 0;
    }

    return river;
}

TerrainMaps generate_terrain_maps(SeedRegistry& registry, const TerrainConfig& config) {
    TerrainMaps maps;
    maps.size = config.size;
    maps.has_slope = config.compute_slope;

    // Height generation using FBM with offsets
    uint64_t height_seed = registry.get_subseed("height");
    SeedRegistry height_reg(height_seed);
    
    // Critical fix: Ensure offsets are floats
    float ox = config.offset_x;
    float oz = config.offset_z;
    
    maps.height = generate_fbm(height_reg, config.size, config.octaves, 
                              ox, oz, config.base_frequency);

    // Apply macro plates
    if (config.macro_points > 0) {
        uint64_t macro_seed = registry.get_subseed("macro");
        SeedRegistry macro_reg(macro_seed);
        // Note: Voronoi isn't perfectly seamless yet without more complex logic
        // For now, we rely on FBM being the dominant factor
        auto macro = generate_voronoi_ridged(macro_reg, config.size, config.macro_points);
        for (size_t i = 0; i < maps.height.size(); ++i) {
            maps.height[i] = std::clamp((maps.height[i] + macro[i]) * 0.5f, 0.0f, 1.0f);
        }
    }

    // Apply erosion
    if (config.erosion_iters > 0) {
        uint64_t erosion_seed = registry.get_subseed("erosion");
        SeedRegistry erosion_reg(erosion_seed);
        apply_hydraulic_erosion(maps.height, config.size, erosion_reg, config.erosion_iters);
    }

    // Temperature and humidity for biomes
    float biome_freq = config.base_frequency * 0.5f;
    
    uint64_t temp_seed = registry.get_subseed("temperature");
    SeedRegistry temp_reg(temp_seed);
    auto temperature = generate_fbm(temp_reg, config.size, 2, ox, oz, biome_freq);

    uint64_t humid_seed = registry.get_subseed("humidity");
    SeedRegistry humid_reg(humid_seed);
    auto humidity = generate_fbm(humid_reg, config.size, 2, ox, oz, biome_freq);

    // Generate biome map from temperature, humidity, and height
    maps.biome = generate_biome_map(temperature, humidity, maps.height, config.size);

    // Generate river mask
    uint64_t river_seed = registry.get_subseed("river");
    SeedRegistry river_reg(river_seed);
    maps.river = generate_river_mask(river_reg, config.size);

    // Compute slope if requested
    if (config.compute_slope) {
        maps.slope = compute_slope_map(maps.height, config.size);
    }

    return maps;
}

// Biome color palette matching the Biome enum
static const std::array<std::array<float, 3>, 16> BIOME_COLORS = {{
    {0.15f, 0.35f, 0.60f},  // 0: Water - deep blue
    {0.75f, 0.78f, 0.80f},  // 1: Tundra - pale gray
    {0.20f, 0.35f, 0.25f},  // 2: BorealForest - dark green
    {0.95f, 0.97f, 1.00f},  // 3: Snow - white
    {0.30f, 0.35f, 0.30f},  // 4: ColdSwamp - murky green
    {0.85f, 0.92f, 0.98f},  // 5: Glacier - ice blue
    {0.72f, 0.68f, 0.50f},  // 6: Steppe - tan/khaki
    {0.25f, 0.50f, 0.20f},  // 7: Forest - green
    {0.50f, 0.45f, 0.40f},  // 8: Mountain - gray-brown
    {0.35f, 0.42f, 0.30f},  // 9: Swamp - dark olive
    {0.55f, 0.58f, 0.55f},  // 10: Alpine - light gray
    {0.85f, 0.75f, 0.55f},  // 11: DesertPlateau - sand
    {0.70f, 0.62f, 0.35f},  // 12: Savanna - golden brown
    {0.75f, 0.50f, 0.35f},  // 13: Mesa - orange-red
    {0.15f, 0.55f, 0.25f},  // 14: Jungle - vibrant green
    {0.20f, 0.48f, 0.30f},  // 15: RainforestHighland - deep green
}};

::props::Mesh generate_terrain_mesh(
    const std::vector<float>& heightmap,
    const std::vector<uint8_t>* biome_map,
    uint32_t size,
    float cell_size,
    float height_scale
) {
    ::props::Mesh mesh;

    if (heightmap.size() != size * size) {
        return mesh;
    }

    bool has_biomes = biome_map && biome_map->size() == size * size;

    // 1. Generate vertices with colors
    mesh.vertices.reserve(size * size);
    mesh.colors.reserve(size * size);
    
    for (uint32_t z = 0; z < size; ++z) {
        for (uint32_t x = 0; x < size; ++x) {
            size_t idx = z * size + x;
            float world_x = static_cast<float>(x) * cell_size;
            float world_y = heightmap[idx] * height_scale;
            float world_z = static_cast<float>(z) * cell_size;
            mesh.vertices.push_back(::props::Vec3(world_x, world_y, world_z));
            
            // Determine color from biome or height
            ::props::Vec3 color;
            if (has_biomes) {
                uint8_t biome_idx = (*biome_map)[idx];
                if (biome_idx < BIOME_COLORS.size()) {
                    color = ::props::Vec3(
                        BIOME_COLORS[biome_idx][0],
                        BIOME_COLORS[biome_idx][1],
                        BIOME_COLORS[biome_idx][2]
                    );
                } else {
                    color = ::props::Vec3(1.0f, 0.0f, 1.0f); // Magenta for invalid
                }
            } else {
                // Height-based gradient fallback
                float h = heightmap[idx];
                if (h < 0.25f) {
                    // Low: water/beach blend
                    float t = h / 0.25f;
                    color = ::props::Vec3(
                        0.15f + t * 0.55f,
                        0.35f + t * 0.30f,
                        0.60f - t * 0.45f
                    );
                } else if (h < 0.5f) {
                    // Mid-low: grass/forest
                    float t = (h - 0.25f) / 0.25f;
                    color = ::props::Vec3(
                        0.25f - t * 0.05f,
                        0.50f + t * 0.05f,
                        0.15f + t * 0.05f
                    );
                } else if (h < 0.75f) {
                    // Mid-high: forest to mountain
                    float t = (h - 0.5f) / 0.25f;
                    color = ::props::Vec3(
                        0.20f + t * 0.30f,
                        0.55f - t * 0.15f,
                        0.20f + t * 0.20f
                    );
                } else {
                    // High: mountain to snow
                    float t = (h - 0.75f) / 0.25f;
                    color = ::props::Vec3(
                        0.50f + t * 0.45f,
                        0.40f + t * 0.55f,
                        0.40f + t * 0.55f
                    );
                }
            }
            mesh.colors.push_back(color);
        }
    }

    // 2. Generate indices (2 triangles per quad)
    mesh.indices.reserve((size - 1) * (size - 1) * 6);
    for (uint32_t z = 0; z < size - 1; ++z) {
        for (uint32_t x = 0; x < size - 1; ++x) {
            uint32_t tl = z * size + x;
            uint32_t tr = z * size + x + 1;
            uint32_t bl = (z + 1) * size + x;
            uint32_t br = (z + 1) * size + x + 1;

            mesh.indices.push_back(tl);
            mesh.indices.push_back(bl);
            mesh.indices.push_back(tr);

            mesh.indices.push_back(tr);
            mesh.indices.push_back(bl);
            mesh.indices.push_back(br);
        }
    }

    // 3. Compute smooth normals
    mesh.normals.reserve(size * size);
    for (uint32_t z = 0; z < size; ++z) {
        for (uint32_t x = 0; x < size; ++x) {
            float gx, gz;

            if (x == 0) {
                gx = (heightmap[z * size + 1] - heightmap[z * size]) * height_scale / cell_size;
            } else if (x == size - 1) {
                gx = (heightmap[z * size + x] - heightmap[z * size + x - 1]) * height_scale / cell_size;
            } else {
                gx = (heightmap[z * size + x + 1] - heightmap[z * size + x - 1]) * height_scale / (2.0f * cell_size);
            }

            if (z == 0) {
                gz = (heightmap[size + x] - heightmap[x]) * height_scale / cell_size;
            } else if (z == size - 1) {
                gz = (heightmap[z * size + x] - heightmap[(z - 1) * size + x]) * height_scale / cell_size;
            } else {
                gz = (heightmap[(z + 1) * size + x] - heightmap[(z - 1) * size + x]) * height_scale / (2.0f * cell_size);
            }

            ::props::Vec3 normal(-gx, 1.0f, -gz);
            mesh.normals.push_back(normal.normalized());
        }
    }

    return mesh;
}

} // namespace terrain
