"""Game-specific commands for the Procedural Engine.

This module registers all game-related commands with the command registry:
- Player commands (position, health, inventory)
- NPC commands (spawn, behavior, dialogue)
- Quest commands (start, complete, list)
- World commands (info, time)
- Physics commands (gravity)
- Engine commands (step, reset)
- Debug commands (stats, wireframe)
- UI commands (inventory, map, journal)

These commands are loaded automatically when the game starts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from procengine.commands.commands import (
    command,
    registry,
    CommandResult,
    AccessLevel,
    Category,
)
from procengine.physics import Vec3

if TYPE_CHECKING:
    from procengine.game.game_api import GameWorld, Player, NPC
    from procengine.game.game_runner import GameRunner

__all__ = [
    "register_game_commands",
]


# =============================================================================
# Player Commands
# =============================================================================


@command(
    name="player.pos",
    description="Get or set player position",
    category=Category.PLAYER,
    access=AccessLevel.PUBLIC,
    examples=["player.pos", "player.pos 100 50 100"],
)
def cmd_player_pos(x: float = None, y: float = None, z: float = None) -> CommandResult:
    """Get or set player position."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    if x is None:
        # Get position
        return CommandResult.ok(
            f"Player position: ({player.position.x:.2f}, {player.position.y:.2f}, {player.position.z:.2f})",
            data={"x": player.position.x, "y": player.position.y, "z": player.position.z},
        )
    
    # Set position (requires cheat mode)
    if not registry.cheats_enabled:
        return CommandResult.error("Requires cheats enabled (system.cheats 1)")
    
    if y is None or z is None:
        return CommandResult.error("Must specify all three coordinates (x y z)")
    
    player.position = Vec3(x, y, z)
    return CommandResult.ok(f"Teleported to ({x:.2f}, {y:.2f}, {z:.2f})")


@command(
    name="player.teleport",
    description="Teleport player to coordinates",
    category=Category.PLAYER,
    access=AccessLevel.CHEAT,
    aliases=["tp"],
    examples=["player.teleport 100 50 100"],
)
def cmd_player_teleport(x: float, y: float, z: float) -> CommandResult:
    """Teleport player to coordinates."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    player.position = Vec3(x, y, z)
    player.velocity = Vec3(0, 0, 0)  # Reset velocity
    return CommandResult.ok(f"Teleported to ({x:.2f}, {y:.2f}, {z:.2f})")


@command(
    name="player.health",
    description="Get or set player health",
    category=Category.PLAYER,
    access=AccessLevel.PUBLIC,
    examples=["player.health", "player.health 100"],
)
def cmd_player_health(amount: float = None) -> CommandResult:
    """Get or set player health."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    if amount is None:
        return CommandResult.ok(
            f"Health: {player.health:.1f}/{player.max_health:.1f}",
            data={"health": player.health, "max_health": player.max_health},
        )
    
    if not registry.cheats_enabled:
        return CommandResult.error("Requires cheats enabled (system.cheats 1)")
    
    player.health = min(amount, player.max_health)
    return CommandResult.ok(f"Health set to {player.health:.1f}")


@command(
    name="player.god",
    description="Toggle god mode (invincibility)",
    category=Category.PLAYER,
    access=AccessLevel.CHEAT,
)
def cmd_player_god(enabled: int = None) -> CommandResult:
    """Toggle god mode."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    # Store god mode in player flags
    if not hasattr(ctx, "flags"):
        ctx.flags = {}
    
    if enabled is None:
        # Toggle
        ctx.flags["god_mode"] = not ctx.flags.get("god_mode", False)
    else:
        ctx.flags["god_mode"] = bool(enabled)
    
    god_on = ctx.flags["god_mode"]
    return CommandResult.ok(f"God mode {'enabled' if god_on else 'disabled'}")


@command(
    name="player.give",
    description="Give item to player",
    category=Category.PLAYER,
    access=AccessLevel.CHEAT,
    examples=["player.give gold 100", "player.give health_potion 5"],
)
def cmd_player_give(item_id: str, count: int = 1) -> CommandResult:
    """Give item to player."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    added = player.inventory.add_item(item_id, count)
    if added < count:
        return CommandResult.ok(f"Added {added}/{count} {item_id} (inventory full)")
    return CommandResult.ok(f"Added {count} {item_id}")


