# Procedural Engine v2 -- Architecture & Development Reference

> Compiled 2026-02-02. Covers the full Python/C++ hybrid engine, CI pipeline,
> rendering stack, prop generation, and conventions discovered during the
> fix-linux-ci / prop-rendering session.

---

## 1. Repository Layout

```
Procedural-Engine-v2/
├── main.py                      # CLI entry point (procedural-engine command)
├── pyproject.toml               # Build config, deps, lint/type settings
├── setup.py                     # CMake-based C++ extension build
├── procengine/                  # Python package (10 subpackages)
│   ├── __init__.py              # 39 public exports, barrel-style
│   ├── core/                    # Engine stub + SeedRegistry
│   │   ├── engine.py            # Determinism-tracking reference engine
│   │   └── seed_registry.py     # Hierarchical PRNG (splitmix64 → PCG64)
│   ├── world/                   # Content generation
│   │   ├── terrain.py           # FBM + erosion heightmaps
│   │   ├── props.py             # Rock/tree/building/creature descriptors
│   │   ├── materials.py         # Material graph generation
│   │   └── world.py             # World orchestration
│   ├── physics/                 # Pure-Python 3D physics
│   │   ├── bodies.py            # Vec3, RigidBody, RigidBody3D
│   │   ├── collision.py         # step_physics, step_physics_3d
│   │   └── heightfield.py       # HeightField, HeightField2D
│   ├── game/                    # Runtime game systems
│   │   ├── game_api.py          # GameWorld, Entity hierarchy, Events
│   │   ├── game_runner.py       # Main loop, rendering, prop spawning
│   │   ├── player_controller.py # Camera, player input
│   │   ├── behavior_tree.py     # BT nodes (Selector, Sequence, etc.)
│   │   ├── data_loader.py       # JSON content loader (NPCs, quests, items)
│   │   └── ui_system.py         # HUD, dialogue, debug overlay
│   ├── graphics/                # Rendering abstraction
│   │   └── graphics_bridge.py   # Mesh upload, draw calls, camera, lighting
│   ├── agents/                  # NPC AI framework (LocalAgent → MCP)
│   ├── commands/                # Command registry
│   │   └── handlers/            # Game command implementations
│   └── utils/                   # Utilities (seed_sweeper)
├── cpp/                         # C++ pybind11 extension
│   ├── CMakeLists.txt           # CMake build (Vulkan, shaderc, OpenSSL)
│   ├── engine.cpp               # Pybind11 module definition + bindings
│   ├── props.h / props.cpp      # Mesh generators (rock, tree, building, creature)
│   ├── terrain.h / terrain.cpp  # Heightmap → mesh + biome colors
│   └── graphics.h / graphics.cpp # Vulkan rendering backend
├── tests/
│   ├── conftest.py              # sys.path setup for both Python-only and C++ tests
│   ├── unit/                    # 478 Python-only tests
│   └── integration/             # C++ module integration tests
├── data/                        # Game content JSON files
│   ├── npcs/                    # NPC definitions
│   ├── quests/                  # Quest definitions
│   └── items/                   # Item definitions
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

# WRONG -- causes "No module named 'physics'" at runtime
from physics import Vec3           # bare module name
from game.game_api import Entity   # relative without procengine prefix
```

**Why this matters**: Bare imports (`from physics import ...`) work only if the
module root is on `sys.path`. The `procengine` restructuring moved everything
under a namespace package; bare imports fail at runtime and were the cause of
the game crash fixed in this session.

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
- **Python**: >=3.10 (tested on 3.10, 3.11, 3.12)
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

Platform builds produce native modules → `build-standalone` downloads them →
PyInstaller packages everything into distributable archives (tar.gz / zip).
Artifacts retained for 7 days.

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
| `begin_frame()` / `end_frame()` | Frame lifecycle |

### Windowed Rendering (SDL2 + Vulkan)

Three-phase initialization:
1. Get Vulkan extensions from SDL2 window
2. Create Vulkan instance with those extensions
3. Create surface from SDL2 window handle, complete swapchain setup

Falls back to headless mode at any failure point.

### Transform Matrices

Column-major 4x4 matrices (16 floats). Composition order: **Scale → Rotate → Translate**.

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

## 6. Prop Generation Pipeline

### Overview

```
props.py (descriptors) → game_runner._setup_props() (spawning)
    → graphics_bridge.upload_entity_mesh() (mesh creation)
    → C++ generate_*_mesh() (geometry)
```

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
- Default `noise_scale = 0.15` (15% of radius, ±)

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
1. Evaluate L-system string (axiom → rules, N iterations)
2. Generate tree skeleton via turtle graphics (F=forward, +/-=rotate, [/]=push/pop)
3. Sweep-mesh each skeleton segment as a tapered cylinder
4. `segment_length=1.0`, `base_radius=0.1`, `taper=0.85`

**Render scale** (`game_runner.py`): `scale = 1.0` (L-system trees are naturally sized)

