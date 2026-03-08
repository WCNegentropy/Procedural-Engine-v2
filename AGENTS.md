# AGENTS.md — Procedural Game Engine v2

## Purpose
This document binds every human contributor and automated agent (e.g., Claude Code, CI bots) to the core constraints, architecture, and best-practice workflow of the Procedural Game Engine.
Paste this file into the root of the game-studio repository so that any context-aware tools inherit these rules automatically.

---

## 1 · Guiding Principles
- **Determinism First** — All runtime output must be a pure function of the designated seeds and engine version. No hidden randomness or non-replayable state.
- **Hybrid Discipline** — Python = author-time generators, game logic, & tooling; C++ = real-time execution & rendering. Cross only at the defined FFI API.
- **One Source of Truth** — The RootSeed governs every subsystem via the SeedRegistry; diverging PRNGs are forbidden.
- **Immutability After Hand-Off** — Once a buffer crosses the Python to C++ boundary, its contents are read-only. C++ mutates runtime state via ECS, never the original generator data.
- **Fail Fast, Fail Loud** — Any determinism hash mismatch, FPS regression, or physics NaN terminates the build or CI run.
- **Build Locked** — Do not modify CMakeLists.txt, build workflows, or dependencies. All changes must be file-level Python/C++ edits only.

---

## 2 · Language Ownership Matrix

| Subsystem         | Python Responsibilities | C++ Responsibilities |
|-------------------|--------------------------|-----------------------|
| **Seeds & PRNG**  | Call `SeedRegistry.get_subseed()`; never instantiate local RNGs. | Master `SeedRegistry`, expose PCG64 stream to Python via FFI. |
| **Terrain**       | Height/Biome/River mask generation, macro-plates, simplex FBM, biome LUT. | GeoClipmap mesh, GPU erosion, collider heightfield. |
| **Chunks**        | ChunkManager load/unload logic, ChunkedHeightField, entity lifecycle. | Terrain mesh upload, vertex data. |
| **Props & Creatures** | Generate JSON descriptors (CSG trees, L-systems, genomes). | Mesh synthesis, LODs, skeleton rigs, GPU upload. |
| **Materials**     | Emit material graph DSL (JSON). | DSL to SPIR-V compile, virtual texture paging. |
| **Physics**       | 3D hybrid solver, ChunkedHeightField sampling, sim-distance filtering. | Bullet-style solver, fluid voxels, wind fields. |
| **Game Logic**    | GameWorld, entities, quests, dialogue, behavior trees, commands. | (Future: native game loop) |
| **UI**            | Dear ImGui orchestration (UIManager, components, headless backend). | ImGui rendering via Vulkan backend. |
| **Testing/Tooling** | Seed mining, dashboards, live editors. | Headless mode, hot-reload endpoint. |

---

## 3 · Determinism Contract
- Use **PCG64** for every random sample.
- Fixed dt = 1/60 s physics step.
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
- Run the active pytest paths (`tests/unit` plus `tests/integration/test_world.py`) before submitting Python-side changes, and run the native integration subset after building `procengine_cpp`.
- The GitHub Actions workflow currently runs on Python 3.12 and builds/packages the project across Linux, Windows, and macOS; keep these jobs green.
- Each commit must leave the repository in a clean state with all checks passing.
- Maintain the root `requirements.txt` with all core dependencies (currently `numpy` and `pytest`).
- Respect the repository `.gitignore`; avoid committing build artifacts or virtual environments.

---

## 5.1 · Repository Structure

