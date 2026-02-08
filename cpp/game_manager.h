#pragma once

#include <cstdint>
#include <vector>
#include <map>
#include <queue>
#include <mutex>
#include <thread>
#include <atomic>
#include <functional>
#include <chrono>
#include <array>
#include <condition_variable>
#include <algorithm>
#include <cmath>
#include "seed_registry.h"
#include "terrain.h"

namespace game_manager {

struct ChunkCoord {
    int x, z;
    bool operator<(const ChunkCoord& o) const {
        return x < o.x || (x == o.x && z < o.z);
    }
    bool operator==(const ChunkCoord& o) const { return x == o.x && z == o.z; }
};

enum class ChunkState : uint8_t {
    Queued, Generating, Ready, Uploaded, MarkedUnload
};

struct ChunkResult {
    ChunkCoord coord;
    terrain::TerrainMaps maps;
};

struct FrameDirective {
    int max_chunk_loads;            // How many chunks Python should upload this frame
    float lod_bias;                 // 0.0 = full detail, 1.0 = lowest
    bool skip_physics_step;         // True if frame budget exhausted
    int recommended_render_distance;
    int recommended_sim_distance;
    float recommended_erosion_iters; // 0 = skip erosion during pressure
};

struct PerformanceMetrics {
    float avg_frame_ms;
    float worst_frame_ms;
    int active_chunks;
    int queued_chunks;
    int ready_chunks;
    int worker_threads_active;
    float gpu_upload_budget_ms;
};

class GameManager {
public:
    explicit GameManager(uint64_t seed, int worker_count = 0);
    ~GameManager();

    // === Per-Frame Sync (called from Python every frame) ===
    FrameDirective sync_frame(float dt, float player_x, float player_z,
                              int render_distance, int sim_distance,
                              int chunk_size);

    // === Async Chunk Results ===
    std::vector<ChunkResult> collect_ready_chunks(int max_count);

    // === Performance Monitoring ===
    PerformanceMetrics get_metrics() const;

    // === Configuration ===
    void set_frame_budget_ms(float budget);
    void set_terrain_config(uint32_t octaves, uint32_t macro_points,
                            uint32_t erosion_iters, bool compute_slope);

    // === Chunk Lifecycle ===
    void mark_chunk_uploaded(ChunkCoord coord);
    std::vector<ChunkCoord> get_chunks_to_unload(int pcx, int pcz,
                                                  int unload_radius);

private:
    void worker_loop();
    void enqueue_generation(ChunkCoord coord, float offset_x, float offset_z);

    uint64_t seed_;
    int chunk_size_;
    terrain::TerrainConfig base_terrain_config_;

    // Thread pool
    std::vector<std::thread> workers_;
    std::atomic<bool> shutdown_{false};

    // Work queue (protected by mutex)
    struct WorkItem {
        ChunkCoord coord;
        float offset_x, offset_z;
    };
    std::queue<WorkItem> work_queue_;
    std::mutex queue_mutex_;
    std::condition_variable queue_cv_;

    // Results queue (protected by mutex)
    std::vector<ChunkResult> ready_results_;
    std::mutex results_mutex_;

    // Chunk registry
    std::map<ChunkCoord, ChunkState> chunk_registry_;
    std::mutex registry_mutex_;

    // Performance tracking
    static constexpr size_t HISTORY_SIZE = 120;
    std::array<float, HISTORY_SIZE> frame_times_{};
    size_t frame_idx_ = 0;
    float frame_budget_ms_ = 13.0f; // conservative for 16.6ms target
};

} // namespace game_manager
