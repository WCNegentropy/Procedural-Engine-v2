"""In-game console for the Procedural Engine.

This module provides an in-game console that allows players to enter commands
directly. Features include:

- Toggle with tilde (~) key
- Command input with history (up/down arrows)
- Autocomplete (tab)
- Output log with scrollback
- Command validation and error messages
- Help system

The console integrates with the CommandRegistry to execute commands and
provides visual feedback for success/failure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, TYPE_CHECKING

from procengine.commands.commands import registry, CommandResult

if TYPE_CHECKING:
    pass

__all__ = [
    "Console",
    "ConsoleConfig",
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
    
    # Colors (RGBA tuples, 0-1 range)
    background_color: tuple = (0.1, 0.1, 0.1, 0.8)
    text_color: tuple = (1.0, 1.0, 1.0, 1.0)
    error_color: tuple = (1.0, 0.3, 0.3, 1.0)
    success_color: tuple = (0.3, 1.0, 0.3, 1.0)
    input_color: tuple = (0.8, 0.8, 1.0, 1.0)
    autocomplete_color: tuple = (0.6, 0.6, 0.6, 1.0)


# =============================================================================
# Console Output Line
# =============================================================================


@dataclass
class ConsoleLine:
    """A single line of console output."""
    
    text: str
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    timestamp: float = 0.0


# =============================================================================
# Console
# =============================================================================


class Console:
    """In-game console for command input and output.
    
    The console provides a text interface for entering commands and viewing
    output. It integrates with the CommandRegistry for command execution
    and provides history, autocomplete, and visual feedback.
    
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
        
        # State
        self._visible: bool = False
        self._input_buffer: str = ""
        self._cursor_pos: int = 0
        
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
    # Input Handling
    # -------------------------------------------------------------------------
    
    def handle_char(self, char: str) -> None:
        """Handle a character input."""
        if not self._visible:
            return
        
        # Insert character at cursor position
        self._input_buffer = (
            self._input_buffer[:self._cursor_pos] +
            char +
            self._input_buffer[self._cursor_pos:]
        )
        self._cursor_pos += 1
        self._update_suggestions()
    
    def handle_backspace(self) -> None:
        """Handle backspace key."""
        if not self._visible or self._cursor_pos == 0:
            return
        
        self._input_buffer = (
            self._input_buffer[:self._cursor_pos - 1] +
            self._input_buffer[self._cursor_pos:]
        )
        self._cursor_pos -= 1
        self._update_suggestions()
    
    def handle_delete(self) -> None:
        """Handle delete key."""
        if not self._visible or self._cursor_pos >= len(self._input_buffer):
            return
        
        self._input_buffer = (
            self._input_buffer[:self._cursor_pos] +
            self._input_buffer[self._cursor_pos + 1:]
        )
        self._update_suggestions()
    
    def handle_left(self) -> None:
        """Handle left arrow key."""
        if self._cursor_pos > 0:
            self._cursor_pos -= 1
    
    def handle_right(self) -> None:
        """Handle right arrow key."""
        if self._cursor_pos < len(self._input_buffer):
            self._cursor_pos += 1
    
    def handle_home(self) -> None:
        """Handle home key."""
        self._cursor_pos = 0
    
    def handle_end(self) -> None:
        """Handle end key."""
        self._cursor_pos = len(self._input_buffer)
    
    def handle_up(self) -> None:
        """Handle up arrow (history navigation)."""
        if not self._history:
            return
        
        if self._history_index == -1:
            # Starting to browse history, save current input
            self._history_temp = self._input_buffer
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        
        self._input_buffer = self._history[self._history_index]
        self._cursor_pos = len(self._input_buffer)
        self._clear_suggestions()
    
    def handle_down(self) -> None:
        """Handle down arrow (history navigation)."""
        if self._history_index == -1:
            return
        
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._input_buffer = self._history[self._history_index]
        else:
            # Return to original input
            self._history_index = -1
            self._input_buffer = self._history_temp
        
        self._cursor_pos = len(self._input_buffer)
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
            
            # Replace input with suggestion
            # Find the command part (before any arguments)
            parts = self._input_buffer.split()
            if parts:
                parts[0] = suggestion
                self._input_buffer = " ".join(parts)
            else:
                self._input_buffer = suggestion
            
            self._cursor_pos = len(self._input_buffer)
            
            # Move to next suggestion
            self._suggestion_index = (self._suggestion_index + 1) % len(self._suggestions)
    
    def handle_escape(self) -> None:
        """Handle escape key."""
        if self._suggestions:
            self._clear_suggestions()
        else:
            self.close()
    
    def submit(self) -> None:
        """Submit the current input for execution."""
        if not self._input_buffer.strip():
            return
        
        command = self._input_buffer.strip()
        
        # Add to history (avoid duplicates)
        if not self._history or self._history[-1] != command:
            self._history.append(command)
        
        # Echo command if configured
        if self.config.echo_commands:
            self._add_line(f"> {command}", self.config.input_color)
        
        # Execute command
        result = registry.execute(command)
        
        # Show result
        if result.message:
            color = self.config.success_color if result.success else self.config.error_color
            for line in result.message.split("\n"):
                self._add_line(line, color)
        
        # Handle special result data
        if result.data and result.data.get("clear"):
            self.clear()
        
        # Clear input
        self._input_buffer = ""
        self._cursor_pos = 0
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
    
    def clear(self) -> None:
        """Clear the console output."""
        self._output.clear()
        self._scroll_offset = 0
    
    def _add_line(self, text: str, color: tuple) -> None:
        """Add a line to the output buffer."""
        import time
        
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
    # Autocomplete
    # -------------------------------------------------------------------------
    
    def _update_suggestions(self) -> None:
        """Update autocomplete suggestions based on input."""
        # Get partial command (first word)
        parts = self._input_buffer.split()
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
    # State Access
    # -------------------------------------------------------------------------
    
    @property
    def input_buffer(self) -> str:
        """Get current input buffer."""
        return self._input_buffer
    
    @property
    def cursor_position(self) -> int:
        """Get cursor position in input buffer."""
        return self._cursor_pos
    
    @property
    def output_lines(self) -> List[ConsoleLine]:
        """Get visible output lines."""
        start = max(0, len(self._output) - self.config.visible_lines - self._scroll_offset)
        end = len(self._output) - self._scroll_offset
        return self._output[start:end]
    
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
        self._input_buffer = text
        self._cursor_pos = len(text)
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
        - lines: List of output lines with text and color
        - suggestions: Autocomplete suggestions
        - config: Console configuration
        """
        return {
            "visible": self._visible,
            "input": self._input_buffer,
            "cursor_pos": self._cursor_pos,
            "lines": [
                {"text": line.text, "color": line.color}
                for line in self.output_lines
            ],
            "suggestions": self._suggestions[:5],  # Limit suggestions shown
            "suggestion_index": self._suggestion_index % max(1, len(self._suggestions)),
            "config": {
                "background_color": self.config.background_color,
                "text_color": self.config.text_color,
                "input_color": self.config.input_color,
                "autocomplete_color": self.config.autocomplete_color,
                "opacity": self.config.opacity,
            },
        }
