"""UI system with Dear ImGui integration.

This module provides game UI components:
- HUD (health bar, minimap, quest tracker)
- DialogueBox for NPC conversations
- InventoryPanel for item management
- QuestLog for tracking objectives
- PauseMenu for game state control
- DebugOverlay for development

The system abstracts Dear ImGui to allow:
- Full rendering when ImGui is available
- Headless mode for testing without graphics

Usage:
    from ui_system import UIManager

    ui = UIManager(1920, 1080)
    ui.set_world(game_world)

    # In render loop:
    ui.begin_frame()
    ui.render_hud(player)
    ui.render_dialogue()  # if in dialogue
    ui.end_frame()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from procengine.game.game_api import GameWorld, Player, NPC, Quest, Inventory, DialogueResponse
    from procengine.game.player_controller import InteractionTarget

__all__ = [
    "UIManager",
    "UIComponent",
    "HUD",
    "DialogueBox",
    "InventoryPanel",
    "QuestLog",
    "PauseMenu",
    "DebugOverlay",
    "ImGuiBackend",
]


# =============================================================================
# UI Backend Abstraction
# =============================================================================


class UIBackend(ABC):
    """Abstract UI rendering backend."""

    @abstractmethod
    def begin_frame(
        self,
        dt: float = 1.0 / 60.0,
        width: float = 0.0,
        height: float = 0.0,
        left_down: bool = False,
        right_down: bool = False,
    ) -> None:
        """Begin UI frame."""
        pass

    @abstractmethod
    def end_frame(self) -> None:
        """End UI frame and render."""
        pass

    @abstractmethod
    def begin_window(
        self,
        title: str,
        x: float,
        y: float,
        width: float,
        height: float,
        flags: int = 0,
    ) -> bool:
        """Begin a window. Returns False if collapsed."""
        pass

    @abstractmethod
    def end_window(self) -> None:
        """End current window."""
        pass

    @abstractmethod
    def text(self, text: str) -> None:
        """Render text."""
        pass

    @abstractmethod
    def text_colored(self, text: str, r: float, g: float, b: float, a: float = 1.0) -> None:
        """Render colored text."""
        pass

    @abstractmethod
    def button(self, label: str, width: float = 0, height: float = 0) -> bool:
        """Render button. Returns True if clicked."""
        pass

    @abstractmethod
    def progress_bar(self, fraction: float, width: float = -1, height: float = 0) -> None:
        """Render progress bar."""
        pass

    @abstractmethod
    def separator(self) -> None:
        """Render horizontal separator."""
        pass

    @abstractmethod
    def same_line(self) -> None:
        """Put next element on same line."""
        pass

    @abstractmethod
    def spacing(self) -> None:
        """Add vertical spacing."""
        pass

    @abstractmethod
    def image(self, texture_id: int, width: float, height: float) -> None:
        """Render an image."""
        pass

    @abstractmethod
    def begin_child(
        self,
        id_str: str,
        width: float = 0,
        height: float = 0,
        border: bool = False,
    ) -> bool:
        """Begin a child region."""
        pass

    @abstractmethod
    def end_child(self) -> None:
        """End child region."""
        pass

    @abstractmethod
    def columns(self, count: int, border: bool = True) -> None:
        """Set up columns layout."""
        pass

    @abstractmethod
    def next_column(self) -> None:
        """Move to next column."""
        pass

    @abstractmethod
    def set_cursor_pos(self, x: float, y: float) -> None:
        """Set cursor position within window."""
        pass


class HeadlessUIBackend(UIBackend):
    """Headless UI backend for testing.

    Records UI calls for verification without actual rendering.
    """

    def __init__(self) -> None:
        self._calls: List[Dict[str, Any]] = []
        self._frame_calls: List[Dict[str, Any]] = []
        self._in_frame: bool = False
        self._window_stack: List[str] = []
        self._button_responses: Dict[str, bool] = {}

    def begin_frame(
        self,
        dt: float = 1.0 / 60.0,
        width: float = 0.0,
        height: float = 0.0,
        left_down: bool = False,
        right_down: bool = False,
    ) -> None:
        self._in_frame = True
        self._frame_calls = []

    def end_frame(self) -> None:
        self._calls.extend(self._frame_calls)
        self._frame_calls = []
        self._in_frame = False

    def _record(self, call_type: str, **kwargs: Any) -> None:
        if self._in_frame:
            self._frame_calls.append({"type": call_type, **kwargs})

    def begin_window(
        self,
        title: str,
        x: float,
        y: float,
        width: float,
        height: float,
        flags: int = 0,
    ) -> bool:
        self._record("begin_window", title=title, x=x, y=y, width=width, height=height)
        self._window_stack.append(title)
        return True

    def end_window(self) -> None:
        if self._window_stack:
            self._window_stack.pop()
        self._record("end_window")

    def text(self, text: str) -> None:
        self._record("text", text=text)

    def text_colored(self, text: str, r: float, g: float, b: float, a: float = 1.0) -> None:
        self._record("text_colored", text=text, r=r, g=g, b=b, a=a)

    def button(self, label: str, width: float = 0, height: float = 0) -> bool:
        self._record("button", label=label, width=width, height=height)
        return self._button_responses.get(label, False)

    def progress_bar(self, fraction: float, width: float = -1, height: float = 0) -> None:
        self._record("progress_bar", fraction=fraction, width=width, height=height)

    def separator(self) -> None:
        self._record("separator")

    def same_line(self) -> None:
        self._record("same_line")

    def spacing(self) -> None:
        self._record("spacing")

    def image(self, texture_id: int, width: float, height: float) -> None:
        self._record("image", texture_id=texture_id, width=width, height=height)

    def begin_child(
        self,
        id_str: str,
        width: float = 0,
        height: float = 0,
        border: bool = False,
    ) -> bool:
        self._record("begin_child", id=id_str, width=width, height=height, border=border)
        return True

    def end_child(self) -> None:
        self._record("end_child")

    def columns(self, count: int, border: bool = True) -> None:
        self._record("columns", count=count, border=border)

    def next_column(self) -> None:
        self._record("next_column")

    def set_cursor_pos(self, x: float, y: float) -> None:
        self._record("set_cursor_pos", x=x, y=y)

    # Testing helpers

    def get_calls(self) -> List[Dict[str, Any]]:
        """Get all recorded calls."""
        return self._calls.copy()

    def get_frame_calls(self) -> List[Dict[str, Any]]:
        """Get calls from current frame."""
        return self._frame_calls.copy()

    def clear_calls(self) -> None:
        """Clear recorded calls."""
        self._calls.clear()
        self._frame_calls.clear()

    def set_button_response(self, label: str, clicked: bool) -> None:
        """Set simulated button click response."""
        self._button_responses[label] = clicked

    def find_calls(self, call_type: str) -> List[Dict[str, Any]]:
        """Find all calls of a specific type."""
        return [c for c in self._calls if c["type"] == call_type]

    def has_window(self, title: str) -> bool:
        """Check if a window was rendered."""
        return any(
            c["type"] == "begin_window" and c["title"] == title
            for c in self._calls
        )

    def has_text(self, text: str) -> bool:
        """Check if specific text was rendered (including button labels)."""
        for c in self._calls:
            if c["type"] in ("text", "text_colored") and text in c.get("text", ""):
                return True
            if c["type"] == "button" and text in c.get("label", ""):
                return True
        return False


class ImGuiBackend(UIBackend):
    """Real UI backend that calls C++ Dear ImGui bindings via procengine_cpp.

    This backend bridges the Python UI system to the C++ ImGui renderer.
    Each method maps to the corresponding ImGui function exposed through pybind11.
    Falls back gracefully if the C++ module is unavailable.
    """

    def __init__(self) -> None:
        import procengine_cpp as cpp
        self._cpp = cpp

    def begin_frame(
        self,
        dt: float = 1.0 / 60.0,
        width: float = 0.0,
        height: float = 0.0,
        left_down: bool = False,
        right_down: bool = False,
    ) -> None:
        self._cpp.imgui_new_frame(dt, width, height, left_down, right_down)

    def end_frame(self) -> None:
        self._cpp.imgui_render()

    def begin_window(
        self,
        title: str,
        x: float,
        y: float,
        width: float,
        height: float,
        flags: int = 0,
    ) -> bool:
        self._cpp.imgui_set_next_window_pos(x, y)
        self._cpp.imgui_set_next_window_size(width, height)
        return self._cpp.imgui_begin(title, flags)

    def end_window(self) -> None:
        self._cpp.imgui_end()

    def text(self, text: str) -> None:
        self._cpp.imgui_text(text)

    def text_colored(self, text: str, r: float, g: float, b: float, a: float = 1.0) -> None:
        self._cpp.imgui_text_colored(text, r, g, b, a)

    def button(self, label: str, width: float = 0, height: float = 0) -> bool:
        return self._cpp.imgui_button(label, width, height)

    def progress_bar(self, fraction: float, width: float = -1, height: float = 0) -> None:
        self._cpp.imgui_progress_bar(fraction, width, height)

    def separator(self) -> None:
        self._cpp.imgui_separator()

    def same_line(self) -> None:
        self._cpp.imgui_same_line()

    def spacing(self) -> None:
        self._cpp.imgui_spacing()

    def image(self, texture_id: int, width: float, height: float) -> None:
        self._cpp.imgui_image(texture_id, width, height)

    def begin_child(
        self,
        id_str: str,
        width: float = 0,
        height: float = 0,
        border: bool = False,
    ) -> bool:
        return self._cpp.imgui_begin_child(id_str, width, height, border)

    def end_child(self) -> None:
        self._cpp.imgui_end_child()

    def columns(self, count: int, border: bool = True) -> None:
        self._cpp.imgui_columns(count, border)

    def next_column(self) -> None:
        self._cpp.imgui_next_column()

    def set_cursor_pos(self, x: float, y: float) -> None:
        self._cpp.imgui_set_cursor_pos(x, y)


# =============================================================================
# UI Components
# =============================================================================


class UIComponent(ABC):
    """Base class for UI components."""

    def __init__(self, backend: UIBackend) -> None:
        self._backend = backend
        self._visible: bool = True

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = value

    @abstractmethod
    def render(self, **kwargs: Any) -> None:
        """Render the component."""
        pass


class HUD(UIComponent):
    """Heads-up display showing health, minimap, and quest tracker."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height

    def render(self, player: Optional["Player"] = None, **kwargs: Any) -> None:
        if not self._visible or not player:
            return

        # Health bar (top-left)
        self._render_health_bar(player)

        # Quest tracker (top-right)
        quests = kwargs.get("active_quests", [])
        if quests:
            self._render_quest_tracker(quests)

        # Interaction prompt (bottom-center)
        interaction_target = kwargs.get("interaction_target")
        if interaction_target:
            self._render_interaction_prompt(interaction_target)

    def _render_health_bar(self, player: "Player") -> None:
        """Render health bar."""
        self._backend.begin_window(
            "##HealthBar",
            10, 10,
            200, 60,
            flags=_NO_DECORATION_FLAGS,
        )

        health_fraction = player.health / player.max_health if player.max_health > 0 else 0

        # Health label
        self._backend.text(f"Health: {int(player.health)}/{int(player.max_health)}")

        # Health bar with color based on health level
        if health_fraction > 0.5:
            self._backend.text_colored("", 0.2, 0.8, 0.2)  # Green
        elif health_fraction > 0.25:
            self._backend.text_colored("", 0.8, 0.8, 0.2)  # Yellow
        else:
            self._backend.text_colored("", 0.8, 0.2, 0.2)  # Red

        self._backend.progress_bar(health_fraction, 180, 20)

        self._backend.end_window()

    def _render_quest_tracker(self, quests: List["Quest"]) -> None:
        """Render quest tracker."""
        self._backend.begin_window(
            "Quest Tracker",
            self._screen_width - 260, 10,
            250, 200,
            flags=_NO_RESIZE_FLAGS,
        )

        for quest in quests[:3]:  # Show max 3 quests
            self._backend.text_colored(quest.title, 1.0, 0.8, 0.2)

            for obj in quest.objectives:
                if obj.is_complete():
                    self._backend.text_colored(
                        f"  [x] {obj.description}",
                        0.5, 0.8, 0.5,
                    )
                else:
                    self._backend.text(
                        f"  [ ] {obj.description} ({obj.current_count}/{obj.required_count})"
                    )

            self._backend.separator()

        self._backend.end_window()

    def _render_interaction_prompt(self, target: "InteractionTarget") -> None:
        """Render interaction prompt.
        
        Parameters
        ----------
        target:
            The interaction target containing entity info and action text.
            Expected to have: entity_name, action_text, entity_type, distance
        """
        # Calculate prompt width based on content
        # Format: "[E] Action Entity Name"
        prompt_text = f"[E] {target.action_text} {target.entity_name}"
        prompt_width = max(
            _PROMPT_MIN_WIDTH, 
            len(prompt_text) * _CHAR_WIDTH_ESTIMATE + _PROMPT_PADDING
        )
        
        self._backend.begin_window(
            "##InteractionPrompt",
            (self._screen_width - prompt_width) / 2,
            self._screen_height - 100,
            prompt_width, 50,
            flags=_NO_DECORATION_FLAGS,
        )

        # Color based on entity type
        if target.entity_type == "npc":
            self._backend.text_colored(prompt_text, *_COLOR_NPC_PROMPT)
        elif target.entity_type == "prop":
            self._backend.text_colored(prompt_text, *_COLOR_PROP_PROMPT)
        else:
            # White default
            self._backend.text(prompt_text)

        self._backend.end_window()


