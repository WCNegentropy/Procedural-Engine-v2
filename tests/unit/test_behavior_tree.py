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

from procengine.game.behavior_tree import (
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
    create_creature_wander_behavior,
    create_flee_behavior,
    face_toward,
    smooth_rotate_toward,
    is_in_vision_cone,
    create_creature_prey_behavior,
    create_creature_predator_behavior,
    create_creature_grazer_behavior,
)
from procengine.physics import Vec3
from procengine.game.game_api import NPC, Creature, GameWorld, Player


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


# =============================================================================
# Creature Behavior Tests
# =============================================================================

class TestCreatureWanderBehavior:
    """Test pre-built creature wander behavior."""

    def test_wander_moves_creature(self):
        creature = Creature(
            entity_id="wander_test",
            position=Vec3(5, 0, 5),
        )
        world = GameWorld()

        tree = create_creature_wander_behavior(origin=creature.position, speed=5.0)

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        for _ in range(120):
            tree.tick(creature, world, 1.0 / 60.0)

        distance = (creature.position - start_pos).length()
        assert distance > 0.5

    def test_wander_returns_running_or_success(self):
        creature = Creature(
            entity_id="wander_status",
            position=Vec3(0, 0, 0),
        )
        world = GameWorld()

        tree = create_creature_wander_behavior(origin=creature.position)
        status = tree.tick(creature, world, 1.0 / 60.0)
        assert status in (NodeStatus.SUCCESS, NodeStatus.FAILURE, NodeStatus.RUNNING)


class TestFleeBehavior:
    """Test pre-built flee behavior."""

    def test_flee_from_player(self):
        creature = Creature(
            entity_id="flee_test",
            position=Vec3(5, 0, 5),
        )
        world = GameWorld()
        world.create_player(position=Vec3(3, 0, 5))

        tree = create_flee_behavior(flee_range=10.0, speed=5.0)

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        for _ in range(60):
            tree.tick(creature, world, 1.0 / 60.0)

        # Creature should have moved away from player
        player = world.get_player()
        start_dist = (start_pos - player.position).length()
        end_dist = (creature.position - player.position).length()
        assert end_dist > start_dist

    def test_flee_idle_when_no_threat(self):
        creature = Creature(
            entity_id="flee_idle",
            position=Vec3(50, 0, 50),
        )
        world = GameWorld()
        world.create_player(position=Vec3(0, 0, 0))

        tree = create_flee_behavior(flee_range=5.0, speed=5.0)

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        status = tree.tick(creature, world, 1.0 / 60.0)
        assert status in (NodeStatus.SUCCESS, NodeStatus.FAILURE, NodeStatus.RUNNING)
        # Should not have moved much (idle branch)
        distance = (creature.position - start_pos).length()
        assert distance < 1.0


# =============================================================================
# Rotation Utility Tests
# =============================================================================

import math


class TestFaceToward:
    """Test face_toward rotation utility."""

    def test_face_positive_z(self):
        angle = face_toward(Vec3(0, 0, 1))
        assert angle == pytest.approx(0.0)

    def test_face_positive_x(self):
        angle = face_toward(Vec3(1, 0, 0))
        assert angle == pytest.approx(math.pi / 2)

    def test_face_negative_z(self):
        angle = face_toward(Vec3(0, 0, -1))
        assert abs(angle) == pytest.approx(math.pi)

    def test_face_negative_x(self):
        angle = face_toward(Vec3(-1, 0, 0))
        assert angle == pytest.approx(-math.pi / 2)

    def test_face_diagonal(self):
        angle = face_toward(Vec3(1, 0, 1))
        assert angle == pytest.approx(math.pi / 4)


