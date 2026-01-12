"""Tests for game_api module.

Tests cover:
- Entity hierarchy (Entity, Character, Player, NPC, Prop, Item)
- Inventory system
- Quest system
- Dialogue system
- NPC agent framework
- GameWorld management
- Save/load serialization
"""
import pytest
import json
import tempfile
from pathlib import Path

from game_api import (
    # Core types
    EntityId,
    EventType,
    Event,
    EventBus,
    # Entities
    Entity,
    Character,
    Player,
    NPC,
    Prop,
    Item,
    # Inventory
    Inventory,
    ItemDefinition,
    # Quest system
    Quest,
    QuestObjective,
    QuestState,
    ObjectiveType,
    # Dialogue
    DialogueResponse,
    DialogueContext,
    # Agent framework
    NPCAgent,
    LocalAgent,
    # Game world
    GameWorld,
    GameConfig,
)
from physics import Vec3, HeightField2D
import numpy as np


# =============================================================================
# Vec3 Tests (using physics module)
# =============================================================================

class TestVec3Integration:
    """Test Vec3 integration with game entities."""

    def test_entity_position_is_vec3(self):
        entity = Entity()
        assert isinstance(entity.position, Vec3)

    def test_character_velocity_is_vec3(self):
        char = Character()
        assert isinstance(char.velocity, Vec3)


# =============================================================================
# Event System Tests
# =============================================================================

class TestEventBus:
    """Test the event bus pub/sub system."""

    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.subscribe(EventType.ENTITY_SPAWNED, handler)
        bus.emit(Event(EventType.ENTITY_SPAWNED, {"id": "test"}))

        assert len(received) == 1
        assert received[0].data["id"] == "test"

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        unsub = bus.subscribe(EventType.ENTITY_SPAWNED, handler)
        bus.emit(Event(EventType.ENTITY_SPAWNED, {}))
        assert len(received) == 1

        unsub()
        bus.emit(Event(EventType.ENTITY_SPAWNED, {}))
        assert len(received) == 1  # No new event

    def test_subscribe_all(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event.event_type)

        bus.subscribe_all(handler)
        bus.emit(Event(EventType.ENTITY_SPAWNED, {}))
        bus.emit(Event(EventType.PLAYER_MOVED, {}))

        assert EventType.ENTITY_SPAWNED in received
        assert EventType.PLAYER_MOVED in received

    def test_multiple_listeners(self):
        bus = EventBus()
        count = [0]

        def handler1(event: Event):
            count[0] += 1

        def handler2(event: Event):
            count[0] += 10

        bus.subscribe(EventType.ITEM_ACQUIRED, handler1)
        bus.subscribe(EventType.ITEM_ACQUIRED, handler2)
        bus.emit(Event(EventType.ITEM_ACQUIRED, {}))

        assert count[0] == 11


# =============================================================================
# Entity Tests
# =============================================================================

class TestEntity:
    """Test base Entity class."""

    def test_entity_creation(self):
        entity = Entity()
        assert entity.entity_id is not None
        assert entity.active is True

    def test_entity_with_position(self):
        entity = Entity(position=Vec3(1, 2, 3))
        assert entity.position.x == 1
        assert entity.position.y == 2
        assert entity.position.z == 3

    def test_entity_serialization(self):
        entity = Entity(
            entity_id="test123",
            position=Vec3(10, 20, 30),
            rotation=1.5,
            active=False,
        )
        data = entity.to_dict()

        assert data["entity_id"] == "test123"
        assert data["position"]["x"] == 10
        assert data["rotation"] == 1.5
        assert data["active"] is False

    def test_entity_deserialization(self):
        data = {
            "entity_id": "abc",
            "position": {"x": 5, "y": 6, "z": 7},
            "rotation": 0.5,
            "active": True,
        }
        entity = Entity.from_dict(data)

        assert entity.entity_id == "abc"
        assert entity.position.x == 5
        assert entity.rotation == 0.5


