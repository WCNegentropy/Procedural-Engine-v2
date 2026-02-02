#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <openssl/sha.h>
#include <vector>
#include <string>
#include <unordered_map>
#include <memory>
#include "seed_registry.h"
#include "terrain.h"
#include "physics.h"
#include "props.h"
#include "materials.h"
#ifndef NO_GRAPHICS
#include "graphics.h"
#include "imgui.h"
#include "imgui_impl_vulkan.h"
#include "imgui_impl_sdl2.h"
#endif

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

struct CachedResource {
    uint64_t hash = 0;
    std::string descriptor_json;
    uint64_t last_access_frame = 0;
    bool dirty = false;
};

class Engine {
public:
    explicit Engine(uint64_t root_seed) : registry_(root_seed), root_(root_seed), frame_(0) {
        shader_cache_ = std::make_unique<materials::ShaderCache>();
    }

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
        cached_descriptors_.clear();
        py::module json = py::module::import("json");

        for (auto item : descriptors) {
            std::string dumped = json.attr("dumps")(item, py::arg("sort_keys")=true).cast<std::string>();
            auto hash_bytes = sha256_bytes(dumped.data(), dumped.size());
            descriptor_hashes_.push_back(hash_bytes);

            // Convert hash bytes to uint64 for easier lookup
            uint64_t hash_val = 0;
            std::memcpy(&hash_val, hash_bytes.data(), sizeof(uint64_t));

            // Cache the descriptor
            CachedResource resource;
            resource.hash = hash_val;
            resource.descriptor_json = dumped;
            resource.last_access_frame = frame_;
            resource.dirty = false;

            cached_descriptors_[hash_val] = resource;
        }
    }

    void hot_reload(uint64_t descriptor_hash) {
        last_hot_reload_ = descriptor_hash;
        hot_reload_queue_.push_back(descriptor_hash);

        // Mark resource as dirty if it exists in cache
        auto it = cached_descriptors_.find(descriptor_hash);
        if (it != cached_descriptors_.end()) {
            it->second.dirty = true;
        }
    }

    void step(double dt) {
        frame_ += 1;

        // Process hot-reload queue
        if (!hot_reload_queue_.empty()) {
            for (uint64_t hash : hot_reload_queue_) {
                rebuild_resource(hash);
            }
            hot_reload_queue_.clear();
        }
    }

    void reset() {
        frame_ = 0;
        hot_reload_queue_.clear();
        cached_descriptors_.clear();
        if (shader_cache_) {
            shader_cache_->clear();
        }
    }

    py::bytes snapshot_state(uint32_t frame) {
        uint64_t data[2] = {root_, frame + frame_};
        auto digest = sha256_bytes(data, sizeof(data));
        return digest_to_bytes(digest);
    }

    /**
     * Rebuild a resource identified by its descriptor hash.
     * This simulates the hot-reload process for materials, meshes, etc.
     */
    void rebuild_resource(uint64_t descriptor_hash) {
        auto it = cached_descriptors_.find(descriptor_hash);
        if (it != cached_descriptors_.end()) {
            it->second.last_access_frame = frame_;
            it->second.dirty = false;
            // Resource has been "rebuilt" - in a full implementation, this would:
            // 1. Parse the descriptor JSON
            // 2. Generate/compile the resource (shader, mesh, etc.)
            // 3. Upload to GPU
            // 4. Swap handles in the scene graph/ECS
        }
    }

    /**
     * Get the number of cached resources.
     */
    size_t get_cached_resource_count() const {
        return cached_descriptors_.size();
    }

    /**
     * Check if a resource needs rebuilding.
     */
    bool is_resource_dirty(uint64_t descriptor_hash) const {
        auto it = cached_descriptors_.find(descriptor_hash);
        return it != cached_descriptors_.end() && it->second.dirty;
    }

    /**
     * Get shader cache for material hot-reloading.
     */
    materials::ShaderCache* get_shader_cache() {
        return shader_cache_.get();
    }

    /**
     * Generate terrain maps using C++ implementation.
     * Returns a tuple of (height, biome, river) or (height, biome, river, slope) numpy arrays.
     */
    py::tuple generate_terrain(uint32_t size = 64, uint32_t octaves = 6,
                               uint32_t macro_points = 8, uint32_t erosion_iters = 0,
                               bool return_slope = false) {
        // Create a child registry for terrain generation using named subseed
        uint64_t terrain_seed = registry_.get_subseed("terrain");
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

    // Hot-reload infrastructure
    std::unordered_map<uint64_t, CachedResource> cached_descriptors_;
    std::vector<uint64_t> hot_reload_queue_;
    std::unique_ptr<materials::ShaderCache> shader_cache_;
};

