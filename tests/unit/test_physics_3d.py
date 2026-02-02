"""Tests for 3D physics: Vec3, RigidBody3D, HeightField2D, step_physics_3d."""

import math
import numpy as np
import pytest

from procengine.physics import (
    Vec3,
    RigidBody3D,
    HeightField2D,
    step_physics_3d,
)


# =============================================================================
# Vec3 Tests
# =============================================================================


class TestVec3:
    """Tests for Vec3 class."""

    def test_default_constructor(self):
        v = Vec3()
        assert v.x == 0.0
        assert v.y == 0.0
        assert v.z == 0.0

    def test_value_constructor(self):
        v = Vec3(1.0, 2.0, 3.0)
        assert v.x == 1.0
        assert v.y == 2.0
        assert v.z == 3.0

    def test_addition(self):
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        c = a + b
        assert c == Vec3(5.0, 7.0, 9.0)

    def test_subtraction(self):
        a = Vec3(5.0, 7.0, 9.0)
        b = Vec3(1.0, 2.0, 3.0)
        c = a - b
        assert c == Vec3(4.0, 5.0, 6.0)

    def test_scalar_multiplication(self):
        v = Vec3(1.0, 2.0, 3.0)
        result = v * 2.0
        assert result == Vec3(2.0, 4.0, 6.0)

    def test_scalar_rmul(self):
        v = Vec3(1.0, 2.0, 3.0)
        result = 2.0 * v
        assert result == Vec3(2.0, 4.0, 6.0)

    def test_scalar_division(self):
        v = Vec3(2.0, 4.0, 6.0)
        result = v / 2.0
        assert result == Vec3(1.0, 2.0, 3.0)

    def test_negation(self):
        v = Vec3(1.0, -2.0, 3.0)
        result = -v
        assert result == Vec3(-1.0, 2.0, -3.0)

    def test_dot_product(self):
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(4.0, 5.0, 6.0)
        assert a.dot(b) == 1*4 + 2*5 + 3*6  # 32

    def test_cross_product(self):
        # i × j = k
        i = Vec3(1.0, 0.0, 0.0)
        j = Vec3(0.0, 1.0, 0.0)
        k = i.cross(j)
        assert k == Vec3(0.0, 0.0, 1.0)

        # j × i = -k
        neg_k = j.cross(i)
        assert neg_k == Vec3(0.0, 0.0, -1.0)

    def test_length(self):
        v = Vec3(3.0, 4.0, 0.0)
        assert v.length() == 5.0

    def test_length_squared(self):
        v = Vec3(3.0, 4.0, 0.0)
        assert v.length_squared() == 25.0

    def test_normalized(self):
        v = Vec3(3.0, 4.0, 0.0)
        n = v.normalized()
        assert math.isclose(n.length(), 1.0, rel_tol=1e-6)
        assert math.isclose(n.x, 0.6, rel_tol=1e-6)
        assert math.isclose(n.y, 0.8, rel_tol=1e-6)

    def test_normalized_zero_vector(self):
        v = Vec3(0.0, 0.0, 0.0)
        n = v.normalized()
        assert n == Vec3(0.0, 0.0, 0.0)

    def test_xz_projection(self):
        v = Vec3(1.0, 5.0, 3.0)
        xz = v.xz()
        assert isinstance(xz, np.ndarray)
        assert len(xz) == 2
        assert xz[0] == 1.0
        assert xz[1] == 3.0

    def test_from_xz(self):
        arr = np.array([1.0, 3.0], dtype=np.float32)
        v = Vec3.from_xz(arr, y=5.0)
        assert v == Vec3(1.0, 5.0, 3.0)

    def test_to_array(self):
        v = Vec3(1.0, 2.0, 3.0)
        arr = v.to_array()
        assert isinstance(arr, np.ndarray)
        assert list(arr) == [1.0, 2.0, 3.0]

    def test_from_array(self):
        arr = np.array([1.0, 2.0, 3.0])
        v = Vec3.from_array(arr)
        assert v == Vec3(1.0, 2.0, 3.0)

    def test_equality(self):
        a = Vec3(1.0, 2.0, 3.0)
        b = Vec3(1.0, 2.0, 3.0)
        c = Vec3(1.0, 2.0, 4.0)
        assert a == b
        assert not (a == c)


# =============================================================================
# RigidBody3D Tests
# =============================================================================


