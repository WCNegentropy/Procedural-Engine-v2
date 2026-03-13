# Procedural Game Engine v2

**Status:** Alpha (Dynamic Open World)

Hybrid Python/C++ procedural game engine with deterministic world generation, dynamic chunk-based infinite terrain, 3D physics, complete game systems, command architecture, and **fully working Vulkan graphics**. Building toward v2.0 AI-native RPG platform with MCP integration.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Build C++ module (headless mode for CI/development)
mkdir -p build && cd build
cmake ../cpp -DNO_GRAPHICS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . -j2
cd ..

# Run the active Python-side suite
python -m pytest tests/unit tests/integration/test_world.py -q
```

`python -m pytest` from the repository root also traverses `Legacy/tests/`, which
are archived reference tests and may require a separately built `procengine_cpp`
module. The commands above mirror the active CI paths for a fresh clone.

---

## Features

### Core Engine
- 100% procedurally generated infinite worlds from a single 64-bit seed
- Deterministic output: same seed always produces identical results
- Hybrid Python/C++ architecture with pybind11 FFI
- Dynamic chunk-based world streaming with configurable render/sim distances
- Two-phase initialization: app boots to main menu; world generation deferred until user action
- `GameManagerBridge` feeds frame-budget directives, async chunk generation, and fallback-safe scheduling into the Python game loop
- Hot-reload infrastructure for iterative development
- SHA-256 state verification across FFI boundary

### Dynamic Chunk System
- **ChunkManager** streams terrain around the player in real time
- Configurable render distance (default 6 chunks) and simulation distance (default 3 chunks)
- MAIN_MENU → WORLD_CREATION → LOADING → PLAYING state machine
- LOADING state generates initial chunks before gameplay begins; transitions to PLAYING after mesh verification
- Load queue sorted closest-first for immediate visual feedback around the player
- Seamless chunk stitching via vertex overlap (chunk_size + 1)
- **ChunkedHeightField** provides physics collision across chunk boundaries
- Entity lifecycle tied to chunks: props spawn on load, despawn on unload
- Prop generation at half render distance for natural density falloff

### Game Systems
- **Entity System**: Player, NPC, Creature, Prop, Item hierarchy with serialization
- **Creature System**: Procedurally-generated creatures with species templates (deer, wolf, lizard, goat, humanoid, goblin, bird), biome-specific spawning, vision cones, smooth rotation, and metaball + skeleton mesh generation
- **Resource Harvesting**: Attack-to-harvest system with deterministic drop tables per prop type, hit counters, and cooldown timing
- **Crafting System**: Recipe-based item creation (17 recipes) with CraftingPanel UI, ingredient validation, and result production
- **Player Equipment**: Weapon/tool equip and unequip system with console commands
- **NPC Agent Framework**: LocalAgent for offline AI, ready for MCP integration
- **Behavior Trees**: Full implementation with Selector, Sequence, Parallel, decorators
- **Behavior Tree Integration**: NPCs and creatures auto-configured with behavior trees on spawn
- **Dialogue System**: Context-aware responses with personality support
- **Quest System**: Objectives, tracking, rewards, and completion
- **Inventory System**: Items with capacity, stacking, and persistence
- **Input Abstraction**: Action-based input system independent of physical keys
- **Camera System**: Third-person camera with terrain collision avoidance
- **Player Controller**: Input to player action translation layer
- **Data Loading**: JSON-based content loading for NPCs, quests, items, recipes, drop tables
- **Save/Load**: JSON serialization for full game state
- **Event System**: Pub/sub for decoupled game systems

### Command Architecture
- **Command Registry**: 56 registered commands with typed parameters and access control
- **In-Game Console**: Toggle with tilde, command history, autocomplete
- **Keybind System**: Key-to-command mapping with configurable binds
- **Access Control**: PUBLIC, CONSOLE, CHEAT, and DEV permission levels
- **MCP Tool Generation**: Commands auto-export as MCP tools for AI integration
- Categories: world, terrain, props, npc, player, physics, engine, quest, ui, system, debug

### UI System (Dear ImGui)
- **Main Menu**: New World, Load Game, Settings, Quit — app boots here before any world generation
- **World Creation Screen**: Editable seed input, determinism explanation, Generate World button
- **Save/Load Screen**: Lists save files, supports save (named) and load from both main menu and pause menu
- **HUD**: Health bar, quest tracker, interaction prompts
- **Dialogue Box**: NPC conversation display with response options
- **Inventory Panel**: Grid of items with use/drop actions
- **Crafting Panel**: Recipe list with ingredient requirements, craft button, and result display
- **Quest Log**: Active and completed quest tracking
- **Pause Menu**: Resume, save, load, settings, quit to main menu
- **Debug Overlay**: FPS counter, player position, entity count, biome info
- **Console Window**: Developer console with input, output history, autocomplete
- **Settings Panel**: Debug overlay toggle, VSync toggle
- **Notification Stack**: Toast-style runtime notifications
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
- Bushes, pine trees, dead trees, fallen logs, boulder clusters, flower patches, mushrooms, and cacti have dedicated descriptor and mesh paths
- Buildings: Shape grammar with BSP mesh synthesis
- Creatures: Species-templated metaball + skeleton with marching cubes, head morphology, limb generation, and capsule fallback; 8 built-in species templates (deer, wolf, lizard, goat, humanoid, goblin, bird, original)
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
- **Biome-specific material pipelines** generated in Python, compiled in C++, and selected per rendered terrain chunk
- **16-biome terrain color palette** with vertex colors
- **Entity meshes**: Players, NPCs, rocks, trees, buildings
- **Render-distance entity culling**: only entities in loaded chunks are drawn
- Three-point lighting model (sun, sky, ground bounce)
- Distance fog with dead zone (exponential falloff, configurable density and max opacity)
- Tone mapping
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
| `procengine.game.game_api` | GameWorld, entities (Player, NPC, Creature, Prop, Item), quests, dialogue, inventory |
| `procengine.game.game_runner` | Main game loop, menu flow, chunk orchestration, rendering |
| `procengine.game.behavior_tree` | NPC and creature AI with behavior trees |
| `procengine.game.ui_system` | Dear ImGui UI (main menu, world creation, save/load, HUD, dialogue, inventory, crafting, console) |
| `procengine.game.harvesting` | Resource harvesting system with drop tables |
| `procengine.commands.commands` | Command registry with 56 registered commands |
| `procengine.commands.console` | In-game console with autocomplete |
| `procengine.physics.bodies` | RigidBody, RigidBody3D, Vec3 |
| `procengine.physics.collision` | 2D and 3D physics simulation |
| `procengine.world.terrain` | FBM noise, erosion, biome generation |
| `procengine.world.chunk` | ChunkManager, ChunkedHeightField |
| `procengine.world.props` | Rock, tree, building, creature, bush, and other prop descriptors |
| `procengine.world.creature_templates` | Species template system (8 built-in templates) for creature generation |
| `procengine.world.materials` | Material graph DSL and node system |
| `procengine.world.world` | Multi-chunk world assembly |
| `procengine.managers.game_manager` | C++ `GameManager` bridge and `FrameDirective` fallback |
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
- World creation is deferred: app boots to main menu, world generated on demand via `_init_world(seed)`

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
# Active Python-side suite (matches the CI `test-python` job)
python -m pytest tests/unit tests/integration/test_world.py -v --tb=short

# Native integration subset (requires a built procengine_cpp module in ./build)
python -m pytest \
  tests/integration/test_cpp_engine.py \
  tests/integration/test_cpp_terrain.py \
  tests/integration/test_cpp_physics.py \
  tests/integration/test_cpp_props.py \
  tests/integration/test_cpp_materials.py \
  tests/integration/test_cpp_seed_registry.py \
  -v --tb=short

# Example targeted runtime regression check
python -m pytest tests/unit/test_chunk_system.py tests/unit/test_game_runner.py -x -q
```

