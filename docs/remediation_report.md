# FFI Remediation Report: Python Features Not Connected to C++ Runtime

**Date:** 2026-03-07
**Scope:** Full audit of Python tests, FFI bindings (`procengine_cpp`), and C++ runtime
**Method:** Complete read of every Python source file, every C++ source file, every test file, and the ENGINE_REFERENCE.md. Every finding below is verified by tracing actual code paths through the game loop.

---

## Architecture Context

The Procedural Engine v2 is a **hybrid Python/C++ engine** with a clear design intent:

- **Python** handles game logic, entity management, physics simulation, behavior trees, commands, and UI logic
- **C++** handles performance-critical work: Vulkan rendering, mesh generation, async terrain generation, ImGui rendering, material compilation
- **`GameRunner`** orchestrates the loop, calling into C++ via `GraphicsBridge` and `GameManagerBridge`

The engine already works -- UI renders (ESC/I/backtick menus function), terrain generates, chunks stream, entities spawn, physics runs. The issues identified below are cases where Python-side features are tested but their results are **never passed through the FFI** to produce any effect in the C++ runtime, or where C++ capabilities exist, are bound and tested, but are never invoked from the game loop.

---

## Verified Findings

### 1. Material System: Python Generates Graphs, C++ Compiles Them, But Nobody Calls the Pipeline

**Files involved:**
- `procengine/world/materials.py` -- `generate_material_graph()` produces a JSON-serializable material graph dict
- `cpp/materials.cpp` -- `MaterialCompiler`, `ShaderCache`, `compile_material_from_dict()` compile graphs to GLSL shaders
- `procengine/graphics/graphics_bridge.py:835` -- `create_material_pipeline()` wraps `GraphicsSystem.create_material_pipeline()`

**What's tested:**
- `tests/unit/test_materials.py` (2 tests) -- verifies Python generates deterministic material graph dicts
- `tests/integration/test_cpp_materials.py` (30 tests) -- verifies C++ compiles those dicts into valid GLSL with correct noise functions, PBR lighting, hash determinism, shader caching, etc.

**What happens at runtime:**
- `main.py:265` calls `generate_material_graph()` in `--generate-only` mode, but the result is only serialized to JSON -- never compiled.
- `game_runner.py:1073` creates a single `create_default_pipeline()` with hardcoded built-in shaders. This is the **only** pipeline ever created.
- `GraphicsBridge.create_material_pipeline()` (line 835) exists and correctly calls `GraphicsSystem.create_material_pipeline(vertex_glsl, fragment_glsl)`, but **no code in the game loop ever calls it.**
- `compile_material_from_dict()` is bound in pybind11 and tested in 30 integration tests, but is **never called from any runtime code** -- only from tests.

**Gap:** Python generates material graphs. C++ can compile them to GLSL shaders and create GPU pipelines. The bridge method to create pipelines exists. But the game loop never connects the pieces -- it never calls `generate_material_graph()`, never compiles the result, and never creates per-material pipelines. All rendering uses a single default pipeline with uniform gray/brown entity colors.

**Evidence:**
```
$ grep -rn "create_material_pipeline\|compile_material" procengine/game/
(no results)
```

---

### 2. Engine Class: Tested for Determinism/Hot-Reload, Never Instantiated in Game Loop

**Files involved:**
- `cpp/engine.cpp` -- C++ `Engine` class with `enqueue_heightmap()`, `enqueue_prop_descriptor()`, `hot_reload()`, `step()`, `snapshot_state()`, `reset()`
- `procengine/core/engine.py` -- Python `Engine` class (reference implementation, same API)

**What's tested:**
- `tests/integration/test_cpp_engine.py` (2 tests) -- snapshot determinism, reset behavior
- `tests/unit/test_engine.py` (3 tests) -- Python Engine snapshot, hot-reload, reset
- `tests/unit/test_engine_determinism.py` (1 test) -- state hash repeatability
- `tests/unit/test_hot_reload.py` (7 tests) -- hot-reload queue processing, descriptor changes, determinism

