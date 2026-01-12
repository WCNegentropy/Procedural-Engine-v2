"""ProcEngine - AI-Native Procedural Game Engine.

A hybrid Python/C++ procedural world generation engine with Vulkan graphics.
Generates 100% deterministic procedural worlds from a single root seed.
"""

__version__ = "1.0.0"
__author__ = "Procedural Engine Team"

# Public API exports for backward compatibility
# These will be populated as modules are moved into the package

# Core
from procengine.core.engine import Engine
from procengine.core.seed_registry import SeedRegistry

# World generation
from procengine.world.terrain import generate_terrain_maps
from procengine.world.props import (
    generate_rock_descriptors,
    generate_tree_descriptors,
    generate_building_descriptors,
    generate_creature_descriptors,
)
from procengine.world.materials import generate_material_graph
from procengine.world.world import generate_chunk, generate_world

# Physics
from procengine.physics.bodies import RigidBody, RigidBody3D, Vec3
from procengine.physics.collision import step_physics, step_physics_3d
from procengine.physics.heightfield import HeightField, HeightField2D

# Game API
from procengine.game.game_api import (
    GameWorld,
    Entity,
    Player,
    NPC,
    Prop,
    Item,
    EventBus,
    Event,
    EventType,
    GameConfig,
)
from procengine.game.behavior_tree import (
    BehaviorTree,
    Selector,
    Sequence,
    Parallel,
    Inverter,
    Succeeder,
    Repeater,
    Action,
    Condition,
    NodeStatus,
    Blackboard,
)
from procengine.game.game_runner import GameRunner, RunnerConfig

# Utility
from procengine.utils.seed_sweeper import generate_seed_batch

__all__ = [
    # Version info
    "__version__",
    "__author__",
    # Core
    "Engine",
    "SeedRegistry",
    # World
    "generate_terrain_maps",
    "generate_rock_descriptors",
    "generate_tree_descriptors",
    "generate_building_descriptors",
    "generate_creature_descriptors",
    "generate_material_graph",
    "generate_chunk",
    "generate_world",
    # Physics
    "RigidBody",
    "RigidBody3D",
    "Vec3",
    "step_physics",
    "step_physics_3d",
    "HeightField",
    "HeightField2D",
    # Game
    "GameWorld",
    "Entity",
    "Player",
    "NPC",
    "Prop",
    "Item",
    "EventBus",
    "Event",
    "EventType",
    "GameConfig",
    # Behavior Tree
    "BehaviorTree",
    "Selector",
    "Sequence",
    "Parallel",
    "Inverter",
    "Succeeder",
    "Repeater",
    "Action",
    "Condition",
    "NodeStatus",
    "Blackboard",
    # Game Runner
    "GameRunner",
    "RunnerConfig",
    # Utils
    "generate_seed_batch",
]
