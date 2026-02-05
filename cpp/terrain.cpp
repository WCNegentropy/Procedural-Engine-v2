#include "terrain.h"
#include "props.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace terrain {

// Simplex noise constants
static constexpr float F2 = 0.3660254037844386f;   // 0.5 * (sqrt(3) - 1)
static constexpr float G2 = 0.21132486540518713f;  // (3 - sqrt(3)) / 6

// Initialize constexpr gradient table (8 gradients for 2D)
constexpr std::array<std::array<float, 2>, 8> SimplexNoise::GRAD2;

SimplexNoise::SimplexNoise(SeedRegistry& registry) {
    // Generate permutation table using Fisher-Yates shuffle
    // This matches numpy's rng.permutation(256) behavior
    std::array<uint8_t, 256> base_perm;
    std::iota(base_perm.begin(), base_perm.end(), 0);

    // Fisher-Yates shuffle using registry's RNG
    for (int i = 255; i > 0; --i) {
        uint64_t r = registry.next_u64();
        int j = static_cast<int>(r % (i + 1));
        std::swap(base_perm[i], base_perm[j]);
    }

    // Double the permutation table for wrapping
    // Stored in member variable perm_ for thread safety
    for (int i = 0; i < 256; ++i) {
        perm_[i] = base_perm[i];
        perm_[i + 256] = base_perm[i];
    }
}

float SimplexNoise::noise2d(float x, float y) const {
    // Skew input space to simplex cell
    float s = (x + y) * F2;
    int i = static_cast<int>(std::floor(x + s));
    int j = static_cast<int>(std::floor(y + s));

    // Unskew back to (x, y) space
    float t = static_cast<float>(i + j) * G2;
    float X0 = static_cast<float>(i) - t;
    float Y0 = static_cast<float>(j) - t;
    float x0 = x - X0;
    float y0 = y - Y0;

    // Determine which simplex we're in
    int i1, j1;
    if (x0 > y0) {
        i1 = 1; j1 = 0;
    } else {
        i1 = 0; j1 = 1;
    }

    // Offsets for corners
    float x1 = x0 - static_cast<float>(i1) + G2;
    float y1 = y0 - static_cast<float>(j1) + G2;
    float x2 = x0 - 1.0f + 2.0f * G2;
    float y2 = y0 - 1.0f + 2.0f * G2;

    // Hash coordinates to gradient indices
    int ii = i & 255;
    int jj = j & 255;
    
    // Modulo 8 matches the 8 gradients in GRAD2, preventing directional bias
    int gi0 = perm_[ii + perm_[jj]] % 8;
    int gi1 = perm_[ii + i1 + perm_[jj + j1]] % 8;
    int gi2 = perm_[ii + 1 + perm_[jj + 1]] % 8;

    // Calculate contribution from each corner
    float n0 = 0.0f, n1 = 0.0f, n2 = 0.0f;

    float t0 = 0.5f - x0 * x0 - y0 * y0;
    if (t0 > 0.0f) {
        t0 *= t0;
        n0 = t0 * t0 * (GRAD2[gi0][0] * x0 + GRAD2[gi0][1] * y0);
    }

    float t1 = 0.5f - x1 * x1 - y1 * y1;
    if (t1 > 0.0f) {
        t1 *= t1;
        n1 = t1 * t1 * (GRAD2[gi1][0] * x1 + GRAD2[gi1][1] * y1);
    }

    float t2 = 0.5f - x2 * x2 - y2 * y2;
    if (t2 > 0.0f) {
        t2 *= t2;
        n2 = t2 * t2 * (GRAD2[gi2][0] * x2 + GRAD2[gi2][1] * y2);
    }

    // Result is in approx [-1, 1] range (scaled by 70.0)
    return 70.0f * (n0 + n1 + n2);
}

std::vector<float> SimplexNoise::grid(uint32_t size, float frequency,
                                      float offset_x, float offset_z) const {
    std::vector<float> result(size * size);

    for (uint32_t y = 0; y < size; ++y) {
        float world_z = (static_cast<float>(y) + offset_z) * frequency;
        for (uint32_t x = 0; x < size; ++x) {
            float world_x = (static_cast<float>(x) + offset_x) * frequency;
            result[y * size + x] = noise2d(world_x, world_z);
        }
    }
    return result;
}

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

    // CRITICAL FIX: Global Normalization
    // Do NOT normalize using local min/max of the chunk, as that guarantees seams.
    // Instead, normalize using the theoretical maximum range of the FBM summation.
    // noise2d returns approx [-1, 1], so FBM sums to [-max_possible, max_possible].
    if (max_possible_value > 0.0f) {
        float scale = 1.0f / max_possible_value;
        for (auto& h : height) {
            // Map [-max, max] to [-1, 1] then to [0, 1]
            h = (h * scale) * 0.5f + 0.5f;
            // Clamp to ensure floating point errors don't exceed bounds
            h = std::clamp(h, 0.0f, 1.0f);
        }
    }

    return height;
}

