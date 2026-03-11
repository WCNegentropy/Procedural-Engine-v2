"""Tests for the crafting system.

Tests cover:
- CraftingRecipe dataclass and methods
- Recipe registration and lookup in GameWorld
- Crafting execution (ingredient consumption, result creation)
- Recipe matching by selected items
- Data loading of recipes from JSON
- CraftingPanel UI component
- player.craft command
"""
import pytest
import json
import tempfile
from pathlib import Path

from procengine.game.game_api import (
    CraftingRecipe,
    EventType,
    Event,
    Inventory,
    ItemDefinition,
    Player,
    GameWorld,
    GameConfig,
)
from procengine.game.data_loader import load_recipes_from_file, DataLoader
from procengine.game.ui_system import (
    CraftingPanel,
    HeadlessUIBackend,
    UIManager,
)
from procengine.physics import Vec3


# =============================================================================
# CraftingRecipe Tests
# =============================================================================


class TestCraftingRecipe:
    """Tests for the CraftingRecipe dataclass."""

    def test_create_recipe(self):
        recipe = CraftingRecipe(
            recipe_id="craft_rope",
            name="Rope",
            description="Weave plant fiber into rope.",
            ingredients={"plant_fiber": 3},
            result_item="rope",
            result_count=1,
            category="materials",
        )
        assert recipe.recipe_id == "craft_rope"
        assert recipe.name == "Rope"
        assert recipe.ingredients == {"plant_fiber": 3}
        assert recipe.result_item == "rope"
        assert recipe.result_count == 1
        assert recipe.category == "materials"

    def test_can_craft_sufficient_materials(self):
        recipe = CraftingRecipe(
            recipe_id="test",
            name="Test",
            ingredients={"wood": 2, "stone": 1},
            result_item="result",
        )
        inv = Inventory()
        inv.add_item("wood", 5)
        inv.add_item("stone", 3)
        assert recipe.can_craft(inv) is True

    def test_can_craft_exact_materials(self):
        recipe = CraftingRecipe(
            recipe_id="test",
            name="Test",
            ingredients={"wood": 2},
            result_item="result",
        )
        inv = Inventory()
        inv.add_item("wood", 2)
        assert recipe.can_craft(inv) is True

    def test_cannot_craft_insufficient_materials(self):
        recipe = CraftingRecipe(
            recipe_id="test",
            name="Test",
            ingredients={"wood": 5, "stone": 3},
            result_item="result",
        )
        inv = Inventory()
        inv.add_item("wood", 2)
        inv.add_item("stone", 3)
        assert recipe.can_craft(inv) is False

    def test_cannot_craft_missing_material(self):
        recipe = CraftingRecipe(
            recipe_id="test",
            name="Test",
            ingredients={"wood": 1, "iron": 1},
            result_item="result",
        )
        inv = Inventory()
        inv.add_item("wood", 10)
        # No iron at all
        assert recipe.can_craft(inv) is False

    def test_get_ingredient_ids(self):
        recipe = CraftingRecipe(
            recipe_id="test",
            name="Test",
            ingredients={"wood": 2, "stone": 1, "rope": 1},
            result_item="result",
        )
        assert recipe.get_ingredient_ids() == frozenset({"wood", "stone", "rope"})

    def test_serialization_roundtrip(self):
        recipe = CraftingRecipe(
            recipe_id="craft_sword",
            name="Iron Sword",
            description="Forge a sword.",
            ingredients={"iron_ingot": 3, "wood": 1},
            result_item="iron_sword",
            result_count=1,
            category="weapons",
        )
        data = recipe.to_dict()
        restored = CraftingRecipe.from_dict(data)
        assert restored.recipe_id == recipe.recipe_id
        assert restored.name == recipe.name
        assert restored.description == recipe.description
        assert restored.ingredients == recipe.ingredients
        assert restored.result_item == recipe.result_item
        assert restored.result_count == recipe.result_count
        assert restored.category == recipe.category


# =============================================================================
# GameWorld Crafting Tests
# =============================================================================


