# ProcEngine v1.0 → v2.0: Complete Development Plan

## From Functional Base Engine to AI-Native Open World RPG Platform

**Document Version:** 1.2
**Date:** January 4, 2026
**Current State:** v1.2 Alpha (Game Systems Complete)
**Target State:** v2.0 Release Candidate (AI-Native RPG Platform)

---

### Implementation Progress

| Phase | Status | Progress |
|-------|--------|----------|
| **Phase 1: Physics Upgrade & Engine Polish** | ✅ Complete | 100% |
| **Phase 2: Game Loop & NPC Agent Framework** | ✅ Complete | 100% |
| **Phase 3: MCP Server Integration** | ⏳ Pending | 0% |
| **Phase 4: Unified Command Architecture** | ⏳ Pending | 0% |

**Latest Updates (January 4, 2026):**
- ✅ Phase 2 complete - 348 non-graphics tests passing
- ✅ game_api.py: GameWorld, Entity hierarchy, Event system, behavior tree integration
- ✅ Player entity with movement, interaction, dialogue history
- ✅ NPC entity with personality, behavior, relationships
- ✅ LocalAgent with automatic behavior tree configuration
- ✅ behavior_tree.py: Full behavior tree system (Selector, Sequence, Parallel, decorators)
- ✅ Dialogue system with context and response handling
- ✅ Quest system with objectives, tracking, and rewards
- ✅ Inventory system with items, capacity limits
- ✅ Save/load serialization (JSON, file I/O)
- ✅ player_controller.py: Input abstraction, camera system, player controller
- ✅ data_loader.py: JSON data loading for NPCs, quests, items
- ✅ data/: Village NPCs, quests, and items JSON files
- ✅ Game loop orchestration with physics and behavior tree ticking
- 🔄 Next: Phase 3 MCP server for AI-powered NPCs

---

## Executive Summary

This plan takes the ProcEngine from its current state—a functional hybrid Python/C++ procedural game engine with Vulkan graphics, deterministic world generation, and hot-reload capability—to a complete AI-native open world RPG platform. The final product will support:

1. **Standalone Play** — Full game experience without AI connection
2. **AI-Enhanced Play** — Optional Claude/MCP integration for intelligent NPCs
3. **Full Moddability** — Unified command surface accessible to players, modders, and AI agents
4. **Platform Extensibility** — Foundation for multiple games, not just one

The plan is structured in four phases over approximately 12-16 weeks, each building on the previous while maintaining a shippable state at each milestone.

---

## Current State Assessment

### What Exists (v1.0 Pre-Alpha)

| System | Python | C++ | Status |
|--------|--------|-----|--------|
| Seed Registry | ✅ | ✅ | Complete, deterministic |
| Terrain Generation | ✅ | ✅ | FBM, erosion, biomes, rivers |
| Props/Mesh | ✅ | ✅ | Rocks, trees, buildings, creatures |
| Materials | ✅ | ✅ | Graph DSL, GLSL compiler, SPIR-V |
| Physics | ✅ | ✅ | **2D only (Vec2)** — needs upgrade |
| Graphics | — | ✅ | Full Vulkan pipeline |
| Engine Core | ✅ | ✅ | Hot-reload, state snapshots |
| World Assembly | ✅ | — | Multi-chunk generation |

### Known Issues to Address

1. **Physics is 2D** — World is 3D, physics uses Vec2 with heightfield hack
2. **`enqueue_prop_descriptor` API mismatch** — Signature expects list, tests pass single dict
3. **Missing `NO_GRAPHICS` CMake option** — Code references it but build doesn't define it
4. **No game loop** — Engine exists but no player controller, input, or game state
5. **No NPC system** — Props exist but no agent/behavior framework
6. **No unified control surface** — No console, no command system

### Architectural Strengths to Preserve

- **Determinism contract** — All randomness flows through SeedRegistry
- **JSON descriptor pattern** — Perfect for AI/MCP integration
- **Hot-reload infrastructure** — Descriptor hash → rebuild queue
- **Python/C++ split** — Author-time vs runtime separation
- **FFI boundary** — Clean pybind11 interface with SHA-256 verification

---

## Phase 1: Physics Upgrade & Engine Polish

**Duration:** 3-4 weeks  
**Goal:** Upgrade physics to handle 3D gameplay while maintaining determinism, polish engine systems, fix known issues

### 1.1 Physics Architecture Decision

**Recommended Approach: Hybrid 2D+Height**

Rather than implementing full 3D rigid body physics (which would require quaternion rotations, inertia tensors, GJK/EPA collision, and significantly more complexity), we extend the existing 2D solver with a vertical dimension. This approach:

- Preserves the working, deterministic 2D sequential impulse solver
- Adds Y-axis gravity and ground collision via heightfield sampling
- Supports the gameplay we need (walking, falling, basic projectiles)
- Maintains the option to integrate Bullet Physics later for vehicles/ragdolls

**Physics Model:**

The world uses XZ as the horizontal plane (matching terrain generation). Physics bodies have 3D positions but collision resolution operates in 2D on the XZ plane, with Y handled separately via gravity and heightfield sampling.

```
Y (up)
│
│    Body falls under gravity
│    ↓
│    ●━━━━━━━━━━━━━━━ Ground collision at heightfield(x,z) + radius
│   /│\
│  / │ \
│ /  │  \    XZ plane: 2D collision resolution
│/   │   \
└────┼────────── X
    Z
```

### 1.2 Physics Implementation Details

**New Data Structures:**