// Helper: Hash integer cell coordinates to a float [0, 1]
// This ensures deterministic, globally consistent feature point positions
static float hash_coords(int x, int y, uint64_t seed) {
    uint64_t h = static_cast<uint64_t>(x) * 374761393ULL;
    h ^= static_cast<uint64_t>(y) * 668265263ULL;
    h ^= seed;
    h = (h ^ (h >> 13)) * 1274126177ULL;
    return static_cast<float>((h ^ (h >> 16)) & 0xFFFFULL) / 65535.0f;
}

// Generate seamless ridged Voronoi noise using global cellular/Worley noise
// Unlike the local implementation, this uses world coordinates to determine
// feature points, ensuring plate boundaries align across chunk boundaries.
std::vector<float> generate_global_voronoi_ridged(
    uint64_t seed, uint32_t size,
    float offset_x, float offset_z, float frequency
) {
    std::vector<float> result(size * size);

    for (uint32_t y = 0; y < size; ++y) {
        for (uint32_t x = 0; x < size; ++x) {
            float world_x = (static_cast<float>(x) + offset_x) * frequency;
            float world_z = (static_cast<float>(y) + offset_z) * frequency;

            // Cell coordinates in the global grid
            int cx = static_cast<int>(std::floor(world_x));
            int cy = static_cast<int>(std::floor(world_z));

            float min_dist = 100.0f;

            // Check 3x3 neighbor cells for closest feature point
            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    int ncx = cx + dx;
                    int ncy = cy + dy;

                    // Generate two independent random values for x and y offsets.
                    // Using different coordinate offsets (123, 456) ensures px and py
                    // are decorrelated, producing better-distributed feature points.
                    float px = static_cast<float>(ncx) + hash_coords(ncx, ncy, seed);
                    float py = static_cast<float>(ncy) + hash_coords(ncx + 123, ncy + 456, seed);

                    float dist_sq = (world_x - px) * (world_x - px) + (world_z - py) * (world_z - py);
                    min_dist = std::min(min_dist, dist_sq);
                }
            }

            // Sqrt for euclidean distance, normalize, and invert for ridges
            // 1.0 at cell centers (plate interiors), lower at edges (plate boundaries)
            result[y * size + x] = 1.0f - std::clamp(std::sqrt(min_dist), 0.0f, 1.0f);
        }
    }

    return result;
}

// Legacy local Voronoi implementation (deprecated - causes chunk boundary seams)
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
    // Note: This erosion simulation is local to the chunk and random.
    // It WILL create seams at chunk boundaries if iterations > 0.
    // For seamless infinite terrain, erosion should either be disabled
    // or implemented using a deterministic, global approach (not done here).
    for (uint32_t iter = 0; iter < iterations; ++iter) {
        uint64_t rx = registry.next_u64();
        uint64_t ry = registry.next_u64();
        int x = static_cast<int>(rx % size);
        int y = static_cast<int>(ry % size);

        int x0 = std::max(x - 1, 0);
        int x1 = std::min(x + 1, static_cast<int>(size) - 1);
        int y0 = std::max(y - 1, 0);
        int y1 = std::min(y + 1, static_cast<int>(size) - 1);

        float sum = 0.0f;
        int count = 0;
        for (int ny = y0; ny <= y1; ++ny) {
            for (int nx = x0; nx <= x1; ++nx) {
                sum += height[ny * size + nx];
                ++count;
            }
        }
        float avg = sum / static_cast<float>(count);

        size_t idx = static_cast<size_t>(y * size + x);
        height[idx] = (height[idx] + avg) * 0.5f;
    }

    for (auto& h : height) {
        h = std::clamp(h, 0.0f, 1.0f);
    }
}