**What happens at runtime:**
- `main.py:138` instantiates `cpp.Engine(config.seed)` in the `ProceduralEngine` class, but this is only used in `--generate-only` / `--benchmark` / `--verify` modes. In the main game mode (`runner.run()` at line 607), the `ProceduralEngine` is never created.
- `GameRunner` never imports or instantiates either the Python or C++ Engine class.
- `Engine.hot_reload()` is tested across 7 unit tests but there is no code path that triggers it during gameplay. The console command system does not expose a hot-reload command.
- `Engine.snapshot_state()` is tested for determinism verification but never called during gameplay.

**Gap:** The Engine's state-tracking, hot-reload, and determinism-verification capabilities are fully implemented in both Python and C++, tested with 13 tests, but the `GameRunner` game loop never uses any of it.

---

### 3. LOD Mesh Generation: C++ Implements It, Tests Verify It, Nobody Calls It

**Files involved:**
- `cpp/props.cpp` -- `generate_lod(Mesh& mesh, float target_ratio)` simplifies meshes by reducing vertex count
- `cpp/engine.cpp` -- bound as `procengine_cpp.generate_lod(mesh, target_ratio)`

**What's tested:**
- `tests/integration/test_cpp_props.py::test_generate_lod` -- verifies vertex reduction at 0.25 ratio
- `tests/integration/test_cpp_props.py::test_lod_deterministic` -- verifies deterministic output

**What happens at runtime:**
- `GameManagerBridge.sync_frame()` returns a `FrameDirective` with a `lod_bias` field.
- `game_runner.py:1310` stores it: `self._current_lod_bias = directive.lod_bias`
- `self._current_lod_bias` is **never read by any other code**. No mesh is ever passed through `generate_lod()`.

**Gap:** The C++ LOD system works (tested), the C++ GameManager provides LOD bias hints (stored), but the game loop never applies LOD to any mesh. All meshes are rendered at full detail regardless of distance or frame budget.

---

### 4. C++ PhysicsWorld / PhysicsWorld3D Containers: Tested but Not Used

**Files involved:**
- `cpp/physics.cpp` -- `PhysicsWorld` (2D) and `PhysicsWorld3D` classes with `add_body()`, `get_body()`, `step()`, `reset()`, `set_heightfield()`
- `cpp/engine.cpp` -- both bound via pybind11

**What's tested:**
- `tests/integration/test_cpp_physics.py::test_physics_world_basic` -- PhysicsWorld add/step/get
- `tests/integration/test_cpp_physics.py::test_physics_world_with_heightfield` -- PhysicsWorld with heightfield

**What happens at runtime:**
- The game uses **Python-side physics** (`procengine.physics.collision.step_physics_3d`), which is by design (documented in ENGINE_REFERENCE.md as "Pure-Python 3D physics").
- The Python physics work as a hybrid: Y-axis gravity + terrain collision in 3D, then XZ-plane sequential impulse collision in 2D projection. This is the correct, intentional architecture.
- The C++ `PhysicsWorld` and `PhysicsWorld3D` container classes are **never instantiated** from any runtime code. They are pure test-only artifacts.

**Note:** This is NOT the same as saying "C++ physics is unused." The C++ `step_physics()` and `step_physics_3d()` free functions are bound but the Python side has its own implementation by design. The container classes (`PhysicsWorld`, `PhysicsWorld3D`) specifically are the untouched part -- they provide persistent body management that the game loop doesn't use (it rebuilds the body list each frame from game entities instead).

---

### 5. C++ Primitive Mesh Generators: Some Tested but Never Called at Runtime

**Files involved:**
- `cpp/props.cpp` -- `generate_box_mesh()`, `generate_capsule_mesh()`, `generate_cylinder_mesh()`, `generate_cone_mesh()`, `generate_plane_mesh()`

**What's tested:**
- `tests/integration/test_mesh_generation.py` -- tests all five primitives