class TestGameWorldCrafting:
    """Tests for crafting in GameWorld."""

    @pytest.fixture
    def world(self):
        world = GameWorld(GameConfig())
        # Register item definitions
        for item_id in ("wood", "stone", "plant_fiber", "rope", "stone_axe"):
            world.register_item_definition(ItemDefinition(
                item_id=item_id,
                name=item_id.replace("_", " ").title(),
            ))
        # Register recipes
        world.register_recipe(CraftingRecipe(
            recipe_id="craft_rope",
            name="Rope",
            ingredients={"plant_fiber": 3},
            result_item="rope",
            result_count=1,
            category="materials",
        ))
        world.register_recipe(CraftingRecipe(
            recipe_id="craft_stone_axe",
            name="Stone Axe",
            ingredients={"stone": 3, "wood": 2, "plant_fiber": 2},
            result_item="stone_axe",
            result_count=1,
            category="tools",
        ))
        # Create and spawn player
        player = Player(entity_id="player", position=Vec3(0, 0, 0))
        world.spawn_entity(player)
        world._player = player
        return world

    def test_register_and_get_recipe(self, world):
        recipe = world.get_recipe("craft_rope")
        assert recipe is not None
        assert recipe.name == "Rope"

    def test_get_recipe_nonexistent(self, world):
        assert world.get_recipe("nonexistent") is None

    def test_get_all_recipes(self, world):
        recipes = world.get_all_recipes()
        assert len(recipes) == 2
        assert "craft_rope" in recipes
        assert "craft_stone_axe" in recipes

    def test_get_recipes_for_items_single_match(self, world):
        # Selecting plant_fiber should match craft_rope
        matches = world.get_recipes_for_items(["plant_fiber"])
        assert len(matches) == 1
        assert matches[0].recipe_id == "craft_rope"

    def test_get_recipes_for_items_multi_match(self, world):
        # Selecting all three should match both recipes
        matches = world.get_recipes_for_items(["wood", "stone", "plant_fiber"])
        recipe_ids = {r.recipe_id for r in matches}
        assert recipe_ids == {"craft_rope", "craft_stone_axe"}

    def test_get_recipes_for_items_no_match(self, world):
        matches = world.get_recipes_for_items(["rope"])
        assert len(matches) == 0

    def test_get_recipes_for_items_empty(self, world):
        matches = world.get_recipes_for_items([])
        assert len(matches) == 0

    def test_craft_item_success(self, world):
        player = world.get_player()
        player.inventory.add_item("plant_fiber", 5)

        crafted_events = []
        world.events.subscribe(EventType.ITEM_CRAFTED, crafted_events.append)

        result = world.craft_item("craft_rope", player)
        assert result is True
        assert player.inventory.get_count("plant_fiber") == 2  # 5 - 3
        assert player.inventory.get_count("rope") == 1
        assert len(crafted_events) == 1
        assert crafted_events[0].data["recipe_id"] == "craft_rope"
        assert crafted_events[0].data["item_id"] == "rope"

    def test_craft_item_insufficient_materials(self, world):
        player = world.get_player()
        player.inventory.add_item("plant_fiber", 1)

        result = world.craft_item("craft_rope", player)
        assert result is False
        assert player.inventory.get_count("plant_fiber") == 1  # Unchanged
        assert player.inventory.get_count("rope") == 0

    def test_craft_item_nonexistent_recipe(self, world):
        player = world.get_player()
        result = world.craft_item("nonexistent", player)
        assert result is False

    def test_craft_complex_recipe(self, world):
        player = world.get_player()
        player.inventory.add_item("stone", 3)
        player.inventory.add_item("wood", 2)
        player.inventory.add_item("plant_fiber", 2)

        result = world.craft_item("craft_stone_axe", player)
        assert result is True
        assert player.inventory.get_count("stone") == 0
        assert player.inventory.get_count("wood") == 0
        assert player.inventory.get_count("plant_fiber") == 0
        assert player.inventory.get_count("stone_axe") == 1

    def test_craft_uses_default_player(self, world):
        """craft_item with player=None should use world._player."""
        player = world.get_player()
        player.inventory.add_item("plant_fiber", 3)

        result = world.craft_item("craft_rope")
        assert result is True
        assert player.inventory.get_count("rope") == 1

    def test_craft_result_count_greater_than_one(self):
        """Recipes that produce multiple items should add the full count."""
        world = GameWorld(GameConfig())
        world.register_item_definition(ItemDefinition(item_id="wood", name="Wood"))
        world.register_item_definition(ItemDefinition(item_id="planks", name="Planks"))
        world.register_recipe(CraftingRecipe(
            recipe_id="craft_planks",
            name="Planks",
            ingredients={"wood": 2},
            result_item="planks",
            result_count=4,
        ))
        player = Player(entity_id="player", position=Vec3(0, 0, 0))
        world.spawn_entity(player)
        world._player = player
        player.inventory.add_item("wood", 2)

        result = world.craft_item("craft_planks", player)
        assert result is True
        assert player.inventory.get_count("planks") == 4
        assert player.inventory.get_count("wood") == 0


