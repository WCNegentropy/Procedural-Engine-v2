"""Behavior Tree system for NPC AI.

This module provides a simple but effective behavior tree implementation
for controlling NPC autonomous behavior. The system supports:

- Composite nodes (Selector, Sequence, Parallel)
- Decorator nodes (Inverter, Repeater, Succeeder)
- Leaf nodes (Action, Condition)
- Blackboard for sharing data between nodes

Behavior trees tick each frame and select actions based on conditions.
Actions can be interrupted by higher-priority behaviors.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from procengine.game.game_api import NPC, GameWorld

__all__ = [
    "NodeStatus",
    "Blackboard",
    "BehaviorNode",
    "CompositeNode",
    "Selector",
    "Sequence",
    "Parallel",
    "DecoratorNode",
    "Inverter",
    "Succeeder",
    "Failer",
    "Repeater",
    "UntilSuccess",
    "UntilFail",
    "Condition",
    "Action",
    "Wait",
    "BehaviorTree",
    "create_idle_behavior",
    "create_patrol_behavior",
    "create_guard_behavior",
]


class NodeStatus(Enum):
    """Status returned by behavior tree nodes."""

    SUCCESS = auto()  # Node completed successfully
    FAILURE = auto()  # Node failed
    RUNNING = auto()  # Node is still executing


@dataclass
class Blackboard:
    """Shared data storage for behavior tree nodes.

    The blackboard allows nodes to share information without direct coupling.
    Common uses include storing targets, waypoints, timers, and state.
    """

    data: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the blackboard."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a value in the blackboard."""
        self.data[key] = value

    def has(self, key: str) -> bool:
        """Check if a key exists in the blackboard."""
        return key in self.data

    def remove(self, key: str) -> None:
        """Remove a key from the blackboard."""
        self.data.pop(key, None)

    def clear(self) -> None:
        """Clear all data from the blackboard."""
        self.data.clear()


class BehaviorNode(ABC):
    """Abstract base class for all behavior tree nodes.

    Each node has a tick() method that returns SUCCESS, FAILURE, or RUNNING.
    Nodes can access the NPC, world, and shared blackboard.
    """

    def __init__(self, name: str = "") -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        """Execute this node and return its status.

        Parameters
        ----------
        npc:
            The NPC this behavior tree controls.
        world:
            The game world for context and queries.
        blackboard:
            Shared data storage for nodes.
        dt:
            Delta time since last tick.

        Returns
        -------
        NodeStatus:
            SUCCESS, FAILURE, or RUNNING.
        """
        pass

    def reset(self) -> None:
        """Reset the node's internal state."""
        pass


# =============================================================================
# Composite Nodes
# =============================================================================


class CompositeNode(BehaviorNode):
    """Base class for nodes with multiple children."""

    def __init__(self, children: Optional[List[BehaviorNode]] = None, name: str = "") -> None:
        super().__init__(name)
        self.children: List[BehaviorNode] = children or []
        self._current_child: int = 0

    def add_child(self, child: BehaviorNode) -> "CompositeNode":
        """Add a child node."""
        self.children.append(child)
        return self

    def reset(self) -> None:
        """Reset this node and all children."""
        self._current_child = 0
        for child in self.children:
            child.reset()


class Selector(CompositeNode):
    """Try each child until one succeeds (OR logic).

    - Returns SUCCESS if any child succeeds
    - Returns FAILURE if all children fail
    - Returns RUNNING if current child is running

    Use for: "Try to attack, else flee, else idle"
    """

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        while self._current_child < len(self.children):
            child = self.children[self._current_child]
            status = child.tick(npc, world, blackboard, dt)

            if status == NodeStatus.SUCCESS:
                self.reset()
                return NodeStatus.SUCCESS
            elif status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            else:  # FAILURE
                self._current_child += 1

        self.reset()
        return NodeStatus.FAILURE


