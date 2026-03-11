"""Tests for the resource harvesting system.

Covers:
- HarvestingSystem: hit detection, cooldown, drop rolling, prop destruction
- Resource drop table loading and validation
- Player attack input → harvest flow
- Resource items loading from JSON
- Harvestable props spawning with correct state
- Interaction context for harvest action text
- Player equipment (equipped_weapon)
"""
import json
import pytest
from pathlib import Path

import numpy as np

from procengine.game.harvesting import HarvestingSystem, HarvestResult
from procengine.game.game_api import (
    Player,
    Prop,
    GameWorld,
    Inventory,
    ItemDefinition,
)
from procengine.game.data_loader import (
    load_items_from_file,
    load_drop_tables_from_file,
    DataLoader,
)
from procengine.game.player_controller import (
    InputAction,
    InputState,
    PlayerController,
    InteractionTarget,
)
from procengine.physics import Vec3


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def drop_tables():
    """Minimal drop tables for testing."""
    return {
        "rock": {
            "hits_required": 3,
            "drops": [
                {"item_id": "stone", "min": 1, "max": 3},
            ],
            "tool_bonus": "pickaxe",
        },
        "tree": {
            "hits_required": 2,
            "drops": [
                {"item_id": "wood", "min": 2, "max": 4},
            ],
            "tool_bonus": "axe",
        },
        "flower_patch": {
            "hits_required": 1,
            "drops": [
                {"item_id": "flower_petal", "min": 1, "max": 2},
            ],
            "tool_bonus": None,
        },
    }


@pytest.fixture
def harvesting_system(drop_tables):
    """HarvestingSystem with fixed seed for deterministic tests."""
    return HarvestingSystem(drop_tables, seed=42)


@pytest.fixture
def world():
    """Minimal GameWorld with a player."""
    w = GameWorld()
    w.create_player(name="Tester", position=Vec3(0, 0, 0))
    # Register resource items so inventory lookups work
    for item_id in ("stone", "wood", "flower_petal"):
        w.register_item_definition(
            ItemDefinition(item_id=item_id, name=item_id.title())
        )
    return w


@pytest.fixture
def player(world):
    return world.get_player()


@pytest.fixture
def harvestable_rock(world):
    """Spawn a harvestable rock near the player."""
    prop = Prop(
        entity_id="rock_test_1",
        position=Vec3(1, 0, 0),
        prop_type="rock",
        interactable=True,
        interaction_action="harvest",
        state={"hits_remaining": 3},
    )
    world.spawn_entity(prop)
    return prop


# =============================================================================
# HarvestResult Tests
# =============================================================================


class TestHarvestResult:
    """Test HarvestResult dataclass."""

    def test_default_result(self):
        result = HarvestResult()
        assert result.hit is False
        assert result.destroyed is False
        assert result.drops == []
        assert result.on_cooldown is False

    def test_hit_result(self):
        result = HarvestResult(hit=True, target_name="Rock", hits_remaining=2)
        assert result.hit is True
        assert result.target_name == "Rock"
        assert result.hits_remaining == 2
        assert result.destroyed is False

    def test_destroyed_result(self):
        result = HarvestResult(
            hit=True,
            target_name="Rock",
            hits_remaining=0,
            destroyed=True,
            drops=[{"item_id": "stone", "count": 2}],
        )
        assert result.destroyed is True
        assert len(result.drops) == 1
        assert result.drops[0]["item_id"] == "stone"


# =============================================================================
# HarvestingSystem Tests
# =============================================================================


