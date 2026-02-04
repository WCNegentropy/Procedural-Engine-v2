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

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from procengine.physics import Vec3

if TYPE_CHECKING:
    from procengine.game.player_controller import Camera as GameCamera, CameraController
    import numpy as np

# Logger for graphics bridge operations
logger = logging.getLogger(__name__)

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
# Entity Color Mapping
# =============================================================================

# Entity type to base color mapping (RGB values in [0, 1])
# These colors are used as base albedo for rendering different entity types
ENTITY_COLORS = {
    "player": (0.85, 0.65, 0.55),     # Skin tone
    "npc": (0.75, 0.60, 0.50),        # Slightly different skin tone
    "character": (0.80, 0.62, 0.52),  # Generic character skin
    "rock": (0.55, 0.50, 0.45),       # Gray rock
    "tree": (0.45, 0.35, 0.25),       # Brown bark
    "building": (0.70, 0.65, 0.60),   # Stone/concrete
}
DEFAULT_ENTITY_COLOR = (0.60, 0.60, 0.60)  # Neutral gray for unknown types


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

                        # Phase 4: Initialize Dear ImGui for UI rendering
                        if hasattr(window_backend, 'sdl_window_handle'):
                            sdl_handle = window_backend.sdl_window_handle
                            if sdl_handle and hasattr(self._graphics_system, 'init_imgui'):
                                if self._graphics_system.init_imgui(sdl_handle):
                                    print("Dear ImGui initialized on graphics bridge")
                                else:
                                    print("Warning: Dear ImGui initialization failed")

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

    def init_imgui(self, window_handle: int) -> bool:
        """Initialize Dear ImGui with the window handle.

        This allows explicit ImGui initialization after the graphics system
        has been initialized, useful when the window handle is available
        later in the initialization sequence.

        Parameters
        ----------
        window_handle:
            Pointer to the SDL window (as an integer).

        Returns
        -------
        bool:
            True if ImGui was successfully initialized, False otherwise.
        """
        if self._headless or not self._graphics_system:
            return False

        try:
            if hasattr(self._graphics_system, 'init_imgui'):
                return self._graphics_system.init_imgui(window_handle)
        except Exception as e:
            print(f"Failed to init ImGui: {e}")

        return False

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
                logger.debug("Generated terrain mesh with biome colors: "
                            f"vertices={len(mesh.vertices)}, normals={len(mesh.normals)}, "
                            f"colors={len(mesh.colors)}, indices={len(mesh.indices)}")
                # Log sample colors at debug level
                if len(mesh.colors) > 0:
                    c = mesh.colors[0]
                    logger.debug(f"Sample color[0]: R={c.x:.3f}, G={c.y:.3f}, B={c.z:.3f}")
            else:
                mesh = cpp.generate_terrain_mesh(heightmap, cell_size, 1.0)
                logger.debug("Generated terrain mesh without biome colors (height-based): "
                            f"vertices={len(mesh.vertices)}, colors={len(mesh.colors)}")

            if not mesh.validate():
                logger.warning("Terrain mesh validation failed")
                return False

            # Upload to GPU
            if not self._headless and self._graphics_system:
                logger.debug("Uploading terrain mesh to GPU...")
                gpu_mesh = self._graphics_system.upload_mesh(mesh)
                if gpu_mesh.is_valid():
                    self._meshes[name] = gpu_mesh
                    logger.debug(f"Terrain mesh uploaded: vertex_count={gpu_mesh.vertex_count}, "
                                f"index_count={gpu_mesh.index_count}")
                    return True
                logger.error("GPU mesh is not valid after upload!")
                return False
            else:
                logger.debug("Storing terrain mesh as placeholder (headless mode)")
                self._meshes[name] = {
                    "type": "terrain",
                    "mesh": mesh,
                    "width": heightmap.shape[1],
                    "height": heightmap.shape[0],
                }
                return True

        except (ImportError, AttributeError) as e:
            logger.warning(f"C++ terrain mesh generation failed: {e}")
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
        entity_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create and upload an entity mesh.

        Parameters
        ----------
        name:
            Unique name for the entity mesh.
        entity_type:
            Type of entity (player, npc, rock, tree, building, etc.).
        entity_state:
            Optional entity state dict with descriptor parameters
            (e.g. L-system params for trees, radius for rocks).

        Returns
        -------
        bool:
            True if uploaded successfully.
        """
        try:
            import procengine_cpp as cpp

            # Select appropriate mesh based on entity type
            if entity_type in ("player", "npc", "character"):
                # Capsule for humanoid characters (radius, height, segments, rings)
                mesh = cpp.generate_capsule_mesh(0.5, 1.5, 16, 8)
            elif entity_type == "rock":
                desc = cpp.RockDescriptor()
                desc.position = cpp.Vec3(0, 0, 0)
                desc.radius = 0.5
                if entity_state:
                    desc.noise_seed = int(entity_state.get("noise_seed", 0))
                    desc.noise_scale = float(entity_state.get("noise_scale", 0.15))
                mesh = cpp.generate_rock_mesh(desc)
            elif entity_type == "tree":
                if entity_state and "axiom" in entity_state:
                    # Build proper L-system tree mesh from entity state
                    desc = cpp.create_tree_from_dict({
                        "axiom": entity_state["axiom"],
                        "rules": entity_state.get("rules", {"F": "F[+F]F[-F]F"}),
                        "angle": entity_state.get("angle", 25.0),
                        "iterations": min(entity_state.get("iterations", 2), 4),
                    })
                    mesh = cpp.generate_tree_mesh(desc)
                else:
                    # Fallback cylinder if no L-system state available
                    mesh = cpp.generate_cylinder_mesh(0.2, 3.0, 16)
            elif entity_type == "building":
                # Box for buildings
                mesh = cpp.generate_box_mesh(cpp.Vec3(3, 2, 3))
            else:
                # Default small box
                mesh = cpp.generate_box_mesh(cpp.Vec3(0.5, 0.5, 0.5))

            # Set entity-specific uniform color for the mesh
            color_tuple = ENTITY_COLORS.get(entity_type, DEFAULT_ENTITY_COLOR)
            entity_color = cpp.Vec3(color_tuple[0], color_tuple[1], color_tuple[2])

            # Debug: log mesh state before and after setting color
            vertex_count_before = len(mesh.vertices)
            color_count_before = len(mesh.colors)

            mesh.set_uniform_color(entity_color)

            # Ensure colors array is properly sized (safety measure)
            mesh.ensure_colors()

            color_count_after = len(mesh.colors)
            print(f"Entity mesh '{entity_type}': vertices={vertex_count_before}, "
                  f"colors before={color_count_before}, colors after={color_count_after}, "
                  f"target color=({color_tuple[0]:.2f}, {color_tuple[1]:.2f}, {color_tuple[2]:.2f})")

            # Validate mesh
            if not mesh.validate():
                logger.warning(f"Mesh validation failed for entity type '{entity_type}': "
                              f"vertices={len(mesh.vertices)}, indices={len(mesh.indices)}")
                # Don't return False - try to upload anyway, GPU might accept it

            # Upload to GPU if graphics available
            if not self._headless and self._graphics_system:
                try:
                    gpu_mesh = self._graphics_system.upload_mesh(mesh)
                    if gpu_mesh.is_valid():
                        self._meshes[name] = gpu_mesh
                        logger.debug(f"Entity mesh '{name}' uploaded: {gpu_mesh.vertex_count} vertices")
                        return True
                    logger.warning(f"GPU mesh invalid after upload for '{name}'")
                    return False
                except Exception as e:
                    logger.error(f"Exception uploading mesh '{name}': {e}")
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

    def destroy_mesh(self, name: str) -> bool:
        """Destroy a mesh and free GPU resources.

        Handles two mesh resource patterns:
        - GPU mesh objects with a `destroy()` method (C++ GPU mesh handles)
        - Graphics system centralized destruction via `destroy_mesh(mesh)`

        In headless mode, simply removes the mesh reference without GPU cleanup.

        Parameters
        ----------
        name:
            Name of the mesh to destroy.

        Returns
        -------
        bool:
            True if the mesh was found and destroyed.
        """
        if name not in self._meshes:
            return False

        mesh = self._meshes.pop(name)

        # GPU mesh cleanup - only needed when not in headless mode
        # Supports two C++ binding patterns for flexibility:
        # 1. Mesh object with destroy() method (resource-owning handle)
        # 2. Graphics system destroy_mesh() method (system-managed resources)
        if not self._headless and self._graphics_system:
            try:
                if hasattr(mesh, 'destroy'):
                    mesh.destroy()
                elif hasattr(self._graphics_system, 'destroy_mesh'):
                    self._graphics_system.destroy_mesh(mesh)
            except Exception as e:
                logger.warning(f"Error destroying mesh '{name}': {e}")

        return True

    def unload_chunk_mesh(self, chunk_coord: Tuple[int, int]) -> bool:
        """Unload a terrain chunk mesh by its coordinates.

        Convenience method for chunk-based world systems.

        Parameters
        ----------
        chunk_coord:
            Chunk coordinates (x, z).

        Returns
        -------
        bool:
            True if the mesh was found and destroyed.
        """
        mesh_name = f"terrain_{chunk_coord[0]}_{chunk_coord[1]}"
        return self.destroy_mesh(mesh_name)

    def has_mesh(self, name: str) -> bool:
        """Check if a mesh exists.

        Parameters
        ----------
        name:
            Name of the mesh to check.

        Returns
        -------
        bool:
            True if the mesh exists.
        """
        return name in self._meshes

    def get_loaded_mesh_count(self) -> int:
        """Get the number of loaded meshes.

        Returns
        -------
        int:
            Number of meshes currently loaded.
        """
        return len(self._meshes)

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
            logger.debug(f"draw_mesh: mesh={mesh_name}, pipeline={pipeline_name}, "
                        f"mesh_type={type(mesh).__name__ if mesh else 'None'}, "
                        f"pipeline_type={type(pipeline).__name__ if pipeline else 'None'}")

        if mesh is None or pipeline is None:
            if self._render_state.frame_count < 5:
                logger.debug(f"draw_mesh SKIPPED: mesh={mesh is not None}, pipeline={pipeline is not None}")
            return

        # Skip if mesh is a placeholder dict (not a real GPU mesh)
        if isinstance(mesh, dict):
            # Placeholder mesh - just count the draw call for headless stats
            self._render_state.draw_calls += 1
            if self._render_state.frame_count < 5:
                logger.debug("draw_mesh SKIPPED: mesh is placeholder dict")
            return

        # Skip if pipeline is a placeholder dict
        if isinstance(pipeline, dict):
            self._render_state.draw_calls += 1
            if self._render_state.frame_count < 5:
                logger.debug("draw_mesh SKIPPED: pipeline is placeholder dict")
            return

        if transform is None:
            transform = create_identity_matrix()

        self._render_state.draw_calls += 1

        if not self._headless and self._graphics_system:
            if self._render_state.frame_count < 5:
                logger.debug("draw_mesh: calling graphics_system.draw_mesh()")
            self._graphics_system.draw_mesh(mesh, pipeline, transform)
        elif self._render_state.frame_count < 5:
            logger.debug(f"draw_mesh SKIPPED: headless={self._headless}")

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
