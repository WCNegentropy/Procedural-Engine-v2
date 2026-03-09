"""Tests for game commands integration.

Tests cover:
- Player commands
- NPC commands
- Quest commands
- World commands
- Integration with GameRunner
"""
import pytest

from procengine.game.game_runner import GameRunner, RunnerConfig, HeadlessBackend
from procengine.commands.commands import registry, CommandResult


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create a GameRunner for testing."""
    config = RunnerConfig(headless=True, world_seed=42)
    backend = HeadlessBackend()
    runner = GameRunner(config, backend=backend)
    runner.initialize()
    runner._init_world(42)
    yield runner
    runner.shutdown()


# =============================================================================
# Player Command Tests
# =============================================================================


class TestPlayerCommands:
    """Tests for player commands."""
    
    def test_player_pos_get(self, runner):
        """Test getting player position."""
        result = runner.execute_command("player.pos")
        assert result.success
        assert "position" in result.message.lower()
        assert result.data is not None
        assert "x" in result.data
        assert "y" in result.data
        assert "z" in result.data
    
    def test_player_teleport_requires_cheats(self, runner):
        """Test teleport requires cheats enabled."""
        registry.cheats_enabled = False
        result = runner.execute_command("player.teleport 10 20 30")
        assert not result.success
        assert "cheats" in result.message.lower()
    
    def test_player_teleport_with_cheats(self, runner):
        """Test teleport works with cheats enabled."""
        registry.cheats_enabled = True
        result = runner.execute_command("player.teleport 10 20 30")
        assert result.success
        assert "10" in result.message
        
        player = runner.player
        assert player.position.x == pytest.approx(10.0)
        assert player.position.y == pytest.approx(20.0)
        assert player.position.z == pytest.approx(30.0)
    
    def test_player_health_get(self, runner):
        """Test getting player health."""
        result = runner.execute_command("player.health")
        assert result.success
        assert "health" in result.message.lower()
        assert result.data is not None
        assert "health" in result.data
    
    def test_player_health_set_requires_cheats(self, runner):
        """Test setting health requires cheats."""
        registry.cheats_enabled = False
        result = runner.execute_command("player.health 50")
        assert not result.success
        assert "cheats" in result.message.lower()
    
    def test_player_health_set_with_cheats(self, runner):
        """Test setting health with cheats enabled."""
        registry.cheats_enabled = True
        result = runner.execute_command("player.health 50")
        assert result.success
        assert runner.player.health == pytest.approx(50.0)
    
    def test_player_inventory(self, runner):
        """Test player inventory command."""
        result = runner.execute_command("player.inventory")
        assert result.success
        # Empty inventory case
        assert "empty" in result.message.lower() or "inventory" in result.message.lower()
    
    def test_player_give_requires_cheats(self, runner):
        """Test give requires cheats."""
        registry.cheats_enabled = False
        result = runner.execute_command("player.give gold 100")
        assert not result.success
    
    def test_player_give_with_cheats(self, runner):
        """Test give works with cheats."""
        registry.cheats_enabled = True
        result = runner.execute_command("player.give gold 100")
        assert result.success
        assert runner.player.inventory.get_count("gold") == 100


# =============================================================================
# World Command Tests
# =============================================================================


class TestWorldCommands:
    """Tests for world commands."""
    
    def test_world_info(self, runner):
        """Test world info command."""
        result = runner.execute_command("world.info")
        assert result.success
        assert "seed" in result.message.lower()
        assert "42" in result.message  # The test seed
    
    def test_world_time_get(self, runner):
        """Test getting world time."""
        result = runner.execute_command("world.time")
        assert result.success
        assert "time" in result.message.lower()
    
    def test_world_time_set_requires_cheats(self, runner):
        """Test setting time requires cheats."""
        registry.cheats_enabled = False
        result = runner.execute_command("world.time 12")
        assert not result.success
    
    def test_world_pause(self, runner):
        """Test pause command."""
        assert not runner.world.paused
        
        result = runner.execute_command("world.pause")
        assert result.success
        assert runner.world.paused
        
        result = runner.execute_command("world.pause")
        assert result.success
        assert not runner.world.paused


# =============================================================================
# Quest Command Tests
# =============================================================================


class TestQuestCommands:
    """Tests for quest commands."""
    
    def test_quest_list(self, runner):
        """Test quest list command."""
        result = runner.execute_command("quest.list")
        assert result.success
    
    def test_quest_start_requires_cheats(self, runner):
        """Test quest start requires cheats."""
        registry.cheats_enabled = False
        result = runner.execute_command("quest.start some_quest")
        assert not result.success
        assert "cheats" in result.message.lower()


# =============================================================================
# NPC Command Tests
# =============================================================================


class TestNPCCommands:
    """Tests for NPC commands."""
    
    def test_npc_list(self, runner):
        """Test NPC list command."""
        result = runner.execute_command("npc.list")
        assert result.success
        # May or may not have NPCs loaded
    
    def test_npc_spawn_requires_console(self, runner):
        """Test NPC spawn requires console open."""
        registry.console_open = False
        result = runner.execute_command("npc.spawn test_npc TestNPC 0 0 0")
        assert not result.success
    
    def test_npc_spawn_with_console(self, runner):
        """Test NPC spawn with console open."""
        registry.console_open = True
        result = runner.execute_command("npc.spawn test_npc TestNPC 10 5 10")
        assert result.success
        
        # Verify NPC was created
        npc = runner.world.get_entity("test_npc")
        assert npc is not None
        assert npc.name == "TestNPC"


# =============================================================================
# System Command Tests
# =============================================================================


class TestSystemCommands:
    """Tests for system commands."""
    
    def test_help_command(self, runner):
        """Test help command."""
        result = runner.execute_command("help")
        assert result.success
        assert "category" in result.message.lower() or "help" in result.message.lower()
    
    def test_echo_command(self, runner):
        """Test echo command."""
        result = runner.execute_command('echo "Hello World"')
        assert result.success
        assert "Hello World" in result.message
    
    def test_cheats_toggle(self, runner):
        """Test cheats toggle."""
        registry.console_open = True
        
        result = runner.execute_command("system.cheats 1")
        assert result.success
        assert registry.cheats_enabled
        
        result = runner.execute_command("system.cheats 0")
        assert result.success
        assert not registry.cheats_enabled
    
    def test_dev_toggle(self, runner):
        """Test dev mode toggle."""
        registry.console_open = True
        
        result = runner.execute_command("system.dev 1")
        assert result.success
        assert registry.dev_mode
        
        result = runner.execute_command("system.dev 0")
        assert result.success
        assert not registry.dev_mode


# =============================================================================
# Console Integration Tests
# =============================================================================


class TestConsoleIntegration:
    """Tests for console integration with GameRunner."""
    
    def test_console_accessible(self, runner):
        """Test console is accessible from runner."""
        assert runner.console is not None
    
    def test_console_toggle(self, runner):
        """Test console can be toggled."""
        assert not runner.console.is_visible
        
        runner._on_console_toggle()
        assert runner.console.is_visible
        
        runner._on_console_toggle()
        assert not runner.console.is_visible
    
    def test_console_open_disables_movement(self, runner):
        """Test opening console disables player movement."""
        assert runner._player_controller.movement_enabled
        
        runner.console.open()
        assert not runner._player_controller.movement_enabled
        
        runner.console.close()
        assert runner._player_controller.movement_enabled
    
    def test_console_command_execution(self, runner):
        """Test executing command through console."""
        runner.console.open()
        runner.console.set_input("help")
        runner.console.submit()
        
        # Output should contain help content
        lines = runner.console._output
        assert len(lines) > 0
    
    def test_keybinds_storage(self, runner):
        """Test keybinds can be stored."""
        assert hasattr(runner, "keybinds")
        assert isinstance(runner.keybinds, dict)
        
        runner.keybinds["F1"] = "help"
        assert runner.keybinds["F1"] == "help"


# =============================================================================
# Command Context Tests
# =============================================================================


class TestCommandContext:
    """Tests for command context (runner) access."""
    
    def test_context_set(self, runner):
        """Test context is set on initialization."""
        assert registry.get_context() is runner
    
    def test_context_provides_world(self, runner):
        """Test context provides world access."""
        ctx = registry.get_context()
        assert hasattr(ctx, "world")
        assert ctx.world is runner.world
    
    def test_context_provides_flags(self, runner):
        """Test context provides flags access."""
        ctx = registry.get_context()
        assert hasattr(ctx, "flags")
        assert isinstance(ctx.flags, dict)
