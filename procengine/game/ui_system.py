"""UI system with Dear ImGui integration.

This module provides game UI components:
- HUD (health bar, stamina, quest tracker, interaction prompt, status bar)
- DialogueBox for NPC conversations with animated text
- InventoryPanel for item management with tooltips
- QuestLog for tracking objectives
- PauseMenu for game state control
- SettingsPanel for options
- DebugOverlay for development
- ConsoleWindow for the developer console
- NotificationStack for game event notifications
- Tooltip for context-sensitive help

The system abstracts Dear ImGui to allow:
- Full rendering when ImGui is available
- Headless mode for testing without graphics

Usage:
    from procengine.game.ui_system import UIManager

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
    from procengine.game.player_controller import InputManager
    from procengine.game.player_controller import InteractionTarget

__all__ = [
    "UIManager",
    "UIComponent",
    "HUD",
    "DialogueBox",
    "InventoryPanel",
    "CraftingPanel",
    "QuestLog",
    "PauseMenu",
    "MainMenu",
    "WorldCreationScreen",
    "SaveLoadScreen",
    "SettingsPanel",
    "DebugOverlay",
    "ConsoleWindow",
    "NotificationStack",
    "ImGuiBackend",
    "HeadlessUIBackend",
]


# =============================================================================
# Window Flags (match ImGuiWindowFlags)
# =============================================================================

_NO_DECORATION_FLAGS = 1   # No title bar, resize, etc.
_NO_RESIZE_FLAGS = 2       # No resize
_MAX_WORLD_SEED = 0xFFFFFFFFFFFFFFFF


# =============================================================================
# UI Layout Constants
# =============================================================================

_CHAR_WIDTH_ESTIMATE = 8    # Estimated pixel width per character
_PROMPT_PADDING = 40        # Extra padding for interaction prompts
_PROMPT_MIN_WIDTH = 200     # Minimum prompt window width


# =============================================================================
# FPS Performance Thresholds
# =============================================================================

_FPS_GOOD_THRESHOLD = 55    # Above this = green (good)
_FPS_WARNING_THRESHOLD = 30 # Above this = yellow, below = red


# =============================================================================
# UI Color Palette — Indie RPG theme
# =============================================================================

# Performance colors
_COLOR_FPS_GOOD = (0.30, 0.90, 0.30)
_COLOR_FPS_WARNING = (0.95, 0.85, 0.25)
_COLOR_FPS_BAD = (0.95, 0.30, 0.30)

# Player state colors
_COLOR_GROUNDED = (0.30, 0.90, 0.30)
_COLOR_AIRBORNE = (0.55, 0.55, 0.90)

# HUD colors
_COLOR_HEALTH_HIGH = (0.20, 0.80, 0.25)
_COLOR_HEALTH_MID = (0.90, 0.85, 0.20)
_COLOR_HEALTH_LOW = (0.90, 0.25, 0.20)
_COLOR_HEALTH_BG = (0.25, 0.08, 0.08)
_COLOR_XP_BAR = (0.30, 0.50, 0.90)

# Interaction prompt colors
_COLOR_NPC_PROMPT = (1.0, 0.85, 0.40)
_COLOR_PROP_PROMPT = (0.60, 0.80, 1.0)
_COLOR_ITEM_PROMPT = (0.55, 0.85, 1.0)

# Section header
_COLOR_SECTION_HEADER = (0.80, 0.80, 0.30)

# Target
_COLOR_TARGET = (0.90, 0.70, 0.30)

# Dialogue colors
_COLOR_NPC_NAME = (0.95, 0.75, 0.30)
_COLOR_DIALOGUE_TEXT = (0.92, 0.92, 0.92)
_COLOR_OPTION_NORMAL = (0.80, 0.85, 0.95)
_COLOR_OPTION_HOVER = (1.0, 1.0, 0.60)
_COLOR_CONTINUE = (0.60, 0.65, 0.75)

# Inventory colors
_COLOR_ITEM_SELECTED = (1.0, 1.0, 0.50)
_COLOR_ITEM_NORMAL = (0.85, 0.85, 0.85)
_COLOR_ITEM_COUNT = (0.65, 0.65, 0.70)
_COLOR_ITEM_DESC = (0.70, 0.70, 0.75)

# Quest colors
_COLOR_QUEST_ACTIVE = (1.0, 0.85, 0.25)
_COLOR_QUEST_COMPLETE = (0.45, 0.80, 0.45)
_COLOR_QUEST_FAILED = (0.80, 0.35, 0.35)
_COLOR_OBJ_DONE = (0.50, 0.80, 0.50)
_COLOR_OBJ_PENDING = (0.80, 0.80, 0.80)

# Console colors
_COLOR_CONSOLE_BG = (0.08, 0.08, 0.10, 0.92)
_COLOR_CONSOLE_PROMPT = (0.50, 0.70, 1.0)
_COLOR_CONSOLE_INPUT = (0.75, 0.80, 1.0)
_COLOR_CONSOLE_AC = (0.55, 0.55, 0.65)
_COLOR_CONSOLE_AC_HL = (0.85, 0.85, 1.0)

# Menu/Button colors
_COLOR_BUTTON_TEXT = (0.92, 0.92, 0.92)
_COLOR_TITLE = (0.95, 0.90, 0.70)
_COLOR_SUBTITLE = (0.70, 0.70, 0.75)

# Status bar
_COLOR_STATUS_BG = (0.10, 0.10, 0.12, 0.75)
_COLOR_STATUS_TEXT = (0.70, 0.72, 0.75)
_COLOR_STATUS_HIGHLIGHT = (0.85, 0.85, 0.95)


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

    def input_text(self, label: str, text: str, buffer_size: int = 256) -> Tuple[bool, str]:
        """Render text input field. Returns (changed, new_text).

        Default fallback for UI backends that do not support native text input.
        The ConsoleWindow component handles input via the Console + TextInputBuffer
        pipeline and does not rely on this method.
        """
        return (False, text)

    def input_text_state(
        self, label: str, text: str, buffer_size: int = 256
    ) -> Tuple[bool, bool, str]:
        """Render text input field and report edit + submit state.

        Returns ``(changed, submitted, new_text)``. Backends without native text
        input support fall back to the basic ``input_text`` contract and never
        report submission.
        """
        changed, new_text = self.input_text(label, text, buffer_size)
        return (changed, False, new_text)

    def process_platform_event(self, event: bytes) -> None:
        """Forward a native platform event to the UI backend."""
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
        self._input_text_values: Dict[str, str] = {}

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

    def input_text(self, label: str, text: str, buffer_size: int = 256) -> Tuple[bool, str]:
        self._record("input_text", label=label, text=text)
        new_val = self._input_text_values.get(label)
        if new_val is not None:
            return (True, new_val)
        return (False, text)

    # -------------------------------------------------------------------------
    # Testing Helpers
    # -------------------------------------------------------------------------

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

    def set_input_text_value(self, label: str, value: str) -> None:
        """Set simulated text input value."""
        self._input_text_values[label] = value

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

    def input_text(self, label: str, text: str, buffer_size: int = 256) -> Tuple[bool, str]:
        if hasattr(self._cpp, "imgui_input_text"):
            return self._cpp.imgui_input_text(label, text, buffer_size)
        return (False, text)

    def input_text_state(
        self, label: str, text: str, buffer_size: int = 256
    ) -> Tuple[bool, bool, str]:
        if hasattr(self._cpp, "imgui_input_text_state"):
            return self._cpp.imgui_input_text_state(label, text, buffer_size)
        changed, new_text = self.input_text(label, text, buffer_size)
        return (changed, False, new_text)

    def process_platform_event(self, event: bytes) -> None:
        if hasattr(self._cpp, "imgui_process_sdl_event"):
            self._cpp.imgui_process_sdl_event(event)


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


# =============================================================================
# HUD — Heads-Up Display
# =============================================================================


class HUD(UIComponent):
    """Heads-up display showing health bar, quest tracker, and interaction prompt.

    Layout:
    - Top-left: Health bar with numeric display
    - Top-right: Active quest tracker (max 3 quests)
    - Bottom-center: "[E] Action Entity" interaction prompt
    - Bottom-left: Status bar (time of day, biome)
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

        # Harvest feedback (bottom-center, above interaction prompt)
        harvest_result = kwargs.get("harvest_result")
        if harvest_result:
            self._render_harvest_feedback(harvest_result)

        # Status bar (bottom-left)
        time_of_day = kwargs.get("time_of_day")
        biome_name = kwargs.get("biome_name")
        if time_of_day is not None or biome_name:
            self._render_status_bar(time_of_day, biome_name)

    def _render_health_bar(self, player: "Player") -> None:
        """Render health bar with color gradient."""
        self._backend.begin_window(
            "##HealthBar",
            10, 10,
            220, 70,
            flags=_NO_DECORATION_FLAGS,
        )

        health_fraction = player.health / player.max_health if player.max_health > 0 else 0

        # Health label with numeric display
        self._backend.text_colored(
            f"HP  {int(player.health)} / {int(player.max_health)}",
            *_COLOR_HEALTH_HIGH if health_fraction > 0.5
            else _COLOR_HEALTH_MID if health_fraction > 0.25
            else _COLOR_HEALTH_LOW,
        )

        # Health bar
        self._backend.progress_bar(health_fraction, 200, 16)

        self._backend.end_window()

    def _render_quest_tracker(self, quests: List["Quest"]) -> None:
        """Render compact quest tracker in top-right corner."""
        self._backend.begin_window(
            "Quest Tracker",
            self._screen_width - 280, 10,
            270, 180,
            flags=_NO_RESIZE_FLAGS,
        )

        self._backend.text_colored("Active Quests", *_COLOR_QUEST_ACTIVE)
        self._backend.separator()

        for quest in quests[:3]:  # Show max 3 quests
            completed, total = quest.get_progress()
            progress_text = f"({completed}/{total})"
            self._backend.text_colored(
                f"  {quest.title} {progress_text}",
                *_COLOR_QUEST_ACTIVE,
            )

            for obj in quest.objectives:
                if obj.is_complete():
                    self._backend.text_colored(
                        f"    [x] {obj.description}",
                        *_COLOR_OBJ_DONE,
                    )
                else:
                    self._backend.text(
                        f"    [ ] {obj.description} ({obj.current_count}/{obj.required_count})"
                    )

            self._backend.spacing()

        self._backend.end_window()

    def _render_interaction_prompt(self, target: "InteractionTarget") -> None:
        """Render interaction prompt at bottom-center.

        Parameters
        ----------
        target:
            The interaction target with entity_name, action_text, entity_type.
        """
        # Use [LMB] for harvest prompts, [E] for other interactions
        if target.action_text.startswith("Harvest"):
            key_hint = "[LMB]"
        else:
            key_hint = "[E]"
        prompt_text = f"{key_hint} {target.action_text} {target.entity_name}"
        prompt_width = max(
            _PROMPT_MIN_WIDTH,
            len(prompt_text) * _CHAR_WIDTH_ESTIMATE + _PROMPT_PADDING,
        )

        self._backend.begin_window(
            "##InteractionPrompt",
            (self._screen_width - prompt_width) / 2,
            self._screen_height - 100,
            prompt_width, 45,
            flags=_NO_DECORATION_FLAGS,
        )

        # Color based on entity type
        color_map = {
            "npc": _COLOR_NPC_PROMPT,
            "prop": _COLOR_PROP_PROMPT,
            "item": _COLOR_ITEM_PROMPT,
        }
        color = color_map.get(target.entity_type, (1.0, 1.0, 1.0))
        self._backend.text_colored(prompt_text, *color)

        self._backend.end_window()

    def _render_harvest_feedback(self, result: Any) -> None:
        """Render harvest hit / drop feedback above the interaction prompt."""
        if not result or not getattr(result, "hit", False):
            return

        if result.destroyed and result.drops:
            parts = [f"{d['item_id'].replace('_', ' ').title()} x{d['count']}" for d in result.drops]
            text = "  ".join(parts)
        else:
            text = f"{result.target_name} — {result.hits_remaining} hits left"

        width = max(200, len(text) * _CHAR_WIDTH_ESTIMATE + 30)
        self._backend.begin_window(
            "##HarvestFeedback",
            (self._screen_width - width) / 2,
            self._screen_height - 150,
            width, 35,
            flags=_NO_DECORATION_FLAGS,
        )
        self._backend.text_colored(text, 1.0, 0.9, 0.3)  # gold-ish
        self._backend.end_window()

    def _render_status_bar(
        self,
        time_of_day: Optional[float],
        biome_name: Optional[str],
    ) -> None:
        """Render status bar at bottom-left with time and biome info."""
        parts: List[str] = []
        if time_of_day is not None:
            hours = int(time_of_day) % 24
            minutes = int((time_of_day % 1) * 60)
            period = "AM" if hours < 12 else "PM"
            display_hour = hours % 12 or 12
            parts.append(f"{display_hour}:{minutes:02d} {period}")
        if biome_name:
            parts.append(biome_name)

        if not parts:
            return

        status_text = "  |  ".join(parts)
        bar_width = max(200, len(status_text) * _CHAR_WIDTH_ESTIMATE + 30)

        self._backend.begin_window(
            "##StatusBar",
            10, self._screen_height - 40,
            bar_width, 30,
            flags=_NO_DECORATION_FLAGS,
        )
        self._backend.text_colored(status_text, *_COLOR_STATUS_TEXT)
        self._backend.end_window()