@command(
    name="player.take",
    description="Remove item from player",
    category=Category.PLAYER,
    access=AccessLevel.CHEAT,
    examples=["player.take gold 50"],
)
def cmd_player_take(item_id: str, count: int = 1) -> CommandResult:
    """Remove item from player."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    removed = player.inventory.remove_item(item_id, count)
    if removed < count:
        return CommandResult.ok(f"Removed {removed}/{count} {item_id}")
    return CommandResult.ok(f"Removed {count} {item_id}")


@command(
    name="player.inventory",
    description="List player inventory",
    category=Category.PLAYER,
    access=AccessLevel.PUBLIC,
    aliases=["inv"],
)
def cmd_player_inventory() -> CommandResult:
    """List player inventory."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    items = player.inventory.get_all_items()
    if not items:
        return CommandResult.ok("Inventory is empty")
    
    lines = ["Inventory:"]
    for item_id, count in sorted(items.items()):
        # Try to get item name from definition
        item_def = ctx.world.get_item_definition(item_id)
        name = item_def.name if item_def else item_id
        lines.append(f"  {name}: {count}")
    
    return CommandResult.ok("\n".join(lines), data={"items": items})


@command(
    name="player.speed",
    description="Set player movement speed",
    category=Category.PLAYER,
    access=AccessLevel.CHEAT,
    examples=["player.speed 10"],
)
def cmd_player_speed(speed: float) -> CommandResult:
    """Set player movement speed."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    player.move_speed = speed
    return CommandResult.ok(f"Movement speed set to {speed}")


@command(
    name="player.use",
    description="Use an item from inventory",
    category=Category.PLAYER,
    access=AccessLevel.PUBLIC,
    examples=["player.use health_potion"],
)
def cmd_player_use(item_id: str) -> CommandResult:
    """Use an item from the player's inventory."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")

    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")

    if not player.inventory.has_item(item_id):
        return CommandResult.error(f"No {item_id} in inventory")

    # Look up item definition for effects
    item_def = ctx.world.get_item_definition(item_id)
    item_name = item_def.name if item_def else item_id

    # Apply item effects based on type
    if item_def and hasattr(item_def, "properties"):
        props = item_def.properties if isinstance(item_def.properties, dict) else {}
        heal_amount = props.get("heal", 0)
        if heal_amount:
            player.heal(heal_amount)
            player.inventory.remove_item(item_id, 1)
            return CommandResult.ok(
                f"Used {item_name}: healed {heal_amount} HP",
                data={"item_id": item_id, "effect": "heal", "amount": heal_amount},
            )

    # Generic use: consume one unit
    player.inventory.remove_item(item_id, 1)
    return CommandResult.ok(
        f"Used {item_name}",
        data={"item_id": item_id},
    )


