# Procedural Engine v2 -- Architecture & Development Reference

> Compiled 2026-03-08. Covers the full Python/C++ hybrid engine, CI pipeline,
> rendering stack, dynamic chunk system, prop generation, command architecture,
> and conventions discovered during development.

---

## 1. Repository Layout

```
Procedural-Engine-v2/
├── main.py                      # CLI entry point (procedural-engine command)
├── pyproject.toml               # Build config, deps, lint/type settings
├── setup.py                     # CMake-based C++ extension build
├── procengine/                  # Python package (9 top-level subpackages)
│   ├── __init__.py              # 53 public exports, barrel-style
│   ├── core/                    # Engine fundamentals
│   │   ├── engine.py            # Determinism-tracking reference engine
│   │   └── seed_registry.py     # Hierarchical PRNG (splitmix64 → PCG64)
│   ├── world/                   # Content generation
│   │   ├── terrain.py           # FBM + erosion heightmaps
│   │   ├── chunk.py             # ChunkManager, ChunkedHeightField
│   │   ├── props.py             # Rock/tree/building/creature descriptors
│   │   ├── materials.py         # Material graph generation
│   │   └── world.py             # World orchestration
│   ├── physics/                 # Pure-Python 3D physics
│   │   ├── bodies.py            # Vec3, RigidBody, RigidBody3D
│   │   ├── collision.py         # step_physics, step_physics_3d
│   │   └── heightfield.py       # HeightField, HeightField2D
│   ├── game/                    # Runtime game systems
│   │   ├── game_api.py          # GameWorld, Entity hierarchy, Events
│   │   ├── game_runner.py       # Main loop, menu flow, chunk orchestration, rendering
│   │   ├── player_controller.py # Camera, player input
│   │   ├── behavior_tree.py     # BT nodes (Selector, Sequence, etc.)
│   │   ├── data_loader.py       # JSON content loader (NPCs, quests, items)
│   │   └── ui_system.py         # Dear ImGui UI (main menu, world creation, save/load, HUD, dialogue, inventory, console, debug)
│   ├── managers/                # Runtime bridges for C++ scheduling/streaming
│   │   └── game_manager.py      # GameManagerBridge, ManagerConfig, FrameDirective
│   ├── graphics/                # Rendering abstraction
│   │   └── graphics_bridge.py   # Mesh upload, draw calls, camera, lighting
│   ├── agents/                  # NPC AI framework (LocalAgent → MCP)
│   ├── commands/                # Command system
│   │   ├── commands.py          # Command registry (52 registered commands)
│   │   ├── console.py           # In-game console with autocomplete
│   │   └── handlers/            # Game command implementations
│   │       └── game_commands.py
│   └── utils/                   # Utilities (seed_sweeper)
├── cpp/                         # C++ pybind11 extension
│   ├── CMakeLists.txt           # CMake build (Vulkan, shaderc, OpenSSL)
│   ├── engine.cpp               # Pybind11 module definition + bindings
│   ├── props.h / props.cpp      # Mesh generators (rock, tree, building, creature)
│   ├── terrain.h / terrain.cpp  # Heightmap → mesh + biome colors
│   └── graphics.h / graphics.cpp # Vulkan rendering backend
├── tests/
│   ├── conftest.py              # sys.path setup for both Python-only and C++ tests
│   ├── unit/                    # Active Python-side suite
│   └── integration/             # Active C++/hybrid integration suite
├── data/                        # Game content JSON files
│   ├── npcs/                    # NPC definitions (6 village NPCs)
│   ├── quests/                  # Quest definitions (6 quests)
│   └── items/                   # Item definitions (18 items)
├── Legacy/                      # Pre-restructure code (DO NOT import from)
└── .github/workflows/ci.yml     # Cross-platform CI/CD
```

---

## 2. Package & Import Conventions

### Naming Rules