class TestCharacter:
    """Test Character class."""

    def test_character_creation(self):
        char = Character()
        assert char.health == 100.0
        assert char.is_alive()

    def test_character_damage_and_heal(self):
        char = Character(health=100, max_health=100)

        char.take_damage(30)
        assert char.health == 70

        char.heal(20)
        assert char.health == 90

        char.heal(50)  # Should cap at max
        assert char.health == 100

    def test_character_death(self):
        char = Character(health=50)
        char.take_damage(60)
        assert char.health == 0
        assert not char.is_alive()

    def test_character_to_rigid_body(self):
        char = Character(
            position=Vec3(1, 2, 3),
            velocity=Vec3(4, 5, 6),
            mass=70,
            radius=0.5,
        )
        body = char.to_rigid_body()

        assert body.position.x == 1
        assert body.velocity.y == 5
        assert body.mass == 70
        assert body.radius == 0.5

    def test_character_serialization(self):
        char = Character(
            entity_id="char1",
            health=75,
            max_health=100,
        )
        char.inventory.add_item("gold", 50)

        data = char.to_dict()
        assert data["health"] == 75
        assert data["inventory"]["items"]["gold"] == 50


class TestPlayer:
    """Test Player class."""

    def test_player_creation(self):
        player = Player(name="Hero")
        assert player.name == "Hero"
        assert len(player.active_quests) == 0

    def test_player_movement_speed(self):
        player = Player(move_speed=5.0, sprint_multiplier=1.5)

        assert player.get_move_speed() == 5.0

        player.is_sprinting = True
        assert player.get_move_speed() == 7.5

    def test_player_dialogue_history(self):
        player = Player()

        player.add_dialogue("npc1", "player", "Hello!")
        player.add_dialogue("npc1", "npc", "Hi there!")

        history = player.get_dialogue_history("npc1")
        assert len(history) == 2
        assert history[0]["role"] == "player"
        assert history[1]["content"] == "Hi there!"

    def test_player_interaction_range(self):
        player = Player(position=Vec3(0, 0, 0), interaction_range=2.0)
        close_npc = NPC(position=Vec3(1, 0, 0))
        far_npc = NPC(position=Vec3(5, 0, 0))

        assert player.can_interact_with(close_npc)
        assert not player.can_interact_with(far_npc)


class TestNPC:
    """Test NPC class."""

    def test_npc_creation(self):
        npc = NPC(name="Guard", personality="Stern and vigilant")
        assert npc.name == "Guard"
        assert npc.personality == "Stern and vigilant"

    def test_npc_disposition(self):
        npc = NPC()

        assert npc.get_disposition("player") == 0.0

        npc.set_disposition("player", 0.5)
        assert npc.get_disposition("player") == 0.5

        npc.adjust_disposition("player", 0.3)
        assert npc.get_disposition("player") == 0.8

        # Test clamping
        npc.adjust_disposition("player", 0.5)
        assert npc.get_disposition("player") == 1.0

    def test_npc_memory(self):
        npc = NPC()
        npc.add_memory({"event": "met_player", "location": "village"})
        assert len(npc.memory) == 1

    def test_npc_can_talk(self):
        npc = NPC(position=Vec3(0, 0, 0), dialogue_range=3.0)

        assert npc.can_talk(Vec3(2, 0, 0))
        assert not npc.can_talk(Vec3(5, 0, 0))


class TestProp:
    """Test Prop class."""

    def test_prop_creation(self):
        prop = Prop(prop_type="chest", interactable=True)
        assert prop.prop_type == "chest"
        assert prop.interactable

    def test_prop_state(self):
        prop = Prop(prop_type="door", state={"open": False})
        assert prop.state["open"] is False

        prop.state["open"] = True
        assert prop.state["open"] is True


# =============================================================================
# Inventory Tests
# =============================================================================

class TestInventory:
    """Test Inventory class."""

    def test_inventory_creation(self):
        inv = Inventory()
        assert len(inv.items) == 0

    def test_add_items(self):
        inv = Inventory(capacity=100)

        added = inv.add_item("gold", 50)
        assert added == 50
        assert inv.get_count("gold") == 50

    def test_remove_items(self):
        inv = Inventory()
        inv.add_item("potion", 5)

        removed = inv.remove_item("potion", 2)
        assert removed == 2
        assert inv.get_count("potion") == 3

        # Try to remove more than available
        removed = inv.remove_item("potion", 10)
        assert removed == 3
        assert inv.get_count("potion") == 0

    def test_has_item(self):
        inv = Inventory()
        inv.add_item("sword", 1)

        assert inv.has_item("sword")
        assert inv.has_item("sword", 1)
        assert not inv.has_item("sword", 2)
        assert not inv.has_item("shield")

    def test_capacity_limit(self):
        inv = Inventory(capacity=10)
        inv.add_item("item1", 5)
        added = inv.add_item("item2", 10)

        assert added == 5  # Only 5 slots available
        assert inv.get_count("item2") == 5

    def test_inventory_serialization(self):
        inv = Inventory(capacity=200)
        inv.add_item("gold", 100)
        inv.add_item("potion", 5)

        data = inv.to_dict()
        restored = Inventory.from_dict(data)

        assert restored.capacity == 200
        assert restored.get_count("gold") == 100
        assert restored.get_count("potion") == 5