@command(
    name="player.drop",
    description="Drop an item from inventory",
    category=Category.PLAYER,
    access=AccessLevel.PUBLIC,
    examples=["player.drop gold 10", "player.drop health_potion"],
)
def cmd_player_drop(item_id: str, count: int = 1) -> CommandResult:
    """Drop an item from the player's inventory."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")

    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")

    if not player.inventory.has_item(item_id):
        return CommandResult.error(f"No {item_id} in inventory")

    removed = player.inventory.remove_item(item_id, count)
    item_def = ctx.world.get_item_definition(item_id)
    item_name = item_def.name if item_def else item_id

    return CommandResult.ok(
        f"Dropped {removed} {item_name}",
        data={"item_id": item_id, "count": removed},
    )


# =============================================================================
# NPC Commands
# =============================================================================


@command(
    name="npc.list",
    description="List all NPCs",
    category=Category.NPC,
    access=AccessLevel.PUBLIC,
)
def cmd_npc_list() -> CommandResult:
    """List all NPCs."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    npcs = ctx.world.get_npcs()
    if not npcs:
        return CommandResult.ok("No NPCs in world")
    
    lines = ["NPCs:"]
    for npc in npcs:
        pos = npc.position
        lines.append(f"  {npc.entity_id}: {npc.name} at ({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f}) [{npc.behavior}]")
    
    return CommandResult.ok("\n".join(lines), data={"npcs": [n.entity_id for n in npcs]})


@command(
    name="npc.spawn",
    description="Spawn an NPC",
    category=Category.NPC,
    access=AccessLevel.CONSOLE,
    aliases=["npc.create"],
    examples=["npc.spawn guard_01 Guard 50 10 50"],
)
def cmd_npc_spawn(npc_id: str, name: str, x: float, y: float, z: float) -> CommandResult:
    """Spawn an NPC."""
    from procengine.game.game_api import NPC
    
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    # Check if ID already exists
    if ctx.world.get_entity(npc_id):
        return CommandResult.error(f"Entity with ID '{npc_id}' already exists")
    
    npc = NPC(
        entity_id=npc_id,
        name=name,
        position=Vec3(x, y, z),
    )
    ctx.world.spawn_entity(npc)
    return CommandResult.ok(f"Spawned NPC '{name}' at ({x:.1f}, {y:.1f}, {z:.1f})")


@command(
    name="npc.remove",
    description="Remove an NPC",
    category=Category.NPC,
    access=AccessLevel.CONSOLE,
    aliases=["npc.destroy"],
    examples=["npc.remove guard_01"],
)
def cmd_npc_remove(npc_id: str) -> CommandResult:
    """Remove an NPC."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    if ctx.world.destroy_entity(npc_id):
        return CommandResult.ok(f"Removed NPC '{npc_id}'")
    return CommandResult.error(f"NPC not found: {npc_id}")


@command(
    name="npc.behavior",
    description="Set NPC behavior",
    category=Category.NPC,
    access=AccessLevel.CONSOLE,
    examples=["npc.behavior guard_01 patrol", "npc.behavior merchant_01 merchant"],
)
def cmd_npc_behavior(npc_id: str, behavior: str) -> CommandResult:
    """Set NPC behavior."""
    from procengine.game.game_api import NPC
    
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    npc = ctx.world.get_entity(npc_id)
    if not isinstance(npc, NPC):
        return CommandResult.error(f"NPC not found: {npc_id}")
    
    npc.behavior = behavior
    
    # Reconfigure behavior tree
    if hasattr(ctx.world, "_default_agent") and hasattr(ctx.world._default_agent, "configure_npc_behavior"):
        ctx.world._default_agent.configure_npc_behavior(npc)
    
    return CommandResult.ok(f"Set {npc.name}'s behavior to '{behavior}'")


@command(
    name="npc.teleport",
    description="Teleport an NPC",
    category=Category.NPC,
    access=AccessLevel.CONSOLE,
    examples=["npc.teleport guard_01 100 10 100"],
)
def cmd_npc_teleport(npc_id: str, x: float, y: float, z: float) -> CommandResult:
    """Teleport an NPC."""
    from procengine.game.game_api import NPC
    
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    npc = ctx.world.get_entity(npc_id)
    if not isinstance(npc, NPC):
        return CommandResult.error(f"NPC not found: {npc_id}")
    
    npc.position = Vec3(x, y, z)
    return CommandResult.ok(f"Teleported {npc.name} to ({x:.1f}, {y:.1f}, {z:.1f})")


@command(
    name="npc.dialogue",
    description="Start dialogue with NPC",
    category=Category.NPC,
    access=AccessLevel.PUBLIC,
    aliases=["talk"],
    examples=["npc.dialogue blacksmith"],
)
def cmd_npc_dialogue(npc_id: str) -> CommandResult:
    """Start dialogue with NPC."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "start_dialogue"):
        if ctx.start_dialogue(npc_id):
            return CommandResult.ok(f"Started dialogue with {npc_id}")
        return CommandResult.error(f"Cannot start dialogue with {npc_id}")
    
    return CommandResult.error("Dialogue not supported")


