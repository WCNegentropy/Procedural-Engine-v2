# Procedural Game Engine v2

**Status:** Alpha (Dynamic Open World)

Hybrid Python/C++ procedural game engine with deterministic world generation, dynamic chunk-based infinite terrain, 3D physics, complete game systems, command architecture, and **fully working Vulkan graphics**. Building toward v2.0 AI-native RPG platform with MCP integration.

---

## Quick Start

```bash
# Install dependencies
pip install numpy pybind11

# Build C++ module (headless mode for CI/development)
cd cpp && mkdir build && cd build
cmake .. -DNO_GRAPHICS=ON && make
cd ../..

# Run tests (694+ tests)
python -m pytest -q
```

---

## Features

### Core Engine
- 100% procedurally generated infinite worlds from a single 64-bit seed
- Deterministic output: same seed always produces identical results
- Hybrid Python/C++ architecture with pybind11 FFI
- Dynamic chunk-based world streaming with configurable render/sim distances
- Hot-reload infrastructure for iterative development
- SHA-256 state verification across FFI boundary

### Dynamic Chunk System
- **ChunkManager** streams terrain around the player in real time
- Configurable render distance (default 6 chunks) and simulation distance (default 3 chunks)
- LOADING state generates initial chunks before gameplay begins; transitions to PLAYING after mesh verification
- Load queue sorted closest-first for immediate visual feedback around the player
- Seamless chunk stitching via vertex overlap (chunk_size + 1)
- **ChunkedHeightField** provides physics collision across chunk boundaries
- Entity lifecycle tied to chunks: props spawn on load, despawn on unload
- Prop generation at half render distance for natural density falloff

### Game Systems
- **Entity System**: Player, NPC, Prop, Item hierarchy with serialization
- **NPC Agent Framework**: LocalAgent for offline AI, ready for MCP integration
- **Behavior Trees**: Full implementation with Selector, Sequence, Parallel, decorators
- **Behavior Tree Integration**: NPCs auto-configured with behavior trees on spawn
- **Dialogue System**: Context-aware responses with personality support
- **Quest System**: Objectives, tracking, rewards, and completion
- **Inventory System**: Items with capacity, stacking, and persistence
- **Input Abstraction**: Action-based input system independent of physical keys
- **Camera System**: Third-person camera with terrain collision avoidance
- **Player Controller**: Input to player action translation layer
- **Data Loading**: JSON-based content loading for NPCs, quests, items
- **Save/Load**: JSON serialization for full game state
- **Event System**: Pub/sub for decoupled game systems

### Command Architecture
- **Command Registry**: 51 registered commands across 11 categories with typed parameters
- **In-Game Console**: Toggle with tilde, command history, autocomplete
- **Keybind System**: Key-to-command mapping with configurable binds
- **Access Control**: PUBLIC, CONSOLE, CHEAT, and DEV permission levels
- **MCP Tool Generation**: Commands auto-export as MCP tools for AI integration
- Categories: world, terrain, props, npc, player, physics, engine, quest, ui, system

### UI System (Dear ImGui)
- **HUD**: Health bar, quest tracker, interaction prompts
- **Dialogue Box**: NPC conversation display with response options
- **Inventory Panel**: Grid of items with use/drop actions
- **Quest Log**: Active and completed quest tracking
- **Pause Menu**: Resume, save, load, settings, quit
- **Debug Overlay**: FPS counter, player position, entity count, biome info
- **Console Window**: Developer console with input, output history, autocomplete
- **Settings Panel**: Debug overlay toggle, VSync toggle
- Headless backend for testing without GPU

### Terrain Generation
- FBM noise heightmaps (6-8 octaves Simplex)
- Voronoi macro-plates with ridged noise
- Hydraulic erosion simulation (100-200 iterations)
- Biome classification (temperature x humidity x height)
- River mask generation
- 64x64 vertex chunks with seamless stitching

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
- ChunkedHeightField for multi-chunk physics
- Deterministic rigid body simulation
- Simulation-distance filtering: only entities in sim-range chunks are updated
- Player always included in physics regardless of sim range
- Python and C++ implementations with full parity

