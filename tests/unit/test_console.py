"""Tests for the console module.

Tests cover:
- Console visibility toggling
- Input handling (characters, backspace, arrows)
- Command history navigation
- Autocomplete functionality
- Output buffer management
- Command submission and execution
- TextInputBuffer (word operations, selection, undo)
- Notification system
"""
import pytest
import tempfile
import os
import time

from procengine.commands.console import (
    Console,
    ConsoleConfig,
    ConsoleLine,
    TextInputBuffer,
    Notification,
    NotificationType,
)
from procengine.commands.commands import registry, command, AccessLevel


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def console():
    """Create a fresh console for testing."""
    return Console()


@pytest.fixture
def clean_registry():
    """Provide a clean registry for console tests."""
    original_commands = registry._commands.copy()
    original_aliases = registry._aliases.copy()
    
    yield registry
    
    registry._commands = original_commands
    registry._aliases = original_aliases


# =============================================================================
# Visibility Tests
# =============================================================================


class TestConsoleVisibility:
    """Tests for console visibility."""
    
    def test_initially_hidden(self, console):
        """Test console is hidden by default."""
        assert not console.is_visible
    
    def test_open(self, console):
        """Test opening the console."""
        console.open()
        assert console.is_visible
        assert registry.console_open
    
    def test_close(self, console):
        """Test closing the console."""
        console.open()
        console.close()
        assert not console.is_visible
        assert not registry.console_open
    
    def test_toggle(self, console):
        """Test toggling the console."""
        assert not console.is_visible
        
        console.toggle()
        assert console.is_visible
        
        console.toggle()
        assert not console.is_visible
    
    def test_open_callback(self, console):
        """Test open callback is called."""
        callback_called = [False]
        
        def on_open():
            callback_called[0] = True
        
        console.on_open = on_open
        console.open()
        
        assert callback_called[0]
    
    def test_close_callback(self, console):
        """Test close callback is called."""
        callback_called = [False]
        
        def on_close():
            callback_called[0] = True
        
        console.on_close = on_close
        console.open()
        console.close()
        
        assert callback_called[0]


# =============================================================================
# Input Handling Tests
# =============================================================================


class TestConsoleInput:
    """Tests for console input handling."""
    
    def test_handle_char_when_visible(self, console):
        """Test character input when console is visible."""
        console.open()
        
        console.handle_char('h')
        console.handle_char('e')
        console.handle_char('l')
        console.handle_char('p')
        
        assert console.input_buffer == "help"
        assert console.cursor_position == 4
    
    def test_handle_char_when_hidden(self, console):
        """Test character input is ignored when console is hidden."""
        console.handle_char('h')
        
        assert console.input_buffer == ""
    
    def test_backspace(self, console):
        """Test backspace removes character."""
        console.open()
        console.handle_char('a')
        console.handle_char('b')
        console.handle_char('c')
        
        console.handle_backspace()
        
        assert console.input_buffer == "ab"
        assert console.cursor_position == 2
    
    def test_backspace_at_start(self, console):
        """Test backspace at start of input does nothing."""
        console.open()
        
        console.handle_backspace()
        
        assert console.input_buffer == ""
        assert console.cursor_position == 0
    
    def test_delete(self, console):
        """Test delete removes character after cursor."""
        console.open()
        console.handle_char('a')
        console.handle_char('b')
        console.handle_char('c')
        
        # Move cursor to middle
        console.handle_left()
        console.handle_left()
        
        console.handle_delete()
        
        assert console.input_buffer == "ac"
    
    def test_cursor_movement(self, console):
        """Test cursor movement with arrow keys."""
        console.open()
        console.handle_char('a')
        console.handle_char('b')
        console.handle_char('c')
        
        # Cursor at end (position 3)
        assert console.cursor_position == 3
        
        console.handle_left()
        assert console.cursor_position == 2
        
        console.handle_left()
        assert console.cursor_position == 1
        
        console.handle_right()
        assert console.cursor_position == 2
    
    def test_cursor_home_end(self, console):
        """Test home and end keys."""
        console.open()
        console.handle_char('a')
        console.handle_char('b')
        console.handle_char('c')
        
        console.handle_home()
        assert console.cursor_position == 0
        
        console.handle_end()
        assert console.cursor_position == 3
    
    def test_cursor_bounds(self, console):
        """Test cursor stays within bounds."""
        console.open()
        console.handle_char('a')
        
        # Try to go past end
        console.handle_right()
        console.handle_right()
        assert console.cursor_position == 1
        
        # Try to go before start
        console.handle_left()
        console.handle_left()
        console.handle_left()
        assert console.cursor_position == 0
    
    def test_insert_at_cursor(self, console):
        """Test inserting character at cursor position."""
        console.open()
        console.handle_char('a')
        console.handle_char('c')
        
        # Move cursor between 'a' and 'c'
        console.handle_left()
        
        # Insert 'b'
        console.handle_char('b')
        
        assert console.input_buffer == "abc"