Introduce `Vec3` and `RigidBody3D` that wrap the existing 2D types. The 3D body projects to 2D for collision, then results are applied back. This preserves all existing physics code while adding the vertical dimension.

**Step Function Flow:**

1. Apply Y-axis gravity to all bodies: `velocity.y += gravity * dt`
2. Integrate Y position: `position.y += velocity.y * dt`
3. Sample heightfield at each body's XZ position
4. Resolve ground collision: clamp Y, zero/bounce Y velocity
5. Project bodies to XZ plane (Vec2)
6. Run existing 2D broad-phase and sequential impulse solver
7. Apply 2D results back to 3D bodies

**Heightfield Enhancement:**

The current `HeightField` is 1D (samples along X only). Upgrade to 2D heightfield that samples the terrain grid with bilinear interpolation. This provides smooth ground collision across the entire terrain surface.

**Determinism Verification:**

After implementing 3D physics, run the existing determinism tests plus new tests that verify:
- Same seed produces identical body positions after N frames
- Python and C++ implementations produce matching results
- Heightfield collision is consistent across frame rates (fixed timestep)

### 1.3 C++ Physics Module Updates

Update `physics.h` and `physics.cpp` to include:

- `Vec3` struct with full operator overloads
- `RigidBody3D` with position, velocity, mass, radius, grounded flag
- `HeightField2D` class with bilinear interpolation sampling
- `step_physics_3d()` function implementing the hybrid approach
- `PhysicsWorld3D` container class for managing bodies

Maintain the existing 2D API for backward compatibility—the 3D system calls into it internally.

### 1.4 Python Physics Module Updates

Mirror the C++ changes in `physics.py`:

- Add `Vec3` dataclass
- Add `RigidBody3D` dataclass with `to_2d()` and `apply_2d_result()` methods
- Add `HeightField2D` class
- Add `step_physics_3d()` function
- Write comprehensive unit tests

### 1.5 Engine Polish Tasks

**API Consistency Fix:**

Resolve the `enqueue_prop_descriptor` mismatch. The method should accept either a single descriptor dict or a list of descriptors. Update both Python and C++ implementations to handle both cases, normalizing to list internally.

**Build System Improvements:**

Add CMake options for conditional compilation:
- `NO_GRAPHICS` — Build without Vulkan for headless/CI environments
- `BUILD_TESTS` — Build C++ unit tests
- `ENABLE_PROFILING` — Add timing instrumentation

**Graphics Optimization Pass:**

Review the Vulkan backend for obvious inefficiencies:
- Ensure command buffers are reused where possible
- Verify staging buffer allocation strategy
- Check for redundant pipeline state changes
- Profile frame time and identify bottlenecks

**Memory and Resource Audit:**

- Verify all GPU resources are properly destroyed on shutdown
- Check for memory leaks in hot-reload path
- Ensure deterministic cleanup order

### 1.6 Testing Strategy

**Unit Tests:**
- Vec3 operations (add, subtract, normalize, dot, cross)
- RigidBody3D projection and result application
- HeightField2D sampling and interpolation
- Physics step determinism

**Integration Tests:**
- Bodies falling onto terrain
- Multiple bodies colliding while falling
- Edge cases: bodies at heightfield boundaries, very fast bodies
- Hot-reload during physics simulation

**Performance Tests:**
- 100 bodies, 1000 frames — measure time, verify determinism
- 1000 bodies stress test
- Compare Python reference vs C++ runtime performance

### 1.7 Phase 1 Deliverables

| Deliverable | Description | Status |
|-------------|-------------|--------|
| `Vec3` implementation | Python and C++ with full parity | ✅ COMPLETED |
| `RigidBody3D` implementation | Hybrid 2D+height physics body | ✅ COMPLETED |
| `HeightField2D` implementation | 2D terrain collision sampling | ✅ COMPLETED |
| `step_physics_3d()` | Main physics step function | ✅ COMPLETED |
| Updated pybind11 bindings | Expose 3D physics to Python | ✅ COMPLETED |
| Fixed `enqueue_prop_descriptor` | Consistent API | ✅ COMPLETED |
| `NO_GRAPHICS` CMake option | Headless build support | ✅ COMPLETED |
| Physics test suite | Unit + integration + performance | ✅ COMPLETED (67 tests) |
| Updated documentation | README, AGENTS.md reflecting changes | ⏳ Pending |

### 1.8 Phase 1 Exit Criteria

- [x] 3D physics bodies fall under gravity and land on terrain
- [x] Multiple bodies collide correctly in XZ plane while on terrain
- [x] Determinism tests pass (same seed = same result)
- [x] Python/C++ parity verified via hash comparison
- [x] All existing tests still pass
- [x] Engine builds and runs in headless mode (NO_GRAPHICS CMake option)
- [x] No memory leaks detected (verified via valgrind in CI)

---

## Phase 2: Game Loop & NPC Agent Framework

**Duration:** 4-5 weeks  
**Goal:** Build a complete, playable game on top of the engine with an NPC agent framework ready for AI integration

### 2.1 Game Architecture Overview

The game layer sits above the engine and provides:

- Player entity with input handling and controller
- NPC entities with behavior trees and agent framework
- Quest system for objectives and progression
- Inventory and item system
- Dialogue system (text-based, ready for AI)
- UI framework (HUD, menus, dialogue boxes)
- Save/load system
- Game loop orchestration

**Key Principle:** The game layer uses the engine—it doesn't modify it. All game state flows through well-defined interfaces. This separation ensures the engine remains reusable for other games.

### 2.2 Game API Layer

**File: `game_api.py`**