**What's used at runtime (via `GraphicsBridge.upload_entity_mesh()`):**
- `generate_capsule_mesh()` -- used for player/NPC meshes
- `generate_cylinder_mesh()` -- used as fallback for tree/dead_tree meshes
- `generate_box_mesh()` -- used for building and default/unknown entity meshes

**What's NOT used at runtime:**
- `generate_cone_mesh()` -- tested but never called from any runtime code
- `generate_plane_mesh()` -- tested but never called from any runtime code

**Gap:** Minor. Two primitive generators are bound, tested, but not used. They exist as utility functions that could be useful but currently aren't invoked.

---

### 6. C++ `Engine.generate_terrain()` vs `generate_terrain_standalone()`: Only Standalone Used

**Files involved:**
- `cpp/engine.cpp` -- `Engine::generate_terrain()` (member method) and `generate_terrain_standalone()` (free function)

**What's tested:**
- `tests/integration/test_cpp_terrain.py::test_standalone_terrain_generation` -- tests `generate_terrain_standalone()`
- `tests/integration/test_cpp_terrain.py::test_engine_terrain_generation` -- tests `Engine.generate_terrain()`

**What happens at runtime:**
- `game_runner.py:1557` uses `cpp.generate_terrain_standalone()` for static terrain setup
- `Engine.generate_terrain()` is only used in `main.py:199` in `--generate-only` mode
- Since the `Engine` class is never instantiated by `GameRunner`, `Engine.generate_terrain()` is never called during gameplay

**Gap:** The Engine-based terrain generation method has no runtime path. However, the equivalent `generate_terrain_standalone()` IS used, so terrain generation itself works fine. The Engine method is redundant for the game loop's purposes.

---

### 7. Some Integration-Tested C++ Prop Features Are Unused at Runtime

**Files involved:**
- `cpp/props.cpp` -- `BuildingDescriptor`, `CreatureDescriptor`, `evaluate_metaball_field()`, `create_creature_from_dict()`

**What's tested:**
- `tests/integration/test_cpp_props.py` -- building mesh generation, creature mesh generation (metaball fields, marching cubes), L-system evaluation, tree skeleton generation

**What happens at runtime:**
- `GraphicsBridge.upload_entity_mesh()` has code paths for buildings (uses `generate_box_mesh()` instead of `generate_building_mesh()`), and does not have any code path for creatures.
- `BuildingDescriptor` and `generate_building_mesh()` are tested (6 tests) but the runtime uses a simple box for buildings instead.
- `CreatureDescriptor`, `evaluate_metaball_field()`, and `generate_creature_mesh()` are tested (4 tests) but never used at runtime. No entity type "creature" exists in the entity rendering path.
- `evaluate_lsystem()` and `generate_tree_skeleton()` are tested individually but at runtime, tree meshes are generated via `generate_tree_mesh()` (which uses them internally) or `create_tree_from_dict()`.

**Gap:** The full procedural building mesh (BSP-split blocks) and creature mesh (metaball marching cubes) generation in C++ is tested but never produces runtime output. Buildings render as plain boxes. Creatures don't exist as a rendered entity type.

---

## Summary: What's Tested but Disconnected from Runtime