# =============================================================================
# History Tests
# =============================================================================


class TestConsoleHistory:
    """Tests for command history navigation."""
    
    def test_history_after_submit(self, console, clean_registry):
        """Test command is added to history after submit."""
        @command(name="test.hist", access=AccessLevel.PUBLIC)
        def hist_cmd():
            return ""
        
        console.open()
        console.set_input("test.hist")
        console.submit()
        
        assert "test.hist" in console.history
    
    def test_navigate_history_up(self, console, clean_registry):
        """Test navigating history with up arrow."""
        @command(name="test.nav", access=AccessLevel.PUBLIC)
        def nav_cmd():
            return ""
        
        console.open()
        
        # Submit several commands
        console.set_input("test.nav 1")
        console.submit()
        console.set_input("test.nav 2")
        console.submit()
        console.set_input("test.nav 3")
        console.submit()
        
        # Navigate up through history
        console.handle_up()
        assert console.input_buffer == "test.nav 3"
        
        console.handle_up()
        assert console.input_buffer == "test.nav 2"
        
        console.handle_up()
        assert console.input_buffer == "test.nav 1"
    
    def test_navigate_history_down(self, console, clean_registry):
        """Test navigating history with down arrow."""
        @command(name="test.navdown", access=AccessLevel.PUBLIC)
        def navdown_cmd():
            return ""
        
        console.open()
        
        console.set_input("test.navdown 1")
        console.submit()
        console.set_input("test.navdown 2")
        console.submit()
        
        # Type new input
        console.set_input("new input")
        
        # Go up, then down
        console.handle_up()
        console.handle_up()
        console.handle_down()
        assert console.input_buffer == "test.navdown 2"
        
        # Going down past end returns to original input
        console.handle_down()
        assert console.input_buffer == "new input"
    
    def test_empty_history(self, console):
        """Test navigation with empty history."""
        console.open()
        
        # Should do nothing with empty history
        console.handle_up()
        assert console.input_buffer == ""
        
        console.handle_down()
        assert console.input_buffer == ""


# =============================================================================
# Autocomplete Tests
# =============================================================================


class TestConsoleAutocomplete:
    """Tests for autocomplete functionality."""
    
    def test_autocomplete_with_tab(self, console, clean_registry):
        """Test autocomplete with tab key."""
        @command(name="test.autocomplete", access=AccessLevel.PUBLIC)
        def ac_cmd():
            return ""
        
        console.open()
        console.set_input("test.auto")
        
        console.handle_tab()
        
        assert console.input_buffer == "test.autocomplete"
    
    def test_autocomplete_cycle(self, console, clean_registry):
        """Test cycling through multiple autocomplete suggestions."""
        @command(name="test.alpha", access=AccessLevel.PUBLIC)
        def alpha_cmd():
            return ""
        
        @command(name="test.another", access=AccessLevel.PUBLIC)
        def another_cmd():
            return ""
        
        console.open()
        console.set_input("test.a")
        
        # First tab completes to first suggestion
        console.handle_tab()
        first_suggestion = console.input_buffer
        
        # Second tab cycles to second suggestion
        console.handle_tab()
        second_suggestion = console.input_buffer
        
        assert first_suggestion != second_suggestion
        assert first_suggestion.startswith("test.a")
        assert second_suggestion.startswith("test.a")
    
    def test_autocomplete_suggestions_property(self, console, clean_registry):
        """Test suggestions property returns current suggestions."""
        @command(name="player.health", access=AccessLevel.PUBLIC)
        def health_cmd():
            return ""
        
        @command(name="player.pos", access=AccessLevel.PUBLIC)
        def pos_cmd():
            return ""
        
        console.open()
        console.set_input("player")
        console.handle_tab()  # Update suggestions
        
        suggestions = console.suggestions
        assert "player.health" in suggestions or "player.pos" in suggestions