class TestItemDefinition:
    """Test ItemDefinition class."""

    def test_item_definition(self):
        item = ItemDefinition(
            item_id="health_potion",
            name="Health Potion",
            description="Restores 50 HP",
            item_type="consumable",
            value=25,
            properties={"heal_amount": 50},
        )

        assert item.item_id == "health_potion"
        assert item.properties["heal_amount"] == 50


# =============================================================================
# Quest Tests
# =============================================================================

class TestQuestObjective:
    """Test QuestObjective class."""

    def test_objective_progress(self):
        obj = QuestObjective(
            objective_id="collect_ore",
            description="Collect iron ore",
            objective_type=ObjectiveType.COLLECT,
            target="iron_ore",
            required_count=5,
        )

        assert not obj.is_complete()

        obj.update_progress(3)
        assert obj.current_count == 3
        assert not obj.is_complete()

        just_completed = obj.update_progress(2)
        assert obj.is_complete()
        assert just_completed

    def test_objective_serialization(self):
        obj = QuestObjective(
            objective_id="talk_smith",
            description="Talk to the blacksmith",
            objective_type=ObjectiveType.TALK,
            target="blacksmith",
        )
        obj.update_progress(1)

        data = obj.to_dict()
        restored = QuestObjective.from_dict(data)

        assert restored.objective_id == "talk_smith"
        assert restored.objective_type == ObjectiveType.TALK
        assert restored.is_complete()


class TestQuest:
    """Test Quest class."""

    def test_quest_creation(self):
        quest = Quest(
            quest_id="find_sword",
            title="The Lost Sword",
            description="Find the ancient sword",
            giver_npc_id="blacksmith",
            objectives=[
                QuestObjective(
                    objective_id="obj1",
                    description="Find the sword",
                    objective_type=ObjectiveType.COLLECT,
                    target="ancient_sword",
                ),
            ],
            rewards={"gold": 100},
        )

        assert quest.quest_id == "find_sword"
        assert not quest.is_complete()

    def test_quest_completion(self):
        quest = Quest(
            quest_id="test",
            title="Test Quest",
            description="",
            giver_npc_id="npc",
            objectives=[
                QuestObjective(
                    objective_id="obj1",
                    description="Required",
                    objective_type=ObjectiveType.COLLECT,
                    target="item",
                    required_count=1,
                ),
                QuestObjective(
                    objective_id="obj2",
                    description="Optional",
                    objective_type=ObjectiveType.COLLECT,
                    target="bonus",
                    optional=True,
                ),
            ],
        )

        assert not quest.is_complete()

        quest.objectives[0].update_progress(1)
        assert quest.is_complete()  # Optional doesn't matter

    def test_quest_progress(self):
        quest = Quest(
            quest_id="test",
            title="Test",
            description="",
            giver_npc_id="npc",
            objectives=[
                QuestObjective("o1", "", ObjectiveType.COLLECT, "a"),
                QuestObjective("o2", "", ObjectiveType.COLLECT, "b"),
            ],
        )

        completed, total = quest.get_progress()
        assert completed == 0
        assert total == 2


# =============================================================================
# Dialogue Tests
# =============================================================================

class TestDialogueResponse:
    """Test DialogueResponse class."""

    def test_dialogue_response(self):
        response = DialogueResponse(
            text="Hello, traveler!",
            emotion="friendly",
            actions=[{"type": "give_item", "item": "map"}],
        )

        assert response.text == "Hello, traveler!"
        assert response.emotion == "friendly"
        assert len(response.actions) == 1

    def test_response_serialization(self):
        response = DialogueResponse(
            text="Farewell",
            ends_conversation=True,
        )

        data = response.to_dict()
        restored = DialogueResponse.from_dict(data)

        assert restored.text == "Farewell"
        assert restored.ends_conversation


