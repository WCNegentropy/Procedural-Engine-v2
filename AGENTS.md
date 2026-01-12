# AGENTS.md — Procedural Game Engine (Flagship Studio Ecosystem)

## Purpose
This document binds every human contributor and automated agent (e.g., ChatGPT Codex, CI bots) to the core constraints, architecture, and best-practice workflow defined in **Procedural Game Engine – Architecture v1** (see `/docs/Architecture_v1.md`).
Paste this file into the root of the game-studio repository so that any context-aware tools inherit these rules automatically.

---

## 1 · Guiding Principles
- **Determinism First** — All runtime output must be a pure function of the designated seeds and engine version. No hidden randomness or non-replayable state.
- **Hybrid Discipline** — Python ≙ author-time generators & tooling; C++ ≙ real-time execution. Cross only at the defined FFI API.
- **One Source of Truth** — The RootSeed governs every subsystem via the SeedRegistry; diverging PRNGs are forbidden.
- **Immutability After Hand-Off** — Once a buffer crosses the Python → C++ boundary, its contents are read-only. C++ mutates runtime state via ECS, never the original generator data.
- **Fail Fast, Fail Loud** — Any determinism hash mismatch, FPS regression, or physics NaN terminates the build or CI run.

---

## 2 · Language Ownership Matrix

| Subsystem         | Python Responsibilities | C++ Responsibilities |
|-------------------|--------------------------|-----------------------|
| **Seeds & PRNG**  | Call `SeedRegistry.get_subseed()`; never instantiate local RNGs. | Master `SeedRegistry`, expose PCG64 stream to Python via FFI. |
| **Terrain**       | Height/Biome/River mask generation, macro-plates, simplex FBM, biome LUT ✅ | GeoClipmap mesh, GPU erosion, collider heightfield. |
| **Props & Creatures** | Generate JSON descriptors (CSG trees, L-systems, genomes). | Mesh synthesis, LODs, skeleton rigs, GPU upload. |
| **Materials**     | Emit material graph DSL (JSON). | DSL→SPIR-V compile, virtual texture paging. |
| **Physics**       | 2D reference solver + broad-phase/heightfield ✅ | Bullet-style solver, fluid voxels, wind fields. |
| **Testing/Tooling** | Seed mining, dashboards, live editors. | Headless mode, hot-reload endpoint. |

> Do **NOT** add gameplay logic that requires per-frame Python execution. Script only large-grain events.

---

## 3 · Determinism Contract
- Use **PCG64** for every random sample.
- Fixed Δt = 1/60 s physics step.
- **SHA-256** hash every buffer passed over FFI and assert equality on C++ side.
- Regression test hashes at frames 0, 100, 500 in CI.

---

## 4 · FFI API Surface (Canonical)
```python
Engine.enqueue_heightmap(memview h16, memview biome8, memview river1)
Engine.enqueue_prop_descriptor(list[dict])
Engine.hot_reload(uint64 descriptorHash)
Engine.step(float dt)
Engine.reset()
Engine.snapshot_state(frame:int) -> bytes   # returns deterministic hash
```

---

## 5 · Best Practices & CI Pipeline
- Adhere to PEP 8 style and type annotate new Python code.
- Run `pytest` and ensure all tests pass before submitting a change.
- Update `TEST_RESULTS.md` with the latest `pytest` results after meaningful changes.
- The GitHub Actions workflow runs tests on Python 3.10 and 3.11 and builds the package; keep these jobs green.
- Each commit must leave the repository in a clean state with all checks passing.
- Maintain the root `requirements.txt` with all core dependencies (currently `numpy` and `pytest`).
- Respect the repository `.gitignore`; avoid committing build artifacts or virtual environments.

---

## 5.1 · Repository Structure

The repository follows a hierarchical package structure for maintainability and AI-agent collaboration:

