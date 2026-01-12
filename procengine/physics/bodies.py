"""Rigid body definitions for 2D and 3D physics.

This module provides both 2D and 3D rigid body representations:
- RigidBody: 2D circular rigid body
- Vec3: 3D vector class
- RigidBody3D: 3D spherical rigid body
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import numpy as np


__all__ = ["RigidBody", "Vec3", "RigidBody3D"]


@dataclass
class RigidBody:
    """Minimal rigid body representation for 2D collisions.

    Attributes
    ----------
    position:
        2D position vector.
    velocity:
        2D velocity vector.
    mass:
        Mass of the body; must be positive.
    radius:
        Radius of the circular body used for broad phase and collision
        response.  The solver is intentionally restricted to circles to keep
        the implementation compact and deterministic.
    """

    position: np.ndarray
    velocity: np.ndarray
    mass: float
    radius: float

    def __post_init__(self) -> None:
        if self.mass <= 0:
            raise ValueError("mass must be positive")
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        self.position = np.asarray(self.position, dtype=np.float32)
        self.velocity = np.asarray(self.velocity, dtype=np.float32)


@dataclass
class Vec3:
    """3D vector for physics calculations.

    Provides full operator overloads and common vector operations.
    Immutable-style operations return new Vec3 instances.
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec3:
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec3):
            return NotImplemented
        return self.x == other.x and self.y == other.y and self.z == other.z

    def dot(self, other: Vec3) -> float:
        """Compute dot product with another vector."""
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        """Compute cross product with another vector."""
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        """Compute the magnitude of the vector."""
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def length_squared(self) -> float:
        """Compute the squared magnitude (avoids sqrt)."""
        return self.x * self.x + self.y * self.y + self.z * self.z

    def normalized(self) -> Vec3:
        """Return a unit vector in the same direction."""
        length = self.length()
        if length > 0.0:
            return self / length
        return Vec3(0.0, 0.0, 0.0)

    def xz(self) -> np.ndarray:
        """Project to XZ plane as a 2D numpy array for 2D physics."""
        return np.array([self.x, self.z], dtype=np.float32)

    @staticmethod
    def from_xz(arr: np.ndarray, y: float = 0.0) -> Vec3:
        """Create Vec3 from XZ 2D array with specified Y."""
        return Vec3(float(arr[0]), y, float(arr[1]))

    def to_array(self) -> np.ndarray:
        """Convert to numpy array."""
        return np.array([self.x, self.y, self.z], dtype=np.float32)

    @staticmethod
    def from_array(arr: np.ndarray) -> Vec3:
        """Create Vec3 from numpy array."""
        return Vec3(float(arr[0]), float(arr[1]), float(arr[2]))


@dataclass
class RigidBody3D:
    """3D rigid body for hybrid 2D+height physics.

    Uses the XZ plane for 2D collision resolution and Y for gravity/terrain.
    The body is represented as a sphere with the given radius.

    Attributes
    ----------
    position:
        3D position (Y is up).
    velocity:
        3D velocity vector.
    mass:
        Mass of the body; must be positive.
    radius:
        Collision radius (spherical).
    grounded:
        Whether the body is currently on the ground.
    """

    position: Vec3 = field(default_factory=Vec3)
    velocity: Vec3 = field(default_factory=Vec3)
    mass: float = 1.0
    radius: float = 1.0
    grounded: bool = False

    def __post_init__(self) -> None:
        if self.mass <= 0:
            raise ValueError("mass must be positive")
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        # Ensure position and velocity are Vec3 instances
        if not isinstance(self.position, Vec3):
            if hasattr(self.position, "__iter__"):
                arr = list(self.position)
                self.position = Vec3(float(arr[0]), float(arr[1]), float(arr[2]))
            else:
                self.position = Vec3()
        if not isinstance(self.velocity, Vec3):
            if hasattr(self.velocity, "__iter__"):
                arr = list(self.velocity)
                self.velocity = Vec3(float(arr[0]), float(arr[1]), float(arr[2]))
            else:
                self.velocity = Vec3()

    def inv_mass(self) -> float:
        """Return inverse mass for impulse calculations."""
        return 1.0 / self.mass

    def to_2d(self) -> RigidBody:
        """Project to 2D RigidBody on XZ plane for collision."""
        return RigidBody(
            position=self.position.xz(),
            velocity=self.velocity.xz(),
            mass=self.mass,
            radius=self.radius,
        )

    def apply_2d_result(self, body_2d: RigidBody) -> None:
        """Apply 2D collision results back to 3D body.

        Updates XZ position and velocity from the 2D body result.
        Y components are preserved.
        """
        self.position = Vec3(
            float(body_2d.position[0]),
            self.position.y,
            float(body_2d.position[1]),
        )
        self.velocity = Vec3(
            float(body_2d.velocity[0]),
            self.velocity.y,
            float(body_2d.velocity[1]),
        )