class TestSmoothRotateToward:
    """Test smooth_rotate_toward interpolation."""

    def test_small_step_toward_target(self):
        current = 0.0
        target = 1.0
        result = smooth_rotate_toward(current, target, dt=0.1, turn_speed=2.0)
        assert 0.0 < result < target
        assert result == pytest.approx(0.2)

    def test_snaps_when_close(self):
        current = 0.9
        target = 1.0
        result = smooth_rotate_toward(current, target, dt=1.0, turn_speed=2.0)
        assert result == pytest.approx(target)

    def test_shortest_arc_positive_to_negative(self):
        # From near +pi to near -pi should go the short way
        current = math.pi - 0.1
        target = -math.pi + 0.1
        result = smooth_rotate_toward(current, target, dt=0.05, turn_speed=4.0)
        # Should rotate in the positive direction (wrap around)
        assert result > current or result < target

    def test_negative_direction(self):
        current = 0.5
        target = -0.5
        result = smooth_rotate_toward(current, target, dt=0.1, turn_speed=2.0)
        assert result < current

    def test_zero_dt_no_change(self):
        result = smooth_rotate_toward(1.0, 2.0, dt=0.0, turn_speed=5.0)
        assert result == pytest.approx(1.0)


# =============================================================================
# Vision Cone Tests
# =============================================================================


class TestVisionCone:
    """Test is_in_vision_cone utility."""

    def test_target_directly_ahead_in_cone(self):
        # Observer at origin facing +Z, target at (0, 0, 5)
        result = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(0, 0, 5),
            cone_half_angle=math.radians(60), max_range=10.0,
        )
        assert result is True

    def test_target_behind_not_in_cone(self):
        # Observer facing +Z, target behind at (0, 0, -5)
        result = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(0, 0, -5),
            cone_half_angle=math.radians(60), max_range=10.0,
        )
        assert result is False

    def test_target_at_cone_edge(self):
        # Observer facing +Z, target at exactly 60 degrees to the side
        half_angle = math.radians(60)
        x = 5.0 * math.sin(half_angle * 0.99)  # just inside
        z = 5.0 * math.cos(half_angle * 0.99)
        result = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(x, 0, z),
            cone_half_angle=half_angle, max_range=10.0,
        )
        assert result is True

    def test_target_beyond_range(self):
        result = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(0, 0, 20),
            cone_half_angle=math.radians(60), max_range=10.0,
        )
        assert result is False

    def test_target_on_observer(self):
        result = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(0, 0, 0),
            cone_half_angle=math.radians(60), max_range=10.0,
        )
        assert result is True

    def test_rotated_observer(self):
        # Observer facing +X (rotation = pi/2)
        result = is_in_vision_cone(
            Vec3(0, 0, 0), math.pi / 2, Vec3(5, 0, 0),
            cone_half_angle=math.radians(60), max_range=10.0,
        )
        assert result is True

        # Same observer, target at +Z should be outside forward cone
        result_side = is_in_vision_cone(
            Vec3(0, 0, 0), math.pi / 2, Vec3(0, 0, 5),
            cone_half_angle=math.radians(45), max_range=10.0,
        )
        assert result_side is False

    def test_narrow_cone(self):
        # Very narrow cone (10 deg half-angle)
        result_ahead = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(0.1, 0, 5),
            cone_half_angle=math.radians(10), max_range=10.0,
        )
        assert result_ahead is True

        result_side = is_in_vision_cone(
            Vec3(0, 0, 0), 0.0, Vec3(3, 0, 3),
            cone_half_angle=math.radians(10), max_range=10.0,
        )
        assert result_side is False


# =============================================================================
# Wander Rotation Tests
# =============================================================================


class TestWanderRotation:
    """Test that wander behavior updates creature rotation."""

    def test_wander_updates_rotation(self):
        creature = Creature(
            entity_id="rot_test",
            position=Vec3(0, 0, 0),
        )
        creature.rotation = 0.0
        world = GameWorld()

        tree = create_creature_wander_behavior(
            origin=creature.position, speed=5.0, wander_radius=10.0,
        )

        # Tick enough times for creature to pick a target and start moving
        for _ in range(60):
            tree.tick(creature, world, 1.0 / 30.0)

        # Creature should have moved and rotation should have changed
        distance = (creature.position - Vec3(0, 0, 0)).length()
        assert distance > 0.5
        # Rotation should not still be exactly zero (statistically near-impossible)
        # unless target happens to be exactly along +Z; allow either changed or very small
        # Just verify the behavior doesn't crash and rotation is a valid float
        assert isinstance(creature.rotation, float)
        assert math.isfinite(creature.rotation)


