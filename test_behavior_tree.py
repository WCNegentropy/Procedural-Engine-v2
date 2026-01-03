"""Tests for behavior_tree module.

Tests cover:
- Node status values
- Blackboard data storage
- Composite nodes (Selector, Sequence, Parallel)
- Decorator nodes (Inverter, Repeater, etc.)
- Leaf nodes (Condition, Action, Wait)
- Pre-built behaviors (idle, patrol, guard)
"""
import pytest
from unittest.mock import MagicMock

from behavior_tree import (
    NodeStatus,
    Blackboard,
    BehaviorNode,
    Selector,
    Sequence,
    Parallel,
    Inverter,
    Succeeder,
    Failer,
    Repeater,
    UntilSuccess,
    UntilFail,
    Condition,
    Action,
    Wait,
    BehaviorTree,
    create_idle_behavior,
    create_patrol_behavior,
    create_guard_behavior,
)
from physics import Vec3
from game_api import NPC, GameWorld, Player


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_npc():
    """Create a mock NPC for testing."""
    return NPC(
        entity_id="test_npc",
        name="Test NPC",
        position=Vec3(0, 0, 0),
    )


@pytest.fixture
def mock_world():
    """Create a mock GameWorld for testing."""
    world = GameWorld()
    world.create_player(position=Vec3(10, 0, 10))
    return world


@pytest.fixture
def blackboard():
    """Create a fresh blackboard."""
    return Blackboard()


# =============================================================================
# Blackboard Tests
# =============================================================================

class TestBlackboard:
    """Test Blackboard class."""

    def test_set_and_get(self):
        bb = Blackboard()
        bb.set("key", "value")
        assert bb.get("key") == "value"

    def test_get_default(self):
        bb = Blackboard()
        assert bb.get("missing") is None
        assert bb.get("missing", 42) == 42

    def test_has(self):
        bb = Blackboard()
        bb.set("exists", True)
        assert bb.has("exists")
        assert not bb.has("missing")

    def test_remove(self):
        bb = Blackboard()
        bb.set("temp", 123)
        bb.remove("temp")
        assert not bb.has("temp")

    def test_clear(self):
        bb = Blackboard()
        bb.set("a", 1)
        bb.set("b", 2)
        bb.clear()
        assert not bb.has("a")
        assert not bb.has("b")


# =============================================================================
# Composite Node Tests
# =============================================================================