# =============================================================================
# Agent Tests
# =============================================================================

class TestLocalAgent:
    """Test LocalAgent class."""

    def test_agent_dialogue(self):
        agent = LocalAgent()

        context = DialogueContext(
            npc_id="npc1",
            npc_name="Guard",
            npc_personality="Stern",
            npc_behavior="guard",
            npc_current_quest=None,
            relationship_to_player=0.0,
            player_name="Hero",
            player_active_quests=[],
            player_inventory_summary=[],
            conversation_history=[],
            world_context={"time_of_day": "morning"},
            player_message="Hello!",
        )

        response = agent.get_dialogue_response(context)
        assert response.text is not None
        assert len(response.text) > 0

    def test_agent_farewell(self):
        agent = LocalAgent()

        context = DialogueContext(
            npc_id="npc1",
            npc_name="Smith",
            npc_personality="Friendly",
            npc_behavior="merchant",
            npc_current_quest=None,
            relationship_to_player=0.5,
            player_name="Hero",
            player_active_quests=[],
            player_inventory_summary=[],
            conversation_history=[],
            world_context={},
            player_message="Goodbye!",
        )

        response = agent.get_dialogue_response(context)
        assert response.ends_conversation

    def test_agent_action(self):
        agent = LocalAgent()
        npc = NPC(behavior="idle")
        world = GameWorld()

        action = agent.get_next_action(npc, world)
        assert action is not None
        assert action["type"] == "idle"


# =============================================================================
# GameWorld Tests
# =============================================================================

class TestGameWorld:
    """Test GameWorld class."""

    def test_world_creation(self):
        world = GameWorld()
        assert world.frame == 0

    def test_spawn_entity(self):
        world = GameWorld()
        entity = Entity(entity_id="test")

        entity_id = world.spawn_entity(entity)
        assert entity_id == "test"
        assert world.get_entity("test") is entity

    def test_destroy_entity(self):
        world = GameWorld()
        entity = Entity(entity_id="temp")
        world.spawn_entity(entity)

        assert world.destroy_entity("temp")
        assert world.get_entity("temp") is None

    def test_create_player(self):
        world = GameWorld()
        player = world.create_player(name="Hero", position=Vec3(0, 5, 0))

        assert player.name == "Hero"
        assert world.get_player() is player
        assert world.get_entity("player") is player

    def test_get_entities_by_type(self):
        world = GameWorld()
        world.spawn_entity(NPC(entity_id="npc1", name="Guard"))
        world.spawn_entity(NPC(entity_id="npc2", name="Smith"))
        world.spawn_entity(Prop(entity_id="prop1", prop_type="rock"))

        npcs = world.get_entities_by_type(NPC)
        assert len(npcs) == 2

    def test_get_entities_in_range(self):
        world = GameWorld()
        world.spawn_entity(Entity(entity_id="e1", position=Vec3(0, 0, 0)))
        world.spawn_entity(Entity(entity_id="e2", position=Vec3(1, 0, 0)))
        world.spawn_entity(Entity(entity_id="e3", position=Vec3(10, 0, 0)))

        nearby = world.get_entities_in_range(Vec3(0, 0, 0), 5.0)
        assert len(nearby) == 2

    def test_quest_management(self):
        world = GameWorld()
        player = world.create_player()

        quest = Quest(
            quest_id="q1",
            title="Test Quest",
            description="A test",
            giver_npc_id="npc",
            objectives=[
                QuestObjective("o1", "Do thing", ObjectiveType.TALK, "npc"),
            ],
            rewards={"gold": 50},
            state=QuestState.AVAILABLE,
        )
        world.register_quest(quest)

        # Start quest
        assert world.start_quest("q1")
        assert "q1" in player.active_quests
        assert quest.state == QuestState.ACTIVE

        # Update objective
        world.update_quest_objective("q1", "o1")
        assert quest.objectives[0].is_complete()

        # Register gold item for reward
        world.register_item_definition(ItemDefinition("gold", "Gold"))

        # Complete quest
        assert world.complete_quest("q1")
        assert "q1" in player.completed_quests
        assert player.inventory.get_count("gold") == 50

    def test_dialogue_flow(self):
        world = GameWorld()
        player = world.create_player(position=Vec3(0, 0, 0))
        npc = NPC(
            entity_id="smith",
            name="Smith",
            position=Vec3(1, 0, 0),
            dialogue_range=3.0,
            behavior="merchant",
        )
        world.spawn_entity(npc)

        # Initiate dialogue
        assert world.initiate_dialogue("smith")
        assert player.current_interaction_target == "smith"

        # Process dialogue
        response = world.process_player_dialogue("smith", "Hello!")
        assert response is not None
        assert response.text is not None

        # End dialogue
        world.end_dialogue("smith")
        assert player.current_interaction_target is None

    def test_physics_integration(self):
        world = GameWorld(GameConfig(gravity=-9.8))
        player = world.create_player(position=Vec3(5, 10, 5))

        # Create flat terrain
        heights = np.zeros((20, 20), dtype=np.float32)
        heightfield = HeightField2D(heights=heights, cell_size=1.0)
        world.set_heightfield(heightfield)

        # Run physics for several steps (5 seconds to ensure settled)
        for _ in range(300):
            world.physics_step()

        # Player should have fallen close to ground
        # With player radius 0.4, grounded position is y=0.4
        assert player.position.y < 10  # Definitely fallen
        assert player.position.y < 2.0  # Close to ground (may bounce a bit)

    def test_game_step(self):
        world = GameWorld()
        world.create_player()

        initial_frame = world.frame
        world.step(1/60)

        assert world.frame == initial_frame + 1
        assert world.time > 0

    def test_pause(self):
        world = GameWorld()
        world.create_player()

        world.paused = True
        initial_frame = world.frame
        world.step(1/60)

        assert world.frame == initial_frame  # Didn't advance

    def test_flags(self):
        world = GameWorld()

        world.set_flag("story_started", True)
        world.set_flag("boss_defeated", False)

        assert world.get_flag("story_started") is True
        assert world.get_flag("boss_defeated") is False
        assert world.get_flag("nonexistent") is None