# =============================================================================
# Output Tests
# =============================================================================


class TestConsoleOutput:
    """Tests for console output."""
    
    def test_print(self, console):
        """Test printing to console."""
        console.print("Hello, world!")
        
        lines = console.output_lines
        assert len(lines) == 1
        assert lines[0].text == "Hello, world!"
    
    def test_print_multiple_lines(self, console):
        """Test printing multiple lines."""
        console.print("Line 1\nLine 2\nLine 3")
        
        lines = console.output_lines
        assert len(lines) == 3
        assert lines[0].text == "Line 1"
        assert lines[1].text == "Line 2"
        assert lines[2].text == "Line 3"
    
    def test_print_error(self, console):
        """Test error printing uses error color."""
        console.print_error("Error message")
        
        lines = console.output_lines
        assert len(lines) == 1
        assert lines[0].text == "Error message"
        assert lines[0].color == console.config.error_color
    
    def test_print_success(self, console):
        """Test success printing uses success color."""
        console.print_success("Success message")
        
        lines = console.output_lines
        assert len(lines) == 1
        assert lines[0].text == "Success message"
        assert lines[0].color == console.config.success_color
    
    def test_clear(self, console):
        """Test clearing output."""
        console.print("Line 1")
        console.print("Line 2")
        
        console.clear()
        
        assert len(console.output_lines) == 0
    
    def test_max_lines(self, console):
        """Test output buffer respects max_lines."""
        console.config.max_lines = 5
        
        for i in range(10):
            console.print(f"Line {i}")
        
        # Should only keep last 5 lines
        lines = console._output
        assert len(lines) == 5
        assert lines[0].text == "Line 5"
        assert lines[4].text == "Line 9"
    
    def test_scroll(self, console):
        """Test scrolling output."""
        console.config.visible_lines = 3
        
        for i in range(10):
            console.print(f"Line {i}")
        
        # Initial view shows last 3 lines
        lines = console.output_lines
        assert len(lines) == 3
        
        # Scroll up
        console.scroll_up(2)
        lines = console.output_lines
        # Should show earlier lines


# =============================================================================
# Command Execution Tests
# =============================================================================


class TestConsoleExecution:
    """Tests for command execution via console."""
    
    def test_submit_executes_command(self, console, clean_registry):
        """Test submitting input executes command."""
        result_value = [None]
        
        @command(name="test.exec", access=AccessLevel.PUBLIC)
        def exec_cmd(value: str):
            result_value[0] = value
            return f"Got: {value}"
        
        console.open()
        console.set_input("test.exec hello")
        console.submit()
        
        assert result_value[0] == "hello"
    
    def test_submit_clears_input(self, console, clean_registry):
        """Test submit clears input buffer."""
        @command(name="test.clear", access=AccessLevel.PUBLIC)
        def clear_cmd():
            return ""
        
        console.open()
        console.set_input("test.clear")
        console.submit()
        
        assert console.input_buffer == ""
        assert console.cursor_position == 0
    
    def test_submit_shows_result(self, console, clean_registry):
        """Test submit shows command result."""
        @command(name="test.result", access=AccessLevel.PUBLIC)
        def result_cmd():
            return "Command result"
        
        console.open()
        console.set_input("test.result")
        console.submit()
        
        # Output should contain the result
        output_texts = [line.text for line in console._output]
        assert any("Command result" in text for text in output_texts)
    
    def test_submit_shows_error(self, console, clean_registry):
        """Test submit shows error for failed command."""
        console.open()
        console.set_input("nonexistent.command")
        console.submit()
        
        # Output should contain error
        output_texts = [line.text for line in console._output]
        assert any("unknown" in text.lower() for text in output_texts)
    
    def test_submit_callback(self, console, clean_registry):
        """Test submit callback is called."""
        submitted_command = [None]
        
        def on_submit(cmd):
            submitted_command[0] = cmd
        
        @command(name="test.callback", access=AccessLevel.PUBLIC)
        def callback_cmd():
            return ""
        
        console.on_submit = on_submit
        console.open()
        console.set_input("test.callback")
        console.submit()
        
        assert submitted_command[0] == "test.callback"
    
    def test_submit_empty_does_nothing(self, console):
        """Test submitting empty input does nothing."""
        console.open()
        console.set_input("")
        console.submit()
        
        # No output added
        assert len(console._output) == 0