| Scope | Convention | Example |
|-------|-----------|---------|
| Python package | `procengine.<subpackage>` | `from procengine.physics import Vec3` |
| C++ module | `procengine_cpp` | `import procengine_cpp as cpp` |
| Test files | `test_<module>.py` | `tests/unit/test_physics_3d.py` |
| CI branches | `claude/<description>-<id>` | `claude/fix-linux-ci-tests-49rmK` |

### Import Rules (Critical)

All imports within the active codebase **must** use the fully-qualified `procengine.*` path:

```python
# CORRECT
from procengine.physics import Vec3, HeightField2D
from procengine.game.game_api import GameWorld, Entity
from procengine.world.chunk import ChunkManager, ChunkedHeightField

# WRONG -- causes "No module named 'physics'" at runtime
from physics import Vec3           # bare module name
from game.game_api import Entity   # relative without procengine prefix
```

### Lazy/Runtime Imports

Several files use deferred imports inside functions. These are easy to miss
during refactoring because they only fail when that code path executes:

- `procengine/game/player_controller.py` -- `_resolve_terrain_collision()`
- `procengine/game/behavior_tree.py` -- `create_patrol_behavior()`, `create_guard_behavior()`
- `procengine/game/game_runner.py` -- `_setup_terrain()`, `_setup_props()`

When renaming or restructuring, always search for runtime imports:
```bash
rg "from procengine" --type py    # find all current imports
rg "^\s+from\s+\w" --type py     # find indented (runtime) imports
```

### Legacy Directory

