"""Tests for ui_system module."""
import pytest

from procengine.game.player_controller import InputManager
from procengine.game.ui_system import (
    UIManager,
    HeadlessUIBackend,
    HUD,
    DialogueBox,
    InventoryPanel,
    QuestLog,
    PauseMenu,
    SettingsPanel,
    DebugOverlay,
    WorldCreationScreen,
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
        assert backend.has_text("HP")

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
# SettingsPanel Tests
# =============================================================================


class TestSettingsPanel:
    """Tests for SettingsPanel component."""

    def test_renders_settings_options(self):
        """Test settings panel options are rendered."""
        backend = HeadlessUIBackend()
        panel = SettingsPanel(backend, 1920, 1080)

        backend.begin_frame()
        panel.render(debug_enabled=True, vsync_enabled=False)
        backend.end_frame()

        assert backend.has_window("Settings")
        assert backend.has_text("Debug Overlay:")
        assert backend.has_text("VSync:")

    def test_back_button_callback(self):
        """Test back button triggers close callback."""
        backend = HeadlessUIBackend()
        panel = SettingsPanel(backend, 1920, 1080)

        closed = [False]
        panel.set_callbacks(on_close=lambda: closed.__setitem__(0, True))
        backend.set_button_response("Back", True)

        backend.begin_frame()
        panel.render()
        backend.end_frame()

        assert closed[0] is True

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

    def test_renders_grounded_state(self):
        """Test grounded state is rendered."""
        backend = HeadlessUIBackend()
        debug = DebugOverlay(backend, 1920, 1080)

        # Test grounded
        backend.begin_frame()
        debug.render(fps=60.0, grounded=True)
        backend.end_frame()

        assert backend.has_text("Grounded")

        # Test airborne
        backend.clear_calls()
        backend.begin_frame()
        debug.render(fps=60.0, grounded=False)
        backend.end_frame()

        assert backend.has_text("Airborne")

    def test_renders_interaction_target(self):
        """Test interaction target is shown in debug."""
        backend = HeadlessUIBackend()
        debug = DebugOverlay(backend, 1920, 1080)

        backend.begin_frame()
        debug.render(
            fps=60.0,
            interaction_target="Village Elder",
        )
        backend.end_frame()

        assert backend.has_text("Target: Village Elder")

    def test_reset_world_button_callback(self):
        """Test Reset World button triggers callback."""
        backend = HeadlessUIBackend()
        debug = DebugOverlay(backend, 1920, 1080)

        reset_called = [False]
        debug.set_callbacks(on_reset_world=lambda: reset_called.__setitem__(0, True))

        # Simulate button click
        backend.set_button_response("Reset World", True)

        backend.begin_frame()
        debug.render(fps=60.0)
        backend.end_frame()

        assert reset_called[0] is True

    def test_fps_color_coding(self):
        """Test FPS is color-coded based on performance."""
        backend = HeadlessUIBackend()
        debug = DebugOverlay(backend, 1920, 1080)

        # Good FPS (should be green)
        backend.begin_frame()
        debug.render(fps=60.0)
        backend.end_frame()

        # Find the FPS text_colored call
        fps_calls = [c for c in backend.get_calls() 
                     if c["type"] == "text_colored" and "FPS:" in str(c.get("text", ""))]
        assert len(fps_calls) > 0
        # Green = high g value
        assert fps_calls[0]["g"] > 0.5


# =============================================================================
# WorldCreationScreen Tests
# =============================================================================


class TestWorldCreationScreen:
    """Tests for WorldCreationScreen component."""

    def test_valid_seed_triggers_start_callback(self):
        """Test a valid seed is passed through unchanged."""
        backend = HeadlessUIBackend()
        screen = WorldCreationScreen(backend, 1920, 1080)

        started = []
        screen._on_start = started.append

        backend.set_input_text_value("##seed", "123456789")
        backend.set_button_response("Generate World", True)

        backend.begin_frame()
        screen.render()
        backend.end_frame()

        assert started == [123456789]
        assert screen.seed_text == "123456789"
        assert not backend.has_text("Seeds must use digits 0-9 only.")

    def test_invalid_seed_shows_error_and_blocks_start(self):
        """Test invalid seed text does not start world generation."""
        backend = HeadlessUIBackend()
        screen = WorldCreationScreen(backend, 1920, 1080)

        started = []
        screen._on_start = started.append

        backend.set_input_text_value("##seed", "not-a-number")
        backend.set_button_response("Generate World", True)

        backend.begin_frame()
        screen.render()
        backend.end_frame()

        assert started == []
        assert backend.has_text("Seeds must use digits 0-9 only.")

    def test_out_of_range_seed_can_be_corrected_and_retried(self):
        """Test users can retry after fixing an out-of-range seed."""
        backend = HeadlessUIBackend()
        screen = WorldCreationScreen(backend, 1920, 1080)

        started = []
        screen._on_start = started.append

        backend.set_input_text_value("##seed", "18446744073709551616")
        backend.set_button_response("Generate World", True)

        backend.begin_frame()
        screen.render()
        backend.end_frame()

        assert started == []
        assert backend.has_text("Seed must be between 0 and 18446744073709551615.")

        backend.clear_calls()
        backend.set_input_text_value("##seed", "18446744073709551615")

        backend.begin_frame()
        screen.render()
        backend.end_frame()

        assert started == [18446744073709551615]
        assert not backend.has_text("Seed must be between 0 and 18446744073709551615.")

    def test_keyboard_fallback_updates_seed_and_submits(self):
        """Test seed entry works from raw menu key presses."""
        backend = HeadlessUIBackend()
        screen = WorldCreationScreen(backend, 1920, 1080)
        input_manager = InputManager()

        started = []
        screen._on_start = started.append
        screen.seed_text = ""

        input_manager.begin_frame()
        input_manager.on_key_down("1")
        input_manager.on_key_down("2")
        input_manager.on_key_down("3")

        backend.begin_frame()
        screen.render(input_manager=input_manager)
        backend.end_frame()

        assert screen.seed_text == "123"
        assert started == []

        input_manager.on_key_up("1")
        input_manager.on_key_up("2")
        input_manager.on_key_up("3")
        input_manager.begin_frame()
        input_manager.on_key_down("BACKSPACE")

        backend.begin_frame()
        screen.render(input_manager=input_manager)
        backend.end_frame()

        assert screen.seed_text == "12"

        input_manager.on_key_up("BACKSPACE")
        input_manager.begin_frame()
        input_manager.on_key_down("RETURN")

        backend.begin_frame()
        screen.render(input_manager=input_manager)
        backend.end_frame()

        assert started == [12]


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


# =============================================================================
# ImGuiBackend Tests
# =============================================================================


class MockCppModule:
    """Mock procengine_cpp module that records ImGui calls."""

    def __init__(self):
        self.calls = []
        self.input_text_responses = {}

    def _record(self, name, *args, **kwargs):
        self.calls.append({"name": name, "args": args, "kwargs": kwargs})

    def imgui_new_frame(self, dt=1.0 / 60.0, width=0.0, height=0.0, left_down=False, right_down=False):
        self._record("imgui_new_frame", dt, width, height, left_down, right_down)

    def imgui_render(self):
        self._record("imgui_render")

    def imgui_begin(self, title, flags=0):
        self._record("imgui_begin", title, flags)
        return True

    def imgui_end(self):
        self._record("imgui_end")

    def imgui_text(self, text):
        self._record("imgui_text", text)

    def imgui_text_colored(self, text, r, g, b, a=1.0):
        self._record("imgui_text_colored", text, r, g, b, a)

    def imgui_button(self, label, width=0, height=0):
        self._record("imgui_button", label, width, height)
        return False

    def imgui_progress_bar(self, fraction, width=-1, height=0):
        self._record("imgui_progress_bar", fraction, width, height)

    def imgui_separator(self):
        self._record("imgui_separator")

    def imgui_same_line(self):
        self._record("imgui_same_line")

    def imgui_spacing(self):
        self._record("imgui_spacing")

    def imgui_image(self, texture_id, width, height):
        self._record("imgui_image", texture_id, width, height)

    def imgui_begin_child(self, id_str, width=0, height=0, border=False):
        self._record("imgui_begin_child", id_str, width, height, border)
        return True

    def imgui_end_child(self):
        self._record("imgui_end_child")

    def imgui_columns(self, count, border=True):
        self._record("imgui_columns", count, border)

    def imgui_next_column(self):
        self._record("imgui_next_column")

    def imgui_set_cursor_pos(self, x, y):
        self._record("imgui_set_cursor_pos", x, y)

    def imgui_set_next_window_pos(self, x, y):
        self._record("imgui_set_next_window_pos", x, y)

    def imgui_set_next_window_size(self, w, h):
        self._record("imgui_set_next_window_size", w, h)

    def imgui_input_text(self, label, text, buffer_size=256):
        self._record("imgui_input_text", label, text, buffer_size)
        new_text = self.input_text_responses.get(label)
        if new_text is None:
            return False, text
        return True, new_text


class TestImGuiBackend:
    """Tests for ImGuiBackend with mocked C++ module."""

    def _make_backend(self):
        """Create an ImGuiBackend with a mocked C++ module."""
        from procengine.game.ui_system import ImGuiBackend

        mock_cpp = MockCppModule()
        backend = object.__new__(ImGuiBackend)
        backend._cpp = mock_cpp
        return backend, mock_cpp

    def test_begin_end_frame(self):
        """Test frame calls delegate to C++."""
        backend, mock = self._make_backend()

        backend.begin_frame(1.0 / 60.0, 1920, 1080, True, False)
        backend.end_frame()

        names = [c["name"] for c in mock.calls]
        assert "imgui_new_frame" in names
        assert "imgui_render" in names

    def test_window_calls(self):
        """Test window begin/end delegates to C++."""
        backend, mock = self._make_backend()

        result = backend.begin_window("Test", 10, 20, 300, 400, flags=0)
        backend.end_window()

        assert result is True
        names = [c["name"] for c in mock.calls]
        assert "imgui_set_next_window_pos" in names
        assert "imgui_set_next_window_size" in names
        assert "imgui_begin" in names
        assert "imgui_end" in names

    def test_text_calls(self):
        """Test text delegates to C++."""
        backend, mock = self._make_backend()

        backend.text("Hello")
        backend.text_colored("World", 1.0, 0.0, 0.0, 0.5)

        names = [c["name"] for c in mock.calls]
        assert "imgui_text" in names
        assert "imgui_text_colored" in names

        text_call = [c for c in mock.calls if c["name"] == "imgui_text"][0]
        assert text_call["args"] == ("Hello",)

        color_call = [c for c in mock.calls if c["name"] == "imgui_text_colored"][0]
        assert color_call["args"] == ("World", 1.0, 0.0, 0.0, 0.5)

    def test_button_call(self):
        """Test button delegates to C++."""
        backend, mock = self._make_backend()

        result = backend.button("Click Me", 100, 30)

        assert result is False
        btn_call = [c for c in mock.calls if c["name"] == "imgui_button"][0]
        assert btn_call["args"] == ("Click Me", 100, 30)

    def test_progress_bar(self):
        """Test progress bar delegates to C++."""
        backend, mock = self._make_backend()

        backend.progress_bar(0.75, 200, 20)

        bar_call = [c for c in mock.calls if c["name"] == "imgui_progress_bar"][0]
        assert bar_call["args"] == (0.75, 200, 20)

    def test_layout_calls(self):
        """Test layout utility calls."""
        backend, mock = self._make_backend()

        backend.separator()
        backend.same_line()
        backend.spacing()

        names = [c["name"] for c in mock.calls]
        assert "imgui_separator" in names
        assert "imgui_same_line" in names
        assert "imgui_spacing" in names

    def test_child_region(self):
        """Test child region calls."""
        backend, mock = self._make_backend()

        result = backend.begin_child("scroll_area", 200, 300, border=True)
        backend.end_child()

        assert result is True
        names = [c["name"] for c in mock.calls]
        assert "imgui_begin_child" in names
        assert "imgui_end_child" in names

    def test_columns(self):
        """Test column layout calls."""
        backend, mock = self._make_backend()

        backend.columns(3, border=False)
        backend.next_column()

        col_call = [c for c in mock.calls if c["name"] == "imgui_columns"][0]
        assert col_call["args"] == (3, False)
        names = [c["name"] for c in mock.calls]
        assert "imgui_next_column" in names

    def test_cursor_pos(self):
        """Test cursor position call."""
        backend, mock = self._make_backend()

        backend.set_cursor_pos(50, 100)

        pos_call = [c for c in mock.calls if c["name"] == "imgui_set_cursor_pos"][0]
        assert pos_call["args"] == (50, 100)

    def test_image(self):
        """Test image call."""
        backend, mock = self._make_backend()

        backend.image(42, 128, 64)

        img_call = [c for c in mock.calls if c["name"] == "imgui_image"][0]
        assert img_call["args"] == (42, 128, 64)

    def test_input_text(self):
        """Test text input delegates to C++."""
        backend, mock = self._make_backend()
        mock.input_text_responses["##seed"] = "42-edited"

        changed, new_text = backend.input_text("##seed", "42", 64)

        assert changed is True
        assert new_text == "42-edited"
        input_call = [c for c in mock.calls if c["name"] == "imgui_input_text"][0]
        assert input_call["args"] == ("##seed", "42", 64)

    def test_implements_uibackend(self):
        """Test that ImGuiBackend is a valid UIBackend subclass."""
        from procengine.game.ui_system import ImGuiBackend, UIBackend

        assert issubclass(ImGuiBackend, UIBackend)

    def test_works_with_ui_manager(self):
        """Test that UIManager can use ImGuiBackend."""
        backend, mock = self._make_backend()
        ui = UIManager(1920, 1080, backend=backend)

        ui.begin_frame()
        ui.end_frame()

        names = [c["name"] for c in mock.calls]
        assert "imgui_new_frame" in names
        assert "imgui_render" in names
        new_frame_call = [c for c in mock.calls if c["name"] == "imgui_new_frame"][0]
        assert new_frame_call["args"] == (1.0 / 60.0, 1920, 1080, False, False)


# =============================================================================
# ConsoleWindow Tests
# =============================================================================


class TestConsoleWindow:
    """Tests for ConsoleWindow component."""

    def test_renders_console_outputs(self):
        """Test console window renders output lines."""
        from procengine.game.ui_system import ConsoleWindow

        backend = HeadlessUIBackend()
        cw = ConsoleWindow(backend, 1920, 1080)

        render_data = {
            "visible": True,
            "input": "test",
            "cursor_pos": 4,
            "lines": [
                {"text": "Welcome to the console", "color": (1, 1, 1, 1)},
                {"text": "> help", "color": (0.5, 0.7, 1.0, 1.0)},
            ],
            "suggestions": [],
            "config": {},
        }

        backend.begin_frame()
        cw.render(render_data=render_data)
        backend.end_frame()

        assert backend.has_window("Developer Console")
        assert backend.has_text("Welcome to the console")

    def test_not_rendered_when_hidden(self):
        """Test console window not rendered when data says hidden."""
        from procengine.game.ui_system import ConsoleWindow

        backend = HeadlessUIBackend()
        cw = ConsoleWindow(backend, 1920, 1080)

        render_data = {"visible": False}

        backend.begin_frame()
        cw.render(render_data=render_data)
        backend.end_frame()

        assert len(backend.get_calls()) == 0

    def test_renders_input_line(self):
        """Test console renders current input with cursor."""
        from procengine.game.ui_system import ConsoleWindow

        backend = HeadlessUIBackend()
        cw = ConsoleWindow(backend, 1920, 1080)

        render_data = {
            "visible": True,
            "input": "hello",
            "cursor_pos": 5,
            "lines": [],
            "suggestions": [],
            "config": {},
        }

        backend.begin_frame()
        cw.render(render_data=render_data)
        backend.end_frame()

        # Should show prompt and input with cursor
        assert backend.has_text(">")
        assert backend.has_text("hello|")

    def test_renders_suggestions(self):
        """Test console renders autocomplete suggestions."""
        from procengine.game.ui_system import ConsoleWindow

        backend = HeadlessUIBackend()
        cw = ConsoleWindow(backend, 1920, 1080)

        render_data = {
            "visible": True,
            "input": "player",
            "cursor_pos": 6,
            "lines": [],
            "suggestions": ["player.health", "player.pos", "player.use"],
            "suggestion_index": 0,
            "config": {},
        }

        backend.begin_frame()
        cw.render(render_data=render_data)
        backend.end_frame()

        assert backend.has_text("[player.health]")

    def test_renders_inline_preview(self):
        """Test console renders inline autocomplete preview."""
        from procengine.game.ui_system import ConsoleWindow

        backend = HeadlessUIBackend()
        cw = ConsoleWindow(backend, 1920, 1080)

        render_data = {
            "visible": True,
            "input": "player",
            "cursor_pos": 6,
            "lines": [],
            "suggestions": [],
            "inline_preview": ".health",
            "config": {},
        }

        backend.begin_frame()
        cw.render(render_data=render_data)
        backend.end_frame()

        assert backend.has_text(".health")


# =============================================================================
# NotificationStack Tests
# =============================================================================


class TestNotificationStack:
    """Tests for NotificationStack component."""

    def test_renders_notifications(self):
        """Test notification stack renders items."""
        from procengine.game.ui_system import NotificationStack

        backend = HeadlessUIBackend()
        stack = NotificationStack(backend, 1920, 1080)

        notifs = [
            {"text": "Quest started!", "color": (0.3, 0.9, 0.3, 1.0), "opacity": 1.0},
            {"text": "Item acquired", "color": (0.5, 0.7, 1.0, 1.0), "opacity": 0.8},
        ]

        backend.begin_frame()
        stack.render(notifications=notifs)
        backend.end_frame()

        assert backend.has_text("Quest started!")
        assert backend.has_text("Item acquired")

    def test_empty_notifications_no_render(self):
        """Test nothing renders when no notifications."""
        from procengine.game.ui_system import NotificationStack

        backend = HeadlessUIBackend()
        stack = NotificationStack(backend, 1920, 1080)

        backend.begin_frame()
        stack.render(notifications=[])
        backend.end_frame()

        assert len(backend.get_calls()) == 0

    def test_notification_with_icon(self):
        """Test notification with icon prefix."""
        from procengine.game.ui_system import NotificationStack

        backend = HeadlessUIBackend()
        stack = NotificationStack(backend, 1920, 1080)

        notifs = [
            {"text": "Health restored", "icon": "+", "color": (0.3, 0.9, 0.3), "opacity": 1.0},
        ]

        backend.begin_frame()
        stack.render(notifications=notifs)
        backend.end_frame()

        assert backend.has_text("+ Health restored")


# =============================================================================
# UIManager Console Integration Tests
# =============================================================================


class TestUIManagerConsoleIntegration:
    """Tests for UIManager integration with Console."""

    def test_set_console(self):
        """Test setting a console on UIManager."""
        from procengine.commands.console import Console

        ui = UIManager(1920, 1080)
        console = Console()
        ui.set_console(console)

        assert ui._console is console

    def test_render_console_when_visible(self):
        """Test render_console works when console is visible."""
        from procengine.commands.console import Console

        ui = UIManager(1920, 1080)
        console = Console()
        console.open()
        console.print("Test output")
        ui.set_console(console)

        ui.begin_frame()
        ui.render_console()
        ui.end_frame()

        assert ui.backend.has_window("Developer Console")
        assert ui.backend.has_text("Test output")

    def test_render_console_when_hidden(self):
        """Test render_console does nothing when console is hidden."""
        from procengine.commands.console import Console

        ui = UIManager(1920, 1080)
        console = Console()
        ui.set_console(console)

        ui.begin_frame()
        ui.render_console()
        ui.end_frame()

        assert not ui.backend.has_window("Developer Console")