| C++ Feature | Integration Tests | Used at Runtime? | Gap |
|---|---|---|---|
| Material compilation (`compile_material_from_dict`) | 30 tests | No | Graphs generated in Python, never compiled or applied |
| Material pipelines (`create_material_pipeline`) | Tested via graphics tests | No | Bridge method exists but never called |
| Engine state tracking (`snapshot_state`, `step`) | 2 tests | No | Never instantiated in game loop |
| Hot-reload system (`hot_reload`, `rebuild_resource`) | 7 Python tests | No | No command or code path triggers it |
| LOD mesh simplification (`generate_lod`) | 2 tests | No | `lod_bias` stored but never applied |
| PhysicsWorld / PhysicsWorld3D containers | 2 tests | No | Game rebuilds body list each frame instead |
| `generate_cone_mesh()` | 1 test | No | Not used for any entity type |
| `generate_plane_mesh()` | 1 test | No | Not used for any entity type |
| `Engine.generate_terrain()` | 1 test | No | `generate_terrain_standalone()` used instead |
| `generate_building_mesh()` (full BSP) | 6 tests | No | Buildings use simple `generate_box_mesh()` |
| `generate_creature_mesh()` (metaballs) | 4 tests | No | No creature entity type rendered |
| `evaluate_metaball_field()` | 1 test | No | Only used in creature tests |
| ShaderCache (`put`, `get`, `clear`, `size`) | 3 tests | No | Materials never compiled at runtime |

**Total: ~60 integration tests verify C++ features that produce no effect during actual gameplay.**

---

## What IS Working Correctly (Not Gaps)

These systems are correctly connected and functioning as designed:

| System | Python Side | C++ Side | Connection |
|---|---|---|---|
| **Terrain mesh generation** | ChunkManager generates heightmaps | `generate_terrain_mesh_with_biomes()` | GraphicsBridge uploads via C++ |
| **Async chunk generation** | GameRunner orchestrates | GameManager generates in worker threads | GameManagerBridge wraps C++ |
| **Prop mesh generation** | Python generates descriptors | 10+ C++ mesh generators (rock, tree, bush, pine, dead tree, fallen log, boulder cluster, flower, mushroom, cactus) | GraphicsBridge creates meshes via C++ |
| **Vulkan rendering** | Python manages draw calls | GraphicsSystem handles Vulkan | GraphicsBridge delegates to C++ |
| **ImGui UI** | Python UIManager with 10 components | C++ ImGui bindings (20+ functions) | ImGuiBackend calls C++ directly |
| **Camera/Lighting** | Python tracks camera state | C++ Camera/Light objects | GraphicsBridge passes to C++ |
| **Frame budgeting** | GameRunner uses FrameDirective | GameManager computes budgets | GameManagerBridge wraps C++ |
| **Chunk lifecycle** | ChunkManager tracks state | GameManager handles unload decisions | Both contribute to chunk management |
| **Physics (by design)** | Pure Python hybrid 2D+height | N/A (Python by design) | Intentional architecture per ENGINE_REFERENCE.md |
| **Behavior trees** | Pure Python | N/A | Game logic stays in Python |
| **Commands/Console** | Pure Python | N/A | UI rendering goes through ImGui |

---

## Recommended Remediation Priority

### Priority 1 -- Connect the Material Pipeline
The biggest untapped feature. 30 C++ tests verify a working material compiler. The bridge method exists. The gap is just connecting the dots:
1. Call `generate_material_graph()` for different biome types during initialization
2. Compile each via `compile_material_from_dict()`
3. Create per-material GPU pipelines via `GraphicsBridge.create_material_pipeline()`
4. Assign pipeline names to chunks/entities based on biome instead of always using "default"

### Priority 2 -- Apply LOD System
The infrastructure exists end-to-end:
1. C++ `generate_lod()` works and is tested
2. `GameManager.sync_frame()` already returns `lod_bias`
3. `GameRunner` already stores `_current_lod_bias`
4. Just need to call `generate_lod()` on distant prop meshes based on `_current_lod_bias` and camera distance

### Priority 3 -- Integrate Engine State Tracking
Connect the Engine class for determinism verification and hot-reload:
1. Instantiate C++ Engine in GameRunner
2. Call `Engine.enqueue_heightmap()` when terrain is generated
3. Expose `Engine.hot_reload()` through the command system
4. Optionally use `Engine.snapshot_state()` for save-game integrity checks

### Priority 4 -- Use Full Procedural Building/Creature Meshes
Replace `generate_box_mesh()` for buildings with `generate_building_mesh()` using actual BSP descriptors. Consider adding creature entities that use the metaball marching-cubes mesh generator.