class TestRigidBody3D:
    """Tests for RigidBody3D class."""

    def test_default_constructor(self):
        body = RigidBody3D()
        assert body.position == Vec3()
        assert body.velocity == Vec3()
        assert body.mass == 1.0
        assert body.radius == 1.0
        assert body.grounded is False

    def test_custom_constructor(self):
        pos = Vec3(1.0, 2.0, 3.0)
        vel = Vec3(0.5, 0.5, 0.5)
        body = RigidBody3D(position=pos, velocity=vel, mass=2.0, radius=0.5)
        assert body.position == pos
        assert body.velocity == vel
        assert body.mass == 2.0
        assert body.radius == 0.5

    def test_list_conversion(self):
        """Test that lists are converted to Vec3."""
        body = RigidBody3D(position=[1.0, 2.0, 3.0], velocity=[4.0, 5.0, 6.0])
        assert isinstance(body.position, Vec3)
        assert isinstance(body.velocity, Vec3)
        assert body.position == Vec3(1.0, 2.0, 3.0)
        assert body.velocity == Vec3(4.0, 5.0, 6.0)

    def test_invalid_mass(self):
        with pytest.raises(ValueError, match="mass must be positive"):
            RigidBody3D(mass=0.0)

        with pytest.raises(ValueError, match="mass must be positive"):
            RigidBody3D(mass=-1.0)

    def test_invalid_radius(self):
        with pytest.raises(ValueError, match="radius must be positive"):
            RigidBody3D(radius=0.0)

        with pytest.raises(ValueError, match="radius must be positive"):
            RigidBody3D(radius=-1.0)

    def test_inv_mass(self):
        body = RigidBody3D(mass=2.0)
        assert body.inv_mass() == 0.5

    def test_to_2d(self):
        body = RigidBody3D(
            position=Vec3(1.0, 5.0, 3.0),
            velocity=Vec3(2.0, 6.0, 4.0),
            mass=2.0,
            radius=0.5,
        )
        body_2d = body.to_2d()
        # 2D projection uses XZ plane
        assert np.allclose(body_2d.position, [1.0, 3.0])
        assert np.allclose(body_2d.velocity, [2.0, 4.0])
        assert body_2d.mass == 2.0
        assert body_2d.radius == 0.5

    def test_apply_2d_result(self):
        from procengine.physics import RigidBody

        body_3d = RigidBody3D(
            position=Vec3(1.0, 5.0, 3.0),
            velocity=Vec3(2.0, 6.0, 4.0),
        )

        # Simulate 2D collision result
        body_2d = RigidBody(
            position=np.array([10.0, 30.0]),
            velocity=np.array([20.0, 40.0]),
            mass=1.0,
            radius=1.0,
        )

        body_3d.apply_2d_result(body_2d)

        # X and Z should be updated, Y should be preserved
        assert body_3d.position.x == 10.0
        assert body_3d.position.y == 5.0  # Preserved
        assert body_3d.position.z == 30.0

        assert body_3d.velocity.x == 20.0
        assert body_3d.velocity.y == 6.0  # Preserved
        assert body_3d.velocity.z == 40.0


# =============================================================================
# HeightField2D Tests
# =============================================================================