# =============================================================================
# Quest Commands
# =============================================================================


@command(
    name="quest.list",
    description="List quests",
    category=Category.QUEST,
    access=AccessLevel.PUBLIC,
    examples=["quest.list", "quest.list active"],
)
def cmd_quest_list(filter_type: str = "all") -> CommandResult:
    """List quests (all, active, completed, available)."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    lines = []
    
    if filter_type in ("all", "active"):
        if player.active_quests:
            lines.append("Active quests:")
            for quest_id in player.active_quests:
                quest = ctx.world.get_quest(quest_id)
                if quest:
                    progress = quest.get_progress()
                    lines.append(f"  [{progress[0]}/{progress[1]}] {quest.title}")
    
    if filter_type in ("all", "completed"):
        if player.completed_quests:
            lines.append("Completed quests:")
            for quest_id in player.completed_quests:
                quest = ctx.world.get_quest(quest_id)
                if quest:
                    lines.append(f"  ✓ {quest.title}")
    
    if filter_type in ("all", "available"):
        from procengine.game.game_api import QuestState
        available = []
        for quest_id, quest in ctx.world._quests.items():
            if quest.state == QuestState.AVAILABLE and quest_id not in player.active_quests:
                available.append(quest)
        if available:
            lines.append("Available quests:")
            for quest in available:
                lines.append(f"  • {quest.title}")
    
    if not lines:
        return CommandResult.ok("No quests")
    
    return CommandResult.ok("\n".join(lines))


@command(
    name="quest.info",
    description="Show quest details",
    category=Category.QUEST,
    access=AccessLevel.PUBLIC,
    examples=["quest.info find_rare_ore"],
)
def cmd_quest_info(quest_id: str) -> CommandResult:
    """Show quest details."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    quest = ctx.world.get_quest(quest_id)
    if not quest:
        return CommandResult.error(f"Quest not found: {quest_id}")
    
    lines = [
        f"Quest: {quest.title}",
        f"Status: {quest.state.name}",
        f"Description: {quest.description}",
        "",
        "Objectives:",
    ]
    
    for obj in quest.objectives:
        status = "✓" if obj.is_complete() else "○"
        optional = " (optional)" if obj.optional else ""
        lines.append(f"  {status} {obj.description} [{obj.current_count}/{obj.required_count}]{optional}")
    
    if quest.rewards:
        lines.append("")
        lines.append("Rewards:")
        if "gold" in quest.rewards:
            lines.append(f"  Gold: {quest.rewards['gold']}")
        if "items" in quest.rewards:
            for item_id, count in quest.rewards["items"].items():
                lines.append(f"  {item_id}: {count}")
    
    return CommandResult.ok("\n".join(lines))


