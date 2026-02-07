"""In-game console for the Procedural Engine.

This module provides an in-game console that allows players to enter commands
directly. Features include:

- Toggle with tilde (~) key
- Real text input with cursor, selection, and word operations
- Command input with history (up/down arrows)
- Autocomplete with inline preview and tab cycling
- Output log with scrollback and filtering
- Command validation and error messages
- Help system
- Notification feed for game events

The console integrates with the CommandRegistry to execute commands and
provides visual feedback for success/failure.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from procengine.commands.commands import registry, CommandResult

if TYPE_CHECKING:
    pass

__all__ = [
    "Console",
    "ConsoleConfig",
    "ConsoleLine",
    "Notification",
    "NotificationType",
    "TextInputBuffer",
]


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class ConsoleConfig:
    """Configuration for the console."""

    # Appearance
    max_lines: int = 100          # Maximum lines in output buffer
    visible_lines: int = 10       # Number of visible lines
    font_size: int = 14           # Font size in pixels
    opacity: float = 0.8          # Background opacity (0-1)

    # Behavior
    persist_history: bool = True  # Save history between sessions
    echo_commands: bool = True    # Echo commands to output
    timestamp: bool = False       # Show timestamps

    # Autocomplete
    max_suggestions: int = 8      # Max autocomplete suggestions to display
    inline_preview: bool = True   # Show inline autocomplete preview

    # Notifications
    notification_duration: float = 4.0   # Seconds before notifications fade
    max_notifications: int = 5           # Max simultaneous notifications

    # Colors (RGBA tuples, 0-1 range)
    background_color: tuple = (0.08, 0.08, 0.10, 0.92)
    text_color: tuple = (0.88, 0.88, 0.88, 1.0)
    error_color: tuple = (1.0, 0.35, 0.35, 1.0)
    success_color: tuple = (0.35, 1.0, 0.45, 1.0)
    warning_color: tuple = (1.0, 0.82, 0.30, 1.0)
    input_color: tuple = (0.75, 0.80, 1.0, 1.0)
    autocomplete_color: tuple = (0.55, 0.55, 0.65, 1.0)
    autocomplete_highlight: tuple = (0.85, 0.85, 1.0, 1.0)
    prompt_color: tuple = (0.50, 0.70, 1.0, 1.0)
    timestamp_color: tuple = (0.45, 0.45, 0.45, 1.0)


# =============================================================================
# Console Output Line
# =============================================================================


@dataclass
class ConsoleLine:
    """A single line of console output."""

    text: str
    color: tuple = (0.88, 0.88, 0.88, 1.0)
    timestamp: float = 0.0


# =============================================================================
# Notification System
# =============================================================================


class NotificationType(Enum):
    """Type of notification for styling."""

    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()
    QUEST = auto()
    ITEM = auto()
    SYSTEM = auto()


@dataclass
class Notification:
    """A timed notification message displayed outside the console."""

    text: str
    notification_type: NotificationType = NotificationType.INFO
    created_at: float = 0.0
    duration: float = 4.0
    icon: str = ""

    @property
    def is_expired(self) -> bool:
        """Check if this notification has expired."""
        return (time.time() - self.created_at) >= self.duration

    @property
    def opacity(self) -> float:
        """Get current opacity (fades out in last second)."""
        elapsed = time.time() - self.created_at
        remaining = self.duration - elapsed
        if remaining <= 0:
            return 0.0
        if remaining < 1.0:
            return remaining
        return 1.0

    def get_color(self) -> tuple:
        """Get RGBA color based on notification type."""
        colors = {
            NotificationType.INFO: (0.88, 0.88, 0.88, 1.0),
            NotificationType.SUCCESS: (0.35, 1.0, 0.45, 1.0),
            NotificationType.WARNING: (1.0, 0.82, 0.30, 1.0),
            NotificationType.ERROR: (1.0, 0.35, 0.35, 1.0),
            NotificationType.QUEST: (1.0, 0.85, 0.30, 1.0),
            NotificationType.ITEM: (0.55, 0.85, 1.0, 1.0),
            NotificationType.SYSTEM: (0.70, 0.70, 0.80, 1.0),
        }
        base = colors.get(self.notification_type, colors[NotificationType.INFO])
        return (base[0], base[1], base[2], base[3] * self.opacity)


# =============================================================================
# Text Input Buffer
# =============================================================================


class TextInputBuffer:
    """Real text input buffer with cursor, selection, and word operations.

    Provides a proper text editing experience beyond simple keydown
    mapping. Supports:
    - Cursor movement with Home/End/Ctrl+Left/Right
    - Selection via Shift+movement
    - Word-level delete (Ctrl+Backspace/Delete)
    - Clipboard-like paste support
    - Undo buffer (basic)
    """

    def __init__(self, initial_text: str = "") -> None:
        self._text: str = initial_text
        self._cursor: int = len(initial_text)
        self._selection_start: int = -1  # -1 = no selection
        self._undo_stack: List[Tuple[str, int]] = []
        self._max_undo: int = 32

    @property
    def text(self) -> str:
        """Get current text content."""
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        """Set text content and move cursor to end."""
        self._push_undo()
        self._text = value
        self._cursor = len(value)
        self._selection_start = -1

    @property
    def cursor(self) -> int:
        """Get cursor position."""
        return self._cursor

    @cursor.setter
    def cursor(self, pos: int) -> None:
        """Set cursor position (clamped)."""
        self._cursor = max(0, min(pos, len(self._text)))

    @property
    def has_selection(self) -> bool:
        """Check if text is selected."""
        return self._selection_start >= 0 and self._selection_start != self._cursor

    @property
    def selection_range(self) -> Tuple[int, int]:
        """Get (start, end) of selection, normalized."""
        if not self.has_selection:
            return (self._cursor, self._cursor)
        return (min(self._selection_start, self._cursor),
                max(self._selection_start, self._cursor))

    @property
    def selected_text(self) -> str:
        """Get selected text."""
        if not self.has_selection:
            return ""
        start, end = self.selection_range
        return self._text[start:end]

    def _push_undo(self) -> None:
        """Save current state to undo stack."""
        self._undo_stack.append((self._text, self._cursor))
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack = self._undo_stack[-self._max_undo:]

    def undo(self) -> None:
        """Undo last text change."""
        if self._undo_stack:
            self._text, self._cursor = self._undo_stack.pop()
            self._selection_start = -1

    def insert(self, text: str) -> None:
        """Insert text at cursor, replacing selection if any."""
        self._push_undo()
        if self.has_selection:
            start, end = self.selection_range
            self._text = self._text[:start] + text + self._text[end:]
            self._cursor = start + len(text)
            self._selection_start = -1
        else:
            self._text = self._text[:self._cursor] + text + self._text[self._cursor:]
            self._cursor += len(text)

    def backspace(self) -> None:
        """Delete character before cursor or selected text."""
        if self.has_selection:
            self._delete_selection()
            return
        if self._cursor == 0:
            return
        self._push_undo()
        self._text = self._text[:self._cursor - 1] + self._text[self._cursor:]
        self._cursor -= 1

    def delete(self) -> None:
        """Delete character after cursor or selected text."""
        if self.has_selection:
            self._delete_selection()
            return
        if self._cursor >= len(self._text):
            return
        self._push_undo()
        self._text = self._text[:self._cursor] + self._text[self._cursor + 1:]

    def backspace_word(self) -> None:
        """Delete word before cursor (Ctrl+Backspace)."""
        if self.has_selection:
            self._delete_selection()
            return
        if self._cursor == 0:
            return
        self._push_undo()
        end = self._cursor
        # Skip trailing whitespace
        pos = end - 1
        while pos > 0 and self._text[pos] == " ":
            pos -= 1
        # Skip word characters (non-space)
        while pos > 0 and self._text[pos - 1] != " ":
            pos -= 1
        self._text = self._text[:pos] + self._text[end:]
        self._cursor = pos

    def delete_word(self) -> None:
        """Delete word after cursor (Ctrl+Delete)."""
        if self.has_selection:
            self._delete_selection()
            return
        if self._cursor >= len(self._text):
            return
        self._push_undo()
        start = self._cursor
        pos = start
        # Skip leading whitespace
        while pos < len(self._text) and self._text[pos] == " ":
            pos += 1
        # Skip word characters
        while pos < len(self._text) and self._text[pos] != " ":
            pos += 1
        self._text = self._text[:start] + self._text[pos:]

    def move_left(self, select: bool = False) -> None:
        """Move cursor left one character."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        if self._cursor > 0:
            self._cursor -= 1

    def move_right(self, select: bool = False) -> None:
        """Move cursor right one character."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        if self._cursor < len(self._text):
            self._cursor += 1

    def move_word_left(self, select: bool = False) -> None:
        """Move cursor left one word (Ctrl+Left)."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        if self._cursor == 0:
            return
        pos = self._cursor - 1
        # Skip whitespace
        while pos > 0 and self._text[pos] == " ":
            pos -= 1
        # Skip word
        while pos > 0 and self._text[pos - 1] != " ":
            pos -= 1
        self._cursor = pos

    def move_word_right(self, select: bool = False) -> None:
        """Move cursor right one word (Ctrl+Right)."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        if self._cursor >= len(self._text):
            return
        pos = self._cursor
        # Skip whitespace
        while pos < len(self._text) and self._text[pos] == " ":
            pos += 1
        # Skip word
        while pos < len(self._text) and self._text[pos] != " ":
            pos += 1
        self._cursor = pos

    def move_home(self, select: bool = False) -> None:
        """Move cursor to beginning."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        self._cursor = 0

    def move_end(self, select: bool = False) -> None:
        """Move cursor to end."""
        if select:
            if self._selection_start < 0:
                self._selection_start = self._cursor
        else:
            self._selection_start = -1
        self._cursor = len(self._text)

    def select_all(self) -> None:
        """Select all text."""
        self._selection_start = 0
        self._cursor = len(self._text)

    def clear(self) -> None:
        """Clear all text."""
        self._push_undo()
        self._text = ""
        self._cursor = 0
        self._selection_start = -1

    def _delete_selection(self) -> None:
        """Delete currently selected text."""
        if not self.has_selection:
            return
        self._push_undo()
        start, end = self.selection_range
        self._text = self._text[:start] + self._text[end:]
        self._cursor = start
        self._selection_start = -1

    def get_display_parts(self) -> Dict[str, object]:
        """Get text parts for rendering with cursor and selection.

        Returns
        -------
        Dict with keys:
            before_cursor: Text before cursor
            at_cursor: Character at cursor (or empty if at end)
            after_cursor: Text after cursor
            selection_start: Start index of selection (-1 if none)
            selection_end: End index of selection (-1 if none)
        """
        sel_start, sel_end = (-1, -1) if not self.has_selection else self.selection_range
        return {
            "before_cursor": self._text[:self._cursor],
            "at_cursor": self._text[self._cursor] if self._cursor < len(self._text) else "",
            "after_cursor": self._text[self._cursor + 1:] if self._cursor < len(self._text) else "",
            "selection_start": sel_start,
            "selection_end": sel_end,
        }