class DialogueBox(UIComponent):
    """Dialogue box for NPC conversations."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._current_npc: Optional["NPC"] = None
        self._current_text: str = ""
        self._current_options: List[Dict[str, str]] = []
        self._selected_option: int = -1
        self._on_option_selected: Optional[Callable[[int], None]] = None
        self._on_advance: Optional[Callable[[], None]] = None

    def set_dialogue(
        self,
        npc: "NPC",
        text: str,
        options: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """Set current dialogue content."""
        self._current_npc = npc
        self._current_text = text
        self._current_options = options or []
        self._selected_option = -1

    def clear(self) -> None:
        """Clear dialogue state."""
        self._current_npc = None
        self._current_text = ""
        self._current_options = []
        self._selected_option = -1

    def render(self, **kwargs: Any) -> None:
        if not self._visible or not self._current_npc:
            return

        box_width = min(600, self._screen_width - 40)
        box_height = 200
        box_x = (self._screen_width - box_width) / 2
        box_y = self._screen_height - box_height - 20

        self._backend.begin_window(
            "Dialogue",
            box_x, box_y,
            box_width, box_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # NPC name
        self._backend.text_colored(
            self._current_npc.name,
            0.9, 0.7, 0.3,
        )
        self._backend.separator()

        # Dialogue text
        self._backend.spacing()
        self._backend.text(self._current_text)
        self._backend.spacing()

        # Options or continue prompt
        if self._current_options:
            self._backend.separator()
            for i, option in enumerate(self._current_options):
                label = option.get("label", f"Option {i + 1}")
                if self._backend.button(f"[{i + 1}] {label}", box_width - 20):
                    self._selected_option = i
                    if self._on_option_selected:
                        self._on_option_selected(i)
        else:
            self._backend.separator()
            self._backend.text("[SPACE] Continue...")

        self._backend.end_window()

    def advance(self) -> None:
        """Advance dialogue (for continue prompts)."""
        if self._on_advance:
            self._on_advance()

    def select_option(self, index: int) -> None:
        """Select a dialogue option."""
        if 0 <= index < len(self._current_options):
            self._selected_option = index
            if self._on_option_selected:
                self._on_option_selected(index)


class InventoryPanel(UIComponent):
    """Inventory panel showing player items."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._selected_item: Optional[str] = None
        self._item_definitions: Dict[str, Any] = {}
        self._on_item_use: Optional[Callable[[str], None]] = None
        self._on_item_drop: Optional[Callable[[str], None]] = None

    def set_item_definitions(self, definitions: Dict[str, Any]) -> None:
        """Set item definitions for display."""
        self._item_definitions = definitions

    def render(self, player: Optional["Player"] = None, **kwargs: Any) -> None:
        if not self._visible or not player:
            return

        panel_width = 400
        panel_height = 500
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Inventory",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=0,
        )

        # Item list
        self._backend.begin_child("ItemList", panel_width - 20, panel_height - 100, border=True)

        items = player.inventory.get_all_items()
        if not items:
            self._backend.text("(Empty)")
        else:
            for item_id, count in items.items():
                item_def = self._item_definitions.get(item_id, {})
                item_name = item_def.get("name", item_id) if isinstance(item_def, dict) else item_id

                # Highlight selected item
                if item_id == self._selected_item:
                    self._backend.text_colored(f"> {item_name} x{count}", 1.0, 1.0, 0.5)
                else:
                    self._backend.text(f"  {item_name} x{count}")

                # Make clickable (simulated with button in headless)
                # In real ImGui, this would be a Selectable

        self._backend.end_child()

        # Action buttons
        self._backend.separator()
        if self._backend.button("Use", 80):
            if self._selected_item and self._on_item_use:
                self._on_item_use(self._selected_item)

        self._backend.same_line()
        if self._backend.button("Drop", 80):
            if self._selected_item and self._on_item_drop:
                self._on_item_drop(self._selected_item)

        self._backend.same_line()
        if self._backend.button("Close", 80):
            self._visible = False

        self._backend.end_window()


