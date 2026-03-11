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

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from procengine.game.game_api import Character, NPC, GameWorld
    from procengine.physics import Vec3

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
    "create_creature_wander_behavior",
    "create_flee_behavior",
    # Rotation and vision utilities
    "face_toward",
    "smooth_rotate_toward",
    "is_in_vision_cone",
    # Enhanced creature behaviors
    "create_creature_prey_behavior",
    "create_creature_predator_behavior",
    "create_creature_grazer_behavior",
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
    from procengine.core.seed_registry import SeedRegistry

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
    from procengine.physics import Vec3

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
        npc.rotation = smooth_rotate_toward(
            npc.rotation, face_toward(direction), dt, turn_speed=4.0,
        )
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
    from procengine.physics import Vec3

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


def create_creature_wander_behavior(
    origin: "Vec3",
    wander_radius: float = 10.0,
    speed: float = 2.5,
    wait_min: float = 3.0,
    wait_max: float = 8.0,
    rng: Optional[np.random.Generator] = None,
) -> BehaviorTree:
    """Create a wander behavior for creatures.

    The creature picks a random nearby point, walks to it, pauses, then
    repeats.  Movement is on the XZ plane; the physics system handles Y
    via gravity and heightfield collision.

    Parameters
    ----------
    origin:
        Starting position around which the creature wanders.
    wander_radius:
        Maximum distance from origin for wander targets.
    speed:
        Movement speed in meters per second.
    wait_min:
        Minimum rest time at each target.
    wait_max:
        Maximum rest time at each target.
    rng:
        NumPy random generator for deterministic behavior.
    """
    from procengine.core.seed_registry import SeedRegistry
    from procengine.physics import Vec3

    _rng = rng if rng is not None else SeedRegistry(0).get_rng("creature_wander")

    def pick_wander_target(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        angle = float(_rng.uniform(0, 2 * np.pi))
        dist = float(_rng.uniform(1.0, wander_radius))
        target = Vec3(
            origin.x + dist * np.cos(angle),
            0.0,
            origin.z + dist * np.sin(angle),
        )
        bb.set("wander_target", target)
        return NodeStatus.SUCCESS

    def move_to_target(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        target = bb.get("wander_target")
        if target is None:
            return NodeStatus.FAILURE

        direction = target - entity.position
        direction = Vec3(direction.x, 0, direction.z)
        distance = direction.length()

        if distance < 0.5:
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        # Smoothly rotate toward movement direction
        entity.rotation = smooth_rotate_toward(
            entity.rotation, face_toward(direction), dt, turn_speed=4.0,
        )
        move = direction * min(speed * dt, distance)
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    def rest(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("rest_time"):
            bb.set("rest_time", float(_rng.uniform(wait_min, wait_max)))
            bb.set("rested", 0.0)

        rested = bb.get("rested", 0.0) + dt
        bb.set("rested", rested)

        if rested >= bb.get("rest_time"):
            bb.remove("rest_time")
            bb.remove("rested")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    return BehaviorTree(
        Repeater(
            Sequence([
                Action(pick_wander_target, "PickWanderTarget"),
                Action(move_to_target, "MoveToTarget"),
                Action(rest, "Rest"),
            ]),
            count=-1,
        )
    )


def create_flee_behavior(
    flee_range: float = 8.0,
    speed: float = 4.0,
    flee_distance: float = 15.0,
) -> BehaviorTree:
    """Create a flee behavior that runs from the player when nearby.

    The creature flees when the player is within *flee_range* and reverts
    to idling otherwise.

    Parameters
    ----------
    flee_range:
        Distance at which the creature starts fleeing.
    speed:
        Flee movement speed.
    flee_distance:
        How far the creature runs before stopping.
    """
    from procengine.physics import Vec3

    def is_threat_nearby(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
    ) -> bool:
        player = world.get_player()
        if not player:
            return False
        distance = (player.position - entity.position).length()
        return distance < flee_range

    def flee_from_threat(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        player = world.get_player()
        if not player:
            return NodeStatus.FAILURE

        direction = entity.position - player.position
        direction = Vec3(direction.x, 0, direction.z)
        distance_to_player = direction.length()

        if distance_to_player > flee_distance:
            return NodeStatus.SUCCESS

        if distance_to_player < 0.01:
            direction = Vec3(1.0, 0, 0)
        else:
            direction = direction.normalized()

        # Snap rotation to flee direction (urgent, no smooth turn)
        entity.rotation = face_toward(direction)
        move = direction * speed * dt
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    def idle_wait(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        waited = bb.get("idle_waited", 0.0) + dt
        bb.set("idle_waited", waited)
        if waited >= 2.0:
            bb.set("idle_waited", 0.0)
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    return BehaviorTree(
        Repeater(
            Selector([
                Sequence([
                    Condition(is_threat_nearby, "ThreatNearby"),
                    Action(flee_from_threat, "FleeFromThreat"),
                ]),
                Action(idle_wait, "IdleWait"),
            ]),
            count=-1,
        )
    )


# =============================================================================
# Rotation and Vision Utilities
# =============================================================================


def face_toward(direction: "Vec3") -> float:
    """Return the Y-axis rotation angle (radians) that faces the given XZ direction.

    Uses ``atan2(x, z)`` matching the convention used by the guard behavior
    and standard Y-up 3D engines (rotation 0 = facing +Z).

    Parameters
    ----------
    direction:
        An XZ-plane direction vector (Y component is ignored).

    Returns
    -------
    float:
        Rotation angle in radians, range [-pi, pi].
    """
    return math.atan2(direction.x, direction.z)


def smooth_rotate_toward(
    current_angle: float,
    target_angle: float,
    dt: float,
    turn_speed: float = 4.0,
) -> float:
    """Smoothly interpolate a rotation angle toward a target.

    Rotates via the shortest arc (handles wrap-around correctly) at a rate
    governed by *turn_speed* (radians per second).

    Parameters
    ----------
    current_angle:
        Current Y-axis rotation in radians.
    target_angle:
        Desired Y-axis rotation in radians.
    dt:
        Delta time in seconds.
    turn_speed:
        Maximum radians per second to turn.

    Returns
    -------
    float:
        Updated rotation angle in radians, range [-pi, pi].
    """
    diff = target_angle - current_angle
    # Wrap to [-pi, pi] for shortest-arc
    diff = (diff + math.pi) % (2.0 * math.pi) - math.pi
    max_step = turn_speed * dt
    if abs(diff) <= max_step:
        return target_angle
    return current_angle + math.copysign(max_step, diff)


def is_in_vision_cone(
    observer_position: "Vec3",
    observer_rotation: float,
    target_position: "Vec3",
    cone_half_angle: float = math.radians(60.0),
    max_range: float = 15.0,
) -> bool:
    """Check whether *target_position* falls within the observer's vision cone.

    The vision cone is a sector on the XZ plane centered on the observer's
    facing direction (derived from *observer_rotation*) with angular half-width
    *cone_half_angle* and depth *max_range*.

    This is the standard "cone of vision" approach used widely in indie and
    AAA game AI alike — a simple dot-product angle check paired with a
    distance check.

    Parameters
    ----------
    observer_position:
        World-space position of the observer.
    observer_rotation:
        Y-axis rotation of the observer in radians (0 = +Z).
    target_position:
        World-space position of the potential target.
    cone_half_angle:
        Half-angle of the vision cone in radians (default 60 deg → 120 deg total).
    max_range:
        Maximum sight distance in world units.

    Returns
    -------
    bool:
        True if the target is within the cone.
    """
    from procengine.physics import Vec3

    dx = target_position.x - observer_position.x
    dz = target_position.z - observer_position.z
    dist_sq = dx * dx + dz * dz

    if dist_sq > max_range * max_range:
        return False
    if dist_sq < 1e-8:
        return True  # on top of observer

    # Observer's forward direction on XZ plane
    fwd_x = math.sin(observer_rotation)
    fwd_z = math.cos(observer_rotation)

    inv_dist = 1.0 / math.sqrt(dist_sq)
    to_target_x = dx * inv_dist
    to_target_z = dz * inv_dist

    dot = fwd_x * to_target_x + fwd_z * to_target_z
    return dot >= math.cos(cone_half_angle)


# =============================================================================
# Enhanced Creature Behaviors
# =============================================================================


def create_creature_prey_behavior(
    origin: "Vec3",
    wander_radius: float = 10.0,
    speed: float = 2.5,
    flee_range: float = 8.0,
    flee_speed_multiplier: float = 1.5,
    flee_distance: float = 15.0,
    vision_half_angle: float = math.radians(75.0),
    vision_range: float = 15.0,
    wait_min: float = 3.0,
    wait_max: float = 8.0,
    rng: Optional[np.random.Generator] = None,
) -> BehaviorTree:
    """Create a prey behavior that combines awareness, fleeing, grazing, and looking around.

    The prey creature:
    1. Checks its vision cone for threats — flees if a threat is detected.
    2. Periodically pauses to look around (head sweep via rotation).
    3. Wanders to nearby points and rests (grazing).

    This replaces the simpler wander+flee combo with a single, richer tree
    for prey species (deer, goat, bird, etc.).

    Parameters
    ----------
    origin:
        Home position around which the creature wanders.
    wander_radius:
        Maximum distance from origin for wander targets.
    speed:
        Base movement speed.
    flee_range:
        Distance at which threats trigger flight.
    flee_speed_multiplier:
        Speed multiplier when fleeing.
    flee_distance:
        Distance to run before stopping.
    vision_half_angle:
        Half-angle of vision cone in radians.
    vision_range:
        Maximum sight distance.
    wait_min:
        Minimum rest/graze time.
    wait_max:
        Maximum rest/graze time.
    rng:
        NumPy random generator for deterministic behavior.
    """
    from procengine.core.seed_registry import SeedRegistry
    from procengine.physics import Vec3

    _rng = rng if rng is not None else SeedRegistry(0).get_rng("creature_prey")
    flee_speed = speed * flee_speed_multiplier

    # --- Threat detection (vision-cone aware) ---
    def can_see_threat(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
    ) -> bool:
        player = world.get_player()
        if not player:
            return False
        dist = (player.position - entity.position).length()
        if dist > vision_range:
            return False
        # Check vision cone first; if threat is very close, detect regardless
        if dist < flee_range * 0.4:
            return True
        return is_in_vision_cone(
            entity.position, entity.rotation, player.position,
            cone_half_angle=vision_half_angle, max_range=vision_range,
        )

    # --- Flee action ---
    def flee_from_threat(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        player = world.get_player()
        if not player:
            return NodeStatus.FAILURE

        direction = entity.position - player.position
        direction = Vec3(direction.x, 0, direction.z)
        dist = direction.length()

        if dist > flee_distance:
            return NodeStatus.SUCCESS

        if dist < 0.01:
            direction = Vec3(1.0, 0, 0)
        else:
            direction = direction.normalized()

        entity.rotation = face_toward(direction)
        move = direction * flee_speed * dt
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    # --- Look around (head sweep) ---
    def look_around(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("look_start_rot"):
            bb.set("look_start_rot", entity.rotation)
            bb.set("look_elapsed", 0.0)
            bb.set("look_duration", float(_rng.uniform(1.5, 3.0)))

        elapsed = bb.get("look_elapsed", 0.0) + dt
        bb.set("look_elapsed", elapsed)
        duration = bb.get("look_duration", 2.0)

        # Sweep ±45 degrees from start rotation
        t = elapsed / duration
        sweep = math.sin(t * math.pi * 2.0) * math.radians(45.0)
        entity.rotation = bb.get("look_start_rot") + sweep

        if elapsed >= duration:
            entity.rotation = bb.get("look_start_rot")
            bb.remove("look_start_rot")
            bb.remove("look_elapsed")
            bb.remove("look_duration")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    # --- Wander target selection ---
    def pick_wander_target(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        angle = float(_rng.uniform(0, 2 * np.pi))
        dist = float(_rng.uniform(1.0, wander_radius))
        target = Vec3(
            origin.x + dist * np.cos(angle),
            0.0,
            origin.z + dist * np.sin(angle),
        )
        bb.set("wander_target", target)
        return NodeStatus.SUCCESS

    # --- Move to target ---
    def move_to_target(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        target = bb.get("wander_target")
        if target is None:
            return NodeStatus.FAILURE

        direction = target - entity.position
        direction = Vec3(direction.x, 0, direction.z)
        distance = direction.length()

        if distance < 0.5:
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        entity.rotation = smooth_rotate_toward(
            entity.rotation, face_toward(direction), dt, turn_speed=4.0,
        )
        move = direction * min(speed * dt, distance)
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    # --- Rest / Graze ---
    def rest(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("rest_time"):
            bb.set("rest_time", float(_rng.uniform(wait_min, wait_max)))
            bb.set("rested", 0.0)

        rested = bb.get("rested", 0.0) + dt
        bb.set("rested", rested)

        if rested >= bb.get("rest_time"):
            bb.remove("rest_time")
            bb.remove("rested")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    # Build tree:
    #   Repeater(infinite):
    #     Selector:
    #       [1] If threat in vision cone → flee
    #       [2] Sequence: pick target → move → (maybe look around) → rest
    should_look = lambda n, w, b: float(_rng.uniform(0, 1)) < 0.3

    return BehaviorTree(
        Repeater(
            Selector([
                # Priority 1: flee from threats in vision cone
                Sequence([
                    Condition(can_see_threat, "CanSeeThreat"),
                    Action(flee_from_threat, "FleeFromThreat"),
                ]),
                # Priority 2: wander, optionally look around, rest
                Sequence([
                    Action(pick_wander_target, "PickWanderTarget"),
                    Action(move_to_target, "MoveToTarget"),
                    Selector([
                        Sequence([
                            Condition(should_look, "ShouldLookAround"),
                            Action(look_around, "LookAround"),
                        ]),
                        Succeeder(Action(lambda n, w, b, d: NodeStatus.SUCCESS, "SkipLook")),
                    ]),
                    Action(rest, "Rest"),
                ]),
            ]),
            count=-1,
        )
    )


def create_creature_predator_behavior(
    origin: "Vec3",
    patrol_radius: float = 15.0,
    speed: float = 3.0,
    chase_speed_multiplier: float = 1.8,
    vision_half_angle: float = math.radians(55.0),
    vision_range: float = 20.0,
    chase_give_up_distance: float = 25.0,
    rest_min: float = 4.0,
    rest_max: float = 10.0,
    rng: Optional[np.random.Generator] = None,
) -> BehaviorTree:
    """Create a predator behavior with vision-cone-based stalking and chasing.

    The predator creature:
    1. Scans its vision cone for nearby creatures (other species).
    2. Stalks detected prey by moving toward it.
    3. Gives up if prey escapes beyond give-up distance.
    4. Patrols its territory when no prey is detected.

    Parameters
    ----------
    origin:
        Home territory center.
    patrol_radius:
        Maximum patrol distance from origin.
    speed:
        Base movement speed.
    chase_speed_multiplier:
        Speed multiplier when chasing prey.
    vision_half_angle:
        Half-angle of vision cone in radians.
    vision_range:
        Maximum detection distance.
    chase_give_up_distance:
        Distance at which predator abandons chase.
    rest_min:
        Minimum rest time between patrols.
    rest_max:
        Maximum rest time between patrols.
    rng:
        NumPy random generator for deterministic behavior.
    """
    from procengine.core.seed_registry import SeedRegistry
    from procengine.physics import Vec3

    _rng = rng if rng is not None else SeedRegistry(0).get_rng("creature_predator")
    chase_speed = speed * chase_speed_multiplier

    def find_prey_in_vision(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
    ) -> bool:
        from procengine.game.game_api import Creature
        best_dist = float("inf")
        best_target = None
        # Search for other creatures within vision range
        nearby = world.get_entities_in_range(entity.position, vision_range)
        for other in nearby:
            if other is entity or not isinstance(other, Creature):
                continue
            if not other.active:
                continue
            dist = (other.position - entity.position).length()
            if dist < best_dist and is_in_vision_cone(
                entity.position, entity.rotation, other.position,
                cone_half_angle=vision_half_angle, max_range=vision_range,
            ):
                best_dist = dist
                best_target = other
        if best_target is not None:
            bb.set("chase_target_id", best_target.entity_id)
            bb.set("chase_target_pos", best_target.position)
            return True
        return False

    def chase_prey(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        target_id = bb.get("chase_target_id")
        if target_id is None:
            return NodeStatus.FAILURE

        # Try to get live position from the entity
        target_entity = world.get_entity(target_id)
        if target_entity is None or not target_entity.active:
            bb.remove("chase_target_id")
            bb.remove("chase_target_pos")
            return NodeStatus.FAILURE

        from procengine.physics import Vec3 as V3
        target_pos = target_entity.position
        bb.set("chase_target_pos", target_pos)

        direction = target_pos - entity.position
        direction = V3(direction.x, 0, direction.z)
        dist = direction.length()

        if dist > chase_give_up_distance:
            bb.remove("chase_target_id")
            bb.remove("chase_target_pos")
            return NodeStatus.FAILURE

        if dist < 1.0:
            # "Caught" the prey — success (could trigger events later)
            bb.remove("chase_target_id")
            bb.remove("chase_target_pos")
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        entity.rotation = smooth_rotate_toward(
            entity.rotation, face_toward(direction), dt, turn_speed=5.0,
        )
        move = direction * min(chase_speed * dt, dist)
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    def pick_patrol_target(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        angle = float(_rng.uniform(0, 2 * np.pi))
        dist = float(_rng.uniform(2.0, patrol_radius))
        target = Vec3(
            origin.x + dist * np.cos(angle),
            0.0,
            origin.z + dist * np.sin(angle),
        )
        bb.set("patrol_target", target)
        return NodeStatus.SUCCESS

    def move_to_patrol(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        target = bb.get("patrol_target")
        if target is None:
            return NodeStatus.FAILURE

        from procengine.physics import Vec3 as V3
        direction = target - entity.position
        direction = V3(direction.x, 0, direction.z)
        dist = direction.length()

        if dist < 0.5:
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        entity.rotation = smooth_rotate_toward(
            entity.rotation, face_toward(direction), dt, turn_speed=3.5,
        )
        move = direction * min(speed * dt, dist)
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    def rest(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("pred_rest_time"):
            bb.set("pred_rest_time", float(_rng.uniform(rest_min, rest_max)))
            bb.set("pred_rested", 0.0)

        rested = bb.get("pred_rested", 0.0) + dt
        bb.set("pred_rested", rested)

        if rested >= bb.get("pred_rest_time"):
            bb.remove("pred_rest_time")
            bb.remove("pred_rested")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    # Build tree:
    #   Repeater(infinite):
    #     Selector:
    #       [1] If prey in vision → chase
    #       [2] Sequence: pick patrol point → move → rest
    return BehaviorTree(
        Repeater(
            Selector([
                # Priority 1: detect and chase prey
                Sequence([
                    Condition(find_prey_in_vision, "FindPreyInVision"),
                    Action(chase_prey, "ChasePrey"),
                ]),
                # Priority 2: patrol territory
                Sequence([
                    Action(pick_patrol_target, "PickPatrolTarget"),
                    Action(move_to_patrol, "MoveToPatrol"),
                    Action(rest, "PredatorRest"),
                ]),
            ]),
            count=-1,
        )
    )


def create_creature_grazer_behavior(
    origin: "Vec3",
    graze_radius: float = 8.0,
    speed: float = 1.5,
    graze_min: float = 5.0,
    graze_max: float = 12.0,
    look_chance: float = 0.4,
    rng: Optional[np.random.Generator] = None,
) -> BehaviorTree:
    """Create a calm grazer behavior for docile creatures.

    The grazer:
    1. Moves slowly between nearby points.
    2. Grazes (rests with head down implied) for extended periods.
    3. Periodically looks around by sweeping its rotation.

    This is a peaceful behavior for creatures like goats or lizards that
    don't flee aggressively but spend most of their time eating.

    Parameters
    ----------
    origin:
        Center of the grazing area.
    graze_radius:
        Maximum distance from origin.
    speed:
        Slow movement speed.
    graze_min:
        Minimum graze duration.
    graze_max:
        Maximum graze duration.
    look_chance:
        Probability [0-1] of looking around after grazing.
    rng:
        NumPy random generator for deterministic behavior.
    """
    from procengine.core.seed_registry import SeedRegistry
    from procengine.physics import Vec3

    _rng = rng if rng is not None else SeedRegistry(0).get_rng("creature_grazer")

    def pick_graze_spot(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        angle = float(_rng.uniform(0, 2 * np.pi))
        dist = float(_rng.uniform(0.5, graze_radius))
        target = Vec3(
            origin.x + dist * np.cos(angle),
            0.0,
            origin.z + dist * np.sin(angle),
        )
        bb.set("graze_target", target)
        return NodeStatus.SUCCESS

    def amble_to_spot(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        target = bb.get("graze_target")
        if target is None:
            return NodeStatus.FAILURE

        direction = target - entity.position
        direction = Vec3(direction.x, 0, direction.z)
        dist = direction.length()

        if dist < 0.3:
            return NodeStatus.SUCCESS

        direction = direction.normalized()
        entity.rotation = smooth_rotate_toward(
            entity.rotation, face_toward(direction), dt, turn_speed=2.5,
        )
        move = direction * min(speed * dt, dist)
        entity.position = entity.position + move
        return NodeStatus.RUNNING

    def graze(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("graze_time"):
            bb.set("graze_time", float(_rng.uniform(graze_min, graze_max)))
            bb.set("grazed", 0.0)

        grazed = bb.get("grazed", 0.0) + dt
        bb.set("grazed", grazed)

        if grazed >= bb.get("graze_time"):
            bb.remove("graze_time")
            bb.remove("grazed")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    def look_around(
        entity: "Character",
        world: "GameWorld",
        bb: Blackboard,
        dt: float,
    ) -> NodeStatus:
        if not bb.has("look_start_rot"):
            bb.set("look_start_rot", entity.rotation)
            bb.set("look_elapsed", 0.0)
            bb.set("look_duration", float(_rng.uniform(1.0, 2.5)))

        elapsed = bb.get("look_elapsed", 0.0) + dt
        bb.set("look_elapsed", elapsed)
        duration = bb.get("look_duration", 2.0)

        t = elapsed / duration
        sweep = math.sin(t * math.pi * 2.0) * math.radians(35.0)
        entity.rotation = bb.get("look_start_rot") + sweep

        if elapsed >= duration:
            entity.rotation = bb.get("look_start_rot")
            bb.remove("look_start_rot")
            bb.remove("look_elapsed")
            bb.remove("look_duration")
            return NodeStatus.SUCCESS
        return NodeStatus.RUNNING

    should_look = lambda n, w, b: float(_rng.uniform(0, 1)) < look_chance

    return BehaviorTree(
        Repeater(
            Sequence([
                Action(pick_graze_spot, "PickGrazeSpot"),
                Action(amble_to_spot, "AmbleToSpot"),
                Action(graze, "Graze"),
                Selector([
                    Sequence([
                        Condition(should_look, "ShouldLookAround"),
                        Action(look_around, "LookAround"),
                    ]),
                    Succeeder(Action(lambda n, w, b, d: NodeStatus.SUCCESS, "SkipLook")),
                ]),
            ]),
            count=-1,
        )
    )
