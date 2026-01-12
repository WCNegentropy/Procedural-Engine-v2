"""Tests for the command system (commands.py).

Tests cover:
- Command parameter validation
- Command registration and lookup
- Command execution
- Access control (cheats, dev mode)
- Help system
- Autocomplete
- Script execution
- MCP tool generation
"""
import pytest
from pathlib import Path
import tempfile
import os

from procengine.commands.commands import (
    AccessLevel,
    Category,
    Command,
    CommandParam,
    CommandResult,
    CommandRegistry,
    command,
    registry,
    execute_script,
    script_recorder,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def clean_registry():
    """Provide a clean registry for testing."""
    # Save original state
    original_commands = registry._commands.copy()
    original_aliases = registry._aliases.copy()
    original_cheats = registry._cheats_enabled
    original_dev = registry._dev_mode
    original_console = registry._console_open
    original_history = registry._history.copy()
    
    # Clear state
    registry._commands.clear()
    registry._aliases.clear()
    registry._cheats_enabled = False
    registry._dev_mode = False
    registry._console_open = False
    registry._history.clear()
    
    yield registry
    
    # Restore original state
    registry._commands = original_commands
    registry._aliases = original_aliases
    registry._cheats_enabled = original_cheats
    registry._dev_mode = original_dev
    registry._console_open = original_console
    registry._history = original_history


@pytest.fixture
def sample_command(clean_registry):
    """Create a sample command for testing."""
    @command(
        name="test.sample",
        description="A sample test command",
        category=Category.DEBUG,
        access=AccessLevel.PUBLIC,
        aliases=["sample"],
    )
    def sample_cmd(name: str, count: int = 1, verbose: bool = False) -> str:
        return f"Sample: {name} x{count} (verbose={verbose})"
    
    return sample_cmd


# =============================================================================
# CommandParam Tests
# =============================================================================


class TestCommandParam:
    """Tests for CommandParam class."""
    
    def test_validate_required_string(self):
        """Test required string parameter validation."""
        param = CommandParam(name="name", param_type=str, required=True)
        
        success, value, error = param.validate("hello")
        assert success
        assert value == "hello"
        assert error == ""
    
    def test_validate_required_missing(self):
        """Test required parameter with missing value."""
        param = CommandParam(name="name", param_type=str, required=True)
        
        success, value, error = param.validate(None)
        assert not success
        assert "required" in error.lower()
    
    def test_validate_optional_with_default(self):
        """Test optional parameter with default."""
        param = CommandParam(name="count", param_type=int, required=False, default=10)
        
        success, value, error = param.validate(None)
        assert success
        assert value == 10
    
    def test_validate_int_conversion(self):
        """Test integer type conversion."""
        param = CommandParam(name="count", param_type=int, required=True)
        
        success, value, error = param.validate("42")
        assert success
        assert value == 42
        assert isinstance(value, int)
    
    def test_validate_float_conversion(self):
        """Test float type conversion."""
        param = CommandParam(name="amount", param_type=float, required=True)
        
        success, value, error = param.validate("3.14")
        assert success
        assert value == pytest.approx(3.14)
    
    def test_validate_bool_true(self):
        """Test boolean true values."""
        param = CommandParam(name="enabled", param_type=bool, required=True)
        
        for val in ["true", "1", "yes", "on", True]:
            success, value, error = param.validate(val)
            assert success
            assert value is True
    
    def test_validate_bool_false(self):
        """Test boolean false values."""
        param = CommandParam(name="enabled", param_type=bool, required=True)
        
        for val in ["false", "0", "no", "off", False]:
            success, value, error = param.validate(val)
            assert success
            assert value is False
    
    def test_validate_invalid_int(self):
        """Test invalid integer value."""
        param = CommandParam(name="count", param_type=int, required=True)
        
        success, value, error = param.validate("not_a_number")
        assert not success
        assert "invalid" in error.lower()
    
    def test_validate_choices(self):
        """Test choices validation."""
        param = CommandParam(
            name="color",
            param_type=str,
            required=True,
            choices=["red", "green", "blue"],
        )
        
        # Valid choice
        success, value, error = param.validate("red")
        assert success
        assert value == "red"
        
        # Invalid choice
        success, value, error = param.validate("yellow")
        assert not success
        assert "must be one of" in error.lower()


# =============================================================================
# CommandResult Tests
# =============================================================================


class TestCommandResult:
    """Tests for CommandResult class."""
    
    def test_ok_result(self):
        """Test creating success result."""
        result = CommandResult.ok("Success!")
        assert result.success
        assert result.message == "Success!"
    
    def test_error_result(self):
        """Test creating error result."""
        result = CommandResult.error("Failed!")
        assert not result.success
        assert result.message == "Failed!"
    
    def test_result_with_data(self):
        """Test result with data."""
        result = CommandResult.ok("Done", data={"count": 42})
        assert result.success
        assert result.data == {"count": 42}


# =============================================================================
# Command Tests
# =============================================================================


class TestCommand:
    """Tests for Command class."""
    
    def test_command_creation(self):
        """Test creating a command."""
        def handler(x: int) -> str:
            return f"x={x}"
        
        cmd = Command(
            name="test.cmd",
            handler=handler,
            description="Test command",
            category=Category.DEBUG,
            access=AccessLevel.CONSOLE,
            params=[CommandParam(name="x", param_type=int, required=True)],
        )
        
        assert cmd.name == "test.cmd"
        assert cmd.description == "Test command"
        assert cmd.category == Category.DEBUG
        assert cmd.access == AccessLevel.CONSOLE
        assert len(cmd.params) == 1
    
    def test_get_usage(self):
        """Test usage string generation."""
        cmd = Command(
            name="test.cmd",
            handler=lambda: None,
            params=[
                CommandParam(name="required_param", param_type=str, required=True),
                CommandParam(name="optional_param", param_type=int, required=False, default=5),
            ],
        )
        
        usage = cmd.get_usage()
        assert "test.cmd" in usage
        assert "<required_param>" in usage
        assert "[optional_param=5]" in usage
    
    def test_get_help(self):
        """Test help text generation."""
        cmd = Command(
            name="test.cmd",
            handler=lambda: None,
            description="A test command",
            params=[
                CommandParam(name="x", param_type=int, required=True, description="The X value"),
            ],
            aliases=["t"],
            examples=["test.cmd 42"],
        )
        
        help_text = cmd.get_help()
        assert "test.cmd" in help_text
        assert "A test command" in help_text
        assert "x" in help_text
        assert "int" in help_text
        assert "The X value" in help_text
        assert "t" in help_text
        assert "test.cmd 42" in help_text
    
    def test_to_mcp_tool(self):
        """Test MCP tool generation."""
        cmd = Command(
            name="test.cmd",
            handler=lambda: None,
            description="A test command",
            params=[
                CommandParam(name="x", param_type=int, required=True),
                CommandParam(name="y", param_type=float, required=False, default=0.0),
            ],
        )
        
        tool = cmd.to_mcp_tool()
        
        assert tool["name"] == "test_cmd"  # Dots replaced with underscores
        assert tool["description"] == "A test command"
        assert "inputSchema" in tool
        assert tool["inputSchema"]["properties"]["x"]["type"] == "integer"
        assert tool["inputSchema"]["properties"]["y"]["type"] == "number"
        assert "x" in tool["inputSchema"]["required"]
        assert "y" not in tool["inputSchema"]["required"]


# =============================================================================
# CommandRegistry Tests
# =============================================================================


class TestCommandRegistry:
    """Tests for CommandRegistry class."""
    
    def test_register_and_get(self, clean_registry):
        """Test command registration and retrieval."""
        cmd = Command(name="test.cmd", handler=lambda: None)
        clean_registry.register(cmd)
        
        retrieved = clean_registry.get("test.cmd")
        assert retrieved is cmd
    
    def test_get_by_alias(self, clean_registry):
        """Test command retrieval by alias."""
        cmd = Command(name="test.cmd", handler=lambda: None, aliases=["t"])
        clean_registry.register(cmd)
        
        retrieved = clean_registry.get("t")
        assert retrieved is cmd
    
    def test_unregister(self, clean_registry):
        """Test command unregistration."""
        cmd = Command(name="test.cmd", handler=lambda: None, aliases=["t"])
        clean_registry.register(cmd)
        
        assert clean_registry.unregister("test.cmd")
        assert clean_registry.get("test.cmd") is None
        assert clean_registry.get("t") is None
    
    def test_get_by_category(self, clean_registry):
        """Test getting commands by category."""
        cmd1 = Command(name="debug.a", handler=lambda: None, category=Category.DEBUG)
        cmd2 = Command(name="debug.b", handler=lambda: None, category=Category.DEBUG)
        cmd3 = Command(name="player.c", handler=lambda: None, category=Category.PLAYER)
        
        clean_registry.register(cmd1)
        clean_registry.register(cmd2)
        clean_registry.register(cmd3)
        
        debug_cmds = clean_registry.get_by_category(Category.DEBUG)
        assert len(debug_cmds) == 2
        assert cmd1 in debug_cmds
        assert cmd2 in debug_cmds
    
    def test_access_control_public(self, clean_registry):
        """Test public command access."""
        cmd = Command(name="test", handler=lambda: None, access=AccessLevel.PUBLIC)
        clean_registry.register(cmd)
        
        can_exec, _ = clean_registry.can_execute(cmd)
        assert can_exec
    
    def test_access_control_console(self, clean_registry):
        """Test console command access."""
        cmd = Command(name="test", handler=lambda: None, access=AccessLevel.CONSOLE)
        clean_registry.register(cmd)
        
        # Without console open
        clean_registry.console_open = False
        can_exec, _ = clean_registry.can_execute(cmd)
        assert not can_exec
        
        # With console open
        clean_registry.console_open = True
        can_exec, _ = clean_registry.can_execute(cmd)
        assert can_exec
    
    def test_access_control_cheat(self, clean_registry):
        """Test cheat command access."""
        cmd = Command(name="test", handler=lambda: None, access=AccessLevel.CHEAT)
        clean_registry.register(cmd)
        
        # Without cheats enabled
        clean_registry.cheats_enabled = False
        can_exec, _ = clean_registry.can_execute(cmd)
        assert not can_exec
        
        # With cheats enabled
        clean_registry.cheats_enabled = True
        can_exec, _ = clean_registry.can_execute(cmd)
        assert can_exec
    
    def test_access_control_dev(self, clean_registry):
        """Test dev command access."""
        cmd = Command(name="test", handler=lambda: None, access=AccessLevel.DEV)
        clean_registry.register(cmd)
        
        # Without dev mode
        clean_registry.dev_mode = False
        can_exec, _ = clean_registry.can_execute(cmd)
        assert not can_exec
        
        # With dev mode
        clean_registry.dev_mode = True
        can_exec, _ = clean_registry.can_execute(cmd)
        assert can_exec
    
    def test_execute_simple(self, clean_registry):
        """Test simple command execution."""
        call_count = [0]
        
        @command(name="test.simple", access=AccessLevel.PUBLIC)
        def simple_cmd():
            call_count[0] += 1
            return "done"
        
        result = clean_registry.execute("test.simple")
        assert result.success
        assert result.message == "done"
        assert call_count[0] == 1
    
    def test_execute_with_args(self, clean_registry):
        """Test command execution with arguments."""
        @command(name="test.args", access=AccessLevel.PUBLIC)
        def args_cmd(name: str, count: int = 1):
            return f"{name}: {count}"
        
        result = clean_registry.execute("test.args hello 5")
        assert result.success
        assert result.message == "hello: 5"
    
    def test_execute_with_quoted_args(self, clean_registry):
        """Test command execution with quoted arguments."""
        @command(name="test.quoted", access=AccessLevel.PUBLIC)
        def quoted_cmd(message: str):
            return message
        
        result = clean_registry.execute('test.quoted "hello world"')
        assert result.success
        assert result.message == "hello world"
    
    def test_execute_with_keyword_args(self, clean_registry):
        """Test command execution with keyword arguments."""
        @command(name="test.kwargs", access=AccessLevel.PUBLIC)
        def kwargs_cmd(a: int, b: int = 0):
            return f"a={a}, b={b}"
        
        result = clean_registry.execute("test.kwargs b=10 a=5")
        assert result.success
        assert "a=5" in result.message
        assert "b=10" in result.message
    
    def test_execute_unknown_command(self, clean_registry):
        """Test executing unknown command."""
        result = clean_registry.execute("nonexistent.command")
        assert not result.success
        assert "unknown" in result.message.lower()
    
    def test_execute_missing_required_arg(self, clean_registry):
        """Test executing command with missing required argument."""
        @command(name="test.required", access=AccessLevel.PUBLIC)
        def required_cmd(x: int):
            return f"x={x}"
        
        result = clean_registry.execute("test.required")
        assert not result.success
        assert "missing" in result.message.lower() or "required" in result.message.lower()
    
    def test_execute_invalid_arg_type(self, clean_registry):
        """Test executing command with invalid argument type."""
        @command(name="test.type", access=AccessLevel.PUBLIC)
        def type_cmd(x: int):
            return f"x={x}"
        
        result = clean_registry.execute("test.type not_a_number")
        assert not result.success
        assert "invalid" in result.message.lower()
    
    def test_execute_access_denied(self, clean_registry):
        """Test executing command without proper access."""
        @command(name="test.cheat", access=AccessLevel.CHEAT)
        def cheat_cmd():
            return "cheated"
        
        clean_registry.cheats_enabled = False
        result = clean_registry.execute("test.cheat")
        assert not result.success
        assert "cheats" in result.message.lower()
    
    def test_execute_dict(self, clean_registry):
        """Test execute_dict for MCP-style execution."""
        @command(name="test.mcp", access=AccessLevel.PUBLIC)
        def mcp_cmd(x: int, y: int = 0):
            return f"x={x}, y={y}"
        
        result = clean_registry.execute_dict("test_mcp", {"x": 10, "y": 20})
        assert result.success
        assert "x=10" in result.message
        assert "y=20" in result.message
    
    def test_autocomplete(self, clean_registry):
        """Test autocomplete suggestions."""
        @command(name="player.pos", access=AccessLevel.PUBLIC)
        def pos_cmd():
            return ""
        
        @command(name="player.health", access=AccessLevel.PUBLIC)
        def health_cmd():
            return ""
        
        @command(name="npc.list", access=AccessLevel.PUBLIC)
        def list_cmd():
            return ""
        
        # Test partial match
        suggestions = clean_registry.autocomplete("player")
        assert "player.pos" in suggestions
        assert "player.health" in suggestions
        assert "npc.list" not in suggestions
        
        # Test category prefix
        suggestions = clean_registry.autocomplete("player.")
        assert "player.pos" in suggestions
        assert "player.health" in suggestions
    
    def test_help_categories(self, clean_registry):
        """Test help listing categories."""
        @command(name="player.test", category=Category.PLAYER, access=AccessLevel.PUBLIC)
        def player_cmd():
            return ""
        
        @command(name="debug.test", category=Category.DEBUG, access=AccessLevel.PUBLIC)
        def debug_cmd():
            return ""
        
        help_text = clean_registry.help()
        assert "player" in help_text.lower()
        assert "debug" in help_text.lower()
    
    def test_help_category(self, clean_registry):
        """Test help for specific category."""
        @command(
            name="player.test",
            description="Test player command",
            category=Category.PLAYER,
            access=AccessLevel.PUBLIC,
        )
        def player_cmd():
            return ""
        
        help_text = clean_registry.help("player")
        assert "player.test" in help_text
        assert "Test player command" in help_text
    
    def test_help_command(self, clean_registry):
        """Test help for specific command."""
        @command(
            name="test.help",
            description="A test command",
            category=Category.DEBUG,
            access=AccessLevel.PUBLIC,
            aliases=["th"],
            examples=["test.help"],
        )
        def help_cmd(x: int):
            return ""
        
        help_text = clean_registry.help("test.help")
        assert "test.help" in help_text
        assert "A test command" in help_text
        assert "x" in help_text
        assert "th" in help_text
    
    def test_history(self, clean_registry):
        """Test command history."""
        @command(name="test.hist", access=AccessLevel.PUBLIC)
        def hist_cmd():
            return ""
        
        clean_registry.execute("test.hist")
        clean_registry.execute("test.hist")
        
        history = clean_registry.get_history(10)
        assert "test.hist" in history
        assert len(history) == 2
    
    def test_get_all_mcp_tools(self, clean_registry):
        """Test MCP tool generation for all commands."""
        @command(name="public.cmd", access=AccessLevel.PUBLIC)
        def pub_cmd():
            return ""
        
        @command(name="console.cmd", access=AccessLevel.CONSOLE)
        def con_cmd():
            return ""
        
        @command(name="cheat.cmd", access=AccessLevel.CHEAT)
        def cheat_cmd():
            return ""
        
        tools = clean_registry.get_all_mcp_tools()
        tool_names = [t["name"] for t in tools]
        
        # PUBLIC and CONSOLE should be included
        assert "public_cmd" in tool_names
        assert "console_cmd" in tool_names
        # CHEAT should not be included
        assert "cheat_cmd" not in tool_names


# =============================================================================
# Script Tests
# =============================================================================


class TestScriptExecution:
    """Tests for script execution."""
    
    def test_execute_script(self, clean_registry):
        """Test executing a script file."""
        @command(name="test.script", access=AccessLevel.PUBLIC)
        def script_cmd(x: int):
            return f"x={x}"
        
        # Create temp script file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Comment line\n")
            f.write("test.script 1\n")
            f.write("test.script 2\n")
            f.write("\n")  # Empty line
            f.write("test.script 3\n")
            script_path = f.name
        
        try:
            results = execute_script(Path(script_path))
            assert len(results) == 3
            assert all(r.success for r in results)
        finally:
            os.unlink(script_path)
    
    def test_execute_script_with_error(self, clean_registry):
        """Test script execution with error."""
        @command(name="test.script", access=AccessLevel.PUBLIC)
        def script_cmd(x: int):
            return f"x={x}"
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test.script 1\n")
            f.write("nonexistent.command\n")  # This will fail
            f.write("test.script 2\n")
            script_path = f.name
        
        try:
            results = execute_script(Path(script_path))
            assert len(results) == 3
            assert results[0].success
            assert not results[1].success
            assert results[2].success
        finally:
            os.unlink(script_path)
    
    def test_script_not_found(self, clean_registry):
        """Test script execution with missing file."""
        results = execute_script(Path("nonexistent_script.txt"))
        assert len(results) == 1
        assert not results[0].success
        assert "not found" in results[0].message.lower()


class TestScriptRecorder:
    """Tests for script recording."""
    
    def test_record_and_stop(self, clean_registry):
        """Test recording commands to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "recorded.txt"
            
            assert script_recorder.start(script_path)
            assert script_recorder.is_recording
            
            script_recorder.record("command1")
            script_recorder.record("command2")
            
            assert script_recorder.stop()
            assert not script_recorder.is_recording
            
            # Check file contents
            with open(script_path) as f:
                content = f.read()
            
            assert "command1" in content
            assert "command2" in content
    
    def test_cannot_start_while_recording(self, clean_registry):
        """Test that starting while recording fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            script_path1 = Path(tmpdir) / "script1.txt"
            script_path2 = Path(tmpdir) / "script2.txt"
            
            assert script_recorder.start(script_path1)
            assert not script_recorder.start(script_path2)  # Should fail
            
            script_recorder.stop()
    
    def test_cannot_stop_without_starting(self, clean_registry):
        """Test that stopping without starting fails."""
        assert not script_recorder.stop()


# =============================================================================
# Built-in Commands Tests
# =============================================================================


class TestBuiltinCommands:
    """Tests for built-in commands."""
    
    def test_help_command(self):
        """Test help command exists and works."""
        result = registry.execute("help")
        assert result.success
        assert "categories" in result.message.lower() or "help" in result.message.lower()
    
    def test_echo_command(self):
        """Test echo command."""
        result = registry.execute('echo "Hello World"')
        assert result.success
        assert "Hello World" in result.message
    
    def test_cheats_command(self):
        """Test cheats toggle command."""
        original = registry.cheats_enabled
        try:
            registry.console_open = True
            
            result = registry.execute("system.cheats 1")
            assert result.success
            assert registry.cheats_enabled
            
            result = registry.execute("system.cheats 0")
            assert result.success
            assert not registry.cheats_enabled
        finally:
            registry.cheats_enabled = original
            registry.console_open = False
    
    def test_dev_command(self):
        """Test dev mode toggle command."""
        original = registry.dev_mode
        try:
            registry.console_open = True
            
            result = registry.execute("system.dev 1")
            assert result.success
            assert registry.dev_mode
            
            result = registry.execute("system.dev 0")
            assert result.success
            assert not registry.dev_mode
        finally:
            registry.dev_mode = original
            registry.console_open = False
    
    def test_history_command(self):
        """Test history command."""
        result = registry.execute("history")
        assert result.success


# =============================================================================
# Decorator Tests
# =============================================================================


class TestCommandDecorator:
    """Tests for the @command decorator."""
    
    def test_decorator_registers_command(self, clean_registry):
        """Test that decorator registers the command."""
        @command(name="test.decorator", access=AccessLevel.PUBLIC)
        def decorated_cmd():
            return "decorated"
        
        cmd = clean_registry.get("test.decorator")
        assert cmd is not None
        assert cmd.handler is decorated_cmd
    
    def test_decorator_extracts_params(self, clean_registry):
        """Test that decorator extracts parameters from signature."""
        @command(name="test.params", access=AccessLevel.PUBLIC)
        def params_cmd(required_str: str, optional_int: int = 10, flag: bool = False):
            return ""
        
        cmd = clean_registry.get("test.params")
        assert len(cmd.params) == 3
        
        # Check required param
        assert cmd.params[0].name == "required_str"
        assert cmd.params[0].param_type == str
        assert cmd.params[0].required
        
        # Check optional int param
        assert cmd.params[1].name == "optional_int"
        assert cmd.params[1].param_type == int
        assert not cmd.params[1].required
        assert cmd.params[1].default == 10
        
        # Check bool flag
        assert cmd.params[2].name == "flag"
        assert cmd.params[2].param_type == bool
        assert not cmd.params[2].required
        assert cmd.params[2].default is False
    
    def test_decorator_preserves_function(self, clean_registry):
        """Test that decorated function is still callable."""
        @command(name="test.callable", access=AccessLevel.PUBLIC)
        def callable_cmd(x: int) -> str:
            return f"direct: {x}"
        
        # Function should still be directly callable
        result = callable_cmd(42)
        assert result == "direct: 42"


# =============================================================================
# Integration Tests
# =============================================================================


class TestCommandIntegration:
    """Integration tests for command system."""
    
    def test_full_workflow(self, clean_registry):
        """Test complete workflow: register, execute, help."""
        # Register command
        @command(
            name="test.workflow",
            description="Workflow test command",
            category=Category.DEBUG,
            access=AccessLevel.PUBLIC,
            aliases=["wf"],
            examples=["test.workflow 42"],
        )
        def workflow_cmd(value: int) -> CommandResult:
            return CommandResult.ok(f"Value: {value}", data={"value": value})
        
        # Execute by name
        result = clean_registry.execute("test.workflow 100")
        assert result.success
        assert result.data["value"] == 100
        
        # Execute by alias
        result = clean_registry.execute("wf 200")
        assert result.success
        assert result.data["value"] == 200
        
        # Get help
        help_text = clean_registry.help("test.workflow")
        assert "Workflow test command" in help_text
        assert "test.workflow 42" in help_text
        
        # Autocomplete
        suggestions = clean_registry.autocomplete("test.w")
        assert "test.workflow" in suggestions
