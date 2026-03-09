# FFI Remediation Report: Current Python ↔ C++ Runtime Gaps

**Date:** 2026-03-08  
**Scope:** Refresh audit of the active runtime wiring in `procengine`, `procengine_cpp`, and the current documentation set

---

## Architecture Context

The current engine split is now clearer than the earlier draft documented:

- **Python** owns game logic, world orchestration, behavior trees, UI state, command handling, and deterministic descriptor generation
- **C++** owns rendering, material compilation, native mesh generation, async chunk scheduling, and native helper/container types
- **`GameRunner`** now drives both `GraphicsBridge` and `GameManagerBridge`, so several previously disconnected native paths are now live at runtime

This report therefore focuses on the **remaining** runtime gaps, and also records
which earlier remediation items have since been connected.

---

## Resolved Since the Previous Draft

### 1. Material Compilation and Material Pipelines Are Now Connected

This is no longer an FFI gap for terrain rendering.

- `procengine/game/game_runner.py:1128-1149` now generates deterministic biome material graphs, compiles them through `procengine_cpp.compile_material_from_dict()`, and registers the result through `GraphicsBridge.create_material_pipeline()`
- `procengine/game/game_runner.py:1425-1473` selects those biome pipelines per rendered chunk, with fallback to the default pipeline
- `procengine/graphics/graphics_bridge.py:871-903` stores and creates those pipelines through the native graphics system

**Status:** Connected.  
**Remaining limitation:** entity rendering still relies on the default pipeline and per-mesh colors rather than per-entity material graphs.

### 2. GameManager / FrameDirective Integration Is Live

The native runtime scheduler is now used by gameplay.

- `procengine/managers/game_manager.py` provides `GameManagerBridge`, `ManagerConfig`, and a Python `FrameDirective` fallback
- `procengine/game/game_runner.py:827-838` instantiates that bridge
- `procengine/game/game_runner.py:1368-1375` consumes native frame directives, including chunk budgets, physics skipping, and `lod_bias`
- `procengine/game/game_runner.py:1972-1974` notifies the native manager when chunk meshes have been uploaded

**Status:** Connected.  
**Remaining limitation:** `lod_bias` is stored but still not applied to generated meshes.

### 3. Full Building and Creature Mesh Paths Are Reachable at Runtime

The older report said buildings rendered only as boxes and creatures had no runtime path. That is now outdated.

- `procengine/graphics/graphics_bridge.py:704-725` generates creature meshes from metaball/skeleton descriptors and building meshes from BSP descriptors when state is present
- `procengine/game/game_runner.py:2117-2126` spawns creature props with the descriptor state needed by that mesh path

**Status:** Connected.  
**Remaining limitation:** these richer paths depend on the relevant descriptor state being present; fallback primitives still exist for missing/invalid state.

### 4. Expanded Prop Families Are Wired Through the Runtime

The runtime now goes well beyond rocks/trees/buildings:

- `procengine/world/props.py` generates descriptors for bush, pine tree, dead tree, fallen log, boulder cluster, flower patch, mushroom, cactus, building, and creature props
- `procengine/game/game_runner.py:2007-2126` spawns those descriptor types as `Prop` entities
- `procengine/graphics/graphics_bridge.py:600-725` routes them into dedicated native mesh generators

**Status:** Connected.

---

## Remaining Verified Gaps

### 1. Engine State Tracking / Hot-Reload Still Does Not Participate in Gameplay

**Files involved:**
- `procengine/core/engine.py`
- `cpp/engine.cpp`
- `main.py`

**Current state:**
- `main.py` still instantiates the engine for CLI-oriented flows such as generation/benchmarking
- `GameRunner` does not instantiate either the Python or C++ `Engine`
- there is still no gameplay command path that calls `Engine.hot_reload()`
- `snapshot_state()` remains a tested determinism utility rather than an in-game runtime feature

**Gap:** the engine-level queueing, hot-reload, and state snapshot features remain outside the actual gameplay loop.

### 2. LOD Simplification Infrastructure Still Stops at `lod_bias`

**Files involved:**
- `cpp/props.cpp` / `cpp/engine.cpp` (`generate_lod`)
- `cpp/game_manager.cpp` / `cpp/game_manager.h` (`FrameDirective.lod_bias`)
- `procengine/game/game_runner.py`

**Current state:**
- the C++ side computes and exposes `lod_bias`
- `GameRunner` stores that value in `_current_lod_bias`
- no Python runtime path calls `generate_lod()` or otherwise simplifies already-built meshes based on that bias

**Gap:** LOD guidance is connected, but mesh simplification is still not applied at runtime.

### 3. `PhysicsWorld` / `PhysicsWorld3D` Containers Remain Test-Only

