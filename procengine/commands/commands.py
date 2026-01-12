"""Unified Command Architecture for the Procedural Engine.

This module provides a single command surface accessible via Console, GUI,
MCP, keybinds, and scripts. Every controllable aspect of the game is exposed
as a command.

Key features:
- Command registration via decorator
- Typed parameters with validation
- Access levels (PUBLIC, CONSOLE, CHEAT, DEV)
- Categories for organization
- Aliases for convenience
- Auto-generated help
- Autocomplete support
- MCP tool generation

Usage:
    from commands import registry, command, AccessLevel, Category
    
    @command(
        name="player.teleport",
        description="Teleport player to coordinates",
        category=Category.PLAYER,
        access=AccessLevel.CHEAT,
    )
    def teleport_player(x: float, y: float, z: float) -> str:
        # Implementation
        return f"Teleported to ({x}, {y}, {z})"
"""
from __future__ import annotations

import inspect
import json
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    get_type_hints,
)

__all__ = [
    "AccessLevel",
    "Category",
    "CommandParam",
    "Command",
    "CommandResult",
    "CommandRegistry",
    "command",
    "registry",
]


# =============================================================================
# Access Levels
# =============================================================================


class AccessLevel(Enum):
    """Access levels for commands.
    
    Commands require the appropriate access level to execute:
    - PUBLIC: Always available (movement, inventory, dialogue)
    - CONSOLE: Requires console open (spawn, teleport, modify)
    - CHEAT: Requires `system.cheats 1` (god mode, give items)
    - DEV: Requires `system.dev 1` (debug, hot-reload)
    """
    PUBLIC = auto()    # Always available
    CONSOLE = auto()   # Requires console open
    CHEAT = auto()     # Requires cheats enabled
    DEV = auto()       # Requires dev mode


# =============================================================================
# Categories
# =============================================================================


class Category(Enum):
    """Categories for organizing commands."""
    WORLD = "world"
    TERRAIN = "terrain"
    PROPS = "props"
    NPC = "npc"
    PLAYER = "player"
    PHYSICS = "physics"
    ENGINE = "engine"
    QUEST = "quest"
    UI = "ui"
    SYSTEM = "system"
    DEBUG = "debug"


# =============================================================================
# Command Parameter
# =============================================================================


@dataclass
class CommandParam:
    """Definition of a command parameter.
    
    Parameters have:
    - name: Parameter name
    - param_type: Python type (str, int, float, bool, etc.)
    - description: Human-readable description
    - required: Whether parameter is required
    - default: Default value if not required
    - choices: Optional list of valid values
    """
    name: str
    param_type: Type
    description: str = ""
    required: bool = True
    default: Any = None
    choices: Optional[List[Any]] = None
    
    def validate(self, value: Any) -> Tuple[bool, Any, str]:
        """Validate and convert a value for this parameter.
        
        Returns:
            (success, converted_value, error_message)
        """
        if value is None:
            if self.required:
                return False, None, f"Parameter '{self.name}' is required"
            return True, self.default, ""
        
        # Type conversion
        try:
            if self.param_type == bool:
                # Handle various boolean representations
                if isinstance(value, bool):
                    converted = value
                elif isinstance(value, str):
                    converted = value.lower() in ("true", "1", "yes", "on")
                else:
                    converted = bool(value)
            elif self.param_type == int:
                converted = int(float(value))  # Allow "1.0" -> 1
            elif self.param_type == float:
                converted = float(value)
            elif self.param_type == str:
                converted = str(value)
            else:
                converted = self.param_type(value)
        except (ValueError, TypeError) as e:
            return False, None, f"Invalid value for '{self.name}': expected {self.param_type.__name__}, got {type(value).__name__}"
        
        # Choices validation
        if self.choices is not None and converted not in self.choices:
            choices_str = ", ".join(str(c) for c in self.choices)
            return False, None, f"'{self.name}' must be one of: {choices_str}"
        
        return True, converted, ""


# =============================================================================
# Command Result
# =============================================================================


@dataclass
class CommandResult:
    """Result of command execution.
    
    Contains:
    - success: Whether command succeeded
    - message: Human-readable result message
    - data: Optional structured data (for programmatic access)
    """
    success: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def ok(cls, message: str = "", data: Optional[Dict[str, Any]] = None) -> "CommandResult":
        """Create a success result."""
        return cls(success=True, message=message, data=data)
    
    @classmethod
    def error(cls, message: str, data: Optional[Dict[str, Any]] = None) -> "CommandResult":
        """Create an error result."""
        return cls(success=False, message=message, data=data)


