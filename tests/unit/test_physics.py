"""Tests verifying deterministic physics solver behaviour."""

import numpy as np

from procengine.physics import HeightField, RigidBody, step_physics
from procengine.physics.collision import _broad_phase_pairs


def test_head_on_collision_deterministic():
    a = RigidBody(position=[0.0, 0.0], velocity=[1.0, 0.0], mass=1.0, radius=0.5)
    b = RigidBody(position=[1.0, 0.0], velocity=[-1.0, 0.0], mass=1.0, radius=0.5)
    bodies = [a, b]
    step_physics(bodies, dt=1 / 60.0, iterations=5)
    assert np.allclose(a.velocity, [-1.0, 0.0])
    assert np.allclose(b.velocity, [1.0, 0.0])


def test_determinism_repeated():
    init_a = [0.0, 0.0]
    init_b = [1.0, 0.0]
    v_a = [1.0, 0.0]
    v_b = [-1.0, 0.0]
    res1_a = RigidBody(position=init_a, velocity=v_a, mass=1.0, radius=0.5)
    res1_b = RigidBody(position=init_b, velocity=v_b, mass=1.0, radius=0.5)
    step_physics([res1_a, res1_b])

    res2_a = RigidBody(position=init_a, velocity=v_a, mass=1.0, radius=0.5)
    res2_b = RigidBody(position=init_b, velocity=v_b, mass=1.0, radius=0.5)
    step_physics([res2_a, res2_b])

    assert np.allclose(res1_a.position, res2_a.position)
    assert np.allclose(res1_b.position, res2_b.position)
    assert np.allclose(res1_a.velocity, res2_a.velocity)
    assert np.allclose(res1_b.velocity, res2_b.velocity)


def test_broad_phase_matches_naive():
    bodies = [
        RigidBody(position=[0.0, 0.0], velocity=[0.0, 0.0], mass=1.0, radius=0.5),
        RigidBody(position=[0.8, 0.0], velocity=[0.0, 0.0], mass=1.0, radius=0.5),
        RigidBody(position=[3.0, 0.0], velocity=[0.0, 0.0], mass=1.0, radius=0.5),
    ]
    cell_size = 1.0
    pairs = _broad_phase_pairs(bodies, cell_size)
    # Compute expected pairs using brute force distance check
    expected = []
    for i in range(len(bodies)):
        for j in range(i + 1, len(bodies)):
            delta = bodies[j].position - bodies[i].position
            if np.linalg.norm(delta) <= 2 * cell_size:
                expected.append((i, j))
    assert set(pairs) == set(expected)


def test_heightfield_collision():
    body = RigidBody(position=[0.0, 0.5], velocity=[0.0, -1.0], mass=1.0, radius=0.5)
    field = HeightField(np.array([0.0]))
    step_physics([body], heightfield=field)
    assert body.position[1] >= 0.5
    assert body.velocity[1] > 0.0


def test_gravity_effect():
    body = RigidBody(position=[0.0, 10.0], velocity=[0.0, 0.0], mass=1.0, radius=0.5)
    step_physics([body], gravity=-9.8)
    assert body.velocity[1] < 0.0
    assert body.position[1] < 10.0


def test_velocity_damping():
    body = RigidBody(position=[0.0, 0.0], velocity=[2.0, 0.0], mass=1.0, radius=0.5)
    step_physics([body], dt=1.0, damping=0.5)
    assert np.allclose(body.velocity, [1.0, 0.0])
    assert np.allclose(body.position, [1.0, 0.0])
