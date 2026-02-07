"""Command system (Phase 4).

This module contains the command pattern implementation:
- registry: Command registry for registering and executing commands
- decorators: @command decorator for defining commands
- handlers: Command handler implementations
- console: In-game console for command input
"""

from procengine.commands.commands import (
    CommandRegistry,
    Command,
    command,
    CommandResult,
    AccessLevel,
    Category,
    registry,
)
from procengine.commands.console import (
    Console,
    ConsoleConfig,
    ConsoleLine,
    TextInputBuffer,
    Notification,
    NotificationType,
)

__all__ = [
    "CommandRegistry",
    "Command",
    "command",
    "CommandResult",
    "AccessLevel",
    "Category",
    "registry",
    "Console",
    "ConsoleConfig",
    "ConsoleLine",
    "TextInputBuffer",
    "Notification",
    "NotificationType",
]