### Materials & Graphics
- Node-based material graph DSL
- GLSL generation and SPIR-V compilation
- **Vulkan backend with full rendering pipeline**
- **16-biome terrain color palette** with vertex colors
- **Entity meshes**: Players, NPCs, rocks, trees, buildings
- **Render-distance entity culling**: only entities in loaded chunks are drawn
- Three-point lighting model (sun, sky, ground bounce)
- Exponential fog and tone mapping
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
Game systems             --->     (Future: native game loop)
Chunk management         --->     Terrain mesh upload, entity meshes
```

### Key Modules (procengine package)

| Module | Purpose |
|--------|---------|
| `procengine.core.engine` | Core engine with state snapshots, hot-reload |
| `procengine.game.game_api` | GameWorld, entities, quests, dialogue, inventory |
| `procengine.game.game_runner` | Main game loop, chunk orchestration, rendering |
| `procengine.game.behavior_tree` | NPC AI with behavior trees |
| `procengine.game.ui_system` | Dear ImGui UI (HUD, dialogue, inventory, console) |
| `procengine.commands.commands` | Command registry with 51 commands |
| `procengine.commands.console` | In-game console with autocomplete |
| `procengine.physics.bodies` | RigidBody, RigidBody3D, Vec3 |
| `procengine.physics.collision` | 2D and 3D physics simulation |
| `procengine.world.terrain` | FBM noise, erosion, biome generation |
| `procengine.world.chunk` | ChunkManager, ChunkedHeightField |
| `procengine.world.props` | Rock, tree, building, creature descriptors |
| `procengine.world.materials` | Material graph DSL and node system |
| `procengine.world.world` | Multi-chunk world assembly |
| `procengine.graphics.graphics_bridge` | Vulkan abstraction layer |

---

## Game API

The game layer provides RPG functionality on top of the engine.

### GameWorld Example

```python
from procengine.game.game_api import GameWorld, GameConfig, NPC, Quest, QuestObjective, ObjectiveType, QuestState
from procengine.physics.bodies import Vec3

# Create world
world = GameWorld(GameConfig(seed=42))

# Create player
player = world.create_player(name="Hero", position=Vec3(0, 10, 0))

# Spawn NPC
blacksmith = NPC(
    entity_id="blacksmith",
    name="Grom the Smith",
    personality="Gruff but kind-hearted dwarf who loves his craft",
    position=Vec3(10, 0, 10),
    behavior="merchant",
)
world.spawn_entity(blacksmith)

# Define quest
quest = Quest(
    quest_id="find_ore",
    title="The Smith's Request",
    description="Grom needs iron ore for his work.",
    giver_npc_id="blacksmith",
    objectives=[
        QuestObjective("collect", "Collect 5 iron ore", ObjectiveType.COLLECT, "iron_ore", 5),
    ],
    rewards={"gold": 100},
    state=QuestState.AVAILABLE,
)
world.register_quest(quest)

# Game loop
for frame in range(600):
    world.step(dt=1/60)

# Save game
world.save_to_file("savegame.json")
```

### Dialogue System

```python
# Start dialogue with NPC
world.initiate_dialogue("blacksmith")

# Process player message and get response
response = world.process_player_dialogue("blacksmith", "Do you have any work for me?")
print(f"{blacksmith.name}: {response.text}")
print(f"Emotion: {response.emotion}")

# Response may include actions like giving quests
for action in response.actions:
    print(f"Action: {action}")
```

### Behavior Trees

```python
from procengine.game.behavior_tree import (
    BehaviorTree, Selector, Sequence,
    Condition, Action, Wait, NodeStatus,
    create_patrol_behavior, create_guard_behavior
)

# Create patrol behavior for NPC
waypoints = [Vec3(0, 0, 0), Vec3(10, 0, 0), Vec3(10, 0, 10), Vec3(0, 0, 10)]
patrol_tree = create_patrol_behavior(waypoints, speed=3.0)

# Tick behavior each frame
status = patrol_tree.tick(npc, world, dt=1/60)

# Or build custom behavior trees
def is_player_nearby(npc, world, bb):
    player = world.get_player()
    return (player.position - npc.position).length() < 5.0

tree = BehaviorTree(
    Selector([
        Sequence([
            Condition(is_player_nearby),
            Action(lambda n, w, b, d: (print("Hello!"), NodeStatus.SUCCESS)[1]),
        ]),
        Wait(2.0),
    ])
)
```

---

## Dynamic Chunk System

The engine uses a chunk-based streaming system for infinite world generation:

```
Render Distance (6 chunks)
    Sim Distance (3 chunks)
        Player [P]

    +---+---+---+---+---+---+---+---+---+---+---+---+---+
    | R | R | R | R | R | R | R | R | R | R | R | R | R |
    | R | R | R | R | R | R | R | R | R | R | R | R | R |
    | R | R | R | S | S | S | S | S | S | S | R | R | R |
    | R | R | R | S | S | S | S | S | S | S | R | R | R |
    | R | R | R | S | S | S | P | S | S | S | R | R | R |
    | R | R | R | S | S | S | S | S | S | S | R | R | R |
    | R | R | R | S | S | S | S | S | S | S | R | R | R |
    | R | R | R | R | R | R | R | R | R | R | R | R | R |
    | R | R | R | R | R | R | R | R | R | R | R | R | R |
    +---+---+---+---+---+---+---+---+---+---+---+---+---+
    R = Rendered only    S = Simulated + Rendered    P = Player
