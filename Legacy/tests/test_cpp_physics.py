"""Integration tests for the C++ physics module."""

from __future__ import annotations

import math
import pytest

procengine_cpp = pytest.importorskip("procengine_cpp")


def test_vec2_basic_operations() -> None:
    """Vec2 class supports basic operations."""
    v1 = procengine_cpp.Vec2(3.0, 4.0)
    assert v1.x == 3.0
    assert v1.y == 4.0
    assert abs(v1.length() - 5.0) < 1e-6

    v2 = procengine_cpp.Vec2(1.0, 0.0)
    assert abs(v1.dot(v2) - 3.0) < 1e-6


def test_rigid_body_creation() -> None:
    """RigidBody can be created with position, velocity, mass, and radius."""
    pos = procengine_cpp.Vec2(1.0, 2.0)
    vel = procengine_cpp.Vec2(3.0, 4.0)
    body = procengine_cpp.RigidBody(pos, vel, 5.0, 0.5)

    assert body.position.x == 1.0
    assert body.position.y == 2.0
    assert body.velocity.x == 3.0
    assert body.velocity.y == 4.0
    assert body.mass == 5.0
    assert body.radius == 0.5


def test_head_on_collision_deterministic() -> None:
    """Two bodies colliding head-on produce deterministic results."""
    def run_collision():
        body_a = procengine_cpp.RigidBody(
            procengine_cpp.Vec2(0.0, 0.0),
            procengine_cpp.Vec2(1.0, 0.0),
            1.0, 0.5
        )
        body_b = procengine_cpp.RigidBody(
            procengine_cpp.Vec2(0.8, 0.0),
            procengine_cpp.Vec2(-1.0, 0.0),
            1.0, 0.5
        )
        bodies = [body_a, body_b]
        procengine_cpp.step_physics(bodies, dt=1/60, iterations=10, restitution=1.0)
        return bodies[0].velocity.x, bodies[1].velocity.x

    v1a, v1b = run_collision()
    v2a, v2b = run_collision()

    assert abs(v1a - v2a) < 1e-6, "Collision should be deterministic"
    assert abs(v1b - v2b) < 1e-6, "Collision should be deterministic"


def test_collision_velocity_exchange() -> None:
    """Equal mass collision should exchange velocities (elastic)."""
    body_a = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.0, 0.0),
        procengine_cpp.Vec2(1.0, 0.0),
        1.0, 0.5
    )
    body_b = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.9, 0.0),  # Close enough to collide
        procengine_cpp.Vec2(0.0, 0.0),
        1.0, 0.5
    )
    bodies = [body_a, body_b]

    # Step multiple times to ensure collision
    for _ in range(5):
        procengine_cpp.step_physics(bodies, dt=1/60, iterations=10, restitution=1.0)

    # After elastic collision, velocities should roughly exchange
    # Body A should slow down, Body B should speed up
    assert bodies[0].velocity.x < 1.0, "Body A should slow down after collision"
    assert bodies[1].velocity.x > 0.0, "Body B should speed up after collision"


def test_heightfield_collision() -> None:
    """Bodies bounce off heightfield."""
    heights = [0.0, 0.0, 1.0, 1.0, 0.0]  # Small hill in the middle
    hf = procengine_cpp.HeightField(heights, x0=0.0, cell_size=1.0)

    # Test sampling
    assert hf.sample(0.5) == 0.0
    assert hf.sample(2.5) == 1.0

    # Create body falling onto heightfield
    body = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.5, 2.0),
        procengine_cpp.Vec2(0.0, -5.0),  # Falling down
        1.0, 0.5
    )
    bodies = [body]

    # Step physics with heightfield
    for _ in range(10):
        procengine_cpp.step_physics(bodies, dt=1/60, heightfield=hf, restitution=1.0)

    # Body should be above ground (height 0 + radius 0.5)
    assert bodies[0].position.y >= 0.5, "Body should stay above heightfield"


def test_gravity_effect() -> None:
    """Gravity accelerates bodies downward."""
    body = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.0, 10.0),
        procengine_cpp.Vec2(0.0, 0.0),
        1.0, 0.5
    )
    bodies = [body]

    initial_y = bodies[0].position.y
    initial_vy = bodies[0].velocity.y

    # Step with gravity
    procengine_cpp.step_physics(bodies, dt=1/60, gravity=-9.8)

    # Velocity should become negative (falling)
    assert bodies[0].velocity.y < initial_vy, "Gravity should accelerate downward"
    # Position should decrease
    assert bodies[0].position.y < initial_y, "Body should fall"


def test_velocity_damping() -> None:
    """Damping reduces velocity over time."""
    body = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.0, 0.0),
        procengine_cpp.Vec2(10.0, 10.0),
        1.0, 0.5
    )
    bodies = [body]

    initial_speed = bodies[0].velocity.length()

    # Step with damping
    for _ in range(10):
        procengine_cpp.step_physics(bodies, dt=1/60, damping=2.0)

    final_speed = bodies[0].velocity.length()
    assert final_speed < initial_speed, "Damping should reduce velocity"


