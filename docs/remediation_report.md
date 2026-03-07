# FFI Remediation Report: Python Features Not Connected to C++ Runtime

**Date:** 2026-03-07
**Scope:** Full audit of Python tests, FFI bindings (`procengine_cpp`), and C++ runtime
**Goal:** Identify features tested on the Python side that are not passed through the FFI to the C++ runtime, resulting in them doing nothing in the actual runtime.

---

## Executive Summary

The Procedural Engine v2 has a hybrid Python/C++ architecture where Python handles game logic and C++ handles performance-critical systems. However, a systematic audit reveals **significant gaps** where the C++ runtime has full implementations of systems that the game loop never actually calls -- instead using slower, parallel Python implementations. The Python test suites verify the Python implementations thoroughly, giving a false sense of full-system coverage, while the corresponding C++ implementations sit unused in the actual runtime.

The most critical finding is that **the entire C++ physics engine is orphaned** -- fully implemented, fully tested in integration tests, but never invoked by the game loop. The game loop exclusively uses the Python physics solver. Similar patterns exist for terrain generation (dual-path redundancy), the Engine state management class, and several other subsystems.

---

## Critical Findings

### 1. Physics Engine -- C++ Implementation Completely Unused

**Severity: CRITICAL**

**What exists in C++ (`cpp/physics.h`, `cpp/physics.cpp`):**
- `Vec2`, `Vec3` -- Full vector math
- `RigidBody`, `RigidBody3D` -- Rigid body with mass, velocity, radius
- `HeightField`, `HeightField2D` -- Terrain collision with bilinear interpolation
- `PhysicsWorld`, `PhysicsWorld3D` -- Full world containers with add/remove/step/reset
- `PhysicsConfig`, `PhysicsConfig3D` -- Configuration structs
- `step_physics()`, `step_physics_3d()` -- Sequential impulse solvers
- `broad_phase_pairs()` -- Spatial grid broad-phase collision detection

**What's exposed via FFI (`cpp/engine.cpp` pybind11 bindings):**
All of the above are bound and accessible as `procengine_cpp.Vec2`, `procengine_cpp.step_physics()`, etc.

**What's tested in integration tests (`tests/integration/test_cpp_physics.py`):**
12 tests verifying C++ physics: Vec2 operations, RigidBody creation, deterministic collisions, heightfield collision, gravity, damping, PhysicsWorld management, broad-phase detection.

**What the game loop actually uses (`procengine/game/game_api.py:32, 1833`):**
```python
from procengine.physics import HeightField2D, RigidBody3D, Vec3, step_physics_3d
```
The game loop imports and uses the **pure Python** physics from `procengine/physics/collision.py`, NOT the C++ implementation. `GameWorld.physics_step()` calls `step_physics_3d()` from the Python module.

**What the Python unit tests cover:**
- `tests/unit/test_physics.py` -- 6 tests on Python 2D physics
- `tests/unit/test_physics_3d.py` -- 30+ tests on Python Vec3, RigidBody3D, HeightField2D
- `tests/unit/test_physics_terrain_collision.py` -- 4 tests on Python terrain collision

**Impact:** The C++ physics engine (which would be significantly faster) is never used. All physics simulation runs in pure Python. Players experience Python-speed physics instead of native C++ physics. The 12 integration tests verify C++ physics works, but it's dead code in the actual game.

**Remediation:** `GameWorld.physics_step()` in `game_api.py` should be updated to call `procengine_cpp.step_physics_3d()` when the C++ module is available, falling back to Python only when it's not. The Python `Vec3` and `RigidBody3D` objects would need a conversion layer to/from C++ equivalents (or the game entities should use C++ types directly).

---

### 2. Terrain Generation -- Dual Path Redundancy

**Severity: HIGH**

**The problem:** There are two completely independent terrain generation paths that both run in production:

**Path A -- Python ChunkManager (synchronous):**
- `procengine/world/chunk.py` `ChunkManager.process_load_queue()` calls
- `procengine/world/terrain.py` `generate_terrain_maps()` (pure Python Simplex noise, FBM, erosion, biomes)
- Used as the fallback path in `game_runner.py:1311-1323`

**Path B -- C++ GameManager (async, threaded):**
- `procengine/managers/game_manager.py` `GameManagerBridge` wraps `procengine_cpp.GameManager`
- C++ `GameManager` generates terrain in worker threads using `cpp/terrain.cpp`
- Results collected via `collect_ready_chunks()` in `game_runner.py:1282`

