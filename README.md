# Procedural Game Engine v1.1

**Status:** Production Ready (3D Physics Complete)

Hybrid Python/C++ procedural game engine with deterministic world generation, 3D physics, Vulkan graphics, and hot-reload capability. Currently in active development toward v2.0 AI-native RPG platform.

---

## Quick Start

```bash
# Install dependencies
pip install numpy pybind11

# Build C++ module (headless mode for CI/development)
cd cpp && mkdir build && cd build
cmake .. -DNO_GRAPHICS=ON && make
cd ../..

# Run tests (172+ tests)
python -m pytest -q
```

---

## Features

### Core Engine
- 100% procedurally generated worlds from a single 64-bit seed
- Deterministic output: same seed always produces identical results
- Hybrid Python/C++ architecture with pybind11 FFI
- Hot-reload infrastructure for iterative development
- SHA-256 state verification across FFI boundary

### Terrain Generation
- FBM noise heightmaps (6-8 octaves Simplex)
- Voronoi macro-plates with ridged noise
- Hydraulic erosion simulation (100-200 iterations)
- Biome classification (temperature x humidity x height)
- River mask generation
- 64x64 vertex chunks with GeoClipmap LOD

### Props & Mesh
- Rocks: SDF-based generation with sphere mesh synthesis
- Trees: L-system skeletons with sweep mesh
- Buildings: Shape grammar with BSP mesh synthesis
- Creatures: Metaball + skeleton with marching cubes
- LOD generation with mesh simplification

### Physics (3D)
- Hybrid 2D+Height approach for efficient 3D simulation
- Sequential impulse solver on XZ plane
- Y-axis gravity with terrain collision
- HeightField2D with bilinear interpolation
- Deterministic rigid body simulation
- Python and C++ implementations with full parity

### Materials & Graphics
- Node-based material graph DSL
- GLSL generation and SPIR-V compilation
- Vulkan backend with shader cache
- Virtual texture system (128KB tiles, LRU paging)
- Forward+ rendering pipeline

---

## Architecture

```
Python (Author-time)              C++ (Runtime)
--------------------              -------------
Terrain descriptors      --->     GeoClipmap mesh, GPU erosion
Prop descriptors         --->     Mesh synthesis, skeletal rigs
Material graph specs     --->     SPIR-V compiler, virtual textures
Physics reference impl   --->     Physics simulation
Hot-reload control       --->     Resource rebuild queue
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `engine.py` | Core engine with state snapshots, hot-reload |
| `terrain.py` | FBM noise, erosion, biome generation |
| `physics.py` | 2D and 3D physics simulation |
| `props.py` | Rock, tree, building, creature descriptors |
| `materials.py` | Material graph DSL and node system |
| `world.py` | Multi-chunk world assembly |

---

## 3D Physics System

The physics system uses a hybrid 2D+height approach that provides efficient 3D simulation while preserving the deterministic 2D solver:

```
Y (up)
|
|    Body falls under gravity
|    v
|    o---------- Ground collision at heightfield(x,z) + radius
|   /|\
|  / | \    XZ plane: 2D collision resolution
| /  |  \
+----+-------- X
    Z
```

### API Example

```python
from physics import Vec3, RigidBody3D, HeightField2D, step_physics_3d
import numpy as np

# Create terrain heightfield
terrain = np.zeros((20, 20), dtype=np.float32)
heightfield = HeightField2D(heights=terrain, cell_size=1.0)

# Create a falling body
body = RigidBody3D(
    position=Vec3(10, 20, 10),
    velocity=Vec3(0, 0, 0),
    mass=1.0,
    radius=0.5
)

# Simulate until grounded
bodies = [body]
for _ in range(600):
    step_physics_3d(bodies, dt=1/60, gravity=-9.8, heightfield=heightfield)

print(f"Grounded: {body.grounded}, Y: {body.position.y:.2f}")
```

### C++ Usage

```python
import procengine_cpp as cpp