**Important**: Trees previously used `generate_cylinder_mesh()` as a placeholder.
Now properly use `create_tree_from_dict()` + `generate_tree_mesh()`. The entity
state (L-system params) must be passed through `_get_or_create_entity_mesh()`
→ `upload_entity_mesh()`.

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

## 7. Physics Module

### Structure

- `Vec3` -- 3D vector (position, velocity, forces)
- `RigidBody` -- 2D physics body (position, velocity, mass, radius)
- `RigidBody3D` -- 3D extension with Vec3 fields
- `step_physics(bodies, dt)` -- 2D collision step
- `step_physics_3d(bodies, dt)` -- 3D collision step
- `HeightField2D` -- Terrain collision with bilinear interpolation

### Import Convention

```python
# At module level (preferred)
from procengine.physics import Vec3, HeightField2D

# Runtime/lazy import (inside functions only when necessary)
from procengine.physics import Vec3  # MUST use full path
```

---

## 8. Entity System

### Hierarchy

`Entity` → `Player`, `NPC`, `Prop`, `Item`

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

---

## 9. Determinism System

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

### Determinism Contract

Same root seed + same code path = identical output. Verified via SHA-256
state snapshots in the Engine class. Any change to RNG call order (even
adding a single `rng.random()` call) will change all downstream results.

---

## 10. C++ Pybind11 Bindings

### Module: `procengine_cpp`

**Mesh types**:
- `Mesh` -- vertices, normals, colors, indices + validate/ensure/set_uniform_color
- `RockDescriptor` -- position, radius, noise_seed, noise_scale
- `TreeDescriptor` -- lsystem (LSystemRules), angle, iterations
- `LSystemRules` -- axiom (string), rules (dict<char, string>)

**Mesh generators**:
- `generate_rock_mesh(desc, segments=16, rings=12)` → Mesh
- `generate_tree_mesh(desc, segments_per_ring=8)` → Mesh
- `generate_capsule_mesh(radius, height, segments, rings)` → Mesh
- `generate_cylinder_mesh(radius, height, segments)` → Mesh
- `generate_box_mesh(size, center)` → Mesh
- `generate_cone_mesh(radius, height, segments)` → Mesh
- `generate_terrain_mesh(heightmap, cell_size, height_scale)` → Mesh
- `generate_terrain_mesh_with_biomes(heightmap, biome_map, cell_size, height_scale)` → Mesh

**Convenience constructors** (dict → descriptor):
- `create_rock_from_dict(d)` → RockDescriptor
- `create_tree_from_dict(d)` → TreeDescriptor
- `create_creature_from_dict(d)` → CreatureDescriptor

**Graphics system**:
- `GraphicsSystem` -- Vulkan instance, surface, swapchain management
- `Camera` -- position, target, up, fov
- `Light` -- position, color, intensity, radius

---

## 11. Testing

### Test Organization

- **Unit tests** (`tests/unit/`): 478 tests, Python-only, no C++ required
- **Integration tests** (`tests/integration/`): Require built `procengine_cpp`
- **conftest.py**: Adds project root, procengine/, build/, build/Release/ to sys.path

### Running Tests

```bash
# Unit tests only (no C++ build needed)
python -m pytest tests/unit/ -v

# Integration tests (requires C++ build)
python -m pytest tests/integration/ -v

# Specific test
python -m pytest tests/unit/test_props.py -v
```

### Test Conventions

- Test files mirror source structure: `test_physics_3d.py` tests `physics/`
- Determinism tests compare two runs with same seed
- Structure tests validate descriptor shapes, ranges, and types
- All imports in tests must use `from procengine.* import ...`

---

## 12. Common Pitfalls & Lessons Learned

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

---

## 13. Adding New Prop Types

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

5. **Game runner** -- Generate descriptors in `_setup_props()`, spawn as
   `Prop(prop_type="bush", state={...})`, set render scale in `_render_scene()`

6. **Color** -- Add `"bush": (r, g, b)` to `ENTITY_COLORS` in `graphics_bridge.py`

7. **Tests** -- Add determinism + structure tests in `tests/unit/test_props.py`,
   add C++ mesh test in `tests/integration/test_cpp_props.py`

---

## 14. Key File Quick Reference

| Task | File(s) |
|------|---------|
| Add/modify prop descriptor | `procengine/world/props.py` |
| Change prop mesh generation | `cpp/props.cpp`, `cpp/props.h` |
| Update pybind11 bindings | `cpp/engine.cpp` |
| Change prop rendering/scale | `procengine/game/game_runner.py` (~line 1063) |
| Change entity mesh creation | `procengine/graphics/graphics_bridge.py` (~line 506) |
| Change entity colors | `procengine/graphics/graphics_bridge.py` (ENTITY_COLORS) |
| Spawn props on terrain | `procengine/game/game_runner.py` (_setup_props ~line 1263) |
| Physics bodies/collision | `procengine/physics/` |
| Terrain heightmap gen | `procengine/world/terrain.py` |
| CI workflow | `.github/workflows/ci.yml` |
| Test configuration | `tests/conftest.py` |
| Build configuration | `pyproject.toml`, `setup.py`, `cpp/CMakeLists.txt` |