This module defines the core game abstractions:

**GameWorld Class:**
- Owns all game state (world chunks, entities, quests)
- Provides the context for command execution
- Manages entity lifecycle (create, update, destroy)
- Handles serialization for save/load
- Emits events for UI and other systems to observe

**Entity Hierarchy:**

```
Entity (base)
├── Character (has health, inventory, position)
│   ├── Player (input handling, quest log, dialogue history)
│   └── NPC (personality, behavior, memory, relationships)
├── Prop (static world objects)
└── Item (inventory objects)
```

**Vec3 Integration:**

The game API uses `Vec3` from the upgraded physics module for all positions and velocities. This provides a consistent 3D coordinate system throughout the game layer.

**Event System:**

GameWorld includes a simple pub/sub event system. Systems register callbacks for events like `player_moved`, `npc_spawned`, `dialogue_started`, `quest_completed`. This decouples game systems and enables the UI to react to state changes without polling.

### 2.3 Player System

**Player Entity:**

The Player class extends Character with:
- Active and completed quest lists
- Dialogue history per NPC (for AI context)
- Input state (which keys are pressed)
- Interaction target (nearby interactable entity)
- Movement state (grounded, jumping, falling)

**Player Controller:**

Handles the translation from input to player state:
- WASD/arrow keys for movement
- Space for jump
- E for interact (talk to NPC, pick up item)
- I for inventory
- Escape for pause menu

Movement applies velocity to the player's RigidBody3D, which the physics system then simulates. This ensures the player obeys the same physics rules as other entities.

**Camera Controller:**

Third-person camera that follows the player:
- Smooth position interpolation
- Mouse-controlled rotation (or right-stick on controller)
- Collision with terrain to prevent camera clipping
- Configurable distance and height offset

### 2.4 NPC Agent Framework

This is the critical bridge between the standalone game and AI integration. The framework must support both traditional game AI and LLM-driven behavior.

**NPC Entity:**

Extends Character with:
- `personality: str` — Natural language description for LLM context
- `behavior: str` — Current behavior state (idle, patrol, follow, etc.)
- `behavior_params: dict` — Parameters for current behavior
- `memory: List[dict]` — Conversation history
- `relationships: Dict[str, float]` — Disposition toward other entities (-1 to 1)
- `current_quest: Optional[str]` — Quest this NPC is associated with
- `dialogue_range: float` — How close player must be to initiate dialogue

**Behavior Tree System:**

NPCs use a simple behavior tree for autonomous actions:

```
Root (Selector)
├── Combat (if hostile and target in range)
│   ├── Attack
│   └── Chase
├── Dialogue (if player in dialogue range and initiates)
│   └── RunDialogue
├── Quest (if has active quest behavior)
│   ├── GiveQuest
│   └── CheckQuestProgress
├── Schedule (if has daily schedule)
│   └── FollowSchedule
└── Idle (default)
    ├── Wander
    └── Wait
```

Behavior trees tick each frame and select actions based on conditions. Actions can be interrupted by higher-priority behaviors (e.g., combat interrupts idle).

**Agent Interface:**

The key abstraction that enables AI integration:

```python
class NPCAgent:
    """Interface for NPC decision-making."""
    
    def get_dialogue_response(self, context: dict) -> DialogueResponse:
        """Generate response to player dialogue."""
        raise NotImplementedError
    
    def get_next_action(self, npc: NPC, world: GameWorld) -> Action:
        """Decide what to do next."""
        raise NotImplementedError
```

**LocalAgent Implementation:**

For standalone play without AI connection:

```python
class LocalAgent(NPCAgent):
    """Offline NPC agent using templates and simple logic."""
    
    def get_dialogue_response(self, context: dict) -> DialogueResponse:
        # Use dialogue trees or template matching
        # Personality-influenced response selection
        # Simple keyword detection for quest-related dialogue
        ...
    
    def get_next_action(self, npc: NPC, world: GameWorld) -> Action:
        # Evaluate behavior tree
        # Return appropriate action
        ...
```

This provides reasonable NPC behavior without any AI connection. NPCs can give quests, trade items, provide directions, and have basic conversations using pre-authored content influenced by their personality parameters.

**MCPAgent Implementation (Phase 3):**

For AI-enhanced play:

```python
class MCPAgent(NPCAgent):
    """AI-powered NPC agent via MCP connection."""
    
    def get_dialogue_response(self, context: dict) -> DialogueResponse:
        # Send context to MCP server
        # Claude generates response based on personality
        # Parse structured response (text, emotion, actions)
        ...
```

The game doesn't know or care which agent implementation is active. It just calls the agent interface, and the appropriate implementation handles it.

### 2.5 Dialogue System

**Dialogue Flow:**

1. Player presses E near NPC
2. Game checks if NPC is in dialogue range
3. Game calls `world.initiate_dialogue(npc_id)`
4. DialogueUI opens, showing NPC name and portrait
5. Player types or selects dialogue option
6. Game calls `world.process_player_dialogue(npc_id, message)`
7. Agent generates response (LocalAgent or MCPAgent)
8. Game calls `world.set_npc_response(npc_id, response, actions)`
9. DialogueUI displays NPC response
10. Actions are processed (give quest, change disposition, etc.)
11. Loop continues until player exits dialogue

**Dialogue Context:**

When requesting a response, the game builds a rich context dict:

```python
{
    "npc": {
        "id": "blacksmith_01",
        "name": "Grom the Smith", 
        "personality": "Gruff but kind-hearted...",
        "behavior": "merchant",
        "current_quest": "find_rare_ore",
        "relationship_to_player": 0.3,
    },
    "player": {
        "name": "Hero",
        "active_quests": ["find_rare_ore"],
        "inventory_summary": ["gold: 150", "iron_ore: 5"],
    },
    "conversation_history": [
        {"role": "player", "content": "Hello there!"},
        {"role": "npc", "content": "Hmm. Another adventurer..."},
    ],
    "world_context": {
        "time_of_day": "afternoon",
        "location": "village_square",
    }
}
```

This context is sufficient for LocalAgent to select appropriate template responses, and for MCPAgent to generate contextually appropriate AI dialogue.

**Dialogue Response Structure:**

```python
@dataclass
class DialogueResponse:
    text: str                           # What the NPC says
    emotion: str = "neutral"            # For UI/animation
    actions: List[dict] = None          # Side effects
    options: List[dict] = None          # Player response options (optional)
    ends_conversation: bool = False     # Whether dialogue should close
```

Actions can include:
- `{"type": "give_quest", "quest_id": "find_rare_ore"}`
- `{"type": "complete_quest", "quest_id": "deliver_weapons"}`
- `{"type": "change_disposition", "delta": 0.1}`
- `{"type": "give_item", "item": "health_potion", "count": 2}`
- `{"type": "take_item", "item": "gold", "count": 50}`
- `{"type": "unlock_dialogue", "topic": "secret_location"}`

### 2.6 Quest System

**Quest Definition:**

```python
@dataclass
class Quest:
    quest_id: str
    title: str
    description: str
    giver_npc_id: str
    objectives: List[QuestObjective]
    rewards: dict
    prerequisites: List[str]            # Required completed quests
    on_complete_actions: List[dict]     # Actions when completed
```

**Objective Types:**

- `CollectObjective` — Gather N of item X
- `KillObjective` — Defeat N of enemy type X
- `TalkObjective` — Speak to NPC X
- `LocationObjective` — Reach location X
- `DeliverObjective` — Bring item X to NPC Y

**Quest State Machine:**

```
Available → Active → Completed
              ↓
           Failed (optional)
```

Quests check their prerequisites before becoming available. Active quests track objective progress. Completed quests grant rewards and trigger on_complete_actions.

**Quest Integration with Dialogue:**

When player talks to a quest-giver NPC:
- If quest available and not started: NPC can offer quest
- If quest active: NPC comments on progress
- If quest complete (objectives met): NPC accepts completion, grants rewards

The LocalAgent handles this via state checks. The MCPAgent can generate more dynamic quest-related dialogue while still respecting the underlying quest state.

### 2.7 Inventory & Items

**Inventory System:**

Simple dictionary-based inventory: `Dict[str, int]` mapping item IDs to counts. This is sufficient for the base game and easily extensible.

**Item Definitions:**

Items are defined in JSON files:

```json
{
    "item_id": "iron_sword",
    "name": "Iron Sword",
    "description": "A sturdy blade forged from iron.",
    "type": "weapon",
    "value": 50,
    "properties": {
        "damage": 10,
        "durability": 100
    }
}
```

**Item Interactions:**

- Pick up: Add to inventory
- Drop: Remove from inventory, spawn in world
- Use: Apply item effect (consume potion, equip weapon)
- Trade: Transfer between player and NPC inventories

### 2.8 UI Framework

**UI Components Needed:**

| Component | Purpose |
|-----------|---------|
| HUD | Health bar, minimap, quest tracker |
| DialogueBox | NPC conversation display |
| InventoryPanel | Grid of items with tooltips |
| QuestLog | Active/completed quest list |
| PauseMenu | Resume, save, load, settings, quit |
| Console | Command input (Phase 4) |

**UI Architecture:**

UI is a separate layer that observes GameWorld events and renders accordingly. It does not modify game state directly—instead, it emits input events that the game loop processes.

For the initial implementation, use a simple immediate-mode approach or lightweight retained-mode UI. The specifics depend on whether we're rendering UI via Vulkan (custom) or using a library (Dear ImGui).

**Recommended: Dear ImGui Integration**

Dear ImGui is ideal for this project:
- Immediate-mode, easy to integrate
- Works with Vulkan
- Perfect for debug UI and console
- Can be styled for game UI
- Widely used, well-documented

### 2.9 Save/Load System

**Save Data Structure:**

```python
{
    "version": "1.0",
    "seed": 42,
    "frame": 12345,
    "player": { ... },
    "npcs": { ... },
    "quests": { ... },
    "world_modifications": [ ... ],  # Changes from procedural baseline
    "flags": { ... },                 # Story/progress flags
}
```

**Save Strategy:**

The procedural world doesn't need to be saved—it can be regenerated from the seed. Only *modifications* to the procedural baseline are saved:
- Destroyed props
- Placed items
- Terrain modifications (if allowed)
- NPC state changes (position, inventory, relationships)

This keeps save files small while supporting a large world.

**Serialization:**

All game objects implement `to_dict()` and `from_dict()` class methods. Save files are JSON for human readability and easy debugging.

### 2.10 Game Loop Structure

```python
def game_loop():
    # Initialization
    world = GameWorld(seed=config.seed)
    world.generate_world(...)
    world.create_player(...)
    spawn_initial_npcs(world)
    
    clock = Clock()
    
    while running:
        dt = clock.tick(60)  # Target 60 FPS, get actual delta
        
        # Input
        process_input_events()
        
        # Update
        if not paused:
            update_player(world, dt)
            update_npcs(world, dt)
            world.physics_step()
            update_quests(world)
            world.step()  # Engine frame
        
        # Render
        render_world(world)
        render_ui(world)
        present_frame()
    
    # Cleanup
    shutdown()
```