# =============================================================================
# Command
# =============================================================================


@dataclass
class Command:
    """A registered command.
    
    Commands have:
    - name: Dotted identifier (e.g., 'npc.dialogue')
    - handler: Function to execute
    - description: Human-readable description
    - category: Organization category
    - access: Required permission level
    - params: List of typed parameters
    - aliases: Alternative names
    - examples: Usage examples
    """
    name: str
    handler: Callable[..., CommandResult]
    description: str = ""
    category: Category = Category.SYSTEM
    access: AccessLevel = AccessLevel.CONSOLE
    params: List[CommandParam] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    
    def get_usage(self) -> str:
        """Get usage string for this command."""
        parts = [self.name]
        for param in self.params:
            if param.required:
                parts.append(f"<{param.name}>")
            else:
                parts.append(f"[{param.name}={param.default}]")
        return " ".join(parts)
    
    def get_help(self) -> str:
        """Get detailed help text for this command."""
        lines = [
            f"Command: {self.name}",
            f"  {self.description}",
            "",
            f"Usage: {self.get_usage()}",
        ]
        
        if self.params:
            lines.append("")
            lines.append("Parameters:")
            for param in self.params:
                type_str = param.param_type.__name__
                req_str = "required" if param.required else f"default={param.default}"
                lines.append(f"  {param.name} ({type_str}, {req_str})")
                if param.description:
                    lines.append(f"    {param.description}")
                if param.choices:
                    lines.append(f"    Choices: {', '.join(str(c) for c in param.choices)}")
        
        if self.examples:
            lines.append("")
            lines.append("Examples:")
            for example in self.examples:
                lines.append(f"  {example}")
        
        if self.aliases:
            lines.append("")
            lines.append(f"Aliases: {', '.join(self.aliases)}")
        
        return "\n".join(lines)
    
    def to_mcp_tool(self) -> Dict[str, Any]:
        """Convert command to MCP tool definition."""
        properties = {}
        required = []
        
        for param in self.params:
            prop = {
                "type": self._python_type_to_json_type(param.param_type),
                "description": param.description or f"Parameter {param.name}",
            }
            if param.choices:
                prop["enum"] = param.choices
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name.replace(".", "_"),
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
    
    def _python_type_to_json_type(self, py_type: Type) -> str:
        """Convert Python type to JSON Schema type."""
        if py_type == int:
            return "integer"
        elif py_type == float:
            return "number"
        elif py_type == bool:
            return "boolean"
        elif py_type == str:
            return "string"
        else:
            return "string"


# =============================================================================
# Command Registry
# =============================================================================


