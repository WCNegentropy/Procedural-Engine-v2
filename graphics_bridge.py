"""Graphics bridge connecting game systems to the rendering backend.

This module provides:
- Camera bridge between player_controller.Camera and graphics.Camera
- Mesh upload helpers
- Material pipeline creation helpers
- Render state management

The bridge abstracts the graphics backend to allow:
- Full rendering when Vulkan/graphics module is available
- Headless/stub mode for testing without graphics

Usage:
    from graphics_bridge import GraphicsBridge

    bridge = GraphicsBridge()
    if bridge.initialize():
        # Upload meshes, create materials
        mesh = bridge.upload_terrain_mesh(heightmap)

        # In render loop:
        bridge.set_camera_from_controller(camera_controller)
        bridge.begin_frame()
        bridge.draw_terrain(mesh)
        bridge.end_frame()
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from physics import Vec3

if TYPE_CHECKING:
    from player_controller import Camera as GameCamera, CameraController
    import numpy as np

__all__ = [
    "GraphicsBridge",
    "RenderState",
    "create_identity_matrix",
    "create_translation_matrix",
    "create_rotation_y_matrix",
    "create_scale_matrix",
]


# =============================================================================
# Matrix Utilities
# =============================================================================


def create_identity_matrix() -> List[float]:
    """Create 4x4 identity matrix as flat list."""
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def create_translation_matrix(x: float, y: float, z: float) -> List[float]:
    """Create 4x4 translation matrix as flat list."""
    return [
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        x, y, z, 1.0,
    ]


def create_rotation_y_matrix(angle: float) -> List[float]:
    """Create 4x4 Y-axis rotation matrix as flat list."""
    c = math.cos(angle)
    s = math.sin(angle)
    return [
        c, 0.0, -s, 0.0,
        0.0, 1.0, 0.0, 0.0,
        s, 0.0, c, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def create_scale_matrix(sx: float, sy: float, sz: float) -> List[float]:
    """Create 4x4 scale matrix as flat list."""
    return [
        sx, 0.0, 0.0, 0.0,
        0.0, sy, 0.0, 0.0,
        0.0, 0.0, sz, 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]


def multiply_matrices(a: List[float], b: List[float]) -> List[float]:
    """Multiply two 4x4 matrices (column-major order)."""
    result = [0.0] * 16
    for i in range(4):
        for j in range(4):
            for k in range(4):
                result[i + j * 4] += a[i + k * 4] * b[k + j * 4]
    return result


def create_transform_matrix(
    position: Vec3,
    rotation_y: float = 0.0,
    scale: float = 1.0,
) -> List[float]:
    """Create a combined transform matrix from position, rotation, and scale."""
    t = create_translation_matrix(position.x, position.y, position.z)
    r = create_rotation_y_matrix(rotation_y)
    s = create_scale_matrix(scale, scale, scale)

    # Order: Scale -> Rotate -> Translate
    return multiply_matrices(t, multiply_matrices(r, s))


# =============================================================================
# Render State
# =============================================================================


@dataclass
class RenderState:
    """Current render state for debugging and testing."""

    frame_count: int = 0
    draw_calls: int = 0
    triangles: int = 0
    vertices: int = 0
    camera_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    camera_target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    light_count: int = 0


# =============================================================================
# Graphics Bridge
# =============================================================================


class GraphicsBridge:
    """Bridge between game systems and graphics backend.

    Provides a unified interface for rendering that works with or without
    the actual Vulkan graphics backend.
    """

    def __init__(self) -> None:
        self._initialized: bool = False
        self._headless: bool = True
        self._graphics_system: Any = None
        self._render_state = RenderState()

        # Cached resources
        self._meshes: Dict[str, Any] = {}
        self._pipelines: Dict[str, Any] = {}

        # Current camera state (from game camera)
        self._camera_position: List[float] = [0.0, 10.0, 10.0]
        self._camera_target: List[float] = [0.0, 0.0, 0.0]
        self._camera_up: List[float] = [0.0, 1.0, 0.0]
        self._camera_fov: float = 60.0

    def initialize(
        self,
        width: int = 1920,
        height: int = 1080,
        enable_validation: bool = True,  # DEBUG: Enable validation by default
        enable_vsync: bool = True,
        window_backend: Optional[Any] = None,
    ) -> bool:
        """Initialize graphics backend.

        Parameters
        ----------
        width:
            Render target width
        height:
            Render target height
        enable_validation:
            Enable Vulkan validation layers for debugging
        enable_vsync:
            Enable vsync (FIFO present mode) for frame rate limiting
        window_backend:
            Optional SDL2Backend with Vulkan support. If provided and supports
            Vulkan, will create a proper swapchain for windowed rendering.

        Returns
        -------
        bool:
            True if graphics are available, False for headless mode.
        """
        try:
            import procengine_cpp as cpp

            # Check if graphics module is available
            if hasattr(cpp, "GraphicsSystem"):
                self._graphics_system = cpp.GraphicsSystem()
                
                # Check if we have an SDL2 backend with Vulkan support
                if (window_backend is not None and 
                    hasattr(window_backend, 'get_vulkan_instance_extensions') and
                    hasattr(window_backend, 'create_vulkan_surface')):
                    
                    # Two-phase initialization for windowed Vulkan rendering
                    print("Initializing graphics with SDL2 Vulkan surface...")
                    
                    # Phase 1: Get required extensions and create Vulkan instance
                    extensions = window_backend.get_vulkan_instance_extensions()
                    if not extensions:
                        print("Warning: Failed to get Vulkan extensions from SDL2")
                        # Fall back to headless
                        return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                    
                    if not self._graphics_system.create_instance_with_extensions(
                        extensions, enable_validation
                    ):
                        print("Warning: Failed to create Vulkan instance with SDL2 extensions")
                        return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                    
                    # Phase 2: Create surface from instance
                    instance_handle = self._graphics_system.get_instance_handle()
                    if instance_handle == 0:
                        print("Warning: Invalid Vulkan instance handle")
                        return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                    
                    surface_handle = window_backend.create_vulkan_surface(instance_handle)
                    if surface_handle is None:
                        print("Warning: Failed to create Vulkan surface from SDL2 window")
                        return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                    
                    # Phase 3: Complete initialization with the surface
                    if self._graphics_system.complete_initialization_with_surface(
                        surface_handle, width, height, enable_vsync
                    ):
                        self._headless = False
                        self._initialized = True
                        print("Graphics initialized with Vulkan surface (windowed mode)")
                        return True
                    else:
                        print("Warning: Failed to complete graphics init with surface")
                        return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                
                else:
                    # Standard headless initialization
                    return self._init_headless(cpp, width, height, enable_validation, enable_vsync)
                    
        except (ImportError, AttributeError) as e:
            print(f"Graphics module import error: {e}")

        # Fall back to headless mode
        self._headless = True
        self._initialized = True
        return False

    def _init_headless(
        self,
        cpp: Any,
        width: int,
        height: int,
        enable_validation: bool,
        enable_vsync: bool,
    ) -> bool:
        """Initialize in headless mode."""
        if self._graphics_system.initialize(width, height, enable_validation, enable_vsync):
            self._headless = False
            self._initialized = True
            print("Graphics initialized in headless mode")
            return True
        
        self._headless = True
        self._initialized = True
        return False

    def shutdown(self) -> None:
        """Shutdown graphics backend."""
        if self._graphics_system:
            self._graphics_system.shutdown()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if initialized."""
        return self._initialized

    @property
    def is_headless(self) -> bool:
        """Check if running in headless mode."""
        return self._headless

    @property
    def render_state(self) -> RenderState:
        """Get current render state."""
        return self._render_state

    # -------------------------------------------------------------------------
    # Camera
    # -------------------------------------------------------------------------

    def set_camera_from_controller(self, camera_controller: "CameraController") -> None:
        """Update graphics camera from game camera controller.

        Parameters
        ----------
        camera_controller:
            The game's camera controller with position and orientation.
        """
        cam = camera_controller.camera

        self._camera_position = [cam.position.x, cam.position.y, cam.position.z]
        self._camera_target = [cam.target.x, cam.target.y, cam.target.z]
        self._camera_up = [0.0, 1.0, 0.0]

        self._render_state.camera_position = tuple(self._camera_position)
        self._render_state.camera_target = tuple(self._camera_target)

        if not self._headless and self._graphics_system:
            try:
                import procengine_cpp as cpp

                graphics_camera = cpp.Camera()
                graphics_camera.position = self._camera_position
                graphics_camera.target = self._camera_target
                graphics_camera.up = self._camera_up
                graphics_camera.fov = self._camera_fov

                self._graphics_system.set_camera(graphics_camera)
            except (ImportError, AttributeError):
                pass

    def set_camera_direct(
        self,
        position: Tuple[float, float, float],
        target: Tuple[float, float, float],
        fov: float = 60.0,
    ) -> None:
        """Set camera directly without controller.

        Parameters
        ----------
        position:
            Camera position in world space.
        target:
            Point the camera looks at.
        fov:
            Field of view in degrees.
        """
        self._camera_position = list(position)
        self._camera_target = list(target)
        self._camera_fov = fov

        self._render_state.camera_position = position
        self._render_state.camera_target = target

        if not self._headless and self._graphics_system:
            try:
                import procengine_cpp as cpp

                graphics_camera = cpp.Camera()
                graphics_camera.position = self._camera_position
                graphics_camera.target = self._camera_target
                graphics_camera.up = self._camera_up
                graphics_camera.fov = fov

                self._graphics_system.set_camera(graphics_camera)
            except (ImportError, AttributeError):
                pass

    # -------------------------------------------------------------------------
    # Mesh Management
    # -------------------------------------------------------------------------

    def upload_mesh(self, name: str, mesh: Any) -> bool:
        """Upload a mesh to GPU.

        Parameters
        ----------
        name:
            Unique name for the mesh.
        mesh:
            Mesh object (props.Mesh from C++ or dict with vertices/indices).

        Returns
        -------
        bool:
            True if uploaded successfully (or stored in headless mode).
        """
        if self._headless:
            # Store reference for headless testing
            self._meshes[name] = {"type": "placeholder", "source": mesh}
            return True

        if self._graphics_system:
            try:
                gpu_mesh = self._graphics_system.upload_mesh(mesh)
                if gpu_mesh.is_valid():
                    self._meshes[name] = gpu_mesh
                    return True
            except Exception:
                pass

        return False

    def upload_terrain_mesh(
        self,
        name: str,
        heightmap: "np.ndarray",
        cell_size: float = 1.0,
        biome_map: Optional["np.ndarray"] = None,
    ) -> bool:
        """Upload terrain mesh from heightmap with optional biome colors.

        Parameters
        ----------
        name:
            Unique name for the terrain mesh.
        heightmap:
            2D numpy array of height values.
        cell_size:
            Size of each terrain cell.
        biome_map:
            Optional 2D numpy array of biome indices (uint8).

        Returns
        -------
        bool:
            True if uploaded successfully.
        """
        try:
            import procengine_cpp as cpp

            # Generate mesh from heightmap with biome colors
            if biome_map is not None:
                mesh = cpp.generate_terrain_mesh_with_biomes(
                    heightmap, biome_map, cell_size, 1.0
                )
                print(f"[TERRAIN] Generated mesh with biome colors:")
                print(f"  vertices: {len(mesh.vertices)}")
                print(f"  normals: {len(mesh.normals)}")
                print(f"  colors: {len(mesh.colors)}")
                print(f"  indices: {len(mesh.indices)}")
                # Log sample colors
                if len(mesh.colors) > 0:
                    c = mesh.colors[0]
                    print(f"  sample color[0]: R={c.x:.3f}, G={c.y:.3f}, B={c.z:.3f}")
                if len(mesh.colors) > 500:
                    c = mesh.colors[500]
                    print(f"  sample color[500]: R={c.x:.3f}, G={c.y:.3f}, B={c.z:.3f}")
            else:
                mesh = cpp.generate_terrain_mesh(heightmap, cell_size, 1.0)
                print(f"[TERRAIN] Generated mesh without biome colors (height-based)")
                print(f"  vertices: {len(mesh.vertices)}")
                print(f"  colors: {len(mesh.colors)}")

            if not mesh.validate():
                print(f"Warning: Terrain mesh validation failed")
                return False

            # Upload to GPU
            if not self._headless and self._graphics_system:
                print(f"[TERRAIN] Uploading mesh to GPU...")
                gpu_mesh = self._graphics_system.upload_mesh(mesh)
                if gpu_mesh.is_valid():
                    self._meshes[name] = gpu_mesh
                    print(f"[TERRAIN] GPU mesh uploaded: vertex_count={gpu_mesh.vertex_count}, index_count={gpu_mesh.index_count}")
                    return True
                print(f"[TERRAIN] ERROR: GPU mesh is not valid!")
                return False
            else:
                print(f"[TERRAIN] Storing as placeholder (headless mode)")
                self._meshes[name] = {
                    "type": "terrain",
                    "mesh": mesh,
                    "width": heightmap.shape[1],
                    "height": heightmap.shape[0],
                }
                return True

        except (ImportError, AttributeError) as e:
            print(f"Warning: C++ terrain mesh generation failed: {e}")
            self._meshes[name] = {
                "type": "terrain",
                "heightmap": heightmap,
                "cell_size": cell_size,
            }
            return True

    def upload_entity_mesh(
        self,
        name: str,
        entity_type: str,
    ) -> bool:
        """Create and upload an entity placeholder mesh.

        Parameters
        ----------
        name:
            Unique name for the entity mesh.
        entity_type:
            Type of entity (player, npc, rock, tree, building, etc.).

        Returns
        -------
        bool:
            True if uploaded successfully.
        """
        try:
            import procengine_cpp as cpp

            # Select appropriate primitive mesh based on entity type
            if entity_type in ("player", "npc", "character"):
                # Capsule for humanoid characters (radius, height, segments, rings)
                mesh = cpp.generate_capsule_mesh(0.5, 1.5, 16, 8)
            elif entity_type == "rock":
                # Use existing rock mesh generator
                desc = cpp.RockDescriptor()
                desc.position = cpp.Vec3(0, 0, 0)
                desc.radius = 0.5
                mesh = cpp.generate_rock_mesh(desc)
            elif entity_type == "tree":
                # Cylinder as placeholder for trees (radius, height, segments)
                mesh = cpp.generate_cylinder_mesh(0.2, 3.0, 16)
            elif entity_type == "building":
                # Box for buildings
                mesh = cpp.generate_box_mesh(cpp.Vec3(3, 2, 3))
            else:
                # Default small box
                mesh = cpp.generate_box_mesh(cpp.Vec3(0.5, 0.5, 0.5))

            # Validate mesh (warn but don't fail for complex meshes)
            if not mesh.validate():
                # Log warning but continue - some complex meshes may have issues
                import warnings
                warnings.warn(f"Mesh validation failed for entity type '{entity_type}', continuing anyway")

            # Upload to GPU if graphics available
            if not self._headless and self._graphics_system:
                try:
                    gpu_mesh = self._graphics_system.upload_mesh(mesh)
                    if gpu_mesh.is_valid():
                        self._meshes[name] = gpu_mesh
                        return True
                    return False
                except Exception:
                    return False
            else:
                # Headless mode - store mesh reference
                self._meshes[name] = {
                    "type": entity_type,
                    "mesh": mesh,
                }
                return True

        except (ImportError, AttributeError) as e:
            # Fallback for headless mode
            self._meshes[name] = {
                "type": entity_type,
            }
            return True

    def get_mesh(self, name: str) -> Optional[Any]:
        """Get a previously uploaded mesh."""
        return self._meshes.get(name)

    def destroy_mesh(self, name: str) -> None:
        """Destroy a mesh and free GPU resources."""
        if name in self._meshes:
            del self._meshes[name]

    # -------------------------------------------------------------------------
    # Pipeline/Material Management
    # -------------------------------------------------------------------------

    def create_material_pipeline(
        self,
        name: str,
        vertex_shader: str,
        fragment_shader: str,
    ) -> bool:
        """Create a material rendering pipeline.

        Parameters
        ----------
        name:
            Unique name for the pipeline.
        vertex_shader:
            GLSL vertex shader source.
        fragment_shader:
            GLSL fragment shader source.

        Returns
        -------
        bool:
            True if created successfully.
        """
        if self._headless:
            self._pipelines[name] = {
                "type": "placeholder",
                "vertex": vertex_shader[:100] + "...",
                "fragment": fragment_shader[:100] + "...",
            }
            return True

        if self._graphics_system:
            try:
                pipeline = self._graphics_system.create_material_pipeline(
                    vertex_shader,
                    fragment_shader,
                )
                if pipeline.is_valid():
                    self._pipelines[name] = pipeline
                    return True
            except Exception:
                pass

        return False

    def get_pipeline(self, name: str) -> Optional[Any]:
        """Get a previously created pipeline."""
        return self._pipelines.get(name)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def begin_frame(self) -> None:
        """Begin a new render frame."""
        self._render_state.draw_calls = 0
        self._render_state.triangles = 0
        self._render_state.vertices = 0

        if not self._headless and self._graphics_system:
            self._graphics_system.begin_frame()

    def end_frame(self) -> None:
        """End frame and present."""
        self._render_state.frame_count += 1

        if not self._headless and self._graphics_system:
            self._graphics_system.end_frame()

    def draw_mesh(
        self,
        mesh_name: str,
        pipeline_name: str,
        transform: Optional[List[float]] = None,
    ) -> None:
        """Draw a mesh with a material pipeline.

        Parameters
        ----------
        mesh_name:
            Name of the uploaded mesh.
        pipeline_name:
            Name of the material pipeline.
        transform:
            4x4 transform matrix (16 floats, column-major). Uses identity if None.
        """
        mesh = self._meshes.get(mesh_name)
        pipeline = self._pipelines.get(pipeline_name)

        # Debug: Log draw call details on first few frames
        if self._render_state.frame_count < 5:
            print(f"[DRAW] mesh={mesh_name}, pipeline={pipeline_name}")
            print(f"  mesh type: {type(mesh).__name__ if mesh else 'None'}")
            print(f"  pipeline type: {type(pipeline).__name__ if pipeline else 'None'}")
            print(f"  headless: {self._headless}")
            print(f"  graphics_system: {self._graphics_system is not None}")

        if mesh is None or pipeline is None:
            if self._render_state.frame_count < 5:
                print(f"  SKIPPED: mesh={mesh is not None}, pipeline={pipeline is not None}")
            return

        # Skip if mesh is a placeholder dict (not a real GPU mesh)
        if isinstance(mesh, dict):
            # Placeholder mesh - just count the draw call for headless stats
            self._render_state.draw_calls += 1
            if self._render_state.frame_count < 5:
                print(f"  SKIPPED: mesh is placeholder dict")
            return

        # Skip if pipeline is a placeholder dict
        if isinstance(pipeline, dict):
            self._render_state.draw_calls += 1
            if self._render_state.frame_count < 5:
                print(f"  SKIPPED: pipeline is placeholder dict")
            return

        if transform is None:
            transform = create_identity_matrix()

        self._render_state.draw_calls += 1

        if not self._headless and self._graphics_system:
            if self._render_state.frame_count < 5:
                print(f"  CALLING graphics_system.draw_mesh()")
            self._graphics_system.draw_mesh(mesh, pipeline, transform)
        elif self._render_state.frame_count < 5:
            print(f"  SKIPPED: headless={self._headless}")

    def draw_entity(
        self,
        mesh_name: str,
        pipeline_name: str,
        position: Vec3,
        rotation: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        """Draw an entity with transform from position/rotation/scale.

        Parameters
        ----------
        mesh_name:
            Name of the uploaded mesh.
        pipeline_name:
            Name of the material pipeline.
        position:
            World position.
        rotation:
            Y-axis rotation in radians.
        scale:
            Uniform scale factor.
        """
        transform = create_transform_matrix(position, rotation, scale)
        self.draw_mesh(mesh_name, pipeline_name, transform)

    # -------------------------------------------------------------------------
    # Lighting
    # -------------------------------------------------------------------------

    def add_light(
        self,
        position: Tuple[float, float, float],
        color: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        intensity: float = 1.0,
        radius: float = 10.0,
    ) -> None:
        """Add a point light to the scene.

        Parameters
        ----------
        position:
            Light position in world space.
        color:
            RGB color (0-1 range).
        intensity:
            Light intensity multiplier.
        radius:
            Light radius for attenuation.
        """
        self._render_state.light_count += 1

        if not self._headless and self._graphics_system:
            try:
                import procengine_cpp as cpp

                light = cpp.Light()
                light.position = list(position)
                light.color = list(color)
                light.intensity = intensity
                light.radius = radius

                self._graphics_system.add_light(light)
            except (ImportError, AttributeError):
                pass

    def clear_lights(self) -> None:
        """Clear all lights from the scene."""
        self._render_state.light_count = 0

        if not self._headless and self._graphics_system:
            try:
                self._graphics_system.clear_lights()
            except (ImportError, AttributeError):
                pass

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get render statistics.

        Returns
        -------
        Dict with frame_count, draw_calls, triangles, vertices, etc.
        """
        if not self._headless and self._graphics_system:
            try:
                stats = self._graphics_system.get_stats()
                return {
                    "frame_count": self._render_state.frame_count,
                    "draw_calls": stats.draw_calls,
                    "triangles": stats.triangles,
                    "vertices": stats.vertices,
                    "frame_time_ms": stats.frame_time_ms,
                }
            except (ImportError, AttributeError):
                pass

        return {
            "frame_count": self._render_state.frame_count,
            "draw_calls": self._render_state.draw_calls,
            "triangles": self._render_state.triangles,
            "vertices": self._render_state.vertices,
            "frame_time_ms": 0.0,
        }