```
/
├── procengine/                 # CORE PYTHON PACKAGE
│   ├── __init__.py             # Version, public API exports
│   ├── core/                   # Engine fundamentals
│   │   ├── engine.py           # Determinism-tracking reference engine
│   │   └── seed_registry.py    # Hierarchical PRNG (splitmix64 → PCG64)
│   ├── world/                  # World generation
│   │   ├── terrain.py          # Heightmap, biomes, erosion
│   │   ├── chunk.py            # ChunkManager, ChunkedHeightField
│   │   ├── props.py            # Rock, tree, building generators
│   │   ├── materials.py        # Material graph DSL
│   │   └── world.py            # Multi-chunk assembly
│   ├── physics/                # Physics system
│   │   ├── bodies.py           # RigidBody, RigidBody3D, Vec3
│   │   ├── collision.py        # Sequential impulse solver
│   │   └── heightfield.py      # HeightField, HeightField2D
│   ├── game/                   # Runtime game systems
│   │   ├── game_api.py         # GameWorld, Entity hierarchy, Events
│   │   ├── game_runner.py      # Main game loop, chunk orchestration, rendering
│   │   ├── behavior_tree.py    # NPC behavior trees
│   │   ├── player_controller.py # Input & camera system
│   │   ├── data_loader.py      # JSON data loading
│   │   └── ui_system.py        # Dear ImGui UI (HUD, dialogue, inventory, console)
│   ├── managers/               # Runtime scheduling bridge
│   │   └── game_manager.py     # GameManagerBridge + FrameDirective fallback
│   ├── commands/               # Command system
│   │   ├── commands.py         # Command registry (52 registered commands)
│   │   ├── console.py          # In-game console
│   │   └── handlers/           # Command implementations
│   │       └── game_commands.py # Game-specific commands
│   ├── agents/                 # NPC AI framework (LocalAgent → MCP)
│   └── graphics/               # Rendering bridge
│       └── graphics_bridge.py  # Vulkan/headless abstraction
│
├── cpp/                        # C++ NATIVE BACKEND
│   ├── CMakeLists.txt
│   ├── engine.cpp              # Pybind11 module definition + bindings
│   ├── graphics.h / graphics.cpp # Vulkan rendering backend
│   ├── terrain.h / terrain.cpp # Heightmap → mesh + biome colors
│   └── props.h / props.cpp     # Mesh generators (rock, tree, building, creature)
│
├── tests/                      # ACTIVE TEST SUITE
│   ├── conftest.py             # Pytest configuration
│   ├── unit/                   # Python-side tests used by CI
│   │   └── test_*.py
│   ├── integration/            # Native/hybrid tests used by CI
│   │   └── test_*.py
│   └── performance/            # Performance tests
│
├── data/                       # GAME CONTENT (JSON)
│   ├── npcs/                   # NPC definitions (6 village NPCs)
│   ├── quests/                 # Quest definitions (6 quests)
│   └── items/                  # Item definitions (18 items)
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

**All imports must use fully-qualified `procengine.*` paths:**
```python
from procengine import Engine, SeedRegistry, generate_terrain_maps
from procengine.physics import RigidBody, step_physics
from procengine.game import GameWorld, Player
from procengine.world.chunk import ChunkManager, ChunkedHeightField
from procengine.commands.commands import CommandRegistry
```

Bare imports (`from physics import ...`) will fail at runtime due to the namespace package structure.

---

## 6 · Implementation Status

### Phase 1: Physics Upgrade
- ✅ Vec3, RigidBody3D, HeightField2D (Python + C++)
- ✅ step_physics_3d with hybrid 2D+height approach
- ✅ NO_GRAPHICS CMake option for headless builds
- ✅ 67 physics tests

### Phase 2: Game Loop & NPC Framework
- ✅ GameWorld, Entity hierarchy, Event system (`game_api.py`)
- ✅ Full behavior tree system with decorators (`behavior_tree.py`)
- ✅ Input abstraction and camera system (`player_controller.py`)
- ✅ JSON data loading for NPCs, quests, items (`data_loader.py`)
- ✅ Game loop orchestration with physics (`game_runner.py`)
- ✅ Save/load serialization (JSON, file I/O)

### Phase 2.5: Graphics, UI & Dynamic World
- ✅ Vulkan rendering pipeline with biome terrain colors
- ✅ Biome-specific material pipelines generated in Python and compiled/applied via C++
- ✅ Entity mesh generation and rendering
- ✅ Dear ImGui UI system with 9 components plus headless backend (`ui_system.py`)
- ✅ Dynamic chunk-based infinite world streaming (`chunk.py`)
- ✅ `GameManagerBridge` / `FrameDirective` integration for async chunk scheduling and frame-budget hints
- ✅ LOADING/PLAYING state machine with mesh verification
- ✅ Render-distance entity culling in dynamic mode
- ✅ Simulation-distance filtering for NPC updates and physics
- ✅ Closest-first chunk load ordering
- ✅ Entity lifecycle tied to chunk load/unload (no orphaned entities)
- ✅ ChunkedHeightField for cross-chunk physics

### Phase 3: MCP Integration
- ⏳ Pending — MCP server, MCPAgent, Game Master mode

### Phase 4: Command Architecture
- ✅ Command registry with 52 registered commands across 11 defined categories (`commands.py`)
- ✅ In-game console with autocomplete (`console.py`)
- ✅ Keybind system with configurable binds
- ✅ Access control levels: PUBLIC, CONSOLE, CHEAT, DEV
- ✅ MCP tool generation from command registry
- ✅ Graphics bridge with headless fallback (`graphics_bridge.py`)

---

## 7 · Graphics Implementation Status

The Vulkan graphics backend is **fully operational** with complete rendering pipeline.
Headless mode remains fully functional for testing and CI.

| Component | File | Status | Description |
|-----------|------|--------|-------------|
| `draw_mesh()` | cpp/graphics.cpp | ✅ Complete | Full vkCmdDraw with pipeline/descriptor binding |
| `create_pipeline()` | cpp/graphics.cpp | ✅ Complete | VkPipeline with shader modules |
| Render passes | cpp/graphics.cpp | ✅ Complete | Depth prepass + forward pass |
| Framebuffers | cpp/graphics.cpp | ✅ Complete | VkFramebuffer for swapchain and headless |
| Swapchain | cpp/graphics.cpp | ✅ Complete | Full management with resize support |
| Uniform buffers | cpp/graphics.cpp | ✅ Complete | Per-frame view/projection/camera |
| Push constants | cpp/graphics.cpp | ✅ Complete | Per-draw model transforms and color |
| Default shaders | cpp/graphics.cpp | ✅ Complete | Basic diffuse lighting shaders |
| Biome colors | cpp/terrain.cpp | ✅ Complete | 16-biome color palette with vertex colors |
| Entity meshes | cpp/props.cpp | ✅ Complete | Capsule, cylinder, box, rock, tree mesh generation |

### Rendering Pipeline

1. **begin_frame()** - Acquire swapchain image, reset command buffer
2. **draw_mesh()** - Queue draw commands with transforms
3. **end_frame()** - Record render pass, submit, present

### Entity Rendering in Dynamic Mode

When `enable_dynamic_chunks` is active, entity rendering is filtered by chunk distance:
- **Player**: Always rendered regardless of distance
- **Render-distance entities**: Only entities belonging to loaded render-distance chunks are drawn
- **Sim-distance entities**: Only entities in sim-range chunks have physics/AI updates
- **Static mode fallback**: All entities rendered (original behavior)

### Entity Mesh Types

| Entity Type | Mesh | Color |
|------------|------|-------|
| Player | Capsule | Skin tone (0.85, 0.65, 0.55) |
| NPC | Capsule | Darker skin tone (0.75, 0.60, 0.50) |
| Rock | Sphere with noise displacement | Gray (0.55, 0.50, 0.45) |
| Tree | L-system sweep mesh | Brown bark (0.45, 0.35, 0.25) |
| Building | Box | Stone (0.70, 0.65, 0.60) |

---

## 8 · Dynamic Chunk System

The engine uses a chunk-based streaming system for infinite procedural worlds.

### ChunkManager (`procengine/world/chunk.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 64 | World units per chunk side |
| `render_distance` | 6 | Chunk radius for rendering |
| `sim_distance` | 3 | Chunk radius for physics/AI simulation |
| `unload_buffer` | 2 | Extra chunks before unloading |