class QuestLog(UIComponent):
    """Quest log showing all quests."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._selected_quest: Optional[str] = None

    def render(
        self,
        active_quests: Optional[List["Quest"]] = None,
        completed_quests: Optional[List["Quest"]] = None,
        **kwargs: Any,
    ) -> None:
        if not self._visible:
            return

        active_quests = active_quests or []
        completed_quests = completed_quests or []

        panel_width = 500
        panel_height = 400
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Quest Log",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=0,
        )

        # Active quests section
        self._backend.text_colored("Active Quests", 1.0, 0.8, 0.2)
        self._backend.separator()

        if not active_quests:
            self._backend.text("  (No active quests)")
        else:
            for quest in active_quests:
                self._render_quest_entry(quest, completed=False)

        self._backend.spacing()

        # Completed quests section
        self._backend.text_colored("Completed Quests", 0.5, 0.8, 0.5)
        self._backend.separator()

        if not completed_quests:
            self._backend.text("  (No completed quests)")
        else:
            for quest in completed_quests:
                self._render_quest_entry(quest, completed=True)

        self._backend.spacing()
        if self._backend.button("Close", 80):
            self._visible = False

        self._backend.end_window()

    def _render_quest_entry(self, quest: "Quest", completed: bool) -> None:
        """Render a single quest entry."""
        if completed:
            self._backend.text_colored(f"  [x] {quest.title}", 0.6, 0.6, 0.6)
        else:
            is_selected = quest.quest_id == self._selected_quest
            if is_selected:
                self._backend.text_colored(f"  > {quest.title}", 1.0, 1.0, 0.5)

                # Show objectives for selected quest
                for obj in quest.objectives:
                    status = "[x]" if obj.is_complete() else "[ ]"
                    self._backend.text(f"      {status} {obj.description}")
            else:
                progress = quest.get_progress()
                self._backend.text(f"    {quest.title} ({progress[0]}/{progress[1]})")


class PauseMenu(UIComponent):
    """Pause menu with game options."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._on_resume: Optional[Callable[[], None]] = None
        self._on_save: Optional[Callable[[], None]] = None
        self._on_load: Optional[Callable[[], None]] = None
        self._on_settings: Optional[Callable[[], None]] = None
        self._on_quit: Optional[Callable[[], None]] = None

    def render(self, **kwargs: Any) -> None:
        if not self._visible:
            return

        menu_width = 300
        menu_height = 300
        menu_x = (self._screen_width - menu_width) / 2
        menu_y = (self._screen_height - menu_height) / 2

        self._backend.begin_window(
            "Paused",
            menu_x, menu_y,
            menu_width, menu_height,
            flags=_NO_RESIZE_FLAGS,
        )

        self._backend.spacing()

        button_width = menu_width - 40

        if self._backend.button("Resume", button_width, 40):
            if self._on_resume:
                self._on_resume()

        self._backend.spacing()

        if self._backend.button("Save Game", button_width, 40):
            if self._on_save:
                self._on_save()

        self._backend.spacing()

        if self._backend.button("Load Game", button_width, 40):
            if self._on_load:
                self._on_load()

        self._backend.spacing()

        if self._backend.button("Settings", button_width, 40):
            if self._on_settings:
                self._on_settings()

        self._backend.spacing()

        if self._backend.button("Quit to Desktop", button_width, 40):
            if self._on_quit:
                self._on_quit()

        self._backend.end_window()