class CommandRegistry:
    """Central registry for all commands.
    
    The registry manages command registration, lookup, execution, and
    provides utilities for autocomplete and help generation.
    """
    
    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}  # alias -> canonical name
        self._context: Optional[Any] = None  # GameWorld or similar
        
        # Access control
        self._cheats_enabled: bool = False
        self._dev_mode: bool = False
        self._console_open: bool = False
        
        # Command history
        self._history: List[str] = []
        self._max_history: int = 100
    
    def set_context(self, context: Any) -> None:
        """Set the execution context (e.g., GameWorld)."""
        self._context = context
    
    def get_context(self) -> Optional[Any]:
        """Get the execution context."""
        return self._context
    
    @property
    def cheats_enabled(self) -> bool:
        """Whether cheats are enabled."""
        return self._cheats_enabled
    
    @cheats_enabled.setter
    def cheats_enabled(self, value: bool) -> None:
        """Set cheats enabled state."""
        self._cheats_enabled = value
    
    @property
    def dev_mode(self) -> bool:
        """Whether developer mode is enabled."""
        return self._dev_mode
    
    @dev_mode.setter
    def dev_mode(self, value: bool) -> None:
        """Set developer mode state."""
        self._dev_mode = value
    
    @property
    def console_open(self) -> bool:
        """Whether the console is open."""
        return self._console_open
    
    @console_open.setter
    def console_open(self, value: bool) -> None:
        """Set console open state."""
        self._console_open = value
    
    def register(self, cmd: Command) -> None:
        """Register a command."""
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd.name
    
    def unregister(self, name: str) -> bool:
        """Unregister a command by name."""
        if name in self._commands:
            cmd = self._commands.pop(name)
            for alias in cmd.aliases:
                self._aliases.pop(alias, None)
            return True
        return False
    
    def get(self, name: str) -> Optional[Command]:
        """Get a command by name or alias."""
        # Check if it's an alias
        canonical = self._aliases.get(name, name)
        return self._commands.get(canonical)
    
    def get_all(self) -> List[Command]:
        """Get all registered commands."""
        return list(self._commands.values())
    
    def get_by_category(self, category: Category) -> List[Command]:
        """Get commands by category."""
        return [cmd for cmd in self._commands.values() if cmd.category == category]
    
    def get_categories(self) -> List[Category]:
        """Get all categories that have commands."""
        return list(set(cmd.category for cmd in self._commands.values()))
    
    def can_execute(self, cmd: Command) -> Tuple[bool, str]:
        """Check if a command can be executed with current access level.
        
        Returns:
            (can_execute, reason_if_not)
        """
        if cmd.access == AccessLevel.PUBLIC:
            return True, ""
        elif cmd.access == AccessLevel.CONSOLE:
            if self._console_open:
                return True, ""
            return False, "Command requires console"
        elif cmd.access == AccessLevel.CHEAT:
            if self._cheats_enabled:
                return True, ""
            return False, "Command requires cheats enabled (system.cheats 1)"
        elif cmd.access == AccessLevel.DEV:
            if self._dev_mode:
                return True, ""
            return False, "Command requires dev mode (system.dev 1)"
        return False, "Unknown access level"
    
    def execute(self, command_str: str) -> CommandResult:
        """Execute a command string.
        
        Parameters:
            command_str: Full command string (e.g., "player.teleport 10 20 30")
            
        Returns:
            CommandResult with success/failure and message.
        """
        # Skip empty commands and comments
        command_str = command_str.strip()
        if not command_str or command_str.startswith("#"):
            return CommandResult.ok()
        
        # Add to history
        self._history.append(command_str)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        # Parse command
        try:
            parts = shlex.split(command_str)
        except ValueError as e:
            return CommandResult.error(f"Parse error: {e}")
        
        if not parts:
            return CommandResult.ok()
        
        cmd_name = parts[0]
        args = parts[1:]
        
        # Look up command
        cmd = self.get(cmd_name)
        if cmd is None:
            return CommandResult.error(f"Unknown command: {cmd_name}")
        
        # Check access
        can_exec, reason = self.can_execute(cmd)
        if not can_exec:
            return CommandResult.error(reason)
        
        # Parse and validate arguments
        kwargs = {}
        positional_idx = 0
        
        for i, arg in enumerate(args):
            # Check for keyword argument (key=value)
            if "=" in arg:
                key, value = arg.split("=", 1)
                # Find matching parameter
                param = None
                for p in cmd.params:
                    if p.name == key:
                        param = p
                        break
                if param is None:
                    return CommandResult.error(f"Unknown parameter: {key}")
                
                valid, converted, error = param.validate(value)
                if not valid:
                    return CommandResult.error(error)
                kwargs[key] = converted
            else:
                # Positional argument
                if positional_idx >= len(cmd.params):
                    return CommandResult.error(f"Too many arguments (expected {len(cmd.params)})")
                
                param = cmd.params[positional_idx]
                valid, converted, error = param.validate(arg)
                if not valid:
                    return CommandResult.error(error)
                kwargs[param.name] = converted
                positional_idx += 1
        
        # Fill in missing optional parameters with defaults
        for param in cmd.params:
            if param.name not in kwargs:
                if param.required:
                    return CommandResult.error(f"Missing required parameter: {param.name}")
                kwargs[param.name] = param.default
        
        # Execute command
        try:
            result = cmd.handler(**kwargs)
            if isinstance(result, CommandResult):
                return result
            elif isinstance(result, str):
                return CommandResult.ok(result)
            else:
                return CommandResult.ok(str(result) if result else "")
        except Exception as e:
            return CommandResult.error(f"Error executing command: {e}")
    
    def execute_dict(self, name: str, arguments: Dict[str, Any]) -> CommandResult:
        """Execute a command with dict arguments (for MCP).
        
        Parameters:
            name: Command name (can use _ instead of .)
            arguments: Dict of parameter name -> value
            
        Returns:
            CommandResult with success/failure and message.
        """
        # Convert MCP-style name to command name
        cmd_name = name.replace("_", ".")
        
        cmd = self.get(cmd_name)
        if cmd is None:
            return CommandResult.error(f"Unknown command: {cmd_name}")
        
        # Check access
        can_exec, reason = self.can_execute(cmd)
        if not can_exec:
            return CommandResult.error(reason)
        
        # Validate arguments
        kwargs = {}
        for param in cmd.params:
            if param.name in arguments:
                valid, converted, error = param.validate(arguments[param.name])
                if not valid:
                    return CommandResult.error(error)
                kwargs[param.name] = converted
            elif param.required:
                return CommandResult.error(f"Missing required parameter: {param.name}")
            else:
                kwargs[param.name] = param.default
        
        # Execute command
        try:
            result = cmd.handler(**kwargs)
            if isinstance(result, CommandResult):
                return result
            elif isinstance(result, str):
                return CommandResult.ok(result)
            else:
                return CommandResult.ok(str(result) if result else "")
        except Exception as e:
            return CommandResult.error(f"Error executing command: {e}")
    
    def autocomplete(self, partial: str) -> List[str]:
        """Get autocomplete suggestions for a partial command.
        
        Parameters:
            partial: Partial command string
            
        Returns:
            List of suggestions.
        """
        partial = partial.lower()
        suggestions = []
        
        # If partial is empty or just whitespace, return nothing
        if not partial.strip():
            # Return all command names when starting fresh
            return sorted(list(self._commands.keys()) + list(self._aliases.keys()))[:20]
        
        # Try to find commands that start with the partial
        for name in self._commands.keys():
            if name.lower().startswith(partial):
                suggestions.append(name)
        
        for alias in self._aliases.keys():
            if alias.lower().startswith(partial):
                suggestions.append(alias)
        
        # Also suggest category completions (e.g., "player." -> all player commands)
        if "." in partial:
            prefix = partial.rsplit(".", 1)[0] + "."
            for name in self._commands.keys():
                if name.lower().startswith(prefix) and name not in suggestions:
                    suggestions.append(name)
        
        return sorted(set(suggestions))[:20]  # Limit to 20 suggestions
    
    def get_history(self, count: int = 10) -> List[str]:
        """Get recent command history."""
        return self._history[-count:]
    
    def clear_history(self) -> None:
        """Clear command history."""
        self._history.clear()
    
    def get_all_mcp_tools(self) -> List[Dict[str, Any]]:
        """Generate MCP tool definitions for all accessible commands."""
        tools = []
        for cmd in self._commands.values():
            if cmd.access in (AccessLevel.PUBLIC, AccessLevel.CONSOLE):
                tools.append(cmd.to_mcp_tool())
        return tools
    
    def help(self, topic: Optional[str] = None) -> str:
        """Get help text.
        
        Parameters:
            topic: Optional command name or category name
            
        Returns:
            Help text string.
        """
        if topic is None:
            # List categories
            lines = ["Available command categories:"]
            for cat in sorted(self.get_categories(), key=lambda c: c.value):
                count = len(self.get_by_category(cat))
                lines.append(f"  {cat.value} ({count} commands)")
            lines.append("")
            lines.append("Use 'help <category>' to list commands in a category.")
            lines.append("Use 'help <command>' for detailed command help.")
            return "\n".join(lines)
        
        topic = topic.lower()
        
        # Check if it's a category
        for cat in Category:
            if cat.value == topic:
                commands = self.get_by_category(cat)
                lines = [f"Commands in '{cat.value}' category:"]
                for cmd in sorted(commands, key=lambda c: c.name):
                    lines.append(f"  {cmd.name} - {cmd.description}")
                return "\n".join(lines)
        
        # Check if it's a command
        cmd = self.get(topic)
        if cmd:
            return cmd.get_help()
        
        return f"Unknown topic: {topic}"