```

- **Render-distance chunks**: Terrain is visible, entities are drawn
- **Sim-distance chunks**: Physics runs, NPCs update behavior trees
- Chunks outside render distance are unloaded (terrain mesh destroyed, entities despawned)
- LOADING state ensures all sim-distance chunks have meshes uploaded before gameplay starts

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
from procengine.physics.bodies import Vec3, RigidBody3D
from procengine.physics.heightfield import HeightField2D
from procengine.physics.collision import step_physics_3d
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
python -m pytest tests/unit/test_game_api.py -v       # Game systems
python -m pytest tests/unit/test_behavior_tree.py -v  # Behavior trees
python -m pytest tests/unit/test_physics_3d.py -v     # 3D physics
python -m pytest tests/unit/test_physics.py -v        # 2D physics
python -m pytest tests/unit/test_chunk_system.py -v   # Dynamic chunks
python -m pytest tests/unit/test_game_runner.py -v    # Game loop
python -m pytest tests/unit/test_commands.py -v       # Command registry
python -m pytest tests/unit/test_ui_system.py -v      # UI system
python -m pytest tests/unit/test_terrain.py -v        # Terrain generation
python -m pytest tests/unit/test_hot_reload.py -v     # Hot-reload system

# Run C++ integration tests
python -m pytest tests/integration/ -v
```

**Current Coverage:** 694+ tests passing (586 unit + 108 integration)

---

## Development Roadmap

This project is actively developing toward v2.0, an AI-native RPG platform.

### Phase 1: Physics Upgrade (Complete)
- [x] Vec3, RigidBody3D, HeightField2D implementation
- [x] step_physics_3d with hybrid 2D+height approach
- [x] Python/C++ parity with pybind11 bindings
- [x] NO_GRAPHICS CMake option for headless builds
- [x] Comprehensive test suite (67 physics tests)

### Phase 2: Game Loop & NPC Framework (Complete)
- [x] GameWorld state management
- [x] Entity hierarchy (Player, NPC, Prop, Item)
- [x] NPC agent framework with LocalAgent
- [x] Behavior tree system
- [x] Dialogue system with context
- [x] Quest system with objectives
- [x] Inventory system
- [x] Save/load serialization
- [x] Event system
- [x] Player controller input handling
- [x] Camera system
- [x] Graphics bridge with entity rendering
- [x] Biome terrain coloring (16 biomes)
- [x] Entity mesh rendering (players, NPCs, props)

### Phase 2.5: Graphics & UI (Complete)
- [x] Vulkan rendering pipeline complete
- [x] Terrain with biome colors
- [x] Entity mesh generation (capsule, cylinder, box, L-system trees)
- [x] Dear ImGui UI framework (HUD, dialogue, inventory, console, debug overlay)
- [x] Dynamic chunk-based world streaming
- [x] Render-distance entity culling
- [x] Simulation-distance NPC/physics filtering
- [x] LOADING/PLAYING state machine with mesh verification
- [x] Closest-first chunk load ordering
- [x] Entity lifecycle tied to chunk load/unload

### Phase 3: MCP Integration (Pending)
- [ ] MCP server for Claude/AI integration
- [ ] AI-powered NPC dialogue via MCPAgent
- [ ] Game Master mode for dynamic events
- [ ] Graceful fallback to LocalAgent

### Phase 4: Command Architecture (Complete)
- [x] Unified command registry (51 commands)
- [x] In-game console with autocomplete
- [x] Keybind system
- [x] Access control (PUBLIC, CONSOLE, CHEAT, DEV)
- [x] MCP tool generation from commands
- [ ] Script execution for modding (planned)

See [plan.md](plan.md) for the complete development plan.

---

## API Reference

### Engine

```python
from procengine import Engine

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
from procengine import SeedRegistry, generate_terrain_maps

registry = SeedRegistry(seed=42)
height, biome, river, slope = generate_terrain_maps(
    registry,
    size=65,
    octaves=6,
    macro_points=8,
    erosion_iters=100,
    return_slope=True
)
# Returns: height, biome, river, slope arrays
```

### World

```python
from procengine import SeedRegistry, generate_world

registry = SeedRegistry(seed=42)
world = generate_world(
    registry,
    width=2,
    height=2,
    terrain_size=65,
    terrain_octaves=6,
    terrain_erosion_iters=100
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