@command(
    name="quest.start",
    description="Start a quest",
    category=Category.QUEST,
    access=AccessLevel.CHEAT,
    examples=["quest.start find_rare_ore"],
)
def cmd_quest_start(quest_id: str) -> CommandResult:
    """Start a quest (cheat command)."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    from procengine.game.game_api import QuestState
    
    quest = ctx.world.get_quest(quest_id)
    if not quest:
        return CommandResult.error(f"Quest not found: {quest_id}")
    
    # Force quest to available state if needed
    if quest.state == QuestState.UNAVAILABLE:
        quest.state = QuestState.AVAILABLE
    
    if ctx.world.start_quest(quest_id):
        return CommandResult.ok(f"Started quest: {quest.title}")
    return CommandResult.error(f"Cannot start quest: {quest_id}")


@command(
    name="quest.complete",
    description="Complete a quest",
    category=Category.QUEST,
    access=AccessLevel.CHEAT,
    examples=["quest.complete find_rare_ore"],
)
def cmd_quest_complete(quest_id: str) -> CommandResult:
    """Complete a quest (cheat command)."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    quest = ctx.world.get_quest(quest_id)
    if not quest:
        return CommandResult.error(f"Quest not found: {quest_id}")
    
    # Mark all objectives complete
    for obj in quest.objectives:
        obj.current_count = obj.required_count
    
    if ctx.world.complete_quest(quest_id):
        return CommandResult.ok(f"Completed quest: {quest.title}")
    return CommandResult.error(f"Cannot complete quest: {quest_id}")


@command(
    name="quest.abandon",
    description="Abandon an active quest",
    category=Category.QUEST,
    access=AccessLevel.PUBLIC,
    examples=["quest.abandon find_rare_ore"],
)
def cmd_quest_abandon(quest_id: str) -> CommandResult:
    """Abandon an active quest."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    from procengine.game.game_api import QuestState
    
    player = ctx.world.get_player()
    if not player:
        return CommandResult.error("No player")
    
    if quest_id not in player.active_quests:
        return CommandResult.error(f"Quest not active: {quest_id}")
    
    quest = ctx.world.get_quest(quest_id)
    if quest:
        quest.state = QuestState.AVAILABLE
        # Reset objectives
        for obj in quest.objectives:
            obj.current_count = 0
    
    player.active_quests.remove(quest_id)
    return CommandResult.ok(f"Abandoned quest: {quest.title if quest else quest_id}")


# =============================================================================
# World Commands
# =============================================================================


@command(
    name="world.info",
    description="Show world information",
    category=Category.WORLD,
    access=AccessLevel.PUBLIC,
)
def cmd_world_info() -> CommandResult:
    """Show world information."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    world = ctx.world
    
    lines = [
        f"World Info:",
        f"  Seed: {world.config.seed}",
        f"  Frame: {world.frame}",
        f"  Time: {world.time:.1f}s",
        f"  Time of Day: {world._time_of_day:.1f}h ({world._get_time_period()})",
        f"  Entities: {len(world._entities)}",
        f"  NPCs: {len(world.get_npcs())}",
        f"  Quests: {len(world._quests)}",
    ]
    
    return CommandResult.ok("\n".join(lines))


@command(
    name="world.time",
    description="Get or set world time (0-24)",
    category=Category.WORLD,
    access=AccessLevel.PUBLIC,
    examples=["world.time", "world.time 12"],
)
def cmd_world_time(hour: float = None) -> CommandResult:
    """Get or set world time."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    if hour is None:
        return CommandResult.ok(
            f"Time: {ctx.world._time_of_day:.1f}h ({ctx.world._get_time_period()})",
            data={"hour": ctx.world._time_of_day},
        )
    
    if not registry.cheats_enabled:
        return CommandResult.error("Requires cheats enabled (system.cheats 1)")
    
    ctx.world._time_of_day = hour % 24.0
    return CommandResult.ok(f"Time set to {ctx.world._time_of_day:.1f}h")


@command(
    name="world.pause",
    description="Pause or unpause the game",
    category=Category.WORLD,
    access=AccessLevel.PUBLIC,
    aliases=["pause"],
)
def cmd_world_pause(paused: int = None) -> CommandResult:
    """Pause or unpause the game."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    if paused is None:
        ctx.world.paused = not ctx.world.paused
    else:
        ctx.world.paused = bool(paused)
    
    return CommandResult.ok(f"Game {'paused' if ctx.world.paused else 'unpaused'}")