class TestHarvestingSystem:
    """Test HarvestingSystem core logic."""

    def test_no_target_in_range(self, harvesting_system, world, player):
        """try_harvest returns empty result when no harvestable props nearby."""
        result = harvesting_system.try_harvest(player, world)
        assert result.hit is False
        assert result.destroyed is False

    def test_hit_prop(self, harvesting_system, world, player, harvestable_rock):
        """Hitting a harvestable rock decrements hits_remaining."""
        result = harvesting_system.try_harvest(player, world)
        assert result.hit is True
        assert result.hits_remaining == 2
        assert result.destroyed is False
        assert harvestable_rock.state["hits_remaining"] == 2

    def test_destroy_prop_after_all_hits(self, harvesting_system, world, player, harvestable_rock):
        """Prop is destroyed after all hits are applied."""
        # Hit 3 times (rock has 3 hits)
        for i in range(3):
            harvesting_system._attack_cooldown = 0  # bypass cooldown
            result = harvesting_system.try_harvest(player, world)
            assert result.hit is True

        # After the third hit, prop should be destroyed
        assert result.destroyed is True
        assert result.hits_remaining == 0
        assert len(result.drops) > 0
        # Entity should be removed from world
        assert world.get_entity("rock_test_1") is None

    def test_drops_added_to_inventory(self, harvesting_system, world, player, harvestable_rock):
        """Drops are added to the player's inventory when prop is destroyed."""
        for _ in range(3):
            harvesting_system._attack_cooldown = 0
            harvesting_system.try_harvest(player, world)

        assert player.inventory.get_count("stone") > 0

    def test_cooldown_prevents_rapid_hits(self, harvesting_system, world, player, harvestable_rock):
        """Attack cooldown prevents hitting on consecutive frames."""
        result1 = harvesting_system.try_harvest(player, world)
        assert result1.hit is True

        # Immediately try again (cooldown active)
        result2 = harvesting_system.try_harvest(player, world)
        assert result2.on_cooldown is True
        assert result2.hit is False

    def test_cooldown_decreases_over_time(self, harvesting_system, world, player, harvestable_rock):
        """Cooldown timer decreases with update()."""
        harvesting_system.try_harvest(player, world)
        assert harvesting_system._attack_cooldown > 0

        harvesting_system.update(1.0)  # 1 second passes
        assert harvesting_system._attack_cooldown == 0

    def test_out_of_range_prop_not_hit(self, harvesting_system, world, player):
        """Props beyond attack_range are not hit."""
        far_prop = Prop(
            entity_id="far_rock",
            position=Vec3(100, 0, 0),
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 3},
        )
        world.spawn_entity(far_prop)

        result = harvesting_system.try_harvest(player, world)
        assert result.hit is False

    def test_non_harvestable_prop_ignored(self, harvesting_system, world, player):
        """Non-harvestable props (like doors) are ignored."""
        door = Prop(
            entity_id="door_1",
            position=Vec3(1, 0, 0),
            prop_type="door",
            interactable=True,
            interaction_action="open",
            state={"open": False},
        )
        world.spawn_entity(door)

        result = harvesting_system.try_harvest(player, world)
        assert result.hit is False

    def test_nearest_prop_is_targeted(self, harvesting_system, world, player):
        """When multiple harvestable props are in range, nearest is targeted."""
        near_prop = Prop(
            entity_id="near_rock",
            position=Vec3(1, 0, 0),
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 3},
        )
        far_prop = Prop(
            entity_id="far_rock",
            position=Vec3(2.5, 0, 0),
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 3},
        )
        world.spawn_entity(near_prop)
        world.spawn_entity(far_prop)

        result = harvesting_system.try_harvest(player, world)
        assert result.hit is True
        assert near_prop.state["hits_remaining"] == 2
        assert far_prop.state["hits_remaining"] == 3  # unchanged

    def test_get_drop_table(self, harvesting_system):
        """get_drop_table returns entry for known prop types."""
        table = harvesting_system.get_drop_table("rock")
        assert table is not None
        assert table["hits_required"] == 3

        assert harvesting_system.get_drop_table("nonexistent") is None

    def test_deterministic_drops(self, drop_tables):
        """Same seed produces same drops."""
        system1 = HarvestingSystem(drop_tables, seed=99)
        system2 = HarvestingSystem(drop_tables, seed=99)

        drops1 = system1._roll_drops("rock")
        drops2 = system2._roll_drops("rock")

        assert drops1 == drops2


# =============================================================================
# Drop Table Loading Tests
# =============================================================================


class TestResourceDropTable:
    """Test loading and validation of resource drop tables."""

    def test_load_drop_tables_from_file(self, tmp_path):
        """load_drop_tables_from_file parses JSON correctly."""
        data = {
            "drop_tables": {
                "rock": {
                    "hits_required": 4,
                    "drops": [{"item_id": "stone", "min": 1, "max": 3}],
                    "tool_bonus": "pickaxe",
                }
            }
        }
        path = tmp_path / "drops.json"
        path.write_text(json.dumps(data))

        tables = load_drop_tables_from_file(path)
        assert "rock" in tables
        assert tables["rock"]["hits_required"] == 4
        assert len(tables["rock"]["drops"]) == 1

    def test_load_drop_tables_empty(self, tmp_path):
        """Empty drop_tables key returns empty dict."""
        path = tmp_path / "empty.json"
        path.write_text('{"drop_tables": {}}')
        tables = load_drop_tables_from_file(path)
        assert tables == {}

    def test_data_loader_load_drop_tables(self, tmp_path):
        """DataLoader.load_drop_tables uses the correct path."""
        items_dir = tmp_path / "items"
        items_dir.mkdir()
        data = {"drop_tables": {"bush": {"hits_required": 2, "drops": [], "tool_bonus": None}}}
        (items_dir / "resource_drops.json").write_text(json.dumps(data))

        loader = DataLoader(data_dir=tmp_path)
        tables = loader.load_drop_tables()
        assert "bush" in tables

    def test_actual_resource_drops_file(self):
        """The shipped resource_drops.json loads without errors."""
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "data" / "items" / "resource_drops.json"
        if path.exists():
            tables = load_drop_tables_from_file(path)
            assert len(tables) >= 10
            for prop_type, entry in tables.items():
                assert "hits_required" in entry
                assert "drops" in entry
                assert isinstance(entry["drops"], list)


# =============================================================================
# Resource Items Tests
# =============================================================================