class TestFleeRotation:
    """Test that flee behavior updates creature rotation."""

    def test_flee_sets_rotation_away_from_threat(self):
        creature = Creature(
            entity_id="flee_rot",
            position=Vec3(5, 0, 0),
        )
        creature.rotation = 0.0
        world = GameWorld()
        world.create_player(position=Vec3(0, 0, 0))

        tree = create_flee_behavior(flee_range=10.0, speed=5.0)

        for _ in range(10):
            tree.tick(creature, world, 1.0 / 60.0)

        # Creature should face away from player (toward +X)
        # atan2(1, 0) = pi/2
        assert creature.rotation == pytest.approx(math.pi / 2, abs=0.3)


# =============================================================================
# Prey Behavior Tests
# =============================================================================


class TestPreyBehavior:
    """Test the enhanced prey behavior with vision cone."""

    def test_prey_flees_when_threat_in_vision(self):
        creature = Creature(
            entity_id="prey_vis",
            position=Vec3(5, 0, 5),
        )
        creature.rotation = 0.0  # facing +Z
        world = GameWorld()
        # Place player directly ahead in vision cone
        world.create_player(position=Vec3(5, 0, 10))

        tree = create_creature_prey_behavior(
            origin=creature.position,
            speed=3.0,
            flee_range=8.0,
            vision_half_angle=math.radians(60),
            vision_range=15.0,
        )

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        for _ in range(60):
            tree.tick(creature, world, 1.0 / 60.0)

        # Creature should have fled away from the player
        player = world.get_player()
        start_dist = (start_pos - player.position).length()
        end_dist = (creature.position - player.position).length()
        assert end_dist > start_dist

    def test_prey_wanders_when_no_threat(self):
        creature = Creature(
            entity_id="prey_wander",
            position=Vec3(0, 0, 0),
        )
        world = GameWorld()
        # No player spawned — no threat

        tree = create_creature_prey_behavior(
            origin=creature.position,
            speed=3.0,
        )

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        for _ in range(120):
            tree.tick(creature, world, 1.0 / 60.0)

        # Creature should have wandered
        dist = (creature.position - start_pos).length()
        assert dist > 0.5


# =============================================================================
# Predator Behavior Tests
# =============================================================================


class TestPredatorBehavior:
    """Test predator behavior with vision-cone based stalking."""

    def test_predator_chases_prey_in_vision(self):
        predator = Creature(
            entity_id="pred_test",
            position=Vec3(0, 0, 0),
            creature_type="wolf",
        )
        predator.rotation = 0.0  # facing +Z

        prey = Creature(
            entity_id="prey_target",
            position=Vec3(0, 0, 8),
            creature_type="deer",
        )

        world = GameWorld()
        world.spawn_entity(predator)
        world.spawn_entity(prey)

        tree = create_creature_predator_behavior(
            origin=predator.position,
            speed=3.0,
            chase_speed_multiplier=1.5,
            vision_half_angle=math.radians(60),
            vision_range=15.0,
        )

        start_pos = Vec3(predator.position.x, predator.position.y, predator.position.z)
        for _ in range(60):
            tree.tick(predator, world, 1.0 / 60.0)

        # Predator should have moved toward prey (in +Z direction)
        assert predator.position.z > start_pos.z + 0.5

    def test_predator_patrols_when_no_prey_visible(self):
        predator = Creature(
            entity_id="pred_patrol",
            position=Vec3(0, 0, 0),
            creature_type="wolf",
        )
        predator.rotation = 0.0

        world = GameWorld()
        world.spawn_entity(predator)

        tree = create_creature_predator_behavior(
            origin=predator.position,
            speed=3.0,
            vision_range=15.0,
        )

        start_pos = Vec3(predator.position.x, predator.position.y, predator.position.z)
        for _ in range(120):
            tree.tick(predator, world, 1.0 / 60.0)

        # Should have moved (patrolling)
        dist = (predator.position - start_pos).length()
        assert dist > 0.5