class Sequence(CompositeNode):
    """Run each child in sequence until one fails (AND logic).

    - Returns SUCCESS if all children succeed
    - Returns FAILURE if any child fails
    - Returns RUNNING if current child is running

    Use for: "Move to target, then attack, then retreat"
    """

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        while self._current_child < len(self.children):
            child = self.children[self._current_child]
            status = child.tick(npc, world, blackboard, dt)

            if status == NodeStatus.FAILURE:
                self.reset()
                return NodeStatus.FAILURE
            elif status == NodeStatus.RUNNING:
                return NodeStatus.RUNNING
            else:  # SUCCESS
                self._current_child += 1

        self.reset()
        return NodeStatus.SUCCESS


class Parallel(CompositeNode):
    """Run all children simultaneously.

    Parameters
    ----------
    success_threshold:
        Number of children that must succeed for the node to succeed.
        Default is all children.
    failure_threshold:
        Number of children that must fail for the node to fail.
        Default is 1 (any failure fails the node).
    """

    def __init__(
        self,
        children: Optional[List[BehaviorNode]] = None,
        name: str = "",
        success_threshold: Optional[int] = None,
        failure_threshold: int = 1,
    ) -> None:
        super().__init__(children, name)
        self._success_threshold = success_threshold
        self._failure_threshold = failure_threshold

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        success_count = 0
        failure_count = 0
        running_count = 0

        for child in self.children:
            status = child.tick(npc, world, blackboard, dt)
            if status == NodeStatus.SUCCESS:
                success_count += 1
            elif status == NodeStatus.FAILURE:
                failure_count += 1
            else:
                running_count += 1

        # Check thresholds
        threshold = self._success_threshold or len(self.children)

        if failure_count >= self._failure_threshold:
            self.reset()
            return NodeStatus.FAILURE
        if success_count >= threshold:
            self.reset()
            return NodeStatus.SUCCESS
        if running_count > 0:
            return NodeStatus.RUNNING

        self.reset()
        return NodeStatus.FAILURE


# =============================================================================
# Decorator Nodes
# =============================================================================


class DecoratorNode(BehaviorNode):
    """Base class for nodes that modify a single child's behavior."""

    def __init__(self, child: BehaviorNode, name: str = "") -> None:
        super().__init__(name)
        self.child = child

    def reset(self) -> None:
        """Reset this node and child."""
        self.child.reset()


class Inverter(DecoratorNode):
    """Inverts the child's result (SUCCESS <-> FAILURE).

    RUNNING is passed through unchanged.
    """

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        status = self.child.tick(npc, world, blackboard, dt)
        if status == NodeStatus.SUCCESS:
            return NodeStatus.FAILURE
        elif status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING


class Succeeder(DecoratorNode):
    """Always returns SUCCESS, regardless of child's result.

    Useful for optional behaviors that shouldn't fail the parent.
    """

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        self.child.tick(npc, world, blackboard, dt)
        return NodeStatus.SUCCESS


class Failer(DecoratorNode):
    """Always returns FAILURE, regardless of child's result."""

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        self.child.tick(npc, world, blackboard, dt)
        return NodeStatus.FAILURE


class Repeater(DecoratorNode):
    """Repeats the child a specified number of times.

    Parameters
    ----------
    count:
        Number of times to repeat. -1 for infinite.
    """

    def __init__(
        self,
        child: BehaviorNode,
        count: int = -1,
        name: str = "",
    ) -> None:
        super().__init__(child, name)
        self._count = count
        self._current = 0

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        status = self.child.tick(npc, world, blackboard, dt)

        if status == NodeStatus.RUNNING:
            return NodeStatus.RUNNING

        # Child completed (success or failure)
        self.child.reset()
        self._current += 1

        if self._count == -1:
            # Infinite repeat
            return NodeStatus.RUNNING
        elif self._current >= self._count:
            self.reset()
            return NodeStatus.SUCCESS
        else:
            return NodeStatus.RUNNING

    def reset(self) -> None:
        super().reset()
        self._current = 0