std::vector<float> compute_slope_map(const std::vector<float>& height, uint32_t size) {
    std::vector<float> slope(size * size);

    for (uint32_t y = 0; y < size; ++y) {
        for (uint32_t x = 0; x < size; ++x) {
            float gx, gy;
            
            // X gradient
            if (x == 0) gx = height[y * size + 1] - height[y * size];
            else if (x == size - 1) gx = height[y * size + x] - height[y * size + x - 1];
            else gx = (height[y * size + x + 1] - height[y * size + x - 1]) * 0.5f;

            // Y gradient
            if (y == 0) gy = height[size + x] - height[x];
            else if (y == size - 1) gy = height[y * size + x] - height[(y - 1) * size + x];
            else gy = (height[(y + 1) * size + x] - height[(y - 1) * size + x]) * 0.5f;

            slope[y * size + x] = std::sqrt(gx * gx + gy * gy);
        }
    }

    // Slope normalization is inherently local (gradient depends on local height deltas).
    // This is generally acceptable for prop placement, but for visuals
    // a global max slope constant would be better if perfect consistency is needed.
    float s_min = 0.0f; // Slope is always >= 0
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
    // Biome LUT [temp][humid][height]
    static constexpr uint8_t BIOME_LUT[3][3][3] = {
        { {0, 0, 1}, {0, 2, 3}, {0, 4, 5} },    // Cold
        { {0, 0, 6}, {0, 7, 8}, {0, 9, 10} },   // Temperate
        { {0, 0, 11}, {0, 12, 13}, {0, 14, 15} } // Hot
    };

    std::vector<uint8_t> biome(size * size);

    for (size_t i = 0; i < size * size; ++i) {
        float t = std::clamp(temperature[i], 0.0f, 1.0f);
        float h = std::clamp(humidity[i], 0.0f, 1.0f);
        float alt = std::clamp(height[i], 0.0f, 1.0f);

        int t_idx = (t < 0.33f) ? 0 : (t < 0.66f ? 1 : 2);
        int h_idx = (h < 0.33f) ? 0 : (h < 0.66f ? 1 : 2);
        int a_idx = (alt < 0.3f) ? 0 : (alt < 0.6f ? 1 : 2);

        biome[i] = BIOME_LUT[t_idx][h_idx][a_idx];
    }
    return biome;
}

// Generate seamless river mask using coherent FBM noise instead of white noise
// This ensures rivers naturally cross chunk boundaries as continuous winding paths
std::vector<uint8_t> generate_river_mask(SeedRegistry& registry, uint32_t size,
                                          float offset_x, float offset_z, float base_frequency) {
    // Use FBM noise to create coherent river patterns
    auto river_noise = generate_fbm(registry, size, 4, offset_x, offset_z, base_frequency * 2.0f);

    std::vector<uint8_t> river(size * size);
    for (size_t i = 0; i < size * size; ++i) {
        // Create distinct river paths by thresholding a narrow band around 0.5.
        // This technique selects values near the noise function's midpoint, which
        // form contour-like bands that naturally wind through the noise field,
        // creating organic river channels that cross chunk boundaries seamlessly.
        river[i] = (std::abs(river_noise[i] - 0.5f) < 0.025f) ? 1 : 0;
    }

    return river;
}

// Legacy white noise river generation (deprecated - causes chunk boundary seams)
std::vector<uint8_t> generate_river_mask_legacy(SeedRegistry& registry, uint32_t size, float probability) {
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

    uint64_t height_seed = registry.get_subseed("height");
    SeedRegistry height_reg(height_seed);
    maps.height = generate_fbm(height_reg, config.size, config.octaves,
                                config.offset_x, config.offset_z, config.base_frequency);

    // Apply macro plates using global Voronoi for seamless boundaries
    if (config.macro_points > 0) {
        uint64_t macro_seed = registry.get_subseed("macro");
        // Convert "points" count to frequency for global Voronoi
        // Using sqrt(points)/size approximates similar point density
        float macro_freq = std::sqrt(static_cast<float>(config.macro_points)) / static_cast<float>(config.size);
        auto macro = generate_global_voronoi_ridged(macro_seed, config.size,
                                                     config.offset_x, config.offset_z, macro_freq);
        for (size_t i = 0; i < maps.height.size(); ++i) {
            maps.height[i] = std::clamp((maps.height[i] + macro[i]) * 0.5f, 0.0f, 1.0f);
        }
    }

    if (config.erosion_iters > 0) {
        uint64_t erosion_seed = registry.get_subseed("erosion");
        SeedRegistry erosion_reg(erosion_seed);
        apply_hydraulic_erosion(maps.height, config.size, erosion_reg, config.erosion_iters);
    }

    float biome_freq = config.base_frequency * 0.5f;
    uint64_t temp_seed = registry.get_subseed("temperature");
    SeedRegistry temp_reg(temp_seed);
    auto temperature = generate_fbm(temp_reg, config.size, 2, 
                                     config.offset_x, config.offset_z, biome_freq);

    uint64_t humid_seed = registry.get_subseed("humidity");
    SeedRegistry humid_reg(humid_seed);
    auto humidity = generate_fbm(humid_reg, config.size, 2, 
                                  config.offset_x, config.offset_z, biome_freq);

    maps.biome = generate_biome_map(temperature, humidity, maps.height, config.size);

    // Generate seamless rivers using coherent noise
    uint64_t river_seed = registry.get_subseed("river");
    SeedRegistry river_reg(river_seed);
    maps.river = generate_river_mask(river_reg, config.size, config.offset_x, config.offset_z, config.base_frequency);

    if (config.compute_slope) {
        maps.slope = compute_slope_map(maps.height, config.size);
    }

    return maps;
}