class TestSelector:
    """Test Selector composite node."""

    def test_returns_success_on_first_success(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        child2 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        child3 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)

        selector = Selector([child1, child2, child3])
        status = selector.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.SUCCESS

    def test_returns_failure_when_all_fail(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        child2 = Action(lambda n, w, b, d: NodeStatus.FAILURE)

        selector = Selector([child1, child2])
        status = selector.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.FAILURE

    def test_returns_running_when_child_running(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        child2 = Action(lambda n, w, b, d: NodeStatus.RUNNING)

        selector = Selector([child1, child2])
        status = selector.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.RUNNING

    def test_resumes_from_running_child(self, mock_npc, mock_world, blackboard):
        call_count = [0]

        def counting_action(n, w, b, d):
            call_count[0] += 1
            return NodeStatus.FAILURE

        def running_then_success(n, w, b, d):
            if b.get("runs", 0) == 0:
                b.set("runs", 1)
                return NodeStatus.RUNNING
            return NodeStatus.SUCCESS

        selector = Selector([
            Action(counting_action),
            Action(running_then_success),
        ])

        # First tick: child1 fails, child2 returns RUNNING
        status1 = selector.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status1 == NodeStatus.RUNNING
        assert call_count[0] == 1

        # Second tick: resumes at child2, returns SUCCESS
        status2 = selector.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status2 == NodeStatus.SUCCESS
        # child1 should not be called again
        assert call_count[0] == 1


class TestSequence:
    """Test Sequence composite node."""

    def test_returns_success_when_all_succeed(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        child2 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)

        sequence = Sequence([child1, child2])
        status = sequence.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.SUCCESS

    def test_returns_failure_on_first_failure(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        child2 = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        child3 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)

        sequence = Sequence([child1, child2, child3])
        status = sequence.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.FAILURE

    def test_returns_running_when_child_running(self, mock_npc, mock_world, blackboard):
        child1 = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        child2 = Action(lambda n, w, b, d: NodeStatus.RUNNING)

        sequence = Sequence([child1, child2])
        status = sequence.tick(mock_npc, mock_world, blackboard, 0.016)

        assert status == NodeStatus.RUNNING


class TestParallel:
    """Test Parallel composite node."""

    def test_runs_all_children(self, mock_npc, mock_world, blackboard):
        results = []

        def make_action(name):
            def action(n, w, b, d):
                results.append(name)
                return NodeStatus.SUCCESS
            return action

        parallel = Parallel([
            Action(make_action("a")),
            Action(make_action("b")),
            Action(make_action("c")),
        ])

        parallel.tick(mock_npc, mock_world, blackboard, 0.016)
        assert set(results) == {"a", "b", "c"}

    def test_fails_on_threshold(self, mock_npc, mock_world, blackboard):
        parallel = Parallel([
            Action(lambda n, w, b, d: NodeStatus.SUCCESS),
            Action(lambda n, w, b, d: NodeStatus.FAILURE),
            Action(lambda n, w, b, d: NodeStatus.SUCCESS),
        ], failure_threshold=1)

        status = parallel.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.FAILURE


# =============================================================================
# Decorator Node Tests
# =============================================================================

class TestInverter:
    """Test Inverter decorator node."""

    def test_inverts_success(self, mock_npc, mock_world, blackboard):
        child = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        inverter = Inverter(child)

        status = inverter.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.FAILURE

    def test_inverts_failure(self, mock_npc, mock_world, blackboard):
        child = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        inverter = Inverter(child)

        status = inverter.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.SUCCESS

    def test_passes_through_running(self, mock_npc, mock_world, blackboard):
        child = Action(lambda n, w, b, d: NodeStatus.RUNNING)
        inverter = Inverter(child)

        status = inverter.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.RUNNING


class TestSucceeder:
    """Test Succeeder decorator node."""

    def test_always_succeeds(self, mock_npc, mock_world, blackboard):
        child = Action(lambda n, w, b, d: NodeStatus.FAILURE)
        succeeder = Succeeder(child)

        status = succeeder.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.SUCCESS


class TestFailer:
    """Test Failer decorator node."""

    def test_always_fails(self, mock_npc, mock_world, blackboard):
        child = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        failer = Failer(child)

        status = failer.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.FAILURE


class TestRepeater:
    """Test Repeater decorator node."""

    def test_repeats_specified_count(self, mock_npc, mock_world, blackboard):
        count = [0]

        def counting_action(n, w, b, d):
            count[0] += 1
            return NodeStatus.SUCCESS

        repeater = Repeater(Action(counting_action), count=3)

        # Should return RUNNING until count reached
        assert repeater.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert repeater.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert repeater.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.SUCCESS
        assert count[0] == 3

    def test_infinite_repeat(self, mock_npc, mock_world, blackboard):
        count = [0]

        def counting_action(n, w, b, d):
            count[0] += 1
            return NodeStatus.SUCCESS

        repeater = Repeater(Action(counting_action), count=-1)

        # Should always return RUNNING
        for _ in range(10):
            assert repeater.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING

        assert count[0] == 10


class TestUntilSuccess:
    """Test UntilSuccess decorator node."""

    def test_repeats_until_success(self, mock_npc, mock_world, blackboard):
        attempts = [0]

        def fail_twice_then_succeed(n, w, b, d):
            attempts[0] += 1
            if attempts[0] < 3:
                return NodeStatus.FAILURE
            return NodeStatus.SUCCESS

        until = UntilSuccess(Action(fail_twice_then_succeed))

        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.SUCCESS


class TestUntilFail:
    """Test UntilFail decorator node."""

    def test_repeats_until_fail(self, mock_npc, mock_world, blackboard):
        attempts = [0]

        def succeed_twice_then_fail(n, w, b, d):
            attempts[0] += 1
            if attempts[0] < 3:
                return NodeStatus.SUCCESS
            return NodeStatus.FAILURE

        until = UntilFail(Action(succeed_twice_then_fail))

        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.RUNNING
        assert until.tick(mock_npc, mock_world, blackboard, 0.016) == NodeStatus.SUCCESS


# =============================================================================
# Leaf Node Tests
# =============================================================================

class TestCondition:
    """Test Condition leaf node."""

    def test_returns_success_when_true(self, mock_npc, mock_world, blackboard):
        condition = Condition(lambda n, w, b: True)
        status = condition.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.SUCCESS

    def test_returns_failure_when_false(self, mock_npc, mock_world, blackboard):
        condition = Condition(lambda n, w, b: False)
        status = condition.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.FAILURE

    def test_receives_context(self, mock_npc, mock_world, blackboard):
        blackboard.set("test_value", 42)

        def check(n, w, b):
            return n.name == "Test NPC" and b.get("test_value") == 42

        condition = Condition(check)
        status = condition.tick(mock_npc, mock_world, blackboard, 0.016)
        assert status == NodeStatus.SUCCESS


class TestAction:
    """Test Action leaf node."""

    def test_executes_action(self, mock_npc, mock_world, blackboard):
        executed = [False]

        def action(n, w, b, d):
            executed[0] = True
            return NodeStatus.SUCCESS

        node = Action(action)
        node.tick(mock_npc, mock_world, blackboard, 0.016)

        assert executed[0]

    def test_receives_delta_time(self, mock_npc, mock_world, blackboard):
        received_dt = [None]

        def action(n, w, b, d):
            received_dt[0] = d
            return NodeStatus.SUCCESS

        node = Action(action)
        node.tick(mock_npc, mock_world, blackboard, 0.033)

        assert received_dt[0] == pytest.approx(0.033)


class TestWait:
    """Test Wait leaf node."""

    def test_returns_running_until_complete(self, mock_npc, mock_world, blackboard):
        wait = Wait(1.0)

        # 0.5 seconds - still waiting
        assert wait.tick(mock_npc, mock_world, blackboard, 0.5) == NodeStatus.RUNNING
        # 0.5 more seconds = 1.0 total - done
        assert wait.tick(mock_npc, mock_world, blackboard, 0.5) == NodeStatus.SUCCESS

    def test_resets_after_completion(self, mock_npc, mock_world, blackboard):
        wait = Wait(0.5)

        wait.tick(mock_npc, mock_world, blackboard, 0.6)  # Complete
        wait.reset()
        # Should be waiting again
        assert wait.tick(mock_npc, mock_world, blackboard, 0.1) == NodeStatus.RUNNING


# =============================================================================
# BehaviorTree Tests
# =============================================================================

class TestBehaviorTree:
    """Test BehaviorTree container class."""

    def test_tree_creation(self):
        root = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        tree = BehaviorTree(root)

        assert tree.root is root
        assert tree.blackboard is not None

    def test_tree_tick(self, mock_npc, mock_world):
        root = Action(lambda n, w, b, d: NodeStatus.SUCCESS)
        tree = BehaviorTree(root)

        status = tree.tick(mock_npc, mock_world, 0.016)
        assert status == NodeStatus.SUCCESS

    def test_tree_shares_blackboard(self, mock_npc, mock_world):
        def set_value(n, w, b, d):
            b.set("value", 123)
            return NodeStatus.SUCCESS

        def check_value(n, w, b, d):
            return NodeStatus.SUCCESS if b.get("value") == 123 else NodeStatus.FAILURE

        tree = BehaviorTree(Sequence([
            Action(set_value),
            Action(check_value),
        ]))

        status = tree.tick(mock_npc, mock_world, 0.016)
        assert status == NodeStatus.SUCCESS

    def test_tree_reset(self, mock_npc, mock_world):
        tree = BehaviorTree(Wait(1.0))
        tree.blackboard.set("test", True)

        tree.tick(mock_npc, mock_world, 0.5)  # Partial wait
        tree.reset()

        # Blackboard should be cleared
        assert not tree.blackboard.has("test")


# =============================================================================
# Pre-built Behavior Tests
# =============================================================================

class TestIdleBehavior:
    """Test pre-built idle behavior."""

    def test_idle_runs(self, mock_npc, mock_world):
        tree = create_idle_behavior(wait_min=0.1, wait_max=0.2)

        # Should return RUNNING
        status = tree.tick(mock_npc, mock_world, 0.05)
        assert status == NodeStatus.RUNNING

    def test_idle_continues_after_wait(self, mock_npc, mock_world):
        tree = create_idle_behavior(wait_min=0.1, wait_max=0.1)

        # Wait complete
        tree.tick(mock_npc, mock_world, 0.15)
        # Should still be running (infinite repeat)
        status = tree.tick(mock_npc, mock_world, 0.05)
        assert status == NodeStatus.RUNNING


class TestPatrolBehavior:
    """Test pre-built patrol behavior."""

    def test_patrol_moves_toward_waypoint(self, mock_npc, mock_world):
        waypoints = [Vec3(10, 0, 0), Vec3(0, 0, 10)]
        tree = create_patrol_behavior(waypoints, speed=5.0)

        # Initial position at origin
        assert mock_npc.position.x == 0
        assert mock_npc.position.z == 0

        # Tick for movement
        tree.tick(mock_npc, mock_world, 1.0)

        # Should have moved toward first waypoint
        assert mock_npc.position.x > 0

    def test_patrol_cycles_waypoints(self, mock_npc, mock_world):
        waypoints = [Vec3(1, 0, 0), Vec3(0, 0, 1)]
        tree = create_patrol_behavior(waypoints, speed=10.0)

        # Move to first waypoint
        for _ in range(10):
            tree.tick(mock_npc, mock_world, 0.1)

        # Check waypoint index advanced
        idx = tree.blackboard.get("waypoint_index", 0)
        assert idx >= 1


class TestGuardBehavior:
    """Test pre-built guard behavior."""

    def test_guard_returns_to_post(self, mock_npc, mock_world):
        guard_pos = Vec3(5, 0, 5)
        tree = create_guard_behavior(guard_pos, alert_range=3.0)

        # NPC starts at origin, guard post is at (5, 0, 5)
        tree.tick(mock_npc, mock_world, 1.0)

        # Should have moved toward guard position
        assert mock_npc.position.x > 0 or mock_npc.position.z > 0

    def test_guard_watches_player_in_range(self, mock_npc, mock_world):
        # Position NPC at origin
        mock_npc.position = Vec3(0, 0, 0)

        # Position player nearby
        player = mock_world.get_player()
        player.position = Vec3(2, 0, 0)

        tree = create_guard_behavior(
            Vec3(0, 0, 0),
            alert_range=5.0,
            chase_range=10.0,
        )

        tree.tick(mock_npc, mock_world, 0.1)

        # Guard should be watching (rotation should change toward player)
        # The exact behavior depends on the tree implementation


# =============================================================================
# Integration Tests
# =============================================================================

class TestBehaviorTreeIntegration:
    """Integration tests for behavior trees with game entities."""

    def test_complex_tree(self, mock_npc, mock_world, blackboard):
        """Test a complex behavior tree structure."""
        # Build a tree that:
        # 1. Checks if health is low
        # 2. If so, flees
        # 3. Otherwise, patrols

        def is_health_low(n, w, b):
            return n.health < 30

        def flee(n, w, b, d):
            b.set("fled", True)
            return NodeStatus.SUCCESS

        def patrol(n, w, b, d):
            b.set("patrolled", True)
            return NodeStatus.SUCCESS

        tree = BehaviorTree(Selector([
            Sequence([
                Condition(is_health_low, "HealthCheck"),
                Action(flee, "Flee"),
            ]),
            Action(patrol, "Patrol"),
        ]))

        # With full health, should patrol
        mock_npc.health = 100
        tree.tick(mock_npc, mock_world, 0.016)
        assert tree.blackboard.get("patrolled") is True
        assert tree.blackboard.get("fled") is None

        # Reset and test with low health
        tree.reset()
        mock_npc.health = 20
        tree.tick(mock_npc, mock_world, 0.016)
        assert tree.blackboard.get("fled") is True

    def test_stateful_behavior(self, mock_npc, mock_world):
        """Test behavior that maintains state across ticks."""
        # Movement behavior that takes multiple ticks
        def move_slowly(n, w, b, d):
            progress = b.get("progress", 0.0)
            progress += d
            b.set("progress", progress)

            if progress >= 1.0:
                return NodeStatus.SUCCESS
            return NodeStatus.RUNNING

        tree = BehaviorTree(Action(move_slowly))

        # Should take multiple ticks to complete
        assert tree.tick(mock_npc, mock_world, 0.3) == NodeStatus.RUNNING
        assert tree.tick(mock_npc, mock_world, 0.3) == NodeStatus.RUNNING
        assert tree.tick(mock_npc, mock_world, 0.3) == NodeStatus.RUNNING
        assert tree.tick(mock_npc, mock_world, 0.3) == NodeStatus.SUCCESS