# =============================================================================
# DialogueBox
# =============================================================================


class DialogueBox(UIComponent):
    """Dialogue box for NPC conversations.

    Features:
    - NPC name with gold accent
    - Scrollable dialogue text area
    - Numbered dialogue options styled as buttons
    - "[SPACE] Continue..." prompt when no options
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

        box_width = min(650, self._screen_width - 40)
        box_height = 220
        box_x = (self._screen_width - box_width) / 2
        box_y = self._screen_height - box_height - 20

        self._backend.begin_window(
            "Dialogue",
            box_x, box_y,
            box_width, box_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # NPC name header
        self._backend.text_colored(self._current_npc.name, *_COLOR_NPC_NAME)
        self._backend.separator()

        # Dialogue text region
        self._backend.spacing()
        # Wrap long text
        words = self._current_text.split()
        line = ""
        chars_per_line = int((box_width - 40) / _CHAR_WIDTH_ESTIMATE)
        for word in words:
            test = f"{line} {word}".strip()
            if len(test) > chars_per_line:
                if line:
                    self._backend.text_colored(line, *_COLOR_DIALOGUE_TEXT)
                line = word
            else:
                line = test
        if line:
            self._backend.text_colored(line, *_COLOR_DIALOGUE_TEXT)

        self._backend.spacing()

        # Options or continue prompt
        if self._current_options:
            self._backend.separator()
            for i, option in enumerate(self._current_options):
                label = option.get("label", f"Option {i + 1}")
                btn_label = f"  [{i + 1}] {label}  "
                if self._backend.button(btn_label, box_width - 30, 28):
                    self._selected_option = i
                    if self._on_option_selected:
                        self._on_option_selected(i)
        else:
            self._backend.separator()
            self._backend.text_colored("[SPACE] Continue...", *_COLOR_CONTINUE)

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


# =============================================================================
# InventoryPanel
# =============================================================================


class InventoryPanel(UIComponent):
    """Inventory panel showing player items with details and actions.

    Features:
    - Scrollable item list with counts
    - Item selection highlighting
    - Item description tooltip area
    - Use / Drop / Close action buttons
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

        panel_width = 420
        panel_height = 520
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Inventory",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=0,
        )

        self._backend.text_colored("Inventory", *_COLOR_TITLE)
        self._backend.separator()

        # Item list scrollable region
        list_height = panel_height - 180
        self._backend.begin_child("ItemList", panel_width - 20, list_height, border=True)

        items = player.inventory.get_all_items()
        if not items:
            self._backend.spacing()
            self._backend.text_colored("  (Empty)", *_COLOR_SUBTITLE)
        else:
            for item_id, count in items.items():
                item_def = self._item_definitions.get(item_id, {})
                if isinstance(item_def, dict):
                    item_name = item_def.get("name", item_id)
                else:
                    item_name = item_id

                is_selected = item_id == self._selected_item

                # Item entry with selection highlighting
                if is_selected:
                    self._backend.text_colored(
                        f"> {item_name}", *_COLOR_ITEM_SELECTED,
                    )
                    self._backend.same_line()
                    self._backend.text_colored(f"  x{count}", *_COLOR_ITEM_COUNT)
                else:
                    if self._backend.button(f"  {item_name}  x{count}##inv_{item_id}", panel_width - 40):
                        self._selected_item = item_id

        self._backend.end_child()

        # Item description area
        if self._selected_item:
            item_def = self._item_definitions.get(self._selected_item, {})
            desc = ""
            if isinstance(item_def, dict):
                desc = item_def.get("description", "")
            if desc:
                self._backend.spacing()
                self._backend.text_colored(desc, *_COLOR_ITEM_DESC)

        # Action buttons row
        self._backend.separator()
        self._backend.spacing()

        if self._backend.button("Use", 90, 30):
            if self._selected_item and self._on_item_use:
                self._on_item_use(self._selected_item)

        self._backend.same_line()
        if self._backend.button("Drop", 90, 30):
            if self._selected_item and self._on_item_drop:
                self._on_item_drop(self._selected_item)

        self._backend.same_line()
        if self._backend.button("Close", 90, 30):
            self._visible = False

        self._backend.end_window()


