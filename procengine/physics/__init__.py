"""Physics simulation systems.

This module contains the 2D/3D physics simulation:
- bodies: RigidBody, RigidBody3D, Vec3 classes
- collision: Sequential impulse solver, step_physics function
- heightfield: HeightField, HeightField2D terrain collision proxies
"""

from procengine.physics.bodies import RigidBody, RigidBody3D, Vec3
from procengine.physics.collision import step_physics, step_physics_3d, detect_collision
from procengine.physics.heightfield import HeightField, HeightField2D

__all__ = [
    "RigidBody",
    "RigidBody3D",
    "Vec3",
    "step_physics",
    "step_physics_3d",
    "detect_collision",
    "HeightField",
    "HeightField2D",
]