class UntilSuccess(DecoratorNode):
    """Repeats the child until it succeeds."""

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        status = self.child.tick(npc, world, blackboard, dt)

        if status == NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS
        elif status == NodeStatus.RUNNING:
            return NodeStatus.RUNNING
        else:  # FAILURE
            self.child.reset()
            return NodeStatus.RUNNING


class UntilFail(DecoratorNode):
    """Repeats the child until it fails."""

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        status = self.child.tick(npc, world, blackboard, dt)

        if status == NodeStatus.FAILURE:
            return NodeStatus.SUCCESS
        elif status == NodeStatus.RUNNING:
            return NodeStatus.RUNNING
        else:  # SUCCESS
            self.child.reset()
            return NodeStatus.RUNNING


# =============================================================================
# Leaf Nodes
# =============================================================================


class Condition(BehaviorNode):
    """Checks a condition and returns SUCCESS or FAILURE.

    Parameters
    ----------
    check:
        Function that takes (npc, world, blackboard) and returns bool.
    """

    def __init__(
        self,
        check: Callable[["NPC", "GameWorld", Blackboard], bool],
        name: str = "",
    ) -> None:
        super().__init__(name)
        self._check = check

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        result = self._check(npc, world, blackboard)
        return NodeStatus.SUCCESS if result else NodeStatus.FAILURE


class Action(BehaviorNode):
    """Executes an action and returns its status.

    Parameters
    ----------
    execute:
        Function that takes (npc, world, blackboard, dt) and returns NodeStatus.
    """

    def __init__(
        self,
        execute: Callable[["NPC", "GameWorld", Blackboard, float], NodeStatus],
        name: str = "",
    ) -> None:
        super().__init__(name)
        self._execute = execute

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        return self._execute(npc, world, blackboard, dt)


class Wait(BehaviorNode):
    """Wait for a specified duration.

    Returns RUNNING until duration elapses, then SUCCESS.
    """

    def __init__(self, duration: float, name: str = "") -> None:
        super().__init__(name)
        self._duration = duration
        self._elapsed = 0.0

    def tick(
        self,
        npc: "NPC",
        world: "GameWorld",
        blackboard: Blackboard,
        dt: float,
    ) -> NodeStatus:
        self._elapsed += dt
        if self._elapsed >= self._duration:
            self.reset()
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    def reset(self) -> None:
        self._elapsed = 0.0


# =============================================================================
# Behavior Tree
# =============================================================================


class BehaviorTree:
    """Container for a behavior tree with root node and blackboard.

    Usage:
        tree = BehaviorTree(root_node)
        status = tree.tick(npc, world, dt)
    """

    def __init__(self, root: BehaviorNode) -> None:
        self.root = root
        self.blackboard = Blackboard()

    def tick(self, npc: "NPC", world: "GameWorld", dt: float) -> NodeStatus:
        """Tick the behavior tree."""
        return self.root.tick(npc, world, self.blackboard, dt)

    def reset(self) -> None:
        """Reset the entire tree."""
        self.root.reset()
        self.blackboard.clear()


# =============================================================================
# Pre-built Behaviors
# =============================================================================


def create_idle_behavior(
    wait_min: float = 2.0,
    wait_max: float = 5.0,
    rng: Optional[np.random.Generator] = None,
) -> BehaviorTree:
    """Create a simple idle behavior that waits randomly.

    The NPC will wait for a random duration, then repeat.

    Parameters
    ----------
    wait_min:
        Minimum wait time in seconds.
    wait_max:
        Maximum wait time in seconds.
    rng:
        NumPy random Generator for deterministic behavior. If None, a
        default seeded generator is created.
    """
    from seed_registry import SeedRegistry

    # Create deterministic RNG if not provided
    _rng = rng if rng is not None else SeedRegistry(0).get_rng("idle_behavior")

    def random_wait(npc: "NPC", world: "GameWorld", bb: Blackboard, dt: float) -> NodeStatus:
        if not bb.has("wait_time"):
            bb.set("wait_time", float(_rng.uniform(wait_min, wait_max)))
            bb.set("waited", 0.0)

        waited = bb.get("waited", 0.0) + dt
        bb.set("waited", waited)

        if waited >= bb.get("wait_time"):
            bb.remove("wait_time")
            bb.remove("waited")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    return BehaviorTree(
        Repeater(
            Action(random_wait, "RandomWait"),
            count=-1,  # Infinite
        )
    )