**What happens at runtime (`game_runner.py:1258-1323`):**
When the C++ GameManager is available, the game loop uses Path B for terrain generation BUT still maintains the Python ChunkManager for spatial queries, entity tracking, and simulation flags. The Python ChunkManager's `process_load_queue()` (which generates terrain in Python) is only called in the fallback path.

However, during the initial LOADING state (`_setup_dynamic_terrain`, line 1728), the Python ChunkManager's `process_load_queue()` IS called to force-load the spawn chunk:
```python
immediate = self._chunk_manager.process_load_queue(max_per_frame=1)
```
This generates terrain using the **Python** path even when C++ is available.

**Additionally:** The Python ChunkManager generates chunk props via `process_prop_queue()` (line 1288) using the Python `generate_chunk_props()` function. This prop generation code is tested in 30+ unit tests but C++ has no prop placement equivalent -- props are always generated in Python.

**Impact:** During initial loading, terrain is generated twice for the spawn chunk (once Python, once C++ async). The two terrain generators can produce slightly different results if their algorithms diverge, leading to potential visual discontinuities at chunk boundaries.

**Remediation:** The initial LOADING state should wait for the C++ GameManager to produce the spawn chunk rather than generating it synchronously in Python. Alternatively, ensure both generators are provably identical (which the integration test `test_cpp_seed_registry.py::test_named_subseeds_match_python` partially validates for seeds, but not for full terrain output).

---

### 3. Engine State Management Class -- Orphaned in Game Loop

**Severity: MODERATE**

**What exists in C++ (`cpp/engine.cpp`):**
The `Engine` class provides:
- `enqueue_heightmap()` -- SHA-256 hash verification of terrain buffers
- `enqueue_prop_descriptor()` -- Hash and cache prop descriptors
- `hot_reload()` -- Mark resources dirty for re-generation
- `step()` -- Process hot-reload queue
- `snapshot_state()` -- Deterministic state snapshots
- `reset()` -- Return to pristine state
- `generate_terrain()` -- Terrain generation via the Engine instance

**What's tested:**
- `tests/integration/test_cpp_engine.py` -- 2 tests (snapshot determinism, reset)
- `tests/unit/test_engine.py` -- 3 tests on Python Engine stub
- `tests/unit/test_engine_determinism.py` -- 1 test on state hash repeatability
- `tests/unit/test_hot_reload.py` -- 7 tests on hot reload functionality

**What exists in Python (`procengine/core/engine.py`):**
A parallel Python `Engine` class that replicates the same SHA-256 hashing, descriptor caching, hot-reload queue, and snapshot logic.

**What the game loop uses:**
**Neither.** The `GameRunner` class does not instantiate or use either `Engine` class. The hot-reload, snapshot, and descriptor-caching features are tested but entirely disconnected from the game loop. There is no code path in `game_runner.py` that calls `Engine.step()`, `Engine.snapshot_state()`, or `Engine.hot_reload()`.

**Impact:** The entire engine state verification system (designed for determinism validation and hot-reload) is dead code. Hot-reload is tested but unusable. State snapshots for determinism verification are tested but never taken during gameplay.

**Remediation:** The `GameRunner` should instantiate the C++ `Engine` and:
- Call `Engine.step()` each frame
- Use `Engine.enqueue_heightmap()` to register terrain for integrity checking
- Expose `Engine.hot_reload()` through the command system
- Optionally take periodic snapshots for determinism verification

---

### 4. Seed Registry -- Dual Implementations, Only Python Used at Runtime

**Severity: MODERATE**

**What exists:**
- **C++ (`cpp/seed_registry.h/cpp`):** Full SeedRegistry with splitmix64, PCG64, named subseeds, sequential subseeds
- **Python (`procengine/core/seed_registry.py`):** Equivalent implementation with identical algorithms
- **FFI bindings:** C++ SeedRegistry is fully bound as `procengine_cpp.SeedRegistry`

**What's tested:**
- `tests/integration/test_cpp_seed_registry.py` -- 5 tests verifying C++ SeedRegistry, including cross-validation that C++ matches Python (`test_named_subseeds_match_python`)
- `tests/unit/test_seed_registry.py` -- 4 tests on Python SeedRegistry

**What the game loop uses:**
The game loop exclusively uses the Python `SeedRegistry`:
- `game_runner.py:1675` creates `SeedRegistry(self.config.world_seed)` for the ChunkManager
- All prop generation, terrain generation (Python path), and chunk seeding use Python SeedRegistry
- The C++ `GameManager` has its own internal C++ `SeedRegistry`, but the Python game loop never instantiates `procengine_cpp.SeedRegistry` directly