```
/
├── procengine/                 # CORE PYTHON PACKAGE
│   ├── __init__.py             # Version, public API exports
│   ├── core/                   # Engine fundamentals
│   │   ├── engine.py           # Main engine class
│   │   └── seed_registry.py    # Deterministic sub-seeding
│   ├── world/                  # World generation
│   │   ├── terrain.py          # Heightmap, biomes, erosion
│   │   ├── props.py            # Rock, tree, building generators
│   │   ├── materials.py        # Material graph DSL
│   │   └── world.py            # Multi-chunk assembly
│   ├── physics/                # Physics system
│   │   ├── bodies.py           # RigidBody, RigidBody3D, Vec3
│   │   ├── collision.py        # Sequential impulse solver
│   │   └── heightfield.py      # HeightField, HeightField2D
│   ├── game/                   # Game layer (Phase 2)
│   │   ├── game_api.py         # GameWorld, Entity, Events
│   │   ├── behavior_tree.py    # NPC behavior trees
│   │   ├── player_controller.py # Input & camera system
│   │   ├── data_loader.py      # JSON data loading
│   │   ├── game_runner.py      # Main game loop
│   │   └── ui_system.py        # UI with headless support
│   ├── commands/               # Command system (Phase 4)
│   │   ├── commands.py         # Command registry
│   │   ├── console.py          # In-game console
│   │   └── handlers/           # Command implementations
│   └── graphics/               # Rendering bridge
│       └── graphics_bridge.py  # Vulkan/headless abstraction
│
├── cpp/                        # C++ NATIVE BACKEND
│   ├── CMakeLists.txt
│   └── *.cpp, *.h              # Vulkan, physics, terrain
│
├── tests/                      # TEST SUITE
│   ├── conftest.py             # Pytest configuration
│   ├── unit/                   # Unit tests
│   │   └── test_*.py
│   ├── integration/            # Integration tests
│   │   └── test_*.py
│   └── performance/            # Performance tests
│
├── data/                       # GAME CONTENT (JSON)
│   ├── npcs/
│   ├── quests/
│   └── items/
│
├── tools/                      # DEV UTILITIES
│   └── seed_sweeper.py
│
├── examples/                   # DEMOS & TUTORIALS
│   ├── biome_colors.py
│   └── frame_timing.py
│
├── docs/                       # DOCUMENTATION
├── scripts/                    # BUILD & CI SCRIPTS
│
├── main.py                     # PRIMARY ENTRY POINT
├── pyproject.toml              # Modern Python packaging
└── requirements.txt            # Dependencies
```

### Import Patterns

**New package imports (preferred):**
```python
from procengine import Engine, SeedRegistry, generate_terrain_maps
from procengine.physics import RigidBody, step_physics
from procengine.game import GameWorld, Player
```

**Legacy imports (still supported for backward compatibility):**
```python
from engine import Engine
from seed_registry import SeedRegistry
from physics import RigidBody, step_physics
```

---

## 6 · Implementation Status

### Python Reference Implementation
- ✅ Deterministic buffer hashing and state snapshot API (`engine.py`)
- ✅ Hot-reload descriptor hash tracking (`engine.py`)
- ✅ State hash regression helper (`Engine.run_and_snapshot`)
- ✅ Reset to initial state (`Engine.reset`)
- ✅ Deterministic rock descriptor generator (`props.py`)
- ✅ Material graph specification emitter (`materials.py`)
- ✅ Deterministic tree L-system descriptor generator (`props.py`)
- ✅ Deterministic building shape grammar descriptor generator (`props.py`)
- ✅ Deterministic creature metaball + skeleton descriptor generator (`props.py`)
- ✅ Deterministic 2D sequential impulse physics solver (`physics.py`)
- ✅ Uniform grid broad-phase and heightfield proxy (`physics.py`)
- ✅ Configurable gravity and damping in physics solver (`physics.py`)
- ✅ Hierarchical seed registry spawning (`seed_registry.py`)
- ✅ Multi-chunk world generator with macro plates and erosion (`world.py`)
- ✅ Deterministic terrain generation (FBM, biomes, erosion, slope) (`terrain.py`)
- ✅ Deterministic Sobol seed batch generator (`seed_sweeper.py`)

