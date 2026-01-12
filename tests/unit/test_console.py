"""Tests for the console module.

Tests cover:
- Console visibility toggling
- Input handling (characters, backspace, arrows)
- Command history navigation
- Autocomplete functionality
- Output buffer management
- Command submission and execution
"""
import pytest
import tempfile
import os

from procengine.commands.console import Console, ConsoleConfig, ConsoleLine
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