# =============================================================================
# Command Decorator
# =============================================================================


def command(
    name: str,
    description: str = "",
    category: Category = Category.SYSTEM,
    access: AccessLevel = AccessLevel.CONSOLE,
    aliases: Optional[List[str]] = None,
    examples: Optional[List[str]] = None,
) -> Callable:
    """Decorator to register a function as a command.
    
    The function's signature is analyzed to extract parameters.
    Type hints are used for validation.
    
    Parameters:
        name: Dotted command name (e.g., 'player.teleport')
        description: Human-readable description
        category: Command category for organization
        access: Required access level
        aliases: Alternative names for the command
        examples: Usage examples
        
    Returns:
        Decorator function.
        
    Example:
        @command(
            name="player.health",
            description="Set player health",
            category=Category.PLAYER,
            access=AccessLevel.CHEAT,
        )
        def set_health(amount: float) -> str:
            registry.get_context().player.health = amount
            return f"Health set to {amount}"
    """
    def decorator(func: Callable) -> Callable:
        # Extract parameters from function signature
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        
        params = []
        for param_name, param in sig.parameters.items():
            # Get type from type hints or default to str
            param_type = hints.get(param_name, str)
            
            # Handle Optional types
            if hasattr(param_type, "__origin__") and param_type.__origin__ is Union:
                # For Optional[X], extract X
                args = param_type.__args__
                param_type = args[0] if args[0] is not type(None) else args[1]
            
            # Check if parameter has default
            has_default = param.default is not inspect.Parameter.empty
            default_value = param.default if has_default else None
            
            params.append(CommandParam(
                name=param_name,
                param_type=param_type,
                required=not has_default,
                default=default_value,
            ))
        
        # Create and register command
        cmd = Command(
            name=name,
            handler=func,
            description=description,
            category=category,
            access=access,
            params=params,
            aliases=aliases or [],
            examples=examples or [],
        )
        
        registry.register(cmd)
        
        return func
    
    return decorator