def create_patrol_behavior(waypoints: List["Vec3"], speed: float = 3.0) -> BehaviorTree:
    """Create a patrol behavior that moves between waypoints.

    Parameters
    ----------
    waypoints:
        List of Vec3 positions to patrol between.
    speed:
        Movement speed in meters per second.
    """
    from physics import Vec3

    def move_to_waypoint(
        npc: "NPC",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        idx = bb.get("waypoint_index", 0)
        target = waypoints[idx % len(waypoints)]

        direction = target - npc.position
        direction = Vec3(direction.x, 0, direction.z)  # Ignore Y
        distance = direction.length()

        if distance < 0.5:
            # Reached waypoint, move to next
            bb.set("waypoint_index", (idx + 1) % len(waypoints))
            return NodeStatus.SUCCESS

        # Move toward waypoint
        direction = direction.normalized()
        move = direction * min(speed * dt, distance)
        npc.position = npc.position + move
        return NodeStatus.RUNNING

    def wait_at_waypoint(
        npc: "NPC",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        waited = bb.get("patrol_wait", 0.0) + dt
        bb.set("patrol_wait", waited)

        if waited >= 2.0:  # Wait 2 seconds at each waypoint
            bb.set("patrol_wait", 0.0)
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    return BehaviorTree(
        Repeater(
            Sequence([
                Action(move_to_waypoint, "MoveToWaypoint"),
                Action(wait_at_waypoint, "WaitAtWaypoint"),
            ]),
            count=-1,  # Infinite patrol
        )
    )


def create_guard_behavior(
    guard_position: "Vec3",
    alert_range: float = 10.0,
    chase_range: float = 15.0,
) -> BehaviorTree:
    """Create a guard behavior that watches for the player.

    The guard will:
    - Stand at guard position
    - Alert when player enters range
    - Return to position when player leaves

    Parameters
    ----------
    guard_position:
        Position the guard should stay at.
    alert_range:
        Distance at which guard notices player.
    chase_range:
        Maximum distance guard will pursue.
    """
    from physics import Vec3

    def is_player_in_range(
        npc: "NPC",
        world: "GameWorld",
        bb: Blackboard,
    ) -> bool:
        player = world.get_player()
        if not player:
            return False
        distance = (player.position - npc.position).length()
        return distance < alert_range

    def return_to_post(
        npc: "NPC",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        direction = guard_position - npc.position
        direction = Vec3(direction.x, 0, direction.z)
        distance = direction.length()

        if distance < 0.5:
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        npc.position = npc.position + direction * min(3.0 * dt, distance)
        return NodeStatus.RUNNING

    def watch_player(
        npc: "NPC",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        player = world.get_player()
        if not player:
            return NodeStatus.FAILURE

        # Face the player
        direction = player.position - npc.position
        import math
        npc.rotation = math.atan2(direction.x, direction.z)

        # Check if player left range
        distance = (player.position - npc.position).length()
        if distance > chase_range:
            return NodeStatus.FAILURE

        return NodeStatus.RUNNING

    return BehaviorTree(
        Selector([
            # If player in range, watch them
            Sequence([
                Condition(is_player_in_range, "PlayerInRange"),
                UntilFail(Action(watch_player, "WatchPlayer")),
            ]),
            # Otherwise, stay at post (or return to it)
            Sequence([
                Action(return_to_post, "ReturnToPost"),
                Wait(3.0, "StandGuard"),
            ]),
        ])
    )