**Impact:** Minor performance impact since seed generation is not a bottleneck. The cross-validation test ensures algorithmic parity, so correctness is not at risk. However, the C++ SeedRegistry binding serves no purpose in the runtime.

**Remediation:** Low priority. The dual implementation is acceptable as long as `test_named_subseeds_match_python` continues to pass. Could optionally use C++ SeedRegistry in performance-critical paths.

---

### 5. Material Compilation -- Tested but Never Invoked at Runtime

**Severity: MODERATE**

**What exists in C++ (`cpp/materials.h/cpp`):**
- `NoiseNode`, `WarpNode`, `BlendNode`, `PBRConstNode`, `TextureNode` -- Graph node types
- `MaterialGraph` -- Complete material graph container
- `MaterialCompiler` -- Compiles material graphs to GLSL vertex/fragment shaders
- `ShaderCache` -- Hash-based compiled shader caching
- `CompilerOptions` -- GLSL version, optimization flags
- `compile_material_from_dict()` -- Python dict to compiled shader pipeline

**What's tested:**
- `tests/integration/test_cpp_materials.py` -- **30 tests** covering node creation, graph compilation, GLSL output structure, PBR functions, noise functions, hash determinism, complex multi-layer graphs, shader cache
- `tests/unit/test_materials.py` -- 2 tests on Python material graph generation

**What the Python side generates:**
- `procengine/world/materials.py` `generate_material_graph()` creates JSON-serializable material graph dicts

**What the game loop uses:**
The `GameRunner._init_graphics_resources()` creates a **default pipeline** via `GraphicsSystem.create_default_pipeline()` (line 1073). It does NOT:
- Generate procedural material graphs
- Compile them via `compile_material_from_dict()`
- Create per-material pipelines
- Use the `ShaderCache`

The `GraphicsBridge` has a `create_material_pipeline()` method that calls `GraphicsSystem.create_material_pipeline()`, but it is never invoked by the game runner.

**Impact:** The entire procedural material system -- one of the more sophisticated subsystems with 30 integration tests -- produces no visible effect at runtime. All rendering uses a single hardcoded default pipeline with built-in shaders.

**Remediation:** The game runner should:
1. Generate material graphs for different biome types using `generate_material_graph()`
2. Compile them via `compile_material_from_dict()`
3. Cache results in `ShaderCache`
4. Create per-material pipelines and assign them to terrain chunks based on biome
5. Draw entities/terrain with the appropriate pipeline instead of always "default"

---

### 6. UI System -- ImGui Backend Partially Connected

**Severity: MODERATE**

**What exists:**
- **C++ ImGui bindings** in `engine.cpp`: 20+ ImGui functions (`imgui_begin`, `imgui_end`, `imgui_text`, `imgui_button`, `imgui_progress_bar`, `imgui_columns`, `imgui_image`, etc.)
- **Python `ImGuiBackend`** in `ui_system.py` (line 430): Wraps all C++ ImGui calls
- **Python `HeadlessUIBackend`** in `ui_system.py`: Records UI calls for testing
- **10 UI components**: HUD, DialogueBox, InventoryPanel, QuestLog, PauseMenu, SettingsPanel, DebugOverlay, ConsoleWindow, NotificationStack, Tooltip

**What's tested:**
- `tests/unit/test_ui_system.py` -- Tests UI components using HeadlessUIBackend

**Connection status:**
- The `GameRunner._init_ui()` method (line 929) tries to create an `ImGuiBackend`
- It attempts to initialize C++ ImGui via `self._graphics_bridge.init_imgui(handle)` (line 950)
- BUT this only works if the backend has a `sdl_window_handle` attribute
- The `SDL2Backend` class does NOT expose `sdl_window_handle` -- it's never set
- Therefore `init_imgui` is never successfully called

**Impact:** The UI system falls back to `HeadlessUIBackend` in all cases, meaning UI components render their logic but produce no visible output. The HUD, inventory, quest log, dialogue boxes, and debug overlay are all tested and functional in Python but never actually appear on screen.

**Remediation:**
1. Add `sdl_window_handle` property to `SDL2Backend` that returns the native window handle
2. Ensure `GraphicsBridge.init_imgui()` properly initializes the ImGui rendering context
3. Wire `UIManager.begin_frame()`/`end_frame()` into the render loop with the real ImGui backend

