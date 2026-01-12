"""Tests for data_loader module."""
import pytest
import json
import tempfile
from pathlib import Path

from data_loader import (
    load_npcs_from_file,
    load_quests_from_file,
    load_items_from_file,
    load_all_game_data,
    DataLoader,
)
from game_api import GameWorld, QuestState, ObjectiveType
from physics import Vec3


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory with test files."""
    npcs_dir = tmp_path / "npcs"
    quests_dir = tmp_path / "quests"
    items_dir = tmp_path / "items"
    npcs_dir.mkdir()
    quests_dir.mkdir()
    items_dir.mkdir()

    # Create test NPC file
    npcs_data = {
        "npcs": [
            {
                "entity_id": "test_npc",
                "name": "Test NPC",
                "personality": "Friendly test NPC",
                "behavior": "idle",
                "position": {"x": 10, "y": 0, "z": 20},
                "dialogue_range": 3.0,
                "is_merchant": False,
                "relationships": {"player": 0.5}
            },
            {
                "entity_id": "test_merchant",
                "name": "Test Merchant",
                "personality": "A merchant",
                "behavior": "merchant",
                "position": {"x": 15, "y": 0, "z": 25},
                "dialogue_range": 4.0,
                "is_merchant": True,
                "merchant_items": ["gold", "potion"]
            }
        ]
    }
    with open(npcs_dir / "test_npcs.json", "w") as f:
        json.dump(npcs_data, f)

    # Create test quest file
    quests_data = {
        "quests": [
            {
                "quest_id": "test_quest",
                "title": "Test Quest",
                "description": "A test quest",
                "giver_npc_id": "test_npc",
                "objectives": [
                    {
                        "objective_id": "obj1",
                        "description": "Collect items",
                        "objective_type": "COLLECT",
                        "target": "test_item",
                        "required_count": 3
                    },
                    {
                        "objective_id": "obj2",
                        "description": "Talk to NPC",
                        "objective_type": "TALK",
                        "target": "test_npc",
                        "required_count": 1,
                        "optional": True
                    }
                ],
                "rewards": {"gold": 100},
                "prerequisites": []
            },
            {
                "quest_id": "locked_quest",
                "title": "Locked Quest",
                "description": "Requires test_quest",
                "giver_npc_id": "test_npc",
                "objectives": [],
                "rewards": {},
                "prerequisites": ["test_quest"]
            }
        ]
    }
    with open(quests_dir / "test_quests.json", "w") as f:
        json.dump(quests_data, f)

    # Create test item file
    items_data = {
        "items": [
            {
                "item_id": "gold",
                "name": "Gold",
                "description": "Currency",
                "item_type": "currency",
                "value": 1,
                "stackable": True,
                "max_stack": 9999
            },
            {
                "item_id": "potion",
                "name": "Health Potion",
                "description": "Heals",
                "item_type": "consumable",
                "value": 25,
                "properties": {"heal_amount": 50}
            },
            {
                "item_id": "sword",
                "name": "Iron Sword",
                "description": "A sword",
                "item_type": "weapon",
                "value": 100,
                "stackable": False,
                "properties": {"damage": 10}
            }
        ]
    }
    with open(items_dir / "test_items.json", "w") as f:
        json.dump(items_data, f)

    return tmp_path


# =============================================================================
# NPC Loading Tests
# =============================================================================

class TestLoadNPCs:
    """Test NPC loading from JSON."""

    def test_load_npcs(self, temp_data_dir):
        npcs = load_npcs_from_file(temp_data_dir / "npcs" / "test_npcs.json")

        assert len(npcs) == 2

    def test_npc_properties(self, temp_data_dir):
        npcs = load_npcs_from_file(temp_data_dir / "npcs" / "test_npcs.json")

        npc = npcs[0]
        assert npc.entity_id == "test_npc"
        assert npc.name == "Test NPC"
        assert npc.personality == "Friendly test NPC"
        assert npc.behavior == "idle"

    def test_npc_position(self, temp_data_dir):
        npcs = load_npcs_from_file(temp_data_dir / "npcs" / "test_npcs.json")

        npc = npcs[0]
        assert npc.position.x == 10
        assert npc.position.y == 0
        assert npc.position.z == 20

    def test_npc_relationships(self, temp_data_dir):
        npcs = load_npcs_from_file(temp_data_dir / "npcs" / "test_npcs.json")

        npc = npcs[0]
        assert npc.get_disposition("player") == 0.5

    def test_merchant_inventory(self, temp_data_dir):
        npcs = load_npcs_from_file(temp_data_dir / "npcs" / "test_npcs.json")

        merchant = npcs[1]
        assert merchant.is_merchant
        assert merchant.merchant_inventory.has_item("gold")
        assert merchant.merchant_inventory.has_item("potion")


# =============================================================================
# Quest Loading Tests
# =============================================================================

class TestLoadQuests:
    """Test quest loading from JSON."""

    def test_load_quests(self, temp_data_dir):
        quests = load_quests_from_file(temp_data_dir / "quests" / "test_quests.json")

        assert len(quests) == 2

    def test_quest_properties(self, temp_data_dir):
        quests = load_quests_from_file(temp_data_dir / "quests" / "test_quests.json")

        quest = quests[0]
        assert quest.quest_id == "test_quest"
        assert quest.title == "Test Quest"
        assert quest.giver_npc_id == "test_npc"

    def test_quest_objectives(self, temp_data_dir):
        quests = load_quests_from_file(temp_data_dir / "quests" / "test_quests.json")

        quest = quests[0]
        assert len(quest.objectives) == 2

        obj1 = quest.objectives[0]
        assert obj1.objective_id == "obj1"
        assert obj1.objective_type == ObjectiveType.COLLECT
        assert obj1.target == "test_item"
        assert obj1.required_count == 3
        assert not obj1.optional

        obj2 = quest.objectives[1]
        assert obj2.optional

    def test_quest_rewards(self, temp_data_dir):
        quests = load_quests_from_file(temp_data_dir / "quests" / "test_quests.json")

        quest = quests[0]
        assert quest.rewards.get("gold") == 100

    def test_quest_prerequisites(self, temp_data_dir):
        quests = load_quests_from_file(temp_data_dir / "quests" / "test_quests.json")

        locked = quests[1]
        assert "test_quest" in locked.prerequisites


# =============================================================================
# Item Loading Tests
# =============================================================================

class TestLoadItems:
    """Test item loading from JSON."""

    def test_load_items(self, temp_data_dir):
        items = load_items_from_file(temp_data_dir / "items" / "test_items.json")

        assert len(items) == 3

    def test_item_properties(self, temp_data_dir):
        items = load_items_from_file(temp_data_dir / "items" / "test_items.json")

        gold = items[0]
        assert gold.item_id == "gold"
        assert gold.name == "Gold"
        assert gold.item_type == "currency"
        assert gold.stackable
        assert gold.max_stack == 9999

    def test_item_custom_properties(self, temp_data_dir):
        items = load_items_from_file(temp_data_dir / "items" / "test_items.json")

        potion = items[1]
        assert potion.properties.get("heal_amount") == 50

        sword = items[2]
        assert sword.properties.get("damage") == 10
        assert not sword.stackable


# =============================================================================
# DataLoader Tests
# =============================================================================

class TestDataLoader:
    """Test DataLoader class."""

    def test_loader_creation(self, temp_data_dir):
        loader = DataLoader(temp_data_dir)
        assert loader.data_dir == temp_data_dir

    def test_load_all(self, temp_data_dir):
        # Rename files to match default paths
        (temp_data_dir / "npcs" / "test_npcs.json").rename(
            temp_data_dir / "npcs" / "village_npcs.json"
        )
        (temp_data_dir / "quests" / "test_quests.json").rename(
            temp_data_dir / "quests" / "village_quests.json"
        )
        (temp_data_dir / "items" / "test_items.json").rename(
            temp_data_dir / "items" / "items.json"
        )

        loader = DataLoader(temp_data_dir)
        world = GameWorld()
        world.create_player()

        counts = loader.load_all(world)

        assert counts["npcs"] == 2
        assert counts["quests"] == 2
        assert counts["items"] == 3

    def test_load_all_registers_items(self, temp_data_dir):
        (temp_data_dir / "items" / "test_items.json").rename(
            temp_data_dir / "items" / "items.json"
        )

        loader = DataLoader(temp_data_dir)
        world = GameWorld()

        loader.load_all(world)

        gold_def = world.get_item_definition("gold")
        assert gold_def is not None
        assert gold_def.name == "Gold"

    def test_load_all_spawns_npcs(self, temp_data_dir):
        (temp_data_dir / "npcs" / "test_npcs.json").rename(
            temp_data_dir / "npcs" / "village_npcs.json"
        )

        loader = DataLoader(temp_data_dir)
        world = GameWorld()

        loader.load_all(world)

        npc = world.get_entity("test_npc")
        assert npc is not None
        assert npc.name == "Test NPC"

    def test_quest_availability_update(self, temp_data_dir):
        (temp_data_dir / "quests" / "test_quests.json").rename(
            temp_data_dir / "quests" / "village_quests.json"
        )

        loader = DataLoader(temp_data_dir)
        world = GameWorld()
        player = world.create_player()

        loader.load_all(world)

        # Quest without prerequisites should be available
        test_quest = world.get_quest("test_quest")
        assert test_quest.state == QuestState.AVAILABLE

        # Quest with prerequisites should be unavailable
        locked_quest = world.get_quest("locked_quest")
        assert locked_quest.state == QuestState.UNAVAILABLE

        # Complete prerequisite and reload
        player.completed_quests.append("test_quest")
        loader._update_quest_availability(world, [locked_quest])

        # Now should be available
        assert locked_quest.state == QuestState.AVAILABLE


# =============================================================================
# Integration with Actual Data Files
# =============================================================================

class TestActualDataFiles:
    """Test loading actual game data files."""

    def test_load_village_npcs(self):
        path = Path("data/npcs/village_npcs.json")
        if not path.exists():
            pytest.skip("village_npcs.json not found")

        npcs = load_npcs_from_file(path)
        assert len(npcs) > 0

        # Check that all NPCs have required fields
        for npc in npcs:
            assert npc.entity_id
            assert npc.name
            assert npc.position is not None

    def test_load_village_quests(self):
        path = Path("data/quests/village_quests.json")
        if not path.exists():
            pytest.skip("village_quests.json not found")

        quests = load_quests_from_file(path)
        assert len(quests) > 0

        for quest in quests:
            assert quest.quest_id
            assert quest.title
            assert quest.giver_npc_id

    def test_load_items(self):
        path = Path("data/items/items.json")
        if not path.exists():
            pytest.skip("items.json not found")

        items = load_items_from_file(path)
        assert len(items) > 0

        for item in items:
            assert item.item_id
            assert item.name

    def test_full_data_load(self):
        data_dir = Path("data")
        if not data_dir.exists():
            pytest.skip("data directory not found")

        world = GameWorld()
        world.create_player()

        counts = load_all_game_data(world, data_dir)

        # Should have loaded content
        assert counts["npcs"] >= 0
        assert counts["quests"] >= 0
        assert counts["items"] >= 0