def test_physics_world_basic() -> None:
    """PhysicsWorld manages bodies correctly."""
    world = procengine_cpp.PhysicsWorld()

    body1 = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.0, 0.0),
        procengine_cpp.Vec2(1.0, 0.0),
        1.0, 0.5
    )
    body2 = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(5.0, 0.0),
        procengine_cpp.Vec2(-1.0, 0.0),
        1.0, 0.5
    )

    idx1 = world.add_body(body1)
    idx2 = world.add_body(body2)

    assert world.body_count() == 2
    assert world.get_body(idx1).position.x == 0.0
    assert world.get_body(idx2).position.x == 5.0

    # Step the world
    config = procengine_cpp.PhysicsConfig()
    config.dt = 1/60
    world.step(config)

    # Bodies should have moved
    assert world.get_body(idx1).position.x > 0.0
    assert world.get_body(idx2).position.x < 5.0

    # Reset
    world.reset()
    assert world.body_count() == 0


def test_physics_world_with_heightfield() -> None:
    """PhysicsWorld supports heightfield collision."""
    world = procengine_cpp.PhysicsWorld()

    hf = procengine_cpp.HeightField([1.0, 1.0, 1.0], x0=0.0, cell_size=1.0)
    world.set_heightfield(hf)

    # Add falling body
    body = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(1.0, 5.0),
        procengine_cpp.Vec2(0.0, -10.0),
        1.0, 0.5
    )
    world.add_body(body)

    config = procengine_cpp.PhysicsConfig()
    config.dt = 1/60
    config.restitution = 0.5

    # Step multiple times
    for _ in range(20):
        world.step(config)

    # Body should have bounced and be above ground
    assert world.get_body(0).position.y >= 1.5, "Body should stay above heightfield"


def test_determinism_repeated() -> None:
    """Multiple runs with same initial conditions produce identical results."""
    def run_simulation():
        bodies = [
            procengine_cpp.RigidBody(
                procengine_cpp.Vec2(0.0, 0.0),
                procengine_cpp.Vec2(2.0, 1.0),
                1.0, 0.5
            ),
            procengine_cpp.RigidBody(
                procengine_cpp.Vec2(1.0, 0.5),
                procengine_cpp.Vec2(-1.0, 0.5),
                2.0, 0.3
            ),
            procengine_cpp.RigidBody(
                procengine_cpp.Vec2(0.5, 1.0),
                procengine_cpp.Vec2(0.0, -2.0),
                0.5, 0.4
            ),
        ]

        for _ in range(100):
            procengine_cpp.step_physics(bodies, dt=1/60, iterations=10, restitution=0.9)

        return [(b.position.x, b.position.y, b.velocity.x, b.velocity.y) for b in bodies]

    results1 = run_simulation()
    results2 = run_simulation()

    for i, (r1, r2) in enumerate(zip(results1, results2)):
        for j in range(4):
            assert abs(r1[j] - r2[j]) < 1e-6, f"Body {i} component {j} should be deterministic"


def test_broad_phase_no_false_negatives() -> None:
    """Broad phase doesn't miss any actual collisions."""
    # Create bodies that will definitely collide
    body_a = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(0.0, 0.0),
        procengine_cpp.Vec2(0.0, 0.0),
        1.0, 1.0
    )
    body_b = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(1.5, 0.0),  # Overlapping (distance 1.5 < sum of radii 2.0)
        procengine_cpp.Vec2(0.0, 0.0),
        1.0, 1.0
    )
    bodies = [body_a, body_b]

    # Give them velocities toward each other
    bodies[0].velocity = procengine_cpp.Vec2(1.0, 0.0)
    bodies[1].velocity = procengine_cpp.Vec2(-1.0, 0.0)

    procengine_cpp.step_physics(bodies, dt=1/60, iterations=10, restitution=1.0)

    # Collision should have been detected and resolved
    # Bodies should be moving apart now
    assert bodies[0].velocity.x < 0 or bodies[1].velocity.x > 0, \
        "Collision should have been resolved"


def test_zero_gravity_no_acceleration() -> None:
    """Without gravity, stationary body stays stationary."""
    body = procengine_cpp.RigidBody(
        procengine_cpp.Vec2(5.0, 5.0),
        procengine_cpp.Vec2(0.0, 0.0),
        1.0, 0.5
    )
    bodies = [body]

    for _ in range(10):
        procengine_cpp.step_physics(bodies, dt=1/60, gravity=0.0)

    assert abs(bodies[0].position.x - 5.0) < 1e-6
    assert abs(bodies[0].position.y - 5.0) < 1e-6
    assert abs(bodies[0].velocity.x) < 1e-6
    assert abs(bodies[0].velocity.y) < 1e-6