# =============================================================================
# Console
# =============================================================================


class Console:
    """In-game console for command input and output.

    The console provides a full text editing interface for entering
    commands and viewing output. It integrates with the CommandRegistry
    for command execution and provides history, autocomplete, and
    visual feedback.

    Features:
    - Real text input with cursor positioning and word operations
    - Tab-completion with inline preview
    - Persistent command history with search
    - Scrollable output with colored messages
    - Notification system for game events
    - Command usage hints on errors

    Usage:
        console = Console()
        console.open()
        console.handle_char('h')
        console.handle_char('e')
        console.handle_char('l')
        console.handle_char('p')
        console.submit()  # Executes 'help'
    """

    def __init__(self, config: Optional[ConsoleConfig] = None) -> None:
        """Initialize the console."""
        self.config = config or ConsoleConfig()

        # Real text input buffer
        self._input = TextInputBuffer()

        # State
        self._visible: bool = False

        # Output
        self._output: List[ConsoleLine] = []
        self._scroll_offset: int = 0

        # History
        self._history: List[str] = []
        self._history_index: int = -1
        self._history_temp: str = ""  # Store current input when browsing history

        # Autocomplete
        self._suggestions: List[str] = []
        self._suggestion_index: int = 0

        # Notifications (displayed outside console)
        self._notifications: List[Notification] = []

        # Callbacks
        self.on_open: Optional[Callable[[], None]] = None
        self.on_close: Optional[Callable[[], None]] = None
        self.on_submit: Optional[Callable[[str], None]] = None

    # -------------------------------------------------------------------------
    # Visibility
    # -------------------------------------------------------------------------

    @property
    def is_visible(self) -> bool:
        """Whether the console is visible."""
        return self._visible

    def open(self) -> None:
        """Open the console."""
        if not self._visible:
            self._visible = True
            registry.console_open = True
            if self.on_open:
                self.on_open()

    def close(self) -> None:
        """Close the console."""
        if self._visible:
            self._visible = False
            registry.console_open = False
            self._clear_suggestions()
            if self.on_close:
                self.on_close()

    def toggle(self) -> None:
        """Toggle console visibility."""
        if self._visible:
            self.close()
        else:
            self.open()

    # -------------------------------------------------------------------------
    # Input Handling — delegates to TextInputBuffer
    # -------------------------------------------------------------------------

    def handle_char(self, char: str) -> None:
        """Handle a character input."""
        if not self._visible:
            return
        self._input.insert(char)
        self._update_suggestions()

    def handle_backspace(self) -> None:
        """Handle backspace key."""
        if not self._visible or (self._input.cursor == 0 and not self._input.has_selection):
            return
        self._input.backspace()
        self._update_suggestions()

    def handle_delete(self) -> None:
        """Handle delete key."""
        if not self._visible:
            return
        self._input.delete()
        self._update_suggestions()

    def handle_backspace_word(self) -> None:
        """Handle Ctrl+Backspace (delete word before cursor)."""
        if not self._visible:
            return
        self._input.backspace_word()
        self._update_suggestions()

    def handle_delete_word(self) -> None:
        """Handle Ctrl+Delete (delete word after cursor)."""
        if not self._visible:
            return
        self._input.delete_word()
        self._update_suggestions()

    def handle_left(self, select: bool = False) -> None:
        """Handle left arrow key."""
        self._input.move_left(select)

    def handle_right(self, select: bool = False) -> None:
        """Handle right arrow key."""
        self._input.move_right(select)

    def handle_word_left(self, select: bool = False) -> None:
        """Handle Ctrl+Left (move cursor left one word)."""
        self._input.move_word_left(select)

    def handle_word_right(self, select: bool = False) -> None:
        """Handle Ctrl+Right (move cursor right one word)."""
        self._input.move_word_right(select)

    def handle_home(self, select: bool = False) -> None:
        """Handle home key."""
        self._input.move_home(select)

    def handle_end(self, select: bool = False) -> None:
        """Handle end key."""
        self._input.move_end(select)

    def handle_select_all(self) -> None:
        """Handle Ctrl+A (select all text)."""
        self._input.select_all()

    def handle_undo(self) -> None:
        """Handle Ctrl+Z (undo)."""
        self._input.undo()
        self._update_suggestions()

    def handle_up(self) -> None:
        """Handle up arrow (history navigation)."""
        if not self._history:
            return

        if self._history_index == -1:
            # Starting to browse history, save current input
            self._history_temp = self._input.text
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1

        self._input.text = self._history[self._history_index]
        self._clear_suggestions()

    def handle_down(self) -> None:
        """Handle down arrow (history navigation)."""
        if self._history_index == -1:
            return

        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._input.text = self._history[self._history_index]
        else:
            # Return to original input
            self._history_index = -1
            self._input.text = self._history_temp

        self._update_suggestions()

    def handle_tab(self) -> None:
        """Handle tab (autocomplete)."""
        if not self._suggestions:
            self._update_suggestions()
            if not self._suggestions:
                return

        # Cycle through suggestions
        if self._suggestions:
            suggestion = self._suggestions[self._suggestion_index]

            # Replace the command part (first word) with the suggestion
            parts = self._input.text.split()
            if parts:
                parts[0] = suggestion
                self._input.text = " ".join(parts)
            else:
                self._input.text = suggestion

            # Move to next suggestion
            self._suggestion_index = (self._suggestion_index + 1) % len(self._suggestions)

    def handle_escape(self) -> None:
        """Handle escape key."""
        if self._suggestions:
            self._clear_suggestions()
        else:
            self.close()

    def handle_paste(self, text: str) -> None:
        """Handle paste operation (Ctrl+V or system paste).

        Parameters
        ----------
        text:
            The text to paste. Multi-line text has newlines stripped.
        """
        if not self._visible:
            return
        # Strip newlines for single-line console input
        clean = text.replace("\n", " ").replace("\r", "")
        self._input.insert(clean)
        self._update_suggestions()

    def submit(self) -> None:
        """Submit the current input for execution."""
        command = self._input.text.strip()
        if not command:
            return

        # Add to history (avoid duplicates)
        if not self._history or self._history[-1] != command:
            self._history.append(command)

        # Echo command if configured
        if self.config.echo_commands:
            self._add_line(f"> {command}", self.config.prompt_color)

        # Execute command
        result = registry.execute(command)

        # Show result
        if result.message:
            color = self.config.success_color if result.success else self.config.error_color
            for line in result.message.split("\n"):
                self._add_line(line, color)

        # Show usage hint on failure
        if not result.success and result.data and result.data.get("command"):
            cmd = registry.get(result.data["command"])
            if cmd:
                self._add_line(f"  Usage: {cmd.get_usage()}", self.config.autocomplete_color)

        # Handle special result data
        if result.data and result.data.get("clear"):
            self.clear()

        # Clear input
        self._input.clear()
        self._history_index = -1
        self._clear_suggestions()

        # Callback
        if self.on_submit:
            self.on_submit(command)

    # -------------------------------------------------------------------------
    # Output
    # -------------------------------------------------------------------------

    def print(self, text: str, color: Optional[tuple] = None) -> None:
        """Print text to the console."""
        color = color or self.config.text_color
        for line in text.split("\n"):
            self._add_line(line, color)

    def print_error(self, text: str) -> None:
        """Print error text to the console."""
        self.print(text, self.config.error_color)

    def print_success(self, text: str) -> None:
        """Print success text to the console."""
        self.print(text, self.config.success_color)

    def print_warning(self, text: str) -> None:
        """Print warning text to the console."""
        self.print(text, self.config.warning_color)

    def clear(self) -> None:
        """Clear the console output."""
        self._output.clear()
        self._scroll_offset = 0

    def _add_line(self, text: str, color: tuple) -> None:
        """Add a line to the output buffer."""
        self._output.append(ConsoleLine(
            text=text,
            color=color,
            timestamp=time.time(),
        ))

        # Trim output to max lines
        if len(self._output) > self.config.max_lines:
            self._output = self._output[-self.config.max_lines:]

        # Auto-scroll to bottom
        self._scroll_offset = 0

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll output up."""
        max_scroll = max(0, len(self._output) - self.config.visible_lines)
        self._scroll_offset = min(max_scroll, self._scroll_offset + lines)

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll output down."""
        self._scroll_offset = max(0, self._scroll_offset - lines)

    # -------------------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------------------

    def notify(
        self,
        text: str,
        notification_type: NotificationType = NotificationType.INFO,
        duration: Optional[float] = None,
        icon: str = "",
    ) -> None:
        """Show a notification message (displayed outside the console).

        Parameters
        ----------
        text:
            Notification message text.
        notification_type:
            Type of notification for color/icon styling.
        duration:
            Display duration in seconds. Uses config default if None.
        icon:
            Optional icon prefix string.
        """
        dur = duration if duration is not None else self.config.notification_duration

        self._notifications.append(Notification(
            text=text,
            notification_type=notification_type,
            created_at=time.time(),
            duration=dur,
            icon=icon,
        ))

        # Trim to max notifications
        if len(self._notifications) > self.config.max_notifications:
            self._notifications = self._notifications[-self.config.max_notifications:]

    def get_active_notifications(self) -> List[Notification]:
        """Get non-expired notifications."""
        self._notifications = [n for n in self._notifications if not n.is_expired]
        return self._notifications.copy()

    def clear_notifications(self) -> None:
        """Clear all notifications."""
        self._notifications.clear()

    # -------------------------------------------------------------------------
    # Autocomplete
    # -------------------------------------------------------------------------

    def _update_suggestions(self) -> None:
        """Update autocomplete suggestions based on input."""
        parts = self._input.text.split()
        if not parts:
            self._suggestions = registry.autocomplete("")
        else:
            # Only autocomplete the command name (first word)
            self._suggestions = registry.autocomplete(parts[0])

        self._suggestion_index = 0

    def _clear_suggestions(self) -> None:
        """Clear autocomplete suggestions."""
        self._suggestions.clear()
        self._suggestion_index = 0

    # -------------------------------------------------------------------------
    # State Access (backwards-compatible properties)
    # -------------------------------------------------------------------------

    @property
    def input_buffer(self) -> str:
        """Get current input buffer."""
        return self._input.text

    @property
    def cursor_position(self) -> int:
        """Get cursor position in input buffer."""
        return self._input.cursor

    @property
    def output_lines(self) -> List[ConsoleLine]:
        """Get visible output lines."""
        start = max(0, len(self._output) - self.config.visible_lines - self._scroll_offset)
        end = len(self._output) - self._scroll_offset
        return self._output[start:end]

    @property
    def all_output(self) -> List[ConsoleLine]:
        """Get all output lines (not just visible)."""
        return self._output.copy()

    @property
    def suggestions(self) -> List[str]:
        """Get current autocomplete suggestions."""
        return self._suggestions

    @property
    def history(self) -> List[str]:
        """Get command history."""
        return self._history.copy()

    def set_input(self, text: str) -> None:
        """Set input buffer directly."""
        self._input.text = text
        self._update_suggestions()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def save_history(self, path: str) -> None:
        """Save command history to file."""
        try:
            with open(path, "w") as f:
                for cmd in self._history[-100:]:  # Save last 100 commands
                    f.write(cmd + "\n")
        except Exception:
            pass

    def load_history(self, path: str) -> None:
        """Load command history from file."""
        try:
            with open(path, "r") as f:
                self._history = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Rendering (for UI integration)
    # -------------------------------------------------------------------------

    def get_render_data(self) -> dict:
        """Get data needed to render the console.

        Returns a dictionary with all information needed for UI rendering:
        - visible: Whether console is visible
        - input: Current input text
        - cursor_pos: Cursor position
        - has_selection: Whether text is selected
        - selection_start/end: Selection range
        - lines: List of output lines with text and color
        - suggestions: Autocomplete suggestions
        - suggestion_index: Currently highlighted suggestion
        - inline_preview: Preview text for autocomplete
        - notifications: Active notification messages
        - config: Console configuration
        """
        # Build inline autocomplete preview
        inline_preview = ""
        if (self.config.inline_preview
                and self._suggestions
                and self._input.text
                and not self._input.text.endswith(" ")):
            top = self._suggestions[self._suggestion_index % len(self._suggestions)]
            partial = self._input.text.split()[0] if self._input.text.split() else ""
            if top.startswith(partial) and len(top) > len(partial):
                inline_preview = top[len(partial):]

        return {
            "visible": self._visible,
            "input": self._input.text,
            "cursor_pos": self._input.cursor,
            "has_selection": self._input.has_selection,
            "selection_start": self._input.selection_range[0] if self._input.has_selection else -1,
            "selection_end": self._input.selection_range[1] if self._input.has_selection else -1,
            "lines": [
                {"text": line.text, "color": line.color, "timestamp": line.timestamp}
                for line in self.output_lines
            ],
            "suggestions": self._suggestions[:self.config.max_suggestions],
            "suggestion_index": self._suggestion_index % max(1, len(self._suggestions)),
            "inline_preview": inline_preview,
            "notifications": [
                {
                    "text": n.text,
                    "icon": n.icon,
                    "color": n.get_color(),
                    "opacity": n.opacity,
                    "type": n.notification_type.name,
                }
                for n in self.get_active_notifications()
            ],
            "config": {
                "background_color": self.config.background_color,
                "text_color": self.config.text_color,
                "input_color": self.config.input_color,
                "prompt_color": self.config.prompt_color,
                "autocomplete_color": self.config.autocomplete_color,
                "autocomplete_highlight": self.config.autocomplete_highlight,
                "timestamp_color": self.config.timestamp_color,
                "opacity": self.config.opacity,
            },
        }