# =============================================================================
# CraftingPanel
# =============================================================================

# Crafting-specific colors
_COLOR_CRAFT_AVAILABLE = (0.40, 0.90, 0.40)
_COLOR_CRAFT_UNAVAILABLE = (0.55, 0.55, 0.55)
_COLOR_CRAFT_SELECTED = (0.30, 0.85, 1.0)
_COLOR_INGREDIENT_HAVE = (0.70, 0.90, 0.70)
_COLOR_INGREDIENT_NEED = (0.90, 0.45, 0.40)
_COLOR_CRAFT_CATEGORY = (0.90, 0.80, 0.50)
_COLOR_CRAFT_RESULT = (1.0, 0.95, 0.60)


class CraftingPanel(UIComponent):
    """Crafting panel with multi-item selection and recipe discovery.

    Features:
    - Left column: inventory items with multi-select checkboxes
    - Right column: available recipes filtered by selected items
    - Recipe detail area with ingredients and craft button
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
        self._selected_items: set = set()  # item_ids currently selected
        self._selected_recipe: Optional[str] = None  # recipe_id
        self._item_definitions: Dict[str, Any] = {}
        self._recipes: List[Any] = []  # List of recipe dicts
        self._on_craft: Optional[Callable[[str], None]] = None  # recipe_id callback
        self._inventory_snapshot: Dict[str, int] = {}

    def set_item_definitions(self, definitions: Dict[str, Any]) -> None:
        """Set item definitions for display."""
        self._item_definitions = definitions

    def set_recipes(self, recipes: List[Any]) -> None:
        """Set available recipes for the panel.

        Parameters
        ----------
        recipes:
            List of recipe dicts with keys: recipe_id, name, description,
            ingredients (dict), result_item, result_count, category.
        """
        self._recipes = recipes

    def _get_matching_recipes(self) -> List[Any]:
        """Get recipes whose ingredients are a subset of selected items."""
        if not self._selected_items:
            return []
        selected = frozenset(self._selected_items)
        matches = []
        for recipe in self._recipes:
            ingredients = recipe.get("ingredients", {})
            if frozenset(ingredients.keys()) <= selected:
                matches.append(recipe)
        return matches

    def _can_craft_recipe(self, recipe: Dict[str, Any]) -> bool:
        """Check if the player has enough of each ingredient."""
        for item_id, needed in recipe.get("ingredients", {}).items():
            if self._inventory_snapshot.get(item_id, 0) < needed:
                return False
        return True

    def render(self, player: Optional["Player"] = None, **kwargs: Any) -> None:
        if not self._visible or not player:
            return

        # Cache current inventory for quantity checks
        self._inventory_snapshot = player.inventory.get_all_items()

        panel_width = 580
        panel_height = 520
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Crafting",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=0,
        )

        self._backend.text_colored("Crafting", *_COLOR_TITLE)
        self._backend.separator()

        content_height = panel_height - 180

        # ---- Left column: item selection ----
        left_width = 200
        self._backend.begin_child(
            "CraftItems", left_width, content_height, border=True,
        )

        self._backend.text_colored("Select Items", *_COLOR_SUBTITLE)
        self._backend.separator()

        items = self._inventory_snapshot
        if not items:
            self._backend.text_colored("  (Empty)", *_COLOR_SUBTITLE)
        else:
            for item_id, count in items.items():
                # Skip quest items -- they can't be used for crafting
                item_def = self._item_definitions.get(item_id, {})
                if isinstance(item_def, dict) and item_def.get("item_type") == "quest":
                    continue

                if isinstance(item_def, dict):
                    item_name = item_def.get("name", item_id)
                else:
                    item_name = item_id

                is_selected = item_id in self._selected_items
                label = f"[x] {item_name}  x{count}" if is_selected else f"[ ] {item_name}  x{count}"

                if is_selected:
                    self._backend.text_colored(label, *_COLOR_ITEM_SELECTED)
                    # Click to deselect
                    if self._backend.button(f"Deselect##desel_{item_id}", left_width - 20):
                        self._selected_items.discard(item_id)
                        self._selected_recipe = None
                else:
                    if self._backend.button(f"{label}##sel_{item_id}", left_width - 20):
                        self._selected_items.add(item_id)
                        self._selected_recipe = None

        self._backend.end_child()

        # ---- Right column: matching recipes ----
        self._backend.same_line()
        right_width = panel_width - left_width - 30
        self._backend.begin_child(
            "CraftRecipes", right_width, content_height, border=True,
        )

        self._backend.text_colored("Recipes", *_COLOR_SUBTITLE)
        self._backend.separator()

        matching = self._get_matching_recipes()
        if not self._selected_items:
            self._backend.spacing()
            self._backend.text_colored("  Select items to", *_COLOR_SUBTITLE)
            self._backend.text_colored("  see recipes", *_COLOR_SUBTITLE)
        elif not matching:
            self._backend.spacing()
            self._backend.text_colored("  No recipes for", *_COLOR_SUBTITLE)
            self._backend.text_colored("  selected items", *_COLOR_SUBTITLE)
        else:
            # Group by category
            categories: Dict[str, List[Any]] = {}
            for recipe in matching:
                cat = recipe.get("category", "misc")
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(recipe)

            for cat_name, cat_recipes in categories.items():
                self._backend.text_colored(
                    f"  -- {cat_name.title()} --", *_COLOR_CRAFT_CATEGORY,
                )
                for recipe in cat_recipes:
                    recipe_id = recipe["recipe_id"]
                    r_name = recipe["name"]
                    r_count = recipe.get("result_count", 1)
                    can_craft = self._can_craft_recipe(recipe)
                    is_sel = recipe_id == self._selected_recipe

                    count_label = f" x{r_count}" if r_count > 1 else ""

                    if is_sel:
                        color = _COLOR_CRAFT_SELECTED
                    elif can_craft:
                        color = _COLOR_CRAFT_AVAILABLE
                    else:
                        color = _COLOR_CRAFT_UNAVAILABLE

                    self._backend.text_colored(
                        f"  {'>' if is_sel else ' '} {r_name}{count_label}",
                        *color,
                    )
                    if self._backend.button(f"Details##rec_{recipe_id}", right_width - 30):
                        self._selected_recipe = recipe_id

                self._backend.spacing()

        self._backend.end_child()

        # ---- Bottom: recipe detail and craft button ----
        self._backend.separator()

        if self._selected_recipe:
            recipe = None
            for r in self._recipes:
                if r["recipe_id"] == self._selected_recipe:
                    recipe = r
                    break

            if recipe:
                result_def = self._item_definitions.get(recipe["result_item"], {})
                result_name = result_def.get("name", recipe["result_item"]) if isinstance(result_def, dict) else recipe["result_item"]
                r_count = recipe.get("result_count", 1)
                count_label = f" x{r_count}" if r_count > 1 else ""

                self._backend.text_colored(
                    f"Craft: {result_name}{count_label}", *_COLOR_CRAFT_RESULT,
                )

                # Show description
                desc = recipe.get("description", "")
                if desc:
                    self._backend.text_colored(desc, *_COLOR_ITEM_DESC)

                # Show ingredients with have/need coloring
                self._backend.text("Requires:")
                for ing_id, ing_count in recipe.get("ingredients", {}).items():
                    ing_def = self._item_definitions.get(ing_id, {})
                    ing_name = ing_def.get("name", ing_id) if isinstance(ing_def, dict) else ing_id
                    have = self._inventory_snapshot.get(ing_id, 0)
                    color = _COLOR_INGREDIENT_HAVE if have >= ing_count else _COLOR_INGREDIENT_NEED
                    self._backend.text_colored(
                        f"  {ing_name}: {have}/{ing_count}", *color,
                    )

                self._backend.spacing()
                can_craft = self._can_craft_recipe(recipe)
                if can_craft:
                    if self._backend.button("Craft", 100, 30):
                        if self._on_craft:
                            self._on_craft(self._selected_recipe)
                            # Refresh inventory snapshot after crafting
                            self._inventory_snapshot = player.inventory.get_all_items()
                            # Prune selected items no longer in inventory
                            self._selected_items = {
                                sid for sid in self._selected_items
                                if sid in self._inventory_snapshot
                            }
                else:
                    self._backend.text_colored("(Not enough materials)", *_COLOR_CRAFT_UNAVAILABLE)
        else:
            self._backend.spacing()
            self._backend.text_colored("Select a recipe for details", *_COLOR_SUBTITLE)

        self._backend.same_line()

        # Close button (right-aligned)
        if self._backend.button("Close", 90, 30):
            self._visible = False
            self._selected_items.clear()
            self._selected_recipe = None

        self._backend.end_window()


# =============================================================================
# QuestLog
# =============================================================================


class QuestLog(UIComponent):
    """Quest log showing active and completed quests with objectives."""

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

        panel_width = 520
        panel_height = 440
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Quest Log",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=0,
        )

        self._backend.text_colored("Quest Log", *_COLOR_TITLE)
        self._backend.separator()

        # --- Active quests ---
        self._backend.spacing()
        self._backend.text_colored("Active Quests", *_COLOR_QUEST_ACTIVE)
        self._backend.separator()

        if not active_quests:
            self._backend.text("  (No active quests)")
        else:
            for quest in active_quests:
                self._render_quest_entry(quest, completed=False)

        self._backend.spacing()
        self._backend.spacing()

        # --- Completed quests ---
        self._backend.text_colored("Completed Quests", *_COLOR_QUEST_COMPLETE)
        self._backend.separator()

        if not completed_quests:
            self._backend.text("  (No completed quests)")
        else:
            for quest in completed_quests:
                self._render_quest_entry(quest, completed=True)

        self._backend.spacing()
        if self._backend.button("Close", 100, 28):
            self._visible = False

        self._backend.end_window()

    def _render_quest_entry(self, quest: "Quest", completed: bool) -> None:
        """Render a single quest entry with expandable objectives."""
        if completed:
            self._backend.text_colored(f"  [x] {quest.title}", *_COLOR_QUEST_COMPLETE)
        else:
            is_selected = quest.quest_id == self._selected_quest
            progress = quest.get_progress()

            if is_selected:
                self._backend.text_colored(
                    f"  > {quest.title}  ({progress[0]}/{progress[1]})",
                    *_COLOR_QUEST_ACTIVE,
                )
                # Show objectives when selected
                for obj in quest.objectives:
                    if obj.is_complete():
                        self._backend.text_colored(
                            f"      [x] {obj.description}",
                            *_COLOR_OBJ_DONE,
                        )
                    else:
                        self._backend.text_colored(
                            f"      [ ] {obj.description} ({obj.current_count}/{obj.required_count})",
                            *_COLOR_OBJ_PENDING,
                        )
            else:
                if self._backend.button(
                    f"    {quest.title}  ({progress[0]}/{progress[1]})##q_{quest.quest_id}",
                    0, 24,
                ):
                    self._selected_quest = quest.quest_id


# =============================================================================
# PauseMenu
# =============================================================================


class PauseMenu(UIComponent):
    """Pause menu with game options.

    Styled as a centered overlay with large buttons.
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
        self._on_resume: Optional[Callable[[], None]] = None
        self._on_save: Optional[Callable[[], None]] = None
        self._on_load: Optional[Callable[[], None]] = None
        self._on_settings: Optional[Callable[[], None]] = None
        self._on_quit: Optional[Callable[[], None]] = None

    def render(self, **kwargs: Any) -> None:
        if not self._visible:
            return

        menu_width = 320
        menu_height = 340
        menu_x = (self._screen_width - menu_width) / 2
        menu_y = (self._screen_height - menu_height) / 2

        self._backend.begin_window(
            "Paused",
            menu_x, menu_y,
            menu_width, menu_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # Title
        self._backend.spacing()
        self._backend.text_colored("    PAUSED", *_COLOR_TITLE)
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        button_width = menu_width - 50

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
        self._backend.separator()
        self._backend.spacing()

        if self._backend.button("Quit to Desktop", button_width, 40):
            if self._on_quit:
                self._on_quit()

        self._backend.end_window()


# =============================================================================
# MainMenu
# =============================================================================


class MainMenu(UIComponent):
    """Main menu shown on application startup.

    Provides options to create a new world, load a saved game,
    open settings, or quit.
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
        self._on_new_world: Optional[Callable[[], None]] = None
        self._on_load_game: Optional[Callable[[], None]] = None
        self._on_settings: Optional[Callable[[], None]] = None
        self._on_quit: Optional[Callable[[], None]] = None

    def render(self, **kwargs: Any) -> None:
        if not self._visible:
            return

        menu_width = 420
        menu_height = 440
        menu_x = (self._screen_width - menu_width) / 2
        menu_y = (self._screen_height - menu_height) / 2

        self._backend.begin_window(
            "Main Menu",
            menu_x, menu_y,
            menu_width, menu_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # Title
        self._backend.spacing()
        self._backend.spacing()
        self._backend.text_colored("   PROCEDURAL ENGINE v2", *_COLOR_TITLE)
        self._backend.spacing()
        self._backend.text_colored("   Deterministic World Generation", *_COLOR_SUBTITLE)
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()
        self._backend.spacing()

        button_width = menu_width - 60

        if self._backend.button("New World", button_width, 50):
            if self._on_new_world:
                self._on_new_world()

        self._backend.spacing()
        self._backend.spacing()

        if self._backend.button("Load Game", button_width, 50):
            if self._on_load_game:
                self._on_load_game()

        self._backend.spacing()
        self._backend.spacing()

        if self._backend.button("Settings", button_width, 50):
            if self._on_settings:
                self._on_settings()

        self._backend.spacing()
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        if self._backend.button("Quit", button_width, 40):
            if self._on_quit:
                self._on_quit()

        self._backend.end_window()


# =============================================================================
# WorldCreationScreen
# =============================================================================


class WorldCreationScreen(UIComponent):
    """World creation screen with editable generation parameters.

    Allows the user to configure world seed and other generation
    parameters before starting world generation.
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
        self._seed_text: str = "42"
        self._status_message: str = ""
        self._on_start: Optional[Callable[[int], None]] = None
        self._on_back: Optional[Callable[[], None]] = None

    @property
    def seed_text(self) -> str:
        return self._seed_text

    @seed_text.setter
    def seed_text(self, value: str) -> None:
        self._seed_text = value

    def set_status(self, message: str) -> None:
        """Set a validation or status message to display."""
        self._status_message = message

    def _parse_seed(self) -> Tuple[Optional[int], str]:
        """Parse and validate the currently entered seed.

        Returns
        -------
        tuple[Optional[int], str]
            ``(seed, "")`` when validation succeeds, otherwise
            ``(None, error_message)``.
        """
        seed_text = self._seed_text.strip()
        if not seed_text:
            return None, "World seed is required. Enter digits 0-9 only."

        if not seed_text.isdigit():
            return None, "Seeds must use digits 0-9 only."

        seed = int(seed_text)
        if seed > _MAX_WORLD_SEED:
            return None, (
                f"Seed must be between 0 and {_MAX_WORLD_SEED}."
            )

        return seed, ""

    def render(self, **kwargs: Any) -> None:
        if not self._visible:
            return

        panel_width = 480
        panel_height = 390
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Create New World",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # Title
        self._backend.spacing()
        self._backend.text_colored("   WORLD CREATION", *_COLOR_TITLE)
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        # Seed input
        self._backend.text("World Seed:")
        self._backend.spacing()
        changed, submitted, new_text = self._backend.input_text_state(
            "##seed", self._seed_text, 64
        )
        if changed:
            self._seed_text = new_text
            self._status_message = ""

        self._backend.spacing()
        self._backend.text_colored(
            "  The seed determines the entire world.",
            *_COLOR_SUBTITLE,
        )
        self._backend.text_colored(
            "  Same seed = same world, every time.",
            *_COLOR_SUBTITLE,
        )
        self._backend.text_colored(
            f"  Use digits only: 0 to {_MAX_WORLD_SEED}.",
            *_COLOR_SUBTITLE,
        )

        self._backend.spacing()
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()
        self._backend.spacing()

        button_width = panel_width - 60

        if self._backend.button("Generate World", button_width, 50) or submitted:
            if self._on_start:
                seed, error_message = self._parse_seed()
                if error_message:
                    self._status_message = error_message
                elif seed is not None:
                    self._status_message = ""
                    self._on_start(seed)

        if self._status_message:
            self._backend.spacing()
            self._backend.text_colored(
                f"  {self._status_message}",
                *_COLOR_QUEST_FAILED,
            )

        self._backend.spacing()
        self._backend.spacing()

        if self._backend.button("Back", button_width, 40):
            if self._on_back:
                self._on_back()

        self._backend.end_window()


# =============================================================================
# SaveLoadScreen
# =============================================================================


class SaveLoadScreen(UIComponent):
    """Save/Load screen listing available save files.

    Used from both the main menu (load only) and the pause menu
    (save and load).
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
        self._mode: str = "load"  # "save" or "load"
        self._save_files: List[str] = []
        self._selected_file: str = "quicksave"
        self._save_name_text: str = "quicksave"
        self._status_message: str = ""
        self._on_save: Optional[Callable[[str], None]] = None
        self._on_load: Optional[Callable[[str], None]] = None
        self._on_back: Optional[Callable[[], None]] = None

    def set_mode(self, mode: str) -> None:
        """Set mode to 'save' or 'load'."""
        self._mode = mode

    def set_save_files(self, files: List[str]) -> None:
        """Update list of available save files."""
        self._save_files = files

    def set_status(self, message: str) -> None:
        """Set a status message to display."""
        self._status_message = message

    def render(self, **kwargs: Any) -> None:
        if not self._visible:
            return

        panel_width = 480
        panel_height = 420
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        title = "Save Game" if self._mode == "save" else "Load Game"
        self._backend.begin_window(
            title,
            panel_x, panel_y,
            panel_width, panel_height,
            flags=_NO_RESIZE_FLAGS,
        )

        self._backend.spacing()
        self._backend.text_colored(f"   {title.upper()}", *_COLOR_TITLE)
        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        button_width = panel_width - 60

        # Save name input (only in save mode)
        if self._mode == "save":
            self._backend.text("Save Name:")
            changed, new_text = self._backend.input_text(
                "##savename", self._save_name_text, 64
            )
            if changed:
                self._save_name_text = new_text
            self._backend.spacing()

            if self._backend.button("Save", button_width, 40):
                if self._on_save:
                    self._on_save(self._save_name_text)
            self._backend.spacing()
            self._backend.separator()
            self._backend.spacing()

        # List available saves
        if self._save_files:
            self._backend.text("Available Saves:")
            self._backend.spacing()

            for save_name in self._save_files:
                label = f"  {save_name}"
                if self._mode == "load":
                    if self._backend.button(f"Load: {save_name}", button_width, 30):
                        if self._on_load:
                            self._on_load(save_name)
                else:
                    self._backend.text(label)
                self._backend.spacing()
        else:
            self._backend.text_colored("  No save files found.", *_COLOR_SUBTITLE)
            self._backend.spacing()

        # Status message
        if self._status_message:
            self._backend.spacing()
            self._backend.text_colored(
                f"  {self._status_message}", *_COLOR_QUEST_ACTIVE
            )
            self._backend.spacing()

        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        if self._backend.button("Back", button_width, 40):
            if self._on_back:
                self._on_back()

        self._backend.end_window()


# =============================================================================
# SettingsPanel
# =============================================================================


class SettingsPanel(UIComponent):
    """Settings panel for game options."""

    def __init__(
        self,
        backend: UIBackend,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(backend)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._on_toggle_debug: Optional[Callable[[], None]] = None
        self._on_toggle_vsync: Optional[Callable[[], None]] = None
        self._on_close: Optional[Callable[[], None]] = None

    def set_callbacks(
        self,
        on_toggle_debug: Optional[Callable[[], None]] = None,
        on_toggle_vsync: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set settings callbacks."""
        self._on_toggle_debug = on_toggle_debug
        self._on_toggle_vsync = on_toggle_vsync
        self._on_close = on_close

    def render(
        self,
        debug_enabled: bool = False,
        vsync_enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        if not self._visible:
            return

        panel_width = 380
        panel_height = 340
        panel_x = (self._screen_width - panel_width) / 2
        panel_y = (self._screen_height - panel_height) / 2

        self._backend.begin_window(
            "Settings",
            panel_x, panel_y,
            panel_width, panel_height,
            flags=_NO_RESIZE_FLAGS,
        )

        self._backend.text_colored("Settings", *_COLOR_TITLE)
        self._backend.separator()
        self._backend.spacing()

        # --- Graphics section ---
        self._backend.text_colored("Graphics", *_COLOR_SECTION_HEADER)
        self._backend.spacing()

        button_width = panel_width - 50

        debug_label = f"Debug Overlay:  {'ON' if debug_enabled else 'OFF'}"
        if self._backend.button(debug_label, button_width, 30):
            if self._on_toggle_debug:
                self._on_toggle_debug()

        self._backend.spacing()

        vsync_label = f"VSync:  {'ON' if vsync_enabled else 'OFF'}"
        if self._backend.button(vsync_label, button_width, 30):
            if self._on_toggle_vsync:
                self._on_toggle_vsync()

        self._backend.spacing()
        self._backend.separator()
        self._backend.spacing()

        if self._backend.button("Back", 120, 30):
            self._visible = False
            if self._on_close:
                self._on_close()

        self._backend.end_window()


# =============================================================================
# DebugOverlay
# =============================================================================


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
        self._show_advanced: bool = False

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
        chunk_info: Optional[str] = None,
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
        chunk_info:
            Optional chunk loading info string.
        """
        if not self._visible:
            return

        window_width = 240
        window_height = 220 if self._show_advanced else 180

        self._backend.begin_window(
            "Debug",
            self._screen_width - window_width - 10,
            self._screen_height - window_height - 10,
            window_width, window_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # === Performance ===
        self._backend.text_colored("Performance", *_COLOR_SECTION_HEADER)

        if fps >= _FPS_GOOD_THRESHOLD:
            self._backend.text_colored(f"  FPS: {fps:.1f}", *_COLOR_FPS_GOOD)
        elif fps >= _FPS_WARNING_THRESHOLD:
            self._backend.text_colored(f"  FPS: {fps:.1f}", *_COLOR_FPS_WARNING)
        else:
            self._backend.text_colored(f"  FPS: {fps:.1f}", *_COLOR_FPS_BAD)

        self._backend.text(f"  Frame: {frame_count}")

        # === Player ===
        self._backend.separator()
        self._backend.text_colored("Player", *_COLOR_SECTION_HEADER)

        if player_pos:
            self._backend.text(
                f"  Pos: ({player_pos[0]:.1f}, {player_pos[1]:.1f}, {player_pos[2]:.1f})"
            )

        ground_text = "Grounded" if grounded else "Airborne"
        ground_color = _COLOR_GROUNDED if grounded else _COLOR_AIRBORNE
        self._backend.text_colored(f"  {ground_text}", *ground_color)

        # === World ===
        self._backend.separator()
        self._backend.text_colored("World", *_COLOR_SECTION_HEADER)
        self._backend.text(f"  Entities: {entity_count}")

        if biome_name:
            self._backend.text(f"  Biome: {biome_name}")

        if chunk_info:
            self._backend.text(f"  {chunk_info}")

        if interaction_target:
            self._backend.text_colored(f"  Target: {interaction_target}", *_COLOR_TARGET)

        # === Actions ===
        self._backend.separator()

        if self._backend.button("Reset World", 110, 24):
            if self._on_reset_world:
                self._on_reset_world()

        self._backend.end_window()


# =============================================================================
# ConsoleWindow
# =============================================================================


class ConsoleWindow(UIComponent):
    """Developer console window rendered via ImGui.

    Displays the console output history, input line with cursor and
    inline autocomplete preview, and suggestion list. The actual input
    handling (character input, history navigation, autocomplete) is
    managed by the ``Console`` object; this component only reads the
    render data and draws it.

    Layout:
    - Top: scrollable output history with colored lines
    - Separator
    - Input line: "> text|cursor ghost_preview"
    - Autocomplete bar: "[selected]  other  other"
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

    def render(self, render_data: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        if not self._visible or render_data is None:
            return

        if not render_data.get("visible", False):
            return

        console_width = min(750, self._screen_width - 40)
        console_height = 320
        console_x = (self._screen_width - console_width) / 2
        console_y = 20.0

        config = render_data.get("config", {})

        self._backend.begin_window(
            "Developer Console",
            console_x, console_y,
            console_width, console_height,
            flags=_NO_RESIZE_FLAGS,
        )

        # --- Output history region ---
        output_height = console_height - 90
        self._backend.begin_child(
            "ConsoleOutput",
            console_width - 20, output_height,
            border=True,
        )

        lines = render_data.get("lines", [])
        for line_data in lines:
            text = line_data.get("text", "")
            color = line_data.get("color", (1.0, 1.0, 1.0, 1.0))
            r, g, b = color[0], color[1], color[2]
            a = color[3] if len(color) > 3 else 1.0
            self._backend.text_colored(text, r, g, b, a)

        self._backend.end_child()

        # --- Separator ---
        self._backend.separator()

        # --- Input line with cursor and inline preview ---
        input_text = render_data.get("input", "")
        cursor_pos = render_data.get("cursor_pos", len(input_text))
        input_color = config.get("input_color", _COLOR_CONSOLE_INPUT)
        prompt_color = config.get("prompt_color", _COLOR_CONSOLE_PROMPT)
        ac_color = config.get("autocomplete_color", _COLOR_CONSOLE_AC)

        # Build display: "> text_before_cursor|text_after_cursor ghost"
        before = input_text[:cursor_pos]
        after = input_text[cursor_pos:]
        inline_preview = render_data.get("inline_preview", "")

        # Prompt symbol
        self._backend.text_colored("> ", *prompt_color)
        self._backend.same_line()

        # Input text with cursor
        if after:
            display = f"{before}|{after}"
        else:
            display = f"{before}|"

        self._backend.text_colored(
            display,
            input_color[0], input_color[1], input_color[2],
            input_color[3] if len(input_color) > 3 else 1.0,
        )

        # Inline autocomplete ghost text
        if inline_preview:
            self._backend.same_line()
            self._backend.text_colored(
                inline_preview,
                ac_color[0], ac_color[1], ac_color[2],
                (ac_color[3] if len(ac_color) > 3 else 1.0) * 0.5,
            )

        # --- Autocomplete suggestions bar ---
        suggestions = render_data.get("suggestions", [])
        if suggestions:
            suggestion_idx = render_data.get("suggestion_index", 0)
            ac_hl_color = config.get("autocomplete_highlight", _COLOR_CONSOLE_AC_HL)
            parts = []
            for i, s in enumerate(suggestions):
                if i == suggestion_idx:
                    parts.append(f"[{s}]")
                else:
                    parts.append(s)

            self._backend.text_colored(
                "  " + "  ".join(parts),
                ac_hl_color[0], ac_hl_color[1], ac_hl_color[2],
                ac_hl_color[3] if len(ac_hl_color) > 3 else 1.0,
            )

        self._backend.end_window()


# =============================================================================
# NotificationStack
# =============================================================================


class NotificationStack(UIComponent):
    """Notification stack rendered in the top-right area.

    Displays timed notifications from the Console's notification system.
    Each notification fades out before expiring.
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

    def render(self, notifications: Optional[List[Dict[str, Any]]] = None, **kwargs: Any) -> None:
        if not self._visible or not notifications:
            return

        notif_width = 300
        notif_height = 32
        base_x = self._screen_width - notif_width - 15
        base_y = 220  # Below quest tracker

        for i, notif in enumerate(notifications):
            text = notif.get("text", "")
            icon = notif.get("icon", "")
            color = notif.get("color", (1.0, 1.0, 1.0, 1.0))
            opacity = notif.get("opacity", 1.0)

            display = f"{icon} {text}".strip() if icon else text
            y = base_y + i * (notif_height + 4)

            self._backend.begin_window(
                f"##Notif_{i}",
                base_x, y,
                notif_width, notif_height,
                flags=_NO_DECORATION_FLAGS,
            )

            r, g, b = color[0], color[1], color[2]
            self._backend.text_colored(display, r, g, b, opacity)

            self._backend.end_window()


# =============================================================================
# UI Manager
# =============================================================================


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
        self._main_menu = MainMenu(self._backend, screen_width, screen_height)
        self._world_creation = WorldCreationScreen(self._backend, screen_width, screen_height)
        self._save_load_screen = SaveLoadScreen(self._backend, screen_width, screen_height)
        self._hud = HUD(self._backend, screen_width, screen_height)
        self._dialogue_box = DialogueBox(self._backend, screen_width, screen_height)
        self._inventory_panel = InventoryPanel(self._backend, screen_width, screen_height)
        self._crafting_panel = CraftingPanel(self._backend, screen_width, screen_height)
        self._quest_log = QuestLog(self._backend, screen_width, screen_height)
        self._pause_menu = PauseMenu(self._backend, screen_width, screen_height)
        self._settings_panel = SettingsPanel(self._backend, screen_width, screen_height)
        self._debug_overlay = DebugOverlay(self._backend, screen_width, screen_height)
        self._console_window = ConsoleWindow(self._backend, screen_width, screen_height)
        self._notification_stack = NotificationStack(self._backend, screen_width, screen_height)

        # Console reference (set via set_console)
        self._console: Optional[Any] = None

        # Game world reference
        self._world: Optional["GameWorld"] = None

        # Current dialogue state
        self._in_dialogue: bool = False
        self._dialogue_npc: Optional["NPC"] = None

    def set_world(self, world: "GameWorld") -> None:
        """Set game world reference."""
        self._world = world

        # Update inventory and crafting panels with item definitions
        if world:
            definitions = {}
            for item_id in world._item_definitions:
                item_def = world.get_item_definition(item_id)
                if item_def:
                    definitions[item_id] = item_def.to_dict()
            self._inventory_panel.set_item_definitions(definitions)
            self._crafting_panel.set_item_definitions(definitions)

            # Pass recipes to crafting panel
            recipes = [r.to_dict() for r in world.get_all_recipes().values()]
            self._crafting_panel.set_recipes(recipes)

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

    def process_platform_event(self, event: bytes) -> None:
        """Forward a native platform event to the active UI backend."""
        self._backend.process_platform_event(event)

    # -------------------------------------------------------------------------
    # Component Rendering
    # -------------------------------------------------------------------------

    def render_hud(
        self,
        player: Optional["Player"] = None,
        interaction_target: Optional["InteractionTarget"] = None,
        harvest_result: Optional[Any] = None,
    ) -> None:
        """Render HUD elements.

        Parameters
        ----------
        player:
            The player entity for health, quest tracking.
        interaction_target:
            Optional InteractionTarget from PlayerController for showing
            "Press E to interact" prompts.
        harvest_result:
            Optional HarvestResult for showing harvest feedback.
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

        # Get time of day if available
        time_of_day = None
        if self._world:
            time_of_day = getattr(self._world, "_time_of_day", None)

        self._hud.render(
            player=player,
            active_quests=active_quests,
            interaction_target=interaction_target,
            time_of_day=time_of_day,
            harvest_result=harvest_result,
        )

    def render_dialogue(self) -> None:
        """Render dialogue box if in dialogue."""
        if self._in_dialogue:
            self._dialogue_box.render()

    def render_inventory(self, player: Optional["Player"] = None) -> None:
        """Render inventory panel."""
        self._inventory_panel.visible = True
        self._inventory_panel.render(player=player)

    def render_crafting(self, player: Optional["Player"] = None) -> None:
        """Render crafting panel."""
        self._crafting_panel.visible = True
        self._crafting_panel.render(player=player)

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

    def render_settings(
        self,
        debug_enabled: bool = False,
        vsync_enabled: bool = True,
    ) -> None:
        """Render settings panel."""
        self._settings_panel.visible = True
        self._settings_panel.render(
            debug_enabled=debug_enabled,
            vsync_enabled=vsync_enabled,
        )

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

    def render_console(self) -> None:
        """Render the developer console if it has data to display."""
        if self._console is None:
            return
        render_data = self._console.get_render_data()
        if render_data.get("visible", False):
            self._console_window.visible = True
            self._console_window.render(render_data=render_data)

    def render_notifications(self) -> None:
        """Render notification stack from console's notification system."""
        if self._console is None:
            return
        render_data = self._console.get_render_data()
        notifications = render_data.get("notifications", [])
        if notifications:
            self._notification_stack.render(notifications=notifications)

    def set_console(self, console: Any) -> None:
        """Set the Console instance for rendering.

        Parameters
        ----------
        console:
            A ``Console`` object whose ``get_render_data()`` method provides
            the state to render.
        """
        self._console = console

    # -------------------------------------------------------------------------
    # Dialogue Management
    # -------------------------------------------------------------------------

    def start_dialogue(self, npc: "NPC") -> None:
        """Start dialogue with an NPC."""
        self._in_dialogue = True
        self._dialogue_npc = npc
        self._dialogue_box.set_dialogue(
            npc,
            "Hello, traveler. What brings you here?",
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
    def crafting_panel(self) -> CraftingPanel:
        return self._crafting_panel

    @property
    def quest_log(self) -> QuestLog:
        return self._quest_log

    @property
    def pause_menu(self) -> PauseMenu:
        return self._pause_menu

    @property
    def settings_panel(self) -> SettingsPanel:
        return self._settings_panel

    @property
    def debug_overlay(self) -> DebugOverlay:
        return self._debug_overlay

    @property
    def console_window(self) -> ConsoleWindow:
        return self._console_window

    @property
    def notification_stack(self) -> NotificationStack:
        return self._notification_stack

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

    def set_settings_callbacks(
        self,
        on_toggle_debug: Optional[Callable[[], None]] = None,
        on_toggle_vsync: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set settings panel callbacks."""
        self._settings_panel.set_callbacks(
            on_toggle_debug=on_toggle_debug,
            on_toggle_vsync=on_toggle_vsync,
            on_close=on_close,
        )

    def set_inventory_callbacks(
        self,
        on_use: Optional[Callable[[str], None]] = None,
        on_drop: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Set inventory panel callbacks."""
        self._inventory_panel._on_item_use = on_use
        self._inventory_panel._on_item_drop = on_drop

    def set_crafting_callbacks(
        self,
        on_craft: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Set crafting panel callbacks."""
        self._crafting_panel._on_craft = on_craft

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

    # -------------------------------------------------------------------------
    # Main Menu & World Creation
    # -------------------------------------------------------------------------

    def render_main_menu(self) -> None:
        """Render the main menu."""
        self._main_menu.visible = True
        self._main_menu.render()

    def render_world_creation(
        self,
        input_manager: Optional["InputManager"] = None,
    ) -> None:
        """Render the world creation screen."""
        self._world_creation.visible = True
        self._world_creation.render(input_manager=input_manager)

    def render_save_load(self) -> None:
        """Render the save/load screen."""
        self._save_load_screen.visible = True
        self._save_load_screen.render()

    def set_main_menu_callbacks(
        self,
        on_new_world: Optional[Callable[[], None]] = None,
        on_load_game: Optional[Callable[[], None]] = None,
        on_settings: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set main menu callbacks."""
        self._main_menu._on_new_world = on_new_world
        self._main_menu._on_load_game = on_load_game
        self._main_menu._on_settings = on_settings
        self._main_menu._on_quit = on_quit

    def set_world_creation_callbacks(
        self,
        on_start: Optional[Callable[[int], None]] = None,
        on_back: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set world creation screen callbacks."""
        self._world_creation._on_start = on_start
        self._world_creation._on_back = on_back

    def set_save_load_callbacks(
        self,
        on_save: Optional[Callable[[str], None]] = None,
        on_load: Optional[Callable[[str], None]] = None,
        on_back: Optional[Callable[[], None]] = None,
    ) -> None:
        """Set save/load screen callbacks."""
        self._save_load_screen._on_save = on_save
        self._save_load_screen._on_load = on_load
        self._save_load_screen._on_back = on_back

    @property
    def main_menu(self) -> MainMenu:
        return self._main_menu

    @property
    def world_creation(self) -> WorldCreationScreen:
        return self._world_creation

    @property
    def save_load_screen(self) -> SaveLoadScreen:
        return self._save_load_screen