# =============================================================================
# Escape Key Tests
# =============================================================================


class TestConsoleEscape:
    """Tests for escape key handling."""
    
    def test_escape_clears_suggestions(self, console, clean_registry):
        """Test escape clears autocomplete suggestions."""
        @command(name="test.escape", access=AccessLevel.PUBLIC)
        def escape_cmd():
            return ""
        
        console.open()
        console.set_input("test")
        console.handle_tab()  # Generate suggestions
        
        console.handle_escape()
        
        assert len(console.suggestions) == 0
    
    def test_escape_closes_console(self, console):
        """Test escape closes console when no suggestions."""
        console.open()
        
        console.handle_escape()
        
        assert not console.is_visible


# =============================================================================
# Persistence Tests
# =============================================================================


class TestConsolePersistence:
    """Tests for history persistence."""
    
    def test_save_and_load_history(self, console, clean_registry):
        """Test saving and loading history."""
        @command(name="test.persist", access=AccessLevel.PUBLIC)
        def persist_cmd():
            return ""
        
        console.open()
        console.set_input("test.persist 1")
        console.submit()
        console.set_input("test.persist 2")
        console.submit()
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            history_path = f.name
        
        try:
            # Save history
            console.save_history(history_path)
            
            # Create new console and load history
            console2 = Console()
            console2.load_history(history_path)
            
            assert "test.persist 1" in console2.history
            assert "test.persist 2" in console2.history
        finally:
            os.unlink(history_path)
    
    def test_load_nonexistent_history(self, console):
        """Test loading nonexistent history file doesn't crash."""
        console.load_history("nonexistent_file.txt")
        
        # Should just have empty history
        assert len(console.history) == 0


# =============================================================================
# Render Data Tests
# =============================================================================


class TestConsoleRenderData:
    """Tests for render data generation."""
    
    def test_get_render_data(self, console):
        """Test get_render_data returns all needed info."""
        console.open()
        console.set_input("test input")
        console.print("Output line")
        
        data = console.get_render_data()
        
        assert data["visible"] is True
        assert data["input"] == "test input"
        assert data["cursor_pos"] == 10
        assert len(data["lines"]) == 1
        assert data["lines"][0]["text"] == "Output line"
        assert "config" in data
    
    def test_render_data_when_hidden(self, console):
        """Test render data when console is hidden."""
        data = console.get_render_data()
        
        assert data["visible"] is False


# =============================================================================
# Config Tests
# =============================================================================