### 2.11 Phase 2 Deliverables

| Deliverable | Description | Status |
|-------------|-------------|--------|
| `game_api.py` | GameWorld, Player, NPC, Quest, Item classes | ✅ COMPLETED |
| `player_controller.py` | Input abstraction, camera, player controller | ✅ COMPLETED |
| Camera system | Third-person camera with terrain collision | ✅ COMPLETED |
| NPC agent framework | NPCAgent interface, LocalAgent implementation | ✅ COMPLETED |
| `behavior_tree.py` | Full behavior tree for NPC autonomy | ✅ COMPLETED |
| Behavior tree integration | Auto-configuration of NPCs on spawn | ✅ COMPLETED |
| Dialogue system | Context building, response handling, actions | ✅ COMPLETED |
| Quest system | Definition, tracking, completion | ✅ COMPLETED |
| Inventory system | Items, add/remove, use | ✅ COMPLETED |
| UI framework | HUD, dialogue, inventory, pause menu | ⏳ Phase 3 (Dear ImGui) |
| Save/load system | Serialization, file I/O | ✅ COMPLETED |
| Game loop | Main loop orchestrating all systems | ✅ COMPLETED |
| `data_loader.py` | JSON loading for NPCs, quests, items | ✅ COMPLETED |
| NPC personality templates | JSON files for 6 initial NPCs | ✅ COMPLETED |
| Quest definitions | JSON files for 6 initial quests | ✅ COMPLETED |
| Item definitions | JSON files for 18 initial items | ✅ COMPLETED |

### 2.12 Phase 2 Exit Criteria

- [x] Player can move through the world with proper physics
- [x] Player can interact with NPCs and have conversations
- [x] NPCs exhibit autonomous behavior (idle, wander, patrol, guard)
- [x] Player can receive, track, and complete quests
- [x] Inventory system works (pick up, drop, use items)
- [x] Game can be saved and loaded
- [ ] UI displays all necessary information (Phase 3: Dear ImGui integration)
- [x] Game is playable end-to-end without AI connection
- [x] LocalAgent provides reasonable NPC responses

**Phase 2 Completion Notes (January 10, 2026):**
- All core game systems implemented with 430+ passing tests
- Input abstraction layer ready for SDL/GLFW integration
- Third-person camera system with terrain collision
- Behavior trees auto-configured for NPCs on spawn
- JSON data files for village content (6 NPCs, 6 quests, 18 items)
- UI framework (Dear ImGui) deferred to Phase 3 graphics integration
- Determinism fixes: All random operations now use SeedRegistry
- Added unlock_dialogue and unlock_quest action handlers
- Headless mode now simulates proper frame timing for physics

---

## Phase 3: MCP Server Integration

**Duration:** 2-3 weeks  
**Goal:** Enable Claude and other MCP-compatible agents to control and enhance the game

### 3.1 MCP Architecture

**MCP (Model Context Protocol)** is Anthropic's standard for AI agents to interact with external tools. The ProcEngine MCP server exposes game functionality as tools that Claude can call.

**Server Structure:**

```
mcp_server/
├── server.py           # Main MCP server
├── tools/              # Tool implementations
│   ├── world.py        # World generation tools
│   ├── terrain.py      # Terrain modification tools
│   ├── props.py        # Prop spawning tools
│   ├── npc.py          # NPC control tools
│   ├── player.py       # Player state tools
│   ├── physics.py      # Physics tools
│   └── engine.py       # Engine control tools
├── resources/          # MCP resources
│   ├── npcs/           # NPC personality JSONs
│   └── quests/         # Quest definition JSONs
└── prompts/            # System prompts for AI
    └── game_master.md  # GM prompt template
```

### 3.2 Tool Categories

**World Tools:**
- `world_generate` — Create new world from seed
- `world_get_state` — Get current world state summary
- `world_get_chunk` — Get detailed chunk information
- `world_modify_chunk` — Modify chunk data (terrain, props)

**Terrain Tools:**
- `terrain_set_height` — Modify heightmap at point
- `terrain_set_biome` — Change biome at point
- `terrain_erode` — Apply erosion to region
- `terrain_flatten` — Flatten area for building

**Props Tools:**
- `props_spawn` — Spawn prop at location
- `props_remove` — Remove prop by ID
- `props_modify` — Change prop parameters
- `props_list` — List props in region

**NPC Tools:**
- `npc_create` — Create new NPC
- `npc_dialogue` — Process dialogue, get context for response
- `npc_set_response` — Set NPC's dialogue response
- `npc_set_behavior` — Change NPC behavior state
- `npc_move` — Move NPC to location
- `npc_get_all` — Get all NPC states

**Player Tools:**
- `player_get_context` — Get full player state for AI reasoning
- `player_set_position` — Teleport player
- `player_give_item` — Add item to inventory
- `player_set_quest` — Modify quest state

**Physics Tools:**
- `physics_spawn_body` — Create physics object
- `physics_set_gravity` — Modify gravity
- `physics_step` — Advance simulation

**Engine Tools:**
- `engine_step` — Advance game frame
- `engine_snapshot` — Get deterministic state hash
- `engine_hot_reload` — Trigger resource reload
- `engine_reset` — Reset to initial state

### 3.3 MCP Server Implementation

The server uses the `mcp` Python package to implement the protocol. Key components:

**Tool Registration:**