class TestResourceItems:
    """Test that new resource items load correctly from items.json."""

    def test_actual_items_json_loads(self):
        """items.json loads without errors and contains new resource items."""
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "data" / "items" / "items.json"
        if not path.exists():
            pytest.skip("items.json not found")

        items = load_items_from_file(path)
        item_ids = {i.item_id for i in items}

        for resource_id in ("wood", "stone", "plant_fiber", "flower_petal", "mushroom", "cactus_flesh", "bark"):
            assert resource_id in item_ids, f"Missing resource item: {resource_id}"

    def test_resource_items_are_stackable(self):
        """Resource items should be stackable."""
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "data" / "items" / "items.json"
        if not path.exists():
            pytest.skip("items.json not found")

        items = load_items_from_file(path)
        item_map = {i.item_id: i for i in items}

        for resource_id in ("wood", "stone", "plant_fiber", "bark"):
            assert item_map[resource_id].stackable is True
            assert item_map[resource_id].max_stack >= 50


# =============================================================================
# Prop Harvestable Property Tests
# =============================================================================


class TestHarvestableProps:
    """Test Prop.is_harvestable property."""

    def test_harvestable_prop(self):
        prop = Prop(
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 3},
        )
        assert prop.is_harvestable is True

    def test_non_harvestable_prop(self):
        prop = Prop(prop_type="door", interactable=True, interaction_action="open")
        assert prop.is_harvestable is False

    def test_depleted_prop(self):
        prop = Prop(
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 0},
        )
        assert prop.is_harvestable is False

    def test_default_prop(self):
        prop = Prop(prop_type="generic")
        assert prop.is_harvestable is False


# =============================================================================
# Player Equipment Tests
# =============================================================================


class TestPlayerEquipment:
    """Test Player.equipped_weapon field."""

    def test_default_no_weapon(self):
        player = Player()
        assert player.equipped_weapon is None

    def test_equip_weapon(self):
        player = Player()
        player.equipped_weapon = "iron_sword"
        assert player.equipped_weapon == "iron_sword"

    def test_serialize_equipped_weapon(self):
        player = Player(equipped_weapon="iron_sword")
        data = player.to_dict()
        assert data["equipped_weapon"] == "iron_sword"

    def test_deserialize_equipped_weapon(self):
        player = Player(equipped_weapon="iron_sword")
        data = player.to_dict()
        restored = Player.from_dict(data)
        assert restored.equipped_weapon == "iron_sword"

    def test_deserialize_no_weapon(self):
        player = Player()
        data = player.to_dict()
        restored = Player.from_dict(data)
        assert restored.equipped_weapon is None


# =============================================================================
# PlayerController Attack Integration Tests
# =============================================================================


class TestPlayerControllerAttack:
    """Test MOUSE1/ATTACK input → harvest flow."""

    def test_attack_with_harvesting_system(self):
        """ATTACK press triggers try_harvest via PlayerController."""
        pc = PlayerController()

        # Create a simple drop table and harvesting system
        tables = {
            "rock": {
                "hits_required": 1,
                "drops": [{"item_id": "stone", "min": 1, "max": 1}],
                "tool_bonus": None,
            }
        }
        hs = HarvestingSystem(tables, seed=0)
        pc._harvesting_system = hs

        # Setup world with player and harvestable prop
        world = GameWorld()
        world.create_player(name="T", position=Vec3(0, 0, 0))
        world.register_item_definition(ItemDefinition(item_id="stone", name="Stone"))

        prop = Prop(
            entity_id="r1",
            position=Vec3(1, 0, 0),
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 1},
        )
        world.spawn_entity(prop)

        player = world.get_player()

        # Simulate ATTACK press
        pc.input.state.pressed.add(InputAction.ATTACK)
        pc.input.state.just_pressed.add(InputAction.ATTACK)

        pc.update(player, world, 1 / 60)

        assert pc._last_harvest_result is not None
        assert pc._last_harvest_result.hit is True
        assert pc._last_harvest_result.destroyed is True
        assert player.inventory.get_count("stone") >= 1

    def test_attack_without_harvesting_system(self):
        """ATTACK press does nothing when harvesting system not set."""
        pc = PlayerController()
        world = GameWorld()
        world.create_player(name="T", position=Vec3(0, 0, 0))
        player = world.get_player()

        pc.input.state.pressed.add(InputAction.ATTACK)
        pc.input.state.just_pressed.add(InputAction.ATTACK)

        pc.update(player, world, 1 / 60)

        assert pc._last_harvest_result is None


# =============================================================================
# Interaction Context Tests
# =============================================================================


class TestHarvestInteractionContext:
    """Test interaction context for harvest props."""

    def test_harvest_action_text(self):
        """Harvest props show 'Harvest (N hits)' action text."""
        pc = PlayerController()

        world = GameWorld()
        world.create_player(name="T", position=Vec3(0, 0, 0))
        player = world.get_player()

        prop = Prop(
            entity_id="rock_ctx",
            position=Vec3(1, 0, 0),
            prop_type="rock",
            interactable=True,
            interaction_action="harvest",
            state={"hits_remaining": 4},
        )
        world.spawn_entity(prop)

        pc._update_interaction_context(player, world)

        target = pc.get_interaction_target()
        assert target is not None
        assert "Harvest" in target.action_text
        assert "4 hits" in target.action_text
        assert target.entity_type == "prop"