# Create 3D physics world
world = cpp.PhysicsWorld3D()

# Add body
body = cpp.RigidBody3D(
    cpp.PhysicsVec3(10, 20, 10),  # position
    cpp.PhysicsVec3(0, 0, 0),     # velocity
    1.0,                          # mass
    0.5                           # radius
)
world.add_body(body)

# Set terrain
heights = [0.0] * 400  # 20x20 flat terrain
hf = cpp.HeightField2D(heights, 20, 20, 0.0, 0.0, 1.0)
world.set_heightfield(hf)

# Simulate
config = cpp.PhysicsConfig3D()
config.gravity = -9.8
config.dt = 1/60
for _ in range(600):
    world.step(config)
```

---

## Build Options

| CMake Option | Description |
|--------------|-------------|
| `NO_GRAPHICS` | Build without Vulkan (headless/CI) |
| `BUILD_TESTS` | Build C++ unit tests |
| `ENABLE_PROFILING` | Add timing instrumentation |

```bash
# Headless build (no Vulkan required)
cmake .. -DNO_GRAPHICS=ON

# Full build with graphics
cmake ..
```

---

## Testing

```bash
# Run all tests
python -m pytest -q

# Run specific categories
python -m pytest test_physics_3d.py -v    # 3D physics (49 tests)
python -m pytest test_physics.py -v       # 2D physics (18 tests)
python -m pytest test_terrain.py -v       # Terrain generation
python -m pytest test_hot_reload.py -v    # Hot-reload system
```

**Current Coverage:** 172+ tests passing

---

## Development Roadmap

This project is actively developing toward v2.0, an AI-native RPG platform.

### Phase 1: Physics Upgrade (Complete)
- [x] Vec3, RigidBody3D, HeightField2D implementation
- [x] step_physics_3d with hybrid 2D+height approach
- [x] Python/C++ parity with pybind11 bindings
- [x] NO_GRAPHICS CMake option for headless builds
- [x] Comprehensive test suite (67 physics tests)

### Phase 2: Game Loop & NPC Framework (Next)
- Player controller and camera system
- NPC agent framework (LocalAgent for offline play)
- Dialogue, quest, and inventory systems
- Save/load system
- UI framework with Dear ImGui

### Phase 3: MCP Integration
- MCP server for Claude/AI integration
- AI-powered NPC dialogue via MCPAgent
- Game Master mode for dynamic events
- Graceful fallback to LocalAgent

### Phase 4: Command Architecture
- Unified command registry
- In-game console with autocomplete
- Keybind system
- Script execution for modding

See [plan.md](plan.md) for the complete development plan.

---

## API Reference

### Engine

```python
from engine import Engine

engine = Engine()
engine.enqueue_heightmap(height16, biome8, river1)
engine.enqueue_prop_descriptor([{"type": "rock", "radius": 2.5}])
engine.step(dt=1/60)
engine.hot_reload(descriptor_hash)
state_hash = engine.snapshot_state(frame)
engine.reset()
```

### Terrain

```python
from terrain import terrain_chunk

chunk = terrain_chunk(
    seed=42,
    size=65,
    octaves=6,
    macro_plates=True,
    erosion_iters=100
)
# Returns: height, biome, river, slope arrays
```

### World

```python
from world import world_chunk

chunk = world_chunk(
    seed=42,
    cx=0, cy=0,
    size=65,
    erosion=True,
    macro_plates=True
)
```

---

## Determinism Contract

| Rule | Detail |
|------|--------|
| Single RootSeed | 64-bit value provided by user |
| SeedRegistry | Deterministic sub-seeds via splitmix64 |
| Unified PRNG | PCG64 streams in both Python and C++ |
| State Hashing | SHA-256 verification at FFI boundary |
| Fixed Step Physics | 60 Hz with float epsilon <= 1e-6 |

---

## License

MIT License - See LICENSE file for details.