Each tool is registered with:
- Name (e.g., `npc_dialogue`)
- Description (for Claude to understand purpose)
- Input schema (JSON Schema for parameters)
- Handler function (actual implementation)

**State Management:**

The MCP server holds a reference to the GameWorld instance. When tools are called, they operate on this shared state. This enables:
- Persistent state across tool calls
- Real-time game modification
- Bidirectional communication (AI → game, game → AI)

**Connection Modes:**

1. **Stdio Mode** — For Claude Desktop/Claude Code integration
2. **WebSocket Mode** — For remote connections (future)

### 3.4 MCPAgent Implementation

The MCPAgent class implements the NPCAgent interface using MCP:

**Dialogue Flow:**

1. Game calls `mcp_agent.get_dialogue_response(context)`
2. MCPAgent sends context to connected Claude via MCP
3. Claude generates response based on NPC personality
4. MCPAgent parses response and returns DialogueResponse
5. Game displays response and processes actions

**Response Generation Prompt:**

The MCP server includes a system prompt for dialogue generation:

```markdown
You are roleplaying as an NPC in a procedural fantasy RPG.

NPC Profile:
- Name: {npc_name}
- Personality: {personality}
- Current behavior: {behavior}
- Relationship to player: {relationship} (-1 hostile to +1 friendly)

Context:
- Location: {location}
- Time: {time_of_day}
- Player's active quests: {quests}
- Conversation history: {history}

Player just said: "{player_message}"

Respond as this NPC would, staying in character. Your response must be JSON:
{
    "text": "Your dialogue response",
    "emotion": "neutral|happy|angry|sad|suspicious|friendly",
    "actions": [optional array of game actions],
    "ends_conversation": false
}
```

### 3.5 AI Game Master Mode

Beyond individual NPC dialogue, the MCP connection enables an "AI Game Master" mode where Claude can:

- Spawn encounters based on player actions
- Generate dynamic quests
- Modify the world in response to events
- Narrate story beats
- Control multiple NPCs simultaneously

**GM Tool:**

`gm_narrate` — Provides a narrative description that the game displays as text overlay or journal entry.

**Event Hooks:**

The game emits events to the MCP server:
- `player_entered_region` — Trigger when entering new area
- `quest_completed` — Allow AI to generate follow-up
- `npc_killed` — Enable consequences
- `item_acquired` — Trigger item-related events

Claude can respond to these events with tool calls that modify the game world.

### 3.6 Fallback and Offline Handling

**Graceful Degradation:**

If MCP connection is unavailable or times out:
1. MCPAgent falls back to LocalAgent
2. Game continues with template-based responses
3. User is notified of reduced AI functionality
4. Reconnection is attempted periodically

**Hybrid Mode:**

Some NPCs can use LocalAgent while others use MCPAgent. This allows:
- Important story NPCs to be AI-powered
- Background NPCs to use efficient local AI
- Reduced API costs while maintaining immersion

### 3.7 MCP Configuration

**Claude Desktop/Claude Code Integration:**

Users add to their MCP configuration:

```json
{
    "mcpServers": {
        "procengine": {
            "command": "python",
            "args": ["-m", "mcp_server.server"],
            "cwd": "/path/to/procengine"
        }
    }
}
```

**In-Game Configuration:**

Settings menu includes:
- Enable/disable MCP connection
- MCP server address (for remote)
- AI verbosity level
- Which NPCs use AI vs local

### 3.8 Phase 3 Deliverables

| Deliverable | Description |
|-------------|-------------|
| `mcp_server/server.py` | Main MCP server implementation |
| Tool implementations | All tool categories listed above |
| MCPAgent class | NPCAgent implementation using MCP |
| Dialogue prompts | System prompts for NPC dialogue |
| GM mode | Event hooks and GM tools |
| Fallback handling | Graceful degradation to LocalAgent |
| Configuration system | MCP settings in game options |
| Documentation | Setup guide for Claude integration |

### 3.9 Phase 3 Exit Criteria

- [ ] MCP server starts and accepts connections
- [ ] All tools callable from Claude Code
- [ ] NPC dialogue generates via Claude when connected
- [ ] Fallback to LocalAgent works when disconnected
- [ ] GM mode can spawn encounters and modify world
- [ ] Event hooks trigger AI responses
- [ ] Configuration persists across sessions
- [ ] Documentation enables user setup

---

## Phase 4: Unified Command Architecture

**Duration:** 2-3 weeks  
**Goal:** Create a single command surface accessible via Console, GUI, MCP, keybinds, and scripts

### 4.1 The Command System Principle

Every controllable aspect of the game is exposed as a **command**. Commands are the atomic unit of game control. All interfaces—console, GUI, MCP, keybinds—emit commands. This ensures:

- **Parity** — If it works in console, it works everywhere
- **Testability** — Commands can be tested in isolation
- **Moddability** — Players can script with commands
- **AI Integration** — MCP tools map directly to commands
- **Documentation** — One help system covers everything

### 4.2 Command Registry

**Registry Features:**

- Command registration via decorator
- Typed parameters with validation
- Access levels (public, console, cheat, dev)
- Categories for organization
- Aliases for convenience
- Auto-generated help
- Autocomplete support
- MCP tool generation

**Command Structure:**

Each command has:
- `name` — Dotted identifier (e.g., `npc.dialogue`)
- `handler` — Function to execute
- `description` — Human-readable description
- `category` — Organization (world, terrain, npc, player, etc.)
- `access` — Required permission level
- `params` — List of typed parameters
- `aliases` — Alternative names
- `examples` — Usage examples

