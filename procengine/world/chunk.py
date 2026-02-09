"""Chunk data structure and ChunkManager for infinite world support.

This module provides the core infrastructure for dynamic chunk-based world
generation, enabling infinite procedural terrain with player-centered loading
and unloading. The system separates render distance from simulation distance
to optimize both visual fidelity and performance.

The chunk system integrates with the existing SeedRegistry for deterministic
terrain generation - revisiting the same chunk coordinates will always produce
identical terrain and props.

Example
-------
>>> from procengine.world.chunk import ChunkManager, Chunk
>>> from procengine.core.seed_registry import SeedRegistry
>>>
>>> manager = ChunkManager(
...     seed_registry=SeedRegistry(42),
...     chunk_size=64,
...     render_distance=8,
...     sim_distance=4,
... )
>>> manager.update_player_position(100.0, 200.0)  # x, z in world coordinates
>>> for chunk in manager.get_render_chunks():
...     print(f"Render chunk at {chunk.coords}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, TYPE_CHECKING
import math

import numpy as np

from procengine.core.seed_registry import SeedRegistry
from procengine.world.terrain import generate_terrain_maps

if TYPE_CHECKING:
    from procengine.physics import HeightField2D

__all__ = [
    "Chunk",
    "ChunkCoord",
    "ChunkManager",
    "ChunkedHeightField",
]

# Type alias for chunk coordinates (x, z in chunk space)
ChunkCoord = Tuple[int, int]


@dataclass
class Chunk:
    """Data container for a single world chunk.

    A chunk represents a square region of the world containing terrain data,
    entity references, and rendering state. Chunks are identified by their
    coordinates in chunk space (not world space).

    Attributes
    ----------
    coords : ChunkCoord
        The (x, z) coordinates in chunk space.
    heightmap : np.ndarray | None
        2D array of terrain heights (size x size).
    biome_map : np.ndarray | None
        2D array of biome indices (uint8).
    river_map : np.ndarray | None
        2D array of river flags (uint8).
    slope_map : np.ndarray | None
        Optional 2D array of terrain slope values.
    mesh_id : str
        Unique identifier for the GPU mesh resource.
    entity_ids : Set[str]
        IDs of entities located within this chunk.
    pending_props : List[Dict[str, Any]]
        Prop descriptors waiting to be spawned as entities.
    is_loaded : bool
        Whether the chunk data has been fully generated.
    is_mesh_uploaded : bool
        Whether the chunk mesh is currently on the GPU.
    is_simulating : bool
        Whether entities in this chunk should be physics-stepped.
    has_props : bool
        Whether props have been generated for this chunk.
    """

    coords: ChunkCoord
    heightmap: Optional[np.ndarray] = None
    biome_map: Optional[np.ndarray] = None
    river_map: Optional[np.ndarray] = None
    slope_map: Optional[np.ndarray] = None
    mesh_id: str = ""
    entity_ids: Set[str] = field(default_factory=set)
    pending_props: List[Dict[str, Any]] = field(default_factory=list)
    is_loaded: bool = False
    is_mesh_uploaded: bool = False
    is_simulating: bool = False
    has_props: bool = False

    def __post_init__(self) -> None:
        """Generate mesh_id from coords if not provided."""
        if not self.mesh_id:
            self.mesh_id = f"terrain_{self.coords[0]}_{self.coords[1]}"

    def world_origin(self, chunk_size: int) -> Tuple[float, float]:
        """Get the world-space origin (x, z) of this chunk.

        Parameters
        ----------
        chunk_size : int
            The size of a chunk in world units.

        Returns
        -------
        Tuple[float, float]
            World coordinates (x, z) of the chunk's corner.
        """
        return (self.coords[0] * chunk_size, self.coords[1] * chunk_size)

    def contains_world_position(
        self, x: float, z: float, chunk_size: int
    ) -> bool:
        """Check if a world position falls within this chunk.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.
        chunk_size : int
            The size of a chunk in world units.

        Returns
        -------
        bool
            True if the position is inside this chunk.
        """
        ox, oz = self.world_origin(chunk_size)
        return ox <= x < ox + chunk_size and oz <= z < oz + chunk_size


class ChunkManager:
    """Manages dynamic loading/unloading of world chunks around the player.

    The ChunkManager tracks which chunks should be loaded, generated,
    and rendered based on player position. It maintains separate distances
    for rendering (visual) and simulation (physics/AI) to optimize
    performance.

    Parameters
    ----------
    seed_registry : SeedRegistry
        The root seed registry for deterministic chunk generation.
    chunk_size : int
        Size of each chunk in world units (default 64).
    render_distance : int
        Radius in chunks for rendering (default 8).
    sim_distance : int
        Radius in chunks for physics simulation (default 4).
    unload_buffer : int
        Extra distance before unloading chunks (default 2).

    Attributes
    ----------
    chunks : Dict[ChunkCoord, Chunk]
        Active chunks indexed by their coordinates.
    render_distance : int
        Current render distance in chunks.
    sim_distance : int
        Current simulation distance in chunks.
    """

    def __init__(
        self,
        seed_registry: SeedRegistry,
        chunk_size: int = 64,
        render_distance: int = 6,
        sim_distance: int = 3,
        unload_buffer: int = 2,
    ) -> None:
        self._registry = seed_registry
        self._chunk_size = chunk_size
        self._render_distance = render_distance
        self._sim_distance = sim_distance
        self._unload_buffer = unload_buffer

        # Active chunks storage
        self._chunks: Dict[ChunkCoord, Chunk] = {}

        # Player chunk position (updated each frame)
        self._player_chunk: ChunkCoord = (0, 0)

        # Queues for async loading/unloading
        self._load_queue: List[ChunkCoord] = []
        self._unload_queue: List[ChunkCoord] = []

        # FIX: Prop generation distance (defaults to half render distance)
        self._prop_distance = max(1, render_distance // 2)
        self._props_queue: List[ChunkCoord] = []

        # Global terrain registry for consistent terrain across all chunks.
        # This ensures the same world coordinate produces the same noise value
        # regardless of which chunk generates it, enabling seamless edges.
        self._terrain_registry = seed_registry.spawn("global_terrain")

        # Statistics
        self._chunks_generated: int = 0
        self._chunks_unloaded: int = 0

    @property
    def chunks(self) -> Dict[ChunkCoord, Chunk]:
        """Get all active chunks."""
        return self._chunks

    @property
    def chunk_size(self) -> int:
        """Get the chunk size in world units."""
        return self._chunk_size

    @property
    def render_distance(self) -> int:
        """Get the render distance in chunks."""
        return self._render_distance

    @render_distance.setter
    def render_distance(self, value: int) -> None:
        """Set the render distance (triggers chunk updates on next update)."""
        self._render_distance = max(1, value)

    @property
    def sim_distance(self) -> int:
        """Get the simulation distance in chunks."""
        return self._sim_distance

    @sim_distance.setter
    def sim_distance(self, value: int) -> None:
        """Set the simulation distance."""
        self._sim_distance = max(1, min(value, self._render_distance))

    @property
    def player_chunk(self) -> ChunkCoord:
        """Get the chunk coordinates the player is currently in."""
        return self._player_chunk

    def world_to_chunk(self, x: float, z: float) -> ChunkCoord:
        """Convert world coordinates to chunk coordinates.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.

        Returns
        -------
        ChunkCoord
            The chunk coordinates containing this world position.
        """
        cx = int(math.floor(x / self._chunk_size))
        cz = int(math.floor(z / self._chunk_size))
        return (cx, cz)

    def chunk_to_world(self, coord: ChunkCoord) -> Tuple[float, float]:
        """Convert chunk coordinates to world origin.

        Parameters
        ----------
        coord : ChunkCoord
            Chunk coordinates.

        Returns
        -------
        Tuple[float, float]
            World coordinates (x, z) of the chunk's origin.
        """
        return (coord[0] * self._chunk_size, coord[1] * self._chunk_size)

    def update_player_position(self, world_x: float, world_z: float) -> None:
        """Update the player's position and compute chunks to load/unload.

        This method should be called each frame (or periodically) with the
        player's current world position. It calculates which chunks need
        to be loaded or unloaded based on the current render and simulation
        distances.

        Parameters
        ----------
        world_x : float
            Player's world X coordinate.
        world_z : float
            Player's world Z coordinate.
        """
        new_chunk = self.world_to_chunk(world_x, world_z)

        # Only recalculate if player moved to a different chunk
        if new_chunk == self._player_chunk and len(self._chunks) > 0:
            return

        self._player_chunk = new_chunk

        # Calculate which chunks should be visible
        render_set = self._get_chunks_in_radius(new_chunk, self._render_distance)
        sim_set = self._get_chunks_in_radius(new_chunk, self._sim_distance)
        unload_threshold = self._render_distance + self._unload_buffer

        # Determine chunks to load, sorted closest-first so the area
        # around the player fills in before distant chunks.
        current_coords = set(self._chunks.keys())
        px, pz = new_chunk
        self._load_queue = sorted(
            (c for c in render_set if c not in current_coords),
            key=lambda c: (c[0] - px) ** 2 + (c[1] - pz) ** 2,
        )

        # Determine chunks to unload (outside render + buffer)
        unload_set = self._get_chunks_outside_radius(
            new_chunk, unload_threshold, current_coords
        )
        self._unload_queue = list(unload_set)

        # Update simulation flags on existing chunks
        for coord, chunk in self._chunks.items():
            chunk.is_simulating = coord in sim_set

        # FIX: Check for loaded chunks that entered prop range but lack props
        prop_radius_sq = self._prop_distance ** 2
        for coord, chunk in self._chunks.items():
            if not chunk.has_props:
                dx = coord[0] - new_chunk[0]
                dz = coord[1] - new_chunk[1]
                if dx * dx + dz * dz <= prop_radius_sq:
                    if coord not in self._props_queue:
                        self._props_queue.append(coord)

    def sync_player_chunk(self, world_x: float, world_z: float) -> None:
        """Update player chunk tracking without modifying load/unload queues.

        Used when an external system (C++ GameManager) handles chunk
        generation and lifecycle.  This keeps sim/render distance filtering
        consistent so that ``get_render_chunks()`` and ``get_sim_chunks()``
        return the correct set of chunks.

        Parameters
        ----------
        world_x : float
            Player's world X coordinate.
        world_z : float
            Player's world Z coordinate.
        """
        new_chunk = self.world_to_chunk(world_x, world_z)
        self._player_chunk = new_chunk

        sim_set = self._get_chunks_in_radius(new_chunk, self._sim_distance)
        for coord, chunk in self._chunks.items():
            chunk.is_simulating = coord in sim_set

        # Check for loaded chunks that entered prop range but lack props
        prop_radius_sq = self._prop_distance ** 2
        for coord, chunk in self._chunks.items():
            if not chunk.has_props:
                dx = coord[0] - new_chunk[0]
                dz = coord[1] - new_chunk[1]
                if dx * dx + dz * dz <= prop_radius_sq:
                    if coord not in self._props_queue:
                        self._props_queue.append(coord)

    def _get_chunks_in_radius(
        self, center: ChunkCoord, radius: int
    ) -> Set[ChunkCoord]:
        """Get all chunk coordinates within radius of center.

        Uses circular distance check to avoid loading corner chunks that
        are farther away than the specified radius.
        """
        result: Set[ChunkCoord] = set()
        radius_sq = radius * radius
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                # Use circular check instead of square
                dist_sq = dx * dx + dz * dz
                if dist_sq <= radius_sq:
                    result.add((center[0] + dx, center[1] + dz))
        return result

    def _get_chunks_outside_radius(
        self, center: ChunkCoord, radius: int, candidates: Set[ChunkCoord]
    ) -> Set[ChunkCoord]:
        """Get chunks from candidates that are outside the radius.

        Uses circular distance check consistent with _get_chunks_in_radius.
        """
        result: Set[ChunkCoord] = set()
        radius_sq = radius * radius
        for coord in candidates:
            dx = coord[0] - center[0]
            dz = coord[1] - center[1]
            dist_sq = dx * dx + dz * dz
            if dist_sq > radius_sq:
                result.add(coord)
        return result

    def process_load_queue(self, max_per_frame: int = 1) -> List[Chunk]:
        """Process pending chunk loads (call once per frame).

        Generates terrain data for queued chunks. To avoid frame stutters,
        this method limits how many chunks are processed per call.

        Parameters
        ----------
        max_per_frame : int
            Maximum chunks to generate this frame (default 1).

        Returns
        -------
        List[Chunk]
            Newly generated chunks that need mesh upload.
        """
        generated: List[Chunk] = []

        # Pre-calculate sim set once for the batch instead of per-chunk
        sim_set = self._get_chunks_in_radius(self._player_chunk, self._sim_distance)

        for _ in range(min(max_per_frame, len(self._load_queue))):
            if not self._load_queue:
                break

            coord = self._load_queue.pop(0)
            if coord in self._chunks:
                continue  # Already loaded

            chunk = self._generate_chunk(coord)

            # Set simulation flag based on current player position
            chunk.is_simulating = coord in sim_set

            self._chunks[coord] = chunk
            generated.append(chunk)
            self._chunks_generated += 1

        return generated

    def process_unload_queue(self, max_per_frame: int = 2) -> List[Chunk]:
        """Process pending chunk unloads (call once per frame).

        Returns chunks that should have their GPU resources freed.

        Parameters
        ----------
        max_per_frame : int
            Maximum chunks to unload this frame (default 2).

        Returns
        -------
        List[Chunk]
            Chunks that were removed and need GPU cleanup.
        """
        unloaded: List[Chunk] = []

        for _ in range(min(max_per_frame, len(self._unload_queue))):
            if not self._unload_queue:
                break

            coord = self._unload_queue.pop(0)
            if coord not in self._chunks:
                continue

            chunk = self._chunks.pop(coord)
            unloaded.append(chunk)
            self._chunks_unloaded += 1

        return unloaded

    def process_prop_queue(self, max_per_frame: int = 1) -> List[Chunk]:
        """Generate props for chunks that have entered prop range.

        This method processes chunks that were initially loaded without props
        (because they were outside prop_distance) but have since entered
        the prop generation range due to player movement.

        Parameters
        ----------
        max_per_frame : int
            Maximum chunks to process this frame (default 1).

        Returns
        -------
        List[Chunk]
            Chunks that had props generated.
        """
        updated_chunks: List[Chunk] = []
        for _ in range(min(max_per_frame, len(self._props_queue))):
            if not self._props_queue:
                break

            coord = self._props_queue.pop(0)
            chunk = self._chunks.get(coord)

            if chunk and not chunk.has_props:
                # Regenerate props using deterministic seed
                chunk_name = f"chunk_{coord[0]}_{coord[1]}"
                chunk_registry = self._registry.spawn(chunk_name)

                from procengine.world.props import generate_chunk_props

                # Slice the maps to original chunk_size for props.
                # Heightmaps are generated with size+1 for vertex overlap,
                # but props should only spawn within [0, chunk_size) bounds.
                height_for_props = chunk.heightmap[:self._chunk_size, :self._chunk_size]
                slope_for_props = chunk.slope_map[:self._chunk_size, :self._chunk_size] if chunk.slope_map is not None else None
                biome_for_props = chunk.biome_map[:self._chunk_size, :self._chunk_size] if chunk.biome_map is not None else None

                chunk.pending_props = generate_chunk_props(
                    chunk_registry,
                    self._chunk_size,
                    height_for_props,
                    slope_for_props,
                    biome_for_props,
                )
                chunk.has_props = True
                updated_chunks.append(chunk)

        return updated_chunks

    def _generate_chunk(self, coord: ChunkCoord) -> Chunk:
        """Generate terrain data for a chunk at the given coordinates.

        Uses the SeedRegistry to ensure deterministic generation -
        the same coordinates will always produce the same terrain and props.

        Parameters
        ----------
        coord : ChunkCoord
            The chunk coordinates to generate.

        Returns
        -------
        Chunk
            A new Chunk with generated terrain data and pending props.

        Notes
        -----
        The chunk generates terrain with size+1 vertices to ensure seamless
        mesh stitching. If a chunk is 64 units wide, it needs 65 vertices
        (0 to 64) to enclose 64 quads. Vertex 64 of Chunk A is physically
        coincident with Vertex 0 of Chunk B.

        Terrain uses a global registry to ensure the same world coordinate
        produces the same noise value regardless of which chunk generates it.
        This enables seamless edges where Noise(x=64) in Chunk A equals
        Noise(x=0) in Chunk B.
        """
        # Create a deterministic seed registry for chunk-specific things (props)
        chunk_name = f"chunk_{coord[0]}_{coord[1]}"
        chunk_registry = self._registry.spawn(chunk_name)

        # Calculate offsets based on chunk size
        # This assumes chunk (1,0) should start noise where chunk (0,0) ended
        offset_x = float(coord[0] * self._chunk_size)
        offset_z = float(coord[1] * self._chunk_size)

        # Request size + 1 to generate overlap vertices.
        # This closes the physical gap between meshes by ensuring the right
        # edge of this chunk contains the exact same data as the left edge
        # of the adjacent chunk.
        gen_size = self._chunk_size + 1

        # Use global terrain registry for consistent terrain across all chunks.
        # This ensures seamless chunk boundaries by using the same noise
        # permutation table for all terrain generation.
        maps = generate_terrain_maps(
            self._terrain_registry,
            size=gen_size,
            octaves=6,
            macro_points=0, # Disable macro points for now as they can cause seams
            erosion_iters=0, # Disable erosion for now as it simulates locally
            return_slope=True,
            offset_x=offset_x,
            offset_z=offset_z,
        )

        height, biome, river, slope = maps

        # FIX: Check if chunk is within prop generation range
        player_x, player_y = self._player_chunk
        dist_sq = (coord[0] - player_x) ** 2 + (coord[1] - player_y) ** 2

        prop_descriptors: List[Dict[str, Any]] = []
        has_props = False
        # Only generate props if within prop_distance
        if dist_sq <= self._prop_distance ** 2:
            from procengine.world.props import generate_chunk_props

            # Slice the maps to original size for props.
            # We don't want props spawning on the overlap edge (index chunk_size)
            # because the neighbor chunk will spawn them at index 0.
            # Use chunk_registry for deterministic per-chunk prop generation.
            prop_descriptors = generate_chunk_props(
                chunk_registry,
                self._chunk_size,
                height[:self._chunk_size, :self._chunk_size],
                slope[:self._chunk_size, :self._chunk_size],
                biome[:self._chunk_size, :self._chunk_size],
            )
            has_props = True

        chunk = Chunk(
            coords=coord,
            heightmap=height,
            biome_map=biome,
            river_map=river,
            slope_map=slope,
            pending_props=prop_descriptors,
            is_loaded=True,
            has_props=has_props,
        )

        return chunk

    def get_chunk_at_world(self, x: float, z: float) -> Optional[Chunk]:
        """Get the chunk containing a world position.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.

        Returns
        -------
        Optional[Chunk]
            The chunk at this position, or None if not loaded.
        """
        coord = self.world_to_chunk(x, z)
        return self._chunks.get(coord)

    def get_render_chunks(self) -> List[Chunk]:
        """Get all chunks that should be rendered.

        Returns
        -------
        List[Chunk]
            All loaded chunks within render distance.
        """
        render_set = self._get_chunks_in_radius(
            self._player_chunk, self._render_distance
        )
        return [
            self._chunks[c] for c in render_set
            if c in self._chunks and self._chunks[c].is_loaded
        ]

    def get_sim_chunks(self) -> List[Chunk]:
        """Get all chunks that should be simulated (physics/AI).

        Returns
        -------
        List[Chunk]
            All loaded chunks within simulation distance.
        """
        return [c for c in self._chunks.values() if c.is_simulating]

    def get_load_queue_size(self) -> int:
        """Get the number of chunks waiting to be loaded."""
        return len(self._load_queue)

    def get_unload_queue_size(self) -> int:
        """Get the number of chunks waiting to be unloaded."""
        return len(self._unload_queue)

    def get_stats(self) -> Dict[str, Any]:
        """Get chunk manager statistics.

        Returns
        -------
        Dict[str, Any]
            Statistics about chunks loaded, generated, etc.
        """
        return {
            "active_chunks": len(self._chunks),
            "render_chunks": len(self.get_render_chunks()),
            "sim_chunks": len(self.get_sim_chunks()),
            "load_queue": len(self._load_queue),
            "unload_queue": len(self._unload_queue),
            "total_generated": self._chunks_generated,
            "total_unloaded": self._chunks_unloaded,
            "player_chunk": self._player_chunk,
        }


class ChunkedHeightField:
    """A heightfield that spans multiple chunks for physics queries.

    This class provides a unified height sampling interface across all
    loaded chunks, enabling physics systems to query terrain height at
    any world position without knowing about chunk boundaries.

    Parameters
    ----------
    chunk_manager : ChunkManager
        The chunk manager providing terrain data.
    default_height : float
        Height to return for positions in unloaded chunks (default 0.0).
    height_scale : float
        Scale factor applied to raw heightmap values (default 30.0).
    """

    def __init__(
        self,
        chunk_manager: ChunkManager,
        default_height: float = 0.0,
        height_scale: float = 30.0,
    ) -> None:
        self._manager = chunk_manager
        self._default_height = default_height
        self._height_scale = height_scale

    @property
    def chunk_size(self) -> int:
        """Get the chunk size in world units."""
        return self._manager.chunk_size

    # Multiplier for calculating effective terrain size from render distance.
    # Value of 4 provides coverage for: current chunk + render distance radius + margin
    # for player movement. This is a heuristic value that provides reasonable bounds.
    _SIZE_MULTIPLIER: int = 4

    @property
    def size_x(self) -> int:
        """Number of samples in X direction (virtual/effective size).
        
        For chunked terrain, this returns a large value to indicate
        effectively infinite terrain in the X direction.
        """
        # Return a large value representing loaded chunk coverage
        # The actual terrain extent depends on loaded chunks
        return self._manager.chunk_size * self._manager.render_distance * self._SIZE_MULTIPLIER

    @property
    def size_z(self) -> int:
        """Number of samples in Z direction (virtual/effective size).
        
        For chunked terrain, this returns a large value to indicate
        effectively infinite terrain in the Z direction.
        """
        # Return a large value representing loaded chunk coverage
        return self._manager.chunk_size * self._manager.render_distance * self._SIZE_MULTIPLIER

    def sample(self, x: float, z: float) -> float:
        """Sample terrain height at a world position.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.

        Returns
        -------
        float
            Terrain height at this position, or default_height if unloaded.
        """
        chunk = self._manager.get_chunk_at_world(x, z)
        if chunk is None or chunk.heightmap is None:
            return self._default_height

        # Convert to local chunk coordinates
        size = self._manager.chunk_size
        local_x = x - chunk.coords[0] * size
        local_z = z - chunk.coords[1] * size

        # Get actual heightmap dimensions (may be size+1 for vertex overlap)
        hm_height, hm_width = chunk.heightmap.shape

        # Clamp to valid range (heightmap may have size+1 for overlap)
        ix = int(min(max(local_x, 0), hm_width - 1))
        iz = int(min(max(local_z, 0), hm_height - 1))

        # Sample and scale
        raw_height = chunk.heightmap[iz, ix]
        return float(raw_height) * self._height_scale

    def sample_interpolated(self, x: float, z: float) -> float:
        """Sample terrain height with bilinear interpolation.

        Provides smoother results than point sampling for physics.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.

        Returns
        -------
        float
            Interpolated terrain height.
        """
        chunk = self._manager.get_chunk_at_world(x, z)
        if chunk is None or chunk.heightmap is None:
            return self._default_height

        size = self._manager.chunk_size
        local_x = x - chunk.coords[0] * size
        local_z = z - chunk.coords[1] * size

        # Get actual heightmap dimensions (may be size+1 for vertex overlap)
        hm_height, hm_width = chunk.heightmap.shape

        # Get the four surrounding points
        x0 = int(math.floor(local_x))
        z0 = int(math.floor(local_z))
        x1 = min(x0 + 1, hm_width - 1)
        z1 = min(z0 + 1, hm_height - 1)
        x0 = max(x0, 0)
        z0 = max(z0, 0)

        # Interpolation weights
        fx = local_x - x0
        fz = local_z - z0

        # Sample four corners
        h = chunk.heightmap
        h00 = float(h[z0, x0])
        h10 = float(h[z0, x1])
        h01 = float(h[z1, x0])
        h11 = float(h[z1, x1])

        # Bilinear interpolation
        h0 = h00 * (1 - fx) + h10 * fx
        h1 = h01 * (1 - fx) + h11 * fx
        height = h0 * (1 - fz) + h1 * fz

        return height * self._height_scale

    def get_normal(self, x: float, z: float) -> Tuple[float, float, float]:
        """Compute the surface normal at a world position.

        Parameters
        ----------
        x : float
            World X coordinate.
        z : float
            World Z coordinate.

        Returns
        -------
        Tuple[float, float, float]
            Normalized surface normal (nx, ny, nz).
        """
        # Sample heights for gradient calculation
        delta = 0.5
        h_center = self.sample(x, z)
        h_right = self.sample(x + delta, z)
        h_forward = self.sample(x, z + delta)

        # Compute tangent vectors
        tx = delta
        ty = h_right - h_center
        tz = 0.0

        bx = 0.0
        by = h_forward - h_center
        bz = delta

        # Cross product for normal
        nx = ty * bz - tz * by
        ny = tz * bx - tx * bz
        nz = tx * by - ty * bx

        # Normalize
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length > 0.0001:
            nx /= length
            ny /= length
            nz /= length
        else:
            nx, ny, nz = 0.0, 1.0, 0.0

        return (nx, ny, nz)