**Current coverage layout:** active tests live under `tests/unit/` and
`tests/integration/`, while `Legacy/tests/` remains archival reference material.
The CI workflow runs the Python-only suite separately from the native build jobs.

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
- [x] Entity hierarchy (Player, NPC, Creature, Prop, Item)
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
- [x] Entity mesh rendering (players, NPCs, creatures, props)

### Phase 2.5: Graphics & UI (Complete)
- [x] Vulkan rendering pipeline complete
- [x] Terrain with biome colors
- [x] Biome-specific material pipelines for terrain rendering
- [x] Entity mesh generation (capsule, cylinder, box, L-system trees)
- [x] Dear ImGui UI framework (main menu, world creation, save/load, HUD, dialogue, inventory, crafting, console, debug overlay)
- [x] Two-phase initialization: app boots to main menu; world created on demand
- [x] Working save/load screens and world cleanup for return-to-menu flow
- [x] Dynamic chunk-based world streaming
- [x] C++ `GameManager` bridge for frame-budgeted chunk scheduling
- [x] Render-distance entity culling
- [x] Simulation-distance NPC/physics filtering
- [x] MAIN_MENU → WORLD_CREATION → LOADING → PLAYING state machine
- [x] Main menu, world creation screen, and save/load screen UI components
- [x] Working save/load from both main menu and pause menu
- [x] World cleanup for returning to main menu from gameplay
- [x] Closest-first chunk load ordering
- [x] Entity lifecycle tied to chunk load/unload

### Phase 2.75: Creatures, Harvesting & Crafting (Complete)
- [x] Creature class promoted from Prop to Character with behavior trees
- [x] Species template system (8 built-in templates: deer, wolf, lizard, goat, humanoid, goblin, bird, original)
- [x] Biome-specific creature spawning with density tuning
- [x] Creature head morphology parameters and limb generation
- [x] Vision cone and smooth rotation for creature AI
- [x] Metaball + skeleton mesh pipeline with marching cubes extraction
- [x] Resource harvesting system with deterministic drop tables
- [x] Crafting system with 17 recipes and CraftingPanel UI
- [x] Player equipment system (equip/unequip weapons and tools)
- [x] Expanded item catalog (38 items across weapon, armor, tool, consumable, material, and other types)

### Phase 3: MCP Integration (Pending)
- [ ] MCP server for Claude/AI integration
- [ ] AI-powered NPC dialogue via MCPAgent
- [ ] Game Master mode for dynamic events
- [ ] Graceful fallback to LocalAgent

### Phase 4: Command Architecture (Complete)
- [x] Unified command registry (56 commands)
- [x] In-game console with autocomplete
- [x] Keybind system
- [x] Access control (PUBLIC, CONSOLE, CHEAT, DEV)
- [x] MCP tool generation from commands
- [ ] Script execution for modding (planned)

See [Legacy/plan.md](Legacy/plan.md) for the original development plan (historical reference).

For the latest audit of still-disconnected runtime/FFI features, see
[`docs/remediation_report.md`](docs/remediation_report.md).

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