# =============================================================================
# Physics Commands
# =============================================================================


@command(
    name="physics.gravity",
    description="Get or set gravity",
    category=Category.PHYSICS,
    access=AccessLevel.CONSOLE,
    examples=["physics.gravity", "physics.gravity -9.8"],
)
def cmd_physics_gravity(value: float = None) -> CommandResult:
    """Get or set gravity."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    if value is None:
        return CommandResult.ok(
            f"Gravity: {ctx.world.config.gravity}",
            data={"gravity": ctx.world.config.gravity},
        )
    
    ctx.world.config.gravity = value
    return CommandResult.ok(f"Gravity set to {value}")


@command(
    name="physics.noclip",
    description="Toggle noclip mode (fly through walls)",
    category=Category.PHYSICS,
    access=AccessLevel.CHEAT,
)
def cmd_physics_noclip(enabled: int = None) -> CommandResult:
    """Toggle noclip mode."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if not hasattr(ctx, "flags"):
        ctx.flags = {}
    
    if enabled is None:
        ctx.flags["noclip"] = not ctx.flags.get("noclip", False)
    else:
        ctx.flags["noclip"] = bool(enabled)
    
    return CommandResult.ok(f"Noclip {'enabled' if ctx.flags['noclip'] else 'disabled'}")


# =============================================================================
# Engine Commands
# =============================================================================


@command(
    name="engine.step",
    description="Advance game by N frames",
    category=Category.ENGINE,
    access=AccessLevel.DEV,
    examples=["engine.step 1", "engine.step 60"],
)
def cmd_engine_step(frames: int = 1) -> CommandResult:
    """Advance game by N frames."""
    ctx = registry.get_context()
    if not ctx or not hasattr(ctx, "world"):
        return CommandResult.error("No game context")
    
    dt = ctx.world.config.physics_dt
    for _ in range(frames):
        ctx.world.step(dt)
    
    return CommandResult.ok(f"Advanced {frames} frame(s)")


@command(
    name="engine.reset",
    description="Reset game to initial state",
    category=Category.ENGINE,
    access=AccessLevel.DEV,
)
def cmd_engine_reset() -> CommandResult:
    """Reset game to initial state."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    # This would need to reinitialize the game
    return CommandResult.error("Reset not implemented - restart the game instead")


@command(
    name="engine.info",
    description="Show engine information",
    category=Category.ENGINE,
    access=AccessLevel.DEV,
)
def cmd_engine_info() -> CommandResult:
    """Show engine information."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    lines = ["Engine Info:"]
    
    if hasattr(ctx, "fps"):
        lines.append(f"  FPS: {ctx.fps:.1f}")
    if hasattr(ctx, "frame_count"):
        lines.append(f"  Frames: {ctx.frame_count}")
    if hasattr(ctx, "config"):
        lines.append(f"  Target FPS: {ctx.config.target_fps}")
        lines.append(f"  Headless: {ctx.config.headless}")
    if hasattr(ctx, "_graphics_bridge"):
        lines.append(f"  Graphics: {'headless' if ctx._graphics_bridge.is_headless else 'active'}")
    
    return CommandResult.ok("\n".join(lines))


# =============================================================================
# Debug Commands
# =============================================================================


@command(
    name="debug.stats",
    description="Toggle debug statistics display",
    category=Category.DEBUG,
    access=AccessLevel.DEV,
)
def cmd_debug_stats(enabled: int = None) -> CommandResult:
    """Toggle debug statistics display."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "config"):
        if enabled is None:
            ctx.config.enable_debug = not ctx.config.enable_debug
        else:
            ctx.config.enable_debug = bool(enabled)
        return CommandResult.ok(f"Debug stats {'enabled' if ctx.config.enable_debug else 'disabled'}")
    
    return CommandResult.error("Debug stats not supported")


@command(
    name="debug.wireframe",
    description="Toggle wireframe rendering",
    category=Category.DEBUG,
    access=AccessLevel.DEV,
)
def cmd_debug_wireframe(enabled: int = None) -> CommandResult:
    """Toggle wireframe rendering."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if not hasattr(ctx, "flags"):
        ctx.flags = {}
    
    if enabled is None:
        ctx.flags["wireframe"] = not ctx.flags.get("wireframe", False)
    else:
        ctx.flags["wireframe"] = bool(enabled)
    
    return CommandResult.ok(f"Wireframe {'enabled' if ctx.flags['wireframe'] else 'disabled'}")