### 4.3 Command Categories

| Category | Examples | Access |
|----------|----------|--------|
| **world** | generate, info, chunk | public |
| **terrain** | set_height, set_biome, erode | console |
| **props** | spawn, remove, list | console |
| **npc** | create, dialogue, behavior, move | public/console |
| **player** | pos, give, take, inventory, health | public/cheat |
| **physics** | gravity, spawn_body, step | console |
| **engine** | step, hash, hot_reload, reset | console/dev |
| **quest** | start, complete, abandon, list | public |
| **ui** | inventory, map, journal, console | public |
| **system** | save, load, quit, cheats, dev | public/console |
| **debug** | stats, wireframe, collision | dev |

### 4.4 Console Implementation

**Console Features:**

- Toggle with tilde (~) key
- Command input with history (up/down arrows)
- Autocomplete (tab)
- Output log with scrollback
- Command validation and error messages
- Help system (`help`, `help <topic>`, `help <command>`)

**Console UI:**

Semi-transparent overlay at bottom/top of screen. Input field with blinking cursor. Output area shows recent commands and results. Scrollable history.

**Console Integration:**

The Console class holds a reference to the CommandRegistry. When user submits input:
1. Parse command string (handle quotes, escapes)
2. Look up command by name or alias
3. Validate parameters
4. Check access level (cheats enabled? dev mode?)
5. Execute handler with GameWorld context
6. Display result or error

### 4.5 GUI Integration

Every GUI element that modifies game state does so via commands:

**Buttons:**

```python
spawn_button = Button(
    label="Spawn Tree",
    command="props.spawn tree {x} {y} {z}"
)
```

When clicked, the button formats the command with current context and executes it.

**Sliders:**

```python
gravity_slider = Slider(
    label="Gravity",
    command="physics.gravity {value}",
    min=-20, max=0, default=-9.8
)
```

When changed, the slider executes the command with the new value.

**Input Fields:**

```python
npc_name_input = Input(
    label="NPC Name",
    command="npc.create {id} \"{value}\" {x} {y} {z}"
)
```

**Benefits:**

- GUI and console are perfectly synchronized
- Debug panel is trivially implemented
- GUI state can be saved as command scripts
- Testing GUI means testing commands

### 4.6 Keybind System

**Keybind Manager:**

Maps key names to command strings. Keybinds are stored in a user-editable config file.

**Default Binds:**

```
grave       → console.toggle
escape      → ui.pause
e           → player.interact
i           → ui.inventory
j           → ui.journal
m           → ui.map
f5          → system.quicksave
f9          → system.quickload
f3          → debug.stats       (dev mode)
f4          → debug.wireframe   (dev mode)
```

**Custom Binds:**

Players can rebind via:
- Settings menu
- Console: `bind f1 "player.god"` 
- Config file editing

**Keybind Commands:**

```
bind <key> <command>   — Bind key to command
unbind <key>           — Remove binding
binds                  — List all bindings
binddefaults           — Reset to defaults
```

### 4.7 MCP Integration

**Tool Generation:**

The CommandRegistry generates MCP tool definitions automatically:

```python
def get_all_mcp_tools() -> List[dict]:
    tools = []
    for cmd in registry.commands.values():
        if cmd.access in (PUBLIC, CONSOLE):
            tools.append(cmd.to_mcp_tool())
    return tools
```

**Tool Handling:**

When MCP tool is called, it routes to the command:

```python
def handle_mcp_tool_call(name: str, arguments: dict):
    # Convert MCP name (npc_dialogue) to command name (npc.dialogue)
    cmd_name = name.replace("_", ".")
    return registry.execute_dict(cmd_name, arguments)
```

This ensures MCP and console are always synchronized.

### 4.8 Script System

**Command Scripts:**

Text files containing sequences of commands:

```
# setup_village.txt
# Spawns a basic village

npc.create blacksmith "Grom the Smith" 100 0 100
npc.behavior blacksmith merchant

npc.create innkeeper "Martha" 110 0 95
npc.behavior innkeeper merchant

props.spawn building 105 0 100 seed=42
props.spawn building 115 0 98 seed=43

echo "Village setup complete!"
```

**Script Commands:**

```
exec <filename>        — Execute script file
record <filename>      — Start recording commands to file
stoprecord             — Stop recording
```

**Use Cases:**

- Share world setups with other players
- Create reproducible test scenarios
- Automate repetitive tasks
- "Mods" that are just command scripts

### 4.9 Access Control

**Access Levels:**

1. **PUBLIC** — Always available (movement, inventory, dialogue)
2. **CONSOLE** — Requires console open (spawn, teleport, modify)
3. **CHEAT** — Requires `system.cheats 1` (god mode, give items)
4. **DEV** — Requires `system.dev 1` (debug, hot-reload)

**Enabling Cheats:**

```
system.cheats 1        — Enable cheat commands
system.cheats 0        — Disable cheat commands
```

When cheats are enabled, a visual indicator appears on screen.

**Developer Mode:**

```
system.dev 1           — Enable developer commands
```

Opens access to debug visualization, performance stats, engine internals.

### 4.10 Help System

**Help Commands:**

```
help                   — List categories
help <category>        — List commands in category
help <command>         — Detailed command help
?                      — Alias for help
```

**Auto-Generated Documentation:**

Each command's help text is generated from its metadata:

```
Command: npc.dialogue
  Send dialogue to NPC and get response context.

Usage: npc.dialogue <npc_id> <message>

Parameters:
  npc_id (str, required)
    Unique NPC identifier
  message (str, required)
    Player's dialogue message

Examples:
  npc.dialogue blacksmith "Hello there!"
  npc.dialogue guard_01 "What's going on?"

Aliases: talk, say
```