class TestGameWorldSaveLoad:
    """Test save/load functionality."""

    def test_save_and_load_dict(self):
        # Create world with entities
        world1 = GameWorld(GameConfig(seed=12345))
        player = world1.create_player(name="TestHero", position=Vec3(10, 5, 10))
        player.inventory.add_item("gold", 100)
        player.active_quests.append("main_quest")

        npc = NPC(entity_id="npc1", name="Guard", position=Vec3(15, 0, 15))
        npc.set_disposition("player", 0.7)
        world1.spawn_entity(npc)

        quest = Quest(
            quest_id="main_quest",
            title="Main Quest",
            description="The main storyline",
            giver_npc_id="npc1",
            state=QuestState.ACTIVE,
        )
        world1.register_quest(quest)

        world1.set_flag("intro_complete", True)

        # Step the world
        for _ in range(10):
            world1.step(1/60)

        # Save
        save_data = world1.save_to_dict()

        # Create new world and load
        world2 = GameWorld()
        world2.load_from_dict(save_data)

        # Verify
        assert world2.config.seed == 12345
        assert world2.frame == 10

        player2 = world2.get_player()
        assert player2.name == "TestHero"
        assert player2.inventory.get_count("gold") == 100
        assert "main_quest" in player2.active_quests

        npc2 = world2.get_entity("npc1")
        assert isinstance(npc2, NPC)
        assert npc2.name == "Guard"
        assert npc2.get_disposition("player") == 0.7

        quest2 = world2.get_quest("main_quest")
        assert quest2.state == QuestState.ACTIVE

        assert world2.get_flag("intro_complete") is True

    def test_save_and_load_file(self):
        world = GameWorld()
        world.create_player(name="FileTest")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = Path(f.name)

        try:
            world.save_to_file(path)

            world2 = GameWorld()
            world2.load_from_file(path)

            assert world2.get_player().name == "FileTest"
        finally:
            path.unlink()