`Legacy/` contains pre-restructure code with 17+ bare `from physics import` etc.
**Never import from Legacy/**. It exists only for historical reference.

---

## 3. Build System

### Python Package

- **Build backend**: setuptools
- **Python**: >=3.10 (supported in packaging metadata; CI currently exercises 3.12)
- **Runtime dependency**: numpy>=1.24 (the only required dependency)
- **Dev dependencies**: pytest, ruff, mypy, numpy-stubs
- **Entry point**: `procedural-engine = "main:main"`

### C++ Extension (`procengine_cpp`)

Built via CMake through `setup.py`:

```
setup.py → CMakeExtension("procengine_cpp", sourcedir="cpp")
         → CMakeBuild invokes cmake configure + build
         → Produces procengine_cpp.{so,pyd,dylib}
```

**Platform-specific build notes**:

| Platform | Vulkan SDK | SSL | Output |
|----------|-----------|-----|--------|
| Linux | libvulkan-dev + validation-layers | libssl-dev | `procengine_cpp.*.so` |
| Windows | LunarG SDK v1.3.290.0 | Chocolatey openssl | `procengine_cpp.*.pyd` |
| macOS | MoltenVK via Homebrew | Homebrew openssl | `procengine_cpp.*.dylib` |

**CMake headless mode**: Build without graphics via `-DNO_GRAPHICS=ON` for
server/testing environments.

### Building Locally

```bash
# Install build deps
pip install pybind11 cmake ninja numpy

# Build C++ extension
python setup.py build_ext --inplace

# Or via pip
pip install -e ".[dev]"
```

---

## 4. CI/CD Pipeline (`.github/workflows/ci.yml`)

### Job Overview

| Job | Platform | Purpose |
|-----|----------|---------|
| `lint` | Ubuntu | ruff lint, ruff format, mypy (all `continue-on-error`) |
| `test-python` | Ubuntu | Unit tests (`tests/unit/`) + select integration |
| `build-linux` | Ubuntu | CMake build + integration tests |
| `build-windows` | Windows | CMake build + integration tests |
| `build-macos` | macOS | CMake build + integration tests |
| `build-standalone` | Matrix (all 3) | PyInstaller packaging |

### Integration Test Suite

All three platform builds run the **same** integration test set:

```bash
python -m pytest \
  tests/integration/test_cpp_engine.py \
  tests/integration/test_cpp_terrain.py \
  tests/integration/test_cpp_physics.py \
  tests/integration/test_cpp_props.py \
  tests/integration/test_cpp_materials.py \
  tests/integration/test_cpp_seed_registry.py \
  -v --tb=short
```

With `continue-on-error: true` to prevent C++ build failures from blocking
the rest of the pipeline.

### Artifact Chain

Platform builds produce native modules -> `build-standalone` downloads them ->
PyInstaller packages everything into distributable archives (tar.gz / zip).
Artifacts retained for 7 days.

### Release Workflow (`.github/workflows/release.yml`)

- Builds platform wheels on Linux, Windows, and macOS
- Builds standalone executables with bundled game data
- Uses the same Python 3.12 toolchain as CI
- Targets tag pushes (`v*`) and manual workflow dispatch

---

## 5. Rendering Pipeline

### Architecture

```
main.py → GameRunner → GraphicsBridge → procengine_cpp.GraphicsSystem (Vulkan)
```

### GraphicsBridge (`procengine/graphics/graphics_bridge.py`)

The bridge abstracts Vulkan into a simple mesh/pipeline/draw API:

| Method | Purpose |
|--------|---------|
| `initialize()` | Create Vulkan instance, surface, swapchain (or headless) |
| `upload_terrain_mesh()` | Heightmap → C++ mesh → GPU upload |
| `upload_entity_mesh()` | Entity type + state → C++ mesh → GPU upload |
| `draw_mesh()` | Queue draw call with transform matrix |
| `draw_entity()` | Convenience: position/rotation/scale → transform → draw |
| `destroy_mesh()` | Free GPU resources for a mesh |
| `begin_frame()` / `end_frame()` | Frame lifecycle |

### Biome Material Pipelines

`GameRunner` now connects the Python material graph DSL to the C++ material
compiler at runtime for terrain rendering:

1. `generate_material_graph()` produces a deterministic graph per biome
2. `procengine_cpp.compile_material_from_dict()` compiles GLSL sources
3. `GraphicsBridge.create_material_pipeline()` registers GPU pipelines
4. Terrain chunks select a biome-specific pipeline with fallback to `default`

### Windowed Rendering (SDL2 + Vulkan)

Three-phase initialization:
1. Get Vulkan extensions from SDL2 window
2. Create Vulkan instance with those extensions
3. Create surface from SDL2 window handle, complete swapchain setup

Falls back to headless mode at any failure point.

### Transform Matrices

Column-major 4x4 matrices (16 floats). Composition order: **Scale -> Rotate -> Translate**.

```python
# Matrix utilities in graphics_bridge.py
create_translation_matrix(x, y, z)
create_rotation_y_matrix(angle)
create_scale_matrix(sx, sy, sz)
create_transform_matrix(position, rotation_y, scale)  # combines all three
```

### Entity Colors

Defined in `ENTITY_COLORS` dict in `graphics_bridge.py`:

| Entity Type | RGB | Description |
|------------|-----|-------------|
| `player` | (0.85, 0.65, 0.55) | Skin tone |
| `npc` | (0.75, 0.60, 0.50) | Darker skin tone |
| `rock` | (0.55, 0.50, 0.45) | Gray rock |
| `tree` | (0.45, 0.35, 0.25) | Brown bark |
| `building` | (0.70, 0.65, 0.60) | Stone |
| default | (0.60, 0.60, 0.60) | Neutral gray |

Colors are applied via `mesh.set_uniform_color()` before GPU upload.

---

## 6. Dynamic Chunk System

### Overview

The engine uses a chunk-based streaming system for infinite procedural worlds.
Chunks are generated, loaded, and unloaded dynamically as the player moves.

```
ChunkManager (procengine/world/chunk.py)
  ├── Chunk generation (terrain, biomes, props)
  ├── Load queue (sorted closest-first)
  ├── Unload queue (outside render_distance + unload_buffer)
  ├── Prop queue (props generated at half render distance)
  └── ChunkedHeightField (physics across chunk boundaries)

GameRunner (procengine/game/game_runner.py)
  ├── LOADING state → progressive chunk generation
  ├── PLAYING state → dynamic load/unload around player
  ├── Entity lifecycle tied to chunks
  └── Render-distance entity culling
```

### ChunkManager Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 64 | World units per chunk side |
| `render_distance` | 6 | Chunk radius for terrain rendering |
| `sim_distance` | 3 | Chunk radius for physics/AI simulation |
| `unload_buffer` | 2 | Extra chunks kept before unloading |

### Chunk Class

Each `Chunk` stores:
- `coord`: (x, z) tuple in chunk space
- `heightmap`, `biome_map`, `river_map`, `slope_map`: numpy arrays (chunk_size+1 for vertex overlap)
- `mesh_id`: GPU mesh identifier
- `entity_ids`: set of entity IDs spawned in this chunk
- `is_loaded`, `is_mesh_uploaded`, `is_simulating`, `has_props`: state flags

### State Machine (GameRunner)

```
MAIN_MENU → WORLD_CREATION → LOADING → PLAYING
              ↕ (back)                    ↕ (pause)
          SAVE_LOAD ←──────────────── PAUSED → (quit) → MAIN_MENU
```

**MAIN_MENU state**:
- Application entry point. No world exists; only UI is rendered.
- Options: New World → WORLD_CREATION, Load Game → SAVE_LOAD, Settings, Quit.

**WORLD_CREATION state**:
- Editable seed input. Calls `_init_world(seed)` on Generate, which creates the `GameWorld`, sets up terrain/chunks, and transitions to LOADING.

**SAVE_LOAD state**:
- Lists `saves/*.json` files. Supports named save (from pause menu) and load (from either menu).
- Loading reads the save's seed, calls `_init_world(seed)`, then applies `load_from_dict()`.

**LOADING state**:
- Generates chunks at `loading_chunks_per_frame` rate (default 4)
- Transitions to PLAYING when:
  - Load queue is empty OR minimum chunk count reached
  - AND all sim-distance chunks have `is_mesh_uploaded == True`
- Prevents player from spawning on invisible terrain

**PLAYING state**:
- `update_player_position()` recalculates which chunks to load/unload
- Load queue sorted by squared distance to player (closest-first)
- Process 1 chunk/frame for loading, 2 chunks/frame for unloading
- Props generated when chunks enter prop range (half render distance)

**PAUSED state**:
- Quit calls `_cleanup_world()` which destroys all chunk/entity meshes, clears world state, and returns to MAIN_MENU.

### Entity Lifecycle

- **On chunk load**: Terrain generated via `_generate_chunk()`, props spawned via `_spawn_chunk_props()`, entity IDs stored in `chunk.entity_ids`
- **On chunk unload**: `_cleanup_chunk()` destroys terrain mesh, despawns all chunk entities from GameWorld, and removes cached entity meshes from `_entity_meshes`
- No orphaned entities: every entity is tied to a chunk and fully cleaned up on unload

### Render/Sim Distance Filtering

| System | Filter | Fallback (static mode) |
|--------|--------|----------------------|
| Entity rendering | Only entities in render-distance chunks drawn | All entities drawn |
| NPC behavior trees | Only NPCs in sim-distance chunks updated | All NPCs updated |
| Physics step | Only characters in sim-distance chunks simulated | All characters simulated |
| Player | Always rendered and always included in physics | Same |

### ChunkedHeightField

Provides seamless physics collision across chunk boundaries:

```python
chunked_hf = ChunkedHeightField(chunk_manager)
height = chunked_hf.sample(world_x, world_z)          # point sample
height = chunked_hf.sample_interpolated(world_x, world_z)  # bilinear
normal = chunked_hf.get_normal(world_x, world_z)      # surface normal
```

Automatically routes queries to the correct chunk based on world coordinates.

---

## 7. Prop Generation Pipeline

### Overview

```
props.py (descriptors) → game_runner._spawn_chunk_props() (spawning)
    → graphics_bridge.upload_entity_mesh() (mesh creation)
    → C++ generate_*_mesh() (geometry)
```

In dynamic mode, props are spawned per-chunk when chunks enter prop range.
Entity IDs are tracked in `chunk.entity_ids` for cleanup on unload.

### Rock Pipeline

**Descriptor** (`procengine/world/props.py`):
```python
{
    "type": "rock",
    "position": [x, y, z],    # within [0, size] (world coordinates)
    "radius": 0.3..1.2,       # absolute world units (NOT scaled by world size)
    "noise_seed": <uint31>,    # deterministic per-rock variation
}
```

**Mesh generation** (`cpp/props.cpp`):
- UV sphere with spatially coherent noise displacement
- `RockDescriptor` fields: `position`, `radius`, `noise_seed`, `noise_scale`
- Noise uses bilinear interpolation over a coarse grid (5x7 + 10x14 octaves)
  on the sphere surface with smoothstep blending
- Normals recomputed from displaced geometry
- Default `noise_scale = 0.15` (15% of radius, +/-)

**Render scale** (`game_runner.py`): `scale = radius * 2.0`

**Important**: Rock radius must NOT be multiplied by world size. This was a
previous bug where `radius = uniform(0.1, 0.5) * 64` produced rocks 12-64 units
wide. Fixed to use absolute values `uniform(0.3, 1.2)`.

### Tree Pipeline

**Descriptor** (`procengine/world/props.py`):
```python
{
    "type": "tree",
    "axiom": "F",
    "rules": {"F": "F[+F]F[-F]F"},
    "angle": 15.0..45.0,       # branch angle in degrees
    "iterations": 2..4,         # L-system expansion depth
}
```

**Mesh generation** (`cpp/props.cpp`):
1. Evaluate L-system string (axiom -> rules, N iterations)
2. Generate tree skeleton via turtle graphics (F=forward, +/-=rotate, [/]=push/pop)
3. Sweep-mesh each skeleton segment as a tapered cylinder
4. `segment_length=1.0`, `base_radius=0.1`, `taper=0.85`

**Render scale** (`game_runner.py`): `scale = 1.0` (L-system trees are naturally sized)

### Entity State Threading

Entity state passes through the pipeline via these signatures:

```python
# game_runner.py
_get_or_create_entity_mesh(entity_id, entity_type, entity_state=None) -> str

# graphics_bridge.py
upload_entity_mesh(name, entity_type, entity_state=None) -> bool
```

Call pattern for props:
```python
mesh_name = self._get_or_create_entity_mesh(
    entity.entity_id, prop_type, entity.state,
)
```

---

## 8. Physics Module

### Structure

- `Vec3` -- 3D vector (position, velocity, forces)
- `RigidBody` -- 2D physics body (position, velocity, mass, radius)
- `RigidBody3D` -- 3D extension with Vec3 fields
- `step_physics(bodies, dt)` -- 2D collision step
- `step_physics_3d(bodies, dt)` -- 3D collision step
- `HeightField2D` -- Terrain collision with bilinear interpolation
- `ChunkedHeightField` -- Multi-chunk terrain collision

### Sim-Distance Filtering

In dynamic-chunk mode, `physics_step()` and `_update_npcs()` in `game_api.py`
use `get_entities_in_sim_range()` to process only entities within sim-distance
chunks. The player is always included in physics regardless of sim range.

```python
# game_api.py
def physics_step(self) -> None:
    sim_entities = self.get_entities_in_sim_range()
    characters = [e for e in sim_entities if isinstance(e, Character)]
    # Player always included
    player = self.get_player()
    if player and player not in characters:
        characters.append(player)
    ...
```

### Import Convention

```python
# At module level (preferred)
from procengine.physics import Vec3, HeightField2D

# Runtime/lazy import (inside functions only when necessary)
from procengine.physics import Vec3  # MUST use full path
```

---

## 9. Entity System

### Hierarchy

`Entity` -> `Character` -> `Player`, `NPC`; `Entity` -> `Prop`, `Item`

### Prop Entity

```python
Prop(
    entity_id="rock_0",
    position=Vec3(x, terrain_y, z),
    prop_type="rock",                     # determines mesh generation
    state={"radius": 0.8, "noise_seed": 12345},  # passed to mesh generator
)
```

- `entity.prop_type` controls which mesh generator is used
- `entity.state` is an arbitrary dict passed to `upload_entity_mesh()`
- `entity.rotation` is Y-axis rotation in radians
- In dynamic mode, entities are tracked via `chunk.entity_ids` and cleaned up on chunk unload

---

## 10. Command System

### Architecture (`procengine/commands/`)

The command system provides a unified control surface for console, GUI,
keybinds, and future MCP integration.

| Component | File | Description |
|-----------|------|-------------|
| `CommandRegistry` | commands.py | 52 registered commands with typed params, validation, access control |
| `Console` | console.py | In-game console with history and autocomplete |
| `game_commands` | handlers/game_commands.py | Game-specific command implementations |

### Access Levels

| Level | Description |
|-------|-------------|
| PUBLIC | Always available |
| CONSOLE | Requires console open |
| CHEAT | Requires `system.cheats 1` |
| DEV | Requires `system.dev 1` |

### Categories

world, terrain, props, npc, player, physics, engine, quest, ui, system, debug

There are 11 defined command categories in the enum, with 9 currently populated
by registered commands in the live registry.

### MCP Tool Generation

Commands auto-export as MCP tools via `registry.get_mcp_tools()`, enabling
AI agents to use the same command surface as the in-game console.

---

## 11. UI System

### Architecture (`procengine/game/ui_system.py`)

The UI system uses Dear ImGui with an abstraction layer for testing:

| Component | Description |
|-----------|-------------|
| `UIBackend` | Abstract interface for UI rendering |
| `ImGuiBackend` | Real Dear ImGui via procengine_cpp C++ bindings |
| `HeadlessUIBackend` | Testing backend (records UI calls without rendering) |
| `UIManager` | Orchestrates all UI components |

### Components

| Component | Purpose |
|-----------|---------|
| MainMenu | New World, Load Game, Settings, Quit — app entry point |
| WorldCreationScreen | Seed input, determinism info, Generate World button |
| SaveLoadScreen | Save file list, named save, load — dual-mode (main menu + pause) |
| HUD | Health bar, quest tracker, interaction prompts |
| DialogueBox | NPC conversation with response options |
| InventoryPanel | Player inventory with use/drop actions |
| QuestLog | Active and completed quest tracking |
| PauseMenu | Resume, save, load, settings, quit to main menu |
| SettingsPanel | Debug overlay toggle, VSync toggle |
| DebugOverlay | FPS, player position, entity count, biome info |
| ConsoleWindow | Developer console with input, output, autocomplete |
| NotificationStack | Toast-style runtime notifications |

---

## 12. Determinism System

### Seed Flow

```
World seed (64-bit integer)
  → SeedRegistry(root_seed)
    → splitmix64 counter for each named subseed
    → numpy.random.Generator(PCG64(subseed)) per system
```

### Key Registries

| Name | Purpose |
|------|---------|
| `"props_rock"` | Rock descriptor generation |
| `"props_tree"` | Tree descriptor generation |
| `"tree_positions"` | Tree placement on terrain |
| `"terrain"` | Heightmap generation |
| `"chunk_<x>_<z>"` | Per-chunk terrain generation |

### Determinism Contract

Same root seed + same code path = identical output. Verified via SHA-256
state snapshots in the Engine class. Any change to RNG call order (even
adding a single `rng.random()` call) will change all downstream results.

---

## 13. C++ Pybind11 Bindings

### Module: `procengine_cpp`

**Mesh types**:
- `Mesh` -- vertices, normals, colors, indices + validate/ensure/set_uniform_color
- `RockDescriptor` -- position, radius, noise_seed, noise_scale
- `TreeDescriptor` -- lsystem (LSystemRules), angle, iterations
- `LSystemRules` -- axiom (string), rules (dict<char, string>)

**Mesh generators**:
- `generate_rock_mesh(desc, segments=16, rings=12)` -> Mesh
- `generate_tree_mesh(desc, segments_per_ring=8)` -> Mesh
- `generate_capsule_mesh(radius, height, segments, rings)` -> Mesh
- `generate_cylinder_mesh(radius, height, segments)` -> Mesh
- `generate_box_mesh(size, center)` -> Mesh
- `generate_cone_mesh(radius, height, segments)` -> Mesh
- `generate_terrain_mesh(heightmap, cell_size, height_scale)` -> Mesh
- `generate_terrain_mesh_with_biomes(heightmap, biome_map, cell_size, height_scale)` -> Mesh

**Convenience constructors** (dict -> descriptor):
- `create_rock_from_dict(d)` -> RockDescriptor
- `create_tree_from_dict(d)` -> TreeDescriptor
- `create_creature_from_dict(d)` -> CreatureDescriptor

**Graphics system**:
- `GraphicsSystem` -- Vulkan instance, surface, swapchain management
- `Camera` -- position, target, up, fov
- `Light` -- position, color, intensity, radius

---

## 14. Testing

### Test Organization

- **Active Python suite**: `tests/unit/` plus `tests/integration/test_world.py`
- **Active native integration suite**: selected `tests/integration/test_cpp_*.py` files after building `procengine_cpp`
- **Legacy archive**: `Legacy/tests/` is still discoverable by root pytest config, but is not part of the active CI suite
- **conftest.py**: Adds project root, procengine/, build/, build/Release/ to sys.path

### Running Tests

```bash
# Python-side CI suite (fresh clone friendly)
python -m pytest tests/unit tests/integration/test_world.py -v --tb=short

# Native integration suite (requires built procengine_cpp in ./build)
python -m pytest \
  tests/integration/test_cpp_engine.py \
  tests/integration/test_cpp_terrain.py \
  tests/integration/test_cpp_physics.py \
  tests/integration/test_cpp_props.py \
  tests/integration/test_cpp_materials.py \
  tests/integration/test_cpp_seed_registry.py \
  -v --tb=short

# Specific test
python -m pytest tests/unit/test_props.py -v

# Chunk system + game runner (most relevant for runtime changes)
python -m pytest tests/unit/test_chunk_system.py tests/unit/test_game_runner.py -x -q
```

### Test Conventions

- Test files mirror source structure: `test_physics_3d.py` tests `physics/`
- Determinism tests compare two runs with same seed
- Structure tests validate descriptor shapes, ranges, and types
- All imports in tests must use `from procengine.* import ...`
- `_advance_past_loading()` helper in game_runner tests to skip LOADING state

---

## 15. Common Pitfalls & Lessons Learned

### 1. Bare Module Imports

**Problem**: `from physics import X` fails with `No module named 'physics'`.
**Fix**: Always use `from procengine.physics import X`.
**Detection**: `rg "^\s*(from|import)\s+(physics|game|world|core)\b" --type py`

### 2. World-Size Scaling in Descriptors

**Problem**: Rock radius was `uniform(0.1, 0.5) * world_size`, making rocks
world-sized (6-32 units in a 64-unit world).
**Rule**: Prop sizes should be absolute values, not scaled by terrain dimensions.
Position can be scaled by world size; physical dimensions should not.

### 3. Placeholder Meshes

**Problem**: `upload_entity_mesh()` used placeholder primitives (cylinders for
trees) because it lacked access to entity state.
**Fix**: Pass `entity_state` dict through the pipeline so the mesh generator
can use descriptor parameters (L-system rules, noise seeds, etc.).

### 4. Per-Vertex vs. Spatially Coherent Noise

**Problem**: Hashing each vertex independently creates jagged, disconnected geometry.
**Fix**: Use bilinear interpolation over a coarse noise grid with smoothstep
blending. Multiple octaves (70/30 blend) provide natural variation at two scales.

### 5. Linux CI Divergence

**Problem**: Linux CI ran "Run full test suite" while Windows/macOS ran
"Run integration tests" (6 specific files with `continue-on-error`).
**Rule**: All three platforms should run the same test step.

### 6. Orphaned Entities on Chunk Unload

**Problem**: When chunks unloaded, only the terrain mesh was destroyed. Entity
objects accumulated in GameWorld forever, causing a memory leak that grew
unbounded as the player explored.
**Fix**: `_cleanup_chunk()` in game_runner.py now destroys all chunk entities,
removes their cached meshes, and destroys the terrain mesh on unload.

### 7. Entity Distance Filtering

**Problem**: `_render_entities()` drew ALL entities regardless of distance.
`_update_npcs()` and `physics_step()` processed ALL entities.
**Fix**: In dynamic mode, rendering filters by render-distance chunks, and
NPC/physics updates filter by sim-distance chunks. Player is always included.

---

## 16. Adding New Prop Types

To add a new procedural prop type (e.g., "bush"):

1. **Descriptor** -- Add `generate_bush_descriptors()` in `procengine/world/props.py`
   using `registry.get_rng("props_bush")` for determinism

2. **C++ Mesh** -- Add `BushDescriptor` struct and `generate_bush_mesh()` in
   `cpp/props.h` + `cpp/props.cpp`

3. **Bindings** -- Expose in `cpp/engine.cpp`:
   ```cpp
   py::class_<props::BushDescriptor>(m, "BushDescriptor")...
   m.def("generate_bush_mesh", &props::generate_bush_mesh, ...);
   m.def("create_bush_from_dict", [](py::dict d) { ... });
   ```

4. **Graphics bridge** -- Add `elif entity_type == "bush":` case in
   `upload_entity_mesh()` that builds the descriptor from `entity_state`

5. **Game runner** -- In dynamic mode, include bush descriptors in
   `_spawn_chunk_props()`. Entity will be tracked in `chunk.entity_ids`
   and automatically cleaned up on chunk unload.

6. **Color** -- Add `"bush": (r, g, b)` to `ENTITY_COLORS` in `graphics_bridge.py`

7. **Tests** -- Add determinism + structure tests in `tests/unit/test_props.py`,
   add C++ mesh test in `tests/integration/test_cpp_props.py`

---

## 17. Key File Quick Reference

| Task | File(s) |
|------|---------|
| Add/modify prop descriptor | `procengine/world/props.py` |
| Change prop mesh generation | `cpp/props.cpp`, `cpp/props.h` |
| Update pybind11 bindings | `cpp/engine.cpp` |
| Main menu / world creation flow | `procengine/game/game_runner.py` (`_init_world`, `_cleanup_world`) |
| Save/load screens | `procengine/game/ui_system.py` (SaveLoadScreen), `procengine/game/game_runner.py` |
| Change entity rendering/scale | `procengine/game/game_runner.py` |
| Change entity mesh creation | `procengine/graphics/graphics_bridge.py` |
| Change entity colors | `procengine/graphics/graphics_bridge.py` (ENTITY_COLORS) |
| Spawn props on terrain | `procengine/game/game_runner.py` (`_spawn_chunk_props`) |
| Chunk load/unload logic | `procengine/world/chunk.py` (ChunkManager) |
| Frame-budget chunk scheduling | `procengine/managers/game_manager.py`, `cpp/game_manager.cpp` |
| Chunk entity cleanup | `procengine/game/game_runner.py` (`_cleanup_chunk`) |
| Physics bodies/collision | `procengine/physics/` |
| Sim-distance filtering | `procengine/game/game_api.py` (physics_step, _update_npcs) |
| Terrain heightmap gen | `procengine/world/terrain.py` |
| Cross-chunk physics | `procengine/world/chunk.py` (ChunkedHeightField) |
| Command definitions | `procengine/commands/commands.py`, `handlers/game_commands.py` |
| UI components | `procengine/game/ui_system.py` |
| CI workflow | `.github/workflows/ci.yml` |
| Release packaging workflow | `.github/workflows/release.yml` |
| Test configuration | `tests/conftest.py` |
| Build configuration | `pyproject.toml`, `setup.py`, `cpp/CMakeLists.txt` |