# =============================================================================
# Data Loader Tests
# =============================================================================


class TestRecipeDataLoader:
    """Tests for loading recipes from JSON files."""

    @pytest.fixture
    def recipe_file(self, tmp_path):
        recipes_data = {
            "recipes": [
                {
                    "recipe_id": "craft_rope",
                    "name": "Rope",
                    "description": "Weave fiber into rope.",
                    "ingredients": {"plant_fiber": 3},
                    "result_item": "rope",
                    "result_count": 1,
                    "category": "materials",
                },
                {
                    "recipe_id": "craft_torch",
                    "name": "Torch",
                    "ingredients": {"wood": 1, "bark": 1},
                    "result_item": "torch",
                    "result_count": 2,
                    "category": "tools",
                },
            ]
        }
        path = tmp_path / "recipes.json"
        with open(path, "w") as f:
            json.dump(recipes_data, f)
        return path

    def test_load_recipes_from_file(self, recipe_file):
        recipes = load_recipes_from_file(recipe_file)
        assert len(recipes) == 2
        assert recipes[0].recipe_id == "craft_rope"
        assert recipes[0].ingredients == {"plant_fiber": 3}
        assert recipes[1].recipe_id == "craft_torch"
        assert recipes[1].result_count == 2

    def test_data_loader_load_recipes(self, tmp_path):
        items_dir = tmp_path / "items"
        items_dir.mkdir()

        recipes_data = {
            "recipes": [
                {
                    "recipe_id": "craft_test",
                    "name": "Test Item",
                    "ingredients": {"a": 1},
                    "result_item": "b",
                }
            ]
        }
        with open(items_dir / "recipes.json", "w") as f:
            json.dump(recipes_data, f)

        loader = DataLoader(data_dir=tmp_path)
        recipes = loader.load_recipes()
        assert len(recipes) == 1
        assert recipes[0].recipe_id == "craft_test"

    def test_load_all_includes_recipes(self, tmp_path):
        """DataLoader.load_all should load and register recipes."""
        items_dir = tmp_path / "items"
        items_dir.mkdir()

        # Items file
        items_data = {
            "items": [
                {"item_id": "wood", "name": "Wood"},
                {"item_id": "planks", "name": "Planks"},
            ]
        }
        with open(items_dir / "items.json", "w") as f:
            json.dump(items_data, f)

        # Recipes file
        recipes_data = {
            "recipes": [
                {
                    "recipe_id": "craft_planks",
                    "name": "Planks",
                    "ingredients": {"wood": 2},
                    "result_item": "planks",
                    "result_count": 4,
                }
            ]
        }
        with open(items_dir / "recipes.json", "w") as f:
            json.dump(recipes_data, f)

        world = GameWorld(GameConfig())
        player = Player(entity_id="player", position=Vec3(0, 0, 0))
        world.spawn_entity(player)
        world._player = player

        loader = DataLoader(data_dir=tmp_path)
        counts = loader.load_all(world)

        assert counts["recipes"] == 1
        assert world.get_recipe("craft_planks") is not None