# =============================================================================
# Global Registry Instance
# =============================================================================

# Global registry singleton
registry = CommandRegistry()


# =============================================================================
# Script Execution
# =============================================================================


def execute_script(path: Path) -> List[CommandResult]:
    """Execute a command script file.
    
    Parameters:
        path: Path to script file
        
    Returns:
        List of results for each command.
    """
    results = []
    
    try:
        with open(path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                result = registry.execute(line)
                if not result.success:
                    result.message = f"Line {line_num}: {result.message}"
                results.append(result)
    except FileNotFoundError:
        results.append(CommandResult.error(f"Script not found: {path}"))
    except Exception as e:
        results.append(CommandResult.error(f"Script error: {e}"))
    
    return results


# =============================================================================
# Script Recording
# =============================================================================


class ScriptRecorder:
    """Records commands to a script file."""
    
    def __init__(self) -> None:
        self._recording: bool = False
        self._path: Optional[Path] = None
        self._commands: List[str] = []
    
    def start(self, path: Path) -> bool:
        """Start recording to a file."""
        if self._recording:
            return False
        self._recording = True
        self._path = path
        self._commands = []
        return True
    
    def stop(self) -> bool:
        """Stop recording and save file."""
        if not self._recording:
            return False
        
        try:
            with open(self._path, "w") as f:
                f.write("# Recorded script\n")
                for cmd in self._commands:
                    f.write(cmd + "\n")
        except Exception:
            return False
        
        self._recording = False
        self._path = None
        self._commands = []
        return True
    
    def record(self, command: str) -> None:
        """Record a command if recording."""
        if self._recording:
            self._commands.append(command)
    
    @property
    def is_recording(self) -> bool:
        """Whether currently recording."""
        return self._recording


# Global script recorder
script_recorder = ScriptRecorder()


# =============================================================================
# Built-in Commands
# =============================================================================


@command(
    name="help",
    description="Show help for commands",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
    aliases=["?"],
)
def cmd_help(topic: str = "") -> str:
    """Show help for commands."""
    return registry.help(topic if topic else None)


@command(
    name="echo",
    description="Print a message",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
)
def cmd_echo(message: str = "") -> str:
    """Print a message."""
    return message


@command(
    name="system.cheats",
    description="Enable or disable cheat commands",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=["system.cheats 1", "system.cheats 0"],
)
def cmd_cheats(enabled: int = 1) -> str:
    """Enable or disable cheat commands."""
    registry.cheats_enabled = bool(enabled)
    return f"Cheats {'enabled' if registry.cheats_enabled else 'disabled'}"


@command(
    name="system.dev",
    description="Enable or disable developer mode",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=["system.dev 1", "system.dev 0"],
)
def cmd_dev(enabled: int = 1) -> str:
    """Enable or disable developer mode."""
    registry.dev_mode = bool(enabled)
    return f"Developer mode {'enabled' if registry.dev_mode else 'disabled'}"


@command(
    name="system.quit",
    description="Quit the game",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
    aliases=["quit", "exit"],
)
def cmd_quit() -> CommandResult:
    """Quit the game."""
    ctx = registry.get_context()
    if ctx and hasattr(ctx, "quit"):
        ctx.quit()
    return CommandResult.ok("Quitting...")


@command(
    name="system.save",
    description="Save game to file",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
    examples=["system.save", "system.save mysave"],
)
def cmd_save(filename: str = "quicksave") -> CommandResult:
    """Save game to file."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "world") and hasattr(ctx.world, "save_to_file"):
        path = Path(f"saves/{filename}.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx.world.save_to_file(path)
        return CommandResult.ok(f"Game saved to {path}")
    
    return CommandResult.error("Save not supported")


@command(
    name="system.load",
    description="Load game from file",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
    examples=["system.load", "system.load mysave"],
)
def cmd_load(filename: str = "quicksave") -> CommandResult:
    """Load game from file."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "world") and hasattr(ctx.world, "load_from_file"):
        path = Path(f"saves/{filename}.json")
        if not path.exists():
            return CommandResult.error(f"Save not found: {path}")
        ctx.world.load_from_file(path)
        return CommandResult.ok(f"Game loaded from {path}")
    
    return CommandResult.error("Load not supported")


@command(
    name="exec",
    description="Execute a command script",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=["exec setup_village.txt"],
)
def cmd_exec(filename: str) -> CommandResult:
    """Execute a command script."""
    path = Path(f"scripts/{filename}")
    if not path.exists():
        path = Path(filename)
    
    if not path.exists():
        return CommandResult.error(f"Script not found: {filename}")
    
    results = execute_script(path)
    errors = [r for r in results if not r.success]
    
    if errors:
        return CommandResult.error(f"Script had {len(errors)} errors:\n" + "\n".join(e.message for e in errors))
    
    return CommandResult.ok(f"Executed {len(results)} commands")


@command(
    name="record",
    description="Start recording commands to file",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=["record myscript.txt"],
)
def cmd_record(filename: str) -> CommandResult:
    """Start recording commands to file."""
    path = Path(f"scripts/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    
    if script_recorder.start(path):
        return CommandResult.ok(f"Recording to {path}")
    return CommandResult.error("Already recording")


@command(
    name="stoprecord",
    description="Stop recording commands",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
)
def cmd_stoprecord() -> CommandResult:
    """Stop recording commands."""
    if script_recorder.stop():
        return CommandResult.ok("Recording stopped")
    return CommandResult.error("Not recording")


@command(
    name="bind",
    description="Bind a key to a command",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=['bind f1 "player.god"', 'bind f5 "system.save quicksave"'],
)
def cmd_bind(key: str, command_str: str) -> CommandResult:
    """Bind a key to a command."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "keybinds"):
        ctx.keybinds[key.upper()] = command_str
        return CommandResult.ok(f"Bound {key.upper()} to '{command_str}'")
    
    return CommandResult.error("Keybinds not supported")


@command(
    name="unbind",
    description="Remove a key binding",
    category=Category.SYSTEM,
    access=AccessLevel.CONSOLE,
    examples=["unbind f1"],
)
def cmd_unbind(key: str) -> CommandResult:
    """Remove a key binding."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "keybinds"):
        if key.upper() in ctx.keybinds:
            del ctx.keybinds[key.upper()]
            return CommandResult.ok(f"Unbound {key.upper()}")
        return CommandResult.error(f"Key not bound: {key}")
    
    return CommandResult.error("Keybinds not supported")


@command(
    name="binds",
    description="List all key bindings",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
)
def cmd_binds() -> CommandResult:
    """List all key bindings."""
    ctx = registry.get_context()
    if not ctx:
        return CommandResult.error("No game context")
    
    if hasattr(ctx, "keybinds"):
        if not ctx.keybinds:
            return CommandResult.ok("No custom keybinds")
        
        lines = ["Key bindings:"]
        for key, cmd in sorted(ctx.keybinds.items()):
            lines.append(f"  {key} -> {cmd}")
        return CommandResult.ok("\n".join(lines))
    
    return CommandResult.error("Keybinds not supported")


@command(
    name="history",
    description="Show command history",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
)
def cmd_history(count: int = 20) -> str:
    """Show command history."""
    history = registry.get_history(count)
    if not history:
        return "No command history"
    return "\n".join(f"{i+1}. {cmd}" for i, cmd in enumerate(history))


@command(
    name="clear",
    description="Clear console output",
    category=Category.SYSTEM,
    access=AccessLevel.PUBLIC,
)
def cmd_clear() -> CommandResult:
    """Clear console output."""
    ctx = registry.get_context()
    if ctx and hasattr(ctx, "console") and hasattr(ctx.console, "clear"):
        ctx.console.clear()
    return CommandResult.ok("", data={"clear": True})