class TestEventIntegration:
    """Test event emission during gameplay."""

    def test_entity_spawn_event(self):
        world = GameWorld()
        events = []

        world.events.subscribe(EventType.NPC_SPAWNED, lambda e: events.append(e))
        world.spawn_entity(NPC(entity_id="test_npc", name="Test"))

        assert len(events) == 1
        assert events[0].data["npc_id"] == "test_npc"

    def test_quest_events(self):
        world = GameWorld()
        world.create_player()
        events = []

        world.events.subscribe(EventType.QUEST_STARTED, lambda e: events.append(e))
        world.events.subscribe(EventType.QUEST_COMPLETED, lambda e: events.append(e))

        quest = Quest(
            quest_id="event_test",
            title="Event Test",
            description="",
            giver_npc_id="npc",
            objectives=[QuestObjective("o1", "", ObjectiveType.TALK, "npc")],
            state=QuestState.AVAILABLE,
        )
        world.register_quest(quest)

        world.start_quest("event_test")
        assert any(e.event_type == EventType.QUEST_STARTED for e in events)

        world.update_quest_objective("event_test", "o1")
        world.complete_quest("event_test")
        assert any(e.event_type == EventType.QUEST_COMPLETED for e in events)

    def test_item_acquired_event(self):
        world = GameWorld()
        player = world.create_player()
        npc = NPC(entity_id="giver", position=Vec3(1, 0, 0))
        world.spawn_entity(npc)
        events = []

        world.events.subscribe(EventType.ITEM_ACQUIRED, lambda e: events.append(e))

        # Simulate dialogue action giving item
        world._execute_action(
            {"type": "give_item", "item": "potion", "count": 3},
            "giver",
        )

        assert len(events) == 1
        assert events[0].data["item_id"] == "potion"
        assert player.inventory.get_count("potion") == 3


# =============================================================================
# Integration Tests
# =============================================================================

class TestGameplayScenario:
    """Integration tests for typical gameplay scenarios."""

    def test_simple_quest_playthrough(self):
        """Test a complete simple quest from start to finish."""
        world = GameWorld()
        player = world.create_player(name="Hero", position=Vec3(0, 0, 0))
        player.inventory.capacity = 1000  # Ensure enough capacity for rewards

        # Create quest-giver NPC
        blacksmith = NPC(
            entity_id="blacksmith",
            name="Grom the Smith",
            personality="Gruff but kind-hearted",
            position=Vec3(5, 0, 5),
            behavior="quest_giver",
            current_quest="find_ore",
        )
        world.spawn_entity(blacksmith)

        # Define quest
        quest = Quest(
            quest_id="find_ore",
            title="Find Rare Ore",
            description="The blacksmith needs iron ore for his work.",
            giver_npc_id="blacksmith",
            objectives=[
                QuestObjective(
                    objective_id="collect_ore",
                    description="Collect 5 iron ore",
                    objective_type=ObjectiveType.COLLECT,
                    target="iron_ore",
                    required_count=5,
                ),
            ],
            rewards={"gold": 100},
            state=QuestState.AVAILABLE,
        )
        world.register_quest(quest)
        world.register_item_definition(ItemDefinition("iron_ore", "Iron Ore"))
        world.register_item_definition(ItemDefinition("gold", "Gold"))

        # Start quest
        assert world.start_quest("find_ore")
        assert "find_ore" in player.active_quests

        # Simulate collecting ore
        for i in range(5):
            player.inventory.add_item("iron_ore", 1)
            world.update_quest_objective("find_ore", "collect_ore")

        # Quest should be completable
        assert quest.is_complete()

        # Complete quest
        assert world.complete_quest("find_ore")
        assert "find_ore" in player.completed_quests
        assert player.inventory.get_count("gold") == 100

    def test_npc_dialogue_with_disposition(self):
        """Test that disposition affects dialogue."""
        world = GameWorld()
        player = world.create_player()

        friendly_npc = NPC(
            entity_id="friend",
            name="Friend",
            position=Vec3(1, 0, 0),
            behavior="idle",
        )
        friendly_npc.set_disposition("player", 0.8)
        world.spawn_entity(friendly_npc)

        hostile_npc = NPC(
            entity_id="enemy",
            name="Enemy",
            position=Vec3(2, 0, 0),
            behavior="idle",
        )
        hostile_npc.set_disposition("player", -0.8)
        world.spawn_entity(hostile_npc)

        # Talk to both
        world.initiate_dialogue("friend")
        response1 = world.process_player_dialogue("friend", "Hello!")
        world.end_dialogue("friend")

        world.initiate_dialogue("enemy")
        response2 = world.process_player_dialogue("enemy", "Hello!")
        world.end_dialogue("enemy")

        # Both should have responses
        assert response1 is not None
        assert response2 is not None

        # Friendly should have friendly emotion
        assert response1.emotion == "friendly"