### State Machine

```
LOADING → PLAYING
```

- **LOADING**: Progressively generates chunks around spawn. Transitions to PLAYING only when the load queue is empty (or minimum chunks met) AND all sim-distance chunks have `is_mesh_uploaded == True`.
- **PLAYING**: Player can move. Chunks dynamically load/unload around the player position. Load queue sorted closest-first for immediate visual feedback.

### Entity Lifecycle

- **On chunk load**: Terrain generated, mesh uploaded, props spawned as entities tracked in `chunk.entity_ids`
- **On chunk unload**: Terrain mesh destroyed, all chunk entities despawned from GameWorld, cached entity meshes cleaned up
- No orphaned entities: every entity is tied to a chunk and cleaned up on unload

### Performance Characteristics

- Load queue: 1 chunk/frame during PLAYING, 4 chunks/frame during LOADING
- Unload queue: 2 chunks/frame
- sim_set calculation: hoisted outside per-chunk loop (calculated once per batch)
- Vertex overlap: chunk_size + 1 for seamless mesh stitching between neighbors

---

## 9 · Command System

### Architecture (`procengine/commands/`)

The command system provides a unified control surface for console, GUI, keybinds, and future MCP integration.

| Component | File | Description |
|-----------|------|-------------|
| `CommandRegistry` | commands.py | Central registry with execute(), autocomplete(), get_mcp_tools() |
| `Console` | console.py | In-game console with input history and autocomplete |
| `game_commands` | handlers/game_commands.py | Game-specific command implementations |

### Access Levels

| Level | Description |
|-------|-------------|
| PUBLIC | Always available (movement, inventory, dialogue) |
| CONSOLE | Requires console open (spawn, teleport, modify) |
| CHEAT | Requires `system.cheats 1` (god mode, give items) |
| DEV | Requires `system.dev 1` (debug, hot-reload) |

### Categories

world, terrain, props, npc, player, physics, engine, quest, ui, system, debug

---

## 10 · Common Pitfalls & Lessons Learned

### 1. Bare Module Imports
**Problem**: `from physics import X` fails with `No module named 'physics'`.
**Fix**: Always use `from procengine.physics import X`.

### 2. World-Size Scaling in Descriptors
**Problem**: Rock radius was `uniform(0.1, 0.5) * world_size`, making rocks world-sized.
**Rule**: Prop sizes should be absolute values, not scaled by terrain dimensions.

### 3. Entity State Threading for Mesh Generation
**Problem**: `upload_entity_mesh()` used placeholder primitives because it lacked entity state.
**Fix**: Pass `entity_state` dict through the pipeline so the mesh generator can use descriptor parameters.

### 4. Orphaned Entities on Chunk Unload
**Problem**: When chunks unloaded, only terrain mesh was destroyed. Entity objects accumulated in GameWorld forever.
**Fix**: `_cleanup_chunk()` in game_runner.py now destroys all chunk entities and their cached meshes on unload.

### 5. Entity Rendering Without Distance Filtering
**Problem**: `_render_entities()` iterated ALL entities regardless of distance, wasting GPU draw calls.
**Fix**: In dynamic mode, only entities in render-distance chunks are drawn. Player is always rendered.

### 6. NPC/Physics Ignoring Simulation Distance
**Problem**: `_update_npcs()` and `physics_step()` processed ALL entities even when dynamic chunks were active.
**Fix**: Both now use `get_entities_in_sim_range()` to filter to sim-distance entities. Player always included in physics.
