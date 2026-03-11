"""Game API layer for the Procedural Engine.

This module provides the game-level abstractions that sit above the engine:
- Entity hierarchy (Entity, Character, Player, NPC, Prop, Item)
- GameWorld for state management and entity lifecycle
- Event system for decoupled game systems
- Inventory and equipment management
- Quest tracking and objectives

The game layer uses the engine—it doesn't modify it. All game state flows
through well-defined interfaces to ensure the engine remains reusable.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple  # noqa: UP035

from procengine.core.seed_registry import SeedRegistry
from procengine.game.behavior_tree import (
    BehaviorTree,
    NodeStatus,
    create_guard_behavior,
    create_idle_behavior,
    create_patrol_behavior,
)
from procengine.physics import HeightField2D, RigidBody3D, Vec3, step_physics_3d

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    # Core types
    "EntityId",
    "EventType",
    "Event",
    # Entities
    "Entity",
    "Character",
    "Player",
    "NPC",
    "Creature",
    "Prop",
    "Item",
    # Inventory & Crafting
    "Inventory",
    "ItemDefinition",
    "CraftingRecipe",
    # Quest system
    "Quest",
    "QuestObjective",
    "QuestState",
    "ObjectiveType",
    # Dialogue
    "DialogueResponse",
    "DialogueContext",
    # Agent framework
    "NPCAgent",
    "LocalAgent",
    # Game world
    "GameWorld",
    "GameConfig",
]


# =============================================================================
# Type Aliases
# =============================================================================

EntityId = str  # Unique identifier for entities


# =============================================================================
# Event System
# =============================================================================


class EventType(Enum):
    """Types of events emitted by the game world."""

    # Entity events
    ENTITY_SPAWNED = auto()
    ENTITY_DESTROYED = auto()
    ENTITY_MOVED = auto()

    # Player events
    PLAYER_MOVED = auto()
    PLAYER_INTERACTED = auto()
    PLAYER_ENTERED_REGION = auto()

    # NPC events
    NPC_SPAWNED = auto()
    NPC_BEHAVIOR_CHANGED = auto()
    NPC_DIALOGUE_STARTED = auto()
    NPC_DIALOGUE_ENDED = auto()

    # Quest events
    QUEST_AVAILABLE = auto()
    QUEST_STARTED = auto()
    QUEST_OBJECTIVE_UPDATED = auto()
    QUEST_COMPLETED = auto()
    QUEST_FAILED = auto()

    # Inventory events
    ITEM_ACQUIRED = auto()
    ITEM_DROPPED = auto()
    ITEM_USED = auto()
    ITEM_CRAFTED = auto()

    # Creature events
    CREATURE_SPAWNED = auto()
    CREATURE_FLED = auto()
    CREATURE_DIED = auto()

    # World events
    WORLD_GENERATED = auto()
    CHUNK_LOADED = auto()
    CHUNK_UNLOADED = auto()


@dataclass
class Event:
    """Game event with type and associated data."""

    event_type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source_entity: Optional[EntityId] = None
    target_entity: Optional[EntityId] = None


EventCallback = Callable[[Event], None]


class EventBus:
    """Simple pub/sub event system for decoupled game systems."""

    def __init__(self) -> None:
        self._listeners: Dict[EventType, List[EventCallback]] = {}
        self._global_listeners: List[EventCallback] = []

    def subscribe(
        self, event_type: EventType, callback: EventCallback
    ) -> Callable[[], None]:
        """Subscribe to a specific event type.

        Returns an unsubscribe function.
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

        def unsubscribe() -> None:
            if callback in self._listeners.get(event_type, []):
                self._listeners[event_type].remove(callback)

        return unsubscribe

    def subscribe_all(self, callback: EventCallback) -> Callable[[], None]:
        """Subscribe to all events.

        Returns an unsubscribe function.
        """
        self._global_listeners.append(callback)

        def unsubscribe() -> None:
            if callback in self._global_listeners:
                self._global_listeners.remove(callback)

        return unsubscribe

    def emit(self, event: Event) -> None:
        """Emit an event to all subscribed listeners."""
        # Notify type-specific listeners
        for callback in self._listeners.get(event.event_type, []):
            callback(event)
        # Notify global listeners
        for callback in self._global_listeners:
            callback(event)


# =============================================================================
# Entity Hierarchy
# =============================================================================