# =============================================================================
# CraftingPanel UI Tests
# =============================================================================


class MockPlayer:
    """Mock player for UI testing."""

    def __init__(self):
        self.inventory = Inventory()
        self.position = Vec3(0, 0, 0)


class TestCraftingPanel:
    """Tests for the CraftingPanel UI component."""

    def test_panel_creation(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        assert panel._selected_items == set()
        assert panel._selected_recipe is None
        assert panel._recipes == []

    def test_set_recipes(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        recipes = [
            {"recipe_id": "r1", "name": "Test", "ingredients": {"a": 1}, "result_item": "b"},
        ]
        panel.set_recipes(recipes)
        assert len(panel._recipes) == 1

    def test_matching_recipes_empty_selection(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        panel.set_recipes([
            {"recipe_id": "r1", "name": "Test", "ingredients": {"a": 1}, "result_item": "b"},
        ])
        assert panel._get_matching_recipes() == []

    def test_matching_recipes_with_selection(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        panel.set_recipes([
            {"recipe_id": "r1", "name": "Rope", "ingredients": {"plant_fiber": 3}, "result_item": "rope"},
            {"recipe_id": "r2", "name": "Axe", "ingredients": {"wood": 2, "stone": 3}, "result_item": "axe"},
        ])
        panel._selected_items = {"plant_fiber"}
        matches = panel._get_matching_recipes()
        assert len(matches) == 1
        assert matches[0]["recipe_id"] == "r1"

    def test_can_craft_recipe_check(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        panel._inventory_snapshot = {"plant_fiber": 5}
        recipe = {"ingredients": {"plant_fiber": 3}}
        assert panel._can_craft_recipe(recipe) is True

    def test_cannot_craft_recipe_check(self):
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        panel._inventory_snapshot = {"plant_fiber": 1}
        recipe = {"ingredients": {"plant_fiber": 3}}
        assert panel._can_craft_recipe(recipe) is False

    def test_render_without_crash(self):
        """Ensure render executes without error on headless backend."""
        backend = HeadlessUIBackend()
        panel = CraftingPanel(backend, 1920, 1080)
        player = MockPlayer()
        player.inventory.add_item("wood", 5)
        panel.set_recipes([
            {"recipe_id": "r1", "name": "Test", "ingredients": {"wood": 2},
             "result_item": "planks", "result_count": 4, "category": "materials"},
        ])
        panel.set_item_definitions({"wood": {"name": "Wood", "item_type": "material"}})
        panel._selected_items = {"wood"}
        panel._selected_recipe = "r1"
        panel.visible = True
        # Should not raise
        panel.render(player=player)


# =============================================================================
# UIManager Crafting Integration
# =============================================================================


class TestUIManagerCrafting:
    """Tests for UIManager crafting integration."""

    def test_crafting_panel_property(self):
        ui = UIManager(1920, 1080)
        assert isinstance(ui.crafting_panel, CraftingPanel)

    def test_set_crafting_callbacks(self):
        ui = UIManager(1920, 1080)
        callback_called = []
        ui.set_crafting_callbacks(on_craft=lambda rid: callback_called.append(rid))
        assert ui._crafting_panel._on_craft is not None

    def test_set_world_populates_crafting_panel(self):
        ui = UIManager(1920, 1080)
        world = GameWorld(GameConfig())
        world.register_item_definition(ItemDefinition(item_id="wood", name="Wood"))
        world.register_recipe(CraftingRecipe(
            recipe_id="craft_test",
            name="Test",
            ingredients={"wood": 1},
            result_item="planks",
        ))
        player = Player(entity_id="player", position=Vec3(0, 0, 0))
        world.spawn_entity(player)
        world._player = player

        ui.set_world(world)
        assert len(ui._crafting_panel._recipes) == 1
        assert "wood" in ui._crafting_panel._item_definitions

    def test_render_crafting_method(self):
        ui = UIManager(1920, 1080)
        player = MockPlayer()
        # Should not raise
        ui.render_crafting(player=player)