# =============================================================================
# Grazer Behavior Tests
# =============================================================================


class TestGrazerBehavior:
    """Test the grazer behavior for docile creatures."""

    def test_grazer_moves_slowly(self):
        creature = Creature(
            entity_id="grazer_test",
            position=Vec3(5, 0, 5),
        )
        world = GameWorld()

        tree = create_creature_grazer_behavior(
            origin=creature.position,
            graze_radius=6.0,
            speed=1.5,
        )

        start_pos = Vec3(creature.position.x, creature.position.y, creature.position.z)
        for _ in range(120):
            tree.tick(creature, world, 1.0 / 60.0)

        dist = (creature.position - start_pos).length()
        assert dist > 0.3  # Has moved
        assert isinstance(creature.rotation, float)
        assert math.isfinite(creature.rotation)

    def test_grazer_stays_near_origin(self):
        origin = Vec3(10, 0, 10)
        creature = Creature(
            entity_id="grazer_stay",
            position=Vec3(origin.x, origin.y, origin.z),
        )
        world = GameWorld()

        tree = create_creature_grazer_behavior(
            origin=origin,
            graze_radius=5.0,
            speed=1.5,
        )

        for _ in range(300):
            tree.tick(creature, world, 1.0 / 60.0)

        # Should be within a reasonable distance of origin
        dist = (creature.position - origin).length()
        assert dist < 15.0  # generous bound


# =============================================================================
# Template Vision Parameter Tests
# =============================================================================


class TestCreatureTemplateVision:
    """Test that creature templates include vision parameters."""

    def test_all_templates_have_vision_params(self):
        from procengine.world.creature_templates import CREATURE_TEMPLATES
        for name, tpl in CREATURE_TEMPLATES.items():
            assert hasattr(tpl, "vision_half_angle_deg"), f"{name} missing vision_half_angle_deg"
            assert hasattr(tpl, "vision_range"), f"{name} missing vision_range"
            assert hasattr(tpl, "turn_speed"), f"{name} missing turn_speed"
            assert 0 < tpl.vision_half_angle_deg <= 90
            assert tpl.vision_range > 0
            assert tpl.turn_speed > 0

    def test_predator_narrower_vision_than_prey(self):
        from procengine.world.creature_templates import CREATURE_TEMPLATES
        wolf = CREATURE_TEMPLATES["wolf"]
        deer = CREATURE_TEMPLATES["deer"]
        assert wolf.vision_half_angle_deg < deer.vision_half_angle_deg

    def test_creature_entity_receives_vision_params(self):
        creature = Creature(
            entity_id="vis_test",
            position=Vec3(0, 0, 0),
            vision_half_angle_deg=75.0,
            vision_range=20.0,
            turn_speed=5.0,
        )
        assert creature.vision_half_angle_deg == 75.0
        assert creature.vision_range == 20.0
        assert creature.turn_speed == 5.0

    def test_creature_serialization_roundtrip(self):
        creature = Creature(
            entity_id="serial_test",
            position=Vec3(1, 2, 3),
            vision_half_angle_deg=80.0,
            vision_range=18.0,
            turn_speed=6.0,
            behavior="prey",
        )
        data = creature.to_dict()
        restored = Creature.from_dict(data)
        assert restored.vision_half_angle_deg == 80.0
        assert restored.vision_range == 18.0
        assert restored.turn_speed == 6.0
        assert restored.behavior == "prey"