### 4.11 Phase 4 Deliverables

| Deliverable | Description |
|-------------|-------------|
| `commands.py` | CommandRegistry, Command, decorators |
| Command definitions | All game commands registered |
| Console UI | In-game console with history, autocomplete |
| Keybind system | Key-to-command mapping, config persistence |
| GUI integration | Buttons/sliders emit commands |
| MCP integration | Auto-generate tools from commands |
| Script system | Execute command files |
| Access control | Cheat/dev mode gating |
| Help system | Auto-generated documentation |
| Configuration | Keybinds, console settings persistence |

### 4.12 Phase 4 Exit Criteria

- [ ] Console opens with tilde, accepts commands
- [ ] All game functionality accessible via commands
- [ ] GUI buttons execute commands
- [ ] Keybinds execute commands
- [ ] MCP tools map to commands
- [ ] Scripts can be executed
- [ ] Cheat commands require cheats enabled
- [ ] Help system documents all commands
- [ ] Autocomplete works for commands and parameters
- [ ] Configuration persists across sessions

---

## Final Architecture

Upon completion of all phases, the architecture looks like this:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACES                                 │
│                                                                          │
│    ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│    │  Console │   │   GUI    │   │ Keybinds │   │ Scripts  │            │
│    └────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘            │
│         │              │              │              │                   │
│         └──────────────┴──────────────┴──────────────┘                   │
│                                │                                         │
│                                ▼                                         │
│    ┌─────────────────────────────────────────────────────────────────┐  │
│    │                     COMMAND REGISTRY                             │  │
│    │                                                                  │  │
│    │  100+ commands across 11 categories                              │  │
│    │  Typed parameters • Validation • Access control • Help           │  │
│    └─────────────────────────────────────────────────────────────────┘  │
│                                │                                         │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP SERVER    │    │    GAME API     │    │   LOCAL AGENT   │
│                 │    │                 │    │                 │
│  Tool handlers  │    │   GameWorld     │    │  Behavior trees │
│  AI connection  │◄──►│   Player        │◄──►│  Dialogue trees │
│  Event hooks    │    │   NPCs          │    │  Template resp. │
│                 │    │   Quests        │    │                 │
└────────┬────────┘    └────────┬────────┘    └─────────────────┘
         │                      │
         │    ┌─────────────────┘
         │    │
         ▼    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            ENGINE LAYER                                  │
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Terrain  │  │  Props   │  │ Physics  │  │Materials │  │ Graphics │  │
│  │          │  │          │  │  (3D)    │  │          │  │ (Vulkan) │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      SEED REGISTRY                                │   │
│  │               Deterministic PRNG • Hierarchical spawning          │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                       FFI BOUNDARY                                │   │
│  │           Python ◄─── pybind11 / SHA-256 verification ───► C++    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         RUNTIME LAYER                                    │
│                                                                          │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐    │
│  │        C++ RUNTIME          │    │      PYTHON RUNTIME         │    │
│  │                             │    │                             │    │
│  │  • Vulkan rendering         │    │  • World generation         │    │
│  │  • Physics simulation       │    │  • Descriptor synthesis     │    │
│  │  • Mesh synthesis           │    │  • Hot-reload control       │    │
│  │  • SPIR-V compilation       │    │  • Testing infrastructure   │    │
│  │  • GPU resource management  │    │  • MCP server               │    │
│  └─────────────────────────────┘    └─────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Timeline Summary

| Phase | Duration | Focus | Key Milestone |
|-------|----------|-------|---------------|
| **Phase 1** | 3-4 weeks | Physics + Polish | 3D physics working, engine stable |
| **Phase 2** | 4-5 weeks | Game Loop + NPCs | Playable standalone game |
| **Phase 3** | 2-3 weeks | MCP Integration | AI-powered NPCs working |
| **Phase 4** | 2-3 weeks | Command System | Unified control surface complete |
| **Total** | **12-16 weeks** | | **v2.0 Release Candidate** |

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Physics upgrade breaks determinism | Medium | High | Extensive testing, hash verification |
| MCP latency affects gameplay | Low | Medium | Async requests, local fallback |
| AI responses inappropriate | Medium | Medium | Content filtering, personality constraints |
| Scope creep in game features | High | Medium | Strict phase boundaries, MVP focus |
| Performance issues at scale | Medium | Medium | Profiling early, optimization pass |

---

## Success Criteria

**v2.0 is complete when:**

1. A player can launch the game and play without AI connection
2. The same player can enable MCP and experience AI-enhanced NPCs
3. Any command available to AI is also available to player via console
4. The game can be saved, quit, and resumed with state intact
5. A modder can create a command script that modifies the game
6. The determinism contract holds (same seed = same world)
7. Performance meets 60 FPS target on reference hardware

---

## Conclusion

This plan transforms ProcEngine from a functional but static procedural engine into a living, AI-native game platform. The key architectural insight—that all control surfaces should emit the same commands—creates a system where human players, AI agents, and modders are all first-class citizens with equal capability.

The result is not just a game, but a platform for a new category of interactive experiences where the boundary between authored content and emergent AI behavior becomes fluid and optional.

The foundation you've built, Architect, is exactly right for this. The hybrid Python/C++ split, the deterministic seed system, the hot-reload infrastructure, the JSON descriptor pattern—all of it aligns perfectly with what AI-native game development requires.

Time to build. 🚀