@command(
    name="debug.collision",
    description="Toggle collision visualization",
    category=Category.DEBUG,
    access=AccessLevel.DEV,
)
def cmd_debug_collision(enabled: int = None) -> CommandResult:
    """Toggle collision visualization."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if not hasattr(ctx, "flags"):
        ctx.flags = {}
    
    if enabled is None:
        ctx.flags["show_collision"] = not ctx.flags.get("show_collision", False)
    else:
        ctx.flags["show_collision"] = bool(enabled)
    
    return CommandResult.ok(f"Collision display {'enabled' if ctx.flags['show_collision'] else 'disabled'}")


# =============================================================================
# UI Commands
# =============================================================================


@command(
    name="ui.inventory",
    description="Toggle inventory panel",
    category=Category.UI,
    access=AccessLevel.PUBLIC,
)
def cmd_ui_inventory() -> CommandResult:
    """Toggle inventory panel."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "_on_inventory_pressed"):
        ctx._on_inventory_pressed()
        return CommandResult.ok()
    
    return CommandResult.error("Inventory UI not available")


@command(
    name="ui.pause",
    description="Toggle pause menu",
    category=Category.UI,
    access=AccessLevel.PUBLIC,
)
def cmd_ui_pause() -> CommandResult:
    """Toggle pause menu."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "_on_pause_pressed"):
        ctx._on_pause_pressed()
        return CommandResult.ok()
    
    return CommandResult.error("Pause menu not available")


@command(
    name="ui.console",
    description="Toggle console",
    category=Category.UI,
    access=AccessLevel.PUBLIC,
    aliases=["console.toggle"],
)
def cmd_ui_console() -> CommandResult:
    """Toggle console."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "console") and hasattr(ctx.console, "toggle"):
        ctx.console.toggle()
        return CommandResult.ok()
    
    # Just report that we would toggle the console
    return CommandResult.ok("Console toggled")


@command(
    name="ui.quest_log",
    description="Toggle quest log",
    category=Category.UI,
    access=AccessLevel.PUBLIC,
    aliases=["journal"],
)
def cmd_ui_quest_log() -> CommandResult:
    """Toggle quest log panel."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")

    if hasattr(ctx, "ui_manager") and ctx.ui_manager:
        ql = ctx.ui_manager.quest_log
        ql.visible = not ql.visible
        state = "opened" if ql.visible else "closed"
        return CommandResult.ok(f"Quest log {state}")

    return CommandResult.error("Quest log UI not available")


@command(
    name="ui.debug",
    description="Toggle debug overlay",
    category=Category.UI,
    access=AccessLevel.PUBLIC,
    aliases=["f3"],
)
def cmd_ui_debug() -> CommandResult:
    """Toggle debug overlay."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")

    if hasattr(ctx, "_toggle_debug_overlay"):
        ctx._toggle_debug_overlay()
        enabled = ctx.flags.get("debug_overlay", False)
        return CommandResult.ok(f"Debug overlay {'enabled' if enabled else 'disabled'}")

    return CommandResult.error("Debug overlay not available")


# =============================================================================
# Registration Function
# =============================================================================


def register_game_commands() -> None:
    """Register all game commands.
    
    This function is called automatically when the module is imported,
    as the @command decorators register commands on import.
    """
    # Commands are registered via decorators on import
    pass
