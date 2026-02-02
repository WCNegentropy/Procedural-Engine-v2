"""Tests for ui_system module."""
import pytest

from procengine.game.ui_system import (
    UIManager,
    HeadlessUIBackend,
    HUD,
    DialogueBox,
    InventoryPanel,
    QuestLog,
    PauseMenu,
    DebugOverlay,
)
from procengine.game.player_controller import InteractionTarget
from procengine.physics import Vec3


# =============================================================================
# Mock Objects for Testing
# =============================================================================


class MockPlayer:
    """Mock player for UI testing."""

    def __init__(self):
        self.health = 80
        self.max_health = 100
        self.position = Vec3(10, 5, 20)
        self.active_quests = []
        self.completed_quests = []
        self.current_interaction_target = None
        self.inventory = MockInventory()


class MockInventory:
    """Mock inventory for UI testing."""

    def __init__(self):
        self._items = {"sword": 1, "potion": 5, "gold": 100}

    def get_all_items(self):
        return self._items.copy()


class MockNPC:
    """Mock NPC for UI testing."""

    def __init__(self, entity_id="npc1", name="Test NPC"):
        self.entity_id = entity_id
        self.name = name


class MockQuest:
    """Mock quest for UI testing."""

    def __init__(self, quest_id="quest1", title="Test Quest"):
        self.quest_id = quest_id
        self.title = title
        self.objectives = [MockObjective()]

    def get_progress(self):
        return (1, 2)


class MockObjective:
    """Mock objective for UI testing."""

    def __init__(self, description="Kill 10 rats", current=5, required=10):
        self.description = description
        self.current_count = current
        self.required_count = required

    def is_complete(self):
        return self.current_count >= self.required_count


# =============================================================================
# HeadlessUIBackend Tests
# =============================================================================