### C++ Runtime Implementation
- ✅ Full terrain generation system (macro-plates, FBM, hydraulic erosion, biomes, rivers, slopes)
- ✅ Props mesh generation (rocks, trees, buildings, creatures with LODs)
- ✅ Material graph compiler (GLSL generation, SPIR-V compilation, shader cache)
- ✅ Physics system (sequential impulse solver, heightfield collider, deterministic simulation)
- ⚠️ Graphics system (see **Graphics Implementation Status** below)
- ✅ Hot-reload infrastructure (descriptor caching, dirty-state tracking, rebuild queue)
- ✅ SeedRegistry with PCG64 PRNG and deterministic sub-seeding
- ✅ Buffer hashing and state snapshot API matching Python spec

### Phase 2 Game Systems (Python)
- ✅ GameWorld, Entity hierarchy, Event system (`game_api.py`)
- ✅ Full behavior tree system with decorators (`behavior_tree.py`)
- ✅ Input abstraction and camera system (`player_controller.py`)
- ✅ JSON data loading for NPCs, quests, items (`data_loader.py`)
- ✅ Game loop orchestration with physics (`game_runner.py`)
- ✅ UI system with headless testing support (`ui_system.py`)
- ✅ Graphics bridge with headless fallback (`graphics_bridge.py`)

---

## 7 · Graphics Implementation Status

The Vulkan graphics backend is now **fully operational** with complete rendering pipeline.
**The game successfully renders terrain, entities, and props!**
Headless mode remains fully functional for testing and CI.

| Component | File:Line | Status | Description |
|-----------|-----------|--------|-------------|
| `draw_mesh()` | cpp/graphics.cpp | ✅ Complete | Full vkCmdDraw calls with pipeline/descriptor binding |
| `create_pipeline()` | cpp/graphics.cpp | ✅ Complete | VkPipeline creation with shader modules |
| Render passes | cpp/graphics.cpp | ✅ Complete | Depth prepass + forward pass |
| Framebuffers | cpp/graphics.cpp | ✅ Complete | VkFramebuffer for swapchain and headless |
| Swapchain | cpp/graphics.cpp | ✅ Complete | Full swapchain management with resize support |
| Uniform buffers | cpp/graphics.cpp | ✅ Complete | Per-frame uniforms (view/projection/camera) |
| Descriptor sets | cpp/graphics.cpp | ✅ Complete | Frame descriptor sets with uniform binding |
| Push constants | cpp/graphics.cpp | ✅ Complete | Per-draw model transforms and color |
| `clear_lights()` | cpp/graphics.cpp | ✅ Complete | C++ GraphicsSystem method |
| Default shaders | cpp/graphics.cpp | ✅ Complete | Basic diffuse lighting shaders |
| Biome colors | cpp/terrain.cpp | ✅ Complete | 16-biome color palette with vertex colors |
| Entity meshes | cpp/props.cpp | ✅ Complete | Capsule, cylinder, box, rock mesh generation |

### Rendering Pipeline

The graphics system implements a deferred command recording approach:
1. **begin_frame()** - Acquire swapchain image, reset command buffer
2. **draw_mesh()** - Queue draw commands with transforms
3. **end_frame()** - Record render pass, submit, present

### Key Features
- Double-buffered rendering with MAX_FRAMES_IN_FLIGHT = 2
- Depth pre-pass for early Z rejection
- Forward rendering with basic diffuse lighting
- Dynamic viewport/scissor for window resizing
- Push constants for per-draw transforms (no descriptor updates)
- Swapchain recreation on window resize
- Headless mode for CI/testing without display
- **16-biome color palette** with realistic three-point lighting
- **Per-vertex colors** for terrain and entity meshes
- **Entity-specific coloring** for players, NPCs, rocks, trees, buildings

### Entity Mesh Rendering
Entity meshes are now fully supported with proper coloring:
- **Players/NPCs**: Capsule mesh with skin-tone coloring
- **Rocks**: Sphere mesh with gray coloring  
- **Trees**: Cylinder mesh with brown bark coloring
- **Buildings**: Box mesh with stone/concrete coloring

The `upload_entity_mesh()` function in `graphics_bridge.py` handles mesh creation,
uniform color application, and GPU upload for all entity types.
