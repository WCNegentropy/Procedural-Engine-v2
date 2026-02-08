#include "game_manager.h"

namespace game_manager {

GameManager::GameManager(uint64_t seed, int worker_count)
    : seed_(seed), chunk_size_(64)
{
    base_terrain_config_.octaves = 6;
    base_terrain_config_.macro_points = 8;
    base_terrain_config_.erosion_iters = 0;
    base_terrain_config_.compute_slope = true;

    if (worker_count <= 0)
        worker_count = std::max(1, (int)std::thread::hardware_concurrency() - 1);

    for (int i = 0; i < worker_count; ++i)
        workers_.emplace_back(&GameManager::worker_loop, this);
}

GameManager::~GameManager() {
    shutdown_ = true;
    queue_cv_.notify_all();
    for (auto& w : workers_)
        if (w.joinable()) w.join();
}

void GameManager::worker_loop() {
    while (!shutdown_) {
        WorkItem item;
        {
            std::unique_lock<std::mutex> lock(queue_mutex_);
            queue_cv_.wait(lock, [&]{ return shutdown_.load() || !work_queue_.empty(); });
            if (shutdown_) return;
            item = work_queue_.front();
            work_queue_.pop();
        }
        // Each worker gets its own SeedRegistry from the global seed
        // combined with chunk coordinates for determinism
        uint64_t chunk_seed = seed_ ^ ((uint64_t)(unsigned int)item.coord.x * 73856093ULL)
                                    ^ ((uint64_t)(unsigned int)item.coord.z * 19349669ULL);
        SeedRegistry reg(chunk_seed);

        terrain::TerrainConfig cfg = base_terrain_config_;
        cfg.size = chunk_size_;
        cfg.offset_x = item.offset_x;
        cfg.offset_z = item.offset_z;

        auto maps = terrain::generate_terrain_maps(reg, cfg);

        {
            std::lock_guard<std::mutex> lock(results_mutex_);
            ready_results_.push_back({item.coord, std::move(maps)});
        }
        {
            std::lock_guard<std::mutex> lock(registry_mutex_);
            chunk_registry_[item.coord] = ChunkState::Ready;
        }
    }
}

void GameManager::enqueue_generation(ChunkCoord coord, float offset_x, float offset_z) {
    {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        work_queue_.push({coord, offset_x, offset_z});
    }
    queue_cv_.notify_one();
}

FrameDirective GameManager::sync_frame(float dt, float player_x, float player_z,
                                        int render_distance, int sim_distance,
                                        int chunk_size)
{
    chunk_size_ = chunk_size;

    // 1. Record frame time
    float frame_ms = dt * 1000.0f;
    frame_times_[frame_idx_ % HISTORY_SIZE] = frame_ms;
    frame_idx_++;

    // 2. Calculate rolling average
    size_t count = std::min(frame_idx_, HISTORY_SIZE);
    float sum = 0, worst = 0;
    for (size_t i = 0; i < count; ++i) {
        sum += frame_times_[i];
        worst = std::max(worst, frame_times_[i]);
    }
    float avg_ms = sum / (float)count;

    // 3. Calculate player chunk position
    int pcx = (int)std::floor(player_x / chunk_size);
    int pcz = (int)std::floor(player_z / chunk_size);

    // 4. Determine chunks to generate (not already in registry)
    int rd = render_distance;
    int rd_sq = rd * rd;
    {
        std::lock_guard<std::mutex> lock(registry_mutex_);
        for (int dx = -rd; dx <= rd; ++dx) {
            for (int dz = -rd; dz <= rd; ++dz) {
                if (dx*dx + dz*dz > rd_sq) continue;
                ChunkCoord c{pcx + dx, pcz + dz};
                if (chunk_registry_.find(c) == chunk_registry_.end()) {
                    chunk_registry_[c] = ChunkState::Queued;
                    float ox = c.x * (float)chunk_size;
                    float oz = c.z * (float)chunk_size;
                    enqueue_generation(c, ox, oz);
                }
            }
        }
    }

    // 5. Build FrameDirective based on pressure
    FrameDirective dir;
    float pressure = avg_ms / frame_budget_ms_;  // >1.0 = over budget

    if (pressure < 0.7f) {
        // Plenty of headroom
        dir.max_chunk_loads = 3;
        dir.lod_bias = 0.0f;
        dir.skip_physics_step = false;
        dir.recommended_render_distance = render_distance;
        dir.recommended_sim_distance = sim_distance;
        dir.recommended_erosion_iters = (float)base_terrain_config_.erosion_iters;
    } else if (pressure < 1.0f) {
        // Moderate load
        dir.max_chunk_loads = 1;
        dir.lod_bias = 0.0f;
        dir.skip_physics_step = false;
        dir.recommended_render_distance = render_distance;
        dir.recommended_sim_distance = sim_distance;
        dir.recommended_erosion_iters = (float)base_terrain_config_.erosion_iters;
    } else {
        // Over budget — shed load
        dir.max_chunk_loads = 0;
        dir.lod_bias = std::min(1.0f, (pressure - 1.0f) * 2.0f);
        dir.skip_physics_step = (pressure > 1.5f);
        dir.recommended_render_distance = std::max(2, render_distance - 1);
        dir.recommended_sim_distance = std::max(1, sim_distance - 1);
        dir.recommended_erosion_iters = 0;
    }

    return dir;
}

std::vector<ChunkResult> GameManager::collect_ready_chunks(int max_count) {
    std::lock_guard<std::mutex> lock(results_mutex_);
    std::vector<ChunkResult> out;
    int n = std::min(max_count, (int)ready_results_.size());
    if (n > 0) {
        out.assign(
            std::make_move_iterator(ready_results_.begin()),
            std::make_move_iterator(ready_results_.begin() + n)
        );
        ready_results_.erase(ready_results_.begin(), ready_results_.begin() + n);
    }
    return out;
}

PerformanceMetrics GameManager::get_metrics() const {
    PerformanceMetrics pm{};
    size_t count = std::min(frame_idx_, HISTORY_SIZE);
    float sum = 0, worst = 0;
    for (size_t i = 0; i < count; ++i) {
        sum += frame_times_[i];
        worst = std::max(worst, frame_times_[i]);
    }
    pm.avg_frame_ms = count > 0 ? sum / (float)count : 0.0f;
    pm.worst_frame_ms = worst;

    // Note: these counts are approximate (no lock in const method)
    pm.active_chunks = 0;
    pm.queued_chunks = 0;
    pm.ready_chunks = 0;
    pm.worker_threads_active = (int)workers_.size();
    pm.gpu_upload_budget_ms = 0.0f;
    return pm;
}

void GameManager::set_frame_budget_ms(float budget) {
    frame_budget_ms_ = budget;
}

void GameManager::set_terrain_config(uint32_t octaves, uint32_t macro_points,
                                      uint32_t erosion_iters, bool compute_slope) {
    base_terrain_config_.octaves = octaves;
    base_terrain_config_.macro_points = macro_points;
    base_terrain_config_.erosion_iters = erosion_iters;
    base_terrain_config_.compute_slope = compute_slope;
}

void GameManager::mark_chunk_uploaded(ChunkCoord coord) {
    std::lock_guard<std::mutex> lock(registry_mutex_);
    auto it = chunk_registry_.find(coord);
    if (it != chunk_registry_.end()) {
        it->second = ChunkState::Uploaded;
    }
}

std::vector<ChunkCoord> GameManager::get_chunks_to_unload(
    int pcx, int pcz, int unload_radius)
{
    int ur_sq = unload_radius * unload_radius;
    std::vector<ChunkCoord> result;
    std::lock_guard<std::mutex> lock(registry_mutex_);
    for (auto it = chunk_registry_.begin(); it != chunk_registry_.end(); ) {
        int dx = it->first.x - pcx;
        int dz = it->first.z - pcz;
        if (dx*dx + dz*dz > ur_sq && it->second == ChunkState::Uploaded) {
            result.push_back(it->first);
            it = chunk_registry_.erase(it);
        } else {
            ++it;
        }
    }
    return result;
}

} // namespace game_manager