---

### 7. LOD (Level of Detail) Mesh Generation -- Tested but Never Used

**Severity: LOW**

**What exists in C++ (`cpp/props.cpp`):**
- `generate_lod()` -- Mesh simplification that reduces vertex count by a target ratio

**What's tested:**
- `tests/integration/test_cpp_props.py::test_generate_lod` -- Validates vertex reduction at 0.25 ratio
- `tests/integration/test_cpp_props.py::test_lod_deterministic` -- Deterministic LOD generation

**What the game loop uses:**
The `GameManagerBridge` returns a `lod_bias` field in `FrameDirective` (stored at `game_runner.py:1310`), but `self._current_lod_bias` is never read or applied. No code path calls `generate_lod()` on any mesh.

**Remediation:** When uploading entity meshes, apply LOD based on `_current_lod_bias` and distance from camera. Use `generate_lod()` to create simplified meshes for distant objects.

---

### 8. Virtual Texture System -- Stub Implementation

**Severity: LOW**

**What exists in C++ (`cpp/graphics.cpp`):**
- `VirtualTextureTile`, `PageTableEntry` -- Data structures
- `VirtualTextureCache` -- LRU cache management with `request_tile()`, `advance_frame()`, `clear()`
- `evict_lru()`, `load_tile()` -- Partially implemented (stub tile loading)

**What's tested:** No tests for virtual textures.

**What the game loop uses:** Nothing. The virtual texture system is internal to graphics.cpp and not exposed via pybind11.

**Remediation:** Complete the tile loading implementation, expose to pybind11, and integrate with the terrain material system for streaming textures.

---

### 9. 3D Physics World Container -- Never Used Despite Being Bound

**Severity: LOW**

**What exists in C++:**
- `PhysicsWorld3D` -- Full container with `add_body()`, `get_body()`, `step()`, `reset()`, `set_heightfield()`

**What's tested:**
- `tests/integration/test_cpp_physics.py::test_physics_world_basic` -- Tests PhysicsWorld (2D version)
- `tests/integration/test_cpp_physics.py::test_physics_world_with_heightfield` -- Tests heightfield integration

**What the game loop uses:**
Neither PhysicsWorld nor PhysicsWorld3D. The game loop manages physics bodies ad-hoc in `GameWorld.physics_step()` by constructing a flat list of `RigidBody3D` each frame and calling `step_physics_3d()`. There is no persistent physics world.

**Impact:** Bodies are created and destroyed every frame rather than being tracked persistently. This prevents optimizations like spatial caching, sleeping bodies, and incremental broad-phase updates.

**Remediation:** Use `PhysicsWorld3D` as a persistent container in `GameWorld`, adding/removing bodies as entities spawn/despawn rather than rebuilding the list each frame.

---

### 10. Behavior Trees -- Pure Python (By Design, No C++ Needed)

**Severity: INFORMATIONAL**

The behavior tree system (`procengine/game/behavior_tree.py`) is pure Python with 30+ unit tests. There is no C++ equivalent, and this is by design -- behavior trees are game logic that runs at NPC-tick frequency, not a performance bottleneck. No remediation needed.

---

### 11. Command System / Console -- Pure Python (By Design, No C++ Needed)

**Severity: INFORMATIONAL**