@dataclass
class Entity:
    """Base class for all game entities.

    Entities have a unique ID, position, and can be serialized.
    """

    entity_id: EntityId = field(default_factory=lambda: str(uuid.uuid4())[:8])
    position: Vec3 = field(default_factory=Vec3)
    rotation: float = 0.0  # Y-axis rotation in radians
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entity to dictionary for save/load."""
        return {
            "entity_id": self.entity_id,
            "position": {"x": self.position.x, "y": self.position.y, "z": self.position.z},
            "rotation": self.rotation,
            "active": self.active,
            "type": self.__class__.__name__,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Entity:
        """Deserialize entity from dictionary."""
        pos_data = data.get("position", {})
        return cls(
            entity_id=data.get("entity_id", str(uuid.uuid4())[:8]),
            position=Vec3(
                pos_data.get("x", 0.0),
                pos_data.get("y", 0.0),
                pos_data.get("z", 0.0),
            ),
            rotation=data.get("rotation", 0.0),
            active=data.get("active", True),
        )


@dataclass
class Character(Entity):
    """Base class for entities with health, inventory, and physics body.

    Characters are entities that can move, have health, and carry items.
    """

    health: float = 100.0
    max_health: float = 100.0
    inventory: "Inventory" = field(default_factory=lambda: Inventory())
    velocity: Vec3 = field(default_factory=Vec3)
    mass: float = 70.0  # kg
    radius: float = 0.4  # meters (collision radius)
    grounded: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.inventory, Inventory):
            self.inventory = Inventory()

    def is_alive(self) -> bool:
        """Check if character is alive."""
        return self.health > 0

    def take_damage(self, amount: float) -> None:
        """Apply damage to character."""
        self.health = max(0.0, self.health - amount)

    def heal(self, amount: float) -> None:
        """Heal character."""
        self.health = min(self.max_health, self.health + amount)

    def to_rigid_body(self) -> RigidBody3D:
        """Create a physics body from this character."""
        return RigidBody3D(
            position=Vec3(self.position.x, self.position.y, self.position.z),
            velocity=Vec3(self.velocity.x, self.velocity.y, self.velocity.z),
            mass=self.mass,
            radius=self.radius,
            grounded=self.grounded,
        )

    def apply_rigid_body(self, body: RigidBody3D) -> None:
        """Apply physics body state back to character."""
        self.position = Vec3(body.position.x, body.position.y, body.position.z)
        self.velocity = Vec3(body.velocity.x, body.velocity.y, body.velocity.z)
        self.grounded = body.grounded

    def to_dict(self) -> Dict[str, Any]:
        """Serialize character to dictionary."""
        data = super().to_dict()
        data.update({
            "health": self.health,
            "max_health": self.max_health,
            "inventory": self.inventory.to_dict(),
            "velocity": {"x": self.velocity.x, "y": self.velocity.y, "z": self.velocity.z},
            "mass": self.mass,
            "radius": self.radius,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        """Deserialize character from dictionary."""
        entity = super().from_dict(data)
        vel_data = data.get("velocity", {})
        char = cls(
            entity_id=entity.entity_id,
            position=entity.position,
            rotation=entity.rotation,
            active=entity.active,
            health=data.get("health", 100.0),
            max_health=data.get("max_health", 100.0),
            inventory=Inventory.from_dict(data.get("inventory", {})),
            velocity=Vec3(
                vel_data.get("x", 0.0),
                vel_data.get("y", 0.0),
                vel_data.get("z", 0.0),
            ),
            mass=data.get("mass", 70.0),
            radius=data.get("radius", 0.4),
        )
        return char


@dataclass
class Player(Character):
    """Player entity with input handling, quest log, and dialogue history.

    The player is a special character that can interact with the world,
    complete quests, and have conversations with NPCs.
    """

    name: str = "Player"
    active_quests: List[str] = field(default_factory=list)  # Quest IDs
    completed_quests: List[str] = field(default_factory=list)  # Quest IDs
    dialogue_history: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    interaction_range: float = 2.0  # meters
    current_interaction_target: Optional[EntityId] = None

    # Movement state
    is_jumping: bool = False
    is_sprinting: bool = False
    move_speed: float = 5.0  # m/s walking
    sprint_multiplier: float = 1.5
    jump_velocity: float = 5.0  # m/s upward

    # Equipment
    equipped_weapon: Optional[str] = None  # item_id of held weapon/tool

    def get_move_speed(self) -> float:
        """Get current movement speed based on state."""
        speed = self.move_speed
        if self.is_sprinting:
            speed *= self.sprint_multiplier
        return speed

    def can_interact_with(self, other: Entity) -> bool:
        """Check if player can interact with another entity."""
        distance = (other.position - self.position).length()
        return distance <= self.interaction_range

    def add_dialogue(self, npc_id: str, role: str, content: str) -> None:
        """Add a dialogue entry to history with an NPC."""
        if npc_id not in self.dialogue_history:
            self.dialogue_history[npc_id] = []
        self.dialogue_history[npc_id].append({"role": role, "content": content})

    def get_dialogue_history(self, npc_id: str) -> List[Dict[str, str]]:
        """Get dialogue history with a specific NPC."""
        return self.dialogue_history.get(npc_id, [])

    def to_dict(self) -> Dict[str, Any]:
        """Serialize player to dictionary."""
        data = super().to_dict()
        data.update({
            "name": self.name,
            "active_quests": self.active_quests.copy(),
            "completed_quests": self.completed_quests.copy(),
            "dialogue_history": {k: v.copy() for k, v in self.dialogue_history.items()},
            "interaction_range": self.interaction_range,
            "move_speed": self.move_speed,
            "sprint_multiplier": self.sprint_multiplier,
            "jump_velocity": self.jump_velocity,
            "equipped_weapon": self.equipped_weapon,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Player":
        """Deserialize player from dictionary."""
        char = super().from_dict(data)
        return cls(
            entity_id=char.entity_id,
            position=char.position,
            rotation=char.rotation,
            active=char.active,
            health=char.health,
            max_health=char.max_health,
            inventory=char.inventory,
            velocity=char.velocity,
            mass=char.mass,
            radius=char.radius,
            name=data.get("name", "Player"),
            active_quests=data.get("active_quests", []),
            completed_quests=data.get("completed_quests", []),
            dialogue_history=data.get("dialogue_history", {}),
            interaction_range=data.get("interaction_range", 2.0),
            move_speed=data.get("move_speed", 5.0),
            sprint_multiplier=data.get("sprint_multiplier", 1.5),
            jump_velocity=data.get("jump_velocity", 5.0),
            equipped_weapon=data.get("equipped_weapon"),
        )


@dataclass
class NPC(Character):
    """Non-player character with personality, behavior, and AI agent.

    NPCs have autonomous behavior via behavior trees and can engage
    in dialogue with the player. They support both local (template-based)
    and AI-powered (MCP) agents.
    """

    name: str = "NPC"
    personality: str = ""  # Natural language description for AI context
    behavior: str = "idle"  # Current behavior state
    behavior_params: Dict[str, Any] = field(default_factory=dict)
    memory: List[Dict[str, Any]] = field(default_factory=list)  # Conversation memory
    relationships: Dict[str, float] = field(default_factory=dict)  # EntityId -> disposition (-1 to 1)
    current_quest: Optional[str] = None  # Quest this NPC is associated with
    dialogue_range: float = 3.0  # How close player must be to talk
    is_merchant: bool = False
    merchant_inventory: "Inventory" = field(default_factory=lambda: Inventory())

    # AI agent reference (set by GameWorld)
    _agent: Optional["NPCAgent"] = field(default=None, repr=False)

    # Behavior tree for autonomous behavior (optional)
    _behavior_tree: Optional[BehaviorTree] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.merchant_inventory, Inventory):
            self.merchant_inventory = Inventory()

    def get_disposition(self, entity_id: str) -> float:
        """Get disposition toward another entity (-1 hostile to +1 friendly)."""
        return self.relationships.get(entity_id, 0.0)

    def set_disposition(self, entity_id: str, value: float) -> None:
        """Set disposition toward another entity."""
        self.relationships[entity_id] = max(-1.0, min(1.0, value))

    def adjust_disposition(self, entity_id: str, delta: float) -> None:
        """Adjust disposition toward another entity."""
        current = self.get_disposition(entity_id)
        self.set_disposition(entity_id, current + delta)

    def add_memory(self, memory_entry: Dict[str, Any]) -> None:
        """Add a memory entry (for AI context)."""
        self.memory.append(memory_entry)
        # Keep memory bounded
        if len(self.memory) > 50:
            self.memory = self.memory[-50:]

    def can_talk(self, player_pos: Vec3) -> bool:
        """Check if player is close enough to talk."""
        distance = (player_pos - self.position).length()
        return distance <= self.dialogue_range

    def set_behavior_tree(self, tree: BehaviorTree) -> None:
        """Set the NPC's behavior tree for autonomous behavior."""
        self._behavior_tree = tree

    def get_behavior_tree(self) -> Optional[BehaviorTree]:
        """Get the NPC's behavior tree."""
        return self._behavior_tree

    def tick_behavior(self, world: "GameWorld", dt: float) -> Optional[NodeStatus]:
        """Tick the NPC's behavior tree if one is assigned.

        Returns
        -------
        Optional[NodeStatus]:
            The status from the behavior tree, or None if no tree assigned.
        """
        if self._behavior_tree is not None:
            return self._behavior_tree.tick(self, world, dt)
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize NPC to dictionary."""
        data = super().to_dict()
        data.update({
            "name": self.name,
            "personality": self.personality,
            "behavior": self.behavior,
            "behavior_params": self.behavior_params.copy(),
            "memory": [m.copy() for m in self.memory],
            "relationships": self.relationships.copy(),
            "current_quest": self.current_quest,
            "dialogue_range": self.dialogue_range,
            "is_merchant": self.is_merchant,
            "merchant_inventory": self.merchant_inventory.to_dict(),
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NPC":
        """Deserialize NPC from dictionary."""
        char = Character.from_dict(data)
        return cls(
            entity_id=char.entity_id,
            position=char.position,
            rotation=char.rotation,
            active=char.active,
            health=char.health,
            max_health=char.max_health,
            inventory=char.inventory,
            velocity=char.velocity,
            mass=char.mass,
            radius=char.radius,
            name=data.get("name", "NPC"),
            personality=data.get("personality", ""),
            behavior=data.get("behavior", "idle"),
            behavior_params=data.get("behavior_params", {}),
            memory=data.get("memory", []),
            relationships=data.get("relationships", {}),
            current_quest=data.get("current_quest"),
            dialogue_range=data.get("dialogue_range", 3.0),
            is_merchant=data.get("is_merchant", False),
            merchant_inventory=Inventory.from_dict(data.get("merchant_inventory", {})),
        )


@dataclass
class Prop(Entity):
    """Static world objects (rocks, trees, furniture, etc.).

    Props are non-character entities that exist in the world.
    They can be interactable or purely decorative.
    """

    prop_type: str = "generic"  # rock, tree, chest, door, etc.
    interactable: bool = False
    interaction_action: str = ""  # Action when interacted with
    state: Dict[str, Any] = field(default_factory=dict)  # Prop-specific state

    @property
    def is_harvestable(self) -> bool:
        """Return ``True`` when this prop can still be harvested."""
        return (
            self.interaction_action == "harvest"
            and self.state.get("hits_remaining", 0) > 0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize prop to dictionary."""
        data = super().to_dict()
        data.update({
            "prop_type": self.prop_type,
            "interactable": self.interactable,
            "interaction_action": self.interaction_action,
            "state": self.state.copy(),
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Prop":
        """Deserialize prop from dictionary."""
        entity = Entity.from_dict(data)
        return cls(
            entity_id=entity.entity_id,
            position=entity.position,
            rotation=entity.rotation,
            active=entity.active,
            prop_type=data.get("prop_type", "generic"),
            interactable=data.get("interactable", False),
            interaction_action=data.get("interaction_action", ""),
            state=data.get("state", {}),
        )


@dataclass
class Creature(Character):
    """A procedurally-generated creature with autonomous behavior.

    Creatures are Character entities with metaball-based mesh generation,
    skeleton data for animation, and creature-specific behavior trees.
    Unlike NPCs, creatures don't have dialogue or quest systems —
    they operate on instinct-based AI (wander, flee, etc.).
    """

    # Creature identity
    creature_type: str = "generic"
    body_plan: str = "quadruped"  # "quadruped" or "biped"

    # Mesh descriptor data (drives C++ metaball mesh generation)
    skeleton: List[Dict[str, Any]] = field(default_factory=list)
    metaballs: List[Dict[str, Any]] = field(default_factory=list)
    limbs: List[Dict[str, Any]] = field(default_factory=list)

    # Creature-specific behavior
    behavior: str = "wander"
    behavior_params: Dict[str, Any] = field(default_factory=dict)
    awareness_range: float = 15.0
    flee_range: float = 8.0
    move_speed: float = 2.5

    # Vision cone parameters (set from CreatureTemplate at spawn time)
    vision_half_angle_deg: float = 60.0
    vision_range: float = 15.0
    turn_speed: float = 4.0

    # Internal state
    _behavior_tree: Optional[BehaviorTree] = field(default=None, repr=False)

    def tick_behavior(self, world: "GameWorld", dt: float) -> Optional[NodeStatus]:
        """Tick the creature's behavior tree."""
        if self._behavior_tree is not None:
            return self._behavior_tree.tick(self, world, dt)
        return None

    def set_behavior_tree(self, tree: BehaviorTree) -> None:
        """Set the creature's behavior tree."""
        self._behavior_tree = tree

    def get_behavior_tree(self) -> Optional[BehaviorTree]:
        """Get the creature's behavior tree."""
        return self._behavior_tree

    def to_dict(self) -> Dict[str, Any]:
        """Serialize creature to dictionary."""
        data = super().to_dict()
        data.update({
            "creature_type": self.creature_type,
            "body_plan": self.body_plan,
            "skeleton": [s.copy() for s in self.skeleton],
            "metaballs": [m.copy() for m in self.metaballs],
            "limbs": [lm.copy() for lm in self.limbs],
            "behavior": self.behavior,
            "behavior_params": self.behavior_params.copy(),
            "awareness_range": self.awareness_range,
            "flee_range": self.flee_range,
            "move_speed": self.move_speed,
            "vision_half_angle_deg": self.vision_half_angle_deg,
            "vision_range": self.vision_range,
            "turn_speed": self.turn_speed,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Creature":
        """Deserialize creature from dictionary."""
        char = Character.from_dict(data)
        return cls(
            entity_id=char.entity_id,
            position=char.position,
            rotation=char.rotation,
            active=char.active,
            health=char.health,
            max_health=char.max_health,
            inventory=char.inventory,
            velocity=char.velocity,
            mass=char.mass,
            radius=char.radius,
            creature_type=data.get("creature_type", "generic"),
            body_plan=data.get("body_plan", "quadruped"),
            skeleton=data.get("skeleton", []),
            metaballs=data.get("metaballs", []),
            limbs=data.get("limbs", []),
            behavior=data.get("behavior", "wander"),
            behavior_params=data.get("behavior_params", {}),
            awareness_range=data.get("awareness_range", 15.0),
            flee_range=data.get("flee_range", 8.0),
            move_speed=data.get("move_speed", 2.5),
            vision_half_angle_deg=data.get("vision_half_angle_deg", 60.0),
            vision_range=data.get("vision_range", 15.0),
            turn_speed=data.get("turn_speed", 4.0),
        )


# =============================================================================
# Inventory System
# =============================================================================


@dataclass
class ItemDefinition:
    """Definition of an item type (loaded from data files)."""

    item_id: str
    name: str
    description: str = ""
    item_type: str = "misc"  # weapon, armor, consumable, quest, misc
    value: int = 0
    stackable: bool = True
    max_stack: int = 99
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize item definition to dictionary."""
        return {
            "item_id": self.item_id,
            "name": self.name,
            "description": self.description,
            "item_type": self.item_type,
            "value": self.value,
            "stackable": self.stackable,
            "max_stack": self.max_stack,
            "properties": self.properties.copy(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemDefinition":
        """Deserialize item definition from dictionary."""
        return cls(
            item_id=data["item_id"],
            name=data["name"],
            description=data.get("description", ""),
            item_type=data.get("item_type", "misc"),
            value=data.get("value", 0),
            stackable=data.get("stackable", True),
            max_stack=data.get("max_stack", 99),
            properties=data.get("properties", {}),
        )


@dataclass
class CraftingRecipe:
    """Definition of a crafting recipe."""

    recipe_id: str
    name: str
    description: str = ""
    ingredients: Dict[str, int] = field(default_factory=dict)  # item_id -> count
    result_item: str = ""  # item_id of crafted item
    result_count: int = 1
    category: str = "misc"  # materials, tools, weapons, armor, consumables

    def can_craft(self, inventory: "Inventory") -> bool:
        """Check if inventory has all required ingredients."""
        return all(
            inventory.has_item(item_id, count)
            for item_id, count in self.ingredients.items()
        )

    def get_ingredient_ids(self) -> frozenset:
        """Return the set of ingredient item IDs (for matching)."""
        return frozenset(self.ingredients.keys())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize recipe to dictionary."""
        return {
            "recipe_id": self.recipe_id,
            "name": self.name,
            "description": self.description,
            "ingredients": self.ingredients.copy(),
            "result_item": self.result_item,
            "result_count": self.result_count,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CraftingRecipe":
        """Deserialize recipe from dictionary."""
        return cls(
            recipe_id=data["recipe_id"],
            name=data["name"],
            description=data.get("description", ""),
            ingredients=data.get("ingredients", {}),
            result_item=data.get("result_item", ""),
            result_count=data.get("result_count", 1),
            category=data.get("category", "misc"),
        )


@dataclass
class Item(Entity):
    """World item entity (dropped item, chest contents, etc.)."""

    item_id: str = ""  # References ItemDefinition
    count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialize item entity to dictionary."""
        data = super().to_dict()
        data.update({
            "item_id": self.item_id,
            "count": self.count,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Item":
        """Deserialize item entity from dictionary."""
        entity = Entity.from_dict(data)
        return cls(
            entity_id=entity.entity_id,
            position=entity.position,
            rotation=entity.rotation,
            active=entity.active,
            item_id=data.get("item_id", ""),
            count=data.get("count", 1),
        )


@dataclass
class Inventory:
    """Container for items with slot-based storage."""

    items: Dict[str, int] = field(default_factory=dict)  # item_id -> count
    capacity: int = 100  # Max total items

    def add_item(self, item_id: str, count: int = 1) -> int:
        """Add items to inventory. Returns count actually added."""
        current_total = sum(self.items.values())
        available_space = self.capacity - current_total
        actual_add = min(count, available_space)

        if actual_add > 0:
            self.items[item_id] = self.items.get(item_id, 0) + actual_add
        return actual_add

    def remove_item(self, item_id: str, count: int = 1) -> int:
        """Remove items from inventory. Returns count actually removed."""
        current = self.items.get(item_id, 0)
        actual_remove = min(count, current)

        if actual_remove > 0:
            self.items[item_id] = current - actual_remove
            if self.items[item_id] <= 0:
                del self.items[item_id]
        return actual_remove

    def has_item(self, item_id: str, count: int = 1) -> bool:
        """Check if inventory has at least count of item."""
        return self.items.get(item_id, 0) >= count

    def get_count(self, item_id: str) -> int:
        """Get count of a specific item."""
        return self.items.get(item_id, 0)

    def get_all_items(self) -> Dict[str, int]:
        """Get all items in inventory."""
        return self.items.copy()

    def clear(self) -> None:
        """Remove all items from inventory."""
        self.items.clear()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize inventory to dictionary."""
        return {
            "items": self.items.copy(),
            "capacity": self.capacity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Inventory":
        """Deserialize inventory from dictionary."""
        return cls(
            items=data.get("items", {}),
            capacity=data.get("capacity", 100),
        )


# =============================================================================
# Quest System
# =============================================================================


class QuestState(Enum):
    """State of a quest."""

    UNAVAILABLE = auto()  # Prerequisites not met
    AVAILABLE = auto()  # Can be started
    ACTIVE = auto()  # In progress
    COMPLETED = auto()  # Successfully finished
    FAILED = auto()  # Failed (optional state)


class ObjectiveType(Enum):
    """Types of quest objectives."""

    COLLECT = auto()  # Gather N of item X
    KILL = auto()  # Defeat N of enemy type X
    TALK = auto()  # Speak to NPC X
    LOCATION = auto()  # Reach location X
    DELIVER = auto()  # Bring item X to NPC Y
    CUSTOM = auto()  # Custom objective with callback


@dataclass
class QuestObjective:
    """A single objective within a quest."""

    objective_id: str
    description: str
    objective_type: ObjectiveType
    target: str  # item_id, enemy_type, npc_id, or location_id
    required_count: int = 1
    current_count: int = 0
    optional: bool = False

    def is_complete(self) -> bool:
        """Check if objective is complete."""
        return self.current_count >= self.required_count

    def update_progress(self, amount: int = 1) -> bool:
        """Update objective progress. Returns True if just completed."""
        was_complete = self.is_complete()
        self.current_count = min(self.required_count, self.current_count + amount)
        return not was_complete and self.is_complete()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize objective to dictionary."""
        return {
            "objective_id": self.objective_id,
            "description": self.description,
            "objective_type": self.objective_type.name,
            "target": self.target,
            "required_count": self.required_count,
            "current_count": self.current_count,
            "optional": self.optional,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuestObjective":
        """Deserialize objective from dictionary."""
        return cls(
            objective_id=data["objective_id"],
            description=data["description"],
            objective_type=ObjectiveType[data["objective_type"]],
            target=data["target"],
            required_count=data.get("required_count", 1),
            current_count=data.get("current_count", 0),
            optional=data.get("optional", False),
        )


@dataclass
class Quest:
    """A quest with objectives and rewards."""

    quest_id: str
    title: str
    description: str
    giver_npc_id: str
    objectives: List[QuestObjective] = field(default_factory=list)
    rewards: Dict[str, Any] = field(default_factory=dict)
    prerequisites: List[str] = field(default_factory=list)  # Required completed quests
    on_complete_actions: List[Dict[str, Any]] = field(default_factory=list)
    state: QuestState = QuestState.UNAVAILABLE

    def is_complete(self) -> bool:
        """Check if all required objectives are complete."""
        return all(
            obj.is_complete()
            for obj in self.objectives
            if not obj.optional
        )

    def get_progress(self) -> Tuple[int, int]:
        """Get (completed, total) required objectives."""
        required = [o for o in self.objectives if not o.optional]
        completed = sum(1 for o in required if o.is_complete())
        return completed, len(required)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize quest to dictionary."""
        return {
            "quest_id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "giver_npc_id": self.giver_npc_id,
            "objectives": [o.to_dict() for o in self.objectives],
            "rewards": self.rewards.copy(),
            "prerequisites": self.prerequisites.copy(),
            "on_complete_actions": [a.copy() for a in self.on_complete_actions],
            "state": self.state.name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Quest":
        """Deserialize quest from dictionary."""
        return cls(
            quest_id=data["quest_id"],
            title=data["title"],
            description=data["description"],
            giver_npc_id=data["giver_npc_id"],
            objectives=[
                QuestObjective.from_dict(o) for o in data.get("objectives", [])
            ],
            rewards=data.get("rewards", {}),
            prerequisites=data.get("prerequisites", []),
            on_complete_actions=data.get("on_complete_actions", []),
            state=QuestState[data.get("state", "UNAVAILABLE")],
        )


# =============================================================================
# Dialogue System
# =============================================================================


@dataclass
class DialogueResponse:
    """Response from an NPC in dialogue."""

    text: str  # What the NPC says
    emotion: str = "neutral"  # For UI/animation: neutral, happy, angry, sad, etc.
    actions: List[Dict[str, Any]] = field(default_factory=list)  # Side effects
    options: List[Dict[str, str]] = field(default_factory=list)  # Player response options
    ends_conversation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize response to dictionary."""
        return {
            "text": self.text,
            "emotion": self.emotion,
            "actions": [a.copy() for a in self.actions],
            "options": [o.copy() for o in self.options],
            "ends_conversation": self.ends_conversation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DialogueResponse":
        """Deserialize response from dictionary."""
        return cls(
            text=data["text"],
            emotion=data.get("emotion", "neutral"),
            actions=data.get("actions", []),
            options=data.get("options", []),
            ends_conversation=data.get("ends_conversation", False),
        )


@dataclass
class DialogueContext:
    """Context provided to NPC agent for dialogue generation."""

    npc_id: str
    npc_name: str
    npc_personality: str
    npc_behavior: str
    npc_current_quest: Optional[str]
    relationship_to_player: float
    player_name: str
    player_active_quests: List[str]
    player_inventory_summary: List[str]
    conversation_history: List[Dict[str, str]]
    world_context: Dict[str, Any]
    player_message: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary for agent processing."""
        return {
            "npc": {
                "id": self.npc_id,
                "name": self.npc_name,
                "personality": self.npc_personality,
                "behavior": self.npc_behavior,
                "current_quest": self.npc_current_quest,
                "relationship_to_player": self.relationship_to_player,
            },
            "player": {
                "name": self.player_name,
                "active_quests": self.player_active_quests,
                "inventory_summary": self.player_inventory_summary,
            },
            "conversation_history": self.conversation_history,
            "world_context": self.world_context,
            "player_message": self.player_message,
        }


# =============================================================================
# NPC Agent Framework
# =============================================================================


class NPCAgent(ABC):
    """Abstract interface for NPC decision-making.

    This interface enables both local (template-based) and AI-powered
    (MCP) agents to control NPC behavior and dialogue.
    """

    @abstractmethod
    def get_dialogue_response(self, context: DialogueContext) -> DialogueResponse:
        """Generate response to player dialogue.

        Parameters
        ----------
        context:
            Full context including NPC personality, conversation history,
            player state, and world context.

        Returns
        -------
        DialogueResponse:
            The NPC's response including text, emotion, and any actions.
        """
        pass

    @abstractmethod
    def get_next_action(self, npc: NPC, world: "GameWorld") -> Optional[Dict[str, Any]]:
        """Decide what the NPC should do next.

        Parameters
        ----------
        npc:
            The NPC to decide for.
        world:
            The game world for context.

        Returns
        -------
        Optional[Dict[str, Any]]:
            An action dict or None for no action. Action types include:
            - {"type": "move_to", "target": Vec3}
            - {"type": "idle", "duration": float}
            - {"type": "follow", "target_id": str}
            - {"type": "patrol", "waypoints": List[Vec3]}
        """
        pass


class LocalAgent(NPCAgent):
    """Offline NPC agent using templates, behavior trees, and simple logic.

    Provides reasonable NPC behavior without any AI connection.
    Uses personality-influenced template responses, behavior trees for
    autonomous movement, and simple state-based behavior decisions.

    The agent automatically assigns appropriate behavior trees to NPCs
    based on their behavior type (idle, patrol, guard, etc.).
    """

    # Default dialogue templates by behavior type
    DEFAULT_TEMPLATES: Dict[str, List[str]] = {
        "idle": [
            "Hello there.",
            "Nice day, isn't it?",
            "What can I do for you?",
        ],
        "merchant": [
            "Looking to trade?",
            "I have fine wares for sale.",
            "Take a look at my goods.",
        ],
        "guard": [
            "Move along, citizen.",
            "Stay out of trouble.",
            "I'm watching you.",
        ],
        "quest_giver": [
            "I have a task for you, if you're interested.",
            "Are you looking for work?",
            "I could use some help.",
        ],
    }

    FAREWELL_TEMPLATES: List[str] = [
        "Farewell.",
        "Safe travels.",
        "Until next time.",
    ]

    def __init__(
        self,
        custom_templates: Optional[Dict[str, List[str]]] = None,
        dialogue_trees: Optional[Dict[str, Any]] = None,
        rng: Optional["np.random.Generator"] = None,
    ) -> None:
        """Initialize local agent with optional custom templates.

        Parameters
        ----------
        custom_templates:
            Custom dialogue templates by behavior type.
        dialogue_trees:
            Structured dialogue trees for specific NPCs/quests.
        rng:
            NumPy random Generator for deterministic behavior. If None, a
            default seeded generator is created from SeedRegistry(0).
        """
        import numpy as np

        self.templates = self.DEFAULT_TEMPLATES.copy()
        if custom_templates:
            self.templates.update(custom_templates)
        self.dialogue_trees = dialogue_trees or {}
        # Use provided RNG or create a default deterministic one
        if rng is not None:
            self._rng = rng
        else:
            self._rng = SeedRegistry(0).get_rng("local_agent")

    def configure_npc_behavior(self, npc: NPC) -> None:
        """Configure NPC behavior tree based on their behavior type.

        This method assigns an appropriate behavior tree to the NPC based
        on their behavior string. Called automatically when NPC is spawned.

        Parameters
        ----------
        npc:
            The NPC to configure.
        """
        behavior = npc.behavior

        if behavior == "idle":
            npc.set_behavior_tree(create_idle_behavior(wait_min=2.0, wait_max=6.0))

        elif behavior == "patrol":
            # Use waypoints from behavior_params, or create default patrol route
            waypoints = npc.behavior_params.get("waypoints", [])
            if not waypoints:
                # Default small patrol around spawn position
                waypoints = [
                    npc.position + Vec3(3, 0, 0),
                    npc.position + Vec3(3, 0, 3),
                    npc.position + Vec3(0, 0, 3),
                    npc.position,
                ]
            speed = npc.behavior_params.get("patrol_speed", 2.0)
            npc.set_behavior_tree(create_patrol_behavior(waypoints, speed))

        elif behavior == "guard":
            guard_range = npc.behavior_params.get("alert_range", 8.0)
            npc.set_behavior_tree(create_guard_behavior(npc.position, guard_range))

        elif behavior == "wander":
            # Wander uses idle behavior with movement from get_next_action
            npc.set_behavior_tree(create_idle_behavior(wait_min=1.0, wait_max=3.0))

        elif behavior == "merchant":
            # Merchants just idle in place
            npc.set_behavior_tree(create_idle_behavior(wait_min=5.0, wait_max=15.0))

        # Other behaviors can be added as needed
        # NPCs without a configured behavior tree will use get_next_action

    def get_dialogue_response(self, context: DialogueContext) -> DialogueResponse:
        """Generate template-based dialogue response."""
        behavior = context.npc_behavior
        player_msg = context.player_message.lower()

        # Check for farewell keywords
        farewell_keywords = ["bye", "goodbye", "farewell", "see you", "later"]
        if any(kw in player_msg for kw in farewell_keywords):
            idx = self._rng.integers(0, len(self.FAREWELL_TEMPLATES))
            return DialogueResponse(
                text=self.FAREWELL_TEMPLATES[idx],
                emotion="neutral",
                ends_conversation=True,
            )

        # Check for quest-related dialogue
        if context.npc_current_quest:
            quest_response = self._handle_quest_dialogue(context)
            if quest_response:
                return quest_response

        # Get templates for this behavior
        templates = self.templates.get(behavior, self.templates["idle"])

        # Simple response selection (could be improved with keyword matching)
        idx = self._rng.integers(0, len(templates))
        text = templates[idx]

        # Adjust emotion based on relationship
        emotion = "neutral"
        if context.relationship_to_player > 0.5:
            emotion = "friendly"
        elif context.relationship_to_player < -0.5:
            emotion = "suspicious"

        return DialogueResponse(
            text=text,
            emotion=emotion,
        )

    def _handle_quest_dialogue(self, context: DialogueContext) -> Optional[DialogueResponse]:
        """Handle quest-related dialogue."""
        quest_id = context.npc_current_quest
        player_msg = context.player_message.lower()

        # Check if player is asking about quests
        quest_keywords = ["quest", "task", "help", "job", "work", "mission"]
        if any(kw in player_msg for kw in quest_keywords):
            if quest_id not in context.player_active_quests:
                # Offer quest
                return DialogueResponse(
                    text=f"I have a task that needs doing. Are you interested?",
                    emotion="hopeful",
                    options=[
                        {"label": "Yes, I'll help.", "value": "accept_quest"},
                        {"label": "Not right now.", "value": "decline_quest"},
                    ],
                )
            else:
                # Quest in progress
                return DialogueResponse(
                    text="How goes the task I gave you?",
                    emotion="curious",
                )

        # Check for quest acceptance
        if "accept" in player_msg or "yes" in player_msg or "help" in player_msg:
            return DialogueResponse(
                text="Excellent! I knew I could count on you.",
                emotion="happy",
                actions=[{"type": "give_quest", "quest_id": quest_id}],
            )

        return None

    def get_next_action(self, npc: NPC, world: "GameWorld") -> Optional[Dict[str, Any]]:
        """Determine next action based on behavior state."""
        behavior = npc.behavior

        if behavior == "idle":
            return {"type": "idle", "duration": 5.0}

        elif behavior == "wander":
            # Simple deterministic wander using seeded RNG
            offset = Vec3(
                float(self._rng.uniform(-5, 5)),
                0,
                float(self._rng.uniform(-5, 5)),
            )
            target = npc.position + offset
            return {"type": "move_to", "target": target}

        elif behavior == "patrol":
            waypoints = npc.behavior_params.get("waypoints", [])
            if waypoints:
                current_idx = npc.behavior_params.get("current_waypoint", 0)
                target = waypoints[current_idx % len(waypoints)]
                npc.behavior_params["current_waypoint"] = (current_idx + 1) % len(waypoints)
                return {"type": "move_to", "target": target}
            return {"type": "idle", "duration": 2.0}

        elif behavior == "follow":
            target_id = npc.behavior_params.get("target_id")
            if target_id:
                return {"type": "follow", "target_id": target_id}
            return {"type": "idle", "duration": 1.0}

        elif behavior == "merchant":
            # Merchants stay in place
            return {"type": "idle", "duration": 10.0}

        else:
            return {"type": "idle", "duration": 3.0}


# =============================================================================
# Game World
# =============================================================================


@dataclass
class GameConfig:
    """Configuration for the game world."""

    seed: int = 42
    world_size: int = 10  # chunks (for static world mode)
    chunk_size: int = 64  # vertices per side
    physics_dt: float = 1.0 / 60.0
    gravity: float = -9.8
    auto_save_interval: float = 300.0  # seconds

    # Dynamic chunk loading settings
    render_distance: int = 6  # chunks radius for rendering (reduced from 8 for perf)
    sim_distance: int = 3  # chunks radius for physics/AI simulation (reduced from 4)
    unload_buffer: int = 2  # extra distance before unloading
    enable_dynamic_chunks: bool = True  # Dynamic infinite world (default)


class GameWorld:
    """Central game state manager.

    Owns all game state including entities, quests, and world data.
    Provides the context for command execution and manages entity lifecycle.

    Supports both static (single chunk) and dynamic (infinite world) modes
    based on the ``enable_dynamic_chunks`` config flag.
    """

    def __init__(self, config: Optional[GameConfig] = None) -> None:
        self.config = config or GameConfig()
        self.events = EventBus()

        # Entity storage
        self._entities: Dict[EntityId, Entity] = {}
        self._player: Optional[Player] = None

        # Spatial entity partitioning by chunk (for dynamic mode)
        # Maps chunk coordinates (x, z) to set of entity IDs in that chunk
        self._entity_chunks: Dict[Tuple[int, int], Set[EntityId]] = {}
        # Reverse mapping: entity ID -> chunk coordinate (for O(1) lookup)
        self._entity_to_chunk: Dict[EntityId, Tuple[int, int]] = {}

        # Quest system
        self._quests: Dict[str, Quest] = {}
        self._item_definitions: Dict[str, ItemDefinition] = {}
        self._crafting_recipes: Dict[str, CraftingRecipe] = {}
        # Index: maps frozenset of ingredient IDs to list of recipes
        self._recipe_by_ingredients: Dict[frozenset, List[CraftingRecipe]] = {}

        # Physics
        self._heightfield: Optional[HeightField2D] = None

        # Chunk management (optional, for dynamic mode)
        self._chunk_manager: Optional[Any] = None  # ChunkManager when enabled

        # Agent for NPCs
        self._default_agent: NPCAgent = LocalAgent()

        # World state
        self._frame: int = 0
        self._time: float = 0.0
        self._time_of_day: float = 12.0  # 0-24 hours
        self._paused: bool = False

        # Flags for game state
        self._flags: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Entity Management
    # -------------------------------------------------------------------------

    def spawn_entity(self, entity: Entity) -> EntityId:
        """Add an entity to the world."""
        self._entities[entity.entity_id] = entity

        # Emit appropriate event
        if isinstance(entity, Creature):
            self._configure_creature_behavior(entity)
            self.events.emit(Event(
                EventType.CREATURE_SPAWNED,
                {"creature_id": entity.entity_id, "type": entity.creature_type},
                source_entity=entity.entity_id,
            ))
        elif isinstance(entity, NPC):
            entity._agent = self._default_agent
            # Configure behavior tree based on NPC behavior type
            if isinstance(self._default_agent, LocalAgent):
                self._default_agent.configure_npc_behavior(entity)
            self.events.emit(Event(
                EventType.NPC_SPAWNED,
                {"npc_id": entity.entity_id, "name": entity.name},
                source_entity=entity.entity_id,
            ))
        else:
            self.events.emit(Event(
                EventType.ENTITY_SPAWNED,
                {"entity_id": entity.entity_id, "type": type(entity).__name__},
                source_entity=entity.entity_id,
            ))

        # Update spatial partition for chunk-based queries
        self._update_entity_chunk(entity.entity_id, entity.position)

        return entity.entity_id

    def destroy_entity(self, entity_id: EntityId) -> bool:
        """Remove an entity from the world."""
        if entity_id in self._entities:
            entity = self._entities.pop(entity_id)

            # Remove from spatial partition and reverse mapping
            chunk_coord = self._entity_to_chunk.pop(entity_id, None)
            if chunk_coord is None:
                chunk_coord = self._position_to_chunk(entity.position)
            self._sync_loaded_chunk_membership(entity_id, chunk_coord, None)
            if chunk_coord in self._entity_chunks:
                self._entity_chunks[chunk_coord].discard(entity_id)
                if not self._entity_chunks[chunk_coord]:
                    del self._entity_chunks[chunk_coord]

            self.events.emit(Event(
                EventType.ENTITY_DESTROYED,
                {"entity_id": entity_id, "type": type(entity).__name__},
                source_entity=entity_id,
            ))
            return True
        return False

    def get_entity(self, entity_id: EntityId) -> Optional[Entity]:
        """Get an entity by ID."""
        return self._entities.get(entity_id)

    def get_entities_by_type(self, entity_type: type) -> List[Entity]:
        """Get all entities of a specific type."""
        return [e for e in self._entities.values() if isinstance(e, entity_type)]

    def get_entities_in_range(self, position: Vec3, radius: float) -> List[Entity]:
        """Get all entities within radius of position."""
        result = []
        for entity in self._entities.values():
            distance = (entity.position - position).length()
            if distance <= radius:
                result.append(entity)
        return result

    def get_npcs(self) -> List[NPC]:
        """Get all NPCs in the world."""
        return [e for e in self._entities.values() if isinstance(e, NPC)]

    # -------------------------------------------------------------------------
    # Chunk Management (for dynamic infinite world mode)
    # -------------------------------------------------------------------------

    def set_chunk_manager(self, manager: Any) -> None:
        """Set the chunk manager for dynamic world mode.

        Parameters
        ----------
        manager:
            A ChunkManager instance (from procengine.world.chunk).
        """
        self._chunk_manager = manager
        self._sync_loaded_chunk_entities()

    def get_chunk_manager(self) -> Optional[Any]:
        """Get the chunk manager if set.

        Returns
        -------
        Optional[ChunkManager]
            The chunk manager, or None if not using dynamic chunks.
        """
        return self._chunk_manager

    def _position_to_chunk(self, position: Vec3) -> Tuple[int, int]:
        """Convert a world position to chunk coordinates.

        Parameters
        ----------
        position:
            World-space position.

        Returns
        -------
        Tuple[int, int]
            Chunk coordinates (x, z).
        """
        import math
        chunk_size = self.config.chunk_size
        cx = int(math.floor(position.x / chunk_size))
        cz = int(math.floor(position.z / chunk_size))
        return (cx, cz)

    def _update_entity_chunk(self, entity_id: EntityId, position: Vec3) -> None:
        """Update the spatial partition for an entity's position.

        Uses reverse mapping for O(1) lookup of entity's current chunk.

        Parameters
        ----------
        entity_id:
            The entity to update.
        position:
            The entity's current world position.
        """
        new_chunk = self._position_to_chunk(position)

        # O(1) lookup of old chunk via reverse mapping
        old_chunk = self._entity_to_chunk.get(entity_id)

        if old_chunk is not None and old_chunk != new_chunk:
            # Remove from old chunk
            if old_chunk in self._entity_chunks:
                self._entity_chunks[old_chunk].discard(entity_id)
                if not self._entity_chunks[old_chunk]:
                    del self._entity_chunks[old_chunk]

        # Add to new chunk
        if new_chunk not in self._entity_chunks:
            self._entity_chunks[new_chunk] = set()
        self._entity_chunks[new_chunk].add(entity_id)

        # Update reverse mapping
        self._entity_to_chunk[entity_id] = new_chunk
        self._sync_loaded_chunk_membership(
            entity_id,
            old_chunk if old_chunk != new_chunk else None,
            new_chunk,
        )

    def _sync_loaded_chunk_membership(
        self,
        entity_id: EntityId,
        old_chunk: Optional[Tuple[int, int]],
        new_chunk: Optional[Tuple[int, int]],
    ) -> None:
        """Mirror world chunk membership into loaded Chunk objects."""
        if self._chunk_manager is None or entity_id == "player":
            return

        if old_chunk is not None:
            old_loaded_chunk = self._chunk_manager.chunks.get(old_chunk)
            if old_loaded_chunk is not None:
                old_loaded_chunk.entity_ids.discard(entity_id)

        if new_chunk is not None:
            new_loaded_chunk = self._chunk_manager.chunks.get(new_chunk)
            if new_loaded_chunk is not None:
                new_loaded_chunk.entity_ids.add(entity_id)

    def _sync_loaded_chunk_entities(self) -> None:
        """Populate loaded chunks from the current world spatial index."""
        if self._chunk_manager is None:
            return

        for chunk in self._chunk_manager.chunks.values():
            chunk.entity_ids.clear()

        for entity in self._entities.values():
            if entity.entity_id == "player":
                continue
            chunk_coord = self._entity_to_chunk.get(entity.entity_id)
            if chunk_coord is None:
                continue
            chunk = self._chunk_manager.chunks.get(chunk_coord)
            if chunk is not None:
                chunk.entity_ids.add(entity.entity_id)

    def _rebuild_spatial_indices(self) -> None:
        """Rebuild chunk-based entity lookup tables from loaded entities."""
        self._entity_chunks.clear()
        self._entity_to_chunk.clear()

        for entity in self._entities.values():
            self._update_entity_chunk(entity.entity_id, entity.position)

    def get_entities_in_chunk(self, chunk_coord: Tuple[int, int]) -> List[Entity]:
        """Get all entities in a specific chunk.

        Parameters
        ----------
        chunk_coord:
            Chunk coordinates (x, z).

        Returns
        -------
        List[Entity]
            Entities located within that chunk.
        """
        entity_ids = self._entity_chunks.get(chunk_coord, set())
        return [self._entities[eid] for eid in entity_ids if eid in self._entities]

    def get_entities_in_sim_range(self) -> List[Entity]:
        """Get entities within simulation range of the player.

        Returns all entities in chunks that are within the simulation
        distance. In static mode, returns all entities.

        Returns
        -------
        List[Entity]
            Entities that should be simulated.
        """
        if self._chunk_manager is None:
            # Static mode - return all entities
            return list(self._entities.values())

        # Dynamic mode - only return entities in sim-range chunks
        result: List[Entity] = []
        for chunk in self._chunk_manager.get_sim_chunks():
            result.extend(self.get_entities_in_chunk(chunk.coords))
        return result

    # -------------------------------------------------------------------------
    # Player Management
    # -------------------------------------------------------------------------

    def create_player(
        self,
        name: str = "Player",
        position: Optional[Vec3] = None,
    ) -> Player:
        """Create and register the player entity."""
        self._player = Player(
            entity_id="player",
            name=name,
            position=position or Vec3(0, 10, 0),
        )
        self._entities["player"] = self._player
        return self._player

    def get_player(self) -> Optional[Player]:
        """Get the player entity."""
        return self._player

    # -------------------------------------------------------------------------
    # Quest Management
    # -------------------------------------------------------------------------

    def register_quest(self, quest: Quest) -> None:
        """Register a quest definition."""
        self._quests[quest.quest_id] = quest

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """Get a quest by ID."""
        return self._quests.get(quest_id)

    def start_quest(self, quest_id: str) -> bool:
        """Start a quest for the player."""
        quest = self._quests.get(quest_id)
        if not quest or not self._player:
            return False

        if quest.state != QuestState.AVAILABLE:
            return False

        quest.state = QuestState.ACTIVE
        self._player.active_quests.append(quest_id)

        self.events.emit(Event(
            EventType.QUEST_STARTED,
            {"quest_id": quest_id, "title": quest.title},
            source_entity="player",
        ))
        return True

    def complete_quest(self, quest_id: str) -> bool:
        """Complete a quest and grant rewards."""
        quest = self._quests.get(quest_id)
        if not quest or not self._player:
            return False

        if quest.state != QuestState.ACTIVE or not quest.is_complete():
            return False

        quest.state = QuestState.COMPLETED
        if quest_id in self._player.active_quests:
            self._player.active_quests.remove(quest_id)
        self._player.completed_quests.append(quest_id)

        # Grant rewards
        rewards = quest.rewards
        if "gold" in rewards:
            self._player.inventory.add_item("gold", rewards["gold"])
        if "items" in rewards:
            for item_id, count in rewards["items"].items():
                self._player.inventory.add_item(item_id, count)
        if "experience" in rewards:
            # Experience would be handled by a leveling system
            pass

        # Execute completion actions
        for action in quest.on_complete_actions:
            self._execute_action(action)

        self.events.emit(Event(
            EventType.QUEST_COMPLETED,
            {"quest_id": quest_id, "title": quest.title, "rewards": rewards},
            source_entity="player",
        ))
        return True

    def update_quest_objective(
        self,
        quest_id: str,
        objective_id: str,
        amount: int = 1,
    ) -> bool:
        """Update progress on a quest objective."""
        quest = self._quests.get(quest_id)
        if not quest or quest.state != QuestState.ACTIVE:
            return False

        for obj in quest.objectives:
            if obj.objective_id == objective_id:
                just_completed = obj.update_progress(amount)

                self.events.emit(Event(
                    EventType.QUEST_OBJECTIVE_UPDATED,
                    {
                        "quest_id": quest_id,
                        "objective_id": objective_id,
                        "current": obj.current_count,
                        "required": obj.required_count,
                        "just_completed": just_completed,
                    },
                    source_entity="player",
                ))
                return True
        return False

    # -------------------------------------------------------------------------
    # Item Management
    # -------------------------------------------------------------------------

    def register_item_definition(self, item_def: ItemDefinition) -> None:
        """Register an item definition."""
        self._item_definitions[item_def.item_id] = item_def

    def get_item_definition(self, item_id: str) -> Optional[ItemDefinition]:
        """Get an item definition by ID."""
        return self._item_definitions.get(item_id)

    # -------------------------------------------------------------------------
    # Crafting
    # -------------------------------------------------------------------------

    def register_recipe(self, recipe: CraftingRecipe) -> None:
        """Register a crafting recipe."""
        self._crafting_recipes[recipe.recipe_id] = recipe
        key = recipe.get_ingredient_ids()
        if key not in self._recipe_by_ingredients:
            self._recipe_by_ingredients[key] = []
        self._recipe_by_ingredients[key].append(recipe)

    def get_recipe(self, recipe_id: str) -> Optional[CraftingRecipe]:
        """Get a recipe by ID."""
        return self._crafting_recipes.get(recipe_id)

    def get_all_recipes(self) -> Dict[str, CraftingRecipe]:
        """Get all registered recipes."""
        return self._crafting_recipes.copy()

    def get_recipes_for_items(self, selected_item_ids: List[str]) -> List[CraftingRecipe]:
        """Get recipes that can be made using (a subset of) the selected items.

        Returns recipes whose ingredient set is a subset of the selected
        items.  The recipes are returned regardless of whether the player
        has enough quantity -- the UI is responsible for showing
        availability.
        """
        selected = frozenset(selected_item_ids)
        matches: List[CraftingRecipe] = []
        for ingredient_key, recipes in self._recipe_by_ingredients.items():
            if ingredient_key <= selected:
                matches.extend(recipes)
        return matches

    def craft_item(self, recipe_id: str, player: Optional["Player"] = None) -> bool:
        """Attempt to craft an item from a recipe.

        Consumes ingredients from the player's inventory and adds the
        result.  Emits ``ITEM_CRAFTED`` on success.

        Returns ``True`` if crafting succeeded.
        """
        recipe = self._crafting_recipes.get(recipe_id)
        if recipe is None:
            return False

        target = player or self._player
        if target is None:
            return False

        if not recipe.can_craft(target.inventory):
            return False

        # Consume ingredients
        for item_id, count in recipe.ingredients.items():
            target.inventory.remove_item(item_id, count)

        # Add crafted item
        target.inventory.add_item(recipe.result_item, recipe.result_count)

        # Emit event
        self.events.emit(Event(
            EventType.ITEM_CRAFTED,
            {
                "recipe_id": recipe.recipe_id,
                "item_id": recipe.result_item,
                "count": recipe.result_count,
            },
            source_entity=target.entity_id,
        ))
        return True

    # -------------------------------------------------------------------------
    # Dialogue
    # -------------------------------------------------------------------------

    def initiate_dialogue(self, npc_id: EntityId) -> bool:
        """Start dialogue with an NPC."""
        npc = self.get_entity(npc_id)
        if not isinstance(npc, NPC) or not self._player:
            return False

        if not npc.can_talk(self._player.position):
            return False

        self._player.current_interaction_target = npc_id

        self.events.emit(Event(
            EventType.NPC_DIALOGUE_STARTED,
            {"npc_id": npc_id, "npc_name": npc.name},
            source_entity="player",
            target_entity=npc_id,
        ))
        return True

    def process_player_dialogue(
        self,
        npc_id: EntityId,
        message: str,
    ) -> Optional[DialogueResponse]:
        """Process player dialogue and get NPC response."""
        npc = self.get_entity(npc_id)
        if not isinstance(npc, NPC) or not self._player:
            return None

        # Build dialogue context
        context = DialogueContext(
            npc_id=npc_id,
            npc_name=npc.name,
            npc_personality=npc.personality,
            npc_behavior=npc.behavior,
            npc_current_quest=npc.current_quest,
            relationship_to_player=npc.get_disposition("player"),
            player_name=self._player.name,
            player_active_quests=self._player.active_quests.copy(),
            player_inventory_summary=self._get_inventory_summary(self._player.inventory),
            conversation_history=self._player.get_dialogue_history(npc_id),
            world_context={
                "time_of_day": self._get_time_period(),
                "location": "world",  # Would be more specific with regions
            },
            player_message=message,
        )

        # Get response from agent
        agent = npc._agent or self._default_agent
        response = agent.get_dialogue_response(context)

        # Record dialogue history
        self._player.add_dialogue(npc_id, "player", message)
        self._player.add_dialogue(npc_id, "npc", response.text)

        # Process response actions
        for action in response.actions:
            self._execute_action(action, npc_id)

        if response.ends_conversation:
            self.end_dialogue(npc_id)

        return response

    def end_dialogue(self, npc_id: EntityId) -> None:
        """End dialogue with an NPC."""
        if self._player and self._player.current_interaction_target == npc_id:
            self._player.current_interaction_target = None

        self.events.emit(Event(
            EventType.NPC_DIALOGUE_ENDED,
            {"npc_id": npc_id},
            source_entity="player",
            target_entity=npc_id,
        ))

    def _get_inventory_summary(self, inventory: Inventory) -> List[str]:
        """Get a summary of inventory for dialogue context."""
        summary = []
        for item_id, count in inventory.items.items():
            item_def = self._item_definitions.get(item_id)
            name = item_def.name if item_def else item_id
            summary.append(f"{name}: {count}")
        return summary

    def _get_time_period(self) -> str:
        """Get time of day as a string."""
        hour = self._time_of_day
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    # -------------------------------------------------------------------------
    # Action Execution
    # -------------------------------------------------------------------------

    def _execute_action(
        self,
        action: Dict[str, Any],
        source_npc_id: Optional[EntityId] = None,
    ) -> None:
        """Execute a dialogue or quest action."""
        action_type = action.get("type")

        if action_type == "give_quest":
            quest_id = action["quest_id"]
            quest = self._quests.get(quest_id)
            if quest:
                quest.state = QuestState.AVAILABLE
                self.start_quest(quest_id)

        elif action_type == "complete_quest":
            self.complete_quest(action["quest_id"])

        elif action_type == "change_disposition":
            if source_npc_id:
                npc = self.get_entity(source_npc_id)
                if isinstance(npc, NPC):
                    npc.adjust_disposition("player", action["delta"])

        elif action_type == "give_item":
            if self._player:
                self._player.inventory.add_item(
                    action["item"],
                    action.get("count", 1),
                )
                self.events.emit(Event(
                    EventType.ITEM_ACQUIRED,
                    {"item_id": action["item"], "count": action.get("count", 1)},
                    source_entity="player",
                ))

        elif action_type == "take_item":
            if self._player:
                self._player.inventory.remove_item(
                    action["item"],
                    action.get("count", 1),
                )

        elif action_type == "set_flag":
            self._flags[action["flag"]] = action.get("value", True)

        elif action_type == "unlock_dialogue":
            # Unlock a dialogue topic for an NPC
            npc_id = action.get("npc_id", source_npc_id)
            topic = action.get("topic")
            if npc_id and topic:
                npc = self.get_entity(npc_id)
                if isinstance(npc, NPC):
                    if not hasattr(npc, "unlocked_topics"):
                        npc.unlocked_topics = set()
                    npc.unlocked_topics.add(topic)

        elif action_type == "unlock_quest":
            # Make a quest available (change from UNAVAILABLE to AVAILABLE)
            quest_id = action.get("quest_id")
            if quest_id and quest_id in self._quests:
                quest = self._quests[quest_id]
                if quest.state == QuestState.UNAVAILABLE:
                    quest.state = QuestState.AVAILABLE

    # -------------------------------------------------------------------------
    # Physics
    # -------------------------------------------------------------------------

    def set_heightfield(self, heightfield: HeightField2D) -> None:
        """Set the terrain heightfield for physics."""
        self._heightfield = heightfield

    def physics_step(self) -> None:
        """Run one physics step for character entities in simulation range.

        In dynamic-chunk mode only characters within sim-distance chunks
        are stepped.  The player is always included regardless of distance.
        In static mode all characters are stepped.
        """
        sim_entities = self.get_entities_in_sim_range()
        characters = [e for e in sim_entities if isinstance(e, Character)]

        # Always include the player even if outside sim-range chunks
        player = self.get_player()
        if player and player not in characters:
            characters.append(player)

        if not characters:
            return

        # Create physics bodies
        bodies = []
        char_list = []
        for entity in characters:
            if entity.active:
                bodies.append(entity.to_rigid_body())
                char_list.append(entity)

        if not bodies:
            return

        # Debug heightfield on first physics step
        if self._frame == 1 and self._heightfield is not None:
            print(f"Physics step: heightfield active, size {self._heightfield.size_x}x{self._heightfield.size_z}")
        elif self._frame == 1:
            print("WARNING: Physics step with NO heightfield - characters will fall forever!")

        # Run physics
        step_physics_3d(
            bodies,
            dt=self.config.physics_dt,
            gravity=self.config.gravity,
            heightfield=self._heightfield,
        )

        # Apply results back
        for char, body in zip(char_list, bodies):
            old_pos = Vec3(char.position.x, char.position.y, char.position.z)
            char.apply_rigid_body(body)

            # Emit movement event if position changed significantly
            if (char.position - old_pos).length() > 0.01:
                event_type = (
                    EventType.PLAYER_MOVED
                    if isinstance(char, Player)
                    else EventType.ENTITY_MOVED
                )
                self.events.emit(Event(
                    event_type,
                    {"old_position": old_pos, "new_position": char.position},
                    source_entity=char.entity_id,
                ))

    # -------------------------------------------------------------------------
    # Game Loop
    # -------------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """Advance the game world by dt seconds."""
        if self._paused:
            return

        self._frame += 1
        self._time += dt

        # Update time of day (1 game hour = 1 real minute)
        self._time_of_day = (self._time_of_day + dt / 60.0) % 24.0

        # Physics
        self.physics_step()

        # Update NPC and creature behaviors
        self._update_npcs(dt)

    def _update_npcs(self, dt: float) -> None:
        """Update NPC and creature behaviors using behavior trees or fallback actions.

        Only entities within simulation distance are updated when dynamic
        chunks are active.  In static mode all entities are updated.
        """
        sim_entities = self.get_entities_in_sim_range()

        # Tick NPCs
        npcs = [e for e in sim_entities if isinstance(e, NPC)]
        for npc in npcs:
            if not npc.active:
                continue

            # First, try to tick the behavior tree if one is assigned
            if npc.get_behavior_tree() is not None:
                npc.tick_behavior(self, dt)
            else:
                # Fallback to agent's get_next_action for legacy behavior
                agent = npc._agent or self._default_agent
                action = agent.get_next_action(npc, self)

                if action:
                    self._execute_npc_action(npc, action, dt)

        # Tick creatures
        creatures = [e for e in sim_entities if isinstance(e, Creature)]
        for creature in creatures:
            if creature.active and creature.get_behavior_tree() is not None:
                creature.tick_behavior(self, dt)

    def _execute_npc_action(
        self,
        npc: NPC,
        action: Dict[str, Any],
        dt: float,
    ) -> None:
        """Execute an NPC action."""
        action_type = action.get("type")

        if action_type == "move_to":
            target = action["target"]
            if isinstance(target, dict):
                target = Vec3(target["x"], target["y"], target["z"])

            direction = target - npc.position
            direction = Vec3(direction.x, 0, direction.z)  # Ignore Y
            distance = direction.length()

            if distance > 0.1:
                direction = direction.normalized()
                speed = 3.0  # NPC walking speed
                move = direction * min(speed * dt, distance)
                npc.position = npc.position + move

        elif action_type == "follow":
            target_id = action["target_id"]
            target_entity = self.get_entity(target_id)
            if target_entity:
                direction = target_entity.position - npc.position
                direction = Vec3(direction.x, 0, direction.z)
                distance = direction.length()

                if distance > 2.0:  # Keep some distance
                    direction = direction.normalized()
                    speed = 4.0
                    move = direction * min(speed * dt, distance - 2.0)
                    npc.position = npc.position + move

        # "idle" action doesn't need handling

    def _configure_creature_behavior(self, creature: Creature) -> None:
        """Assign a behavior tree to a newly spawned creature.

        Parameters
        ----------
        creature:
            The creature to configure.
        """
        import math as _math
        from procengine.game.behavior_tree import (
            create_creature_wander_behavior,
            create_flee_behavior,
            create_creature_prey_behavior,
            create_creature_predator_behavior,
            create_creature_grazer_behavior,
        )

        behavior = creature.behavior
        vision_half = _math.radians(creature.vision_half_angle_deg)
        vision_range = creature.vision_range

        if behavior == "prey":
            creature.set_behavior_tree(
                create_creature_prey_behavior(
                    origin=creature.position,
                    wander_radius=10.0,
                    speed=creature.move_speed,
                    flee_range=creature.flee_range,
                    flee_speed_multiplier=1.5,
                    vision_half_angle=vision_half,
                    vision_range=vision_range,
                )
            )
        elif behavior == "predator":
            creature.set_behavior_tree(
                create_creature_predator_behavior(
                    origin=creature.position,
                    patrol_radius=15.0,
                    speed=creature.move_speed,
                    vision_half_angle=vision_half,
                    vision_range=vision_range,
                )
            )
        elif behavior == "grazer":
            creature.set_behavior_tree(
                create_creature_grazer_behavior(
                    origin=creature.position,
                    graze_radius=8.0,
                    speed=creature.move_speed,
                )
            )
        elif behavior == "flee":
            creature.set_behavior_tree(
                create_flee_behavior(
                    flee_range=creature.flee_range,
                    speed=creature.move_speed * 1.5,
                )
            )
        else:
            # Default: wander
            creature.set_behavior_tree(
                create_creature_wander_behavior(
                    origin=creature.position,
                    wander_radius=10.0,
                    speed=creature.move_speed,
                )
            )

    # -------------------------------------------------------------------------
    # Save/Load
    # -------------------------------------------------------------------------

    def save_to_dict(self) -> Dict[str, Any]:
        """Serialize game world to dictionary."""
        return {
            "version": "1.0",
            "seed": self.config.seed,
            "frame": self._frame,
            "time": self._time,
            "time_of_day": self._time_of_day,
            "player": self._player.to_dict() if self._player else None,
            "entities": {
                eid: e.to_dict()
                for eid, e in self._entities.items()
                if eid != "player"
            },
            "quests": {qid: q.to_dict() for qid, q in self._quests.items()},
            "flags": self._flags.copy(),
        }

    def save_to_file(self, path: Path) -> None:
        """Save game world to a JSON file."""
        data = self.save_to_dict()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Load game world from dictionary."""
        self.config.seed = data.get("seed", 42)
        self._frame = data.get("frame", 0)
        self._time = data.get("time", 0.0)
        self._time_of_day = data.get("time_of_day", 12.0)
        self._flags = data.get("flags", {})
        # Reset collections up front so repeated loads replace state instead
        # of leaking stale entities, quests, or chunk index entries.
        self._entities = {}
        self._player = None
        self._quests = {}
        self._entity_chunks = {}
        self._entity_to_chunk = {}

        # Load player
        if data.get("player"):
            self._player = Player.from_dict(data["player"])
            self._entities["player"] = self._player

        # Load other entities
        for eid, edata in data.get("entities", {}).items():
            entity_type = edata.get("type", "Entity")
            if entity_type == "NPC":
                entity = NPC.from_dict(edata)
                entity._agent = self._default_agent
            elif entity_type == "Creature":
                entity = Creature.from_dict(edata)
            elif entity_type == "Prop":
                entity = Prop.from_dict(edata)
            elif entity_type == "Item":
                entity = Item.from_dict(edata)
            elif entity_type == "Character":
                entity = Character.from_dict(edata)
            else:
                entity = Entity.from_dict(edata)
            self._entities[eid] = entity

        # Load quests
        for qid, qdata in data.get("quests", {}).items():
            self._quests[qid] = Quest.from_dict(qdata)

        self._rebuild_spatial_indices()

    def load_from_file(self, path: Path) -> None:
        """Load game world from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        self.load_from_dict(data)

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def frame(self) -> int:
        """Current frame number."""
        return self._frame

    @property
    def time(self) -> float:
        """Total elapsed time in seconds."""
        return self._time

    @property
    def paused(self) -> bool:
        """Whether the game is paused."""
        return self._paused

    @paused.setter
    def paused(self, value: bool) -> None:
        """Set pause state."""
        self._paused = value

    def get_flag(self, flag: str, default: Any = None) -> Any:
        """Get a game flag value."""
        return self._flags.get(flag, default)

    def set_flag(self, flag: str, value: Any) -> None:
        """Set a game flag value."""
        self._flags[flag] = value