class TestHeightField2D:
    """Tests for HeightField2D class."""

    def test_constructor(self):
        heights = np.array([[0.0, 1.0], [2.0, 3.0]])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)
        assert hf.size_x == 2
        assert hf.size_z == 2

    def test_invalid_heights_1d(self):
        with pytest.raises(ValueError, match="heights must be a 2D array"):
            HeightField2D(heights=np.array([1.0, 2.0, 3.0]))

    def test_invalid_cell_size(self):
        with pytest.raises(ValueError, match="cell_size must be positive"):
            HeightField2D(heights=np.array([[0.0]]), cell_size=0.0)

    def test_sample_corners(self):
        # 2x2 grid with known values
        heights = np.array([
            [0.0, 1.0],  # z=0 row
            [2.0, 3.0],  # z=1 row
        ])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)

        # Sample at corners
        assert hf.sample(0.0, 0.0) == 0.0
        assert hf.sample(1.0, 0.0) == 1.0
        assert hf.sample(0.0, 1.0) == 2.0
        assert hf.sample(1.0, 1.0) == 3.0

    def test_sample_interpolation(self):
        heights = np.array([
            [0.0, 2.0],
            [0.0, 2.0],
        ])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)

        # Sample at midpoint along X
        mid = hf.sample(0.5, 0.0)
        assert math.isclose(mid, 1.0, rel_tol=1e-6)

    def test_sample_bilinear(self):
        heights = np.array([
            [0.0, 0.0],
            [0.0, 4.0],
        ])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)

        # Center should be 1.0 (bilinear interpolation of 0,0,0,4)
        center = hf.sample(0.5, 0.5)
        assert math.isclose(center, 1.0, rel_tol=1e-6)

    def test_sample_clamped_out_of_bounds(self):
        heights = np.array([
            [5.0, 5.0],
            [5.0, 5.0],
        ])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)

        # Out of bounds should clamp
        assert hf.sample(-10.0, -10.0) == 5.0
        assert hf.sample(100.0, 100.0) == 5.0

    def test_in_bounds(self):
        heights = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ])
        hf = HeightField2D(heights=heights, x0=0.0, z0=0.0, cell_size=1.0)

        assert hf.in_bounds(0.0, 0.0) is True
        assert hf.in_bounds(2.0, 1.0) is True
        assert hf.in_bounds(-0.1, 0.0) is False
        assert hf.in_bounds(2.1, 0.0) is False

    def test_offset_origin(self):
        heights = np.array([[10.0]])
        hf = HeightField2D(heights=heights, x0=5.0, z0=5.0, cell_size=1.0)

        assert hf.sample(5.0, 5.0) == 10.0
        assert hf.in_bounds(5.0, 5.0) is True
        assert hf.in_bounds(0.0, 0.0) is False


# =============================================================================
# step_physics_3d Tests
# =============================================================================