# =============================================================================
# Behavior Tree Integration Tests
# =============================================================================

class TestBehaviorTreeIntegration:
    """Test integration between behavior trees and game entities."""

    def test_npc_gets_behavior_tree_on_spawn(self):
        """NPCs should get a behavior tree assigned on spawn."""
        world = GameWorld()

        npc = NPC(
            entity_id="patrol_guard",
            name="Guard",
            position=Vec3(0, 0, 0),
            behavior="patrol",
        )
        world.spawn_entity(npc)

        # NPC should have a behavior tree assigned
        assert npc.get_behavior_tree() is not None

    def test_idle_npc_behavior_tree(self):
        """Idle NPCs should get an idle behavior tree."""
        world = GameWorld()

        npc = NPC(
            entity_id="idle_npc",
            name="Idle NPC",
            behavior="idle",
        )
        world.spawn_entity(npc)

        tree = npc.get_behavior_tree()
        assert tree is not None

    def test_guard_npc_behavior_tree(self):
        """Guard NPCs should get a guard behavior tree."""
        world = GameWorld()

        npc = NPC(
            entity_id="guard_npc",
            name="Guard",
            behavior="guard",
            behavior_params={"alert_range": 10.0},
        )
        world.spawn_entity(npc)

        tree = npc.get_behavior_tree()
        assert tree is not None

    def test_merchant_npc_behavior_tree(self):
        """Merchant NPCs should get a merchant behavior tree."""
        world = GameWorld()

        npc = NPC(
            entity_id="merchant_npc",
            name="Merchant",
            behavior="merchant",
            is_merchant=True,
        )
        world.spawn_entity(npc)

        tree = npc.get_behavior_tree()
        assert tree is not None

    def test_manual_behavior_tree_set(self):
        """Manual behavior tree assignment should work."""
        from behavior_tree import create_idle_behavior

        npc = NPC(
            entity_id="test_npc",
            name="Test NPC",
        )

        custom_tree = create_idle_behavior(wait_min=1.0, wait_max=2.0)
        npc.set_behavior_tree(custom_tree)

        assert npc.get_behavior_tree() is custom_tree

    def test_behavior_tree_tick(self):
        """Ticking behavior tree should not error."""
        from behavior_tree import NodeStatus

        world = GameWorld()

        npc = NPC(
            entity_id="tick_npc",
            name="Tick NPC",
            behavior="idle",
        )
        world.spawn_entity(npc)

        # Tick behavior should return a status
        status = npc.tick_behavior(world, dt=1.0/60.0)
        assert status in (NodeStatus.SUCCESS, NodeStatus.FAILURE, NodeStatus.RUNNING)

    def test_game_step_ticks_behavior_trees(self):
        """Game step should tick NPC behavior trees."""
        world = GameWorld()
        world.create_player()

        npc = NPC(
            entity_id="step_npc",
            name="Step NPC",
            behavior="idle",
        )
        world.spawn_entity(npc)

        # Running step should not error
        for _ in range(10):
            world.step(dt=1.0/60.0)

    def test_patrol_behavior_moves_npc(self):
        """Patrol behavior should move NPC toward waypoints."""
        world = GameWorld()

        # Create NPC with patrol behavior and custom waypoints
        start_pos = Vec3(0, 0, 0)
        waypoints = [
            Vec3(10, 0, 0),
            Vec3(10, 0, 10),
            Vec3(0, 0, 10),
            Vec3(0, 0, 0),
        ]

        npc = NPC(
            entity_id="patrol_npc",
            name="Patrol NPC",
            position=start_pos,
            behavior="patrol",
            behavior_params={"waypoints": waypoints, "patrol_speed": 5.0},
        )
        world.spawn_entity(npc)

        # Simulate several seconds of patrol
        dt = 1.0/60.0
        for _ in range(120):  # 2 seconds
            npc.tick_behavior(world, dt)

        # NPC should have moved from start position
        distance_moved = (npc.position - start_pos).length()
        assert distance_moved > 1.0  # Should have moved at least 1 meter