static const std::array<std::array<float, 3>, 16> BIOME_COLORS = {{
    {0.15f, 0.35f, 0.60f}, {0.75f, 0.78f, 0.80f}, {0.20f, 0.35f, 0.25f}, {0.95f, 0.97f, 1.00f},
    {0.30f, 0.35f, 0.30f}, {0.85f, 0.92f, 0.98f}, {0.72f, 0.68f, 0.50f}, {0.25f, 0.50f, 0.20f},
    {0.50f, 0.45f, 0.40f}, {0.35f, 0.42f, 0.30f}, {0.55f, 0.58f, 0.55f}, {0.85f, 0.75f, 0.55f},
    {0.70f, 0.62f, 0.35f}, {0.75f, 0.50f, 0.35f}, {0.15f, 0.55f, 0.25f}, {0.20f, 0.48f, 0.30f},
}};

::props::Mesh generate_terrain_mesh(
    const std::vector<float>& heightmap,
    const std::vector<uint8_t>* biome_map,
    uint32_t size,
    float cell_size,
    float height_scale
) {
    ::props::Mesh mesh;
    if (heightmap.size() != size * size) return mesh;
    bool has_biomes = biome_map && biome_map->size() == size * size;

    mesh.vertices.reserve(size * size);
    mesh.colors.reserve(size * size);
    
    for (uint32_t z = 0; z < size; ++z) {
        for (uint32_t x = 0; x < size; ++x) {
            size_t idx = z * size + x;
            float world_x = static_cast<float>(x) * cell_size;
            float world_y = heightmap[idx] * height_scale;
            float world_z = static_cast<float>(z) * cell_size;
            mesh.vertices.push_back(::props::Vec3(world_x, world_y, world_z));
            
            ::props::Vec3 color;
            if (has_biomes) {
                uint8_t biome_idx = (*biome_map)[idx];
                if (biome_idx < BIOME_COLORS.size()) {
                    color = ::props::Vec3(BIOME_COLORS[biome_idx][0], BIOME_COLORS[biome_idx][1], BIOME_COLORS[biome_idx][2]);
                } else {
                    color = ::props::Vec3(1.0f, 0.0f, 1.0f);
                }
            } else {
                float h = heightmap[idx];
                color = ::props::Vec3(h, h, h); // Simple grayscale fallback
            }
            mesh.colors.push_back(color);
        }
    }

    mesh.indices.reserve((size - 1) * (size - 1) * 6);
    for (uint32_t z = 0; z < size - 1; ++z) {
        for (uint32_t x = 0; x < size - 1; ++x) {
            uint32_t tl = z * size + x;
            uint32_t tr = z * size + x + 1;
            uint32_t bl = (z + 1) * size + x;
            uint32_t br = (z + 1) * size + x + 1;
            mesh.indices.push_back(tl); mesh.indices.push_back(bl); mesh.indices.push_back(tr);
            mesh.indices.push_back(tr); mesh.indices.push_back(bl); mesh.indices.push_back(br);
        }
    }

    mesh.normals.reserve(size * size);
    for (uint32_t z = 0; z < size; ++z) {
        for (uint32_t x = 0; x < size; ++x) {
            float gx, gz;
            if (x == 0) gx = (heightmap[z * size + 1] - heightmap[z * size]) * height_scale / cell_size;
            else if (x == size - 1) gx = (heightmap[z * size + x] - heightmap[z * size + x - 1]) * height_scale / cell_size;
            else gx = (heightmap[z * size + x + 1] - heightmap[z * size + x - 1]) * height_scale / (2.0f * cell_size);

            if (z == 0) gz = (heightmap[size + x] - heightmap[x]) * height_scale / cell_size;
            else if (z == size - 1) gz = (heightmap[z * size + x] - heightmap[(z - 1) * size + x]) * height_scale / cell_size;
            else gz = (heightmap[(z + 1) * size + x] - heightmap[(z - 1) * size + x]) * height_scale / (2.0f * cell_size);

            ::props::Vec3 normal(-gx, 1.0f, -gz);
            mesh.normals.push_back(normal.normalized());
        }
    }

    return mesh;
}

} // namespace terrain