class TestStepPhysics3D:
    """Tests for step_physics_3d function."""

    def test_empty_bodies(self):
        """Should handle empty list without error."""
        step_physics_3d([])

    def test_invalid_dt(self):
        with pytest.raises(ValueError, match="dt must be positive"):
            step_physics_3d([], dt=0.0)

        with pytest.raises(ValueError, match="dt must be positive"):
            step_physics_3d([], dt=-1.0)

    def test_invalid_iterations(self):
        with pytest.raises(ValueError, match="iterations must be at least 1"):
            step_physics_3d([], iterations=0)

    def test_gravity_effect(self):
        """Body should fall under gravity."""
        body = RigidBody3D(position=Vec3(0.0, 10.0, 0.0))
        step_physics_3d([body], gravity=-9.8, dt=1/60)

        assert body.velocity.y < 0.0
        assert body.position.y < 10.0

    def test_terrain_collision(self):
        """Body should land on terrain."""
        heights = np.ones((10, 10)) * 5.0  # Flat terrain at y=5
        hf = HeightField2D(heights=heights, cell_size=1.0)

        body = RigidBody3D(
            position=Vec3(5.0, 5.1, 5.0),  # Just above ground
            velocity=Vec3(0.0, -1.0, 0.0),  # Moving down
            radius=0.5,
        )

        step_physics_3d([body], heightfield=hf, gravity=-9.8)

        # Body should be at ground level (height + radius)
        assert body.position.y >= 5.0 + 0.5 - 0.01  # Allow small tolerance
        assert body.grounded is True

    def test_grounded_flag(self):
        """Grounded flag should update correctly."""
        heights = np.zeros((10, 10))
        hf = HeightField2D(heights=heights, cell_size=1.0)

        # Body in air
        body = RigidBody3D(position=Vec3(5.0, 10.0, 5.0), radius=0.5)
        step_physics_3d([body], heightfield=hf, gravity=-9.8)
        assert body.grounded is False

        # Body on ground
        body2 = RigidBody3D(
            position=Vec3(5.0, 0.4, 5.0),
            velocity=Vec3(0.0, -1.0, 0.0),
            radius=0.5,
        )
        step_physics_3d([body2], heightfield=hf, gravity=-9.8)
        assert body2.grounded is True

    def test_xz_collision(self):
        """Two bodies should collide on XZ plane."""
        body_a = RigidBody3D(
            position=Vec3(0.0, 0.0, 0.0),
            velocity=Vec3(1.0, 0.0, 0.0),
            mass=1.0,
            radius=0.5,
        )
        body_b = RigidBody3D(
            position=Vec3(0.8, 0.0, 0.0),  # Close enough to collide
            velocity=Vec3(-1.0, 0.0, 0.0),
            mass=1.0,
            radius=0.5,
        )

        step_physics_3d([body_a, body_b], gravity=0.0, dt=1/60, iterations=10)

        # After collision, velocities should have exchanged
        assert body_a.velocity.x < 0.0
        assert body_b.velocity.x > 0.0

    def test_determinism(self):
        """Same inputs should produce same outputs."""
        def run_simulation():
            body = RigidBody3D(
                position=Vec3(5.0, 10.0, 5.0),
                velocity=Vec3(1.0, 0.0, 1.0),
            )
            heights = np.zeros((10, 10))
            hf = HeightField2D(heights=heights, cell_size=1.0)

            for _ in range(100):
                step_physics_3d([body], heightfield=hf, gravity=-9.8, dt=1/60)

            return body.position, body.velocity

        pos1, vel1 = run_simulation()
        pos2, vel2 = run_simulation()

        assert pos1 == pos2
        assert vel1 == vel2

    def test_damping(self):
        """Velocity should decrease with damping."""
        body = RigidBody3D(
            position=Vec3(0.0, 0.0, 0.0),
            velocity=Vec3(10.0, 10.0, 10.0),
        )

        step_physics_3d([body], gravity=0.0, damping=0.5, dt=1.0)

        # Damping should reduce velocity
        assert body.velocity.x < 10.0
        assert body.velocity.y < 10.0
        assert body.velocity.z < 10.0

    def test_no_gravity(self):
        """Body should maintain height with no gravity."""
        body = RigidBody3D(position=Vec3(0.0, 10.0, 0.0))
        step_physics_3d([body], gravity=0.0, dt=1/60)

        assert body.position.y == 10.0
        assert body.velocity.y == 0.0

    def test_multiple_bodies_falling(self):
        """Multiple bodies should fall independently."""
        heights = np.zeros((20, 20))
        hf = HeightField2D(heights=heights, cell_size=1.0)

        bodies = [
            RigidBody3D(position=Vec3(5.0, 20.0, 5.0), radius=0.5),
            RigidBody3D(position=Vec3(10.0, 15.0, 10.0), radius=0.5),
            RigidBody3D(position=Vec3(15.0, 10.0, 15.0), radius=0.5),
        ]

        # Run for longer to let bodies settle (with restitution they bounce)
        for _ in range(600):
            step_physics_3d(bodies, heightfield=hf, gravity=-9.8, dt=1/60, restitution=0.3)

        # All should be near ground level after settling
        for body in bodies:
            assert math.isclose(body.position.y, 0.5, abs_tol=0.2)


class TestPhysics3DIntegration:
    """Integration tests for 3D physics with terrain."""

    def test_sloped_terrain(self):
        """Body should handle sloped terrain correctly."""
        # Create sloped terrain (increasing height along X)
        size = 10
        heights = np.zeros((size, size))
        for i in range(size):
            heights[:, i] = float(i) * 0.5  # Slope up along X

        hf = HeightField2D(heights=heights, cell_size=1.0)

        body = RigidBody3D(
            position=Vec3(5.0, 10.0, 5.0),
            velocity=Vec3(0.0, 0.0, 0.0),
            radius=0.5,
        )

        # Let body fall and settle (longer with low restitution)
        for _ in range(600):
            step_physics_3d([body], heightfield=hf, gravity=-9.8, dt=1/60, restitution=0.3)

        # Should land on slope at appropriate height
        expected_ground = hf.sample(body.position.x, body.position.z) + 0.5
        assert math.isclose(body.position.y, expected_ground, abs_tol=0.3)

    def test_terrain_bounce(self):
        """Body should bounce off terrain with restitution."""
        heights = np.zeros((10, 10))
        hf = HeightField2D(heights=heights, cell_size=1.0)

        body = RigidBody3D(
            position=Vec3(5.0, 5.0, 5.0),
            velocity=Vec3(0.0, -5.0, 0.0),  # Moving down fast
            radius=0.5,
        )

        step_physics_3d([body], heightfield=hf, gravity=0.0, restitution=1.0, dt=1/60)

        # With full restitution, body should bounce up
        if body.position.y <= 0.5:
            assert body.velocity.y >= 0.0
