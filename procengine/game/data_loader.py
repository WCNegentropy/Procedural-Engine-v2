"""Data loader for game content (NPCs, quests, items).

This module provides utilities for loading game content from JSON files
and registering them with the GameWorld.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING

from procengine.physics import Vec3
from procengine.game.game_api import (
    NPC,
    Quest,
    QuestObjective,
    QuestState,
    ObjectiveType,
    ItemDefinition,
    GameWorld,
    Inventory,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "load_npcs_from_file",
    "load_quests_from_file",
    "load_items_from_file",
    "load_all_game_data",
    "DataLoader",
]


def _parse_vec3(data: Dict[str, float]) -> Vec3:
    """Parse a Vec3 from a dictionary."""
    return Vec3(
        data.get("x", 0.0),
        data.get("y", 0.0),
        data.get("z", 0.0),
    )


def load_npcs_from_file(path: Path) -> List[NPC]:
    """Load NPC definitions from a JSON file.

    Parameters
    ----------
    path:
        Path to JSON file containing NPC definitions.

    Returns
    -------
    List[NPC]:
        List of NPC objects ready to be spawned.
    """
    with open(path, "r") as f:
        data = json.load(f)

    npcs = []
    for npc_data in data.get("npcs", []):
        # Parse position
        pos_data = npc_data.get("position", {})
        position = _parse_vec3(pos_data)

        # Create inventory for merchants
        merchant_inventory = Inventory()
        for item_id in npc_data.get("merchant_items", []):
            merchant_inventory.add_item(item_id, 10)  # Default stock

        npc = NPC(
            entity_id=npc_data["entity_id"],
            name=npc_data["name"],
            personality=npc_data.get("personality", ""),
            behavior=npc_data.get("behavior", "idle"),
            position=position,
            dialogue_range=npc_data.get("dialogue_range", 3.0),
            is_merchant=npc_data.get("is_merchant", False),
            current_quest=npc_data.get("current_quest"),
            merchant_inventory=merchant_inventory,
        )

        # Set relationships
        for entity_id, disposition in npc_data.get("relationships", {}).items():
            npc.set_disposition(entity_id, disposition)

        # Store patrol waypoints in behavior_params
        if "patrol_waypoints" in npc_data:
            npc.behavior_params["waypoints"] = [
                _parse_vec3(wp) for wp in npc_data["patrol_waypoints"]
            ]

        npcs.append(npc)

    return npcs


def load_quests_from_file(path: Path) -> List[Quest]:
    """Load quest definitions from a JSON file.

    Parameters
    ----------
    path:
        Path to JSON file containing quest definitions.

    Returns
    -------
    List[Quest]:
        List of Quest objects ready to be registered.
    """
    with open(path, "r") as f:
        data = json.load(f)

    quests = []
    for quest_data in data.get("quests", []):
        # Parse objectives
        objectives = []
        for obj_data in quest_data.get("objectives", []):
            objective = QuestObjective(
                objective_id=obj_data["objective_id"],
                description=obj_data["description"],
                objective_type=ObjectiveType[obj_data["objective_type"]],
                target=obj_data["target"],
                required_count=obj_data.get("required_count", 1),
                current_count=0,
                optional=obj_data.get("optional", False),
            )
            objectives.append(objective)

        quest = Quest(
            quest_id=quest_data["quest_id"],
            title=quest_data["title"],
            description=quest_data["description"],
            giver_npc_id=quest_data["giver_npc_id"],
            objectives=objectives,
            rewards=quest_data.get("rewards", {}),
            prerequisites=quest_data.get("prerequisites", []),
            on_complete_actions=quest_data.get("on_complete_actions", []),
            state=QuestState.UNAVAILABLE,  # Will be set to AVAILABLE when prerequisites met
        )

        quests.append(quest)

    return quests


def load_items_from_file(path: Path) -> List[ItemDefinition]:
    """Load item definitions from a JSON file.

    Parameters
    ----------
    path:
        Path to JSON file containing item definitions.

    Returns
    -------
    List[ItemDefinition]:
        List of ItemDefinition objects ready to be registered.
    """
    with open(path, "r") as f:
        data = json.load(f)

    items = []
    for item_data in data.get("items", []):
        item = ItemDefinition(
            item_id=item_data["item_id"],
            name=item_data["name"],
            description=item_data.get("description", ""),
            item_type=item_data.get("item_type", "misc"),
            value=item_data.get("value", 0),
            stackable=item_data.get("stackable", True),
            max_stack=item_data.get("max_stack", 99),
            properties=item_data.get("properties", {}),
        )
        items.append(item)

    return items


class DataLoader:
    """Utility class for loading and registering game data.

    Provides a convenient interface for loading NPCs, quests, and items
    from data directories and registering them with a GameWorld.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        """Initialize the data loader.

        Parameters
        ----------
        data_dir:
            Root directory for game data. Defaults to './data'.
        """
        self.data_dir = data_dir or Path("data")

    def load_npcs(self, filename: str = "npcs/village_npcs.json") -> List[NPC]:
        """Load NPCs from a file relative to data_dir."""
        return load_npcs_from_file(self.data_dir / filename)

    def load_quests(self, filename: str = "quests/village_quests.json") -> List[Quest]:
        """Load quests from a file relative to data_dir."""
        return load_quests_from_file(self.data_dir / filename)

    def load_items(self, filename: str = "items/items.json") -> List[ItemDefinition]:
        """Load items from a file relative to data_dir."""
        return load_items_from_file(self.data_dir / filename)

    def load_all(self, world: GameWorld) -> Dict[str, int]:
        """Load all game data and register with world.

        Parameters
        ----------
        world:
            GameWorld to register content with.

        Returns
        -------
        Dict[str, int]:
            Counts of loaded content by type.
        """
        counts = {"npcs": 0, "quests": 0, "items": 0}

        # Load items first (needed for inventory references)
        try:
            items = self.load_items()
            for item in items:
                world.register_item_definition(item)
            counts["items"] = len(items)
        except FileNotFoundError:
            pass

        # Load quests
        try:
            quests = self.load_quests()
            for quest in quests:
                world.register_quest(quest)
            counts["quests"] = len(quests)

            # Update quest availability based on prerequisites
            self._update_quest_availability(world, quests)
        except FileNotFoundError:
            pass

        # Load and spawn NPCs
        try:
            npcs = self.load_npcs()
            for npc in npcs:
                world.spawn_entity(npc)
            counts["npcs"] = len(npcs)
        except FileNotFoundError:
            pass

        return counts

    def _update_quest_availability(
        self,
        world: GameWorld,
        quests: List[Quest],
    ) -> None:
        """Update quest states based on prerequisites."""
        player = world.get_player()
        completed = set(player.completed_quests) if player else set()

        for quest in quests:
            if quest.state == QuestState.UNAVAILABLE:
                # Check if all prerequisites are met
                if all(prereq in completed for prereq in quest.prerequisites):
                    quest.state = QuestState.AVAILABLE


def load_all_game_data(world: GameWorld, data_dir: Optional[Path] = None) -> Dict[str, int]:
    """Convenience function to load all game data.

    Parameters
    ----------
    world:
        GameWorld to register content with.
    data_dir:
        Optional custom data directory.

    Returns
    -------
    Dict[str, int]:
        Counts of loaded content by type.
    """
    loader = DataLoader(data_dir)
    return loader.load_all(world)