class TestConsoleConfig:
    """Tests for console configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ConsoleConfig()
        
        assert config.max_lines == 100
        assert config.visible_lines == 10
        assert config.echo_commands is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = ConsoleConfig(
            max_lines=50,
            visible_lines=5,
            echo_commands=False,
        )
        
        console = Console(config)
        
        assert console.config.max_lines == 50
        assert console.config.visible_lines == 5
        assert console.config.echo_commands is False


# =============================================================================
# TextInputBuffer Tests
# =============================================================================


class TestTextInputBuffer:
    """Tests for TextInputBuffer cursor, selection, word ops, and undo."""

    def test_initial_state(self):
        """Test buffer starts empty."""
        buf = TextInputBuffer()
        assert buf.text == ""
        assert buf.cursor == 0
        assert not buf.has_selection

    def test_insert(self):
        """Test inserting text."""
        buf = TextInputBuffer()
        buf.insert("hello")
        assert buf.text == "hello"
        assert buf.cursor == 5

    def test_insert_at_cursor(self):
        """Test inserting text in the middle."""
        buf = TextInputBuffer("ac")
        buf.cursor = 1
        buf.insert("b")
        assert buf.text == "abc"
        assert buf.cursor == 2

    def test_backspace(self):
        """Test backspace removes character before cursor."""
        buf = TextInputBuffer("abc")
        buf.cursor = 3
        buf.backspace()
        assert buf.text == "ab"
        assert buf.cursor == 2

    def test_backspace_at_start(self):
        """Test backspace at position 0 does nothing."""
        buf = TextInputBuffer("abc")
        buf.cursor = 0
        buf.backspace()
        assert buf.text == "abc"

    def test_delete(self):
        """Test delete removes character after cursor."""
        buf = TextInputBuffer("abc")
        buf.cursor = 1
        buf.delete()
        assert buf.text == "ac"
        assert buf.cursor == 1

    def test_delete_at_end(self):
        """Test delete at end does nothing."""
        buf = TextInputBuffer("abc")
        buf.cursor = 3
        buf.delete()
        assert buf.text == "abc"

    def test_move_left_right(self):
        """Test cursor movement."""
        buf = TextInputBuffer("hello")
        buf.cursor = 3
        buf.move_left()
        assert buf.cursor == 2
        buf.move_right()
        assert buf.cursor == 3

    def test_move_bounds(self):
        """Test cursor stays within bounds."""
        buf = TextInputBuffer("hi")
        buf.cursor = 0
        buf.move_left()
        assert buf.cursor == 0
        buf.cursor = 2
        buf.move_right()
        assert buf.cursor == 2

    def test_home_end(self):
        """Test home/end movements."""
        buf = TextInputBuffer("hello world")
        buf.cursor = 5
        buf.move_home()
        assert buf.cursor == 0
        buf.move_end()
        assert buf.cursor == 11

    def test_word_left(self):
        """Test word-left movement."""
        buf = TextInputBuffer("hello world foo")
        buf.cursor = 15
        buf.move_word_left()
        assert buf.cursor == 12  # before 'foo'
        buf.move_word_left()
        assert buf.cursor == 6  # before 'world'
        buf.move_word_left()
        assert buf.cursor == 0  # start

    def test_word_right(self):
        """Test word-right movement."""
        buf = TextInputBuffer("hello world foo")
        buf.cursor = 0
        buf.move_word_right()
        assert buf.cursor == 5  # after 'hello'
        buf.move_word_right()
        assert buf.cursor == 11  # after 'world'

    def test_backspace_word(self):
        """Test deleting a word backwards."""
        buf = TextInputBuffer("hello world")
        buf.cursor = 11
        buf.backspace_word()
        assert buf.text == "hello "
        assert buf.cursor == 6

    def test_delete_word(self):
        """Test deleting a word forwards."""
        buf = TextInputBuffer("hello world")
        buf.cursor = 0
        buf.delete_word()
        assert buf.text == " world"
        assert buf.cursor == 0

    def test_select_all(self):
        """Test select all."""
        buf = TextInputBuffer("hello")
        buf.select_all()
        assert buf.has_selection
        assert buf.cursor == 5
        assert buf.selected_text == "hello"

    def test_insert_replaces_selection(self):
        """Test that insert replaces selected text."""
        buf = TextInputBuffer("hello world")
        buf.select_all()
        # cursor at end, selection from 0
        buf.cursor = 5
        buf._selection_start = 0
        buf.insert("bye")
        assert buf.text == "bye world"
        assert not buf.has_selection

    def test_backspace_removes_selection(self):
        """Test backspace with selection removes selected text."""
        buf = TextInputBuffer("hello world")
        # Select "world"
        buf.cursor = 11
        buf.move_left(select=True)
        buf.move_left(select=True)
        buf.move_left(select=True)
        buf.move_left(select=True)
        buf.move_left(select=True)
        # Now selection covers "world"
        buf.backspace()
        assert buf.text == "hello "
        assert not buf.has_selection

    def test_undo(self):
        """Test undo restores previous state."""
        buf = TextInputBuffer()
        buf.insert("hello")
        buf.insert(" world")
        buf.undo()
        assert buf.text == "hello"
        buf.undo()
        assert buf.text == ""

    def test_undo_empty_stack(self):
        """Test undo with no history does nothing."""
        buf = TextInputBuffer()
        buf.undo()  # Should not raise
        assert buf.text == ""

    def test_clear(self):
        """Test clear empties the buffer."""
        buf = TextInputBuffer("hello")
        buf.clear()
        assert buf.text == ""
        assert buf.cursor == 0
        assert not buf.has_selection

    def test_set_text(self):
        """Test setting text via property replaces contents."""
        buf = TextInputBuffer("old text")
        buf.text = "new text"
        assert buf.text == "new text"
        assert buf.cursor == 8

    def test_selection_with_move_left(self):
        """Test selection via move_left with select=True."""
        buf = TextInputBuffer("hello")
        buf.cursor = 5
        buf.move_left(select=True)
        buf.move_left(select=True)
        assert buf.has_selection
        assert buf.cursor == 3
        assert buf.selected_text == "lo"

    def test_selected_text(self):
        """Test getting selected text."""
        buf = TextInputBuffer("hello world")
        # Select "hello" using select_all + adjust
        buf.cursor = 0
        buf.move_right(select=True)
        buf.move_right(select=True)
        buf.move_right(select=True)
        buf.move_right(select=True)
        buf.move_right(select=True)
        assert buf.selected_text == "hello"


# =============================================================================
# Notification Tests
# =============================================================================


class TestNotifications:
    """Tests for the notification system."""

    def test_notification_creation(self):
        """Test creating a notification."""
        notif = Notification(
            text="Test notification",
            notification_type=NotificationType.INFO,
        )
        assert notif.text == "Test notification"
        assert notif.notification_type == NotificationType.INFO

    def test_console_notify(self):
        """Test console.notify adds to notification list."""
        console = Console()
        console.notify("Item acquired!", NotificationType.SUCCESS)
        
        data = console.get_render_data()
        notifications = data.get("notifications", [])
        assert len(notifications) >= 1
        assert any("Item acquired!" in n.get("text", "") for n in notifications)

    def test_notification_types(self):
        """Test all notification types exist."""
        assert NotificationType.INFO is not None
        assert NotificationType.SUCCESS is not None
        assert NotificationType.WARNING is not None
        assert NotificationType.ERROR is not None

    def test_console_print_warning(self):
        """Test console.print_warning outputs with warning color."""
        console = Console()
        console.print_warning("Watch out!")
        
        lines = console.output_lines
        assert len(lines) == 1
        assert lines[0].text == "Watch out!"
        assert lines[0].color == console.config.warning_color


# =============================================================================
# Console Word Operations Tests
# =============================================================================


class TestConsoleWordOperations:
    """Tests for console word-level operations via handle_*_word methods."""

    def test_handle_backspace_word(self):
        """Test Ctrl+Backspace deletes word backwards."""
        console = Console()
        console.open()
        console.set_input("hello world")
        console.handle_backspace_word()
        assert console.input_buffer == "hello "

    def test_handle_delete_word(self):
        """Test Ctrl+Delete deletes word forwards."""
        console = Console()
        console.open()
        console.set_input("hello world")
        # Move cursor to start
        console.handle_home()
        console.handle_delete_word()
        assert console.input_buffer == " world"

    def test_handle_word_left(self):
        """Test Ctrl+Left moves cursor one word left."""
        console = Console()
        console.open()
        console.set_input("hello world")
        console.handle_word_left()
        assert console.cursor_position == 6  # before 'world'

    def test_handle_word_right(self):
        """Test Ctrl+Right moves cursor one word right."""
        console = Console()
        console.open()
        console.set_input("hello world")
        console.handle_home()
        console.handle_word_right()
        assert console.cursor_position == 5  # after 'hello'

    def test_handle_select_all(self):
        """Test Ctrl+A selects all text."""
        console = Console()
        console.open()
        console.set_input("hello")
        console.handle_select_all()
        data = console.get_render_data()
        # After select_all, the buffer should have a selection
        assert data["cursor_pos"] == 5

    def test_handle_undo(self):
        """Test Ctrl+Z undoes last input change."""
        console = Console()
        console.open()
        console.handle_char('a')
        console.handle_char('b')
        console.handle_undo()
        assert console.input_buffer == "a"

    def test_handle_paste(self):
        """Test Ctrl+V pastes text."""
        console = Console()
        console.open()
        console.set_input("hello ")
        console.handle_paste("world")
        assert console.input_buffer == "hello world"

    def test_handle_left_with_selection(self):
        """Test Shift+Left extends selection."""
        console = Console()
        console.open()
        console.set_input("hello")
        console.handle_left(select=True)
        console.handle_left(select=True)
        # Cursor should be at 3 with selection from 5
        assert console.cursor_position == 3