PYBIND11_MODULE(procengine_cpp, m) {
    py::class_<SeedRegistry>(m, "SeedRegistry")
        .def(py::init<uint64_t>())
        .def("get_subseed", &SeedRegistry::get_subseed,
             py::arg("name"),
             "Get a deterministic sub-seed for a named subsystem")
        .def("get_subseed_sequential", &SeedRegistry::get_subseed_sequential,
             "Get a sequential sub-seed (legacy API)")
        .def("next_u64", &SeedRegistry::next_u64)
        .def("root_seed", &SeedRegistry::root_seed);

    py::class_<Engine>(m, "Engine")
        .def(py::init<uint64_t>())
        .def("enqueue_heightmap", &Engine::enqueue_heightmap)
        .def("enqueue_prop_descriptor", &Engine::enqueue_prop_descriptor)
        .def("hot_reload", &Engine::hot_reload,
             "Queue a descriptor for hot-reloading by hash")
        .def("step", &Engine::step)
        .def("reset", &Engine::reset)
        .def("snapshot_state", &Engine::snapshot_state)
        .def("rebuild_resource", &Engine::rebuild_resource,
             "Rebuild a resource identified by its descriptor hash")
        .def("get_cached_resource_count", &Engine::get_cached_resource_count,
             "Get the number of cached resources")
        .def("is_resource_dirty", &Engine::is_resource_dirty,
             "Check if a resource needs rebuilding")
        .def("get_shader_cache", &Engine::get_shader_cache,
             py::return_value_policy::reference_internal,
             "Get the shader cache for material hot-reloading")
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

    // Physics bindings
    py::class_<physics::Vec2>(m, "Vec2")
        .def(py::init<>())
        .def(py::init<float, float>())
        .def_readwrite("x", &physics::Vec2::x)
        .def_readwrite("y", &physics::Vec2::y)
        .def("length", &physics::Vec2::length)
        .def("dot", &physics::Vec2::dot)
        .def("__repr__", [](const physics::Vec2& v) {
            return "Vec2(" + std::to_string(v.x) + ", " + std::to_string(v.y) + ")";
        });

    py::class_<physics::RigidBody>(m, "RigidBody")
        .def(py::init<>())
        .def(py::init<physics::Vec2, physics::Vec2, float, float>(),
             py::arg("position"), py::arg("velocity"), py::arg("mass"), py::arg("radius"))
        .def_readwrite("position", &physics::RigidBody::position)
        .def_readwrite("velocity", &physics::RigidBody::velocity)
        .def_readwrite("mass", &physics::RigidBody::mass)
        .def_readwrite("radius", &physics::RigidBody::radius);

    py::class_<physics::HeightField>(m, "HeightField")
        .def(py::init<>())
        .def(py::init<const std::vector<float>&, float, float>(),
             py::arg("heights"), py::arg("x0") = 0.0f, py::arg("cell_size") = 1.0f)
        .def("sample", &physics::HeightField::sample,
             "Sample height at x with linear interpolation")
        .def("in_bounds", &physics::HeightField::in_bounds,
             "Check if x is within heightfield bounds")
        .def("x_min", &physics::HeightField::x_min,
             "Get minimum x coordinate")
        .def("x_max", &physics::HeightField::x_max,
             "Get maximum x coordinate")
        .def("empty", &physics::HeightField::empty);

    py::class_<physics::PhysicsConfig>(m, "PhysicsConfig")
        .def(py::init<>())
        .def_readwrite("dt", &physics::PhysicsConfig::dt)
        .def_readwrite("iterations", &physics::PhysicsConfig::iterations)
        .def_readwrite("restitution", &physics::PhysicsConfig::restitution)
        .def_readwrite("cell_size", &physics::PhysicsConfig::cell_size)
        .def_readwrite("gravity", &physics::PhysicsConfig::gravity)
        .def_readwrite("damping", &physics::PhysicsConfig::damping);

    py::class_<physics::PhysicsWorld>(m, "PhysicsWorld")
        .def(py::init<>())
        .def("add_body", &physics::PhysicsWorld::add_body)
        .def("get_body", py::overload_cast<size_t>(&physics::PhysicsWorld::get_body),
             py::return_value_policy::reference_internal)
        .def("step", &physics::PhysicsWorld::step,
             py::arg("config") = physics::PhysicsConfig())
        .def("reset", &physics::PhysicsWorld::reset)
        .def("body_count", &physics::PhysicsWorld::body_count)
        .def("set_heightfield", &physics::PhysicsWorld::set_heightfield)
        .def("clear_heightfield", &physics::PhysicsWorld::clear_heightfield);

    // ========================================================================
    // 3D Physics bindings
    // ========================================================================

    py::class_<physics::Vec3>(m, "PhysicsVec3")
        .def(py::init<>())
        .def(py::init<float, float, float>())
        .def_readwrite("x", &physics::Vec3::x)
        .def_readwrite("y", &physics::Vec3::y)
        .def_readwrite("z", &physics::Vec3::z)
        .def("length", &physics::Vec3::length)
        .def("length_squared", &physics::Vec3::length_squared)
        .def("dot", &physics::Vec3::dot)
        .def("cross", &physics::Vec3::cross)
        .def("normalized", &physics::Vec3::normalized)
        .def("xz", &physics::Vec3::xz, "Project to XZ plane as Vec2")
        .def("__add__", [](const physics::Vec3& a, const physics::Vec3& b) { return a + b; })
        .def("__sub__", [](const physics::Vec3& a, const physics::Vec3& b) { return a - b; })
        .def("__mul__", [](const physics::Vec3& v, float s) { return v * s; })
        .def("__rmul__", [](const physics::Vec3& v, float s) { return v * s; })
        .def("__truediv__", [](const physics::Vec3& v, float s) { return v / s; })
        .def("__neg__", [](const physics::Vec3& v) { return -v; })
        .def("__eq__", [](const physics::Vec3& a, const physics::Vec3& b) { return a == b; })
        .def("__repr__", [](const physics::Vec3& v) {
            return "PhysicsVec3(" + std::to_string(v.x) + ", " +
                   std::to_string(v.y) + ", " + std::to_string(v.z) + ")";
        });

    py::class_<physics::RigidBody3D>(m, "RigidBody3D")
        .def(py::init<>())
        .def(py::init<physics::Vec3, physics::Vec3, float, float>(),
             py::arg("position"), py::arg("velocity"), py::arg("mass"), py::arg("radius"))
        .def_readwrite("position", &physics::RigidBody3D::position)
        .def_readwrite("velocity", &physics::RigidBody3D::velocity)
        .def_readwrite("mass", &physics::RigidBody3D::mass)
        .def_readwrite("radius", &physics::RigidBody3D::radius)
        .def_readwrite("grounded", &physics::RigidBody3D::grounded)
        .def("inv_mass", &physics::RigidBody3D::inv_mass)
        .def("to_2d", &physics::RigidBody3D::to_2d, "Project to 2D RigidBody on XZ plane");

    py::class_<physics::HeightField2D>(m, "HeightField2D")
        .def(py::init<>())
        .def(py::init<const std::vector<float>&, size_t, size_t, float, float, float>(),
             py::arg("heights"), py::arg("size_x"), py::arg("size_z"),
             py::arg("x0") = 0.0f, py::arg("z0") = 0.0f, py::arg("cell_size") = 1.0f)
        .def("sample", &physics::HeightField2D::sample,
             py::arg("x"), py::arg("z"),
             "Sample height at (x, z) with bilinear interpolation")
        .def("in_bounds", &physics::HeightField2D::in_bounds,
             "Check if (x, z) is within bounds")
        .def("empty", &physics::HeightField2D::empty)
        .def("size_x", &physics::HeightField2D::size_x)
        .def("size_z", &physics::HeightField2D::size_z);

    py::class_<physics::PhysicsConfig3D>(m, "PhysicsConfig3D")
        .def(py::init<>())
        .def_readwrite("dt", &physics::PhysicsConfig3D::dt)
        .def_readwrite("iterations", &physics::PhysicsConfig3D::iterations)
        .def_readwrite("restitution", &physics::PhysicsConfig3D::restitution)
        .def_readwrite("cell_size", &physics::PhysicsConfig3D::cell_size)
        .def_readwrite("gravity", &physics::PhysicsConfig3D::gravity)
        .def_readwrite("damping", &physics::PhysicsConfig3D::damping);

    py::class_<physics::PhysicsWorld3D>(m, "PhysicsWorld3D")
        .def(py::init<>())
        .def("add_body", &physics::PhysicsWorld3D::add_body)
        .def("get_body", py::overload_cast<size_t>(&physics::PhysicsWorld3D::get_body),
             py::return_value_policy::reference_internal)
        .def("step", &physics::PhysicsWorld3D::step,
             py::arg("config") = physics::PhysicsConfig3D())
        .def("reset", &physics::PhysicsWorld3D::reset)
        .def("body_count", &physics::PhysicsWorld3D::body_count)
        .def("set_heightfield", &physics::PhysicsWorld3D::set_heightfield)
        .def("clear_heightfield", &physics::PhysicsWorld3D::clear_heightfield);

    // Standalone 3D physics step function for testing
    m.def("step_physics_3d", [](py::list body_list, float dt, uint32_t iterations,
                                 float restitution, float cell_size, float gravity,
                                 float damping, py::object heightfield_obj) {
        // Convert Python list to C++ vector
        std::vector<physics::RigidBody3D> bodies;
        for (auto item : body_list) {
            auto body = item.cast<physics::RigidBody3D>();
            bodies.push_back(body);
        }

        physics::PhysicsConfig3D config;
        config.dt = dt;
        config.iterations = iterations;
        config.restitution = restitution;
        config.cell_size = cell_size;
        config.gravity = gravity;
        config.damping = damping;

        const physics::HeightField2D* hf = nullptr;
        physics::HeightField2D hf_storage;
        if (!heightfield_obj.is_none()) {
            hf_storage = heightfield_obj.cast<physics::HeightField2D>();
            hf = &hf_storage;
        }

        physics::step_physics_3d(bodies, config, hf);

        // Update the original list with new positions/velocities/grounded state
        for (size_t i = 0; i < bodies.size(); ++i) {
            body_list[i].attr("position") = py::cast(bodies[i].position);
            body_list[i].attr("velocity") = py::cast(bodies[i].velocity);
            body_list[i].attr("grounded") = py::cast(bodies[i].grounded);
        }
    },
    py::arg("bodies"),
    py::arg("dt") = physics::DEFAULT_DT,
    py::arg("iterations") = 10,
    py::arg("restitution") = 0.5f,
    py::arg("cell_size") = 0.0f,
    py::arg("gravity") = -9.8f,
    py::arg("damping") = 0.0f,
    py::arg("heightfield") = py::none(),
    "Step 3D physics simulation using hybrid 2D+height approach (modifies bodies in-place)");

    // Standalone physics step function for testing
    m.def("step_physics", [](py::list body_list, float dt, uint32_t iterations,
                              float restitution, float cell_size, float gravity,
                              float damping, py::object heightfield_obj) {
        // Convert Python list to C++ vector
        std::vector<physics::RigidBody> bodies;
        for (auto item : body_list) {
            auto body = item.cast<physics::RigidBody>();
            bodies.push_back(body);
        }

        physics::PhysicsConfig config;
        config.dt = dt;
        config.iterations = iterations;
        config.restitution = restitution;
        config.cell_size = cell_size;
        config.gravity = gravity;
        config.damping = damping;

        const physics::HeightField* hf = nullptr;
        physics::HeightField hf_storage;
        if (!heightfield_obj.is_none()) {
            hf_storage = heightfield_obj.cast<physics::HeightField>();
            hf = &hf_storage;
        }

        physics::step_physics(bodies, config, hf);

        // Update the original list with new positions/velocities
        // Create new Vec2 objects for proper type conversion
        for (size_t i = 0; i < bodies.size(); ++i) {
            physics::Vec2 new_pos = bodies[i].position;
            physics::Vec2 new_vel = bodies[i].velocity;
            body_list[i].attr("position") = py::cast(new_pos);
            body_list[i].attr("velocity") = py::cast(new_vel);
        }
    },
    py::arg("bodies"),
    py::arg("dt") = physics::DEFAULT_DT,
    py::arg("iterations") = 10,
    py::arg("restitution") = 1.0f,
    py::arg("cell_size") = 0.0f,
    py::arg("gravity") = 0.0f,
    py::arg("damping") = 0.0f,
    py::arg("heightfield") = py::none(),
    "Step physics simulation (modifies bodies in-place)");

    // Props bindings
    py::class_<props::Vec3>(m, "Vec3")
        .def(py::init<>())
        .def(py::init<float, float, float>())
        .def_readwrite("x", &props::Vec3::x)
        .def_readwrite("y", &props::Vec3::y)
        .def_readwrite("z", &props::Vec3::z)
        .def("length", &props::Vec3::length)
        .def("dot", &props::Vec3::dot)
        .def("cross", &props::Vec3::cross)
        .def("normalized", &props::Vec3::normalized)
        .def("__repr__", [](const props::Vec3& v) {
            return "Vec3(" + std::to_string(v.x) + ", " +
                   std::to_string(v.y) + ", " + std::to_string(v.z) + ")";
        });

    py::class_<props::Mesh>(m, "Mesh")
        .def(py::init<>())
        .def_readonly("vertices", &props::Mesh::vertices)
        .def_readonly("normals", &props::Mesh::normals)
        .def_readonly("colors", &props::Mesh::colors)
        .def_readonly("indices", &props::Mesh::indices)
        .def("vertex_count", &props::Mesh::vertex_count)
        .def("triangle_count", &props::Mesh::triangle_count)
        .def("clear", &props::Mesh::clear)
        .def("append", &props::Mesh::append)
        .def("validate", &props::Mesh::validate,
             "Validate mesh integrity (vertices/normals count, index bounds)")
        .def("ensure_normals", &props::Mesh::ensure_normals,
             "Ensure normals array matches vertices array size")
        .def("ensure_colors", &props::Mesh::ensure_colors,
             "Ensure colors array matches vertices array size")
        .def("set_uniform_color", &props::Mesh::set_uniform_color,
             py::arg("color"),
             "Set all vertex colors to a uniform color")
        .def("get_vertices_numpy", [](const props::Mesh& mesh) {
            auto arr = py::array_t<float>({mesh.vertices.size(), size_t(3)});
            auto ptr = arr.mutable_data();
            for (size_t i = 0; i < mesh.vertices.size(); ++i) {
                ptr[i * 3 + 0] = mesh.vertices[i].x;
                ptr[i * 3 + 1] = mesh.vertices[i].y;
                ptr[i * 3 + 2] = mesh.vertices[i].z;
            }
            return arr;
        })
        .def("get_normals_numpy", [](const props::Mesh& mesh) {
            auto arr = py::array_t<float>({mesh.normals.size(), size_t(3)});
            auto ptr = arr.mutable_data();
            for (size_t i = 0; i < mesh.normals.size(); ++i) {
                ptr[i * 3 + 0] = mesh.normals[i].x;
                ptr[i * 3 + 1] = mesh.normals[i].y;
                ptr[i * 3 + 2] = mesh.normals[i].z;
            }
            return arr;
        })
        .def("get_indices_numpy", [](const props::Mesh& mesh) {
            auto arr = py::array_t<uint32_t>(mesh.indices.size());
            std::memcpy(arr.mutable_data(), mesh.indices.data(),
                        mesh.indices.size() * sizeof(uint32_t));
            return arr;
        });

    // Rock mesh generation
    py::class_<props::RockDescriptor>(m, "RockDescriptor")
        .def(py::init<>())
        .def_readwrite("position", &props::RockDescriptor::position)
        .def_readwrite("radius", &props::RockDescriptor::radius)
        .def_readwrite("noise_seed", &props::RockDescriptor::noise_seed)
        .def_readwrite("noise_scale", &props::RockDescriptor::noise_scale);

    m.def("generate_rock_mesh", &props::generate_rock_mesh,
          py::arg("desc"),
          py::arg("segments") = 16,
          py::arg("rings") = 12,
          "Generate a noise-displaced sphere mesh for a rock");

    // Tree mesh generation
    py::class_<props::LSystemRules>(m, "LSystemRules")
        .def(py::init<>())
        .def_readwrite("axiom", &props::LSystemRules::axiom)
        .def_readwrite("rules", &props::LSystemRules::rules);

    py::class_<props::TreeDescriptor>(m, "TreeDescriptor")
        .def(py::init<>())
        .def_readwrite("lsystem", &props::TreeDescriptor::lsystem)
        .def_readwrite("angle", &props::TreeDescriptor::angle)
        .def_readwrite("iterations", &props::TreeDescriptor::iterations);

    py::class_<props::TreeSegment>(m, "TreeSegment")
        .def(py::init<>())
        .def_readwrite("start", &props::TreeSegment::start)
        .def_readwrite("end", &props::TreeSegment::end)
        .def_readwrite("start_radius", &props::TreeSegment::start_radius)
        .def_readwrite("end_radius", &props::TreeSegment::end_radius);

    m.def("evaluate_lsystem", &props::evaluate_lsystem,
          py::arg("rules"), py::arg("iterations"),
          "Evaluate L-system string after N iterations");

    m.def("generate_tree_skeleton", &props::generate_tree_skeleton,
          py::arg("lstring"), py::arg("angle"),
          py::arg("segment_length") = 1.0f,
          py::arg("base_radius") = 0.1f,
          py::arg("taper") = 0.85f,
          "Generate tree skeleton from L-system string");

    m.def("generate_tree_mesh", &props::generate_tree_mesh,
          py::arg("desc"),
          py::arg("segments_per_ring") = 8,
          "Generate tree mesh from descriptor");

    // Building mesh generation
    py::class_<props::BuildingBlock>(m, "BuildingBlock")
        .def(py::init<>())
        .def_readwrite("size", &props::BuildingBlock::size)
        .def_readwrite("position", &props::BuildingBlock::position)
        .def_readwrite("children", &props::BuildingBlock::children);

    py::class_<props::BuildingDescriptor>(m, "BuildingDescriptor")
        .def(py::init<>())
        .def_readwrite("root", &props::BuildingDescriptor::root);

    m.def("generate_building_mesh", &props::generate_building_mesh,
          py::arg("desc"),
          "Generate building mesh from BSP descriptor");

    // Creature mesh generation
    py::class_<props::Bone>(m, "Bone")
        .def(py::init<>())
        .def_readwrite("length", &props::Bone::length)
        .def_readwrite("angle", &props::Bone::angle);

    py::class_<props::Metaball>(m, "Metaball")
        .def(py::init<>())
        .def_readwrite("center", &props::Metaball::center)
        .def_readwrite("radius", &props::Metaball::radius)
        .def_readwrite("strength", &props::Metaball::strength);

    py::class_<props::CreatureDescriptor>(m, "CreatureDescriptor")
        .def(py::init<>())
        .def_readwrite("skeleton", &props::CreatureDescriptor::skeleton)
        .def_readwrite("metaballs", &props::CreatureDescriptor::metaballs);

    m.def("evaluate_metaball_field", &props::evaluate_metaball_field,
          py::arg("metaballs"), py::arg("point"),
          "Evaluate metaball field strength at a point");

    m.def("generate_creature_mesh", &props::generate_creature_mesh,
          py::arg("desc"),
          py::arg("grid_resolution") = 32,
          py::arg("threshold") = 1.0f,
          "Generate creature mesh using marching cubes");

    // LOD generation
    m.def("generate_lod", &props::generate_lod,
          py::arg("mesh"), py::arg("target_ratio"),
          "Generate simplified LOD version of mesh");

    // Primitive mesh generation
    m.def("generate_box_mesh", &props::generate_box_mesh,
          py::arg("size"),
          py::arg("center") = props::Vec3(0, 0, 0),
          "Generate an axis-aligned box mesh");

    m.def("generate_capsule_mesh", &props::generate_capsule_mesh,
          py::arg("radius"),
          py::arg("height"),
          py::arg("segments") = 16,
          py::arg("rings") = 8,
          "Generate a capsule mesh (cylinder with hemisphere caps)");

    m.def("generate_cylinder_mesh", &props::generate_cylinder_mesh,
          py::arg("radius"),
          py::arg("height"),
          py::arg("segments") = 16,
          "Generate a cylinder mesh");

    m.def("generate_cone_mesh", &props::generate_cone_mesh,
          py::arg("radius"),
          py::arg("height"),
          py::arg("segments") = 16,
          "Generate a cone mesh");

    m.def("generate_plane_mesh", &props::generate_plane_mesh,
          py::arg("size"),
          py::arg("subdivisions") = 1,
          "Generate a subdivided plane mesh");

    // Terrain mesh generation
    m.def("generate_terrain_mesh", [](py::array_t<float> heightmap_array,
                                       float cell_size,
                                       float height_scale) {
        auto buf = heightmap_array.request();
        if (buf.ndim != 2) {
            throw std::runtime_error("Heightmap must be a 2D array");
        }
        if (buf.shape[0] != buf.shape[1]) {
            throw std::runtime_error("Heightmap must be square");
        }

        uint32_t size = static_cast<uint32_t>(buf.shape[0]);
        std::vector<float> heightmap(size * size);
        std::memcpy(heightmap.data(), buf.ptr, heightmap.size() * sizeof(float));

        return terrain::generate_terrain_mesh(heightmap, size, cell_size, height_scale);
    },
    py::arg("heightmap"),
    py::arg("cell_size") = 1.0f,
    py::arg("height_scale") = 1.0f,
    "Generate terrain mesh from heightmap (2D numpy array)");

    // Generate terrain mesh with biome colors
    m.def("generate_terrain_mesh_with_biomes", 
        [](py::array_t<float> heightmap, py::array_t<uint8_t> biome_map, 
           float cell_size, float height_scale) {
            auto h_buf = heightmap.request();
            auto b_buf = biome_map.request();
            
            if (h_buf.ndim != 2 || b_buf.ndim != 2) {
                throw std::runtime_error("heightmap and biome_map must be 2D arrays");
            }
            
            uint32_t size = static_cast<uint32_t>(h_buf.shape[0]);
            
            std::vector<float> h_vec(static_cast<float*>(h_buf.ptr),
                                      static_cast<float*>(h_buf.ptr) + h_buf.size);
            std::vector<uint8_t> b_vec(static_cast<uint8_t*>(b_buf.ptr),
                                        static_cast<uint8_t*>(b_buf.ptr) + b_buf.size);
            
            return terrain::generate_terrain_mesh(h_vec, &b_vec, size, cell_size, height_scale);
        },
        py::arg("heightmap"),
        py::arg("biome_map"),
        py::arg("cell_size") = 1.0f,
        py::arg("height_scale") = 1.0f,
        "Generate terrain mesh with biome-based vertex colors"
    );

    // Helper function to create descriptors from Python dicts with error handling
    m.def("create_rock_from_dict", [](py::dict d) {
        props::RockDescriptor desc;
        try {
            if (!d.contains("position")) {
                throw std::runtime_error("Missing required key 'position'");
            }
            if (!d.contains("radius")) {
                throw std::runtime_error("Missing required key 'radius'");
            }
            auto pos = d["position"].cast<py::list>();
            if (py::len(pos) < 3) {
                throw std::runtime_error("'position' must have at least 3 elements");
            }
            desc.position = props::Vec3(
                pos[0].cast<float>(),
                pos[1].cast<float>(),
                pos[2].cast<float>()
            );
            desc.radius = d["radius"].cast<float>();
            if (d.contains("noise_seed")) {
                desc.noise_seed = d["noise_seed"].cast<uint32_t>();
            }
            if (d.contains("noise_scale")) {
                desc.noise_scale = d["noise_scale"].cast<float>();
            }
        } catch (const py::cast_error& e) {
            throw std::runtime_error(std::string("Type conversion error in create_rock_from_dict: ") + e.what());
        }
        return desc;
    }, "Create RockDescriptor from Python dict");

    m.def("create_tree_from_dict", [](py::dict d) {
        props::TreeDescriptor desc;
        try {
            if (!d.contains("axiom")) {
                throw std::runtime_error("Missing required key 'axiom'");
            }
            if (!d.contains("rules")) {
                throw std::runtime_error("Missing required key 'rules'");
            }
            if (!d.contains("angle")) {
                throw std::runtime_error("Missing required key 'angle'");
            }
            if (!d.contains("iterations")) {
                throw std::runtime_error("Missing required key 'iterations'");
            }
            desc.lsystem.axiom = d["axiom"].cast<std::string>();
            auto rules = d["rules"].cast<py::dict>();
            for (auto item : rules) {
                std::string key_str = item.first.cast<std::string>();
                if (key_str.empty()) {
                    throw std::runtime_error("Empty key in rules dictionary");
                }
                char key = key_str[0];
                desc.lsystem.rules[key] = item.second.cast<std::string>();
            }
            desc.angle = d["angle"].cast<float>();
            desc.iterations = d["iterations"].cast<uint32_t>();
        } catch (const py::cast_error& e) {
            throw std::runtime_error(std::string("Type conversion error in create_tree_from_dict: ") + e.what());
        }
        return desc;
    }, "Create TreeDescriptor from Python dict");

    m.def("create_creature_from_dict", [](py::dict d) {
        props::CreatureDescriptor desc;
        try {
            if (!d.contains("skeleton")) {
                throw std::runtime_error("Missing required key 'skeleton'");
            }
            if (!d.contains("metaballs")) {
                throw std::runtime_error("Missing required key 'metaballs'");
            }

            auto skeleton = d["skeleton"].cast<py::list>();
            for (size_t i = 0; i < py::len(skeleton); ++i) {
                auto b = skeleton[i].cast<py::dict>();
                if (!b.contains("length") || !b.contains("angle")) {
                    throw std::runtime_error("Bone at index " + std::to_string(i) + " missing 'length' or 'angle'");
                }
                props::Bone bone_data;
                bone_data.length = b["length"].cast<float>();
                bone_data.angle = b["angle"].cast<float>();
                desc.skeleton.push_back(bone_data);
            }

            auto metaballs = d["metaballs"].cast<py::list>();
            for (size_t i = 0; i < py::len(metaballs); ++i) {
                auto m_dict = metaballs[i].cast<py::dict>();
                if (!m_dict.contains("center") || !m_dict.contains("radius")) {
                    throw std::runtime_error("Metaball at index " + std::to_string(i) + " missing 'center' or 'radius'");
                }
                props::Metaball ball;
                auto center = m_dict["center"].cast<py::list>();
                if (py::len(center) < 3) {
                    throw std::runtime_error("Metaball 'center' at index " + std::to_string(i) + " must have at least 3 elements");
                }
                ball.center = props::Vec3(
                    center[0].cast<float>(),
                    center[1].cast<float>(),
                    center[2].cast<float>()
                );
                ball.radius = m_dict["radius"].cast<float>();
                desc.metaballs.push_back(ball);
            }
        } catch (const py::cast_error& e) {
            throw std::runtime_error(std::string("Type conversion error in create_creature_from_dict: ") + e.what());
        }
        return desc;
    }, "Create CreatureDescriptor from Python dict");

    // ========================================================================
    // Materials bindings
    // ========================================================================

    // Node types
    py::class_<materials::NoiseNode>(m, "NoiseNode")
        .def(py::init<>())
        .def_readwrite("seed", &materials::NoiseNode::seed)
        .def_readwrite("frequency", &materials::NoiseNode::frequency)
        .def_readwrite("octaves", &materials::NoiseNode::octaves)
        .def_readwrite("persistence", &materials::NoiseNode::persistence);

    py::class_<materials::WarpNode>(m, "WarpNode")
        .def(py::init<>())
        .def_readwrite("input", &materials::WarpNode::input)
        .def_readwrite("strength", &materials::WarpNode::strength);

    py::class_<materials::BlendNode>(m, "BlendNode")
        .def(py::init<>())
        .def_readwrite("input_a", &materials::BlendNode::input_a)
        .def_readwrite("input_b", &materials::BlendNode::input_b)
        .def_readwrite("factor", &materials::BlendNode::factor)
        .def_readwrite("blend_mode", &materials::BlendNode::blend_mode);

    py::class_<materials::PBRConstNode>(m, "PBRConstNode")
        .def(py::init<>())
        .def_readwrite("albedo", &materials::PBRConstNode::albedo)
        .def_readwrite("roughness", &materials::PBRConstNode::roughness)
        .def_readwrite("metallic", &materials::PBRConstNode::metallic);

    // Material graph
    py::class_<materials::MaterialNode>(m, "MaterialNode")
        .def(py::init<>())
        .def_readwrite("name", &materials::MaterialNode::name)
        .def_readwrite("type", &materials::MaterialNode::type);

    py::class_<materials::MaterialGraph>(m, "MaterialGraph")
        .def(py::init<>())
        .def_readwrite("output_node", &materials::MaterialGraph::output_node)
        .def_readonly("evaluation_order", &materials::MaterialGraph::evaluation_order);

    // Compiled shader
    py::class_<materials::CompiledShader>(m, "CompiledShader")
        .def(py::init<>())
        .def_readonly("vertex_source", &materials::CompiledShader::vertex_source)
        .def_readonly("fragment_source", &materials::CompiledShader::fragment_source)
        .def_readonly("hash", &materials::CompiledShader::hash)
        .def_readonly("valid", &materials::CompiledShader::valid)
        .def_readonly("error_message", &materials::CompiledShader::error_message);

    // Compiler options
    py::class_<materials::CompilerOptions>(m, "CompilerOptions")
        .def(py::init<>())
        .def_readwrite("include_noise_functions", &materials::CompilerOptions::include_noise_functions)
        .def_readwrite("include_pbr_lighting", &materials::CompilerOptions::include_pbr_lighting)
        .def_readwrite("optimize", &materials::CompilerOptions::optimize)
        .def_readwrite("glsl_version", &materials::CompilerOptions::glsl_version);

    // Material compiler
    py::class_<materials::MaterialCompiler>(m, "MaterialCompiler")
        .def(py::init<>())
        .def("compile", &materials::MaterialCompiler::compile,
             py::arg("graph"),
             py::arg("options") = materials::CompilerOptions(),
             "Compile material graph to GLSL shaders")
        .def_static("compute_hash", &materials::MaterialCompiler::compute_hash,
                    "Compute hash for material graph");

    // Shader cache
    py::class_<materials::ShaderCache>(m, "ShaderCache")
        .def(py::init<>())
        .def("get", &materials::ShaderCache::get, py::return_value_policy::reference)
        .def("put", &materials::ShaderCache::put)
        .def("clear", &materials::ShaderCache::clear)
        .def("size", &materials::ShaderCache::size);

    // Utility functions
    m.def("create_noise_material", &materials::create_noise_material,
          py::arg("seed"), py::arg("frequency"),
          "Create a simple noise material graph");

    m.def("create_pbr_material", &materials::create_pbr_material,
          py::arg("albedo"), py::arg("roughness"), py::arg("metallic") = 0.0f,
          "Create a PBR constant material graph");

    // Helper function to extract float array from Python object (list, tuple, or numpy array)
    auto extract_float_array = [](py::object obj, size_t expected_size) -> std::vector<float> {
        std::vector<float> result;
        result.reserve(expected_size);

        // Try as numpy array first
        if (py::hasattr(obj, "tolist")) {
            // It's a numpy array, convert to list first
            py::list lst = obj.attr("tolist")().cast<py::list>();
            for (size_t i = 0; i < py::len(lst) && i < expected_size; ++i) {
                result.push_back(lst[i].cast<float>());
            }
        } else {
            // Try as sequence (list, tuple)
            py::sequence seq = obj.cast<py::sequence>();
            for (size_t i = 0; i < py::len(seq) && i < expected_size; ++i) {
                result.push_back(seq[i].cast<float>());
            }
        }

        // Pad with zeros if not enough elements
        while (result.size() < expected_size) {
            result.push_back(0.0f);
        }

        return result;
    };

    // Helper to create material graph from Python dict (matching materials.py format)
    m.def("compile_material_from_dict", [extract_float_array](py::dict graph_dict) {
        materials::MaterialGraph graph;

        try {
            if (!graph_dict.contains("nodes")) {
                throw std::runtime_error("Missing required key 'nodes'");
            }
            if (!graph_dict.contains("output")) {
                throw std::runtime_error("Missing required key 'output'");
            }

            auto nodes_dict = graph_dict["nodes"].cast<py::dict>();
            graph.output_node = graph_dict["output"].cast<std::string>();

            for (auto item : nodes_dict) {
                std::string node_name = item.first.cast<std::string>();
                auto node_data = item.second.cast<py::dict>();

                if (!node_data.contains("type")) {
                    throw std::runtime_error("Node '" + node_name + "' missing required key 'type'");
                }
                std::string node_type = node_data["type"].cast<std::string>();

                materials::MaterialNode node;
                node.name = node_name;
                node.type = node_type;

                if (node_type == "noise") {
                    materials::NoiseNode noise;
                    noise.seed = node_data["seed"].cast<uint32_t>();
                    noise.frequency = node_data["frequency"].cast<float>();
                    node.data = noise;
                } else if (node_type == "warp") {
                    materials::WarpNode warp;
                    warp.input = node_data["input"].cast<std::string>();
                    warp.strength = node_data["strength"].cast<float>();
                    node.data = warp;
                } else if (node_type == "blend") {
                    materials::BlendNode blend;
                    blend.input_a = node_data["input_a"].cast<std::string>();
                    blend.input_b = node_data["input_b"].cast<std::string>();
                    blend.factor = node_data["factor"].cast<float>();
                    node.data = blend;
                } else if (node_type == "pbr_const") {
                    materials::PBRConstNode pbr;
                    // Extract albedo from list, tuple, or numpy array
                    auto albedo_vals = extract_float_array(node_data["albedo"], 3);
                    pbr.albedo[0] = albedo_vals[0];
                    pbr.albedo[1] = albedo_vals[1];
                    pbr.albedo[2] = albedo_vals[2];
                    pbr.roughness = node_data["roughness"].cast<float>();
                    node.data = pbr;
                }

                graph.nodes[node_name] = node;
            }
        } catch (const py::cast_error& e) {
            throw std::runtime_error(std::string("Type conversion error in compile_material_from_dict: ") + e.what());
        }

        materials::MaterialCompiler compiler;
        return compiler.compile(graph);
    }, "Compile material graph from Python dict to GLSL shaders");

#ifndef NO_GRAPHICS
    // ========================================================================
    // Graphics bindings
    // ========================================================================

    // GPU resources
    py::class_<graphics::GPUBuffer>(m, "GPUBuffer")
        .def(py::init<>())
        .def("is_valid", &graphics::GPUBuffer::is_valid);

    py::class_<graphics::GPUImage>(m, "GPUImage")
        .def(py::init<>())
        .def("is_valid", &graphics::GPUImage::is_valid);

    py::class_<graphics::GPUMesh>(m, "GPUMesh")
        .def(py::init<>())
        .def("is_valid", &graphics::GPUMesh::is_valid)
        .def_readonly("vertex_count", &graphics::GPUMesh::vertex_count)
        .def_readonly("index_count", &graphics::GPUMesh::index_count);

    // Pipeline
    py::class_<graphics::Pipeline>(m, "GraphicsPipeline")
        .def(py::init<>())
        .def("is_valid", &graphics::Pipeline::is_valid)
        .def_readonly("hash", &graphics::Pipeline::hash);

    // Camera
    py::class_<graphics::Camera>(m, "Camera")
        .def(py::init<>())
        .def_readwrite("position", &graphics::Camera::position)
        .def_readwrite("target", &graphics::Camera::target)
        .def_readwrite("up", &graphics::Camera::up)
        .def_readwrite("fov", &graphics::Camera::fov)
        .def_readwrite("near_plane", &graphics::Camera::near_plane)
        .def_readwrite("far_plane", &graphics::Camera::far_plane);

    // Light
    py::class_<graphics::Light>(m, "Light")
        .def(py::init<>())
        .def_readwrite("position", &graphics::Light::position)
        .def_readwrite("radius", &graphics::Light::radius)
        .def_readwrite("color", &graphics::Light::color)
        .def_readwrite("intensity", &graphics::Light::intensity);

    // Render statistics
    py::class_<graphics::RenderStats>(m, "RenderStats")
        .def(py::init<>())
        .def_readonly("draw_calls", &graphics::RenderStats::draw_calls)
        .def_readonly("triangles", &graphics::RenderStats::triangles)
        .def_readonly("vertices", &graphics::RenderStats::vertices)
        .def_readonly("frame_time_ms", &graphics::RenderStats::frame_time_ms);

    // Graphics system
    py::class_<graphics::GraphicsSystem>(m, "GraphicsSystem")
        .def(py::init<>())
        .def("initialize", &graphics::GraphicsSystem::initialize,
             py::arg("width") = 1920,
             py::arg("height") = 1080,
             py::arg("enable_validation") = false,
             py::arg("enable_vsync") = true,
             "Initialize the graphics system (headless mode)")
        .def("create_instance_with_extensions", &graphics::GraphicsSystem::create_instance_with_extensions,
             py::arg("extensions"),
             py::arg("enable_validation") = false,
             "Create Vulkan instance with specified extensions (phase 1 of two-phase init)")
        .def("complete_initialization_with_surface", &graphics::GraphicsSystem::complete_initialization_with_surface,
             py::arg("surface"),
             py::arg("width"),
             py::arg("height"),
             py::arg("enable_vsync") = true,
             "Complete initialization with a surface (phase 2 of two-phase init)")
        .def("get_instance_handle", &graphics::GraphicsSystem::get_instance_handle,
             "Get the Vulkan instance handle as uint64 for FFI")
        .def("shutdown", &graphics::GraphicsSystem::shutdown,
             "Shutdown the graphics system")
        .def("resize", &graphics::GraphicsSystem::resize,
             py::arg("width"),
             py::arg("height"),
             "Resize the render targets")
        .def("upload_mesh", &graphics::GraphicsSystem::upload_mesh,
             "Upload a mesh to GPU")
        .def("destroy_mesh", &graphics::GraphicsSystem::destroy_mesh,
             "Destroy a mesh and free GPU resources")
        .def("create_material_pipeline", &graphics::GraphicsSystem::create_material_pipeline,
             py::arg("vertex_glsl"),
             py::arg("fragment_glsl"),
             "Create a material pipeline from GLSL shaders")
        .def("destroy_pipeline", &graphics::GraphicsSystem::destroy_pipeline,
             "Destroy a pipeline")
        .def("create_default_pipeline", &graphics::GraphicsSystem::create_default_pipeline,
             "Create default shaders for basic rendering")
        .def("begin_frame", &graphics::GraphicsSystem::begin_frame,
             "Begin rendering a frame")
        .def("draw_mesh", py::overload_cast<const graphics::GPUMesh&, const graphics::Pipeline&,
             const std::array<float, 16>&>(&graphics::GraphicsSystem::draw_mesh),
             py::arg("mesh"),
             py::arg("pipeline"),
             py::arg("transform"),
             "Draw a mesh with transform")
        .def("end_frame", &graphics::GraphicsSystem::end_frame,
             "End frame and present")
        .def("set_camera", &graphics::GraphicsSystem::set_camera,
             "Set camera parameters")
        .def("add_light", &graphics::GraphicsSystem::add_light,
             "Add light to scene")
        .def("clear_lights", &graphics::GraphicsSystem::clear_lights,
             "Clear all lights from the scene")
        .def("get_stats", &graphics::GraphicsSystem::get_stats,
             "Get render statistics")
        .def("is_initialized", &graphics::GraphicsSystem::is_initialized,
             "Check if graphics system is initialized")
        .def("init_imgui", &graphics::GraphicsSystem::init_imgui,
             py::arg("sdl_window_handle"),
             "Initialize Dear ImGui with Vulkan + SDL2 backends")
        .def("shutdown_imgui", &graphics::GraphicsSystem::shutdown_imgui,
             "Shut down Dear ImGui")
        .def("imgui_new_frame", &graphics::GraphicsSystem::imgui_new_frame,
             "Begin a new ImGui frame")
        .def("imgui_render", &graphics::GraphicsSystem::imgui_render,
             "Finalize ImGui frame data for rendering")
        .def("imgui_initialized", &graphics::GraphicsSystem::imgui_initialized,
             "Check if Dear ImGui has been initialized");

    // ========================================================================
    // Dear ImGui bindings (free functions for Python ImGuiBackend)
    // ========================================================================

    m.def("imgui_new_frame", []() {
        ImGui_ImplVulkan_NewFrame();
        ImGui_ImplSDL2_NewFrame();
        ImGui::NewFrame();
    }, "Begin a new ImGui frame (Vulkan + SDL2 + ImGui::NewFrame)");

    m.def("imgui_render", []() {
        ImGui::Render();
    }, "Finalize ImGui rendering (call before end_frame)");

    m.def("imgui_begin", [](const std::string& title, int flags) -> bool {
        return ImGui::Begin(title.c_str(), nullptr, static_cast<ImGuiWindowFlags>(flags));
    }, py::arg("title"), py::arg("flags") = 0,
    "Begin an ImGui window");

    m.def("imgui_end", []() {
        ImGui::End();
    }, "End an ImGui window");

    m.def("imgui_text", [](const std::string& text) {
        ImGui::TextUnformatted(text.c_str());
    }, py::arg("text"),
    "Render unformatted text");

    m.def("imgui_text_colored", [](const std::string& text, float r, float g, float b, float a) {
        ImGui::TextColored(ImVec4(r, g, b, a), "%s", text.c_str());
    }, py::arg("text"), py::arg("r"), py::arg("g"), py::arg("b"), py::arg("a") = 1.0f,
    "Render colored text");

    m.def("imgui_button", [](const std::string& label, float w, float h) -> bool {
        return ImGui::Button(label.c_str(), ImVec2(w, h));
    }, py::arg("label"), py::arg("width") = 0.0f, py::arg("height") = 0.0f,
    "Render a button, returns true if clicked");

    m.def("imgui_progress_bar", [](float fraction, float width, float height) {
        ImGui::ProgressBar(fraction, ImVec2(width, height));
    }, py::arg("fraction"), py::arg("width") = -1.0f, py::arg("height") = 0.0f,
    "Render a progress bar");

    m.def("imgui_separator", []() {
        ImGui::Separator();
    }, "Render a horizontal separator");

    m.def("imgui_same_line", []() {
        ImGui::SameLine();
    }, "Place next widget on the same line");

    m.def("imgui_spacing", []() {
        ImGui::Spacing();
    }, "Add vertical spacing");

    m.def("imgui_image", [](uint64_t texture_id, float w, float h) {
        ImGui::Image(static_cast<ImTextureID>(texture_id), ImVec2(w, h));
    }, py::arg("texture_id"), py::arg("width"), py::arg("height"),
    "Render an image by texture ID");

    m.def("imgui_begin_child", [](const std::string& id, float w, float h, bool border) -> bool {
        return ImGui::BeginChild(id.c_str(), ImVec2(w, h), border ? ImGuiChildFlags_Borders : ImGuiChildFlags_None);
    }, py::arg("id"), py::arg("width") = 0.0f, py::arg("height") = 0.0f, py::arg("border") = false,
    "Begin a scrollable child region");

    m.def("imgui_end_child", []() {
        ImGui::EndChild();
    }, "End a child region");

    m.def("imgui_columns", [](int count, bool border) {
        ImGui::Columns(count, nullptr, border);
    }, py::arg("count"), py::arg("border") = true,
    "Set up column layout");

    m.def("imgui_next_column", []() {
        ImGui::NextColumn();
    }, "Move to next column");

    m.def("imgui_set_cursor_pos", [](float x, float y) {
        ImGui::SetCursorPos(ImVec2(x, y));
    }, py::arg("x"), py::arg("y"),
    "Set cursor position within current window");

    m.def("imgui_set_next_window_pos", [](float x, float y) {
        ImGui::SetNextWindowPos(ImVec2(x, y), ImGuiCond_FirstUseEver);
    }, py::arg("x"), py::arg("y"),
    "Set position for the next window");

    m.def("imgui_set_next_window_size", [](float w, float h) {
        ImGui::SetNextWindowSize(ImVec2(w, h), ImGuiCond_FirstUseEver);
    }, py::arg("width"), py::arg("height"),
    "Set size for the next window");

#endif // NO_GRAPHICS
}