**Files involved:**
- `cpp/physics.cpp`
- `cpp/engine.cpp`

**Current state:**
- the gameplay loop intentionally uses the Python hybrid 2D+height physics implementation
- the native container-style physics worlds are still only exercised by tests

**Architecture decision:** the Python hybrid 2D+height physics implementation is the intentional runtime path. The native container-style physics worlds serve as tested building blocks for potential future native physics migration, but the current architecture deliberately uses the Python implementation for flexibility and determinism control. This is not a gap.

### 4. Cone and Plane Primitive Helpers — Utility Reserve

**Files involved:**
- `cpp/props.cpp`
- `tests/integration/test_mesh_generation.py`

**Current state:**
- `generate_capsule_mesh()`, `generate_cylinder_mesh()`, `generate_box_mesh()`, and many descriptor-driven generators are used at runtime
- `generate_cone_mesh()` and `generate_plane_mesh()` are still only covered in tests/utilities

**Architecture decision:** these are intentionally available as tested utility primitives for future prop types (e.g., pine trees already use cone meshes internally). Their presence in the test suite validates they work correctly; they will be called from runtime code when new prop types need them. This is not a gap.

### 5. `Engine.generate_terrain()` vs Chunk Orchestration — Separate API Paths

**Files involved:**
- `main.py`
- `procengine/game/game_runner.py`
- `cpp/engine.cpp`

**Current state:**
- CLI-oriented generation uses the engine wrapper for batch generation
- gameplay terrain generation uses `generate_terrain_standalone()` / chunk orchestration paths for dynamic streaming

**Architecture decision:** the engine-member terrain API and the chunk orchestration API serve different purposes by design. The engine wrapper is for CLI batch generation and determinism verification. The chunk orchestration path is for runtime streaming with per-chunk seeds and progressive loading. Having both is intentional and not a gap.

---

## Summary Table

| Feature / API | Runtime status | Notes |
|---|---|---|
| Biome material compilation + pipelines | **Connected** | Terrain chunks now use compiled biome pipelines |
| GameManager / FrameDirective scheduling | **Connected** | Async chunk scheduling and frame budgets are live |
| Building mesh generation | **Connected** | Uses BSP descriptor path when state is available |
| Creature mesh generation | **Connected** | Uses metaball/skeleton path with fallback mesh |
| Expanded prop generator families | **Connected** | Bush, pine, dead tree, fallen log, cactus, etc. |
| Engine hot-reload / snapshot gameplay use | **Still disconnected** | Tested utility, not used in `GameRunner` |
| Runtime LOD simplification | **Still disconnected** | `lod_bias` is stored but not applied |
| PhysicsWorld / PhysicsWorld3D containers | **Architecture decision** | Python physics is the intentional runtime path |
| Cone / plane primitive helpers | **Architecture decision** | Utility reserve for future prop types |
| `Engine.generate_terrain()` in gameplay | **Architecture decision** | CLI batch vs runtime streaming are separate by design |

---

## What Is Working Correctly

These Python ↔ C++ connections are verified as live in the current runtime:

| System | Connection |
|---|---|
| Terrain mesh upload | Python chunk generation -> C++ terrain mesh generation -> GPU upload |
| Biome material pipelines | Python graph generation -> C++ material compilation -> runtime pipeline selection |
| Async chunk scheduling | `GameRunner` -> `GameManagerBridge` -> native worker threads / directives |
| Native prop mesh generation | Python descriptors -> C++ mesh generators for active prop families |
| Building / creature runtime meshes | Descriptor threading now reaches the native builders |
| Vulkan rendering | Python draw orchestration -> native graphics backend |
| ImGui backend | Python UI state -> C++ ImGui bindings |

---

## Recommended Next Remediation Priorities

### Priority 1 — Apply LOD at Runtime
Use `_current_lod_bias` from `FrameDirective` to simplify distant prop meshes or swap lower-detail variants.

### Priority 2 — Integrate Engine State Tracking into Gameplay
Instantiate the engine in `GameRunner`, feed terrain/descriptor changes into it, and expose hot-reload or snapshot flows through commands/debug tooling.

### Architectural Decisions (Not Gaps)

The following items were previously listed as remediation priorities but are
intentional architecture decisions and do not require action:

- **Native physics containers (PhysicsWorld / PhysicsWorld3D):** The Python
  hybrid physics implementation is the intentional runtime path. Native
  containers are tested building blocks for potential future migration.
- **Cone / plane primitive helpers:** Utility reserve for future prop types.
  Already tested and available when needed.
- **Engine.generate_terrain() vs chunk orchestration:** CLI batch generation
  and runtime streaming are separate APIs by design.
