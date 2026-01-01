#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <openssl/sha.h>
#include <vector>
#include <string>
#include "seed_registry.h"
#include "terrain.h"

namespace py = pybind11;

static std::array<uint8_t,32> sha256_bytes(const void* data, size_t len) {
    std::array<uint8_t,32> out;
    SHA256_CTX ctx;
    SHA256_Init(&ctx);
    SHA256_Update(&ctx, data, len);
    SHA256_Final(out.data(), &ctx);
    return out;
}

static py::bytes digest_to_bytes(const std::array<uint8_t,32>& d) {
    return py::bytes(reinterpret_cast<const char*>(d.data()), d.size());
}

class Engine {
public:
    explicit Engine(uint64_t root_seed) : registry_(root_seed), root_(root_seed), frame_(0) {}

    void enqueue_heightmap(py::buffer h16, py::buffer biome8, py::buffer river1) {
        auto h = h16.request();
        auto b = biome8.request();
        auto r = river1.request();
        h_hash_ = sha256_bytes(h.ptr, h.size * h.itemsize);
        b_hash_ = sha256_bytes(b.ptr, b.size * b.itemsize);
        r_hash_ = sha256_bytes(r.ptr, r.size * r.itemsize);
    }

    void enqueue_prop_descriptor(py::list descriptors) {
        descriptor_hashes_.clear();
        py::module json = py::module::import("json");
        for (auto item : descriptors) {
            std::string dumped = json.attr("dumps")(item, py::arg("sort_keys")=true).cast<std::string>();
            descriptor_hashes_.push_back(sha256_bytes(dumped.data(), dumped.size()));
        }
    }

    void hot_reload(uint64_t descriptor_hash) {
        last_hot_reload_ = descriptor_hash;
    }

    void step(double dt) {
        frame_ += 1;
    }

    void reset() {
        frame_ = 0;
    }

    py::bytes snapshot_state(uint32_t frame) {
        uint64_t data[2] = {root_, frame + frame_};
        auto digest = sha256_bytes(data, sizeof(data));
        return digest_to_bytes(digest);
    }

    /**
     * Generate terrain maps using C++ implementation.
     * Returns a tuple of (height, biome, river) or (height, biome, river, slope) numpy arrays.
     */
    py::tuple generate_terrain(uint32_t size = 64, uint32_t octaves = 6,
                               uint32_t macro_points = 8, uint32_t erosion_iters = 0,
                               bool return_slope = false) {
        // Create a child registry for terrain generation
        uint64_t terrain_seed = registry_.get_subseed();
        SeedRegistry terrain_reg(terrain_seed);

        terrain::TerrainConfig config;
        config.size = size;
        config.octaves = octaves;
        config.macro_points = macro_points;
        config.erosion_iters = erosion_iters;
        config.compute_slope = return_slope;

        auto maps = terrain::generate_terrain_maps(terrain_reg, config);

        // Convert to numpy arrays
        auto height = py::array_t<float>({size, size});
        auto biome = py::array_t<uint8_t>({size, size});
        auto river = py::array_t<uint8_t>({size, size});

        std::memcpy(height.mutable_data(), maps.height.data(), maps.height.size() * sizeof(float));
        std::memcpy(biome.mutable_data(), maps.biome.data(), maps.biome.size() * sizeof(uint8_t));
        std::memcpy(river.mutable_data(), maps.river.data(), maps.river.size() * sizeof(uint8_t));

        if (return_slope) {
            auto slope = py::array_t<float>({size, size});
            std::memcpy(slope.mutable_data(), maps.slope.data(), maps.slope.size() * sizeof(float));
            return py::make_tuple(height, biome, river, slope);
        }

        return py::make_tuple(height, biome, river);
    }

private:
    SeedRegistry registry_;
    uint64_t root_;
    uint64_t frame_;
    uint64_t last_hot_reload_ = 0;
    std::array<uint8_t,32> h_hash_{};
    std::array<uint8_t,32> b_hash_{};
    std::array<uint8_t,32> r_hash_{};
    std::vector<std::array<uint8_t,32>> descriptor_hashes_;
};

PYBIND11_MODULE(procengine_cpp, m) {
    py::class_<SeedRegistry>(m, "SeedRegistry")
        .def(py::init<uint64_t>())
        .def("get_subseed", &SeedRegistry::get_subseed)
        .def("next_u64", &SeedRegistry::next_u64);

    py::class_<Engine>(m, "Engine")
        .def(py::init<uint64_t>())
        .def("enqueue_heightmap", &Engine::enqueue_heightmap)
        .def("enqueue_prop_descriptor", &Engine::enqueue_prop_descriptor)
        .def("hot_reload", &Engine::hot_reload)
        .def("step", &Engine::step)
        .def("reset", &Engine::reset)
        .def("snapshot_state", &Engine::snapshot_state)
        .def("generate_terrain", &Engine::generate_terrain,
             py::arg("size") = 64,
             py::arg("octaves") = 6,
             py::arg("macro_points") = 8,
             py::arg("erosion_iters") = 0,
             py::arg("return_slope") = false,
             "Generate terrain maps (height, biome, river, [slope])");

    // Standalone terrain generation function for testing
    m.def("generate_terrain_standalone", [](uint64_t seed, uint32_t size, uint32_t octaves,
                                             uint32_t macro_points, uint32_t erosion_iters,
                                             bool return_slope) {
        SeedRegistry reg(seed);
        terrain::TerrainConfig config;
        config.size = size;
        config.octaves = octaves;
        config.macro_points = macro_points;
        config.erosion_iters = erosion_iters;
        config.compute_slope = return_slope;

        auto maps = terrain::generate_terrain_maps(reg, config);

        auto height = py::array_t<float>({size, size});
        auto biome = py::array_t<uint8_t>({size, size});
        auto river = py::array_t<uint8_t>({size, size});

        std::memcpy(height.mutable_data(), maps.height.data(), maps.height.size() * sizeof(float));
        std::memcpy(biome.mutable_data(), maps.biome.data(), maps.biome.size() * sizeof(uint8_t));
        std::memcpy(river.mutable_data(), maps.river.data(), maps.river.size() * sizeof(uint8_t));

        if (return_slope) {
            auto slope = py::array_t<float>({size, size});
            std::memcpy(slope.mutable_data(), maps.slope.data(), maps.slope.size() * sizeof(float));
            return py::make_tuple(height, biome, river, slope);
        }

        return py::make_tuple(height, biome, river);
    },
    py::arg("seed"),
    py::arg("size") = 64,
    py::arg("octaves") = 6,
    py::arg("macro_points") = 8,
    py::arg("erosion_iters") = 0,
    py::arg("return_slope") = false,
    "Generate terrain maps from a seed (standalone function for testing)");
}
