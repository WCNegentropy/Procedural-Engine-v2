#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <openssl/sha.h>
#include <vector>
#include <string>
#include "seed_registry.h"
#include "terrain.h"
#include "physics.h"
#include "props.h"

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
        .def("sample", &physics::HeightField::sample)
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
        for (size_t i = 0; i < bodies.size(); ++i) {
            body_list[i].attr("position") = bodies[i].position;
            body_list[i].attr("velocity") = bodies[i].velocity;
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
        .def_readonly("indices", &props::Mesh::indices)
        .def("vertex_count", &props::Mesh::vertex_count)
        .def("triangle_count", &props::Mesh::triangle_count)
        .def("clear", &props::Mesh::clear)
        .def("append", &props::Mesh::append)
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
        .def_readwrite("radius", &props::RockDescriptor::radius);

    m.def("generate_rock_mesh", &props::generate_rock_mesh,
          py::arg("desc"),
          py::arg("segments") = 16,
          py::arg("rings") = 12,
          "Generate a sphere mesh for a rock");

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

    // Helper function to create descriptors from Python dicts
    m.def("create_rock_from_dict", [](py::dict d) {
        props::RockDescriptor desc;
        auto pos = d["position"].cast<py::list>();
        desc.position = props::Vec3(
            pos[0].cast<float>(),
            pos[1].cast<float>(),
            pos[2].cast<float>()
        );
        desc.radius = d["radius"].cast<float>();
        return desc;
    }, "Create RockDescriptor from Python dict");

    m.def("create_tree_from_dict", [](py::dict d) {
        props::TreeDescriptor desc;
        desc.lsystem.axiom = d["axiom"].cast<std::string>();
        auto rules = d["rules"].cast<py::dict>();
        for (auto item : rules) {
            char key = item.first.cast<std::string>()[0];
            desc.lsystem.rules[key] = item.second.cast<std::string>();
        }
        desc.angle = d["angle"].cast<float>();
        desc.iterations = d["iterations"].cast<uint32_t>();
        return desc;
    }, "Create TreeDescriptor from Python dict");

    m.def("create_creature_from_dict", [](py::dict d) {
        props::CreatureDescriptor desc;

        auto skeleton = d["skeleton"].cast<py::list>();
        for (auto bone : skeleton) {
            auto b = bone.cast<py::dict>();
            props::Bone bone_data;
            bone_data.length = b["length"].cast<float>();
            bone_data.angle = b["angle"].cast<float>();
            desc.skeleton.push_back(bone_data);
        }

        auto metaballs = d["metaballs"].cast<py::list>();
        for (auto mb : metaballs) {
            auto m_dict = mb.cast<py::dict>();
            props::Metaball ball;
            auto center = m_dict["center"].cast<py::list>();
            ball.center = props::Vec3(
                center[0].cast<float>(),
                center[1].cast<float>(),
                center[2].cast<float>()
            );
            ball.radius = m_dict["radius"].cast<float>();
            desc.metaballs.push_back(ball);
        }

        return desc;
    }, "Create CreatureDescriptor from Python dict");
}