class DebugOverlay(UIComponent):
    """Debug overlay showing FPS, player stats, and developer tools.
    
    This component provides essential development/debugging information:
    - FPS counter and frame number
    - Player position (X, Y, Z)
    - Entity count in world
    - Biome info at player location
    - Memory/performance hints
    - Reset World button for testing
    
    Toggle with F3 key (configurable in InputManager).
    """

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._on_reset_world: Optional[Callable[[], None]] = None
        self._on_toggle_physics_debug: Optional[Callable[[], None]] = None
        self._show_advanced: bool = False  # Toggle for advanced stats

    def set_callbacks(
        self,
        on_reset_world: Optional[Callable[[], None]] = None,
        on_toggle_physics_debug: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set debug action callbacks.
        
        Parameters
        ----------
        on_reset_world:
            Called when "Reset World" button is pressed.
        on_toggle_physics_debug:
            Called when physics debug visualization is toggled.
        """
        self._on_reset_world = on_reset_world
        self._on_toggle_physics_debug = on_toggle_physics_debug

    def render(
        self,
        fps: float = 0.0,
        frame_count: int = 0,
        player_pos: Optional[Tuple[float, float, float]] = None,
        entity_count: int = 0,
        biome_name: Optional[str] = None,
        physics_active: bool = True,
        grounded: bool = False,
        interaction_target: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Render debug overlay.
        
        Parameters
        ----------
        fps:
            Current frames per second.
        frame_count:
            Total frame count since start.
        player_pos:
            Player position as (x, y, z) tuple.
        entity_count:
            Number of entities in world.
        biome_name:
            Name of biome at player's location.
        physics_active:
            Whether physics simulation is running.
        grounded:
            Whether player is grounded.
        interaction_target:
            Name of entity player can interact with (if any).
        """
        if not self._visible:
            return

        # Calculate window size based on content
        window_width = 220
        window_height = 200 if self._show_advanced else 160

        self._backend.begin_window(
            "Debug",
            self._screen_width - window_width - 10, 
            self._screen_height - window_height - 10,
            window_width, window_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # Performance section
        self._backend.text_colored("=== Performance ===", *_COLOR_SECTION_HEADER)
        
        # Color FPS based on performance
        if fps >= _FPS_GOOD_THRESHOLD:
            self._backend.text_colored(f"FPS: {fps:.1f}", *_COLOR_FPS_GOOD)
        elif fps >= _FPS_WARNING_THRESHOLD:
            self._backend.text_colored(f"FPS: {fps:.1f}", *_COLOR_FPS_WARNING)
        else:
            self._backend.text_colored(f"FPS: {fps:.1f}", *_COLOR_FPS_BAD)
            
        self._backend.text(f"Frame: {frame_count}")

        # Player section
        self._backend.separator()
        self._backend.text_colored("=== Player ===", *_COLOR_SECTION_HEADER)
        
        if player_pos:
            self._backend.text(f"Pos: ({player_pos[0]:.1f}, {player_pos[1]:.1f}, {player_pos[2]:.1f})")
        
        # Ground state
        ground_text = "Grounded" if grounded else "Airborne"
        ground_color = _COLOR_GROUNDED if grounded else _COLOR_AIRBORNE
        self._backend.text_colored(ground_text, *ground_color)

        # World section
        self._backend.separator()
        self._backend.text_colored("=== World ===", *_COLOR_SECTION_HEADER)
        self._backend.text(f"Entities: {entity_count}")
        
        if biome_name:
            self._backend.text(f"Biome: {biome_name}")
            
        if interaction_target:
            self._backend.text_colored(f"Target: {interaction_target}", *_COLOR_TARGET)

        # Action buttons
        self._backend.separator()
        
        if self._backend.button("Reset World", 100, 25):
            if self._on_reset_world:
                self._on_reset_world()

        self._backend.end_window()


# =============================================================================
# UI Manager
# =============================================================================


# Window flags (would be ImGuiWindowFlags in real ImGui)
_NO_DECORATION_FLAGS = 1  # No title bar, resize, etc.
_NO_RESIZE_FLAGS = 2  # No resize

# UI Layout Constants
_CHAR_WIDTH_ESTIMATE = 8  # Estimated pixel width per character
_PROMPT_PADDING = 40  # Extra padding for interaction prompts
_PROMPT_MIN_WIDTH = 200  # Minimum prompt window width

# FPS Performance Thresholds
_FPS_GOOD_THRESHOLD = 55  # Above this = green (good)
_FPS_WARNING_THRESHOLD = 30  # Above this = yellow (warning), below = red (bad)

# UI Colors (R, G, B tuples, 0.0-1.0 range)
_COLOR_FPS_GOOD = (0.3, 0.9, 0.3)  # Green
_COLOR_FPS_WARNING = (0.9, 0.9, 0.3)  # Yellow
_COLOR_FPS_BAD = (0.9, 0.3, 0.3)  # Red
_COLOR_GROUNDED = (0.3, 0.9, 0.3)  # Green
_COLOR_AIRBORNE = (0.6, 0.6, 0.9)  # Light blue
_COLOR_NPC_PROMPT = (1.0, 0.85, 0.4)  # Gold/yellow
_COLOR_PROP_PROMPT = (0.6, 0.8, 1.0)  # Light blue
_COLOR_SECTION_HEADER = (0.8, 0.8, 0.3)  # Yellow
_COLOR_TARGET = (0.9, 0.7, 0.3)  # Orange


class UIManager:
    """Manages all UI components and rendering.

    Provides a high-level interface for the game to render UI without
    needing to know the details of each component.
    """

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        backend: Optional[UIBackend] = None,
    ) -> None:
        """Initialize UI manager.

        Parameters
        ----------
        screen_width:
            Screen width in pixels.
        screen_height:
            Screen height in pixels.
        backend:
            UI backend. Uses headless if not provided.
        """
        self._backend = backend or HeadlessUIBackend()
        self._screen_width = screen_width
        self._screen_height = screen_height

        # Create components
        self._hud = HUD(self._backend, screen_width, screen_height)
        self._dialogue_box = DialogueBox(self._backend, screen_width, screen_height)
        self._inventory_panel = InventoryPanel(self._backend, screen_width, screen_height)
        self._quest_log = QuestLog(self._backend, screen_width, screen_height)
        self._pause_menu = PauseMenu(self._backend, screen_width, screen_height)
        self._debug_overlay = DebugOverlay(self._backend, screen_width, screen_height)

        # Game world reference
        self._world: Optional["GameWorld"] = None

        # Current dialogue state
        self._in_dialogue: bool = False
        self._dialogue_npc: Optional["NPC"] = None

    def set_world(self, world: "GameWorld") -> None:
        """Set game world reference."""
        self._world = world

        # Update inventory panel with item definitions
        if world:
            definitions = {}
            for item_id in world._item_definitions:
                item_def = world.get_item_definition(item_id)
                if item_def:
                    definitions[item_id] = item_def.to_dict()
            self._inventory_panel.set_item_definitions(definitions)

    def shutdown(self) -> None:
        """Cleanup UI resources."""
        pass

    def begin_frame(
        self,
        dt: float = 1.0 / 60.0,
        width: Optional[float] = None,
        height: Optional[float] = None,
        left_down: bool = False,
        right_down: bool = False,
    ) -> None:
        """Begin UI frame."""
        frame_width = self._screen_width if width is None else width
        frame_height = self._screen_height if height is None else height
        self._backend.begin_frame(
            dt,
            frame_width,
            frame_height,
            left_down,
            right_down,
        )

    def end_frame(self) -> None:
        """End UI frame."""
        self._backend.end_frame()

    # -------------------------------------------------------------------------
    # Component Rendering
    # -------------------------------------------------------------------------

    def render_hud(
        self, 
        player: Optional["Player"] = None,
        interaction_target: Optional["InteractionTarget"] = None,
    ) -> None:
        """Render HUD elements.
        
        Parameters
        ----------
        player:
            The player entity for health, quest tracking.
        interaction_target:
            Optional InteractionTarget from PlayerController for showing
            "Press E to interact" prompts.
        """
        if not player:
            return

        # Get active quests for tracker
        active_quests = []
        if self._world:
            for quest_id in player.active_quests:
                quest = self._world.get_quest(quest_id)
                if quest:
                    active_quests.append(quest)

        self._hud.render(
            player=player,
            active_quests=active_quests,
            interaction_target=interaction_target,
        )

    def render_dialogue(self) -> None:
        """Render dialogue box if in dialogue."""
        if self._in_dialogue:
            self._dialogue_box.render()

    def render_inventory(self, player: Optional["Player"] = None) -> None:
        """Render inventory panel."""
        self._inventory_panel.visible = True
        self._inventory_panel.render(player=player)

    def render_quest_log(self, player: Optional["Player"] = None) -> None:
        """Render quest log."""
        if not player or not self._world:
            return

        active_quests = [
            self._world.get_quest(qid)
            for qid in player.active_quests
            if self._world.get_quest(qid)
        ]
        completed_quests = [
            self._world.get_quest(qid)
            for qid in player.completed_quests
            if self._world.get_quest(qid)
        ]

        self._quest_log.visible = True
        self._quest_log.render(
            active_quests=active_quests,
            completed_quests=completed_quests,
        )

    def render_pause_menu(self) -> None:
        """Render pause menu."""
        self._pause_menu.visible = True
        self._pause_menu.render()

    def render_debug(
        self, 
        fps: float, 
        frame_count: int,
        interaction_target: Optional["InteractionTarget"] = None,
    ) -> None:
        """Render debug overlay.
        
        Parameters
        ----------
        fps:
            Current frames per second.
        frame_count:
            Total frame count.
        interaction_target:
            Optional interaction target to display in debug info.
        """
        player_pos = None
        entity_count = 0
        grounded = False
        target_name = None

        if self._world:
            player = self._world.get_player()
            if player:
                player_pos = (player.position.x, player.position.y, player.position.z)
                grounded = player.grounded
            entity_count = len(self._world._entities)
        
        if interaction_target:
            target_name = interaction_target.entity_name

        self._debug_overlay.visible = True
        self._debug_overlay.render(
            fps=fps,
            frame_count=frame_count,
            player_pos=player_pos,
            entity_count=entity_count,
            grounded=grounded,
            interaction_target=target_name,
        )

    # -------------------------------------------------------------------------
    # Dialogue Management
    # -------------------------------------------------------------------------

    def start_dialogue(self, npc: "NPC") -> None:
        """Start dialogue with an NPC."""
        self._in_dialogue = True
        self._dialogue_npc = npc
        self._dialogue_box.set_dialogue(
            npc,
            f"Hello, traveler. What brings you here?",  # Default greeting
            options=None,
        )
        self._dialogue_box.visible = True

    def update_dialogue(self, response: "DialogueResponse") -> None:
        """Update dialogue with a new response."""
        if self._dialogue_npc:
            self._dialogue_box.set_dialogue(
                self._dialogue_npc,
                response.text,
                response.options,
            )

    def end_dialogue(self) -> None:
        """End current dialogue."""
        self._in_dialogue = False
        self._dialogue_npc = None
        self._dialogue_box.clear()
        self._dialogue_box.visible = False

    def advance_dialogue(self) -> None:
        """Advance dialogue (for continue prompts)."""
        self._dialogue_box.advance()

    def select_dialogue_option(self, index: int) -> None:
        """Select a dialogue option."""
        self._dialogue_box.select_option(index)

    # -------------------------------------------------------------------------
    # Properties and Callbacks
    # -------------------------------------------------------------------------

    @property
    def hud(self) -> HUD:
        return self._hud

    @property
    def dialogue_box(self) -> DialogueBox:
        return self._dialogue_box

    @property
    def inventory_panel(self) -> InventoryPanel:
        return self._inventory_panel

    @property
    def quest_log(self) -> QuestLog:
        return self._quest_log

    @property
    def pause_menu(self) -> PauseMenu:
        return self._pause_menu

    @property
    def debug_overlay(self) -> DebugOverlay:
        return self._debug_overlay

    @property
    def backend(self) -> UIBackend:
        return self._backend

    def set_pause_callbacks(
        self,
        on_resume: Optional[Callable[[], None]] = None,
        on_save: Optional[Callable[[], None]] = None,
        on_load: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set pause menu callbacks."""
        self._pause_menu._on_resume = on_resume
        self._pause_menu._on_save = on_save
        self._pause_menu._on_load = on_load
        self._pause_menu._on_settings = on_settings
        self._pause_menu._on_quit = on_quit

    def set_inventory_callbacks(
        self,
        on_use: Optional[Callable[[str], None]] = None,
        on_drop: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Set inventory panel callbacks."""
        self._inventory_panel._on_item_use = on_use
        self._inventory_panel._on_item_drop = on_drop

    def set_dialogue_callbacks(
        self,
        on_option: Optional[Callable[[int], None]] = None,
        on_advance: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set dialogue callbacks."""
        self._dialogue_box._on_option_selected = on_option
        self._dialogue_box._on_advance = on_advance

    def set_debug_callbacks(
        self,
        on_reset_world: Optional[Callable[[], None]] = None,
        on_toggle_physics_debug: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set debug overlay callbacks.
        
        Parameters
        ----------
        on_reset_world:
            Called when user clicks "Reset World" button in debug overlay.
        on_toggle_physics_debug:
            Called when user toggles physics debug visualization.
        """
        self._debug_overlay.set_callbacks(
            on_reset_world=on_reset_world,
            on_toggle_physics_debug=on_toggle_physics_debug,
        )