The command system (`procengine/commands/`) and console (`console.py`) are pure Python with 70+ unit tests. Console rendering is supposed to go through ImGui (see Finding #6), but the command execution layer itself is correctly Python-only. The console's `get_render_data()` method produces data for the UI system, which would display it if ImGui were connected.

---

### 12. Game API (Entities, Inventory, Quests, Dialogue) -- Pure Python (By Design)

**Severity: INFORMATIONAL**

The game entity hierarchy (`game_api.py`) with Player, NPC, Prop, Item, Inventory, Quest, EventBus, and GameWorld is pure Python with 60+ tests. This is by design -- game logic stays in Python for rapid iteration. No remediation needed.

---

## Summary Matrix

| Feature | Python Tests | C++ Impl | FFI Bound | Used in Game Loop | Status |
|---|---|---|---|---|---|
| Physics Engine (2D+3D) | 40+ unit tests | Full | Yes | **NO -- Python used instead** | CRITICAL |
| Terrain Generation | 9+ unit tests | Full | Yes | Partial (dual path) | HIGH |
| Engine State/Hot-Reload | 11 unit tests | Full | Yes | **NO** | MODERATE |
| Seed Registry | 4 unit tests | Full | Yes | **NO -- Python used** | MODERATE |
| Material Compilation | 2 unit tests | Full | Yes | **NO** | MODERATE |
| UI/ImGui Rendering | 32+ unit tests | Full | Yes | **Broken** (no window handle) | MODERATE |
| LOD Mesh Generation | 0 unit tests | Full | Yes | **NO** | LOW |
| Virtual Textures | 0 tests | Partial | No | **NO** | LOW |
| PhysicsWorld3D Container | 0 unit tests | Full | Yes | **NO** | LOW |
| Behavior Trees | 30+ unit tests | None | N/A | Yes (Python) | OK |
| Command/Console | 70+ unit tests | None | N/A | Yes (Python) | OK |
| Game API/Entities | 60+ unit tests | None | N/A | Yes (Python) | OK |
| Graphics Bridge | 20+ unit tests | Full | Yes | Yes | OK |
| Prop Mesh Generation | 30+ unit tests | Full | Yes | Yes (via GraphicsBridge) | OK |
| Chunk Management | 40+ unit tests | Full | Yes | Yes (hybrid) | OK |
| GameManager/Frame Budget | 10+ unit tests | Full | Yes | Yes | OK |

---

## Recommended Remediation Priority

### Priority 1 -- Critical (Performance + Correctness)
1. **Wire C++ physics into game loop** -- Replace Python `step_physics_3d()` with `procengine_cpp.step_physics_3d()` in `GameWorld.physics_step()`, with Python fallback
2. **Fix ImGui initialization** -- Add `sdl_window_handle` to SDL2Backend so the UI actually renders

### Priority 2 -- High (Eliminate Redundancy)
3. **Unify terrain generation path** -- Remove dual-path terrain generation; use C++ GameManager exclusively during LOADING state
4. **Integrate Engine class** -- Instantiate C++ Engine in GameRunner for state verification and hot-reload support

### Priority 3 -- Moderate (Feature Completion)
5. **Activate material system** -- Generate biome-specific material graphs and compile to per-material pipelines
6. **Apply LOD system** -- Use `generate_lod()` and `_current_lod_bias` for distance-based mesh simplification
7. **Use PhysicsWorld3D** -- Persistent physics world instead of per-frame body list reconstruction

### Priority 4 -- Low (Future Work)
8. **Complete virtual texture system** -- Finish tile loading, expose via FFI, integrate with material system

---

## Test Gap Analysis

The following test files verify C++ functionality that is never exercised during actual gameplay:

| Test File | Tests | Feature Tested | Runtime Status |
|---|---|---|---|
| `test_cpp_physics.py` | 12 | C++ physics engine | Dead code in runtime |
| `test_cpp_engine.py` | 2 | C++ Engine state management | Dead code in runtime |
| `test_cpp_seed_registry.py` | 5 | C++ SeedRegistry | Dead code (C++ GameManager uses internally) |
| `test_cpp_materials.py` | 30 | Material graph compilation | Dead code in runtime |

**Total: 49 integration tests verify C++ code that produces zero effect during gameplay.**

Additionally, the following Python unit tests verify features that are implemented but have no path to the actual rendered game:

| Test File | Tests | Feature Tested | Runtime Status |
|---|---|---|---|
| `test_engine.py` | 3 | Python Engine state | Never instantiated |
| `test_engine_determinism.py` | 1 | Engine determinism | Never verified |
| `test_hot_reload.py` | 7 | Hot-reload system | Never triggered |
| `test_materials.py` | 2 | Material graph gen | Generated but never compiled |
| `test_ui_system.py` | 32 | UI components | Render to HeadlessUIBackend only |

**Total: 45 additional unit tests verify features that do nothing visible at runtime.**

**Grand total: 94 tests (out of ~694) verify features that are disconnected from the actual game runtime.**

---

## Conclusion

The Procedural Engine v2 has a well-engineered C++ backend with comprehensive test coverage, but approximately **13.5% of all tests** verify functionality that is completely disconnected from the game loop. The most impactful gap is the physics engine -- a full C++ sequential impulse solver sits unused while the game runs an equivalent Python implementation at significantly lower performance.

The root cause is architectural: the Python game loop was developed as a self-contained system with its own implementations, while the C++ backend was developed in parallel. The FFI bindings exist and the integration tests prove they work, but the game runner was never updated to prefer C++ implementations over Python ones. The result is a system where Python tests pass, C++ integration tests pass, but the actual game runs on Python for every major subsystem except graphics rendering and chunk scheduling.