class TestHeadlessUIBackend:
    """Tests for HeadlessUIBackend."""

    def test_records_calls(self):
        """Test that calls are recorded."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        backend.text("Hello World")
        backend.end_frame()

        calls = backend.get_calls()
        assert len(calls) == 1
        assert calls[0]["type"] == "text"
        assert calls[0]["text"] == "Hello World"

    def test_window_calls(self):
        """Test window begin/end calls are recorded."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        backend.begin_window("Test Window", 0, 0, 100, 100)
        backend.text("Content")
        backend.end_window()
        backend.end_frame()

        assert backend.has_window("Test Window")

    def test_button_response(self):
        """Test button response simulation."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        result1 = backend.button("Click Me")
        backend.end_frame()

        assert result1 is False  # Default is not clicked

        # Set up simulated click
        backend.set_button_response("Click Me", True)

        backend.begin_frame()
        result2 = backend.button("Click Me")
        backend.end_frame()

        assert result2 is True

    def test_text_search(self):
        """Test text search functionality."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        backend.text("Hello World")
        backend.text_colored("Important Message", 1, 0, 0)
        backend.end_frame()

        assert backend.has_text("Hello")
        assert backend.has_text("Important")
        assert not backend.has_text("Nonexistent")

    def test_find_calls(self):
        """Test finding calls by type."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        backend.button("Button 1")
        backend.text("Some text")
        backend.button("Button 2")
        backend.end_frame()

        button_calls = backend.find_calls("button")
        assert len(button_calls) == 2

    def test_clear_calls(self):
        """Test clearing recorded calls."""
        backend = HeadlessUIBackend()

        backend.begin_frame()
        backend.text("Test")
        backend.end_frame()

        assert len(backend.get_calls()) > 0

        backend.clear_calls()
        assert len(backend.get_calls()) == 0


# =============================================================================
# HUD Tests
# =============================================================================


class TestHUD:
    """Tests for HUD component."""

    def test_renders_health_bar(self):
        """Test health bar is rendered."""
        backend = HeadlessUIBackend()
        hud = HUD(backend, 1920, 1080)

        player = MockPlayer()

        backend.begin_frame()
        hud.render(player=player)
        backend.end_frame()

        # Should have health window
        assert backend.has_window("##HealthBar")
        assert backend.has_text("Health:")

    def test_renders_quest_tracker(self):
        """Test quest tracker is rendered when quests active."""
        backend = HeadlessUIBackend()
        hud = HUD(backend, 1920, 1080)

        player = MockPlayer()
        quests = [MockQuest()]

        backend.begin_frame()
        hud.render(player=player, active_quests=quests)
        backend.end_frame()

        assert backend.has_window("Quest Tracker")
        assert backend.has_text("Test Quest")

    def test_renders_interaction_prompt(self):
        """Test interaction prompt is shown."""
        backend = HeadlessUIBackend()
        hud = HUD(backend, 1920, 1080)

        player = MockPlayer()
        
        # Create an InteractionTarget for the prompt
        target = InteractionTarget(
            entity_id="npc_elder",
            entity_name="Village Elder",
            entity_type="npc",
            action_text="Talk to",
            distance=2.5,
        )

        backend.begin_frame()
        hud.render(player=player, interaction_target=target)
        backend.end_frame()

        assert backend.has_text("Talk to Village Elder")

    def test_visibility_toggle(self):
        """Test HUD can be hidden."""
        backend = HeadlessUIBackend()
        hud = HUD(backend, 1920, 1080)

        player = MockPlayer()
        hud.visible = False

        backend.begin_frame()
        hud.render(player=player)
        backend.end_frame()

        # Should not render anything when hidden
        assert len(backend.get_calls()) == 0


# =============================================================================
# DialogueBox Tests
# =============================================================================


class TestDialogueBox:
    """Tests for DialogueBox component."""

    def test_renders_dialogue(self):
        """Test dialogue renders correctly."""
        backend = HeadlessUIBackend()
        dialogue = DialogueBox(backend, 1920, 1080)

        npc = MockNPC(name="Wise Elder")
        dialogue.set_dialogue(npc, "Greetings, traveler!", None)

        backend.begin_frame()
        dialogue.render()
        backend.end_frame()

        assert backend.has_window("Dialogue")
        assert backend.has_text("Wise Elder")
        assert backend.has_text("Greetings, traveler!")

    def test_renders_options(self):
        """Test dialogue options render."""
        backend = HeadlessUIBackend()
        dialogue = DialogueBox(backend, 1920, 1080)

        npc = MockNPC()
        options = [
            {"label": "Tell me more"},
            {"label": "Goodbye"},
        ]
        dialogue.set_dialogue(npc, "What would you like to know?", options)

        backend.begin_frame()
        dialogue.render()
        backend.end_frame()

        assert backend.has_text("[1] Tell me more")
        assert backend.has_text("[2] Goodbye")

    def test_option_selection_callback(self):
        """Test option selection triggers callback."""
        backend = HeadlessUIBackend()
        dialogue = DialogueBox(backend, 1920, 1080)

        selected = [None]

        def on_option(index):
            selected[0] = index

        dialogue._on_option_selected = on_option

        npc = MockNPC()
        options = [{"label": "Option 1"}, {"label": "Option 2"}]
        dialogue.set_dialogue(npc, "Choose:", options)

        dialogue.select_option(1)
        assert selected[0] == 1

    def test_clear_dialogue(self):
        """Test dialogue can be cleared."""
        backend = HeadlessUIBackend()
        dialogue = DialogueBox(backend, 1920, 1080)

        npc = MockNPC()
        dialogue.set_dialogue(npc, "Hello", None)
        dialogue.clear()

        backend.begin_frame()
        dialogue.render()
        backend.end_frame()

        # Should not render when cleared
        assert not backend.has_window("Dialogue")


# =============================================================================
# InventoryPanel Tests
# =============================================================================


class TestInventoryPanel:
    """Tests for InventoryPanel component."""

    def test_renders_items(self):
        """Test inventory items are rendered."""
        backend = HeadlessUIBackend()
        inventory = InventoryPanel(backend, 1920, 1080)

        player = MockPlayer()

        backend.begin_frame()
        inventory.render(player=player)
        backend.end_frame()

        assert backend.has_window("Inventory")
        assert backend.has_text("sword")
        assert backend.has_text("potion")
        assert backend.has_text("gold")

    def test_renders_empty_inventory(self):
        """Test empty inventory message."""
        backend = HeadlessUIBackend()
        inventory = InventoryPanel(backend, 1920, 1080)

        player = MockPlayer()
        player.inventory._items = {}

        backend.begin_frame()
        inventory.render(player=player)
        backend.end_frame()

        assert backend.has_text("Empty")

    def test_item_definitions_display(self):
        """Test item definitions are used for display names."""
        backend = HeadlessUIBackend()
        inventory = InventoryPanel(backend, 1920, 1080)

        inventory.set_item_definitions({
            "sword": {"name": "Iron Sword"},
            "potion": {"name": "Health Potion"},
        })

        player = MockPlayer()

        backend.begin_frame()
        inventory.render(player=player)
        backend.end_frame()

        assert backend.has_text("Iron Sword")
        assert backend.has_text("Health Potion")

    def test_action_buttons(self):
        """Test action buttons are rendered."""
        backend = HeadlessUIBackend()
        inventory = InventoryPanel(backend, 1920, 1080)

        player = MockPlayer()

        backend.begin_frame()
        inventory.render(player=player)
        backend.end_frame()

        button_calls = backend.find_calls("button")
        button_labels = [c["label"] for c in button_calls]

        assert "Use" in button_labels
        assert "Drop" in button_labels
        assert "Close" in button_labels


# =============================================================================
# QuestLog Tests
# =============================================================================


class TestQuestLog:
    """Tests for QuestLog component."""

    def test_renders_active_quests(self):
        """Test active quests are rendered."""
        backend = HeadlessUIBackend()
        quest_log = QuestLog(backend, 1920, 1080)

        quests = [MockQuest(title="Main Quest"), MockQuest(title="Side Quest")]

        backend.begin_frame()
        quest_log.render(active_quests=quests)
        backend.end_frame()

        assert backend.has_window("Quest Log")
        assert backend.has_text("Active Quests")
        assert backend.has_text("Main Quest")
        assert backend.has_text("Side Quest")

    def test_renders_completed_quests(self):
        """Test completed quests are rendered."""
        backend = HeadlessUIBackend()
        quest_log = QuestLog(backend, 1920, 1080)

        completed = [MockQuest(title="Old Quest")]

        backend.begin_frame()
        quest_log.render(completed_quests=completed)
        backend.end_frame()

        assert backend.has_text("Completed Quests")
        assert backend.has_text("Old Quest")

    def test_empty_quests_message(self):
        """Test empty quest lists show message."""
        backend = HeadlessUIBackend()
        quest_log = QuestLog(backend, 1920, 1080)

        backend.begin_frame()
        quest_log.render(active_quests=[], completed_quests=[])
        backend.end_frame()

        assert backend.has_text("No active quests")
        assert backend.has_text("No completed quests")


# =============================================================================
# PauseMenu Tests
# =============================================================================


class TestPauseMenu:
    """Tests for PauseMenu component."""

    def test_renders_menu_options(self):
        """Test pause menu options are rendered."""
        backend = HeadlessUIBackend()
        menu = PauseMenu(backend, 1920, 1080)

        backend.begin_frame()
        menu.render()
        backend.end_frame()

        assert backend.has_window("Paused")

        button_calls = backend.find_calls("button")
        button_labels = [c["label"] for c in button_calls]

        assert "Resume" in button_labels
        assert "Save Game" in button_labels
        assert "Load Game" in button_labels
        assert "Settings" in button_labels
        assert "Quit to Desktop" in button_labels

    def test_callback_triggers(self):
        """Test callbacks are triggered on button click."""
        backend = HeadlessUIBackend()
        menu = PauseMenu(backend, 1920, 1080)

        resume_called = [False]
        quit_called = [False]

        menu._on_resume = lambda: resume_called.__setitem__(0, True)
        menu._on_quit = lambda: quit_called.__setitem__(0, True)

        # Simulate resume click
        backend.set_button_response("Resume", True)

        backend.begin_frame()
        menu.render()
        backend.end_frame()

        assert resume_called[0] is True


# =============================================================================
# DebugOverlay Tests
# =============================================================================


class TestDebugOverlay:
    """Tests for DebugOverlay component."""

    def test_renders_stats(self):
        """Test debug stats are rendered."""
        backend = HeadlessUIBackend()
        debug = DebugOverlay(backend, 1920, 1080)

        backend.begin_frame()
        debug.render(
            fps=60.5,
            frame_count=1234,
            player_pos=(10.5, 5.0, 20.3),
            entity_count=42,
        )
        backend.end_frame()

        assert backend.has_window("Debug")
        assert backend.has_text("FPS:")
        assert backend.has_text("Frame:")
        assert backend.has_text("Pos:")
        assert backend.has_text("Entities:")


# =============================================================================
# UIManager Tests
# =============================================================================


class TestUIManager:
    """Tests for UIManager."""

    def test_initialization(self):
        """Test UIManager initializes correctly."""
        ui = UIManager(1920, 1080)

        assert ui.hud is not None
        assert ui.dialogue_box is not None
        assert ui.inventory_panel is not None
        assert ui.quest_log is not None
        assert ui.pause_menu is not None
        assert ui.debug_overlay is not None

    def test_render_hud(self):
        """Test HUD rendering through manager."""
        ui = UIManager(1920, 1080)

        player = MockPlayer()

        ui.begin_frame()
        ui.render_hud(player)
        ui.end_frame()

        assert ui.backend.has_window("##HealthBar")

    def test_dialogue_lifecycle(self):
        """Test dialogue start/update/end through manager."""
        ui = UIManager(1920, 1080)

        npc = MockNPC(name="Elder")

        ui.start_dialogue(npc)
        assert ui._in_dialogue is True

        ui.begin_frame()
        ui.render_dialogue()
        ui.end_frame()

        assert ui.backend.has_text("Elder")

        ui.end_dialogue()
        assert ui._in_dialogue is False

    def test_render_debug(self):
        """Test debug overlay through manager."""
        ui = UIManager(1920, 1080)

        ui.begin_frame()
        ui.render_debug(fps=60.0, frame_count=100)
        ui.end_frame()

        assert ui.backend.has_text("FPS")

    def test_set_callbacks(self):
        """Test callback setting."""
        ui = UIManager(1920, 1080)

        called = {"resume": False, "save": False}

        ui.set_pause_callbacks(
            on_resume=lambda: called.__setitem__("resume", True),
            on_save=lambda: called.__setitem__("save", True),
        )

        assert ui.pause_menu._on_resume is not None
        assert ui.pause_menu._on_save is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestUIIntegration:
    """Integration tests for UI system."""

    def test_full_frame_rendering(self):
        """Test rendering a complete UI frame."""
        ui = UIManager(1920, 1080)

        player = MockPlayer()
        player.active_quests = ["quest1"]

        # Simulate full gameplay frame
        ui.begin_frame()
        ui.render_hud(player)
        ui.render_debug(fps=60.0, frame_count=100)
        ui.end_frame()

        calls = ui.backend.get_calls()
        assert len(calls) > 0

    def test_dialogue_with_options_flow(self):
        """Test complete dialogue flow with options."""
        ui = UIManager(1920, 1080)

        npc = MockNPC()
        ui.start_dialogue(npc)

        # Set up dialogue with options
        class MockResponse:
            text = "What do you want?"
            options = [{"label": "Quest"}, {"label": "Trade"}]

        ui.update_dialogue(MockResponse())

        selected = [None]
        ui.set_dialogue_callbacks(
            on_option=lambda i: selected.__setitem__(0, i)
        )

        ui.select_dialogue_option(1)
        assert selected[0] == 1

        ui.end_dialogue()
        assert ui._in_dialogue is False
